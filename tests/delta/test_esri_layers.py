"""ArcGIS services in Delta: drawn, legended and queried in the browser,
with no Earth Engine and nothing fetched in Python (geeView/delta/js/esri,
js/plugins/esri.js). Recorded answers are unit-tested in
geeView/delta/tests/esri_*.test.mjs; these run against the live services.

Needs the local eeCreds proxy (it serves the page) and a network.
"""
import json
import os
import time

import pytest

pytestmark = pytest.mark.live

NFHL = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer"
TOPO = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer"
LCMS = "https://imagery.geoplatform.gov/iipp/rest/services/Vegetation/USFS_EDW_LCMS_AnnualChange_CONUS/ImageServer"
# a zone AE on the Cache la Poudre in Fort Collins (Flood Hazard Zones draws from zoom 14)
ZONE = (-105.068, 40.59)
MAP_CENTER = (750, 437)
FIXTURES = os.path.join(os.path.dirname(__file__), "..", "..", "geeView", "delta", "tests", "fixtures", "esri")


def wait_for(page, js, arg=None, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page.evaluate(js, arg):
            return
        time.sleep(0.25)
    raise AssertionError("timed out waiting for: " + js + " " + repr(getattr(page, "delta_errors", None)))


# imagery.geoplatform.gov answers 403 to a HeadlessChrome user agent (a bot
# filter; desktop browsers get the service), so the tests' browser says Chrome.
CHROME_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def recorder(seen, routes=None):
    def setup(ctx):
        ctx.set_extra_http_headers({"User-Agent": CHROME_UA})
        ctx.on("request", lambda req: seen.append(req.url))
        for pattern, handler in (routes or []):
            ctx.route(pattern, handler)
    return setup


def ee_requests(seen):
    return [u for u in seen if "ee_api_js" in u or "/ee-api/" in u]


def layers(page):
    return page.evaluate("__delta.store.get().layers")


def by_name(page, name):
    return [l for l in layers(page) if l["name"] == name][0]


def build(Map):
    Map.addEsriMapService(TOPO, name="Topo")
    Map.addEsriImageService(LCMS, name="LCMS 2021", time=2021)
    Map.addEsriMapService(NFHL, name="Flood", viz_params={"layers": "show:28"})
    Map.setCenter(ZONE[0], ZONE[1], 15)
    Map.turnOnInspector()


def settled(page):
    wait_for(page, "() => { const ls = __delta.store.get().layers; return ls.length === 3 && ls.every(l => !l.loading && (l.legend || l.error)); }", timeout=120)


def query_center(page):
    page.evaluate("() => __delta.store.set({results: []}, 'test')")
    page.mouse.dblclick(*MAP_CENTER)
    wait_for(page, "() => __delta.store.get().querying === false && __delta.store.get().results.length >= 3", timeout=90)
    return page.evaluate("__delta.store.get().results")


def test_esri_services_draw_with_legends_and_no_earth_engine(live_map):
    seen = []
    page = live_map(build, setup=recorder(seen))
    settled(page)
    for name in ("Topo", "LCMS 2021", "Flood"):
        l = by_name(page, name)
        assert l["error"] is None, l
        assert page.evaluate("(id) => __delta.engine.layers.stats(id).onMap", l["id"]), name
    assert by_name(page, "Topo")["kind"] == "esri.tile"
    assert by_name(page, "Flood")["kind"] == "esri.map"
    assert by_name(page, "LCMS 2021")["kind"] == "esri.image"
    lcms = by_name(page, "LCMS 2021")["legend"]
    assert lcms["type"] == "images" and len(lcms["items"]) == 16
    flood = by_name(page, "Flood")["legend"]
    assert flood["type"] == "images" and any("A" in i["label"] for i in flood["items"]), flood
    # export images were asked for the view, with the time and the sublayer
    assert any("/ImageServer/exportImage?" in u and "time=" in u for u in seen)
    assert any("/NFHL/MapServer/export?" in u and "show%3A28" in u for u in seen)
    assert ee_requests(seen) == [], ee_requests(seen)


def test_query_identifies_each_service(live_map):
    seen = []
    page = live_map(build, setup=recorder(seen))
    settled(page)
    rs = query_center(page)
    titles = {r["title"] for r in rs}
    assert {"Topo", "LCMS 2021", "Flood"} <= titles, titles
    flood = [r for r in rs if r["title"] == "Flood"]
    assert flood[0]["kind"] == "table" and flood[0]["meta"].startswith("Flood Hazard Zones"), flood[0]
    rows = dict(flood[0]["data"]["rows"])
    assert rows.get("FLD_ZONE") == "AE", rows
    lc = [r for r in rs if r["title"] == "LCMS 2021"][0]
    assert lc["kind"] == "value" and lc["data"]["bands"][0]["label"], lc
    assert ee_requests(seen) == []


def test_a_failing_identify_is_one_card(live_map):
    with open(os.path.join(FIXTURES, "error_body.json"), encoding="utf-8") as f:
        body = json.dumps(json.load(f)["response"])

    def fail_identify(route):
        route.fulfill(status=200, content_type="application/json", body=body,
                      headers={"Access-Control-Allow-Origin": "*"})

    seen = []
    page = live_map(build, setup=recorder(seen, [("**/NFHL/MapServer/identify**", fail_identify)]))
    settled(page)
    rs = query_center(page)
    flood = [r for r in rs if r["title"] == "Flood"]
    assert len(flood) == 1 and flood[0]["meta"] == "Query failed", flood
    assert "Invalid URL" in flood[0]["data"]["error"]
    assert any(r["title"] == "LCMS 2021" and r["meta"] != "Query failed" for r in rs)
