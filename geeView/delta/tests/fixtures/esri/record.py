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
ZONE = {"x": -105.068, "y": 40.59, "spatialReference": {"wkid": 4326}}
# the Web Mercator bounds of map tile z 4, x 3, y 6
_H = 20037508.342789244
_S = 2 * _H / 16
Z4_TILE = {"xmin": -_H + 3 * _S, "ymin": _H - 7 * _S, "xmax": -_H + 4 * _S, "ymax": _H - 6 * _S,
           "spatialReference": {"wkid": 3857}}
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
    # feature tiles: the zoom 4 tile x 3, y 6 (the West), small pages to page through
    "states_query_z4": (STATES + "/query", {"geometry": Z4_TILE, "geometryType": "esriGeometryEnvelope", "inSR": "3857",
                                            "spatialRel": "esriSpatialRelIntersects", "outSR": "4326",
                                            "outFields": "OBJECTID,STATE_NAME", "where": "1=1",
                                            "maxAllowableOffset": "0.088", "geometryPrecision": "6",
                                            "resultRecordCount": "5", "f": "geojson"}, "GET"),
    "states_query_z4_page2": (STATES + "/query", {"geometry": Z4_TILE, "geometryType": "esriGeometryEnvelope", "inSR": "3857",
                                                  "spatialRel": "esriSpatialRelIntersects", "outSR": "4326",
                                                  "outFields": "OBJECTID,STATE_NAME", "where": "1=1",
                                                  "maxAllowableOffset": "0.088", "geometryPrecision": "6",
                                                  "resultRecordCount": "5", "resultOffset": "5", "f": "geojson"}, "GET"),
    "mtbs63_query": (MTBS63 + "/query", {"geometry": {"xmin": -105.7, "ymin": 40.55, "xmax": -105.6, "ymax": 40.65,
                                                      "spatialReference": {"wkid": 4326}},
                                         "geometryType": "esriGeometryEnvelope", "spatialRel": "esriSpatialRelIntersects",
                                         "outSR": "4326", "outFields": "objectid,fire_name", "where": "year = 2020",
                                         "maxAllowableOffset": "0.0005", "geometryPrecision": "6", "f": "json"}, "GET"),
    "mtbs63_attributes": (MTBS63 + "/query", {"where": "fire_name = 'CAMERON PEAK' AND year = 2020", "outFields": "*",
                                              "returnGeometry": "false", "f": "json"}, "GET"),
    # renderers, as public layers draw them (found by searching ArcGIS Online, 2026-11-24)
    "drawinginfo_unique": ("https://services9.arcgis.com/RHVPKKiFTONKtxq3/arcgis/rest/services/USA_Wildfires_v1/FeatureServer/1",
                           {"f": "json"}, "GET"),
    "drawinginfo_unique_size": ("https://services9.arcgis.com/RHVPKKiFTONKtxq3/arcgis/rest/services/USA_Wildfires_v1/FeatureServer/0",
                                {"f": "json"}, "GET"),
    "drawinginfo_classbreaks": ("https://services.arcgis.com/F7DSX1DSNSiWmOqh/arcgis/rest/services/Carbon_Recovery_After_Wildfire/FeatureServer/0",
                                {"f": "json"}, "GET"),
    "drawinginfo_visualvars": ("https://services.arcgis.com/jIL9msH9OI208GCb/arcgis/rest/services/USA_Wildfire_Hazard_Potential/FeatureServer/0",
                               {"f": "json"}, "GET"),
    "drawinginfo_heatmap": ("https://services1.arcgis.com/0MSEUqKaxRlEPj5g/arcgis/rest/services/Percent_Pop_NY_Tract__Dot_Density__ATD_WFL1/FeatureServer/0",
                            {"f": "json"}, "GET"),
    "drawinginfo_dotdensity": ("https://services1.arcgis.com/0MSEUqKaxRlEPj5g/arcgis/rest/services/South_Florida_Population_Density_Radcliffe/FeatureServer/0",
                               {"f": "json"}, "GET"),
    "drawinginfo_piechart": ("https://services7.arcgis.com/zX8NTiUjIKUVyth8/arcgis/rest/services/Reg_Units_Crop_Centroid/FeatureServer/18",
                             {"f": "json"}, "GET"),
    # identify at Fort Collins, in an 800 by 600 view
    # a zone AE on the Cache la Poudre, zoomed in past layer 28's minScale (1:36,111)
    "nfhl_identify": (NFHL + "/identify", {"geometry": ZONE, "geometryType": "esriGeometryPoint", "sr": "4326",
                                            "layers": "visible:28", "tolerance": "8",
                                            "mapExtent": "-105.08,40.58,-105.056,40.596", "imageDisplay": "800,600,96",
                                            "returnGeometry": "false", "f": "json"}, "GET"),
    "topo_identify": (TOPO + "/identify", {"geometry": FOCO, "geometryType": "esriGeometryPoint", "sr": "4326",
                                           "layers": "visible", "tolerance": "8",
                                           "mapExtent": "-105.2,40.5,-104.96,40.66", "imageDisplay": "800,600,96",
                                           "returnGeometry": "false", "f": "json"}, "GET"),
    "lcms_identify": (LCMS + "/identify", {"geometry": {"x": -105.65, "y": 40.6, "spatialReference": {"wkid": 4326}},
                                           "geometryType": "esriGeometryPoint", "returnGeometry": "false",
                                           "returnCatalogItems": "true", "returnPixelValues": "true", "f": "json"}, "GET"),
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
