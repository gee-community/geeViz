"""Feature Service GeoJSON reaches run_code with string feature ids.

ArcGIS ``f=geojson`` gives each feature its integer OBJECTID as ``id``;
``ee.Feature`` copies that into ``system:index`` unchanged and Earth
Engine rejects it server-side ("Value of property 'system:index' must be
a string"). Agents loading a perimeter with
``georest.restesri.services.queryFeatureService`` and wrapping it as
``ee.FeatureCollection(gj)`` (as the instructions tell them to) hit this
on the first server-side call.
"""
import inspect
import io
import tokenize

import pytest

import geeViz.mcp.server as srv

georest = pytest.importorskip("georest")
import georest.restesri.services as services  # noqa: E402


def test_ids_become_strings_and_other_ids_are_left_alone():
    gj = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": 20, "properties": {}, "geometry": None},
        {"type": "Feature", "id": 3.0, "properties": None, "geometry": None},
        {"type": "Feature", "id": "a", "properties": {}, "geometry": None},
        {"type": "Feature", "properties": {}, "geometry": None},
        {"type": "Feature", "id": None, "properties": {}, "geometry": None},
    ]}
    out = srv._stringify_feature_ids(gj)
    assert [f.get("id") for f in out["features"]] == ["20", "3.0", "a", None, None]
    assert srv._stringify_feature_ids({"type": "FeatureCollection"}) == {"type": "FeatureCollection"}
    assert srv._stringify_feature_ids(None) is None


def test_query_feature_service_returns_string_ids(monkeypatch):
    def fake_fetch_json(url, params=None, *a, **k):
        if (params or {}).get("returnCountOnly") in (True, "true"):
            return {"count": 1}
        return {"type": "FeatureCollection", "features": [
            {"type": "Feature", "id": 20, "properties": {"OBJECTID": 20},
             "geometry": {"type": "Point", "coordinates": [0, 0]}}]}

    monkeypatch.setattr(services, "queryFeatureService", services.queryFeatureService)
    monkeypatch.setattr(services, "fetch_json", fake_fetch_json, raising=False)
    original_params = inspect.signature(services.queryFeatureService).parameters

    srv._install_string_feature_ids(services)
    srv._install_string_feature_ids(services)  # once per session: must not stack

    assert getattr(services.queryFeatureService, "_geeviz_string_ids", False)
    assert not getattr(services.queryFeatureService.__wrapped__, "_geeviz_string_ids", False)
    # esriLib inspects the signature to decide what it can pass
    assert inspect.signature(services.queryFeatureService).parameters.keys() == original_params.keys()

    gj = services.queryFeatureService("https://example.com/arcgis/rest/services/x/FeatureServer/0")
    assert gj["features"][0]["id"] == "20"


def _code_only(src):
    toks = [t for t in tokenize.generate_tokens(io.StringIO(src).readline)
            if t.type not in (tokenize.COMMENT, tokenize.STRING)]
    return tokenize.untokenize(toks)


def test_comment_stripper_drops_comments():
    assert "_install_string_feature_ids" not in _code_only("x = 1  # _install_string_feature_ids(s)\n")


def test_run_code_namespace_setup_installs_it():
    src = _code_only(inspect.getsource(srv._ensure_initialized_locked))
    assert "_install_string_feature_ids(" in src
