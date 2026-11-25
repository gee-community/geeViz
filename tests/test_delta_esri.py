"""geeViz's Map.addEsri* on the Delta skin: one Map.addEsriLayer call per
layer, drawn in the browser, and nothing fetched in Python. The original
skin, and any layer with a token, keep esriLib's Python fetch.

No network: urlopen is patched to fail the test if anything is fetched.
"""
import calendar
import json
import re
import urllib.request

import pytest

import geeViz.geeView as gv
from geeViz import esriLib

NFHL = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer"
LCMS = "https://imagery.geoplatform.gov/iipp/rest/services/Vegetation/USFS_EDW_LCMS_AnnualChange_CONUS/ImageServer"
MTBS63 = "https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_MTBS_01/MapServer/63"


def ms(y, m=1, d=1):
    return calendar.timegm((y, m, d, 0, 0, 0)) * 1000


@pytest.fixture
def no_fetch(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("Python fetched a service: %r" % (a[:1],))
    monkeypatch.setattr(urllib.request, "urlopen", boom)


@pytest.fixture
def delta_map():
    m = gv.mapper()
    m.setSkin("delta")
    return m


def esri_calls(js):
    """The (url, viz, name, visible) of each Map.addEsriLayer call."""
    out = []
    for m in re.finditer(r"Map\.addEsriLayer\((\".*?\"),(\{.*?\}),(\".*?\"),(true|false)\);", js):
        out.append((json.loads(m.group(1)), json.loads(m.group(2)), json.loads(m.group(3)), m.group(4) == "true"))
    return out


def test_delta_esri_layers_are_drawn_in_the_browser(no_fetch, delta_map):
    m = delta_map
    m.addEsriMapService(NFHL, name="Flood", viz_params={"layers": "show:28"})
    m.addEsriImageService(LCMS, viz_params={"renderingRule": {"rasterFunction": "None"}}, time=2021)
    m.addEsriFeatureService(MTBS63, where="year > 2020", viz_params={"strokeColor": "d62728"},
                            max_features=500, simplify=False, max_layer_mb=20, bbox=[-106, 40, -105, 41])
    calls = esri_calls(m._build_run_js())
    assert [c[0] for c in calls] == [NFHL, LCMS, MTBS63]
    flood, lcms, mtbs = (c[1] for c in calls)
    assert calls[0][2] == "Flood"
    assert flood["esri"]["layers"] == "show:28"
    assert flood["esriKind"] == "esri.map"
    assert lcms["esriKind"] == "esri.image"
    assert lcms["esri"]["renderingRule"] == {"rasterFunction": "None"}
    assert lcms["esri"]["time"] == [ms(2021), ms(2022) - 1]
    assert mtbs["esriKind"] == "esri.feature"
    assert mtbs["esri"]["where"] == "year > 2020"
    assert mtbs["esri"]["maxFeatures"] == 500
    assert mtbs["esri"]["simplify"] is False
    assert mtbs["esri"]["maxLayerMB"] == 20
    assert mtbs["esri"]["bbox"] == [-106, 40, -105, 41]
    assert mtbs["strokeColor"] == "d62728"


def test_time_forms(no_fetch, delta_map):
    m = delta_map
    m.addEsriImageService(LCMS, name="a", time="2010-06-15")
    m.addEsriImageService(LCMS, name="b", time=("2010", "2012"))
    m.addEsriImageService(LCMS, name="c", time="all")
    a, b, c = (x[1] for x in esri_calls(m._build_run_js()))
    assert a["esri"]["time"] == [ms(2010, 6, 15), ms(2010, 6, 16) - 1]
    assert b["esri"]["time"] == [ms(2010), ms(2013) - 1]
    assert c["timelapse"] is True and "time" not in c["esri"]


def test_add_time_lapse_with_a_service_url(no_fetch, delta_map):
    delta_map.addTimeLapse(LCMS, {"canAreaChart": True}, "LCMS change")
    (url, viz, name, visible), = esri_calls(delta_map._build_run_js())
    assert (url, name) == (LCMS, "LCMS change")
    assert viz["timelapse"] is True and viz["canAreaChart"] is True


def test_a_name_comes_from_the_url(no_fetch, delta_map):
    delta_map.addEsriMapService(NFHL)
    delta_map.addEsriFeatureService(MTBS63)
    names = [c[2] for c in esri_calls(delta_map._build_run_js())]
    assert names == ["NFHL", "EDW_MTBS_01 63"]


def test_a_token_keeps_the_python_fetch(monkeypatch, delta_map):
    seen = []
    monkeypatch.setattr(esriLib, "addEsriMapService", lambda *a, **k: seen.append((a, k)))
    delta_map.addEsriMapService(NFHL, name="Secure", token="SECRET-TOKEN")
    assert seen and seen[0][1]["token"] == "SECRET-TOKEN"
    assert "addEsriLayer" not in delta_map._build_run_js()


def test_the_original_skin_fetches_in_python(monkeypatch):
    seen = []
    monkeypatch.setattr(esriLib, "addEsriMapService", lambda *a, **k: seen.append(k.get("target_map")))
    m = gv.mapper()
    m.setSkin("original")
    m.addEsriMapService(NFHL, name="Flood")
    assert seen == [m]
    assert "addEsriLayer" not in m._build_run_js()


def test_switching_to_the_original_skin_later_fetches_at_view(monkeypatch, delta_map):
    def fake(url, **k):
        k["target_map"].addTileLayer("https://t/{z}/{x}/{y}", name=k.get("name") or "x")
    monkeypatch.setattr(esriLib, "addEsriMapService", fake)
    delta_map.addEsriMapService(NFHL, name="Flood")
    assert delta_map.idDictList[0].get("_is_esri")
    delta_map.setSkin("original")
    js = delta_map._build_run_js()
    assert "addEsriLayer" not in js
    assert "https://t/{z}/{x}/{y}" in js
    # the recorded layer is kept, for a later Delta view
    assert delta_map.idDictList[0].get("_is_esri")


def test_export_layer_json_lists_the_service(no_fetch, delta_map, tmp_path):
    delta_map.addEsriMapService(NFHL, name="Flood")
    out = delta_map.exportLayerJson(filename="layers.json", output_dir=str(tmp_path))
    data = json.loads((tmp_path / "layers.json").read_text()) if (tmp_path / "layers.json").exists() else out
    text = json.dumps(data)
    assert NFHL in text and "esri.map" in text
