"""The Delta skin writes a map document (georest.view) instead of a map
script: every layer and map command geeViz records becomes data the viewer
applies, and the viewer's files come from georest.

Needs Earth Engine for the ee objects (nothing is computed).
"""
import inspect
import json
import os
import re

import pytest

import geeViz.geeView as gv
from georest.view._document import validate

ee = gv.ee
NFHL = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer"
SQUARE = {"type": "Feature", "properties": {"n": 1},
          "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}}


@pytest.fixture
def m():
    m = gv.mapper()
    m.setSkin("geoview")
    return m


def test_layers_and_commands_become_a_document(m):
    img = ee.Image(1)
    m.addLayer(img, {"min": 0, "max": 1}, "One")
    m.addTimeLapse(ee.ImageCollection([img, img]), {"min": 0, "max": 1}, "Frames")
    m.addSelectLayer(ee.FeatureCollection([ee.Feature(ee.Geometry.Point([0, 0]))]), {}, "Pick")
    m.addAreaChartLayer(img, {"line": True}, "Chart me")
    m.addTileLayer("https://t/{z}/{x}/{y}.png", name="Tiles", max_zoom=15)
    m.addEsriMapService(NFHL, name="Flood", viz_params={"layers": "show:28"})
    m.addLayer(SQUARE, {"strokeColor": "ff0000"}, "Square")
    m.setCenter(-105, 40, 9)
    m.turnOnInspector()
    m.setQueryPrecision(2, 0.5)
    m.setTitle("A map")
    m.setYLabelMaxLength(20)
    m.setCanReorderLayers(False)
    doc = validate(m._build_document())
    assert [(l["type"], l["name"]) for l in doc["layers"]] == [
        ("ee.image", "One"), ("ee.timelapse", "Frames"), ("ee.select", "Pick"), ("ee.areaChart", "Chart me"),
        ("xyz", "Tiles"), ("esri.map", "Flood"), ("geojson", "Square"),
    ]
    one = doc["layers"][0]
    assert one["source"]["serialized"] == json.loads(img.serialize())
    assert doc["layers"][4]["source"] == {"url": "https://t/{z}/{x}/{y}.png", "maxZoom": 15}
    assert doc["layers"][5]["source"]["options"]["layers"] == "show:28"
    assert doc["layers"][6]["source"]["geojson"] == SQUARE
    cmds = doc["commands"]
    for want in (["setCenter", -105, 40, 9], ["turnOnInspector"], ["setQueryPrecision", 2, 0.5], ["setTitle", "A map"],
                 ["setGlobal", "yLabelMaxLength", 20], ["setProperty", "canReorderLayers", False],
                 ["setGlobal", "queryWindowMode", "sidePane"]):
        assert want in cmds, (want, cmds)
    # the viewer writes name then accent (bold) with nothing between: "geeViz geoView"
    assert doc["brand"]["name"] + doc["brand"]["accent"] == "geeViz geoView", doc["brand"]
    assert doc["brand"]["accent"] == "geoView"
    # geeViz maps keep the geeViz logo; georest's viewer shows its own otherwise
    assert doc["brand"]["logo"] == "geeviz"


@pytest.mark.parametrize("cmd, want", [
    ('Map.setCenter(-105,40,9)', ["setCenter", -105, 40, 9]),
    ('Map.setCenter(-105,40,null)', ["setCenter", -105, 40, None]),
    ('map.setZoom(7)', ["mapSetZoom", 7]),
    ('synchronousCenterObject({"type": "Polygon", "coordinates": []})', ["synchronousCenterObject", {"type": "Polygon", "coordinates": []}]),
    ('areaChart.populateChartLayerSelect()', ["populateChartLayerSelect"]),
    ('Map.canReorderLayers = false;', ["setProperty", "canReorderLayers", False]),
    ('yLabelMaxLength = 20', ["setGlobal", "yLabelMaxLength", 20]),
    ('Map.setQueryTransform([30, 0, -2361915, 0, -30, 3177735])', ["setQueryTransform", [30, 0, -2361915, 0, -30, 3177735]]),
    ('Map.setTitle("a \\"quoted\\" title")', ["setTitle", 'a "quoted" title']),
])
def test_command_strings_become_data(cmd, want):
    assert gv._command_to_data(cmd) == want


def test_an_unreadable_command_is_named():
    with pytest.raises(ValueError, match="alert"):
        gv._command_to_data("alert(1)")


def test_every_command_method_is_readable(m):
    # every mapper method that records a command, called with sample arguments
    samples = {
        "setCenter": (-105, 40, 9), "setZoom": (7,), "setTitle": ("t",), "setMapTitle": ("t",),
        "setQueryCRS": ("EPSG:5070",), "setQueryScale": (30,), "setQueryTransform": ([30, 0, 0, 0, -30, 0],),
        "setQueryPrecision": (2, 0.5), "setQueryDateFormat": ("YYYY",), "setQueryBoxColor": ("ff0000",),
        "turnOnInspector": (), "turnOnAutoAreaCharting": (), "turnOnUserDefinedAreaCharting": (),
        "turnOnSelectionAreaCharting": (), "populateAreaChartLayerSelect": (), "setYLabelMaxLength": (20,),
        "setYLabelBreakLength": (10,), "setYLabelMaxLines": (5,), "setYLabelFontSize": (10,),
        "setCanReorderLayers": (False,), "centerObject": (ee.Geometry.Point([-105, 40]).buffer(1000),),
    }
    src = inspect.getsource(gv.mapper)
    recorders = set(re.findall(r"def (\w+)\(self[^)]*\):(?:(?!\n    def ).)*?mapCommandList\.append", src, re.S))
    missing = recorders - set(samples) - {"_sync_center"}
    assert not missing, f"add samples for: {missing}"
    for name, args in samples.items():
        if not hasattr(m, name):
            continue
        m.clearMapCommands() if hasattr(m, "clearMapCommands") else None
        getattr(m, name)(*args)
    for cmd in m.mapCommandList:
        gv._command_to_data(cmd)


def test_view_writes_the_document_and_opens_georests_page(m, monkeypatch, tmp_path):
    monkeypatch.setattr(gv.webbrowser, "open", lambda *a, **k: True)
    m.addLayer(SQUARE, {}, "Square")
    m.view(open_browser=False, open_iframe=False)
    url = m.view_url
    assert "/geoview/geoview.html?" in url, url
    doc_rel = re.search(r"[?&]doc=([^&]+)", url).group(1)
    assert doc_rel.startswith("../geeView/src/gee/gee-run/map-") and doc_rel.endswith(".json")
    path = os.path.join(os.path.dirname(gv.__file__), "geeView", "src", "gee", "gee-run", doc_rel.rsplit("/", 1)[1])
    with open(path, encoding="utf-8") as f:
        assert json.load(f)["layers"][0]["name"] == "Square"


def test_export_html_is_georests_page_with_the_document(m, tmp_path):
    m.addLayer(SQUARE, {}, "Square")
    out = tmp_path / "map.html"
    m.export_html(str(out), asset_base="/geeView/static")
    html = out.read_text(encoding="utf-8")
    assert '<base href="/geeView/static/geoview/">' in html
    assert 'id="geoview-document">{' in html
    assert "./js/main.js" in html and "delta/js" not in html
    # the agent's sign-in placeholders are still there for it to fill
    assert "urlParams.accessToken=" in html
