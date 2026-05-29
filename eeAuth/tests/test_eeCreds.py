"""Tests for the eeCreds high-level API."""
import base64
import json
import os
import sys
import tempfile
from unittest.mock import patch, MagicMock

_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
sys.path.insert(0, _REPO_ROOT)


def _sa_dict(client_email="sa@p.iam.gserviceaccount.com", project="p"):
    return {
        "type": "service_account",
        "client_email": client_email,
        "project_id": project,
        "private_key": "-----BEGIN PRIVATE KEY-----\nFAKE\n-----END PRIVATE KEY-----\n",
        "private_key_id": "fake",
        "client_id": "12345",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }


def _oauth_authorized_user_dict():
    """A google-auth ``authorized_user`` credentials file format."""
    return {
        "type": "authorized_user",
        "client_id": "1234.apps.googleusercontent.com",
        "client_secret": "fake-secret",
        "refresh_token": "fake-refresh-token",
    }


def _fresh():
    """Build a fresh EECreds instance per test — singleton state would
    leak across tests otherwise."""
    from geeViz.eeAuth.eeCreds import EECreds
    return EECreds()


# ─────────────────────── addCreds polymorphism ───────────────────────
def test_addCreds_dict_sa():
    creds = _fresh()
    creds.addCreds(_sa_dict(), name="x")
    info = creds.info("x")
    assert info["type"] == "sa"
    assert info["source"] == "dict"
    assert info["project_id"] == "p"
    assert info["client_email"] == "sa@p.iam.gserviceaccount.com"


def test_addCreds_dict_oauth():
    creds = _fresh()
    creds.addCreds(_oauth_authorized_user_dict(), name="ian", project="myproj")
    info = creds.info("ian")
    assert info["type"] == "oauth"
    assert info["project_id"] == "myproj"  # override worked


def test_addCreds_dict_oauth_from_refresh_token_only():
    """Even without type=authorized_user, presence of refresh_token →
    OAuth."""
    creds = _fresh()
    creds.addCreds(
        {"refresh_token": "x", "client_id": "y", "client_secret": "z"},
        name="ian", project="myproj",
    )
    assert creds.info("ian")["type"] == "oauth"


def test_addCreds_json_string():
    creds = _fresh()
    json_string = json.dumps(_sa_dict("foo@p.iam.gserviceaccount.com"))
    creds.addCreds(json_string, name="foo")
    info = creds.info("foo")
    assert info["client_email"] == "foo@p.iam.gserviceaccount.com"
    assert info["source"] == "json_string"


def test_addCreds_base64():
    creds = _fresh()
    raw = json.dumps(_sa_dict("b64@p.iam.gserviceaccount.com")).encode()
    b64 = base64.b64encode(raw).decode("ascii")
    creds.addCreds(b64, name="b")
    info = creds.info("b")
    assert info["source"] == "base64"
    assert info["client_email"] == "b64@p.iam.gserviceaccount.com"


def test_addCreds_path_to_file():
    creds = _fresh()
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as tf:
        json.dump(_sa_dict("path@p.iam.gserviceaccount.com"), tf)
        tmp = tf.name
    try:
        creds.addCreds(tmp, name="from-file")
        info = creds.info("from-file")
        assert info["client_email"] == "path@p.iam.gserviceaccount.com"
        assert info["source"].startswith("path:")
    finally:
        os.unlink(tmp)


def test_addCreds_bytes_input():
    """Bytes input is decoded as UTF-8 or base64."""
    creds = _fresh()
    raw = json.dumps(_sa_dict("bytes@p.iam.gserviceaccount.com")).encode()
    creds.addCreds(raw, name="b")
    assert creds.info("b")["client_email"] == "bytes@p.iam.gserviceaccount.com"


def test_addCreds_bad_input_raises_useful_error():
    creds = _fresh()
    try:
        creds.addCreds("definitely not json or base64 or a path !!!", name="bad")
    except ValueError as e:
        # Useful message that names the failure modes attempted
        msg = str(e).lower()
        assert "json" in msg or "base64" in msg or "path" in msg
        return
    raise AssertionError("expected ValueError on garbage input")


def test_addCreds_chains():
    """addCreds returns self for fluent style."""
    creds = _fresh()
    out = creds.addCreds(_sa_dict(), "a").addCreds(_sa_dict(), "b")
    assert out is creds
    assert creds.list() == ["a", "b"]


