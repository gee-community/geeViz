"""Plain library EE work must be attributable, not just agent work.

``CURRENT_USER_EMAIL`` is set by the MCP wrapper from the agent's
before_tool_callback, so it is populated for agent-initiated calls and
empty for everything else. A script or notebook doing ``Map.addLayer``
therefore minted a workload tag carrying no identity at all: the tag
store wrote ``user_sub=UNATTRIBUTED``, and the usage poller then declined
to bill it — correctly, since it will not charge a user it cannot name.

The visible symptom is EE work that appears in ``ee_usage_hourly`` as
``unattributed`` and never reaches ``cdu_ledger``. Measured on a dev
database: 70 rows and 6.34 EECU-hours unattributed in 48 hours against 2
rows attributed.

``$GEEVIZ_USER_EMAIL`` closes that gap for local use. The ContextVar
still wins, so nothing about the agent path changes — this only fills in
where there was no identity to begin with.
"""
import os

import pytest

from geeViz.eeAuth import server as eeserver
from geeViz.eeAuth.client import CURRENT_USER_EMAIL


def _parts_from_builder(monkeypatch, env_email, ctx_email=""):
    """Mint through the default builder and recover the parts it used."""
    captured = {}

    class _Store:
        def put(self, tag, parts):
            captured.update(parts)

    class _Singleton:
        def current(self):
            return "ee-persistent"

        def getTagStore(self):
            return _Store()

        def _resolve_tag_secret(self):
            return "test-secret"

    # Reach the MODULE through sys.modules: the package exports the
    # singleton INSTANCE as ``geeViz.eeAuth.eeCreds``, which shadows the
    # submodule of the same name, so the dotted-string form patches the
    # wrong object and the builder quietly keeps the real singleton.
    import sys
    import geeViz.eeAuth.eeCreds  # noqa: F401  (ensure it is imported)
    monkeypatch.setattr(sys.modules["geeViz.eeAuth.eeCreds"], "eeCreds",
                        _Singleton())
    if env_email is None:
        monkeypatch.delenv("GEEVIZ_USER_EMAIL", raising=False)
    else:
        monkeypatch.setenv("GEEVIZ_USER_EMAIL", env_email)
    class _Req:
        # The builder honours a client-set tag first; an empty mapping is
        # "the caller set none", which is the path under test.
        query_params: dict = {}

    token = CURRENT_USER_EMAIL.set(ctx_email)
    try:
        eeserver._default_workload_tag_builder(_Req(), "askterra")
    finally:
        CURRENT_USER_EMAIL.reset(token)
    return captured


def test_a_local_run_can_name_itself(monkeypatch):
    parts = _parts_from_builder(monkeypatch, "ian.housman@gmail.com")
    assert parts.get("user_email") == "ian.housman@gmail.com", (
        "GEEVIZ_USER_EMAIL did not reach the tag parts, so local EE work "
        "still mints an anonymous tag and never reaches cdu_ledger")


def test_the_context_var_still_wins(monkeypatch):
    """Agent-initiated work must not be relabelled by a stray env var on
    the box — the ContextVar is the real caller."""
    parts = _parts_from_builder(monkeypatch, "env@example.com",
                                ctx_email="agent@example.com")
    assert parts.get("user_email") == "agent@example.com"


def test_no_identity_anywhere_stays_anonymous(monkeypatch):
    """Unset means unset. Inventing an identity would be worse than
    recording none: the poller's whole contract is that it never charges
    a user it cannot name."""
    parts = _parts_from_builder(monkeypatch, None)
    assert "user_email" not in parts


def test_a_blank_env_var_is_not_an_identity(monkeypatch):
    parts = _parts_from_builder(monkeypatch, "   ")
    assert "user_email" not in parts
