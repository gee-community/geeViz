"""Comprehensive tests for credential auto-discovery and Map.view mode
selection. Covers the full matrix:

- Credential types: SA via path env, SA via b64 env, OAuth refresh token
  (authorized_user file), bare ``refresh_token`` dict
- Quantities: zero, one, multiple
- Auth modes: ``auto``, ``proxy``, ``legacy``
- Surfaces: Python SDK init (via ensure_started), Map.view() URL builder

Discovery is exercised against a fake-filesystem + env-patched setup
so no real GCP credentials are required.
"""
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


# ──────────────────────── helpers ────────────────────────
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


def _oauth_dict():
    """A `~/.config/earthengine/credentials`-style authorized_user file."""
    return {
        "type": "authorized_user",
        "client_id": "1234.apps.googleusercontent.com",
        "client_secret": "fake-secret",
        "refresh_token": "fake-refresh-token",
    }


def _sa_b64(**kw):
    return base64.b64encode(json.dumps(_sa_dict(**kw)).encode()).decode("ascii")


def _fresh():
    from geeViz.eeAuth.eeCreds import EECreds
    return EECreds()


# Track tmp files we create so the discovery tests can put real paths
# in env vars then clean up.
_tmp_files: list[str] = []


def _write_tmp(payload: dict, suffix=".json") -> str:
    """Write JSON to a tmp file and return its path. Tracked for cleanup."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    _tmp_files.append(path)
    return path


def _cleanup_tmp():
    for p in _tmp_files:
        try:
            os.unlink(p)
        except OSError:
            pass
    _tmp_files.clear()


# ─────────────────────── discover() — credential types ───────────────────────
def test_discover_finds_adc_path():
    """Discovers GOOGLE_APPLICATION_CREDENTIALS pointing at an SA JSON."""
    creds = _fresh()
    path = _write_tmp(_sa_dict("adc@p.iam.gserviceaccount.com"))
    try:
        with patch.dict(os.environ,
                        {"GOOGLE_APPLICATION_CREDENTIALS": path},
                        clear=False):
            discovered = creds.discover()
        assert "adc" in discovered
        assert creds.has("adc")
        info = creds.info("adc")
        assert info["client_email"] == "adc@p.iam.gserviceaccount.com"
        assert info["type"] == "sa"
    finally:
        _cleanup_tmp()


def test_discover_finds_ee_persistent_oauth():
    """Discovers `~/.config/earthengine/credentials` style refresh token."""
    creds = _fresh()
    path = _write_tmp(_oauth_dict())
    try:
        # Patch ee.oauth.get_credentials_path to point at our tmp file.
        import ee.oauth as _ee_oauth
        with patch.object(_ee_oauth, "get_credentials_path", return_value=path):
            with patch.dict(os.environ, {}, clear=False):
                # Make sure GOOGLE_APPLICATION_CREDENTIALS is unset so it
                # doesn't compete with the ee-persistent lookup.
                os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
                discovered = creds.discover()
        assert "ee-persistent" in discovered
        assert creds.has("ee-persistent")
        info = creds.info("ee-persistent")
        assert info["type"] == "oauth", \
            "authorized_user JSON must be classified as oauth"
    finally:
        _cleanup_tmp()


def test_discover_backfills_project_for_oauth_from_ee_state():
    """When ``ee.Initialize(project='X')`` has been called, discovery
    must pick X up as the project for OAuth entries — otherwise the
    proxy forwards EE calls without ``x-goog-user-project`` and the
    upstream falls back to ``earthengine-legacy`` which personal
    Google accounts can't use → 403 'project not found or deleted'."""
    creds = _fresh()
    path = _write_tmp(_oauth_dict())
    try:
        # Stub ee.data._get_state to simulate a successful prior
        # ee.Initialize(project='rcr-gee-training').
        class _FakeState:
            cloud_api_user_project = "rcr-gee-training"
        import ee.data, ee.oauth as _ee_oauth
        with patch.object(ee.data, "_get_state", return_value=_FakeState()), \
             patch.object(_ee_oauth, "get_credentials_path", return_value=path), \
             patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
            os.environ.pop("GOOGLE_CLOUD_PROJECT", None)
            os.environ.pop("GEE_PROJECT", None)
            creds.discover()

        # The OAuth entry must have the project backfilled
        info = creds.info("ee-persistent")
        assert info["project_id"] == "rcr-gee-training", \
            f"OAuth entry should have project from EE state; got {info['project_id']!r}"
        # And the token dict (which the proxy reads) should carry it too
        entry = creds._entries["ee-persistent"]
        assert entry.project_id == "rcr-gee-training"
    finally:
        _cleanup_tmp()


def test_discover_backfills_project_for_oauth_from_env_var():
    """Falls back to GOOGLE_CLOUD_PROJECT when ee.data state AND ADC
    don't have a project (i.e. ee.Initialize never called and the user
    hasn't run ``gcloud auth application-default set-quota-project``)."""
    creds = _fresh()
    path = _write_tmp(_oauth_dict())
    try:
        # Stub ee.data._get_state to return an empty project
        class _FakeState:
            cloud_api_user_project = None
        import ee.data, ee.oauth as _ee_oauth
        with patch.object(ee.data, "_get_state", return_value=_FakeState()), \
             patch.object(_ee_oauth, "get_credentials_path", return_value=path), \
             patch.object(_ee_oauth, "get_appdefault_project", return_value=None), \
             patch.dict(os.environ,
                        {"GOOGLE_CLOUD_PROJECT": "my-fallback-project"},
                        clear=False):
            os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
            creds.discover()
        assert creds.info("ee-persistent")["project_id"] == "my-fallback-project"
    finally:
        _cleanup_tmp()


def test_discover_backfills_project_for_oauth_from_adc():
    """ADC's ``quota_project_id`` is the source EE itself uses, so it
    should take priority over env vars / gcloud-config when neither
    ee.data state nor an explicit env var is set."""
    creds = _fresh()
    path = _write_tmp(_oauth_dict())
    try:
        class _FakeState:
            cloud_api_user_project = None
        import ee.data, ee.oauth as _ee_oauth
        with patch.object(ee.data, "_get_state", return_value=_FakeState()), \
             patch.object(_ee_oauth, "get_credentials_path", return_value=path), \
             patch.object(_ee_oauth, "get_appdefault_project",
                          return_value="adc-quota-project"), \
             patch("geeViz.eeAuth.eeCreds._gcloud_default_project",
                   return_value="gcloud-other-project"), \
             patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
            os.environ.pop("GOOGLE_CLOUD_PROJECT", None)
            os.environ.pop("GEE_PROJECT", None)
            creds.discover()
        # ADC must beat both env vars (unset here) and gcloud-config
        assert creds.info("ee-persistent")["project_id"] == "adc-quota-project"
    finally:
        _cleanup_tmp()