# ─────────────────────── introspection ───────────────────────
def test_list_and_has():
    creds = _fresh()
    assert creds.list() == []
    creds.addCreds(_sa_dict(), "x")
    creds.addCreds(_sa_dict(), "y")
    assert creds.list() == ["x", "y"]
    assert creds.has("x")
    assert not creds.has("z")


def test_current_falls_back_to_first():
    """Without explicit .use(), .current() returns the first registered name."""
    creds = _fresh()
    creds.addCreds(_sa_dict(), "first")
    creds.addCreds(_sa_dict(), "second")
    assert creds.current() == "first"


def test_info_without_args_returns_current():
    creds = _fresh()
    creds.addCreds(_sa_dict("only@p.iam.gserviceaccount.com"), "only")
    assert creds.info()["name"] == "only"


# ─────────────────────── use() ───────────────────────
def test_use_switches_tenant_immediately():
    """Plain .use() (no `with`) takes effect right away."""
    from geeViz.eeAuth import CURRENT_TENANT
    creds = _fresh()
    creds.addCreds(_sa_dict(), "a")
    creds.addCreds(_sa_dict(), "b")
    # set known state before
    token = CURRENT_TENANT.set("")
    try:
        creds.use("b")
        assert CURRENT_TENANT.get() == "b"
    finally:
        CURRENT_TENANT.reset(token)


def test_use_as_context_manager_restores_previous():
    from geeViz.eeAuth import CURRENT_TENANT
    creds = _fresh()
    creds.addCreds(_sa_dict(), "a")
    creds.addCreds(_sa_dict(), "b")
    token = CURRENT_TENANT.set("a")
    try:
        with creds.use("b"):
            assert CURRENT_TENANT.get() == "b"
        # On exit, restores to whatever was set before this .use()
        assert CURRENT_TENANT.get() == "a"
    finally:
        CURRENT_TENANT.reset(token)


def test_use_unknown_raises():
    creds = _fresh()
    creds.addCreds(_sa_dict(), "x")
    try:
        creds.use("ghost")
    except KeyError as e:
        assert "ghost" in str(e)
        return
    raise AssertionError("expected KeyError on unknown credential")


# ─────────────────────── token minting (uses google.auth mocks) ───────────────────────
def test_get_token_caches_and_refreshes():
    """First get_token mints; second returns the cache; force_refresh
    re-mints."""
    creds = _fresh()
    creds.addCreds(_sa_dict("t@p.iam.gserviceaccount.com"), "t")
    # Stub the build_credentials so we don't try to refresh a fake key
    fake_creds = MagicMock()
    fake_creds.token = "tok-1"
    with patch.object(creds, "_build_credentials", return_value=fake_creds):
        tok1 = creds.get_token("t")
        assert tok1["access_token"] == "tok-1"
        assert tok1["tenant"] == "t"
        # Second call → cache hit; refresh shouldn't be called twice
        fake_creds.token = "tok-2"
        tok2 = creds.get_token("t")
        assert tok2["access_token"] == "tok-1", "should have cached"
        # Force refresh
        tok3 = creds.get_token("t", force_refresh=True)
        assert tok3["access_token"] == "tok-2"


def test_get_token_unknown_falls_back_to_first():
    """Forgiving lookup — unknown name → first registered."""
    creds = _fresh()
    creds.addCreds(_sa_dict("default@p.iam.gserviceaccount.com"), "default")
    creds.addCreds(_sa_dict("other@p.iam.gserviceaccount.com"), "other")
    fake_creds = MagicMock()
    fake_creds.token = "tok"
    with patch.object(creds, "_build_credentials", return_value=fake_creds):
        tok = creds.get_token("ghost")
        # Falls back to first registered, NOT to the requested ghost
        assert tok["tenant"] == "default"


# ─────────────────────── start() / proxy ───────────────────────
def test_start_requires_registered_creds():
    creds = _fresh()
    try:
        creds.start(launch_proxy=False, ee_init=False)
    except RuntimeError as e:
        assert "no credentials" in str(e).lower()
        return
    raise AssertionError("expected RuntimeError on start() with empty registry")


def test_start_returns_status():
    """start(launch_proxy=False, ee_init=False) is idempotent + reports state."""
    creds = _fresh()
    creds.addCreds(_sa_dict(), "x")
    status = creds.start(launch_proxy=False, ee_init=False)
    assert status["started"] is True
    assert status["tenants"] == ["x"]
    # Second call returns the same status (idempotent)
    status2 = creds.start(launch_proxy=False, ee_init=False)
    assert status2["started"] is True


