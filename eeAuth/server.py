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

Workload tagging — every POST is stamped with a workload tag in the
query string for billing attribution. A tag the client already set is
respected; otherwise the default builder mints a short deterministic
``wl_<hex>`` (see ``tags.mint_workload_tag``) over the tenant, cred,
pid, source and whatever caller identity the attribution ContextVars
carried, and records ``tag -> parts`` in the eeCreds ``TagStore`` so
``eeCreds.lookupWorkloadTag(tag)`` can recover them. The legacy
``ee-proxy__<tenant>`` shape survives only as the last-resort fallback
when minting itself raises. Pass ``workload_tag_builder=...`` to
``build_proxy_router`` to own that policy entirely.
"""
from __future__ import annotations

import asyncio
import datetime
import logging
import os
from typing import Callable, Optional
from urllib.parse import parse_qsl, urlencode

# Module-load timestamp — used by the /health probe so detached-mode
# clients can tell how stale a discovered proxy process is.
_PROCESS_STARTED_AT = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from html import escape as _html_escape
from starlette.requests import ClientDisconnect

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
    """Default workload-tag policy for the ee-proxy.

    Rule: **if the client already set a tag** (via
    ``ee.data.setWorkloadTag()`` on the Python side, or baked into a
    tile URL returned by ``getMapId``), respect it. Otherwise mint a
    reversible ``wl_<hex>`` tag that includes richer parts than plain
    ``ee-proxy__<tenant>`` and store the mapping in the eeCreds
    singleton's ``TagStore`` so ``eeCreds.lookupWorkloadTag(tag)`` can
    recover the parts later.

    Caller identity comes from the four ContextVars in
    ``geeViz.eeAuth.client`` — ``CURRENT_USER_EMAIL``,
    ``CURRENT_SESSION_ID``, ``CURRENT_ACTION`` and
    ``CURRENT_BILLING_TENANT``. The first three are read straight out of
    the context and added as ``user_email`` / ``session_id`` / ``action``
    parts. ``CURRENT_BILLING_TENANT`` is different: when set it
    **overrides the ``tenant`` argument**, because that argument is
    whatever ``tenant_resolver`` produced (a credential name such as
    "ee-persistent") while the billing tenant is the deploy-time
    identity that actually pays ("askterra").

    The additive shape is deliberate. Attribution parts join the mint
    ONLY when they are non-empty, so a standalone geeViz install — where
    nobody populates the ContextVars — mints exactly the same 4-part
    (tenant / cred / pid / src) tag it always did. The hash changes only
    when a real caller identity was propagated, which keeps existing
    billing breakdowns stable.

    Custom builders passed via ``workload_tag_builder=...`` skip this
    entirely and own their own policy — see the agent's
    ``TenantAwareHttp`` path for an example.
    """
    # 1. Client-set tag wins. Same rule applies to Python getInfo calls
    #    (SDK puts workloadTag in the query) AND browser tile fetches
    #    (URL from getMapId already includes it).
    client_tag = request.query_params.get("workloadTag")
    if client_tag:
        return client_tag

    # 2. Fallback — mint richer parts + persist mapping so the tag is
    #    reversible. Pull the eeCreds singleton lazily to avoid a
    #    circular import at module load.
    #
    # Attribution ContextVars: the caller (agent MCP wrapper, notebook
    # running alongside an agent, any code that populates them) can
    # thread user/session/action/billing-tenant through to this builder
    # via ``geeViz.eeAuth.client``'s ContextVars. When set, the mint
    # includes them as parts so the puller can attribute the row to a
    # real user + session. When unset, the mint falls back to the
    # cred/pid/src shape (matches pre-2026.8 standalone behavior).
    #
    # ``CURRENT_BILLING_TENANT`` is separate from the ``tenant`` arg
    # (which comes from ``tenant_resolver`` — usually the header-supplied
    # cred name like "ee-persistent" for ADC). Billing tenant is the
    # deploy-time identity ("askterra", "geeviz"); prefer it when set.
    try:
        from geeViz.eeAuth.eeCreds import eeCreds as _singleton
        from geeViz.eeAuth.tags import mint_workload_tag, _default_secret
        from geeViz.eeAuth.client import (
            CURRENT_USER_EMAIL as _CUR_USER,
            CURRENT_SESSION_ID as _CUR_SESSION,
            CURRENT_ACTION as _CUR_ACTION,
            CURRENT_BILLING_TENANT as _CUR_BILL_TENANT,
        )
        _ctx_user = (_CUR_USER.get() or "").strip()
        # Local fallback: $GEEVIZ_USER_EMAIL.
        #
        # CURRENT_USER_EMAIL is set by the MCP wrapper from the agent's
        # before_tool_callback, so it is populated for agent-initiated
        # work and empty for everything else. Plain library use -- a
        # script or notebook doing ``Map.addLayer`` -- therefore minted a
        # tag with no identity at all, the tag store wrote
        # user_sub=UNATTRIBUTED, and the usage poller declined to bill it
        # (correctly: it will not charge a user it cannot name). The
        # symptom is EE work that shows up in ee_usage_hourly as
        # ``unattributed`` and never reaches cdu_ledger.
        #
        # The ContextVar still wins, so nothing about the agent path
        # changes. This only fills the gap where there was no identity to
        # begin with.
        if not _ctx_user:
            _ctx_user = (os.environ.get("GEEVIZ_USER_EMAIL") or "").strip()
        _ctx_session = (_CUR_SESSION.get() or "").strip()
        _ctx_action = (_CUR_ACTION.get() or "").strip()
        _ctx_bill = (_CUR_BILL_TENANT.get() or "").strip()
        # Prefer the billing tenant when set. Falls back to the arg
        # (the router's tenant_resolver output) so standalone geeViz
        # deployments — where nobody sets CURRENT_BILLING_TENANT — get
        # exactly the same behavior as before.
        _mint_tenant = _ctx_bill or (tenant or "default")
        parts: dict = {
            "tenant": _mint_tenant,
            "cred":   _singleton.current() or "unknown",
            "pid":    os.getpid(),
            "src":    "proxy-default",
        }
        # Which deployment minted this. mint_workload_tag spells it out in
        # the tag itself, which is the only way a puller can tell this
        # tag apart from a sibling deployment's -- they share one GCP
        # project and therefore one Cloud Monitoring stream. Omitted when
        # unset so a standalone geeViz deployment, where nobody defines
        # GEEVIZ_ENV, keeps minting exactly the tags it did before.
        _mint_env = (os.environ.get("GEEVIZ_ENV") or "").strip()
        if _mint_env:
            parts["env"] = _mint_env
        # Add attribution parts only when they're set — keeps the tag
        # hash deterministic for the standalone case (which used to
        # mint with just the 4 fields above) and ONLY changes the hash
        # when a real caller identity was propagated.
        if _ctx_user:
            parts["user_email"] = _ctx_user
        if _ctx_session:
            parts["session_id"] = _ctx_session
        if _ctx_action:
            parts["action"] = _ctx_action
        secret = _singleton._resolve_tag_secret() if hasattr(
            _singleton, "_resolve_tag_secret"
        ) else _default_secret()
        tag = mint_workload_tag(parts, secret=secret)
        try:
            _singleton.getTagStore().put(tag, parts)
        except Exception:
            logger.exception("ee-proxy: default builder store.put failed")
        return tag
    except Exception:
        # Never let attribution failure break a live request. Fall back
        # to the legacy shape.
        logger.exception("ee-proxy: default builder minting failed; using legacy shape")
        parts_list = ["ee-proxy"]
        if tenant:
            parts_list.append(tenant)
        return build_workload_tag(*parts_list)


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
            is :func:`_default_workload_tag_builder`, which passes a
            client-set tag through untouched and otherwise mints a
            reversible ``wl_<hex>`` tag and stores its parts. (It falls
            back to the legacy ``ee-proxy__<tenant>`` shape only if
            minting raises.)

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

    def _example_project(src, tenant):
        """An EE project id the reader can paste, if one is knowable.

        Every worked example needs a project in the path, and
        ``<your-project>`` in a curl line is the difference between a
        command that runs and one that returns 404 to someone who is
        already unsure whether the proxy works.
        """
        for attr in ("project_for", "get_project"):
            try:
                got = getattr(src, attr)(tenant)
                if got:
                    return str(got)
            except Exception:
                pass
        try:
            import ee as _ee
            got = _ee.data._cloud_api_user_project
            if got:
                return str(got)
        except Exception:
            pass
        return "&lt;your-ee-project&gt;"

    router = APIRouter()

    # Both spellings, because FastAPI answers the one without the
    # trailing slash with a 307 and an EMPTY BODY. A browser follows it
    # and nobody notices; curl, Insomnia and Postman do not follow by
    # default, so `GET /ee-api` -- the obvious thing to try by hand --
    # renders as a blank response from an apparently dead server.
    @router.get("", response_class=HTMLResponse, include_in_schema=False)
    @router.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def index(request: Request) -> HTMLResponse:
        """Human-friendly landing page — served when someone visits
        ``/ee-api/`` in a browser instead of an EE client.

        Lists tenants, endpoints, health link, upstream URL, version.
        No JS, no external assets — works over air-gapped networks and
        renders identically in every browser."""
        try:
            from geeViz import __version__ as _ver
        except Exception:
            _ver = "(unknown)"

        src = _resolve_creds()
        tenants: list = []
        try:
            if hasattr(src, "list"):
                tenants = list(src.list())
            elif hasattr(src, "list_tenants"):
                tenants = list(src.list_tenants())
        except Exception:
            tenants = []
        tenants.sort()

        base = str(request.url).rstrip("/")
        health_url = f"{base}/health"
        # Copy-pasteable examples beat correct-but-abstract ones, so the
        # snippets below use a tenant that is actually registered here
        # rather than <tenant-name>. Falls back to a placeholder only
        # when nothing is registered yet.
        example_tenant = tenants[0] if tenants else "<tenant-name>"
        example_project = _example_project(src, example_tenant)
        tenant_rows = (
            "".join(f"<li><code>{_html_escape(t)}</code></li>" for t in tenants)
            if tenants
            else "<li><em>(no tenants registered)</em></li>"
        )

        html = f"""<!doctype html>
