"""The layers of a shown map ride back to the agent for its export panel.

The layers live only in this process (``Map.idDictList`` in the session's
namespace); the agent's export panel may be served by another instance.
So the tool call that SHOWS a map (map_control's view or export, past
layer validation) attaches a ``_map_layers`` snapshot to its result, the
same way ``_llm_usage`` travels, and the agent drains it.

What would go wrong quietly: layers from a map that failed validation and
never rendered listed as exportable (the panel showed one the person had
never seen), the shared default ``Map`` reported into someone's session, a
snapshot on every call, a tile layer's junk ``item`` passed off as an
expression, or the snapshot attached somewhere the agent does not look.
"""
import asyncio
import json
from types import SimpleNamespace

import pytest


@pytest.fixture(scope="module")
def srv():
    import geeViz.mcp.server as _s
    return _s


@pytest.fixture
def session(srv, monkeypatch):
    """A session with a map holding one exportable and one tile layer."""
    sid = "export-test-session"
    Map = SimpleNamespace(idDictList=[
        {"name": "NDVI", "function": "addSerializedLayer", "item": '{"x": 1}', "viz": '{"min": 0}'},
        {"name": "Basemap", "function": "addTileLayer", "item": "https://tiles/{z}", "viz": "{}"},
    ])
    sess = SimpleNamespace(namespace={"Map": Map}, session_id=sid)
    monkeypatch.setitem(srv._sessions, sid, sess)
    yield sid, Map, sess


def test_nothing_is_reported_until_a_map_is_shown(srv, session):
    sid, _, _ = session
    assert srv._map_layer_snapshot(sid) is None


def test_a_shown_map_lists_every_layer_with_its_map_name(srv, session):
    sid, Map, sess = session
    srv._note_shown_map(sess, Map, "lcms utah")
    snap = srv._map_layer_snapshot(sid)
    assert [e["name"] for e in snap] == ["NDVI", "Basemap"]
    assert {e["map"] for e in snap} == {"lcms utah"}
    assert snap[0]["item"] == '{"x": 1}'
    assert snap[1]["item"] == "", "a tile URL was reported as an Earth Engine expression"
    assert srv._map_layer_snapshot(sid) is None, "a shown map was reported twice"


def test_map_names_come_from_the_file(srv):
    assert srv._map_display_name("/out/sess/lcms_salt_lake.html") == "lcms salt lake"
    assert srv._map_display_name("") == "Map"


def _fake_testlayers(status):
    return lambda: {"pass": status == "ok",
                    "layers": [{"name": "NDVI", "status": status, "error": "bad band" if status == "error" else None}]}


def test_a_map_that_failed_validation_is_not_reported(srv, session, tmp_path):
    sid, Map, sess = session
    Map.testLayers = _fake_testlayers("error")
    Map.mapCommandList = []
    sess.output_dir = str(tmp_path)
    out = json.loads(srv._map_control_inner(Map, "export", sess, False, "m.html", None))
    assert out["pass"] is False
    assert srv._map_layer_snapshot(sid) is None, "layers of a map that never rendered were reported"


def test_an_exported_map_is_reported_under_its_file_name(srv, session, tmp_path):
    sid, Map, sess = session
    Map.testLayers = _fake_testlayers("ok")
    Map.mapCommandList = []
    Map.export_html = lambda path: path
    sess.output_dir = str(tmp_path)
    srv._map_control_inner(Map, "export", sess, False, "fire_scars.html", None)
    snap = srv._map_layer_snapshot(sid)
    assert snap and {e["map"] for e in snap} == {"fire scars"}
    assert {e["map_file"] for e in snap} == {"fire_scars.html"}, "the panel cannot open this map"


def test_the_map_file_comes_from_a_path_or_a_file_url(srv):
    assert srv._map_file_of("/out/sess/lcms utah.html") == "lcms utah.html"
    assert srv._map_file_of(r"C:\out\sess\m.html") == "m.html"
    assert srv._map_file_of("file:///C:/out/sess/geeView%20map.html") == "geeView map.html"
    assert srv._map_file_of("http://localhost:1234/geeView/") == "", "a served map has no file to open"
    assert srv._map_file_of("/out/sess/chart.png") == ""


