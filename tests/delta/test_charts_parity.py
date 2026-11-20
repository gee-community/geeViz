"""Delta's Earth Engine charting equals charts.py for the same inputs.

Each test runs delta/js/engine/charts.js (or sankey.js) in the browser with
the page's Earth Engine client, and charts.summarize_and_chart in this
process, over the same polygon, scale, crs and transform, and compares the
tables: same columns, same labels, numbers to 1e-6.

Needs Earth Engine, the local eeCreds proxy and a network: every test is live.
Run serially (view() rewrites a shared runGeeViz.js).
"""
import math

import pytest

from make_fixtures import df_to_table, sankey_to_js

pytestmark = pytest.mark.live

# Verified against the live catalog (2026-11-18): current LCMS release, the
# NLCD 2021 release's 2021 image (no deprecation), MODIS 061 16-day NDVI.
LCMS = "projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11"
NLCD_2021 = "USGS/NLCD_RELEASES/2021_REL/NLCD/2021"
NDVI = "MODIS/061/MOD13A2"
CRS = "EPSG:5070"
TRANSFORM = [30, 0, -2361915.0, 0, -30, 3177735.0]
SCALE = 30
# A fixed polygon about 3 km on a side near (-111.6, 40.6).
POLY = [[[-111.6177, 40.5865], [-111.5823, 40.5865], [-111.5823, 40.6135], [-111.6177, 40.6135], [-111.6177, 40.5865]]]
# Three periods, so one reduction carries two stacked transition bands.
SANKEY_PERIODS = [[2016, 2018], [2020, 2022], [2023, 2023]]

# The same Earth Engine objects in both clients. The JS strings build them
# from the page's window.ee.
JS_OBJECTS = {
    "lcms": "ee.ImageCollection(%r).filter('study_area==\"CONUS\"').select(['Land_Cover']).filter(ee.Filter.calendarRange(2015, 2023, 'year'))" % LCMS,
    "nlcd": "ee.Image(%r).select(['landcover'])" % NLCD_2021,
    "ndvi": "ee.ImageCollection(%r).filterDate('2019-01-01', '2022-01-01').select(['NDVI'])" % NDVI,
    "lcms_all": "ee.ImageCollection(%r).filter('study_area==\"CONUS\"').select(['Land_Cover'])" % LCMS,
    # 2017 masked over the whole area
    "lcms_masked": "ee.ImageCollection(%r).filter('study_area==\"CONUS\"').select(['Land_Cover']).filter(ee.Filter.calendarRange(2015, 2019, 'year'))"
    ".map((img) => ee.Image(ee.Algorithms.If(ee.Number(img.date().get('year')).eq(2017), img.updateMask(0), img)))" % LCMS,
}


def ee():
    import geeViz.geeView as gv

    return gv.ee


def py_object(key):
    e = ee()
    lcms_all = e.ImageCollection(LCMS).filter('study_area=="CONUS"').select(["Land_Cover"])
    return {
        "lcms": lcms_all.filter(e.Filter.calendarRange(2015, 2023, "year")),
        "nlcd": e.Image(NLCD_2021).select(["landcover"]),
        "ndvi": e.ImageCollection(NDVI).filterDate("2019-01-01", "2022-01-01").select(["NDVI"]),
        "lcms_all": lcms_all,
        "lcms_masked": lcms_all.filter(e.Filter.calendarRange(2015, 2019, "year")).map(
            lambda img: e.Image(e.Algorithms.If(e.Number(img.date().get("year")).eq(2017), img.updateMask(0), img))
        ),
    }[key]


def build(Map):
    Map.setCenter(-111.6, 40.6, 12)


@pytest.fixture
def page(live_map):
    return live_map(build, wait_layers=False)


def js_zonal(page, key):
    return page.evaluate(
        """async ({poly, crs, transform, scale}) => {
          const c = await import('./delta/js/engine/charts.js');
          const obj = %s;
          const geom = ee.Geometry.Polygon(poly);
          const r = await c.zonalStats(obj, geom, {scale, crs, transform});
          return {columns: r.columns, rows: r.rows, labels: r.labels, isHistogram: r.isHistogram,
                  fh: c.reducerName(ee.Reducer.frequencyHistogram())};
        }""" % JS_OBJECTS[key],
        {"poly": POLY, "crs": CRS, "transform": TRANSFORM, "scale": SCALE},
    )