def test_discover_falls_back_to_gcloud_config_when_no_other_hint():
    """When ee.data state is empty, ADC has no quota_project_id, AND
    env vars are unset, fall back to ``gcloud config get-value project``.
    This is the chicken-and-egg scenario: ``import geeViz.geeView``
    runs robustInitializer BEFORE the user has called
    ``ee.Initialize(project=...)``, so we have nothing else to read."""
    from geeViz.eeAuth import eeCreds as _eecreds_module
    creds = _fresh()
    path = _write_tmp(_oauth_dict())
    try:
        class _FakeState:
            cloud_api_user_project = None
        import ee.data, ee.oauth as _ee_oauth
        with patch.object(ee.data, "_get_state", return_value=_FakeState()), \
             patch.object(_ee_oauth, "get_credentials_path", return_value=path), \
             patch.object(_ee_oauth, "get_appdefault_project", return_value=None), \
             patch("geeViz.eeAuth.eeCreds._gcloud_default_project",
                   return_value="gcloud-fallback-project"), \
             patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
            os.environ.pop("GOOGLE_CLOUD_PROJECT", None)
            os.environ.pop("GEE_PROJECT", None)
            creds.discover()
        assert creds.info("ee-persistent")["project_id"] == "gcloud-fallback-project"
    finally:
        _cleanup_tmp()


def test_detect_oauth_project_filters_out_earthengine_legacy_placeholder():
    """``ee.data._get_state().cloud_api_user_project`` defaults to the
    literal string ``earthengine-legacy`` BEFORE any ``ee.Initialize(
    project=...)`` runs. That's the SDK's internal placeholder for
    "no real project set" — treating it as a hit would route every
    request through a consumer personal accounts can't use → 403.

    Detection must filter this value out at every step and fall
    through to ADC / env vars / gcloud config."""
    from geeViz.eeAuth.eeCreds import EECreds
    # Stub state to return the placeholder, env vars to be unset,
    # and gcloud to return a real project.
    class _FakeState:
        cloud_api_user_project = "earthengine-legacy"
    import ee.data, ee.oauth as _ee_oauth
    with patch.object(ee.data, "_get_state", return_value=_FakeState()), \
         patch.object(_ee_oauth, "get_appdefault_project", return_value=None), \
         patch("geeViz.eeAuth.eeCreds._gcloud_default_project",
               return_value="real-gcloud-project"), \
         patch.dict(os.environ, {}, clear=False):
        os.environ.pop("GOOGLE_CLOUD_PROJECT", None)
        os.environ.pop("GEE_PROJECT", None)
        result = EECreds._detect_oauth_project()
    assert result == "real-gcloud-project", \
        f"earthengine-legacy must be filtered; got {result!r}"


def test_detect_oauth_project_filters_legacy_from_env_vars_too():
    """If a user has GOOGLE_CLOUD_PROJECT=earthengine-legacy set
    (somehow — copy-paste mistake, misguided tutorial), filter that
    out too — never let the placeholder propagate."""
    from geeViz.eeAuth.eeCreds import EECreds
    class _FakeState:
        cloud_api_user_project = None
    import ee.data, ee.oauth as _ee_oauth
    with patch.object(ee.data, "_get_state", return_value=_FakeState()), \
         patch.object(_ee_oauth, "get_appdefault_project", return_value=None), \
         patch("geeViz.eeAuth.eeCreds._gcloud_default_project",
               return_value="real-gcloud-project"), \
         patch.dict(os.environ,
                    {"GOOGLE_CLOUD_PROJECT": "earthengine-legacy"},
                    clear=False):
        result = EECreds._detect_oauth_project()
    assert result == "real-gcloud-project", \
        "earthengine-legacy must be filtered from env vars too"


def test_detect_oauth_project_filters_sdk_projects():
    """EE's shared OAuth-client project numbers (e.g. 764086051850) are
    listed in ``ee.oauth.SDK_PROJECTS``. They aren't billable by end
    users, so any source returning one of them must be filtered the
    same way ``earthengine-legacy`` is."""
    from geeViz.eeAuth.eeCreds import EECreds
    class _FakeState:
        cloud_api_user_project = None
    import ee.data, ee.oauth as _ee_oauth
    # Use a real SDK project so is_sdk_project returns True.
    sdk_proj = _ee_oauth.SDK_PROJECTS[0]
    with patch.object(ee.data, "_get_state", return_value=_FakeState()), \
         patch.object(_ee_oauth, "get_appdefault_project",
                      return_value=sdk_proj), \
         patch("geeViz.eeAuth.eeCreds._gcloud_default_project",
               return_value="real-user-project"), \
         patch.dict(os.environ, {}, clear=False):
        os.environ.pop("GOOGLE_CLOUD_PROJECT", None)
        os.environ.pop("GEE_PROJECT", None)
        result = EECreds._detect_oauth_project()
    assert result == "real-user-project", \
        f"SDK project {sdk_proj!r} must be filtered; got {result!r}"


def test_gcloud_default_project_returns_empty_when_unset():
    """``gcloud config get-value project`` returning ``(unset)`` or
    empty must produce ``""`` from the helper — never the literal
    string ``(unset)``."""
    from geeViz.eeAuth.eeCreds import _gcloud_default_project
    from unittest.mock import MagicMock
    import subprocess as _sp
    fake_result = MagicMock()
    fake_result.returncode = 0
    fake_result.stdout = "(unset)\n"
    with patch.object(_sp, "run", return_value=fake_result):
        with patch("shutil.which", return_value="/fake/gcloud"):
            assert _gcloud_default_project() == ""


def test_gcloud_default_project_handles_missing_gcloud_silently():
    """No gcloud installed → return empty, no exception."""
    from geeViz.eeAuth.eeCreds import _gcloud_default_project
    with patch("shutil.which", return_value=None):
        assert _gcloud_default_project() == ""


def test_initialize_via_proxy_emits_helpful_message_on_earthengine_legacy_403():
    """When the OAuth-no-project failure mode happens, the error
    message must tell users how to fix it — listing the four
    remediation paths — rather than dumping a raw HttpError."""
    from geeViz.eeAuth import client as _cl
    import io, sys as _sys

    # Capture stderr so we can inspect what was printed
    captured = io.StringIO()
    real_stderr = _sys.stderr
    _sys.stderr = captured

    # Stub ee.Initialize to raise the exact error users see
    class _FakeError(Exception):
        pass
    fake_err = _FakeError(
        'HttpError: <HttpError 403 ...> "Caller does not have required '
        'permission to use project earthengine-legacy. Grant the caller '
        'the roles/serviceusage.serviceUsageConsumer role... '
        "reason': 'USER_PROJECT_DENIED'"
    )

    import ee
    try:
        with patch.object(ee, "Initialize", side_effect=fake_err):
            result = _cl.initialize_via_proxy("http://nope/ee-api")
    finally:
        _sys.stderr = real_stderr

    assert result is False
    out = captured.getvalue()
    # Must surface the friendly remediation list, not just the raw error
    assert "OAuth credentials have no project" in out
    assert "eeCreds.addCreds(..., project=" in out
    assert "GOOGLE_CLOUD_PROJECT" in out
    assert "gcloud config set project" in out
    assert "ee.Initialize(project=" in out