def test_the_shared_default_map_is_never_reported(srv, monkeypatch):
    Map = SimpleNamespace(idDictList=[{"name": "x", "function": "addSerializedLayer", "item": "{}", "viz": "{}"}])
    sess = SimpleNamespace(namespace={"Map": Map}, session_id=srv._DEFAULT_SESSION_ID)
    monkeypatch.setitem(srv._sessions, srv._DEFAULT_SESSION_ID, sess)
    srv._note_shown_map(sess, Map, "Map")
    assert srv._map_layer_snapshot(srv._DEFAULT_SESSION_ID) is None
    assert srv._map_layer_snapshot(None) is None
    assert srv._map_layer_snapshot("") is None


def test_an_unknown_session_is_not_created(srv):
    before = set(srv._sessions)
    assert srv._map_layer_snapshot("never-seen-session") is None
    assert set(srv._sessions) == before


def test_a_tool_call_attaches_the_layers_where_the_agent_looks(srv, session, monkeypatch):
    """Through the real wrapper, on FastMCP's real return shape (a tuple
    of content and a structured dict holding a JSON ``result`` string)."""
    sid, Map, sess = session

    async def fake_inner(name, arguments, context=None, convert_result=False):
        arguments.pop("_agent_session_id", None)  # what the inner wrapper does
        srv._note_shown_map(sess, Map, "Map")
        return ([], {"result": json.dumps({"stdout": "ok"})})

    monkeypatch.setattr(srv, "_pre_usage_call_tool", fake_inner)
    out = asyncio.run(srv._tool_manager_call_tool_with_usage(
        "map_control", {"action": "view", "_agent_session_id": sid}, convert_result=True))
    inner = json.loads(out[1]["result"])
    assert [e["name"] for e in inner["_map_layers"]] == ["NDVI", "Basemap"]


def test_a_call_that_shows_no_map_attaches_nothing(srv, session, monkeypatch):
    sid, _, _ = session

    async def fake_inner(name, arguments, context=None, convert_result=False):
        return SimpleNamespace(structuredContent={"success": True}, content=[])

    monkeypatch.setattr(srv, "_pre_usage_call_tool", fake_inner)
    out = asyncio.run(srv._tool_manager_call_tool_with_usage("run_code", {"session_id": sid}))
    assert "_map_layers" not in out.structuredContent


def test_the_field_name_matches_what_the_agent_drains(srv):
    assert srv._MAP_LAYERS_FIELD == "_map_layers"


def test_a_geojson_layer_carries_its_features(srv, monkeypatch):
    """A GeoJSON layer (addEsriFeatureService, or GeoJSON given to
    addLayer) has no Earth Engine expression, but its features are in
    hand, so they ride along and the panel can offer them as a file.
    Another ``addLayer`` entry (not GeoJSON) still reports nothing."""
    sid = "export-test-geojson"
    gj = json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"NAME": "Salt Lake"},
         "geometry": {"type": "Point", "coordinates": [-111.9, 40.7]}}]})
    Map = SimpleNamespace(idDictList=[
        {"name": "Utah Counties", "function": "addLayer", "item": gj,
         "viz": json.dumps({"strokeColor": "2b5c8f", "layerType": "geoJSONVector"})},
        {"name": "Other", "function": "addLayer", "item": '{"not": "geojson"}', "viz": "{}"},
        {"name": "Bad viz", "function": "addLayer", "item": gj, "viz": "not json"},
    ])
    sess = SimpleNamespace(namespace={"Map": Map}, session_id=sid)
    monkeypatch.setitem(srv._sessions, sid, sess)
    srv._note_shown_map(sess, Map, "utah counties")
    snap = {e["name"]: e for e in srv._map_layer_snapshot(sid)}
    assert snap["Utah Counties"]["item"] == gj
    assert snap["Other"]["item"] == ""
    assert snap["Bad viz"]["item"] == ""
