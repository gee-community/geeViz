"""Client-side helpers for routing the Earth Engine Python SDK through a
token-injecting proxy.

The pattern:

1. Run a proxy server (see ``geeViz.eeAuth.server``) that holds the SA
   credentials and substitutes the right bearer token per request based
   on a tenant header / query param.
2. Tell the EE SDK to send all REST calls through that proxy instead of
   directly to Google. Pass anonymous credentials — the proxy supplies
   the real ones.
3. Switch tenants on the client side by setting a ``ContextVar``; the
   custom HTTP transport reads it and stamps the routing header on
   every outbound request.

That gives you full multi-tenant concurrency in a single Python process,
which the bare EE SDK can't do because ``ee.Initialize()`` stores
credentials in module-global state.

Quick start
-----------
::

    from geeViz.eeAuth import initialize_via_proxy, tenant_context
    import ee

    initialize_via_proxy("http://localhost:8888/ee-api")
    # Now ee.X calls go through the proxy with the default tenant

    with tenant_context("training"):
        ee.Image(1).getInfo()  # uses the training SA
"""
from __future__ import annotations

import contextvars
import logging
import sys
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)

# ContextVar holding the current tenant id. ``TenantAwareHttp`` reads it
# on every outbound EE REST call and stamps the routing header. Empty
# string means "use the proxy's default tenant" (no header sent).
CURRENT_TENANT: contextvars.ContextVar[str] = contextvars.ContextVar(
    "geeViz_ee_tenant", default="",
)

# Header name the proxy looks at to pick a credential. Matches the
# default in ``geeViz.eeAuth.server`` — both sides must agree on the
# string for routing to work. Override at init time if you've deployed
# the proxy with a different header (e.g. the AskTerra agent uses
# ``X-AskTerra-Tenant``).
DEFAULT_TENANT_HEADER = "X-geeViz-Creds"


def set_tenant(tenant: str):
    """Set the current tenant for subsequent EE calls in this context.

    Returns a token that can be passed to ``reset_tenant`` to restore
    the previous value. Prefer ``tenant_context()`` for scoped use.
    """
    return CURRENT_TENANT.set(tenant or "")


def reset_tenant(token) -> None:
    """Restore the tenant to what it was before the matching ``set_tenant``
    call."""
    CURRENT_TENANT.reset(token)


@contextmanager
def tenant_context(tenant: str):
    """Scoped tenant switch::

        with tenant_context("training"):
            ee.Image(1).getInfo()
        # back to previous tenant here
    """
    token = set_tenant(tenant)
    try:
        yield
    finally:
        reset_tenant(token)


class TenantAwareHttp:
    """``httplib2.Http`` subclass that stamps the tenant header on every
    outbound request and strips whatever Authorization the SDK injected.

    Subclassed at first instantiation so ``httplib2`` is only imported
    when actually used — keeps unit tests that mock the EE init path
    from needing the dependency. The header name is set per-instance so
    you can run multiple proxies with different conventions in the same
    process if you really need to.

    Thread safety
    -------------
    ``httplib2.Http`` is NOT thread-safe — its per-host connection cache
    (``self.connections``) is a plain ``dict`` mutated from inside
    ``request()`` and ``socket.HTTPConnection`` objects hold per-instance
    socket state. When the EE SDK shares one transport across a
    ``ThreadPoolExecutor`` (as ``Map.testLayers()`` does with 8 workers),
    concurrent threads tear down each other's sockets mid-request,
    surfacing as ``'NoneType' object has no attribute 'close'`` and
    Windows ``WinError 10038/10057`` socket errors.

    Workaround: route each thread's ``request()`` call to its OWN
    ``httplib2.Http`` instance stored in ``threading.local()``. EE's SDK
    only consults the transport for ``request()`` — it doesn't reach into
    ``self.connections`` directly — so per-thread instances are a safe
    drop-in.
    """
    _impl_cls = None  # lazily-defined subclass keyed by header name

    def __new__(cls, tenant_header: str = DEFAULT_TENANT_HEADER):
        if cls._impl_cls is None:
            import httplib2
            import threading as _threading

            class _Impl(httplib2.Http):
                _tenant_header = tenant_header
                _thread_local = _threading.local()

                def _thread_http(self):
                    """Lazy per-thread ``httplib2.Http`` so concurrent
                    SDK calls don't share socket/connection state."""
                    h = getattr(self.__class__._thread_local, "http", None)
                    if h is None:
                        h = httplib2.Http()
                        self.__class__._thread_local.http = h
                    return h

                def request(self, uri, method="GET", body=None, headers=None, **kw):
                    headers = dict(headers or {})
                    # Strip SDK-injected auth — proxy substitutes its own
                    headers.pop("Authorization", None)
                    headers.pop("authorization", None)
                    # Stamp current tenant
                    tenant = CURRENT_TENANT.get()
                    if tenant:
                        headers[self._tenant_header] = tenant
                    return self._thread_http().request(
                        uri, method, body, headers, **kw
                    )
            cls._impl_cls = _Impl
        return cls._impl_cls()