def test_initialize_via_proxy_explains_sa_missing_serviceusage_role():
    """When an SA's project_id IS a real project but the SA itself
    lacks ``roles/serviceusage.serviceUsageConsumer`` on it, the
    error must name the project, point at the missing role, and
    offer the ``project=`` override as an alternative fix. This is
    the failure mode users hit when registering an SA whose JSON's
    project_id has restrictive IAM."""
    from geeViz.eeAuth import client as _cl
    import io, sys as _sys
    captured = io.StringIO()
    real_stderr = _sys.stderr
    _sys.stderr = captured

    fake_err = Exception(
        "HttpError 403 when requesting $discovery/rest "
        "Caller does not have required permission to use project "
        "my-real-project. Grant the caller the "
        "roles/serviceusage.serviceUsageConsumer role. "
        "reason: USER_PROJECT_DENIED"
    )

    import ee
    try:
        with patch.object(ee, "Initialize", side_effect=fake_err):
            result = _cl.initialize_via_proxy("http://nope/ee-api")
    finally:
        _sys.stderr = real_stderr

    assert result is False
    out = captured.getvalue()
    # The denied project name must appear so the user knows where to look.
    assert "my-real-project" in out, \
        f"expected the project name in the message; got: {out!r}"
    # Trailing-period stripping must work (regex would otherwise capture
    # 'my-real-project.' with the sentence period).
    assert "my-real-project." not in out, \
        "trailing period from EE's error sentence must be stripped"
    # Must NOT be the OAuth-earthengine-legacy branch.
    assert "earthengine-legacy" not in out
    # Must name the missing role and offer both fixes.
    assert "serviceUsageConsumer" in out
    assert "eeCreds.addCreds(..., project=" in out, \
        "must offer the project= override as an alternative remedy"


def test_proxy_strips_quota_project_on_discovery_path():
    """EE's own ``_cloud_api_utils.build_cloud_resource`` strips
    ``quota_project_id`` from credentials before fetching
    ``$discovery/rest`` — the serviceUsage API rejects discovery
    requests that carry a consumer project. Our proxy must mirror that:
    when the incoming path contains ``$discovery/rest``, do NOT inject
    ``x-goog-user-project`` on the forwarded request.

    Without this, SAs that have full EE perms but lack
    ``serviceusage.serviceUsageConsumer`` 403 on init even though they
    can do all the real work afterward — that's the bug the user hit.
    """
    src_path = os.path.join(_REPO_ROOT, "geeViz", "eeAuth", "server.py")
    src = open(src_path, encoding="utf-8").read()
    # The fix lives in the proxy route handler; look for the guard.
    assert "$discovery/rest" in src, \
        "server.py must reference the $discovery/rest path it special-cases"
    assert "is_discovery" in src, \
        "server.py must compute is_discovery=… and gate the " \
        "x-goog-user-project injection on it"
    # Find the line that sets x-goog-user-project and check the guard.
    qp_lines = [
        ln for ln in src.splitlines()
        if "x-goog-user-project" in ln and "fwd_headers" in ln
    ]
    assert qp_lines, "expected lines setting fwd_headers['x-goog-user-project']"
    for ln in qp_lines:
        # The surrounding context (the line and a couple above) must guard
        # on is_discovery so we don't set the header on the discovery call.
        ln_idx = src.index(ln)
        context = src[max(0, ln_idx - 200):ln_idx + len(ln)]
        assert "is_discovery" in context, (
            f"x-goog-user-project must be guarded by is_discovery; "
            f"found unguarded write near:\n{ln}"
        )


def test_discover_does_not_overwrite_sa_project_with_oauth_hint():
    """The project backfill must NOT clobber an SA's project_id that
    came from its own JSON. SA files have authoritative project info;
    only OAuth entries (which lack project info) should get backfilled."""
    creds = _fresh()
    sa_with_real_project = _sa_dict(client_email="adc@p.iam",
                                     project="actual-sa-project")
    path = _write_tmp(sa_with_real_project)
    try:
        class _FakeState:
            cloud_api_user_project = "wrong-oauth-hint-project"
        import ee.data
        with patch.object(ee.data, "_get_state", return_value=_FakeState()), \
             patch.dict(os.environ,
                        {"GOOGLE_APPLICATION_CREDENTIALS": path},
                        clear=False):
            creds.discover()
        # SA project from the JSON wins — NOT the OAuth hint
        info = creds.info("adc")
        assert info["type"] == "sa"
        assert info["project_id"] == "actual-sa-project", \
            "SA project from JSON must NOT be overwritten by OAuth project hint"
    finally:
        _cleanup_tmp()


def test_discover_finds_env_default_b64():
    """Discovers GEE_SERVICE_ACCOUNT_B64 base64-encoded SA."""
    creds = _fresh()
    with patch.dict(os.environ, {
        "GEE_SERVICE_ACCOUNT_B64": _sa_b64(client_email="env@p.iam.gserviceaccount.com"),
    }, clear=False):
        # Clear any other discovery sources to isolate
        os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
        discovered = creds.discover()
    assert "env-default" in discovered
    assert creds.info("env-default")["client_email"] == "env@p.iam.gserviceaccount.com"


def test_discover_finds_per_tenant_envs():
    """Discovers GEE_<NAME>_SERVICE_ACCOUNT for arbitrary names."""
    creds = _fresh()
    with patch.dict(os.environ, {
        "GEE_TRAINING_SERVICE_ACCOUNT": _sa_b64(client_email="train@p.iam"),
        "GEE_ACME_SERVICE_ACCOUNT": _sa_b64(client_email="acme@p.iam"),
    }, clear=False):
        os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
        os.environ.pop("GEE_SERVICE_ACCOUNT_B64", None)
        discovered = creds.discover()
    assert "training" in discovered
    assert "acme" in discovered


def test_discover_skips_existing_names_by_default():
    """Already-registered credentials are not overwritten."""
    creds = _fresh()
    creds.addCreds(_sa_dict("manual@p.iam"), name="adc")
    path = _write_tmp(_sa_dict("env@p.iam"))
    try:
        with patch.dict(os.environ,
                        {"GOOGLE_APPLICATION_CREDENTIALS": path},
                        clear=False):
            discovered = creds.discover()
        # discover() didn't add 'adc' again
        assert "adc" not in discovered
        # And the manual creds are preserved
        assert creds.info("adc")["client_email"] == "manual@p.iam"
    finally:
        _cleanup_tmp()


