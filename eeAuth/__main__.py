"""Command-line runner — ``python -m geeViz.eeAuth``.

Stands up a standalone EE auth proxy on the given port. The proxy reads
SA credentials from env vars (``GEE_SERVICE_ACCOUNT_B64`` for default,
``GEE_<NAME>_SERVICE_ACCOUNT`` for additional tenants) and routes
incoming EE REST calls through the right SA based on the tenant header
or query param.

Usage::

    # Smallest case — one SA, no tenancy
    GEE_SERVICE_ACCOUNT_B64=$(base64 -w0 sa.json) python -m geeViz.eeAuth

    # Custom port + upstream
    python -m geeViz.eeAuth --port 9000 --upstream https://earthengine.googleapis.com

    # Verbose logging
    python -m geeViz.eeAuth --log-level DEBUG

Then point your EE clients at it (e.g. ``http://localhost:8888/ee-api``)
via the JS ``ee.initialize(authProxyAPIURL, ...)`` or the Python helper
``geeViz.eeAuth.initialize_via_proxy(url)``.
"""
from __future__ import annotations

import argparse
import logging
import sys

from .server import create_proxy_app, DEFAULT_UPSTREAM, DEFAULT_TENANT_HEADER


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m geeViz.eeAuth",
        description="Standalone Earth Engine multi-tenant auth proxy.",
    )
    parser.add_argument(
        "--host", default="0.0.0.0",
        help="Listen host (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port", type=int, default=8888,
        help="Listen port (default: 8888)",
    )
    parser.add_argument(
        "--upstream", default=DEFAULT_UPSTREAM,
        help=f"Upstream EE base URL (default: {DEFAULT_UPSTREAM})",
    )
    parser.add_argument(
        "--prefix", default="/ee-api",
        help="URL prefix for the proxy (default: /ee-api)",
    )
    parser.add_argument(
        "--tenant-header", default=DEFAULT_TENANT_HEADER,
        help=f"Header for tenant routing (default: {DEFAULT_TENANT_HEADER})",
    )
    parser.add_argument(
        "--tenant-query", default="tenant",
        help="Query-param fallback for tenant routing (default: tenant)",
    )
    parser.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level (default: INFO)",
    )

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        import uvicorn
    except ImportError:
        print(
            "ERROR: uvicorn is required to run the standalone proxy. "
            "Install with: pip install uvicorn",
            file=sys.stderr,
        )
        return 1

    # Use eeCreds (not the legacy env-var SARegistry) so the standalone
    # runner finds the full set of credential sources discover() knows
    # about — EE persistent file, gcloud ADC, $GEE_SERVICE_ACCOUNT_B64,
    # per-tenant SA env vars, keyless impersonation, and the WIF/ADC
    # fallback. Without this, scripts using ``ensure_started(mode=
    # 'detached')`` would see a fingerprint mismatch (client discovers
    # more tenants than the env-var-only proxy) and keep respawning.
    from . import eeCreds as _ee_creds_singleton
    _ee_creds_singleton.discover()
    tenants = _ee_creds_singleton.list()
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles
    import os as _os
    app = FastAPI()
    app.include_router(
        _ee_creds_singleton.router(
            upstream=args.upstream,
            tenant_header=args.tenant_header,
            tenant_query_param=args.tenant_query,
        ),
        prefix=args.prefix,
    )
    # Also serve /geeView/* from the geeViz package — same long-lived
    # process now handles both EE auth (``/ee-api/*``) and Map.view()
    # HTML (``/geeView/...``). Map.view() writes exports into
    # ``<package>/geeView/src/gee/gee-run/`` and opens the browser to
    # this server's ``/geeView/src/gee/gee-run/<file>`` URL; everything
    # else (frontend JS, CSS, EE tile fetches) is same-origin.
    _PKG_DIR = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    _GEEVIEW_DIR = _os.path.join(_PKG_DIR, "geeView")
    if _os.path.isdir(_GEEVIEW_DIR):
        app.mount(
            "/geeView",
            StaticFiles(directory=_GEEVIEW_DIR, html=True),
            name="geeview-static",
        )
    if not tenants:
        print(
            "WARNING: no tenants discovered — set GEE_SERVICE_ACCOUNT_B64, "
            "GEE_<NAME>_SERVICE_ACCOUNT, run `earthengine authenticate`, "
            "or `gcloud auth application-default login`. Proxy will 400 "
            "on every request until at least one tenant is configured.",
            file=sys.stderr,
        )
    else:
        print(
            f"Loaded {len(tenants)} tenant(s): {', '.join(tenants)}",
            file=sys.stderr,
        )

    print(
        f"geeViz EE proxy starting on http://{args.host}:{args.port}{args.prefix}",
        file=sys.stderr,
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level.lower())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
