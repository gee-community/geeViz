"""A detached Earth Engine proxy left running from an older geeViz lacks
routes the client now needs (the Delta page at /geoview). Its version can
match (the version does not change between development builds), so /health
lists the features it serves, and the client replaces a proxy missing any.

Offline: a stub credential source, no Earth Engine, no listening socket.
"""
import importlib

eeCreds = importlib.import_module("geeViz.eeAuth.eeCreds")  # the package exports an instance by this name


def _health():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from geeViz.eeAuth.server import build_proxy_router

    class StubCreds:
        def list(self):
            return ["t"]

        def project_for(self, tenant):
            return "p"

        def get_token(self, *a, **k):
            return "not-a-real-token"

    app = FastAPI()
    app.include_router(build_proxy_router(creds=StubCreds()), prefix="/ee-api")
    return TestClient(app).get("/ee-api/health").json()


def test_health_lists_the_features_the_proxy_serves():
    assert "geoview" in eeCreds.PROXY_FEATURES
    assert set(eeCreds.PROXY_FEATURES) <= set(_health()["features"])


def test_a_proxy_missing_a_feature_is_stale():
    assert eeCreds._missing_features({"ok": True}) == list(eeCreds.PROXY_FEATURES)
    assert eeCreds._missing_features({"features": []}) == list(eeCreds.PROXY_FEATURES)
    assert eeCreds._missing_features(_health()) == []


def test_ensure_detached_replaces_a_proxy_missing_a_feature(monkeypatch):
    c = eeCreds.EECreds()
    killed, spawned = [], []
    c._entries = {"t": object()}
    monkeypatch.setattr(c, "_tenant_fingerprint", lambda: "fp")
    monkeypatch.setattr(c, "_read_detached_state", lambda: {"pid": 1, "url": "http://127.0.0.1:8889/ee-api", "version": ""})
    monkeypatch.setattr(c, "_pid_alive", lambda pid: True)
    old = {"ok": True, "version": "", "tenant_fingerprint": "fp"}  # an older proxy: no "features"
    monkeypatch.setattr(c, "_probe_detached_health", lambda url, *a, **k: old)
    monkeypatch.setattr(c, "_kill_detached", killed.append)
    monkeypatch.setattr(c, "_clear_detached_state", lambda: None)
    monkeypatch.setattr(c, "_spawn_detached", lambda port: spawned.append(port) or {"url": "http://127.0.0.1:8889/ee-api", "pid": 2})
    monkeypatch.setattr(c, "_init_ee_against_detached", lambda *a, **k: None)
    monkeypatch.setattr(c, "list", lambda: ["t"])
    monkeypatch.setattr(c, "current", lambda: "t")
    c._ensure_detached(None)
    assert len(killed) == 1 and spawned == [8889]
    # a current proxy is attached to, not replaced
    killed.clear(), spawned.clear()
    old["features"] = list(eeCreds.PROXY_FEATURES)
    assert c._ensure_detached(None)["attached"] is True
    assert killed == [] and spawned == []