def test_discover_overwrite_replaces_existing():
    """overwrite=True replaces existing names."""
    creds = _fresh()
    creds.addCreds(_sa_dict("manual@p.iam"), name="adc")
    path = _write_tmp(_sa_dict("env@p.iam"))
    try:
        with patch.dict(os.environ,
                        {"GOOGLE_APPLICATION_CREDENTIALS": path},
                        clear=False):
            discovered = creds.discover(overwrite=True)
        assert "adc" in discovered
        assert creds.info("adc")["client_email"] == "env@p.iam"
    finally:
        _cleanup_tmp()


def test_discover_with_nothing_to_find_returns_empty_list():
    creds = _fresh()
    # Clear every source we know about
    with patch.dict(os.environ, {}, clear=False):
        for k in ("GOOGLE_APPLICATION_CREDENTIALS", "GEE_SERVICE_ACCOUNT_B64"):
            os.environ.pop(k, None)
        for k in [k for k in os.environ if k.startswith("GEE_")
                  and k.endswith("_SERVICE_ACCOUNT")]:
            os.environ.pop(k, None)
        # Patch ee.oauth so the persistent file lookup returns empty
        # and the gcloud ADC well-known path is also absent.
        import ee.oauth as _ee_oauth
        from google.auth import _cloud_sdk as _gauth_cloud_sdk
        with patch.object(_ee_oauth, "get_credentials_path",
                          return_value="/this/path/does/not/exist"), \
             patch.object(_gauth_cloud_sdk,
                          "get_application_default_credentials_path",
                          return_value="/this/path/also/does/not/exist"):
            discovered = creds.discover()
    assert discovered == []
    assert creds.list() == []


def test_discover_finds_gcloud_adc_default_file():
    """When ``gcloud auth application-default login`` has run, its
    well-known credentials file at e.g.
    ``~/AppData/Roaming/gcloud/application_default_credentials.json``
    must be picked up so ``Map.view()`` can spin up the proxy in
    ADC-only environments. Registered as ``"adc-default"``."""
    creds = _fresh()
    adc_path = _write_tmp(_oauth_dict())
    try:
        from google.auth import _cloud_sdk as _gauth_cloud_sdk
        import ee.oauth as _ee_oauth
        with patch.dict(os.environ, {}, clear=False), \
             patch.object(_gauth_cloud_sdk,
                          "get_application_default_credentials_path",
                          return_value=adc_path), \
             patch.object(_ee_oauth, "get_credentials_path",
                          return_value="/nope-ee"):
            for k in ("GOOGLE_APPLICATION_CREDENTIALS", "GEE_SERVICE_ACCOUNT_B64"):
                os.environ.pop(k, None)
            discovered = creds.discover()
        assert "adc-default" in discovered, \
            f"gcloud ADC well-known file must be discovered; got {discovered!r}"
        info = creds.info("adc-default")
        assert info["type"] == "oauth"
    finally:
        _cleanup_tmp()


def test_discover_finds_multiple_simultaneously():
    """All four sources at once → discovery picks them all up."""
    creds = _fresh()
    sa_path = _write_tmp(_sa_dict("adc@p.iam"))
    oauth_path = _write_tmp(_oauth_dict())
    try:
        import ee.oauth as _ee_oauth
        with patch.dict(os.environ, {
            "GOOGLE_APPLICATION_CREDENTIALS": sa_path,
            "GEE_SERVICE_ACCOUNT_B64": _sa_b64(client_email="env@p.iam"),
            "GEE_PROD_SERVICE_ACCOUNT": _sa_b64(client_email="prod@p.iam"),
        }, clear=False), patch.object(_ee_oauth, "get_credentials_path",
                                      return_value=oauth_path):
            discovered = creds.discover()
        assert set(discovered) >= {"adc", "ee-persistent", "env-default", "prod"}
    finally:
        _cleanup_tmp()


# ─────────────────────── ensure_started — mode matrix ───────────────────────
def test_ensure_started_mode_legacy_does_nothing():
    """mode='legacy' must not touch state — Map.view() falls through."""
    creds = _fresh()
    status = creds.ensure_started(mode="legacy")
    assert status["proxy_url"] == ""
    assert status["mode"] == "legacy"
    assert creds._started is False


def test_ensure_started_mode_invalid_raises():
    creds = _fresh()
    try:
        creds.ensure_started(mode="banana")
    except ValueError as e:
        assert "auto/proxy/legacy" in str(e)
        return
    raise AssertionError("expected ValueError on invalid mode")


def _patch_no_creds_anywhere():
    """Context-manager stack that blocks every discovery source so the
    'no credentials' branches can be exercised. Mirrors what
    ``EECreds.discover()`` checks."""
    import contextlib
    import ee.oauth as _ee_oauth
    from google.auth import _cloud_sdk as _gauth_cloud_sdk
    stack = contextlib.ExitStack()
    stack.enter_context(
        patch.object(_ee_oauth, "get_credentials_path", return_value="/nope")
    )
    stack.enter_context(
        patch.object(_gauth_cloud_sdk,
                     "get_application_default_credentials_path",
                     return_value="/nope-adc")
    )
    return stack


def test_ensure_started_mode_proxy_raises_when_no_creds():
    """mode='proxy' is explicit — fail noisily so users notice."""
    creds = _fresh()
    # No credentials anywhere
    with patch.dict(os.environ, {}, clear=False):
        for k in list(os.environ):
            if "SERVICE_ACCOUNT" in k or k == "GOOGLE_APPLICATION_CREDENTIALS":
                os.environ.pop(k, None)
        with _patch_no_creds_anywhere():
            try:
                creds.ensure_started(mode="proxy")
            except RuntimeError as e:
                assert "no credentials" in str(e).lower() \
                    or "discover" in str(e).lower()
                return
    raise AssertionError("expected RuntimeError on mode='proxy' with no creds")


def test_ensure_started_mode_auto_falls_back_silently_with_no_creds():
    """mode='auto' returns empty proxy_url so caller falls back to legacy."""
    creds = _fresh()
    with patch.dict(os.environ, {}, clear=False):
        for k in list(os.environ):
            if "SERVICE_ACCOUNT" in k or k == "GOOGLE_APPLICATION_CREDENTIALS":
                os.environ.pop(k, None)
        with _patch_no_creds_anywhere():
            status = creds.ensure_started(mode="auto")
    assert status["proxy_url"] == ""
    assert status["mode"] == "auto"


