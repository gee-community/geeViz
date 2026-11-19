"""Delta Chart area tool: charts and Sankey over an area.

The Map view source charts the map's bounds; the cards' numbers must equal
charts.summarize_and_chart run in this process over the same rectangle with
the same scale, crs and transform. Units and Show as changes re-render from
the cache with no Earth Engine request, a single image charts as bars, the
Sankey draws gradient links with tooltips, stale areas are dropped, an
uploaded GeoJSON polygon charts, and CSV and PNG actions download files.

Needs Earth Engine, the local eeCreds proxy and a network: every test is live.
Run serially (view() rewrites a shared runGeeViz.js).
"""
import json
import math
import re
import time

import pytest

from make_fixtures import df_to_table, sankey_to_js

pytestmark = pytest.mark.live

# Verified against the live catalog (2026-11-18): the current LCMS release
# and the NLCD 2021 release's 2021 image (no deprecation warning).
LCMS = "projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11"
NLCD_2021 = "USGS/NLCD_RELEASES/2021_REL/NLCD/2021"
PERIODS = [[2016, 2018], [2020, 2022]]
CENTER = (-111.6, 40.6)
ZOOM = 14
# Earth Engine API calls (value:compute and friends); map tiles are GETs to .../tiles/...
EE_CALL = re.compile(r"/v1(alpha|beta)?/projects/[^/]+/(value:compute|maps|table|image|thumbnails|videoThumbnails|algorithms)")


def ee():
    import geeViz.geeView as gv

    return gv.ee


def lcms_collection():
    e = ee()
    return e.ImageCollection(LCMS).filter('study_area=="CONUS"').select(["Land_Cover"]).filter(e.Filter.calendarRange(2015, 2023, "year"))


def nlcd_image():
    return ee().Image(NLCD_2021).select(["landcover"])


def build(Map):
    Map.addLayer(
        lcms_collection(),
        {"autoViz": True, "canAreaChart": True, "areaChartParams": {"line": True, "sankey": True, "sankeyTransitionPeriods": PERIODS}},
        "LCMS Land Cover",
    )
    Map.addLayer(nlcd_image(), {"autoViz": True, "canAreaChart": True}, "NLCD 2021")
    Map.setCenter(CENTER[0], CENTER[1], ZOOM)


@pytest.fixture
def page(live_map):
    p = live_map(build, wait_layers=False)
    p.ee_calls = []
    p.on("request", lambda r: p.ee_calls.append(r.url) if r.method == "POST" and EE_CALL.search(r.url) else None)
    return p


def wait_for(page, js, arg=None, timeout=150):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page.evaluate(js, arg):
            return
        time.sleep(0.25)
    state = page.evaluate(
        """() => { const s = __delta.store.get(); return {tool: s.tool, areaFrom: s.areaFrom, charting: s.charting, where: s.where,
          results: s.results.map(r => [r.title, r.kind]), notices: s.notices, chartArea: s.chartArea && s.chartArea.label}; }"""
    )
    raise AssertionError("timed out waiting for: %s\nstate: %s\nconsole errors: %s" % (js, state, page.delta_errors))


def wait_charts(page, n=3):
    wait_for(page, "(n) => !__delta.store.get().charting && __delta.store.get().results.length >= n", n)


def results(page):
    return page.evaluate("__delta.store.get().results")


def result(page, layer, kind):
    found = [r for r in results(page) if r["data"]["layerName"] == layer and r["kind"] == kind]
    assert len(found) == 1, [(r["data"]["layerName"], r["kind"]) for r in results(page)]
    return found[0]


def chart_view(page):
    page.evaluate("__delta.api.turnOnAutoAreaCharting()")
    wait_charts(page)


def view_geometry(page):
    b = page.evaluate("__delta.store.get().chartArea.bounds")
    return ee().Geometry.Rectangle([b["west"], b["south"], b["east"], b["north"]], None, False)