def initialize_via_proxy(
    proxy_url: str,
    tenant_header: str = DEFAULT_TENANT_HEADER,
    project: Optional[str] = None,
) -> bool:
    """Initialize the Earth Engine SDK to route all REST calls through
    ``proxy_url``.

    Uses ``AnonymousCredentials`` since the proxy holds the real SA
    credentials. The SDK's bearer-token header is stripped by
    ``TenantAwareHttp`` before reaching the proxy anyway.

    Args:
        proxy_url: Base URL of the EE proxy, e.g.
            ``"http://localhost:8888/ee-api"``. No trailing slash.
        tenant_header: Header name the proxy expects for tenant routing.
            Default ``X-geeViz-Creds`` matches ``geeViz.eeAuth.server``.
        project: Placeholder project id passed to ``ee.Initialize`` (EE
            requires one but the proxy overrides per-tenant via
            ``x-goog-user-project``). Default
            ``"ee-proxy-placeholder"``.

    Returns:
        True on success, False if init failed (caller should fall back
        to direct ``ee.Initialize`` or surface the error). Prints any
        underlying exception to stderr; doesn't re-raise.
    """
    try:
        import ee
        from google.auth.credentials import AnonymousCredentials

        ee.Initialize(
            credentials=AnonymousCredentials(),
            url=proxy_url.rstrip("/"),
            http_transport=TenantAwareHttp(tenant_header=tenant_header),
            project=project or "ee-proxy-placeholder",
        )
        print(
            f"[geeViz.eeAuth] EE initialized via proxy: {proxy_url} "
            f"(tenant_header={tenant_header})",
            file=sys.stderr,
        )
        return True
    except Exception as e:
        msg = str(e)
        # Pull the offending project out of the standard EE
        # USER_PROJECT_DENIED message so we can name it in the hint.
        import re as _re
        m_proj = _re.search(
            r"permission to use project ([A-Za-z0-9._-]+)", msg
        )
        # GCP project IDs can contain ``-`` but not trailing ``.``;
        # the regex above happens to gobble a sentence-ending period
        # from the EE error text, so trim it.
        denied_project = m_proj.group(1).rstrip(".") if m_proj else None

        # The classic "OAuth credentials have no project" failure mode:
        # EE routes the call to earthengine-legacy as the consumer
        # project, and the personal Google account can't use that.
        if (denied_project == "earthengine-legacy"
                and "USER_PROJECT_DENIED" in msg):
            print(
                "[geeViz.eeAuth] proxy init failed: OAuth credentials have "
                "no project set, so EE routed to 'earthengine-legacy' "
                "which your account can't use.\n"
                "  Fix: tell the library which GCP project to bill against "
                "via ONE of:\n"
                "    1. eeCreds.addCreds(..., project='YOUR_PROJECT')\n"
                "    2. export GOOGLE_CLOUD_PROJECT=YOUR_PROJECT\n"
                "    3. gcloud config set project YOUR_PROJECT\n"
                "    4. ee.Initialize(project='YOUR_PROJECT')  # before importing geeViz\n"
                "  Your project must have the Earth Engine API enabled and "
                "be registered for EE.",
                file=sys.stderr,
            )
        # SA registered with a project_id its identity doesn't have
        # ``serviceusage.services.use`` on. Discovery 403s but direct
        # EE calls (value:compute, etc.) may still work — this is a real
        # IAM gap, not a library bug. Surface it actionably.
        elif (denied_project
                and "USER_PROJECT_DENIED" in msg
                and "serviceusage" in msg.lower()):
            print(
                f"[geeViz.eeAuth] proxy init: the credential can't use "
                f"project {denied_project!r} for service-usage discovery.\n"
                f"  This usually means the service account is missing "
                f"`roles/serviceusage.serviceUsageConsumer` on "
                f"{denied_project!r}. Fix by EITHER:\n"
                f"    1. Granting that role to the SA in GCP Console → "
                f"IAM for project {denied_project!r}, OR\n"
                f"    2. Overriding the project at registration:\n"
                f"         eeCreds.addCreds(..., project='OTHER_PROJECT')\n"
                f"       (use a project the SA HAS got serviceusage.services.use on).\n"
                f"  Some EE calls may still succeed (they take a different "
                f"code path), but discovery-driven operations will fail.",
                file=sys.stderr,
            )
        else:
            print(
                f"[geeViz.eeAuth] proxy init failed: {type(e).__name__}: {e}",
                file=sys.stderr,
            )
        return False