def test_ensure_started_auto_discovers_and_would_start_with_creds():
    """When credentials are discoverable, auto mode starts the proxy.
    Stub the actual port-binding to keep the test hermetic."""
    creds = _fresh()
    # Stub _launch_proxy so we don't actually bind a port. Set _proxy_url
    # so the post-start state looks valid.
    def _fake_launch(self, host, port):
        self._proxy_url = f"http://{host}:{port}/ee-api"
    with patch.object(type(creds), "_launch_proxy", _fake_launch), \
         patch.dict(os.environ, {
            "GEE_SERVICE_ACCOUNT_B64": _sa_b64(),
         }, clear=False):
        # Also stub ee_init since we don't have real ee credentials
        from geeViz.eeAuth import client as _cl
        with patch.object(_cl, "initialize_via_proxy", return_value=True):
            status = creds.ensure_started(mode="auto")
    assert status["proxy_url"].startswith("http://"), \
        f"auto mode should have started proxy, got {status!r}"
    assert "env-default" in status["tenants"]


def test_ensure_started_idempotent():
    """Calling ensure_started twice is safe; second returns same state."""
    creds = _fresh()
    creds.addCreds(_sa_dict(), "x")
    # Stub launch
    creds._started = True
    creds._proxy_url = "http://stub/ee-api"
    status1 = creds.ensure_started(mode="auto")
    status2 = creds.ensure_started(mode="auto")
    assert status1["proxy_url"] == status2["proxy_url"]


# ─────────────────────── Map.view — auth path selection ───────────────────────
def test_map_view_reads_GEEVIZ_EEAUTH_MODE_env():
    """Map.view() must consult GEEVIZ_EEAUTH_MODE to pick auto/proxy/legacy."""
    src_path = os.path.join(_REPO_ROOT, "geeViz", "geeView.py")
    src = open(src_path, encoding="utf-8").read()
    view_start = src.index("def view(")
    view_end = src.index("\n    def ", view_start + 100)
    view_body = src[view_start:view_end]
    assert "GEEVIZ_EEAUTH_MODE" in view_body, \
        "Map.view() must read GEEVIZ_EEAUTH_MODE env var"


def test_map_view_calls_ensure_started_in_auto_mode():
    """Default mode is 'auto'; Map.view() must call ensure_started so
    discovery + proxy auto-start happens."""
    src_path = os.path.join(_REPO_ROOT, "geeViz", "geeView.py")
    src = open(src_path, encoding="utf-8").read()
    view_start = src.index("def view(")
    view_end = src.index("\n    def ", view_start + 100)
    view_body = src[view_start:view_end]
    assert "ensure_started" in view_body, \
        "Map.view() must call eeCreds.ensure_started()"


def test_map_view_legacy_emits_deprecation_warning():
    """When the legacy path runs, a DeprecationWarning must be emitted."""
    src_path = os.path.join(_REPO_ROOT, "geeViz", "geeView.py")
    src = open(src_path, encoding="utf-8").read()
    view_start = src.index("def view(")
    view_end = src.index("\n    def ", view_start + 100)
    view_body = src[view_start:view_end]
    assert "DeprecationWarning" in view_body, \
        "legacy path must emit DeprecationWarning"
    assert "legacy direct-token" in view_body.lower() or \
           "legacy" in view_body.lower()


def test_map_view_mode_proxy_propagates_runtime_error():
    """When GEEVIZ_EEAUTH_MODE=proxy and proxy can't start, Map.view()
    must surface the error rather than silently falling back."""
    src_path = os.path.join(_REPO_ROOT, "geeViz", "geeView.py")
    src = open(src_path, encoding="utf-8").read()
    view_start = src.index("def view(")
    view_end = src.index("\n    def ", view_start + 100)
    view_body = src[view_start:view_end]
    # The except RuntimeError: raise pattern must be present
    assert "except RuntimeError" in view_body
    assert "raise" in view_body[view_body.index("except RuntimeError"):]


# ─────────────────────── single vs multiple creds ───────────────────────
def test_single_cred_picks_first_automatically():
    creds = _fresh()
    creds.addCreds(_sa_dict("only@p.iam"), "only-creds")
    assert creds.current() == "only-creds"


def test_multiple_creds_first_is_default():
    creds = _fresh()
    creds.addCreds(_sa_dict(), "first-added")
    creds.addCreds(_sa_dict(), "second-added")
    creds.addCreds(_sa_dict(), "third-added")
    # Without an explicit .use(), current() returns the first-added
    assert creds.current() == "first-added"


def test_multiple_creds_use_switches():
    from geeViz.eeAuth import CURRENT_TENANT
    creds = _fresh()
    creds.addCreds(_sa_dict(), "a")
    creds.addCreds(_sa_dict(), "b")
    creds.addCreds(_sa_dict(), "c")
    token = CURRENT_TENANT.set("")
    try:
        creds.use("b")
        assert CURRENT_TENANT.get() == "b"
        with creds.use("c"):
            assert CURRENT_TENANT.get() == "c"
        assert CURRENT_TENANT.get() == "b"
    finally:
        CURRENT_TENANT.reset(token)


def test_no_creds_use_raises():
    creds = _fresh()
    try:
        creds.use("anything")
    except KeyError:
        return
    raise AssertionError("use() must raise when no creds match")


# ─────────────────────── refresh token + SA together ───────────────────────
def test_mixed_refresh_and_sa_credentials_coexist():
    """A registry can hold a personal-account refresh token AND a
    service account at the same time. Switching between them works."""
    creds = _fresh()
    creds.addCreds(_oauth_dict(), "ian", project="my-quota")
    creds.addCreds(_sa_dict("acme-sa@p.iam"), "acme")
    assert creds.info("ian")["type"] == "oauth"
    assert creds.info("acme")["type"] == "sa"
    assert set(creds.list()) == {"ian", "acme"}


def test_oauth_default_project_from_quota_project_id():
    """Authorized_user files don't have project_id, but they often have
    quota_project_id. addCreds(...) should pick it up."""
    creds = _fresh()
    oauth_with_quota = {**_oauth_dict(), "quota_project_id": "quota-proj"}
    creds.addCreds(oauth_with_quota, "ian")
    assert creds.info("ian")["project_id"] == "quota-proj"


def test_oauth_with_explicit_project_override():
    """User-supplied project argument wins over what's in the JSON."""
    creds = _fresh()
    creds.addCreds(_oauth_dict(), "ian", project="my-project")
    assert creds.info("ian")["project_id"] == "my-project"


# ─────────────────────── Python SDK init via initialize_via_proxy ───────────────────────
def test_initialize_via_proxy_uses_anonymous_creds():
    """The Python SDK init path must use AnonymousCredentials so the
    SDK doesn't try to attach its own token — the proxy supplies the
    real one. (Source-of-truth check on the library.)"""
    src_path = os.path.join(_REPO_ROOT, "geeViz", "eeAuth", "client.py")
    src = open(src_path, encoding="utf-8").read()
    assert "AnonymousCredentials" in src
    assert "ee.Initialize(" in src
    assert "http_transport=" in src


