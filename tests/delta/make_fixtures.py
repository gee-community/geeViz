"""Fixtures for Delta's charts.py ports (delta/js/engine/charts.js, sankey.js).

Run from C:\\RCR\\geeVizBuilder:

    python geeViz/tests/delta/make_fixtures.py            # recompute outputs, no Earth Engine
    python geeViz/tests/delta/make_fixtures.py --record   # also re-record raw reductions (needs Earth Engine)

Each fixture stores the raw reduction dict exactly as charts.py received it
from getInfo (Earth Engine's key order), the inputs, and what charts.py's
own functions return for them. The Node tests feed the same raw dicts to the
JavaScript ports and compare, so they need no Earth Engine.

--record captures the raw dicts by wrapping charts.reduce_region while
charts.summarize_and_chart runs, so the recorded dicts are the ones the real
composition (filterBounds, unmask sentinel, mosaic per label, toBands and
rename) reduced; it also stores summarize_and_chart's numeric outputs.
"""

import json
import math
import pathlib
import random
import sys

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"

LCMS = "projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11"
NLCD_2021 = "USGS/NLCD_RELEASES/2021_REL/NLCD/2021"
NDVI = "MODIS/061/MOD13A2"
CRS = "EPSG:5070"
TRANSFORM = [30, 0, -2361915.0, 0, -30, 3177735.0]
SCALE = 30
CENTER = [-111.6, 40.6]
SANKEY_PERIODS = [[2016, 2018], [2020, 2022]]
AREA_FORMATS = ["Percentage", "Hectares", "Acres", "Pixels"]


def _charts():
    from geeViz.outputLib import charts

    return charts


def _num(v):
    if v is None:
        return None
    try:
        if isinstance(v, float) and math.isnan(v):
            return None
    except TypeError:
        pass
    if hasattr(v, "item"):
        v = v.item()
        if isinstance(v, float) and math.isnan(v):
            return None
    return v


def df_to_table(df, has_labels):
    """DataFrame -> the JS ports' {columns, rows} shape."""
    rows = []
    for i, idx in enumerate(df.index):
        rows.append({"x": str(idx) if has_labels else None, "values": [_num(v) for v in df.iloc[i].tolist()]})
    return {"columns": [str(c) for c in df.columns], "rows": rows}


def obj_info_to_js(info):
    return {
        "objType": info["obj_type"],
        "bandNames": list(info["band_names"]),
        "isThematic": info["is_thematic"],
        "classInfo": {
            bn: {
                "classValues": ci["class_values"],
                "classNames": ci["class_names"],
                "classPalette": ci["class_palette"],
            }
            for bn, ci in info["class_info"].items()
        },
        "size": info["size"],
    }


def sankey_to_js(sankey_df, matrix_dict):
    links = [{k: _num(v) for k, v in rec.items()} for rec in sankey_df.to_dict("records")]
    matrix = {
        key: {
            "index": [str(i) for i in mdf.index],
            "columns": [str(c) for c in mdf.columns],
            "values": [[_num(v) for v in r] for r in mdf.values.tolist()],
        }
        for key, mdf in matrix_dict.items()
    }
    return {"links": links, "matrix": matrix}


def strip_sentinel(df):
    # the same rule as zonal_stats._strip_sentinel_cols (include_masked_area=True)
    drop = [c for c in df.columns if str(c).strip() in ("0", "0.0")]
    return df.drop(columns=drop) if drop else df


###########################################################################
# Outputs from stored raw dicts (no Earth Engine)
###########################################################################


def thematic_outputs(fx):
    cl = _charts()
    info = fx["objInfoPy"]
    out = {}
    for scale in fx.get("scales", [SCALE]):
        for af in AREA_FORMATS:
            df = cl.parse_thematic_results(fx["raw"], info, fx["labels"], af, scale)
            if fx.get("stripSentinel", True):
                df = strip_sentinel(df)
            out[f"{af}@{scale}"] = df_to_table(df, bool(fx["labels"]))
    return out


def continuous_outputs(fx):
    cl = _charts()
    df = cl.parse_continuous_results(fx["raw"], fx["objInfoPy"], fx["labels"])
    return df_to_table(df, bool(fx["labels"]))