# ─────────────────────── compatibility with build_proxy_router ───────────────────────
def test_eeCreds_works_with_build_proxy_router():
    """Polymorphism: build_proxy_router should accept an EECreds the
    same way it accepts an SARegistry."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from geeViz.eeAuth.server import build_proxy_router

    creds = _fresh()
    creds.addCreds(_sa_dict("rooted@p.iam.gserviceaccount.com"), "default")

    app = FastAPI()
    app.include_router(build_proxy_router(creds=creds), prefix="/ee-api")

    # The proxy will fail on actual upstream calls (no real key), but
    # building the router and resolving the tenant resolver should work.
    # Try a GET with an unknown tenant → should return 400 not 500.
    client = TestClient(app)
    resp = client.get(
        "/ee-api/v1/projects/test/algorithms",
        headers={"X-geeViz-Creds": "this-tenant-doesnt-exist"},
    )
    # EECreds.get_token() is forgiving (falls back to first registered)
    # so this WON'T 400 — it'll try to mint with the fake SA and fail
    # later (500 from token mint OR 502 from upstream). Either way,
    # the routing layer worked.
    assert resp.status_code in (200, 400, 500, 502)


def test_create_proxy_app_with_eeCreds_lists_tenants():
    from fastapi.testclient import TestClient
    from geeViz.eeAuth.server import create_proxy_app

    creds = _fresh()
    creds.addCreds(_sa_dict(), "tenant-a")
    creds.addCreds(_sa_dict(), "tenant-b")

    app = create_proxy_app(creds=creds)
    resp = TestClient(app).get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["tenants_loaded"]) == {"tenant-a", "tenant-b"}


# ─────────────────────── singleton ───────────────────────
def test_module_singleton_exists_and_is_eecreds_instance():
    from geeViz.eeAuth import eeCreds
    from geeViz.eeAuth.eeCreds import EECreds
    assert isinstance(eeCreds, EECreds)


def test_router_helper_returns_apirouter():
    from fastapi import APIRouter
    creds = _fresh()
    creds.addCreds(_sa_dict(), "x")
    router = creds.router()
    assert isinstance(router, APIRouter)


# ─────────────────────── User-question tests ───────────────────────
def test_single_cred_used_automatically_without_use():
    """If only one credential is registered, get_token returns it
    without any .use() call needed — the simplest possible path
    'works automatically'."""
    creds = _fresh()
    creds.addCreds(_sa_dict("only@p.iam.gserviceaccount.com"), "only-one")
    fake_creds = MagicMock()
    fake_creds.token = "tok"
    with patch.object(creds, "_build_credentials", return_value=fake_creds):
        # No .use() call — just fetch the token
        tok = creds.get_token()
        assert tok["tenant"] == "only-one"
        assert tok["access_token"] == "tok"


def test_stop_clears_proxy_state():
    """eeCreds.stop() must clear the proxy thread + URL so the registry
    can be restarted cleanly."""
    creds = _fresh()
    creds.addCreds(_sa_dict(), "x")
    # Use start without launching the proxy (faster + no port binding)
    creds.start(launch_proxy=False, ee_init=False)
    assert creds._started is True
    creds.stop()
    assert creds._started is False
    assert creds._proxy_url is None
    assert creds._proxy_thread is None


def test_stop_is_safe_when_not_started():
    """Calling stop() on a never-started registry should be a no-op
    rather than crashing."""
    creds = _fresh()
    creds.stop()   # should not raise
    assert creds._started is False


def test_default_header_mentions_geeviz():
    """The default tenant_header should be geeViz-branded so it's
    obviously library-owned in browser DevTools / packet captures."""
    from geeViz.eeAuth.server import DEFAULT_TENANT_HEADER as SRV_DEFAULT
    from geeViz.eeAuth.client import DEFAULT_TENANT_HEADER as CL_DEFAULT
    assert "geeViz" in SRV_DEFAULT, \
        f"server default should mention geeViz, got {SRV_DEFAULT!r}"
    # Client and server must agree by default — otherwise routing breaks
    assert SRV_DEFAULT == CL_DEFAULT, \
        "client and server default headers must match"


def test_tenant_header_is_configurable():
    """build_proxy_router must accept tenant_header= so deployments
    can use whatever name they want (e.g. AskTerra agent uses
    X-AskTerra-Tenant for back-compat)."""
    import inspect
    from geeViz.eeAuth.server import build_proxy_router
    sig = inspect.signature(build_proxy_router)
    assert "tenant_header" in sig.parameters

    from geeViz.eeAuth.client import initialize_via_proxy, TenantAwareHttp
    # Both client paths must accept it too
    assert "tenant_header" in inspect.signature(initialize_via_proxy).parameters


def test_stop_then_restart():
    """A stopped registry can be started again."""
    creds = _fresh()
    creds.addCreds(_sa_dict(), "x")
    creds.start(launch_proxy=False, ee_init=False)
    creds.stop()
    # Restart works
    status = creds.start(launch_proxy=False, ee_init=False)
    assert status["started"] is True


# ─────────────────────── Port-conflict handling ───────────────────────
def test_find_free_port_returns_preferred_when_available():
    """When the preferred port is bindable, return it as-is."""
    creds = _fresh()
    import socket
    # Get a port that's definitely free by binding-then-closing
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        free_port = s.getsockname()[1]
    chosen = creds._find_free_port("127.0.0.1", free_port)
    assert chosen == free_port


def test_find_free_port_walks_past_busy():
    """When the preferred port is busy, walk up until a free one is found."""
    creds = _fresh()
    import socket
    # Bind two consecutive ports so the walk has to step past them
    blocker1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker1.bind(("127.0.0.1", 0))
    busy_port = blocker1.getsockname()[1]
    blocker2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        blocker2.bind(("127.0.0.1", busy_port + 1))
    except OSError:
        # Adjacent port already in use — skip the +1 part of the assertion
        blocker2.close()
        blocker2 = None
    try:
        chosen = creds._find_free_port("127.0.0.1", busy_port)
        # Must have walked past at least the busy port
        assert chosen != busy_port, \
            "should have walked past the busy preferred port"
        if blocker2 is not None:
            assert chosen != busy_port + 1, \
                "should have walked past the adjacent busy port too"
        # And the chosen port is bindable right now (probe-and-close)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", chosen))
    finally:
        blocker1.close()
        if blocker2 is not None:
            blocker2.close()


def test_find_free_port_falls_back_to_os_assigned_when_all_taken():
    """If every port in the explicit walk range is taken, the OS picks
    any free port (port 0 in bind() means ephemeral)."""
    creds = _fresh()
    # Stub socket.socket to ALWAYS raise OSError on bind for the
    # 50-port walk, but succeed on the port=0 fallback path.
    import socket
    real_socket = socket.socket

    class _FakeSocket:
        def __init__(self, family, type_, *args, **kwargs):
            self._sock = real_socket(family, type_, *args, **kwargs)
            self._call_count = 0

        def bind(self, addr):
            host, port = addr
            # Fail every explicit port in the walk range; succeed only
            # when the caller asks for ephemeral (port == 0).
            if port == 0:
                return self._sock.bind(addr)
            raise OSError(10048, "simulated EADDRINUSE")

        def getsockname(self):
            return self._sock.getsockname()

        def close(self):
            self._sock.close()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.close()

    with patch("socket.socket", _FakeSocket):
        chosen = creds._find_free_port("127.0.0.1", 8889)
    # Must have gotten SOME port — the OS-assigned fallback fires
    assert isinstance(chosen, int) and chosen > 0


def test_sync_oauth_project_updates_all_oauth_entries():
    """sync_oauth_project should update every OAuth entry's project_id
    and invalidate cached tokens, so the next mint includes the new
    project. SA entries are NOT touched (their project_id is from JSON)."""
    creds = _fresh()
    creds.addCreds(_sa_dict(project="sa-keeps-this"), name="sa-entry")
    creds.addCreds(_oauth_authorized_user_dict(), name="oauth-1", project="wrong-1")
    creds.addCreds(_oauth_authorized_user_dict(), name="oauth-2", project="wrong-2")

    # Prime a cached token on oauth-1 so we can confirm it gets invalidated
    fake_creds = MagicMock()
    fake_creds.token = "stale-token"
    with patch.object(creds, "_build_credentials", return_value=fake_creds):
        creds.get_token("oauth-1")
    assert creds._entries["oauth-1"]._token["access_token"] == "stale-token"

    updated = creds.sync_oauth_project("correct-project")

    # 2 OAuth entries updated, SA untouched
    assert updated == 2
    assert creds.info("oauth-1")["project_id"] == "correct-project"
    assert creds.info("oauth-2")["project_id"] == "correct-project"
    assert creds.info("sa-entry")["project_id"] == "sa-keeps-this", \
        "SA entry must not be touched by sync_oauth_project"
    # Cached token invalidated on oauth-1 → next get_token re-mints
    assert creds._entries["oauth-1"]._token == {}


def test_sync_oauth_project_rejects_earthengine_legacy():
    """The SDK placeholder ``earthengine-legacy`` must never propagate
    via sync_oauth_project — otherwise we'd just re-create the original
    bug after legacy init was somehow set to the placeholder."""
    creds = _fresh()
    creds.addCreds(_oauth_authorized_user_dict(), name="ian",
                   project="my-real-project")
    updated = creds.sync_oauth_project("earthengine-legacy")
    assert updated == 0
    assert creds.info("ian")["project_id"] == "my-real-project", \
        "entry must be untouched when sync called with the legacy placeholder"


def test_sync_oauth_project_noop_when_already_correct():
    """sync_oauth_project with the same project that's already set
    should be a no-op (no log noise, no token invalidation)."""
    creds = _fresh()
    creds.addCreds(_oauth_authorized_user_dict(), name="ian",
                   project="already-right")
    updated = creds.sync_oauth_project("already-right")
    assert updated == 0


def test_ee_persistent_refresh_token_only_credentials_work():
    """The old ``earthengine authenticate`` credentials file format
    contains just ``refresh_token`` (and sometimes ``scopes``) with no
    ``client_id`` / ``client_secret`` / ``token_uri``. EE injects its
    well-known OAuth client at runtime — we have to do the same when
    building google.oauth2.credentials.Credentials, otherwise the
    first refresh raises:

        RefreshError: The credentials do not contain the necessary
        fields need to refresh the access token. You must specify
        refresh_token, token_uri, client_id, and client_secret.

    Regression test for the eeCreds proxy crash when auto-discovery
    pulled in a bare-refresh-token EE persistent credentials file.
    """
    creds = _fresh()
    # Bare EE-persistent file — only the refresh token
    creds.addCreds({"refresh_token": "fake-refresh"}, name="ee-persistent")

    import ee.oauth
    # Build the credentials object (lazy until first get_token; force it)
    entry = creds._entries["ee-persistent"]
    google_creds = creds._build_credentials(entry)

    # The four refresh-required fields must all be populated — either
    # from the user's JSON or from EE's well-known fallback.
    assert google_creds.refresh_token == "fake-refresh"
    assert google_creds.client_id == ee.oauth.CLIENT_ID, \
        "must fall back to EE's well-known client_id when JSON lacks it"
    assert google_creds.client_secret == ee.oauth.CLIENT_SECRET, \
        "must fall back to EE's well-known client_secret when JSON lacks it"
    assert google_creds.token_uri  # must be a non-empty URL


def test_oauth_user_provided_client_id_takes_precedence():
    """If the JSON has its own client_id/client_secret (e.g. a custom
    OAuth app), those win over EE's well-known fallback."""
    creds = _fresh()
    creds.addCreds({
        "type": "authorized_user",
        "refresh_token": "x",
        "client_id": "MY-CUSTOM-CLIENT.apps.googleusercontent.com",
        "client_secret": "my-custom-secret",
    }, name="custom")

    entry = creds._entries["custom"]
    google_creds = creds._build_credentials(entry)
    assert google_creds.client_id == "MY-CUSTOM-CLIENT.apps.googleusercontent.com"
    assert google_creds.client_secret == "my-custom-secret"


