"""Uncached Esri services must actually draw, and feature layers must not
download geometry no screen can show.

Three defects, found together on the esri_integration example:

* Every NAIP ImageServer on IIPP is uncached. addEsriImageService added it
  as ``/tile/{z}/{y}/{x}`` regardless, and every tile answered 404 -- the
  layer was blank.
* The dynamic-overlay path that uncached services need emitted a bare
  ``addDynamicToMap(...)``. That builds a ``<dynamic-layer>`` element the
  viewer never defines: "layer.startUp is not a function", zero export
  requests, for every dynamic MapServer too (FEMA NFHL et al.).
* Feature layers were fetched at full resolution and thinned client-side
  afterwards: 37 NIFC fire perimeters were 34 MB and ~30 s, where asking
  the server for ~5 m geometry is 6 MB and ~6 s.
"""
import inspect
import json
import shutil
import subprocess

import pytest

NODE = shutil.which("node")

NAIP = "https://imagery.geoplatform.gov/iipp/rest/services/NAIP/NAIP_plus/ImageServer"
UNCACHED_META = {"name": "NAIP_plus", "bandCount": 4, "capabilities": "Image,Metadata"}
CACHED_META = {"name": "X", "tileInfo": {"rows": 256}, "singleFusedMapCache": True}


def _mapper():
    # Imported at run time: test_esriLib swaps a stub into
    # sys.modules["geeViz.geeView"] during collection.
    import geeViz.geeView as gv
    m = gv.mapper()
    m.idDictList = []
    m.mapCommandList = []
    return m


def _esri():
    import geeViz.esriLib as el
    return el


# ── uncached ImageServer -> exportImage ────────────────────────────────

def test_an_uncached_image_service_is_drawn_through_export_image():
    m = _mapper()
    _esri().addEsriImageService(NAIP, name="NAIP", target_map=m, _meta=UNCACHED_META)
    (d,) = m.idDictList
    assert d.get("_is_dynamic_esri"), "an uncached service was added as tiles"
    assert d["_dyn_base_url_1"].startswith(NAIP + "/exportImage?")
    assert d["_dyn_base_url_1"].endswith("bbox=")
    assert "/tile/" not in d["_dyn_base_url_1"]


def test_a_cached_image_service_stays_on_tiles():
    m = _mapper()
    _esri().addEsriImageService(NAIP, name="NAIP", target_map=m, _meta=CACHED_META)
    (d,) = m.idDictList
    assert d.get("_is_tile_url")
    assert d["_tile_url_template"] == NAIP + "/tile/{z}/{y}/{x}"


def test_metadata_is_read_when_not_supplied(monkeypatch):
    """The wiring, not just the branch: called the ordinary way, the
    service is asked whether it is cached."""
    from georest.restesri import portal
    asked = []
    monkeypatch.setattr(portal, "getServiceMetadata",
                        lambda url, token=None: asked.append(url) or UNCACHED_META)
    m = _mapper()
    _esri().addEsriImageService(NAIP, target_map=m)
    assert asked == [NAIP]
    assert m.idDictList[0].get("_is_dynamic_esri")


def test_a_dynamic_map_service_keeps_its_export_endpoint():
    m = _mapper()
    m.addDynamicMapService("https://x.test/arcgis/rest/services/F/MapServer", layers="show:1")
    url = m.idDictList[0]["_dyn_base_url_1"]
    assert "/MapServer/export?" in url and "layers=show:1" in url


# ── the viewer call actually draws ─────────────────────────────────────

_HARNESS = r"""
const fs = require("fs");
const src = fs.readFileSync(0, "utf8");
const calls = [];
const Map = new Proxy({}, { get: (_, fn) => (...a) => { calls.push([fn, a]); } });
const ee = { data: new Proxy({}, { get: () => () => {} }) };
const showMessage = () => {}, $ = () => ({ click() {} });
const staticTemplates = { loadingModal: {} }, mode = "geeViz";
const localStorage = {}, window = { location: { origin: "" } };
const layerLoadErrorMessages = [];
// What the shipped viewer does with this call.
function addDynamicToMap() { throw new Error("layer.startUp is not a function"); }
let queryWindowMode, yLabelMaxLength;
setTimeout = () => {};
eval(src.replace("var layerLoadErrorMessages=[];", "") + ";runGeeViz();");
process.stdout.write(JSON.stringify({ calls, errors: layerLoadErrorMessages }));
"""


@pytest.mark.skipif(NODE is None, reason="node not available")
def test_a_dynamic_layer_goes_through_the_viewers_working_path():
    m = _mapper()
    _esri().addEsriImageService(NAIP, name="NAIP", target_map=m, _meta=UNCACHED_META)
    js = m._build_run_js()
    out = subprocess.run([NODE, "-e", _HARNESS], input=js, text=True,
                         capture_output=True, encoding="utf-8")
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout)
    assert got["errors"] == [], got["errors"]
    adds = [a for fn, a in got["calls"] if fn == "addLayer"]
    assert len(adds) == 1, got["calls"]
    item, viz, name = adds[0][0], adds[0][1], adds[0][2]
    assert name == "NAIP"
    assert viz["layerType"] == "dynamicMapService"
    assert item[0]["baseURL"].startswith(NAIP + "/exportImage?")
    assert item[1]["baseURL"] == item[0]["baseURL"]
    assert item[0]["ending"].startswith("&")


# ── server-side generalization ─────────────────────────────────────────

GEOJSON = {"type": "FeatureCollection", "features": []}


def _patch_query(monkeypatch, supports=True):
    from georest.restesri import services
    seen = {}
    if supports:
        def fake(url, where="1=1", geometry=None, max_features=1000, token=None,
                 max_allowable_offset=None, geometry_precision=None):
            seen.update(max_allowable_offset=max_allowable_offset,
                        geometry_precision=geometry_precision)
            return GEOJSON
    else:
        def fake(url, where="1=1", geometry=None, max_features=1000, token=None):
            seen["called"] = True
            return GEOJSON
    monkeypatch.setattr(services, "queryFeatureService", fake)
    return seen


FEAT = "https://x.test/arcgis/rest/services/F/FeatureServer/0"


def test_auto_asks_the_server_for_display_geometry(monkeypatch):
    seen = _patch_query(monkeypatch)
    _esri().addEsriFeatureService(FEAT, target_map=_mapper())
    assert seen["max_allowable_offset"] == pytest.approx(5 / 111_320, rel=1e-3)
    assert seen["geometry_precision"] == 6


def test_a_numeric_simplify_is_the_server_tolerance(monkeypatch):
    seen = _patch_query(monkeypatch)
    _esri().addEsriFeatureService(FEAT, target_map=_mapper(), simplify=50)
    assert seen["max_allowable_offset"] == pytest.approx(50 / 111_320, rel=1e-3)


def test_simplify_false_fetches_exact_geometry(monkeypatch):
    seen = _patch_query(monkeypatch)
    _esri().addEsriFeatureService(FEAT, target_map=_mapper(), simplify=False)
    assert seen["max_allowable_offset"] is None


def test_an_older_georest_still_works(monkeypatch):
    """georest 0.4.0 has no generalization parameters; passing them would
    be a TypeError on every feature layer."""
    seen = _patch_query(monkeypatch, supports=False)
    _esri().addEsriFeatureService(FEAT, target_map=_mapper())
    assert seen == {"called": True}