def sankey_outputs(fx):
    """prepare_sankey_data's parse half, fed the stored histogram.

    prepare_sankey_data builds its images and calls reduce_region; replacing
    reduce_region with one that returns the stored dict runs charts.py's own
    parsing code on it, with no Earth Engine call.
    """
    cl = _charts()
    out = {}
    orig = cl.reduce_region
    cl.reduce_region = lambda *a, **k: fx["raw"]
    try:
        import ee

        fake_ic = _FakeCollection(ee)
        for af in ["Percentage", "Hectares", "Acres", "Pixels"]:
            for mp in fx["minPercentages"]:
                sdf, mdict = cl.prepare_sankey_data(
                    fake_ic,
                    fx["band"],
                    fx["periods"],
                    fx["classInfoPy"],
                    _FakeGeometry(ee),
                    scale=fx["scale"],
                    area_format=af,
                    min_percentage=mp,
                )
                out[f"{af}@{mp}"] = sankey_to_js(sdf, mdict)
    finally:
        cl.reduce_region = orig
    return out


class _FakeImage:
    def __getattr__(self, name):
        return lambda *a, **k: self


class _FakeCollection:
    """Enough of an ee.ImageCollection for prepare_sankey_data's image
    building, which only chains calls; nothing is sent to Earth Engine."""

    def __init__(self, ee):
        self.ee = ee

    def filterBounds(self, g):
        return self

    def filter(self, f):
        return self

    def select(self, b):
        return self

    def mode(self):
        return _FakeImage()


class _FakeGeometry:
    def __init__(self, ee):
        pass


def _patch_ee_for_fakes():
    import ee

    ee.Filter.calendarRange = staticmethod(lambda *a, **k: None)
    _charts().detect_geometry_type = lambda g: ("single", g)


###########################################################################
# Synthetic fixtures
###########################################################################


def ee_sorted(d):
    """A dict with keys in Earth Engine's order (sorted as strings), nested."""
    if isinstance(d, dict):
        return {k: ee_sorted(d[k]) for k in sorted(d)}
    return d


def synthetic_missing_year():
    names = ["Trees", "Shrubs", "Barren"]
    raw = {
        "2002----Land_Cover": {"1": 120.5, "3": 30, "5": 49.5},
        # 2003 absent: no data for that year in this area
        "2004----Land_Cover": {"1": 100, "3": 60.25, "5": 39.75},
        "2005----Land_Cover": {"1": 80, "3": 70},
    }
    info = {
        "obj_type": "ImageCollection",
        "band_names": ["Land_Cover"],
        "is_thematic": True,
        "class_info": {"Land_Cover": {"class_values": [1, 3, 5], "class_names": names, "class_palette": ["004e2b", "f4ae38", "b3a397"]}},
        "size": 4,
    }
    return {"name": "missing_year", "kind": "thematic", "raw": raw, "objInfoPy": info, "labels": ["2002", "2003", "2004", "2005"], "scales": [30, 60], "stripSentinel": True}


def synthetic_multiband():
    raw = {
        "2020----Change": {"0": 5, "1": 90.5, "3": 4.5},
        "2020----Land_Use": {"0": 5, "1": 60, "2": 35, "10": 0.25},
        "2021----Change": {"1": 91, "2": 2},
        "2021----Land_Use": None,
    }
    info = {
        "obj_type": "ImageCollection",
        "band_names": ["Change", "Land_Use"],
        "is_thematic": True,
        "class_info": {
            "Change": {"class_values": [1, 2, 3], "class_names": ["Stable", "Slow Loss", "Fast Loss"], "class_palette": ["3d4551", "f39268", "d54309"]},
            "Land_Use": {"class_values": [1, 2], "class_names": ["Agriculture", "Developed"], "class_palette": ["fbff97", "e6558b"]},
        },
        "size": 2,
    }
    return {"name": "multiband", "kind": "thematic", "raw": raw, "objInfoPy": info, "labels": ["2020", "2021"], "scales": [30], "stripSentinel": True}


def synthetic_image_unknown_classes():
    # single image; a value with no class name keeps its raw value as the column
    raw = {"landcover": {"11": 10, "41": 70.5, "42": 19.5, "99": 1}}
    info = {
        "obj_type": "Image",
        "band_names": ["landcover"],
        "is_thematic": True,
        "class_info": {"landcover": {"class_values": [11, 41, 42], "class_names": ["Open Water", "Deciduous Forest", "Evergreen Forest"], "class_palette": ["466b9f", "68ab5f", "1c5f2c"]}},
        "size": 1,
    }
    return {"name": "image_unknown_classes", "kind": "thematic", "raw": raw, "objInfoPy": info, "labels": [], "scales": [30, 120], "stripSentinel": True}