def py_table(obj, geom, d, area_format, is_collection):
    from geeViz.outputLib import charts as cl

    # the viewer leaves masked pixels out unless a layer sets shouldUnmask
    res = cl.summarize_and_chart(
        obj, geom, scale=d["nominalScale"], crs=d["crs"], transform=d["transform"], area_format=area_format, include_masked_area=False
    )
    return df_to_table(res["df"], is_collection)


def assert_tables_equal(js, py):
    assert js["columns"] == py["columns"]
    assert [r["x"] for r in js["rows"]] == [r["x"] for r in py["rows"]]
    for jr, pr in zip(js["rows"], py["rows"]):
        assert len(jr["values"]) == len(pr["values"])
        for jv, pv in zip(jr["values"], pr["values"]):
            assert jv is not None and pv is not None and math.isclose(jv, pv, rel_tol=0, abs_tol=1e-6), (jr["x"], jv, pv)


def test_chart_numbers_equal_python(page):
    chart_view(page)
    lc = result(page, "LCMS Land Cover", "chart")
    nl = result(page, "NLCD 2021", "chart")
    sk = result(page, "LCMS Land Cover", "sankey")
    d = lc["data"]
    # the viewer's inputs: the 30 m CONUS Albers grid at this zoom
    assert d["crs"] == "EPSG:5070" and d["transform"] == [30, 0, -2361915.0, 0, -30, 3177735.0] and d["nominalScale"] == 30
    assert d["areaFormat"] == "Hectares"
    geom = view_geometry(page)
    py = py_table(lcms_collection(), geom, d, "Hectares", True)
    assert [r["x"] for r in d["rows"]] == [str(y) for y in range(2015, 2024)]
    assert_tables_equal(d, py)
    assert_tables_equal(nl["data"], py_table(nlcd_image(), geom, nl["data"], "Hectares", False))
    # % of area: charts.py's Percentage, from the same cached reductions
    page.click("#tool-options .seg[data-k=showas] [data-v=pct]")
    wait_for(page, "__delta.store.get().results.every(r => r.data.areaFormat === 'Percentage')")
    lc = result(page, "LCMS Land Cover", "chart")
    assert_tables_equal(lc["data"], py_table(lcms_collection(), geom, lc["data"], "Percentage", True))
    # the Sankey's links and transition tables equal charts.py's at the viewer's 0.5% minimum
    from geeViz.outputLib import charts as cl

    sk = result(page, "LCMS Land Cover", "sankey")
    res = cl.summarize_and_chart(
        lcms_collection(), geom, chart_type="sankey", transition_periods=PERIODS, min_percentage=0.5,
        scale=d["nominalScale"], crs=d["crs"], transform=d["transform"],
    )
    pys = sankey_to_js(res["df"], res["matrix"])
    assert len(pys["links"]) > 3
    strip = lambda ls: [{k: v for k, v in l.items() if k != "value"} for l in ls]
    assert strip(sk["data"]["links"]) == strip(pys["links"])
    for jl, pl in zip(sk["data"]["links"], pys["links"]):
        assert math.isclose(jl["value"], pl["value"], rel_tol=0, abs_tol=1e-6)
    assert list(sk["data"]["matrix"]) == list(pys["matrix"])
    # the heading says where the charts apply
    assert page.inner_text("#where").startswith("Map view (")


def test_units_and_show_as_rerender_without_ee(page):
    chart_view(page)
    page.wait_for_timeout(1500)
    before = len(page.ee_calls)
    assert before > 0, "the Earth Engine request filter matched nothing"
    lc0 = result(page, "LCMS Land Cover", "chart")
    page.click("#pane-right .units [data-u=imperial]")
    wait_for(page, "__delta.store.get().results.some(r => r.data.areaFormat === 'Acres')")
    lc1 = result(page, "LCMS Land Cover", "chart")
    assert lc1["data"]["yLabel"] == "Acres"
    assert lc1["data"]["rows"] != lc0["data"]["rows"]
    assert "Acres" in page.inner_text("#tool-options .seg[data-k=showas]")
    page.click("#tool-options .seg[data-k=showas] [data-v=pct]")
    wait_for(page, "__delta.store.get().results.every(r => r.data.areaFormat === 'Percentage')")
    page.click("#tool-options .seg[data-k=showas] [data-v=area]")
    page.click("#pane-right .units [data-u=metric]")
    wait_for(page, "__delta.store.get().results.every(r => r.data.areaFormat === 'Hectares')")
    page.wait_for_timeout(2500)
    assert len(page.ee_calls) == before, page.ee_calls[before:]
    assert page.evaluate("__delta.store.get().charting") is False
    # every card still draws
    assert page.locator("#results-mount .card-r").count() == 3


