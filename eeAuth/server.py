"""FastAPI proxy for Earth Engine that injects per-tenant SA tokens.

The proxy receives requests from EE clients (browser JS, Python SDK
via ``geeViz.eeAuth.client``), looks up the requested tenant in the SA
registry, mints a token (cached), and forwards to the real EE endpoint
with the right ``Authorization`` and ``x-goog-user-project`` headers.

Two ways to use:

1. **Standalone**::

       python -m geeViz.eeAuth --port 8888

   or programmatically::

       from geeViz.eeAuth.server import create_proxy_app
       app = create_proxy_app()
       # serve with uvicorn / etc.

2. **Mounted in an existing FastAPI app**::

       from fastapi import FastAPI
       from geeViz.eeAuth.server import build_proxy_router

       app = FastAPI()
       app.include_router(build_proxy_router(), prefix="/ee-api")

Tenant routing — the proxy picks the SA in this order:

1. ``X-geeViz-Creds`` request header (server-side EE SDK; set by
   ``geeViz.eeAuth.client.TenantAwareHttp``).
2. ``?tenant=`` query string parameter (browser map iframes).
3. Default tenant (the registry's ``default`` entry, loaded from
   ``GEE_SERVICE_ACCOUNT_B64``).

Workload tagging — every POST is stamped with a workload tag
``ee-proxy__<tenant>`` in the query string for billing attribution.
Pass ``workload_tag_builder=...`` to ``build_proxy_router`` if you want
to construct your own tag (e.g. include user / session).
"""
from __future__ import annotations

import logging
import os
from typing import Callable, Optional
from urllib.parse import parse_qsl, urlencode

from fastapi import APIRouter, FastAPI, Request, Response

from .registry import get_registry
from .tags import build_workload_tag

logger = logging.getLogger(__name__)

# Default upstream — EE serves compute + maps from content-earthengine.
# value:compute also works at earthengine.googleapis.com, but
# content-earthengine accepts both, so we route everything there.
DEFAULT_UPSTREAM = "https://content-earthengine.googleapis.com"

# Header the proxy expects for routing. Default is geeViz-branded so it's
# obviously library-owned in browser DevTools / packet captures; override
# per-deployment via ``build_proxy_router(tenant_header=...)``. The agent
# uses ``X-AskTerra-Tenant`` for back-compat with iframe URLs already in
# production. Both sides (client transport + proxy router) must use the
# SAME value — the library's defaults match by convention.
DEFAULT_TENANT_HEADER = "X-geeViz-Creds"


# Headers we never forward to upstream — they're either hop-by-hop, leak
# our infrastructure (IAP, forwarding proxies), or are our own internal
# routing signals that EE would reject.
_STRIPPED_HEADERS = frozenset({
    "host", "content-length", "authorization",
    "x-forwarded-for", "x-forwarded-proto", "x-forwarded-host", "x-real-ip",
    "x-goog-authenticated-user-email", "x-goog-authenticated-user-id",
    "x-goog-iap-jwt-assertion",
    # Stripped because the server sets its own — what the client claims is irrelevant.
    "x-goog-user-project",
})


def _default_tenant_resolver(
    request: Request, tenant_header: str
) -> str:
    """Read tenant from header, then query param. Returns ``""`` if
    neither present — the registry's default tenant will be used."""
    t = request.headers.get(tenant_header, "").strip().lower()
    if t:
        return t
    return (request.query_params.get("tenant", "") or "").strip().lower()


def _default_workload_tag_builder(
    request: Request, tenant: str
) -> str:
    """Build a simple workload tag from the tenant. Override for richer
    attribution (e.g. include user / session from your own headers)."""
    parts = ["ee-proxy"]
    if tenant:
        parts.append(tenant)
    return build_workload_tag(*parts)


def _rewrite_query_with_workload_tag(
    query: str,
    tenant: str,
    workload_tag_builder: Callable[[Request, str], str],
    request: Request,
    tenant_query_param: str,
) -> str:
    """Strip any client-set workloadTag and tenant query param; add our
    own workload tag if a tag builder produced one."""
    try:
        tag = workload_tag_builder(request, tenant)
    except Exception:
        logger.exception("ee-proxy: workload_tag_builder failed")
        tag = ""
    pairs = [
        (k, v) for k, v in parse_qsl(query or "", keep_blank_values=True)
        if k != "workloadTag" and k != tenant_query_param
    ]
    if tag:
        pairs.append(("workloadTag", tag))
    return urlencode(pairs)