def test_launch_proxy_picks_alternate_port_when_preferred_busy():
    """End-to-end: when proxy_port is busy, start() should still
    succeed on an alternate port, and proxy_url reflects the actual port."""
    creds = _fresh()
    creds.addCreds(_sa_dict(), "x")
    import socket
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", 0))
    busy_port = blocker.getsockname()[1]
    try:
        # Stub initialize_via_proxy so we don't actually init ee
        from geeViz.eeAuth import client as _cl
        with patch.object(_cl, "initialize_via_proxy", return_value=True):
            creds.start(proxy_port=busy_port)
        try:
            assert creds.proxy_url, "proxy_url should be set after start"
            # The actual port in the URL is NOT the busy one
            assert f":{busy_port}/" not in creds.proxy_url, \
                f"start() bound the busy port {busy_port}; URL: {creds.proxy_url}"
        finally:
            creds.stop()
    finally:
        blocker.close()


# ─────────────────── Map.view() proxy integration ───────────────────
def test_map_view_uses_eeCreds_proxy_when_available():
    """When eeCreds.proxy_url is set, Map.view() must register that
    upstream with the local HTTP server so /ee-api/* gets reverse-proxied
    — and keep the viewer URL empty (no proxy address baked in)."""
    src_path = os.path.join(_REPO_ROOT, "geeViz", "geeView.py")
    src = open(src_path, encoding="utf-8").read()
    # Find the view() method body
    view_start = src.index("def view(")
    view_end = src.index("\n    def ", view_start + 100)
    view_body = src[view_start:view_end]

    # Must check eeCreds for an active proxy
    assert "eeCreds" in view_body, \
        "Map.view() must consult eeCreds for an active proxy URL"
    assert "proxy_url" in view_body, \
        "Map.view() must read eeCreds.proxy_url"
    # Upstream must be registered with the local HTTP server so its
    # _GeeVizRequestHandler can reverse-proxy /ee-api/* requests.
    assert "_set_ee_api_upstream(ee_proxy_url)" in view_body, \
        "Map.view() must register the proxy with the local server " \
        "via _set_ee_api_upstream() so /ee-api/* is reverse-proxied"
    # And the legacy direct-token path must remain as fallback
    assert "_mint_access_token" in view_body, \
        "Map.view() must keep the direct-token fallback for when " \
        "no proxy is running"


