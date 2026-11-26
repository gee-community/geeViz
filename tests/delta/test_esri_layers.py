"""ArcGIS services in Delta: drawn, legended and queried in the browser,
with no Earth Engine and nothing fetched in Python (georest.view js/esri,
js/plugins/esri.js). Recorded answers are unit-tested in
georest tests/view/js/esri_*.test.mjs; these run against the live services.

Needs the local eeCreds proxy (it serves the page) and a network.
"""
import json
import os
import time

import pytest

pytestmark = pytest.mark.live

NFHL = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer"
TOPO = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer"
MTBS63 = "https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_MTBS_01/MapServer/63"
LCMS = "https://imagery.geoplatform.gov/iipp/rest/services/Vegetation/USFS_EDW_LCMS_AnnualChange_CONUS/ImageServer"
# a zone AE on the Cache la Poudre in Fort Collins (Flood Hazard Zones draws from zoom 14)
ZONE = (-105.068, 40.59)
MAP_CENTER = (750, 437)
FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


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
    page.mouse.click(*MAP_CENTER)
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
    with open(os.path.join(FIXTURES, "esri_error_body.json"), encoding="utf-8") as f:
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


def build_fires(Map):
    Map.addEsriFeatureService(MTBS63, name="Fires", where="year = 2020", viz_params={"strokeColor": "d62728"})
    # the Cameron Peak fire, 2020, west of Fort Collins
    Map.setCenter(-105.62, 40.62, 11)
    Map.turnOnInspector()


def test_a_feature_layer_draws_for_the_view_and_answers_a_click(live_map):
    seen = []
    page = live_map(build_fires, setup=recorder(seen))
    wait_for(page, "() => { const l = __delta.store.get().layers[0]; return l && l.kind === 'esri.feature' && !l.loading && (l.progress || {}).loaded > 0; }", timeout=120)
    l = layers(page)[0]
    assert l["error"] is None, l
    queries = [u for u in seen if "/MapServer/63/query" in u]
    assert queries and all("maxAllowableOffset" in u for u in queries), queries[:2]
    assert page.evaluate("(id) => __delta.engine.layers.stats(id).onMap", l["id"])
    page.evaluate("() => __delta.store.set({results: []}, 'test')")
    page.mouse.click(*MAP_CENTER)
    wait_for(page, "() => __delta.store.get().querying === false && __delta.store.get().results.length >= 1", timeout=60)
    rs = page.evaluate("__delta.store.get().results")
    names = [dict(r["data"]["rows"]).get("fire_name") for r in rs]
    assert "CAMERON PEAK" in names, rs
    # every field, asked for the feature hit
    assert any("objectIds=" in u and ("outFields=*" in u or "outFields=%2A" in u) for u in seen)
    assert ee_requests(seen) == []


STATES = "https://services.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services/USA_States_Generalized_Boundaries/FeatureServer/0"


def build_states(Map):
    Map.addEsriFeatureService(STATES, name="States")
    Map.setCenter(-105.5, 39.0, 6)


def test_a_feature_layer_draws_with_its_service_renderer(live_map):
    page = live_map(build_states, setup=recorder([]))
    wait_for(page, "() => { const l = __delta.store.get().layers[0]; return l && l.legend && !l.loading; }", timeout=120)
    l = layers(page)[0]
    assert l["error"] is None, l
    lg = l["legend"]
    # the service's simple renderer: an orange fill at alpha 59 with a grey outline
    assert lg["type"] == "symbols" and len(lg["items"]) == 1, lg
    g = lg["items"][0]["glyph"]
    assert (g["geom"], g["fill"], g["stroke"]) == ("polygon", "#e38b4f", "#6e6e6e"), g
    # one symbol: shown in the row, nothing to open
    assert page.evaluate("(id) => !!document.querySelector(`.layer[data-id='${id}'] .legbtn.symbol svg`)", l["id"])


def test_elevation_without_earth_engine_comes_from_terrain_tiles(live_map):
    seen = []
    page = live_map(build, setup=recorder(seen))
    settled(page)
    # move the mouse over the map until the status bar shows a number
    deadline = time.time() + 30
    text = ""
    while time.time() < deadline:
        page.mouse.move(MAP_CENTER[0] + 40, MAP_CENTER[1] + 20)
        page.mouse.move(MAP_CENTER[0] + 41, MAP_CENTER[1] + 21)
        time.sleep(1.2)
        text = page.evaluate("() => [...document.querySelectorAll('span')].map(s => s.textContent).find(t => t.startsWith('Elev ')) || ''")
        if any(ch.isdigit() for ch in text):
            break
    assert any(ch.isdigit() for ch in text), text
    assert any("elevation-tiles-prod/terrarium/" in u for u in seen)
    assert not any("3DEPElevation" in u for u in seen)
    assert ee_requests(seen) == []


def build_bad_where(Map):
    Map.addEsriFeatureService(STATES, name="Bad where", where="NO_SUCH_FIELD = 1")
    Map.setCenter(-105.5, 39.0, 6)


def test_a_feature_layer_that_fails_shows_the_service_message(live_map):
    page = live_map(build_bad_where, setup=recorder([]), wait_layers=False)
    wait_for(page, "() => { const l = __delta.store.get().layers[0]; return l && l.error; }", timeout=60)
    err = layers(page)[0]["error"]
    assert "does not allow" not in err and len(err) > 10, err
    print(err)