def build_proxy_router(
    creds=None,
    upstream: str = DEFAULT_UPSTREAM,
    tenant_header: str = DEFAULT_TENANT_HEADER,
    tenant_query_param: str = "tenant",
    tenant_resolver: Optional[Callable[[Request, str], str]] = None,
    workload_tag_builder: Optional[Callable[[Request, str], str]] = None,
) -> APIRouter:
    """Build a FastAPI ``APIRouter`` that handles ``{path:path}`` and
    proxies every request to ``upstream`` with the right SA token.

    Args:
        creds: Object exposing ``get_token(tenant, force_refresh=False)
            -> {access_token, project_id, tenant, ...}``. Accepts an
            :class:`EECreds` instance, an :class:`SARegistry`, or any
            other object with the same interface. ``None`` (default)
            uses the process-wide env-var registry (legacy).
        upstream: Base URL of the real EE API.
            ``content-earthengine.googleapis.com`` works for both maps
            and compute. ``earthengine.googleapis.com`` is also accepted
            for most endpoints.
        tenant_header: Header name to read for routing. Default
            ``X-geeViz-Creds``. Must match the client side.
        tenant_query_param: Query string key to read for tenant routing
            (browser iframe pattern). Default ``"tenant"``. Stripped
            from the outbound URL so EE never sees it.
        tenant_resolver: Custom function ``(request) -> str`` to pick
            the tenant. Override for richer auth schemes (e.g. resolve
            via IAP email lookup). Default reads ``tenant_header`` then
            ``tenant_query_param``.
        workload_tag_builder: Custom function ``(request, tenant) -> str``
            that returns the workload tag for billing attribution.
            Returning ``""`` disables tagging on this request. Default
            builds ``ee-proxy__<tenant>``.

    Mount the returned router on whatever prefix you like — typically
    ``/ee-api``.
    """
    upstream = upstream.rstrip("/")
    resolver = tenant_resolver or (
        lambda r: _default_tenant_resolver(r, tenant_header)
    )
    tag_builder = workload_tag_builder or _default_workload_tag_builder

    # Shared async HTTP client. Opening a new ``httpx.AsyncClient`` per
    # request — which the original code did — costs a fresh TLS handshake
    # to ``content-earthengine.googleapis.com`` on every EE call (50-150ms
    # round-trips that pile up fast when the map viewer fires N parallel
    # ``value:compute`` queries per layer). One shared client per router
    # keeps connections in a pool and reuses them. ``http2=True`` because
    # EE supports it and HTTP/2 multiplexing further reduces head-of-line
    # blocking for parallel requests on a single connection.
    import httpx as _httpx
    upstream_client = _httpx.AsyncClient(
        timeout=_httpx.Timeout(120.0, connect=10.0),
        follow_redirects=False,
        limits=_httpx.Limits(
            max_keepalive_connections=64,
            max_connections=128,
            keepalive_expiry=60.0,
        ),
    )

    def _resolve_creds():
        """Resolve the credential source for each request. Honours the
        ``creds`` argument when provided, else falls back to the
        env-var registry singleton — both expose ``get_token`` so the
        proxy code below doesn't care which is in use."""
        if creds is not None:
            return creds
        return get_registry()

    router = APIRouter()

    @router.api_route(
        "/{path:path}",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
    )
    async def ee_proxy(path: str, request: Request) -> Response:
        import httpx

        # 1. Resolve tenant + mint a token from the credential source.
        tenant = resolver(request)
        registry = _resolve_creds()
        try:
            tok = registry.get_token(tenant or None)
        except KeyError as e:
            return Response(
                content=f"tenant routing failed: {e}",
                status_code=400,
            )
        except Exception as e:
            logger.exception("ee-proxy: token mint failed (tenant=%r)", tenant)
            return Response(content=f"auth mint failed: {e}", status_code=500)

        actual_tenant = tok.get("tenant", tenant or "default")
        access_token = tok["access_token"]
        quota_project = (
            tok.get("project_id")
            or os.environ.get("GEE_PROJECT", "")
        )

        # 2. Rewrite the query string: strip client-set workloadTag and
        #    the internal tenant param; add our own workload tag on POSTs.
        #    GET requests can't carry unknown query params on most EE
        #    endpoints, so we just strip there without adding.
        if request.method == "POST":
            rewritten_query = _rewrite_query_with_workload_tag(
                request.url.query or "",
                actual_tenant,
                tag_builder,
                request,
                tenant_query_param,
            )
        else:
            rewritten_query = urlencode([
                (k, v) for k, v in parse_qsl(
                    request.url.query or "", keep_blank_values=True
                )
                if k != "workloadTag" and k != tenant_query_param
            ])
        upstream_url = f"{upstream}/{path}"
        if rewritten_query:
            upstream_url = f"{upstream_url}?{rewritten_query}"

        # 3. Forward headers — strip hop-by-hop, auth, IAP, and our own
        #    tenant routing header (must never leak to EE).
        stripped = set(_STRIPPED_HEADERS)
        stripped.add(tenant_header.lower())
        fwd_headers = {}
        for k, v in request.headers.items():
            if k.lower() in stripped:
                continue
            fwd_headers[k] = v
        fwd_headers["authorization"] = f"Bearer {access_token}"
        # ``$discovery/rest`` is the googleapiclient discovery doc. EE
        # itself strips quota-project on credentials before fetching it
        # (see ee._cloud_api_utils.build_cloud_resource) because the
        # serviceUsage API rejects discovery requests that carry a
        # consumer project. Mirror that here — without this, SAs that
        # otherwise work fine 403 on init.
        is_discovery = "$discovery/rest" in path
        if quota_project and not is_discovery:
            fwd_headers["x-goog-user-project"] = quota_project

        body = await request.body()

        # 4. Forward + retry once on 401 (token rotation). Uses the
        # shared ``upstream_client`` (keep-alive connection pool) — see
        # the construction above for why we don't create per-request.
        try:
            upstream_resp = await upstream_client.request(
                request.method, upstream_url,
                content=body if body else None,
                headers=fwd_headers,
            )
        except httpx.HTTPError as e:
            logger.exception("ee-proxy: upstream error for %s %s",
                             request.method, path)
            return Response(content=f"upstream error: {e}", status_code=502)

        if upstream_resp.status_code == 401:
            try:
                tok = registry.get_token(actual_tenant, force_refresh=True)
                fwd_headers["authorization"] = f"Bearer {tok['access_token']}"
                qp = (tok.get("project_id")
                      or os.environ.get("GEE_PROJECT", ""))
                if qp and not is_discovery:
                    fwd_headers["x-goog-user-project"] = qp
                upstream_resp = await upstream_client.request(
                    request.method, upstream_url,
                    content=body if body else None,
                    headers=fwd_headers,
                )
            except Exception:
                logger.exception("ee-proxy: retry after 401 failed")

        # 5. Pass through, stripping hop-by-hop and auth-related response
        #    headers that are context-specific to the upstream.
        resp_headers = {}
        for k, v in upstream_resp.headers.items():
            if k.lower() in ("content-encoding", "content-length",
                              "transfer-encoding", "connection", "server"):
                continue
            resp_headers[k] = v
        return Response(
            content=upstream_resp.content,
            status_code=upstream_resp.status_code,
            headers=resp_headers,
            media_type=upstream_resp.headers.get("content-type"),
        )

    return router