def test_map_view_bakes_tenant_into_run_js_not_url():
    """The tenant must be baked into the per-session run_js (NOT the
    page URL). This pins every browser tab to the tenant that was
    current at Map.view() time, immune to subsequent
    ``eeCreds.use()`` changes that mutate process-wide state."""
    src_path = os.path.join(_REPO_ROOT, "geeViz", "geeView.py")
    src = open(src_path, encoding="utf-8").read()
    view_start = src.index("def view(")
    view_end = src.index("\n    def ", view_start + 100)
    view_body = src[view_start:view_end]
    proxy_branch_start = view_body.index("if ee_proxy_url:")
    proxy_branch_end = view_body.index("else:", proxy_branch_start)
    proxy_branch = view_body[proxy_branch_start:proxy_branch_end]
    # Query string in the proxy branch must be empty — no tenant param.
    assert 'query = ""' in proxy_branch, \
        "proxy branch must leave the URL query empty; tenant goes in run_js"
    assert "?tenant=" not in proxy_branch, \
        "proxy branch must NOT add ?tenant= to the URL"
    # And _build_run_js must accept and emit the tenant.
    assert "_build_run_js(tenant=" in view_body, \
        "view() must pass tenant= to _build_run_js so it's baked into JS"
    build_start = src.index("def _build_run_js(self")
    build_end = src.index("\n    def ", build_start + 1)
    build_body = src[build_start:build_end]
    assert "authProxyAPIURL=window.location.origin" in build_body, \
        "_build_run_js must emit a JS assignment to authProxyAPIURL"
    assert "/ee-api/t/" in build_body, \
        "_build_run_js must use path-prefix tenant routing (/ee-api/t/<tenant>)"