def test_python_sdk_and_map_viewer_share_same_proxy():
    """Source-of-truth: both code paths point at the same eeCreds
    proxy_url, ensuring 'Python SDK + Map viewer' parity."""
    # Map.view() reads eeCreds.proxy_url
    geeview_src = open(os.path.join(_REPO_ROOT, "geeViz", "geeView.py"),
                       encoding="utf-8").read()
    assert "eeCreds" in geeview_src
    # initialize_via_proxy uses a proxy_url arg that eeCreds.start sets
    client_src = open(os.path.join(_REPO_ROOT, "geeViz", "eeAuth", "client.py"),
                      encoding="utf-8").read()
    assert "initialize_via_proxy" in client_src
    # eeCreds.start calls initialize_via_proxy with its own _proxy_url
    # and the first credential's project_id (so EE builds API paths with
    # the real project instead of the ``ee-proxy-placeholder`` string).
    eecreds_src = open(os.path.join(_REPO_ROOT, "geeViz", "eeAuth", "eeCreds.py"),
                       encoding="utf-8").read()
    assert "initialize_via_proxy(" in eecreds_src
    assert "first.project_id" in eecreds_src, \
        "eeCreds.start must pass the first credential's project_id to " \
        "initialize_via_proxy so EE-built URLs aren't 'projects/ee-proxy-placeholder/...'"


# ─────────────────────── URL construction in Map.view ───────────────────────
def test_proxy_mode_url_registers_upstream_and_keeps_url_clean():
    """When proxy is active, ``Map.view()`` must:
    - register the upstream proxy URL with the local HTTP server via
      ``_set_ee_api_upstream`` so it can reverse-proxy /ee-api/*
    - default to an EMPTY query string — the JS viewer's same-origin
      ``window.location.origin + "/ee-api"`` default does the work
    - include ``?tenant=`` only when there are multiple registered
      credentials AND the active one isn't the default (first registered)
    - never include accessToken / accessTokenCreationTime / projectID —
      the proxy injects auth + x-goog-user-project server-side
    """
    src_path = os.path.join(_REPO_ROOT, "geeViz", "geeView.py")
    src = open(src_path, encoding="utf-8").read()
    view_start = src.index("def view(")
    view_end = src.index("\n    def ", view_start + 100)
    view_body = src[view_start:view_end]
    # Isolate the proxy branch so legacy-branch occurrences don't pollute
    proxy_branch_start = view_body.index("if ee_proxy_url:")
    proxy_branch_end = view_body.index("else:", proxy_branch_start)
    proxy_branch = view_body[proxy_branch_start:proxy_branch_end]
    # Upstream proxy URL must be handed to the local server for reverse-proxy.
    assert "_set_ee_api_upstream(ee_proxy_url)" in proxy_branch, \
        "proxy branch must register the upstream with the local server"
    # Tenant is baked into the per-session run_js, not the URL. But
    # the URL now carries a per-call ``?v=<timestamp>`` cache-buster
    # so a second ``Map.view()`` in the same notebook triggers a
    # real browser reload instead of Chrome silently focusing the
    # existing tab (which showed layers from the previous cell).
    # 2026.7.1 release-notes entry: "Map.view() cache-buster".
    assert 'query = f"?v={_v}"' in proxy_branch, \
        "proxy branch must build a ?v=<timestamp> cache-buster so " \
        "each Map.view() triggers a fresh browser navigation"
    assert "?tenant=" not in proxy_branch, \
        "proxy branch must NOT add ?tenant= to URL — that flow drifts " \
        "open tabs when eeCreds.use() runs after Map.view()"
    # No proxy address / no token params / no projectID in the URL.
    assert "geeAuthProxyURL=" not in proxy_branch, \
        "proxy URL must not carry geeAuthProxyURL — JS default is same-origin"
    assert "accessToken=" not in proxy_branch, \
        "proxy URL must not carry accessToken — proxy handles auth"
    assert "accessTokenCreationTime=" not in proxy_branch, \
        "proxy URL must not carry accessTokenCreationTime"
    assert "projectID=" not in proxy_branch, \
        "proxy URL must not carry projectID — proxy injects x-goog-user-project"


def test_legacy_mode_url_still_uses_accessToken_template():
    """When proxy is unavailable, the URL must use the legacy format
    with the minted token baked in."""
    src_path = os.path.join(_REPO_ROOT, "geeViz", "geeView.py")
    src = open(src_path, encoding="utf-8").read()
    view_start = src.index("def view(")
    view_end = src.index("\n    def ", view_start + 100)
    view_body = src[view_start:view_end]
    # Legacy URL template — the {} placeholders for project + token + time
    assert "?projectID={}&accessToken={}&accessTokenCreationTime={}" in view_body


# ─────────────────────── robustInitializer wiring ───────────────────────
def test_geeView_robustInitializer_is_thin_pointer_to_eeAuth():
    """``geeView.robustInitializer`` must be a thin delegate to
    ``geeViz.eeAuth.robust_init``; the real flow lives in eeAuth so
    it's usable from any entry point, not just module-import."""
    src_path = os.path.join(_REPO_ROOT, "geeViz", "geeView.py")
    src = open(src_path, encoding="utf-8").read()
    init_start = src.index("def robustInitializer(")
    init_end = src.index("\n######", init_start)
    body = src[init_start:init_end]
    assert "from geeViz.eeAuth import robust_init" in body, \
        "robustInitializer must import robust_init from eeAuth"
    assert "_robust_init(verbose=verbose)" in body, \
        "robustInitializer must delegate to eeAuth's robust_init"
    # No legacy retry logic should live here anymore
    assert "simpleSetProject" not in body, \
        "simpleSetProject must not be referenced from the wrapper — " \
        "the canonical flow lives in eeAuth.eeCreds.robust_init"


def _robust_init_body() -> str:
    """Return the source of EECreds.robust_init for assertion."""
    src_path = os.path.join(_REPO_ROOT, "geeViz", "eeAuth", "eeCreds.py")
    src = open(src_path, encoding="utf-8").read()
    start = src.index("def robust_init(self")
    # Function ends at the next top-level method definition in EECreds.
    end = src.index("\n    def ", start + 1)
    return src[start:end]


def test_robust_init_tries_eeAuth_proxy_first():
    """eeAuth.robust_init must attempt the proxy via ``ensure_started``
    before any other path."""
    body = _robust_init_body()
    assert "ensure_started" in body, \
        "robust_init must call ensure_started for proxy attempt"
    assert "eeauth-proxy" in body, \
        "robust_init must return source='eeauth-proxy' on proxy success"