def create_proxy_app(
    creds=None,
    upstream: str = DEFAULT_UPSTREAM,
    tenant_header: str = DEFAULT_TENANT_HEADER,
    tenant_query_param: str = "tenant",
    tenant_resolver: Optional[Callable[[Request, str], str]] = None,
    workload_tag_builder: Optional[Callable[[Request, str], str]] = None,
    prefix: str = "/ee-api",
) -> FastAPI:
    """Build a standalone FastAPI app with the proxy mounted at ``prefix``.
    Suitable for direct serving via ``uvicorn`` or for testing.

    ``creds`` accepts an :class:`EECreds` / :class:`SARegistry`-like
    object; ``None`` falls back to the env-var registry. See
    :func:`build_proxy_router` for the other parameters.

    Use ``build_proxy_router`` directly if you want to mount in an
    existing FastAPI app and share its middleware / lifecycle.
    """
    app = FastAPI(title="geeViz EE proxy")
    app.include_router(
        build_proxy_router(
            creds=creds,
            upstream=upstream,
            tenant_header=tenant_header,
            tenant_query_param=tenant_query_param,
            tenant_resolver=tenant_resolver,
            workload_tag_builder=workload_tag_builder,
        ),
        prefix=prefix,
    )

    def _list_tenants() -> list:
        if creds is None:
            return get_registry().list_tenants()
        # EECreds uses list() (insertion order); SARegistry uses list_tenants()
        if hasattr(creds, "list_tenants"):
            return creds.list_tenants()
        return creds.list()

    @app.get("/")
    def _root():
        """Lightweight health check + tenant listing."""
        return {
            "service": "geeViz.eeAuth proxy",
            "tenants_loaded": _list_tenants(),
            "mount_prefix": prefix,
            "upstream": upstream,
            "tenant_header": tenant_header,
        }

    return app