def synthetic_multi_output():
    raw = {
        "2019----NDVI_p5": 0.1,
        "2019----NDVI_p50": 0.45,
        "2019----NDVI_p95": 0.8,
        "2019----EVI": 0.3,
        "2020----NDVI_p5": None,
        "2020----NDVI_p50": 0.5,
        "2020----NDVI_p95": 0.85,
        "2020----EVI": 0.31,
    }
    info = {"obj_type": "ImageCollection", "band_names": ["NDVI", "EVI"], "is_thematic": False, "class_info": {}, "size": 2}
    return {"name": "multi_output", "kind": "continuous", "raw": raw, "objInfoPy": info, "labels": ["2019", "2020", "2021"]}


def synthetic_sankey():
    # classes 1, 2, 3; two transitions; one flow under 0.5% and one value
    # outside the class list (skipped by charts.py)
    def enc(f, t):
        return str(f * 10000 + 9900 + t)

    raw = {
        "2016-2018---2020-2022": {enc(1, 1): 700, enc(1, 2): 3, enc(2, 2): 200.5, enc(3, 1): 96.5, enc(9, 1): 4},
        # 2 -> 3 is exactly 0.5% (5 of 1000): kept at a 0.5 minimum (>=)
        "2020-2022---2023": {enc(1, 1): 600, enc(2, 3): 5, enc(3, 3): 395},
    }
    class_info = {"Land_Cover": {"class_values": [1, 2, 3], "class_names": ["Trees", "Shrubs", "Barren"], "class_palette": ["004e2b", "#f4ae38", "b3a397"]}}
    return {
        "name": "sankey_synthetic",
        "kind": "sankey",
        "raw": raw,
        "band": "Land_Cover",
        "periods": [[2016, 2018], [2020, 2022], 2023],
        "classInfoPy": class_info,
        "scale": 30,
        "minPercentages": [0.5, 0.2, 0],
    }


def pyfuncs():
    cl = _charts()
    rng = random.Random(7)
    round_cases = [0.125, 0.375, 2.675, 0.5, 1.5, 2.5, -0.125, -2.5, 1.005, 12.345, 57.925, 0.0, 99.995, 1e-7, 33.33333333333333]
    for _ in range(400):
        round_cases.append(rng.random() * 10 ** rng.randint(-3, 5))
        round_cases.append(rng.randint(0, 100000) / 1000)
        round_cases.append(rng.randint(0, 20000) / 200)
    rounds = [[x, n, round(x, n)] for x in round_cases for n in (0, 2)]
    sums = []
    for _ in range(400):
        vals = []
        for _ in range(rng.randint(0, 14)):
            if rng.random() < 0.4:
                vals.append(rng.randint(0, 10 ** rng.randint(0, 7)))
            else:
                vals.append(rng.random() * 10 ** rng.randint(-2, 7))
        sums.append([vals, sum(vals)])
    names = ["Trees", "Tall Shrubs & Trees Mix (AK Only)", "Grass/Forb/Herb & Shrubs Mix", "x" * 31, "abcdefghij", ""]
    truncs = [[n, m, cl.truncate_class_name(n, m)] for n in names for m in (30, 10, 4, 3, 2, 0, None)]
    norm = [[v, a, cl._normalize_class_prop(v, as_int=a)] for v, a in [
        ("1,2,3", True), ("1, 2 ,3,", True), ("1.5,abc,7", True), ("Trees,Shrubs & Trees Mix", False),
        ([1, 2.0, 3], True), (["a", "b"], False), ("", True), (None, False), (5, True),
    ]]
    return {"name": "pyfuncs", "kind": "pyfuncs", "round": rounds, "sum": sums, "truncate": truncs, "normalize": norm}


###########################################################################
# Recording (Earth Engine)
###########################################################################


