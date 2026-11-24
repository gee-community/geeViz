"""Record real ArcGIS REST responses for Delta's Esri plug-in tests.

Each fixture is <name>.json: {"request": {"url", "params", "method"},
"response": <the service's JSON>}. Tests read them through a fake fetch;
never edit one by hand, rerun this instead:

    venv/Scripts/python.exe geeViz/geeView/delta/tests/fixtures/esri/record.py [name ...]

With names, only those fixtures are recorded. Standard library only.
"""
import json
import os
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

NFHL = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer"
TOPO = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer"
LCMS = "https://imagery.geoplatform.gov/iipp/rest/services/Vegetation/USFS_EDW_LCMS_AnnualChange_CONUS/ImageServer"
MTBS63 = "https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_MTBS_01/MapServer/63"
STATES = "https://services.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services/USA_States_Generalized_Boundaries/FeatureServer/0"
CITIES = "https://services.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services/USA_Major_Cities_/FeatureServer/0"
RIVERS = "https://services.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services/USA_Rivers_and_Streams/FeatureServer/0"
DEP3 = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer"

# Fort Collins, Colorado, and a square around Cameron Peak
FOCO = {"x": -105.08, "y": 40.58, "spatialReference": {"wkid": 4326}}
SQUARE = {"rings": [[[-105.7, 40.55], [-105.7, 40.65], [-105.6, 40.65], [-105.6, 40.55], [-105.7, 40.55]]],
          "spatialReference": {"wkid": 4326}}

# name -> (url, params, method)
FIXTURES = {
    "nfhl_info": (NFHL, {"f": "json"}, "GET"),
    "nfhl_legend": (NFHL + "/legend", {"f": "json"}, "GET"),
    "topo_info": (TOPO, {"f": "json"}, "GET"),
    "lcms_info": (LCMS, {"f": "json"}, "GET"),
    "lcms_legend": (LCMS + "/legend", {"f": "json"}, "GET"),
    "lcms_catalog_years": (LCMS + "/query", {"where": "1=1", "outFields": "year", "returnDistinctValues": "true",
                                             "returnGeometry": "false", "orderByFields": "year", "f": "json"}, "GET"),
    "mtbs63_info": (MTBS63, {"f": "json"}, "GET"),
    "states_info": (STATES, {"f": "json"}, "GET"),
    "error_body": (STATES.rsplit("/", 1)[0] + "/999/query", {"where": "1=1", "f": "json"}, "GET"),
    "esri_point": (CITIES + "/query", {"where": "1=1", "outFields": "NAME", "resultRecordCount": "1",
                                       "outSR": "4326", "f": "json"}, "GET"),
    "esri_polyline": (RIVERS + "/query", {"where": "1=1", "outFields": "*", "resultRecordCount": "1",
                                          "outSR": "4326", "maxAllowableOffset": "0.01", "f": "json"}, "GET"),
    "esri_polygon": (STATES + "/query", {"where": "STATE_ABBR='HI'", "outFields": "STATE_NAME",
                                         "outSR": "4326", "maxAllowableOffset": "0.05", "f": "json"}, "GET"),
}


def fetch(url, params, method):
    data = urllib.parse.urlencode(params)
    if method == "POST":
        req = urllib.request.Request(url, data=data.encode(), method="POST",
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
    else:
        req = urllib.request.Request(url + "?" + data)
    req.add_header("User-Agent", "geeViz-delta-fixtures")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def record(name):
    url, params, method = FIXTURES[name]
    params = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in params.items()}
    out = {"request": {"url": url, "params": params, "method": method}, "response": fetch(url, params, method)}
    with open(os.path.join(HERE, name + ".json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=1)
    print(name, "ok", len(json.dumps(out["response"])), "bytes")


if __name__ == "__main__":
    for n in sys.argv[1:] or list(FIXTURES):
        record(n)