def test_robust_init_respects_legacy_env():
    """``GEEVIZ_EEAUTH_MODE=legacy`` must skip the proxy attempt."""
    body = _robust_init_body()
    assert "GEEVIZ_EEAUTH_MODE" in body
    assert '"legacy"' in body or "'legacy'" in body


def test_robust_init_calls_ee_initialize_with_no_project():
    """The defining behavior of the simple flow: call
    ``ee.Initialize()`` with NO project arg and let EE's own resolution
    chain (credentials.quota_project_id → ADC → env vars) pick the
    project. No project prompts, no manual ADC fallback handling."""
    body = _robust_init_body()
    # Must call ee.Initialize() with no args (or just no project kw).
    # The simplest check: the literal ``ee.Initialize()`` appears in
    # the flow, separate from any ee.Initialize(project=...) form.
    assert "ee.Initialize()" in body, \
        "robust_init must call ee.Initialize() with no project arg " \
        "and let EE auto-resolve via credentials.quota_project_id / ADC"
    assert '"ee-auto-init"' in body, \
        "robust_init must report source='ee-auto-init' on this path"


def test_robust_init_falls_back_to_authenticate_force_true_localhost():
    """When ee.Initialize() fails, the interactive fallback must run
    ``ee.Authenticate(force=True, auth_mode='localhost')`` — that's the
    combination that reliably works for desktop dev."""
    body = _robust_init_body()
    assert 'ee.Authenticate(force=True, auth_mode="localhost")' in body, \
        "robust_init must use ee.Authenticate(force=True, " \
        "auth_mode='localhost') as the interactive fallback"


def test_robust_init_uses_colab_auth_mode_in_colab():
    """In Colab, ``auth_mode='localhost'`` opens a loopback server on the
    Colab VM that the user's browser can't reach — the flow hangs. The
    interactive fallback must detect Colab (``google.colab`` in
    ``sys.modules``) and switch to ``auth_mode='colab'`` (silent
    google.colab.auth flow)."""
    body = _robust_init_body()
    assert '"google.colab" in sys.modules' in body, \
        "robust_init must detect Colab via sys.modules to pick the " \
        "right auth_mode"
    assert 'ee.Authenticate(force=True, auth_mode="colab")' in body, \
        "robust_init must use auth_mode='colab' when running in Colab"


def test_robust_init_retries_project_prompt_on_failure():
    """When the automatic resolution chain fails and the interactive
    fallback has to prompt for a project id, a typo or an
    inaccessible-project rejection must not be instantly fatal — a
    common Colab failure is entering a project the wrong signed-in
    account can't reach. The loop gives the user multiple attempts and
    only raises when they're exhausted (or when there is no stdin to
    read from)."""
    body = _robust_init_body()
    assert "_prompt_for_project" in body, \
        "robust_init must invoke _prompt_for_project in the " \
        "interactive fallback"
    assert "MAX_PROJECT_ATTEMPTS" in body, \
        "robust_init must define a bounded retry count for the " \
        "project prompt loop"
    # Loop structure: for attempt in range(MAX_PROJECT_ATTEMPTS): ...
    assert "for attempt in range(MAX_PROJECT_ATTEMPTS)" in body, \
        "robust_init must retry the project prompt in a bounded loop"
    # Successful project must be cached (so the next run skips the
    # prompt via step 3a); failed prompts must NOT be cached.
    assert "_write_cached_project" in body, \
        "robust_init must persist a working project id via " \
        "_write_cached_project after ee.Initialize succeeds"


def test_robust_init_invalidates_stale_cached_project():
    """When step 3a's cached project no longer works (deleted, access
    revoked, wrong Google account), the cache must be wiped so the
    interactive fallback offers a fresh prompt instead of a future run
    silently retrying the same broken value on every import."""
    body = _robust_init_body()
    assert "_clear_cached_project" in body, \
        "robust_init must clear the cached project when it fails to " \
        "prevent poisoning subsequent runs"


def test_robust_init_defaults_to_auto_mode_in_colab():
    """The detached proxy runs in a separate process, so the project id
    resolved by the step-4 interactive prompt only reaches THIS
    process's tenant registry. Every ``/ee-api`` request would then be
    signed without ``x-goog-user-project`` and EE would return 403.
    In Colab, default to ``auto`` mode so the proxy shares this
    process's registry and ``sync_oauth_project`` after the prompt
    actually takes effect. Users can still opt into detached explicitly
    via ``GEEVIZ_EEAUTH_MODE=detached``."""
    body = _robust_init_body()
    assert '"google.colab" in sys.modules else "detached"' in body, \
        "robust_init must default GEEVIZ_EEAUTH_MODE to 'auto' in " \
        "Colab (and 'detached' elsewhere) so the interactive project " \
        "prompt reaches the same tenant registry as Map.view()'s proxy"


def test_robust_init_verifies_with_getinfo_call():
    """robust_init must verify each init attempt with a real EE call
    before declaring success — a silently misconfigured proxy or stale
    project would otherwise break the next user operation."""
    body = _robust_init_body()
    assert "_verify_and_return_project" in body, \
        "robust_init must factor verification into a helper"
    # Helper is called in the fast-path, the proxy-success branch, the
    # ee-auto-init branch, and the interactive-auth branch.
    assert body.count("_verify_and_return_project()") >= 4, \
        "robust_init must verify EVERY init attempt with a getInfo() call"


def test_robust_init_syncs_oauth_project_after_init():
    """After ``ee.Initialize()`` succeeds (either auto or after auth),
    OAuth entries must be synced to the working project — otherwise a
    subsequent ``Map.view()`` would route through the proxy with the
    stale guess."""
    body = _robust_init_body()
    # Both the ee-auto-init branch and the interactive-auth branch must
    # call sync_oauth_project on success.
    assert body.count("self.sync_oauth_project") >= 2, \
        "robust_init must call sync_oauth_project after both the " \
        "ee-auto-init and interactive-auth success branches"


def test_robust_init_propagates_proxy_mode_errors():
    """mode='proxy' is explicit — if the user demanded the proxy and it
    can't start, surface the error rather than falling through."""
    body = _robust_init_body()
    assert "except RuntimeError" in body, \
        "robust_init must catch RuntimeError specifically"
    rt_idx = body.index("except RuntimeError")
    next_except = body.find("except", rt_idx + len("except RuntimeError"))
    rt_block = body[rt_idx:next_except if next_except > 0 else rt_idx + 300]
    assert "raise" in rt_block, \
        "RuntimeError from mode='proxy' must propagate, not swallow"


def test_robust_init_final_error_lists_concrete_remedies():
    """If init fails even after ``ee.Authenticate(force=True)``, the
    error must tell the user exactly which commands to run instead of
    a generic 'auth failed' message."""
    body = _robust_init_body()
    assert "earthengine set_project" in body, \
        "final error must suggest `earthengine set_project YOUR_PROJECT`"
    assert "set-quota-project" in body, \
        "final error must suggest `gcloud auth application-default " \
        "set-quota-project YOUR_PROJECT`"
    assert "ee.Initialize(project=" in body, \
        "final error must suggest `ee.Initialize(project='YOUR_PROJECT')`"