def _record():
    import geeViz.geeView as gv

    ee = gv.ee
    cl = _charts()
    geom = ee.Geometry.Point(CENTER).buffer(1500).bounds()
    captured = []
    orig_reduce = cl.reduce_region
    orig_prep = cl.prepare_for_reduction
    orig_info = cl.get_obj_info

    def rec_reduce(*a, **k):
        r = orig_reduce(*a, **k)
        captured.append(("raw", r))
        return r

    def rec_prep(*a, **k):
        r = orig_prep(*a, **k)
        captured.append(("prep", r))
        return r

    def rec_info(*a, **k):
        r = orig_info(*a, **k)
        obj = a[0]
        first = ee.Image(obj.first()) if isinstance(obj, ee.ImageCollection) else ee.Image(obj)
        captured.append(("info", r, first.toDictionary().getInfo()))
        return r

    cl.reduce_region, cl.prepare_for_reduction, cl.get_obj_info = rec_reduce, rec_prep, rec_info
    lcms = ee.ImageCollection(LCMS).filter('study_area=="CONUS"').select(["Land_Cover"])
    cases = {
        "lcms_land_cover": dict(obj=lcms.filter(ee.Filter.calendarRange(2015, 2023, "year")), kw={}),
        "nlcd_2021": dict(obj=ee.Image(NLCD_2021).select(["landcover"]), kw={}),
        "ndvi_mean": dict(obj=ee.ImageCollection(NDVI).filterDate("2019-01-01", "2022-01-01").select(["NDVI"]), kw={}),
        "lcms_sankey": dict(obj=lcms, kw={"chart_type": "sankey", "transition_periods": SANKEY_PERIODS, "min_percentage": 0.5}),
    }
    out = {}
    try:
        for name, c in cases.items():
            captured.clear()
            res = cl.summarize_and_chart(c["obj"], geom, scale=SCALE, crs=CRS, transform=TRANSFORM, **c["kw"])
            raws = [x[1] for x in captured if x[0] == "raw"]
            infos = [x for x in captured if x[0] == "info"]
            preps = [x[1] for x in captured if x[0] == "prep"]
            assert len(raws) == 1, (name, len(raws))
            info_py, props = infos[-1][1], infos[-1][2]
            fx = {"name": name, "raw": raws[0], "objInfoPy": info_py, "props": props, "objInfo": obj_info_to_js(info_py)}
            if name == "lcms_sankey":
                fx.update(kind="sankey", band="Land_Cover", periods=SANKEY_PERIODS, classInfoPy=info_py["class_info"], scale=SCALE, minPercentages=[0.5, 0.2])
                fx["summarize"] = sankey_to_js(res["df"], res["matrix"])
            else:
                _, bands, labels = preps[-1]
                fx.update(labels=list(labels), stackBandNames=list(bands), scales=[SCALE, 60])
                fx["kind"] = "thematic" if info_py["is_thematic"] else "continuous"
                fx["summarize"] = df_to_table(res["df"], bool(labels))
            out[name] = fx
    finally:
        cl.reduce_region, cl.prepare_for_reduction, cl.get_obj_info = orig_reduce, orig_prep, orig_info
    return out


def build(record=False):
    FIXTURES.mkdir(exist_ok=True)
    live = {}
    if record:
        live = _record()
    else:
        for name in ["lcms_land_cover", "nlcd_2021", "ndvi_mean", "lcms_sankey"]:
            p = FIXTURES / f"{name}.json"
            if p.exists():
                live[name] = json.loads(p.read_text(encoding="utf-8"))
    _patch_ee_for_fakes()
    cl = _charts()
    fixtures = list(live.values()) + [synthetic_missing_year(), synthetic_multiband(), synthetic_image_unknown_classes(), synthetic_multi_output(), synthetic_sankey()]
    for fx in fixtures:
        # synthetic dicts get Earth Engine's key order; recorded ones have it
        fx["raw"] = ee_sorted(fx["raw"])
        if fx["kind"] == "thematic":
            fx["objInfo"] = obj_info_to_js(fx["objInfoPy"])
            fx["expected"] = thematic_outputs(fx)
        elif fx["kind"] == "continuous":
            fx["objInfo"] = obj_info_to_js(fx["objInfoPy"])
            fx["expected"] = continuous_outputs(fx)
        elif fx["kind"] == "sankey":
            fx["expected"] = sankey_outputs(fx)
        if fx["kind"] != "sankey" and "stackBandNames" not in fx and fx["labels"]:
            # charts.prepare_for_reduction's expected_names loop (label-major, band-minor)
            fx["stackBandNames"] = [f"{x}{cl.SPLIT_STR}{b}" for x in fx["labels"] for b in fx["objInfoPy"]["band_names"]]
        (FIXTURES / f"{fx['name']}.json").write_text(json.dumps(fx, indent=1, ensure_ascii=False), encoding="utf-8")
    pf = pyfuncs()
    (FIXTURES / "pyfuncs.json").write_text(json.dumps(pf, indent=1, ensure_ascii=False), encoding="utf-8")
    print("wrote", len(fixtures) + 1, "fixtures to", FIXTURES)


if __name__ == "__main__":
    build(record="--record" in sys.argv)