<html><head><meta charset="utf-8">
<title>geeViz eeAuth proxy</title>
<style>
  body {{ font: 15px/1.5 -apple-system, Segoe UI, Roboto, sans-serif;
         max-width: 780px; margin: 2rem auto; padding: 0 1rem; color: #222; }}
  h1 {{ border-bottom: 1px solid #ddd; padding-bottom: .4rem; }}
  h2 {{ margin-top: 1.6rem; }}
  code, pre {{ font-family: SFMono-Regular, Menlo, monospace; font-size: 13px; }}
  pre {{ background: #f6f8fa; padding: .8rem 1rem; border-radius: 6px;
         overflow-x: auto; }}
  .grid {{ display: grid; grid-template-columns: 12rem 1fr; gap: .4rem 1rem; }}
  .grid dt {{ font-weight: 600; }}
  .muted {{ color: #666; }}
  table {{ border-collapse: collapse; margin: .5rem 0 1rem; }}
  th, td {{ text-align: left; padding: .3rem .8rem .3rem 0; }}
  th {{ border-bottom: 1px solid #ddd; }}
  a {{ color: #0969da; }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #0d1117; color: #c9d1d9; }}
    h1 {{ border-color: #30363d; }}
    pre {{ background: #161b22; }}
    th {{ border-color: #30363d; }}
    .muted {{ color: #8b949e; }}
    a {{ color: #58a6ff; }}
  }}
</style>
</head><body>
<h1>geeViz eeAuth proxy</h1>
<p class="muted">
  This URL is a <strong>reverse proxy</strong> that forwards Earth Engine
  REST calls to the upstream API, injecting per-tenant service-account
  bearer tokens. Point your EE client at it instead of calling EE
  directly — see below.
</p>

<h2>Status</h2>
<dl class="grid">
  <dt>Proxy base URL</dt><dd><code>{_html_escape(base)}</code></dd>
  <dt>Upstream</dt><dd><code>{_html_escape(upstream)}</code></dd>
  <dt>geeViz version</dt><dd><code>{_html_escape(_ver)}</code></dd>
  <dt>Health probe</dt><dd><a href="{_html_escape(health_url)}"><code>{_html_escape(health_url)}</code></a></dd>
  <dt>Tenant header</dt><dd><code>{_html_escape(tenant_header)}</code></dd>
  <dt>Tenant query param</dt><dd><code>{_html_escape(tenant_query_param)}</code></dd>
</dl>

<h2>Registered tenants ({len(tenants)})</h2>
<ul>{tenant_rows}</ul>

<h2>Endpoints</h2>
<table>
  <tr><th>Method</th><th>Path</th><th>Purpose</th></tr>
  <tr><td>GET</td><td><code>/</code></td><td>This page.</td></tr>
  <tr><td>GET</td><td><code>/health</code></td><td>Liveness + tenant fingerprint (JSON).</td></tr>
  <tr><td>ANY</td><td><code>/{{ee-api-path}}</code></td><td>Proxied to <code>{_html_escape(upstream)}/{{path}}</code> with the tenant's SA token.</td></tr>
</table>

<h2>Proxy modes</h2>
<p class="muted">Which one this URL is running under depends on how you started it — set via <code>Map.setAuthMode(...)</code>, the <code>GEEVIZ_EEAUTH_MODE</code> env var, or the default.</p>
<table>
  <tr><th>Mode</th><th>Process</th><th>Failure behavior</th></tr>
  <tr><td><code>attached</code></td><td>in-process daemon thread</td><td>silent fallback</td></tr>
  <tr><td><code>attached_strict</code></td><td>in-process daemon thread</td><td>raises on failure</td></tr>
  <tr><td><code>detached</code></td><td>subprocess (survives script exit)</td><td>silent fallback</td></tr>
  <tr><td><code>legacy</code></td><td>none (tokens minted into URL)</td><td>deprecated</td></tr>
</table>
<p class="muted">Legacy aliases: <code>auto</code> → <code>attached</code>, <code>proxy</code> → <code>attached_strict</code>.</p>

<h2>Picking a tenant</h2>
<p class="muted">Three ways, any of which works on every endpoint below.
Omit all three and the default credential is used.</p>
<table>
  <tr><th>Form</th><th>Looks like</th></tr>
  <tr><td>Header</td><td><code>{_html_escape(tenant_header)}: {_html_escape(example_tenant)}</code></td></tr>
  <tr><td>URL path</td><td><code>{_html_escape(base)}/t/{_html_escape(example_tenant)}/v1/…</code></td></tr>
  <tr><td>Query param</td><td><code>?{_html_escape(tenant_query_param)}={_html_escape(example_tenant)}</code></td></tr>
</table>
<p class="muted">The path form is the one browser tabs use, because a
tenant in the URL needs no header and so survives an <code>&lt;img&gt;</code>
tag fetching a map tile.</p>

<h2>Use it from Python</h2>
<pre>from geeViz.eeAuth import initialize_via_proxy
initialize_via_proxy("{_html_escape(base)}")
import ee
ee.Number(1).getInfo()  # → routes through this proxy</pre>

<h2>Use it from curl</h2>
<p class="muted">Liveness — no credential needed, and the fastest way to
tell "proxy is up" from "proxy is wedged":</p>
<pre>curl {_html_escape(health_url)}</pre>

<p class="muted">A real server-side computation. This is
<code>2 + 40</code> evaluated by Earth Engine, not locally:</p>
<pre>curl -X POST {_html_escape(base)}/v1/projects/{_html_escape(example_project)}/value:compute \\
  -H "Content-Type: application/json" \\
  -H "{_html_escape(tenant_header)}: {_html_escape(example_tenant)}" \\
  -d '{{"expression":{{"result":"0","values":{{"0":{{
        "functionInvocationValue":{{"functionName":"Number.add","arguments":{{
          "left":{{"constantValue":2}},"right":{{"constantValue":40}}}}}}}}}}}}}}'
# → {{ "result": 42 }}</pre>

<p class="muted">Anything in the EE REST API works the same way — the
proxy only adds the bearer token:</p>
<pre>curl -H "{_html_escape(tenant_header)}: {_html_escape(example_tenant)}" \\
  {_html_escape(base)}/v1/projects/earthengine-legacy/algorithms</pre>

<h2>Use it from Insomnia / Postman / Bruno</h2>
<ol>
  <li>Set the environment's base URL to <code>{_html_escape(base)}</code>.</li>
  <li>Add a header <code>{_html_escape(tenant_header)}</code> =
      <code>{_html_escape(example_tenant)}</code> at the environment or
      folder level, so every request inherits it.</li>
  <li><strong>Leave authentication set to None.</strong> The proxy mints
      the token; a bearer token you add yourself is passed through and
      will be rejected upstream.</li>
  <li>Enable "follow redirects" if you want to hit
      <code>{_html_escape(base)}</code> with no trailing path — otherwise
      you get an empty 307.</li>
</ol>
<pre>POST {{{{baseUrl}}}}/v1/projects/{_html_escape(example_project)}/value:compute
{_html_escape(tenant_header)}: {_html_escape(example_tenant)}
Content-Type: application/json

{{"expression":{{"result":"0","values":{{"0":{{"constantValue":42}}}}}}}}</pre>

<h2>Use it from Node.js</h2>
<p class="muted">No SDK and no credentials — <code>fetch</code> is built
in from Node 18.</p>
<pre>const BASE = "{_html_escape(base)}";
const TENANT = "{_html_escape(example_tenant)}";

const res = await fetch(
  `${{BASE}}/v1/projects/{_html_escape(example_project)}/value:compute`, {{
    method: "POST",
    headers: {{
      "Content-Type": "application/json",
      "{_html_escape(tenant_header)}": TENANT,
    }},
    body: JSON.stringify({{
      expression: {{ result: "0", values: {{ "0": {{ constantValue: 42 }} }} }},
    }}),
  }});
console.log(await res.json());   // {{ result: 42 }}</pre>

<h2>Use it from Express</h2>
<p class="muted">Re-expose the proxy to your own front end so browser
JavaScript can call Earth Engine <em>without ever holding a token</em> —
the token stays on this process, and your server decides which tenant a
given user is allowed to spend.</p>
<pre>import express from "express";

const app = express();
const BASE = "{_html_escape(base)}";

app.use(express.json({{ limit: "10mb" }}));

// Map the signed-in user to a tenant SERVER-SIDE. Never take the tenant
// from the client: it names whose EE quota the call spends.
const tenantFor = (req) =&gt; req.session?.tenant ?? "{_html_escape(example_tenant)}";

app.use("/ee", async (req, res) =&gt; {{
  const upstream = await fetch(BASE + req.url, {{
    method: req.method,
    headers: {{
      "Content-Type": "application/json",
      "{_html_escape(tenant_header)}": tenantFor(req),
    }},
    body: req.method === "GET" ? undefined : JSON.stringify(req.body),
  }});
  // arrayBuffer, not text: computePixels and maps:getMap return binary.
  const buf = Buffer.from(await upstream.arrayBuffer());
  res.status(upstream.status)
     .type(upstream.headers.get("content-type") ?? "application/json")
     .send(buf);
}});

app.listen(3000);</pre>
<p class="muted">Inside <code>app.use("/ee", …)</code> Express has already
stripped the mount path, so <code>req.url</code> is what to forward —
<code>req.originalUrl</code> would send <code>/ee</code> upstream too.</p>

<h2>Use it from the Earth Engine JavaScript SDK</h2>
<p class="muted">The SDK sends every REST call to whatever
<code>authProxyAPIURL</code> holds, so pointing it here is the whole
integration. Set it <strong>before</strong> <code>ee.initialize()</code>:</p>
<pre>// Path form, so map tiles fetched by &lt;img&gt; carry the tenant too.
authProxyAPIURL = window.location.origin +
                  "/ee-api/t/{_html_escape(example_tenant)}";
ee.initialize(authProxyAPIURL, null, onReady, onError);</pre>

<p class="muted" style="margin-top: 2rem; font-size: 12px;">
  This page renders because the incoming request had no path after
  <code>/</code>. Any real EE path (e.g.
  <code>/v1/projects/…/value:compute</code>) is proxied through, not
  rendered.
</p>
</body></html>
"""
        return HTMLResponse(content=html)

    @router.get("/health")
    async def health() -> dict:  # noqa: F811 – see docstring for fields
        """Liveness + identity probe for detached-mode discovery.

        Returned fields:
          - ``ok``                     — always true (request reached us)
          - ``version``                — geeViz package version (for
                                         version-skew detection in
                                         ``eeCreds._ensure_detached_proxy``)
          - ``tenant_fingerprint``     — sha256 of sorted tenant names, so
                                         clients can detect when the
                                         detached process is using a
                                         stale tenant set vs. the
                                         current environment
          - ``tenants``                — list of tenant names currently
                                         registered (mainly for human
                                         debugging via curl)
          - ``pid``                    — process id of the proxy
          - ``started_at``             — ISO timestamp of process start
        """
        import hashlib
        import os
        try:
            from geeViz import __version__ as _ver
        except Exception:
            _ver = ""
        src = _resolve_creds()
        names = []
        try:
            if hasattr(src, "list"):
                names = list(src.list())
            elif hasattr(src, "list_tenants"):
                names = list(src.list_tenants())
        except Exception:
            names = []
        names.sort()
        fp = hashlib.sha256(",".join(names).encode("utf-8")).hexdigest()[:16]
        return {
            "ok": True,
            "version": _ver,
            "tenant_fingerprint": fp,
            "tenants": names,
            "pid": os.getpid(),
            "started_at": _PROCESS_STARTED_AT,
        }

    @router.api_route(
        "/{path:path}",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
    )
    async def ee_proxy(path: str, request: Request) -> Response:
        """Forward an EE API request to the upstream, injecting the tenant's
        Bearer token.

        Tenant resolution order (first non-empty wins): path prefix
        ``/t/<tenant>/`` → configured header (``X-EE-Tenant`` by default)
        → configured query param (``tenant`` by default) → default tenant.

        Args:
            path: Everything after ``/ee-api/`` in the request URL.
            request: FastAPI Request; body, headers, and query params are
                forwarded as-is (Origin stripped for token / SSO paths so
                EE doesn't reject).

        Returns:
            Response: Upstream response passed through with its status,
            headers (minus hop-by-hop), and body. 204 for the tenant-ack
            path (``/t/<tenant>`` with no trailing segment).
        """
        import httpx

        # 1. Resolve tenant + mint a token from the credential source.
        #
        # Path-prefix syntax ``/ee-api/t/<tenant>/<rest>`` wins over
        # header and query. ``Map.view()`` bakes the tenant into the
        # JS-side ``authProxyAPIURL`` exactly this way to pin each
        # browser tab to its load-time tenant, immune to process-wide
        # eeCreds switches in the host script. Strip the prefix so
        # only the genuine EE path is forwarded upstream.
        path_tenant = ""
        if path.startswith("t/"):
            rest = path[len("t/"):]
            slash = rest.find("/")
            if slash > 0:
                path_tenant = rest[:slash]
                path = rest[slash + 1:]
            else:
                # ``/ee-api/t/<tenant>`` with no trailing segment —
                # tenant-ack ping, no upstream call needed.
                return Response(content=b"", status_code=204)
        tenant = path_tenant or resolver(request)
        registry = _resolve_creds()
        try:
            # ``get_token`` calls ``creds.refresh()`` (synchronous OAuth
            # HTTP roundtrip, ~200-1000ms+ on cache miss) which would
            # block the asyncio event loop. Offload to the default
            # threadpool so other /ee-api requests — including the MCP
            # subprocess's first-init verification call — can proceed
            # in parallel. Cached tokens (TTL ~50min) return instantly,
            # but the first request per tenant pays the refresh cost,
            # and that's exactly when the agent's own map renderer and
            # the MCP subprocess race for the same loop.
            tok = await asyncio.to_thread(
                registry.get_token, tenant or None
            )
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

        try:
            body = await request.body()
        except ClientDisconnect:
            # Browser aborted the request before we finished reading it —
            # typical map-viewer pattern where pan/zoom cancels in-flight
            # tile fetches. Client is gone; no one to respond to. Return
            # a 499 (Nginx's "Client Closed Request") so anything logging
            # by status still sees this as a disconnect, not a 5xx.
            return Response(status_code=499)

        # 4. Forward + retry once on 401 (token rotation). Uses the
        # shared ``upstream_client`` (keep-alive connection pool) — see
        # the construction above for why we don't create per-request.
        async def _do_upstream():
            return await upstream_client.request(
                request.method, upstream_url,
                content=body if body else None,
                headers=fwd_headers,
            )

        try:
            upstream_resp = await _do_upstream()
        except (httpx.ReadTimeout, httpx.ConnectTimeout) as e:
            # EE compute occasionally exceeds the 120s deadline. One
            # retry with fresh connection buys the caller another shot
            # before a hard 504. Compute requests are idempotent — the
            # server-side operation may still complete, but retrying
            # the read doesn't duplicate work.
            logger.warning(
                "ee-proxy: upstream timeout on %s %s — retrying once",
                request.method, path,
            )
            try:
                upstream_resp = await _do_upstream()
            except (httpx.ReadTimeout, httpx.ConnectTimeout):
                logger.warning(
                    "ee-proxy: upstream timeout on %s %s — returning 504",
                    request.method, path,
                )
                return Response(
                    content=f"upstream timeout after retry: {e}",
                    status_code=504,
                )
            except httpx.HTTPError as e2:
                logger.exception("ee-proxy: upstream error on retry for %s %s",
                                 request.method, path)
                return Response(content=f"upstream error: {e2}", status_code=502)
        except httpx.HTTPError as e:
            logger.exception("ee-proxy: upstream error for %s %s",
                             request.method, path)
            return Response(content=f"upstream error: {e}", status_code=502)

        if upstream_resp.status_code == 401:
            try:
                tok = await asyncio.to_thread(
                    registry.get_token, actual_tenant, True
                )
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
    serve_geeview: bool = True,
) -> FastAPI:
    """Build a standalone FastAPI app with the proxy mounted at ``prefix``.
    Suitable for direct serving via ``uvicorn`` or for testing.

    ``creds`` accepts an :class:`EECreds` / :class:`SARegistry`-like
    object; ``None`` falls back to the env-var registry. See
    :func:`build_proxy_router` for the other parameters.

    Use ``build_proxy_router`` directly if you want to mount in an
    existing FastAPI app and share its middleware / lifecycle.

    Args:
        serve_geeview: When True (default for standalone runs), also
            mount the geeView frontend bundle at ``/geeView/*``. This
            makes the detached proxy the single long-lived server for
            both EE auth (``/ee-api/*``) and ``Map.view()`` HTML
            (``/geeView/...``). Same origin, same port — browser tabs
            survive script exits without a daemon-thread server inside
            each script. Set False to keep the proxy auth-only.
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

    if serve_geeview:
        # Mount the geeViz package directory at /geeView. Map.view()
        # writes exports into ``<package>/geeView/src/gee/gee-run/`` —
        # the browser fetches them at ``/geeView/src/gee/gee-run/<file>``
        # and all relative asset references (``src/lib/...``,
        # ``src/css/...``, ``src/gee/...``) resolve under the same
        # ``/geeView/`` root, matching what the legacy in-script
        # ``_GeeVizRequestHandler`` served.
        from fastapi.staticfiles import StaticFiles
        import os as _os

        class _NoStoreStatic(StaticFiles):
            """StaticFiles that refuses to be cached.

            ``Map.view()`` REWRITES ``runGeeViz.js`` in place on every
            call, so the URL never changes while the content does.
            Starlette's StaticFiles sends ``last-modified`` and ``etag``
            but no ``Cache-Control``, and with no explicit directive a
            browser is free to serve a heuristically-fresh copy without
            revalidating -- which shows the PREVIOUS map, with no error
            and nothing in the console.

            geeViz's own request handler already forces no-store for
            exactly this reason (see ``geeView._GeeVizRequestHandler``);
            running behind this proxy quietly lost it, and the proxy is
            the default path.
            """

            async def get_response(self, path, scope):
                resp = await super().get_response(path, scope)
                resp.headers["Cache-Control"] = "no-store, must-revalidate"
                resp.headers["Pragma"] = "no-cache"
                resp.headers["Expires"] = "0"
                return resp

        _PKG_DIR = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
        _GEEVIEW_DIR = _os.path.join(_PKG_DIR, "geeView")
        if _os.path.isdir(_GEEVIEW_DIR):
            app.mount(
                "/geeView",
                _NoStoreStatic(directory=_GEEVIEW_DIR, html=True),
                name="geeview-static",
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
