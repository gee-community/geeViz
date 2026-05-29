"""Tests for the geeViz.eeAuth library.

Covers the public API surface — anything users would import from
``geeViz.eeAuth.*``. Internal behavior is mostly covered by the agent's
test suite (which exercises the same modules end-to-end).
"""
import base64
import json
import os
import sys
from unittest.mock import patch

# Ensure the repo root and agent dir are both on the path
_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "geeViz_agent"))


def _b64_sa(client_email, project_id="test-proj"):
    sa = {
        "type": "service_account",
        "client_email": client_email,
        "project_id": project_id,
        "private_key": "-----BEGIN PRIVATE KEY-----\nFAKE\n-----END PRIVATE KEY-----\n",
        "private_key_id": "fake",
        "client_id": "12345",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    return base64.b64encode(json.dumps(sa).encode("utf-8")).decode("ascii")


# ─────────────────────── Public API surface ───────────────────────
def test_top_level_exports_present():
    """Every name in __init__.py's __all__ must be importable."""
    from geeViz import eeAuth
    for name in eeAuth.__all__:
        assert hasattr(eeAuth, name), f"geeViz.eeAuth missing public export: {name}"


def test_registry_exports():
    from geeViz.eeAuth import SARegistry, get_registry, reset_registry, DEFAULT_TENANT
    assert DEFAULT_TENANT == "default"
    assert callable(get_registry)
    assert callable(reset_registry)
    assert isinstance(SARegistry, type)


def test_tags_exports_and_sanitize():
    from geeViz.eeAuth import build_workload_tag, sanitize_workload_tag_part
    assert sanitize_workload_tag_part("Foo@bar.com") == "foo-bar-com"
    assert build_workload_tag("a", "b", "c") == "a__b__c"
    # Empty parts dropped
    assert build_workload_tag("a", "", "c") == "a__c"


def test_client_exports():
    from geeViz.eeAuth import (
        initialize_via_proxy, tenant_context, set_tenant, reset_tenant,
        TenantAwareHttp, CURRENT_TENANT,
    )
    assert callable(initialize_via_proxy)
    assert callable(tenant_context)
    # CURRENT_TENANT is a ContextVar
    import contextvars
    assert isinstance(CURRENT_TENANT, contextvars.ContextVar)


def test_server_exports():
    from geeViz.eeAuth import build_proxy_router, create_proxy_app
    assert callable(build_proxy_router)
    assert callable(create_proxy_app)


# ─────────────────────── tenant_context ───────────────────────
def test_tenant_context_sets_and_resets():
    from geeViz.eeAuth import tenant_context, CURRENT_TENANT
    assert CURRENT_TENANT.get() == ""
    with tenant_context("training"):
        assert CURRENT_TENANT.get() == "training"
    assert CURRENT_TENANT.get() == ""


def test_tenant_context_nested():
    from geeViz.eeAuth import tenant_context, CURRENT_TENANT
    with tenant_context("alpha"):
        assert CURRENT_TENANT.get() == "alpha"
        with tenant_context("beta"):
            assert CURRENT_TENANT.get() == "beta"
        assert CURRENT_TENANT.get() == "alpha"
    assert CURRENT_TENANT.get() == ""


def test_tenant_context_restores_on_exception():
    from geeViz.eeAuth import tenant_context, CURRENT_TENANT
    try:
        with tenant_context("training"):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert CURRENT_TENANT.get() == ""


# ─────────────────────── Registry behavior ───────────────────────
def test_registry_loads_from_env():
    from geeViz.eeAuth import reset_registry, get_registry
    with patch.dict(os.environ, {
        "GEE_SERVICE_ACCOUNT_B64": _b64_sa("default@p.iam"),
        "GEE_ACME_SERVICE_ACCOUNT": _b64_sa("acme@p.iam"),
    }, clear=False):
        reset_registry()
        reg = get_registry()
        assert "default" in reg.list_tenants()
        assert "acme" in reg.list_tenants()


def test_registry_fallback_to_default_on_unknown_tenant():
    from geeViz.eeAuth import reset_registry, get_registry
    with patch.dict(os.environ,
                    {"GEE_SERVICE_ACCOUNT_B64": _b64_sa("d@p.iam")},
                    clear=False):
        reset_registry()
        assert get_registry().resolve("never-heard-of-this") == "default"


# ─────────────────────── Proxy app smoke test ───────────────────────
def test_create_proxy_app_returns_fastapi():
    """create_proxy_app should produce a working FastAPI instance with
    the proxy mounted at the prefix and a root health check."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from geeViz.eeAuth import reset_registry
    from geeViz.eeAuth.server import create_proxy_app

    # Make sure the registry has at least one tenant so the proxy's
    # root endpoint returns something interesting.
    with patch.dict(os.environ,
                    {"GEE_SERVICE_ACCOUNT_B64": _b64_sa("d@p.iam")},
                    clear=False):
        reset_registry()
        app = create_proxy_app(prefix="/ee-api")
        assert isinstance(app, FastAPI)
        client = TestClient(app)
        resp = client.get("/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["service"] == "geeViz.eeAuth proxy"
        assert "default" in body["tenants_loaded"]
        assert body["mount_prefix"] == "/ee-api"


def test_build_proxy_router_is_mountable():
    """build_proxy_router should produce an APIRouter you can include
    in any FastAPI app at any prefix."""
    from fastapi import APIRouter, FastAPI
    from geeViz.eeAuth.server import build_proxy_router

    router = build_proxy_router()
    assert isinstance(router, APIRouter)
    # And it can be mounted
    app = FastAPI()
    app.include_router(router, prefix="/anything")
    # Catch-all route should match many path shapes
    routes = [getattr(r, "path", "") for r in app.routes]
    assert any("/anything" in p for p in routes)


def test_proxy_rejects_unknown_tenant_when_no_default():
    """When no SA is registered, the proxy should 400 — never 500."""
    from fastapi.testclient import TestClient
    from geeViz.eeAuth import reset_registry
    from geeViz.eeAuth.server import create_proxy_app

    # Clear all SA env vars to simulate misconfigured deploy
    sa_env_keys = [k for k in os.environ if "SERVICE_ACCOUNT" in k and k.startswith("GEE_")]
    saved = {k: os.environ.pop(k) for k in sa_env_keys}
    try:
        reset_registry()
        app = create_proxy_app()
        client = TestClient(app)
        resp = client.get(
            "/ee-api/v1/projects/earthengine-legacy/algorithms",
            headers={"X-geeViz-Creds": "ghost"},
        )
        # 400 with a useful message, not a 500 crash
        assert resp.status_code == 400
        assert "tenant" in resp.text.lower()
    finally:
        # Restore env vars
        for k, v in saved.items():
            os.environ[k] = v
        reset_registry()


# ─────────────────────── Backward-compat shims ───────────────────────
def test_agent_sa_registry_shim_still_works():
    """The agent's geeviz_agent.sa_registry module should re-export from
    geeViz.eeAuth.registry so existing imports keep working."""
    from geeviz_agent import sa_registry
    assert sa_registry.SARegistry is not None
    # Same identity as the library export
    from geeViz.eeAuth import SARegistry
    assert sa_registry.SARegistry is SARegistry


def test_agent_workload_tags_shim_still_works():
    from geeviz_agent import workload_tags
    from geeViz.eeAuth import build_workload_tag
    assert workload_tags.build_workload_tag is build_workload_tag


# ─────────────────────── CLI smoke test ───────────────────────
def test_main_module_help_runs():
    """`python -m geeViz.eeAuth --help` should print usage without error.

    Doesn't actually start a server — just verifies the CLI entry parses.
    """
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "geeViz.eeAuth", "--help"],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    assert "Standalone Earth Engine multi-tenant auth proxy" in result.stdout


if __name__ == "__main__":
    tests = [(k, v) for k, v in list(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {name}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {name}: {type(e).__name__}: {e}")
    print()
    if failed:
        print(f"{failed}/{len(tests)} tests FAILED")
        raise SystemExit(1)
    print(f"{len(tests)}/{len(tests)} tests passed")
