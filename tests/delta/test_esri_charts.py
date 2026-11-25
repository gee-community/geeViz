"""Chart area on ArcGIS services in Delta, with no Earth Engine: class areas
from an image service's computeHistograms (over time for a timelapse, with
a Sankey between periods) and feature counts from outStatistics.

Needs the local eeCreds proxy (it serves the page) and a network.
"""
import time

import pytest

pytestmark = pytest.mark.live

LCMS = "https://imagery.geoplatform.gov/iipp/rest/services/Vegetation/USFS_EDW_LCMS_AnnualChange_CONUS/ImageServer"
MTBS63 = "https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_MTBS_01/MapServer/63"
CHROME_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def wait_for(page, js, timeout=180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page.evaluate(js):
            return
        time.sleep(0.5)
    raise AssertionError("timed out waiting for " + js + " " + repr(page.evaluate("__delta.store.get().notices")))


def recorder(seen):
    def setup(ctx):
        ctx.set_extra_http_headers({"User-Agent": CHROME_UA})
        ctx.on("request", lambda req: seen.append(req.url))
    return setup


def no_ee(seen):
    return [u for u in seen if "ee_api_js" in u or "/ee-api/" in u] == []


def build(Map):
    Map.addEsriImageService(LCMS, name="LCMS 2021", time=2021, viz_params={"canAreaChart": True})
    Map.addEsriFeatureService(MTBS63, name="Fires", where="year >= 2018", viz_params={"canAreaChart": True, "chartField": "fire_type"})
    Map.setCenter(-105.65, 40.6, 12)
    Map.turnOnAutoAreaCharting()


def test_esri_layers_chart_the_view_without_earth_engine(live_map):
    seen = []
    page = live_map(build, setup=recorder(seen))
    wait_for(page, "() => { const r = __delta.store.get().results; return r.some(x => x.title === 'LCMS 2021') && r.some(x => x.title === 'Fires') && !__delta.store.get().charting; }")
    rs = {r["title"]: r for r in page.evaluate("__delta.store.get().results")}
    lc = rs["LCMS 2021"]
    assert lc["kind"] == "chart" and "Stable" in lc["data"]["columns"], lc["data"]["columns"]
    assert all(c for c in lc["data"]["colors"]), lc["data"]["colors"]
    fires = rs["Fires"]
    assert fires["kind"] == "chart" and fires["data"]["yLabel"] == "Features"
    assert any("/computeHistograms" in u for u in seen)
    assert no_ee(seen)


def build_tl(Map):
    Map.addTimeLapse(LCMS, {"canAreaChart": True, "areaChartParams": {"sankey": True, "line": True}}, "LCMS change")
    Map.setCenter(-105.65, 40.6, 12)
    Map.turnOnAutoAreaCharting()


def test_an_esri_timelapse_charts_over_time_with_a_sankey(live_map):
    seen = []
    page = live_map(build_tl, setup=recorder(seen), wait_layers=False)
    wait_for(page, "() => __delta.store.get().layers.length === 1")
    page.evaluate("() => __delta.store.update(s => ({...s, layers: s.layers.map(x => ({...x, visible: true}))}), 'test')")
    # charting follows the view: nudge it once the layer is on
    page.evaluate("() => { const m = __delta.engine.gmap; m.panBy(1, 0); }")
    wait_for(page, "() => { const r = __delta.store.get().results; return r.some(x => x.kind === 'sankey') && r.some(x => x.kind === 'chart') && !__delta.store.get().charting; }", timeout=300)
    rs = page.evaluate("__delta.store.get().results")
    chart = [r for r in rs if r["kind"] == "chart"][0]
    assert chart["data"]["isCollection"] is True and len(chart["data"]["rows"]) >= 40
    sk = [r for r in rs if r["kind"] == "sankey"][0]
    assert sk["data"]["links"], sk["data"]
    assert no_ee(seen)