# ─────────────── robust_init behavior tests ───────────────
def test_diagnose_ee_credentials_reads_refresh_token_and_project():
    """``_diagnose_ee_credentials`` must surface what's in the EE
    credentials JSON without interpreting it — refresh_token presence
    and the ``project`` field both go through verbatim."""
    from geeViz.eeAuth.eeCreds import _diagnose_ee_credentials
    path = _write_tmp({
        "refresh_token": "abc",
        "project": "my-stored-proj",
        "client_id": "1.apps.googleusercontent.com",
        "client_secret": "shh",
    })
    try:
        import ee.oauth as _ee_oauth
        with patch.object(_ee_oauth, "get_credentials_path", return_value=path), \
             patch.object(_ee_oauth, "get_appdefault_project", return_value=""):
            d = _diagnose_ee_credentials()
        assert d["has_ee_refresh_token"] is True
        assert d["ee_project"] == "my-stored-proj"
    finally:
        _cleanup_tmp()


def test_diagnose_reports_missing_refresh_token():
    """When the EE credentials file has no refresh_token field (user
    deleted it), the diagnosis must say so — that's the signal robust_init
    uses to NOT silently fall through to ADC."""
    from geeViz.eeAuth.eeCreds import _diagnose_ee_credentials
    # File present but no refresh_token
    path = _write_tmp({"scopes": ["a", "b"]})
    try:
        import ee.oauth as _ee_oauth
        with patch.object(_ee_oauth, "get_credentials_path", return_value=path), \
             patch.object(_ee_oauth, "get_appdefault_project", return_value=""):
            d = _diagnose_ee_credentials()
        assert d["has_ee_refresh_token"] is False, \
            "missing refresh_token must report has_ee_refresh_token=False"
    finally:
        _cleanup_tmp()


def test_save_ee_project_to_credentials_file_roundtrip():
    """``_save_ee_project_to_credentials_file`` must write to the EE
    credentials JSON's ``project`` field — same place
    ``earthengine set_project`` writes — so next session reads it back."""
    from geeViz.eeAuth.eeCreds import _save_ee_project_to_credentials_file
    path = _write_tmp({"refresh_token": "abc", "scopes": ["s"]})
    try:
        import ee.oauth as _ee_oauth
        with patch.object(_ee_oauth, "get_credentials_path", return_value=path):
            _save_ee_project_to_credentials_file("persisted-proj")
        with open(path, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert saved.get("project") == "persisted-proj", \
            f"project field not persisted; got {saved!r}"
        # Other fields preserved.
        assert saved.get("refresh_token") == "abc"
        assert saved.get("scopes") == ["s"]
    finally:
        _cleanup_tmp()


def test_robust_init_returns_already_initialized_when_ee_works():
    """Fast path: when ``ee.Number(1).getInfo()`` already succeeds,
    robust_init must NOT touch anything else."""
    from geeViz.eeAuth.eeCreds import EECreds
    creds = EECreds()
    import ee
    # Stub the fast-path check to succeed; if anything else is called
    # the test would fail because we didn't stub the proxy/diagnosis.
    class _FakeState:
        cloud_api_user_project = "already-here"
    with patch.object(ee, "Number") as mock_num, \
         patch.object(ee.data, "_get_state", return_value=_FakeState()):
        mock_num.return_value.getInfo.return_value = 1
        result = creds.robust_init(verbose=False)
    assert result["ok"] is True
    assert result["source"] == "already-initialized"
    assert result["project"] == "already-here"


def test_robust_init_uses_ee_initialize_auto_resolution():
    """When the fast-path and the proxy both fail, robust_init must call
    plain ``ee.Initialize()`` (no project arg) and let EE pick the
    project from credentials' quota_project_id / ADC. If that succeeds,
    return source='ee-auto-init' with the project EE picked."""
    from geeViz.eeAuth.eeCreds import EECreds
    creds = EECreds()
    import ee

    call_state = {"initialized": False, "init_kwargs": None}

    def _fake_getinfo():
        if not call_state["initialized"]:
            raise Exception("not init")
        return 1

    def _fake_init(*_a, **kw):
        call_state["initialized"] = True
        call_state["init_kwargs"] = kw

    class _State:
        cloud_api_user_project = "resolved-by-ee"

    with patch.object(ee, "Number") as mock_num, \
         patch.object(ee, "Initialize", side_effect=_fake_init), \
         patch.object(ee.data, "_get_state", return_value=_State()), \
         patch.dict(os.environ, {"GEEVIZ_EEAUTH_MODE": "legacy"}, clear=False):
        mock_num.return_value.getInfo.side_effect = _fake_getinfo
        result = creds.robust_init(verbose=False, interactive=False)

    assert result["ok"] is True
    assert result["source"] == "ee-auto-init"
    assert result["project"] == "resolved-by-ee"
    # The defining behavior: project was NOT passed in — EE resolved it.
    assert "project" not in (call_state["init_kwargs"] or {}), \
        f"ee.Initialize must be called with no project arg; got " \
        f"kwargs={call_state['init_kwargs']!r}"


def test_robust_init_raises_in_non_interactive_when_init_fails():
    """Non-interactive callers (daemons, CI) must get a clear
    RuntimeError when ee.Initialize() fails, NOT a hanging
    ee.Authenticate() prompt."""
    from geeViz.eeAuth.eeCreds import EECreds
    creds = EECreds()
    import ee

    def _fake_getinfo():
        raise Exception("not init")

    def _fake_init(*_a, **_kw):
        raise Exception("no credentials")

    with patch.object(ee, "Number") as mock_num, \
         patch.object(ee, "Initialize", side_effect=_fake_init), \
         patch.object(ee, "Authenticate") as mock_auth, \
         patch.dict(os.environ, {"GEEVIZ_EEAUTH_MODE": "legacy"}, clear=False):
        mock_num.return_value.getInfo.side_effect = _fake_getinfo
        try:
            creds.robust_init(verbose=False, interactive=False)
            raised = False
        except RuntimeError as e:
            raised = True
            msg = str(e)
        assert raised, "init failure + non-interactive must raise RuntimeError"
        assert "non-interactively" in msg, \
            f"error must say it's non-interactive; got: {msg}"
        # Must NOT have called ee.Authenticate in non-interactive mode.
        mock_auth.assert_not_called()


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
    _cleanup_tmp()
    print()
    if failed:
        print(f"{failed}/{len(tests)} tests FAILED")
        raise SystemExit(1)
    print(f"{len(tests)}/{len(tests)} tests passed")