def py_zonal(key):
    from geeViz.outputLib import charts as cl

    obj = py_object(key)
    res = cl.summarize_and_chart(obj, ee().Geometry.Polygon(POLY), scale=SCALE, crs=CRS, transform=TRANSFORM)
    return df_to_table(res["df"], isinstance(obj, ee().ImageCollection))


def assert_tables_equal(js, py):
    assert js["columns"] == py["columns"]
    assert [r["x"] for r in js["rows"]] == [r["x"] for r in py["rows"]]
    for jr, pr in zip(js["rows"], py["rows"]):
        assert len(jr["values"]) == len(pr["values"])
        for jv, pv in zip(jr["values"], pr["values"]):
            if pv is None:
                assert jv is None, (jr["x"], jv)
            else:
                assert jv is not None and math.isclose(jv, pv, rel_tol=0, abs_tol=1e-6), (jr["x"], jv, pv)


def test_lcms_land_cover_collection_matches_charts_py(page):
    js = js_zonal(page, "lcms")
    assert "frequencyHistogram" in js["fh"]
    assert js["isHistogram"] is True
    py = py_zonal("lcms")
    assert js["labels"] == [str(y) for y in range(2015, 2024)]
    assert len(py["columns"]) >= 5
    assert_tables_equal(js, py)


def test_year_masked_over_the_area_is_a_gap_not_zero(page):
    """Through zonalStats (unmask sentinel on): charts.py charts the masked
    year as 0 for every class; Delta charts it as a gap. Every other year,
    including its area totals, is charts.py's."""
    js = js_zonal(page, "lcms_masked")
    py = py_zonal("lcms_masked")
    assert js["labels"] == ["2015", "2016", "2017", "2018", "2019"]
    i = js["labels"].index("2017")
    assert py["rows"][i]["values"] and all(v == 0 for v in py["rows"][i]["values"])
    py["rows"][i]["values"] = [None] * len(py["columns"])
    assert all(v is not None for r in js["rows"] if r["x"] != "2017" for v in r["values"])
    assert_tables_equal(js, py)


def test_nlcd_single_image_matches_charts_py(page):
    js = js_zonal(page, "nlcd")
    py = py_zonal("nlcd")
    assert js["isHistogram"] is True
    assert [r["x"] for r in js["rows"]] == [None]
    assert_tables_equal(js, py)


def test_ndvi_collection_mean_matches_charts_py(page):
    js = js_zonal(page, "ndvi")
    py = py_zonal("ndvi")
    assert js["isHistogram"] is False
    assert js["columns"] == ["NDVI"]
    assert js["labels"] == ["2019", "2020", "2021"]
    assert_tables_equal(js, py)


def test_lcms_sankey_matches_charts_py(page):
    from geeViz.outputLib import charts as cl

    js = page.evaluate(
        """async ({poly, crs, transform, scale, periods}) => {
          const s = await import('./delta/js/engine/sankey.js');
          const ic = %s;
          const r = await s.sankeyForCollection(ic, ee.Geometry.Polygon(poly), periods,
              {scale, crs, transform, minPercentage: 0.5});
          return {links: r.links, matrix: r.matrix, bands: Object.keys(r.raw)};
        }""" % JS_OBJECTS["lcms_all"],
        {"poly": POLY, "crs": CRS, "transform": TRANSFORM, "scale": SCALE, "periods": SANKEY_PERIODS},
    )
    # every pair in one reduction: the raw dict has one band per pair
    assert js["bands"] == ["2016-2018---2020-2022", "2020-2022---2023"]
    res = cl.summarize_and_chart(
        py_object("lcms_all"), ee().Geometry.Polygon(POLY), chart_type="sankey",
        transition_periods=SANKEY_PERIODS, min_percentage=0.5, scale=SCALE, crs=CRS, transform=TRANSFORM,
    )
    py = sankey_to_js(res["df"], res["matrix"])
    assert len(py["links"]) > 3
    assert [{k: v for k, v in l.items() if k != "value"} for l in js["links"]] == [
        {k: v for k, v in l.items() if k != "value"} for l in py["links"]
    ]
    for jl, pl in zip(js["links"], py["links"]):
        assert math.isclose(jl["value"], pl["value"], rel_tol=0, abs_tol=1e-6)
    assert list(js["matrix"]) == list(py["matrix"])
    for key, pm in py["matrix"].items():
        jm = js["matrix"][key]
        assert jm["index"] == pm["index"] and jm["columns"] == pm["columns"]
        for jr, pr in zip(jm["values"], pm["values"]):
            assert all(math.isclose(a, b, rel_tol=0, abs_tol=1e-6) for a, b in zip(jr, pr))