def test_map_view_falls_back_without_eecreds_running():
    """When eeCreds isn't started (proxy_url is None), Map.view() must
    fall back to the legacy direct-token mint path."""
    src_path = os.path.join(_REPO_ROOT, "geeViz", "geeView.py")
    src = open(src_path, encoding="utf-8").read()
    view_start = src.index("def view(")
    view_end = src.index("\n    def ", view_start + 100)
    view_body = src[view_start:view_end]
    # Conditional must check for an empty / falsy proxy_url and skip
    # the proxy branch in that case (we look for the legacy URL pattern
    # being still reachable).
    assert "accessTokenCreationTime={}" in view_body, \
        "legacy direct-token URL pattern must still be present"


# ─────────────── /ee-api reverse-proxy in _GeeVizRequestHandler ───────────────
def test_set_ee_api_upstream_round_trip():
    """``_set_ee_api_upstream`` must accept a URL, normalize trailing
    slashes, and ``None`` must reset the upstream so the handler 503s."""
    from geeViz import geeView
    try:
        geeView._set_ee_api_upstream("http://127.0.0.1:8889/ee-api/")
        assert geeView._EE_API_UPSTREAM == "http://127.0.0.1:8889/ee-api", \
            f"trailing slash must be stripped; got {geeView._EE_API_UPSTREAM!r}"
        geeView._set_ee_api_upstream(None)
        assert geeView._EE_API_UPSTREAM is None
        geeView._set_ee_api_upstream("")
        assert geeView._EE_API_UPSTREAM is None
    finally:
        geeView._set_ee_api_upstream(None)