def test_single_image_is_bar(page):
    chart_view(page)
    nl = result(page, "NLCD 2021", "chart")
    assert nl["data"]["isCollection"] is False and nl["data"]["chartType"] == "bar"
    types = page.evaluate(
        """(id) => document.querySelector('#results-mount .card-r[data-rid="' + id + '"] .achart-plot').data.map(t => t.type)""",
        nl["id"],
    )
    assert types == ["bar"]
    lc = result(page, "LCMS Land Cover", "chart")
    n = page.evaluate(
        """(id) => document.querySelector('#results-mount .card-r[data-rid="' + id + '"] .achart-plot').data.map(t => t.type || 'scatter')""",
        lc["id"],
    )
    assert set(n) == {"scatter"} and len(n) == len(lc["data"]["columns"])
    # the legend lists the classes as text
    legend = page.inner_text('#results-mount .card-r[data-rid="%s"] .legend-mini' % lc["id"])
    assert "Trees" in legend


def test_sankey_card_renders(page):
    chart_view(page)
    sk = result(page, "LCMS Land Cover", "sankey")
    card = '#results-mount .card-r[data-rid="%s"]' % sk["id"]
    info = page.evaluate(
        """(sel) => {
          const svg = document.querySelector(sel + ' .sankey-wrap svg');
          const links = [...svg.querySelectorAll('path.link')];
          const grads = links.map(l => /^url\\(#(.+)\\)$/.exec(l.getAttribute('stroke'))[1]);
          return {
            n: links.length,
            gradients: grads.every(id => { const g = svg.querySelector('#' + CSS.escape(id)); return g && g.tagName === 'linearGradient' && g.querySelectorAll('stop').length === 2; }),
            width: svg.getBoundingClientRect().width,
            cardWidth: document.querySelector(sel + ' .sankey-wrap').getBoundingClientRect().width,
            labels: [...svg.querySelectorAll('text.node-label')].map(t => t.textContent),
            cols: [...svg.querySelectorAll('text.col-label')].map(t => t.textContent),
          };
        }""",
        card,
    )
    assert info["n"] == len(sk["data"]["links"]) and info["n"] > 0
    assert info["gradients"]
    assert abs(info["width"] - info["cardWidth"]) < 2  # drawn at the card's width
    assert info["cols"] == ["2016-2018", "2020-2022"]
    assert info["labels"] and all(l in sk["data"]["classNames"] for l in info["labels"])
    # hover the widest link at its middle: the tooltip names source, target and value
    page.locator(card).scroll_into_view_if_needed()
    pt = page.evaluate(
        """(sel) => {
          const links = [...document.querySelectorAll(sel + ' path.link')];
          const l = links.reduce((a, b) => (+a.getAttribute('stroke-width') >= +b.getAttribute('stroke-width') ? a : b));
          const p = l.getPointAtLength(l.getTotalLength() / 2);
          const m = l.getScreenCTM();
          const d = l.__data__;
          return {x: p.x * m.a + p.y * m.c + m.e, y: p.x * m.b + p.y * m.d + m.f, s: d.source.name, t: d.target.name, v: d.value.toLocaleString('en-US', {maximumFractionDigits: 3})};
        }""",
        card,
    )
    page.mouse.move(pt["x"], pt["y"])
    wait_for(page, "document.querySelector('.tip.on') !== null", timeout=5)
    tip = page.inner_text(".tip.on")
    assert pt["s"] in tip and pt["t"] in tip and "→" in tip
    assert pt["v"] + " ha" in tip


