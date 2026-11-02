"""An impersonation config with its own source credentials is used as written.

The daily review's local agent runs with an ADC file of type
impersonated_service_account (a key for one account, impersonating the
test runtime account). eeCreds took the source identity from ADC, which
was that same file, so the target was asked to impersonate itself and IAM
refused (403 iam.serviceAccounts.getAccessToken); Earth Engine calls then
hung until the MCP request timed out.
"""
import google.auth

from geeViz.eeAuth.eeCreds import EECreds

TARGET = "runner@proj.iam.gserviceaccount.com"
CONFIG = {
    "type": "impersonated_service_account",
    "service_account_impersonation_url":
        f"https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/{TARGET}:generateAccessToken",
    "source_credentials": {"type": "service_account", "client_email": "source@proj.iam.gserviceaccount.com"},
    "delegates": [],
    "quota_project_id": "proj",
}


def test_a_self_contained_config_does_not_take_its_source_from_adc(monkeypatch):
    seen = {}
    monkeypatch.setattr(google.auth, "load_credentials_from_dict",
                        lambda info, scopes=None: (seen.setdefault("info", info), "proj"))
    monkeypatch.setattr(google.auth, "default",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("source taken from ADC")))
    c = EECreds()
    c.addCreds(CONFIG, "adc-default")
    c._build_credentials(c._entries["adc-default"])
    assert seen["info"]["source_credentials"]["client_email"].startswith("source@")


def test_a_bare_target_still_impersonates_from_adc(monkeypatch):
    calls = []
    monkeypatch.setattr(google.auth, "default", lambda *a, **k: (calls.append(1) or object(), "proj"))
    c = EECreds()
    c.addImpersonation(TARGET, "imp")
    try:
        c._build_credentials(c._entries["imp"])
    except Exception:
        pass   # building the real impersonated credential object may reject the stub source
    assert calls, "a target with no source credentials must still take its source from ADC"