def test_resolve_ee_tenant_precedence_request_then_referer_then_current():
    """Tenant resolution order: explicit ?tenant on the request → ?tenant
    on the Referer URL → ``eeCreds.current()``."""
    from geeViz import geeView
    from unittest.mock import patch

    # 1. Explicit ?tenant on the request itself wins outright.
    assert geeView._resolve_ee_tenant(
        "/ee-api/v1/value:compute?tenant=alpha",
        referer="http://localhost:8001/geeView/?tenant=beta",
    ) == "alpha"

    # 2. No ?tenant on the request → use Referer's ?tenant.
    assert geeView._resolve_ee_tenant(
        "/ee-api/v1/value:compute",
        referer="http://localhost:8001/geeView/?tenant=beta",
    ) == "beta"

    # 3. Neither → eeCreds.current().
    class _StubCreds:
        @staticmethod
        def current():
            return "from-current"
    with patch("geeViz.eeAuth.eeCreds.eeCreds", _StubCreds):
        assert geeView._resolve_ee_tenant(
            "/ee-api/v1/value:compute", referer="",
        ) == "from-current"


def test_geeviz_request_handler_proxies_ee_api(tmp_path):
    """End-to-end: stand up a stub upstream + the geeViz handler, hit
    /ee-api/* on the handler, and verify the request lands at the upstream
    with the tenant header stamped and the response streamed back."""
    import http.server
    import socketserver
    import threading
    import urllib.request
    from geeViz import geeView

    upstream_received = {}

    class _Upstream(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_args, **_kwargs):
            pass

        def do_GET(self):  # noqa: N802
            upstream_received["path"] = self.path
            upstream_received["headers"] = dict(self.headers)
            body = b'{"upstream":"ok"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    upstream = socketserver.TCPServer(("127.0.0.1", 0), _Upstream)
    upstream_port = upstream.server_address[1]
    upstream_thread = threading.Thread(
        target=upstream.serve_forever, daemon=True
    )
    upstream_thread.start()

    handler_server = socketserver.ThreadingTCPServer(
        ("127.0.0.1", 0), geeView._GeeVizRequestHandler
    )
    handler_server.daemon_threads = True
    handler_port = handler_server.server_address[1]
    handler_thread = threading.Thread(
        target=handler_server.serve_forever, daemon=True
    )
    handler_thread.start()

    try:
        geeView._set_ee_api_upstream(
            f"http://127.0.0.1:{upstream_port}/ee-api"
        )
        # Hit the handler with an /ee-api request, including ?tenant.
        req = urllib.request.Request(
            f"http://127.0.0.1:{handler_port}/ee-api/v1/value:compute?tenant=acme"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            assert resp.status == 200
            assert resp.read() == b'{"upstream":"ok"}'
        # Upstream must have seen the forwarded request with tenant header.
        # urllib normalises header names via str.capitalize(), and the BaseHTTPRequestHandler
        # preserves the on-wire casing — so look it up case-insensitively.
        assert upstream_received["path"] == "/ee-api/v1/value:compute?tenant=acme"
        hdrs_lower = {k.lower(): v for k, v in upstream_received["headers"].items()}
        assert hdrs_lower.get("x-geeviz-creds") == "acme", \
            f"expected tenant header to be forwarded; got {hdrs_lower!r}"
    finally:
        geeView._set_ee_api_upstream(None)
        handler_server.shutdown(); handler_server.server_close()
        upstream.shutdown(); upstream.server_close()


def test_geeviz_request_handler_parses_tenant_from_path_prefix(tmp_path):
    """``/ee-api/t/<tenant>/v1/...`` must route to the named tenant
    regardless of process-wide ``eeCreds.current()``. This is the
    mechanism that pins each browser tab to its Map.view()-time tenant
    even when subsequent ``eeCreds.use()`` switches change global state."""
    import http.server
    import socketserver
    import threading
    import urllib.request
    from unittest.mock import patch
    from geeViz import geeView

    upstream_received = {}

    class _Upstream(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_a, **_kw):
            pass

        def do_GET(self):  # noqa: N802
            upstream_received["path"] = self.path
            upstream_received["headers"] = dict(self.headers)
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    upstream = socketserver.TCPServer(("127.0.0.1", 0), _Upstream)
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()

    handler_server = socketserver.ThreadingTCPServer(
        ("127.0.0.1", 0), geeView._GeeVizRequestHandler,
    )
    handler_server.daemon_threads = True
    handler_thread = threading.Thread(target=handler_server.serve_forever, daemon=True)
    handler_thread.start()

    # Stub eeCreds.current() so we can prove the path-prefix WINS over it.
    class _StubCreds:
        @staticmethod
        def current():
            return "drifted-default"

    try:
        geeView._set_ee_api_upstream(
            f"http://127.0.0.1:{upstream.server_address[1]}/ee-api",
        )
        url = (
            f"http://127.0.0.1:{handler_server.server_address[1]}"
            f"/ee-api/t/pinned-tenant/v1/value:compute"
        )
        with patch("geeViz.eeAuth.eeCreds.eeCreds", _StubCreds):
            with urllib.request.urlopen(url, timeout=10) as resp:
                assert resp.status == 200
        # Path forwarded WITHOUT the /t/<tenant> segment
        assert upstream_received["path"] == "/ee-api/v1/value:compute", \
            f"path prefix must be stripped; got {upstream_received['path']!r}"
        # Tenant taken from the path (NOT from eeCreds.current(), which
        # would have returned 'drifted-default')
        hdrs = {k.lower(): v for k, v in upstream_received["headers"].items()}
        assert hdrs.get("x-geeviz-creds") == "pinned-tenant", \
            f"path tenant must win; got {hdrs!r}"
    finally:
        geeView._set_ee_api_upstream(None)
        handler_server.shutdown(); handler_server.server_close()
        upstream.shutdown(); upstream.server_close()


def test_build_run_js_emits_tenant_pin_when_provided():
    """``_build_run_js(tenant='foo')`` must produce JS that re-assigns
    ``authProxyAPIURL`` to a tenant-prefixed origin path. With no
    tenant, the JS must NOT touch ``authProxyAPIURL`` so the bundle's
    own default (``window.location.origin + '/ee-api'``) sticks."""
    from geeViz.geeView import Map
    # No tenant — no override.
    js = Map._build_run_js(tenant="")
    assert "authProxyAPIURL=" not in js.split("function runGeeViz")[0], \
        "no tenant arg should leave authProxyAPIURL alone"

    # With tenant — override at the very top of the script.
    js2 = Map._build_run_js(tenant="acme")
    pre = js2.split("function runGeeViz")[0]
    assert "authProxyAPIURL=window.location.origin+'/ee-api/t/acme'" in pre, \
        f"expected tenant pin in JS prefix; got: {pre[:200]!r}"
    # Must execute BEFORE function runGeeViz is defined so it fires at load time
    assert pre.index("authProxyAPIURL=") < pre.index("var layerLoadErrorMessages"), \
        "tenant pin must run BEFORE the rest of runGeeViz setup"


def test_geeviz_request_handler_503s_when_no_upstream_registered():
    """If no upstream is registered, /ee-api requests must 503 cleanly
    rather than hanging or crashing the server."""
    import socketserver
    import threading
    import urllib.error
    import urllib.request
    from geeViz import geeView

    geeView._set_ee_api_upstream(None)
    handler_server = socketserver.ThreadingTCPServer(
        ("127.0.0.1", 0), geeView._GeeVizRequestHandler
    )
    handler_server.daemon_threads = True
    handler_port = handler_server.server_address[1]
    handler_thread = threading.Thread(
        target=handler_server.serve_forever, daemon=True
    )
    handler_thread.start()
    try:
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{handler_port}/ee-api/anything", timeout=5
            )
            raised = False
        except urllib.error.HTTPError as e:
            raised = True
            assert e.code == 503, f"expected 503 when no upstream; got {e.code}"
        assert raised, "no upstream must surface as 503, not 200"
    finally:
        handler_server.shutdown(); handler_server.server_close()


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