def test_stale_chart_results_are_dropped(page):
    page.evaluate("__delta.api.turnOnUserDefinedAreaCharting()")
    # two areas 50 ms apart: only the second one's cards may remain
    page.evaluate(
        """() => {
          const A = ee.Geometry.Rectangle([-111.70, 40.55, -111.62, 40.62], null, false);
          const B = ee.Geometry.Rectangle([-111.60, 40.58, -111.58, 40.60], null, false);
          window.__first = __delta.charter.chartArea(A, 'First area');
          return new Promise(res => setTimeout(() => { window.__second = __delta.charter.chartArea(B, 'Second area'); res(); }, 50));
        }"""
    )
    wait_charts(page)
    page.evaluate("Promise.all([window.__first, window.__second])")
    page.wait_for_timeout(2000)
    rs = results(page)
    keys = {r["data"]["areaKey"] for r in rs}
    labels = {r["data"]["areaLabel"] for r in rs}
    assert labels == {"Second area"}, labels
    assert len(keys) == 1
    assert len(rs) == 3 and len({r["id"] for r in rs}) == 3
    assert page.locator("#results-mount .card-r").count() == 3
    assert page.evaluate("__delta.store.get().where") == "Second area"
    assert page.evaluate("__delta.store.get().chartArea.key") == keys.pop()


def test_upload_geojson_source(page):
    page.evaluate("__delta.api.turnOnUserDefinedAreaCharting()")
    page.click("#tool-options .seg[data-k=src] [data-v=upload]")
    assert page.evaluate("__delta.store.get().areaFrom") == "upload"
    # where uploaded files go is disclosed
    hint = page.inner_text("#tool-options")
    assert ".zip and .kmz files are converted by the ogre.adc4gis.com service" in hint
    assert ".geojson, .json and .kml stay in your browser" in hint
    poly = [[[-111.62, 40.59], [-111.59, 40.59], [-111.59, 40.615], [-111.62, 40.615], [-111.62, 40.59]]]
    gj = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"name": "Test unit"}, "geometry": {"type": "Polygon", "coordinates": poly}}]}
    page.set_input_files("#tool-options input[data-role=area-upload]", files=[{"name": "test unit.geojson", "mimeType": "application/geo+json", "buffer": json.dumps(gj).encode()}])
    wait_for(page, "__delta.store.get().where === 'test unit'")
    wait_charts(page)
    assert page.evaluate("__delta.store.get().chartArea.source") == "upload"
    e = ee()
    # only the geometry goes to Earth Engine (as the page sends it)
    fc = e.FeatureCollection([e.Feature(e.Geometry(f["geometry"])).dissolve(100, e.Projection("EPSG:4326")) for f in gj["features"]])
    nl = result(page, "NLCD 2021", "chart")
    assert_tables_equal(nl["data"], py_table(nlcd_image(), fc.geometry(), nl["data"], "Hectares", False))
    # the heading carries the area's size
    assert "ha" in page.inner_text("#where")


def test_csv_and_png_actions(page):
    chart_view(page)
    lc = result(page, "LCMS Land Cover", "chart")
    sk = result(page, "LCMS Land Cover", "sankey")
    for r, ext in [(lc, "csv"), (lc, "png"), (sk, "csv"), (sk, "png")]:
        card = '#results-mount .card-r[data-rid="%s"]' % r["id"]
        page.locator(card).scroll_into_view_if_needed()
        with page.expect_download(timeout=30000) as dl:
            page.click(card + " [data-act=%s]" % ext)
        path = dl.value.path()
        data = open(path, "rb").read()
        assert len(data) > 100, (r["kind"], ext)
        assert dl.value.suggested_filename.endswith("." + ext)
        if ext == "png":
            assert data[:8] == b"\x89PNG\r\n\x1a\n"
        elif r["kind"] == "chart":
            first = data.decode().splitlines()[0]
            assert first.startswith("Year,") and "Trees" in first
        else:
            assert "2020-2022" in data.decode()
    # expand opens the chart in the modal
    page.click('#results-mount .card-r[data-rid="%s"] [data-act=expand]' % sk["id"])
    wait_for(page, "document.querySelector('dialog.dz-modal[open] .sankey-wrap svg') !== null", timeout=10)
