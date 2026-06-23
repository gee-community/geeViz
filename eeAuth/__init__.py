"""Earth Engine multi-tenant auth proxy + client helpers.

A drop-in toolkit for running Earth Engine work behind a token-injecting
HTTP proxy. Lets a single Python process talk to EE on behalf of many
service accounts concurrently — bypassing the `ee.Initialize()` global-
credential limitation that normally forces process-per-tenant designs.

What "by default" gets you
--------------------------
**You usually don't need to touch this module directly.** Calling
``Map.view()`` in :mod:`geeViz.geeView` auto-starts the proxy on first
use. The flow is:

1. ``Map.view()`` → ``eeCreds.ensure_started("auto")``
2. :func:`~geeViz.eeAuth.eeCreds.EECreds.discover` finds whatever
   credentials are visible in the environment
   (``$GOOGLE_APPLICATION_CREDENTIALS``, the EE persistent file,
   ``gcloud`` ADC, env-var SAs).
3. If anything was discovered, a local ``uvicorn`` proxy is spawned in
   a daemon thread (or reused if already running).
4. ``ee.Initialize`` is pointed at the proxy and EE traffic routes
   through it for the rest of the process.

Single-credential users get this for free. Multi-credential workflows
register additional creds with
:meth:`~geeViz.eeAuth.eeCreds.EECreds.addCreds` and switch with
:meth:`~geeViz.eeAuth.eeCreds.EECreds.use` / ``with eeCreds.use(...)``.
Every browser tab that ``Map.view()`` opens is pinned to the tenant
that was current at the time of the call — subsequent ``use()``
switches in Python can't drift open tabs to a different credential.

Layout
------
- :mod:`geeViz.eeAuth.eeCreds`  — high-level ``eeCreds`` singleton & API
- :mod:`geeViz.eeAuth.registry` — lower-level env-var-driven SA cache
- :mod:`geeViz.eeAuth.tags`     — workload-tag construction (EE billing attribution)
- :mod:`geeViz.eeAuth.client`   — initialize the ``ee`` SDK to route through a proxy
- :mod:`geeViz.eeAuth.server`   — FastAPI proxy app (mountable in your own
                                   FastAPI app OR runnable standalone)

Typical use — multi-credential (when you want it)
-------------------------------------------------
::

    from geeViz.eeAuth import eeCreds
    import ee

    eeCreds.addCreds("/path/to/sa-prod.json", "prod")
    eeCreds.addCreds("/path/to/sa-training.json", "training")
    eeCreds.start()                  # spins up the local proxy

    eeCreds.use("prod")
    ee.Number(1).getInfo()           # routes through prod SA

    with eeCreds.use("training"):
        ee.Number(2).getInfo()       # routes through training SA
    # back to prod here

Typical use — running the proxy standalone (Cloud Run, Docker, etc.)
--------------------------------------------------------------------
::

    python -m geeViz.eeAuth --port 8888

Embedded in your FastAPI app::

    from fastapi import FastAPI
    from geeViz.eeAuth.server import build_proxy_router
    from geeViz.eeAuth import eeCreds

    eeCreds.discover()
    app = FastAPI()
    app.include_router(
        build_proxy_router(creds=eeCreds), prefix="/ee-api",
    )

The proxy resolves which SA to use for each request from (in order):

1. ``X-geeViz-Creds`` request header
2. ``?tenant=`` query string parameter
3. ``/ee-api/t/<tenant>/`` path-prefix (used by ``Map.view()`` to pin
   each browser tab to its tenant)
4. Default tenant (``GEE_SERVICE_ACCOUNT_B64`` env var, or the first
   registered credential in ``eeCreds``)

Add SAs by setting env vars matching ``GEE_<NAME>_SERVICE_ACCOUNT``
where NAME is a tenant id. The value is a base64-encoded SA JSON key.

Why this exists
---------------
The Earth Engine Python SDK stores credentials in module-level state via
``ee.Initialize()``. Two tenants can't run concurrently in one process
without racing each other's auth. By routing every REST call through a
local proxy that injects the right SA per request, you keep one Python
process, one ``ee.Initialize`` call, and get full multi-tenant
concurrency.
"""
# Public API re-exports
from .registry import (
    SARegistry,
    get_registry,
    reset_registry,
    DEFAULT_TENANT,
)
from .tags import (
    build_workload_tag,
    sanitize_workload_tag_part,
)
from .client import (
    initialize_via_proxy,
    tenant_context,
    set_tenant,
    reset_tenant,
    TenantAwareHttp,
    CURRENT_TENANT,
)
from .server import (
    build_proxy_router,
    create_proxy_app,
)
from .eeCreds import (
    eeCreds,
    EECreds,
)


def robust_init(*, verbose: bool = False, interactive: bool = True) -> dict:
    """Module-level convenience: ``eeCreds.robust_init(...)``.

    Centralizes the "get EE up and running, prefer the proxy, never
    silently fall through to gcloud ADC without saying so" bootstrap
    that ``geeViz.geeView`` and external callers both want.
    """
    return eeCreds.robust_init(verbose=verbose, interactive=interactive)

__all__ = [
    # High-level API (recommended for most users)
    "eeCreds",
    "EECreds",
    "robust_init",
    # Lower-level building blocks
    "SARegistry",
    "get_registry",
    "reset_registry",
    "DEFAULT_TENANT",
    # Tags
    "build_workload_tag",
    "sanitize_workload_tag_part",
    # Client-side EE init
    "initialize_via_proxy",
    "tenant_context",
    "set_tenant",
    "reset_tenant",
    "TenantAwareHttp",
    "CURRENT_TENANT",
    # Server-side proxy
    "build_proxy_router",
    "create_proxy_app",
]

__version__ = "2026.6.2"
