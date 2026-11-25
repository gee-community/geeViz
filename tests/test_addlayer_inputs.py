"""Map.addLayer and Map.addTimeLapse take anything: ArcGIS URLs, tile URLs,
GeoJSON (a URL, text or a dict), Earth Engine asset ids and objects. The
same detection as georest.view (georest.view._inputs).

Needs Earth Engine for the ee objects; asset lookups are stubbed.
"""
import json

import pytest

import geeViz.geeView as gv
from georest.view._document import validate

ee = gv.ee
NFHL = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer"
LANDSAT = "https://landsat2.arcgis.com/arcgis/rest/services/Landsat/MS/ImageServer"
FS = "https://services.arcgis.com/x/arcgis/rest/services/fires/FeatureServer/0"
XYZ = "https://basemap.nationalmap.gov/arcgis/rest/services/USGSHydroCached/MapServer/tile/{z}/{y}/{x}"
GJ_URL = "https://example.com/data/parks.geojson"
POINT = {"type": "Feature", "properties": {"n": 1}, "geometry": {"type": "Point", "coordinates": [-105, 40]}}


@pytest.fixture
def m():
    m = gv.mapper()
    m.setSkin("delta")
    return m


@pytest.fixture
def assets(monkeypatch):
    types = {"USGS/SRTMGL1_003": "IMAGE", "USGS/NLCD_RELEASES/2021_REL/NLCD": "IMAGE_COLLECTION",
             "TIGER/2018/States": "TABLE", "projects/x/assets/folder": "FOLDER"}

    def get_asset(asset_id):
        if asset_id not in types:
            raise ee.EEException("Asset not found")
        return {"type": types[asset_id], "name": asset_id}
    monkeypatch.setattr(ee.data, "getAsset", get_asset)
    return types


def doc(m):
    return validate(m._build_document())


def test_addLayer_takes_urls_and_geojson(m):
    m.addLayer(NFHL, {"layers": "show:28"}, "Flood")
    m.addLayer(FS, {"where": "acres > 100", "maxFeatures": 500}, "Fires")
    m.addLayer(LANDSAT, {"reducer": ee.Reducer.max(), "time": ("2020-07-01", "2020-09-30")}, "Landsat max")
    m.addLayer(XYZ, {"classLegendDict": {"Water": "#0000ff"}, "maxZoom": 16}, "Hydro")
    m.addLayer(GJ_URL, {"strokeColor": "00aa00"}, "Parks")
    m.addLayer(json.dumps(POINT), {}, "Text point")
    d = doc(m)
    assert [(l["type"], l["name"]) for l in d["layers"]] == [
        ("esri.map", "Flood"), ("esri.feature", "Fires"), ("esri.image", "Landsat max"), ("xyz", "Hydro"),
        ("geojson", "Parks"), ("geojson", "Text point")]
    flood, fires, landsat, hydro, parks, text = d["layers"]
    assert flood["source"]["options"]["layers"] == "show:28"
    assert fires["source"]["options"]["where"] == "acres > 100" and fires["source"]["options"]["maxFeatures"] == 500
    assert landsat["source"]["options"]["mosaicRule"] == {"mosaicMethod": "esriMosaicNone", "mosaicOperation": "MT_MAX"}
    assert len(landsat["source"]["options"]["time"]) == 2
    assert hydro["source"] == {"url": XYZ, "maxZoom": 16}
    assert hydro["viz"]["classLegendDict"] == {"Water": "0000ff"}
    assert parks["source"] == {"url": GJ_URL}
    assert text["source"]["geojson"] == POINT


def test_addLayer_takes_asset_ids(m, assets):
    m.addLayer("USGS/SRTMGL1_003", {"min": 0, "max": 3000}, "SRTM")
    m.addLayer("USGS/NLCD_RELEASES/2021_REL/NLCD", {}, "NLCD")
    m.addLayer("TIGER/2018/States", {}, "States")
    d = doc(m)
    assert [l["type"] for l in d["layers"]] == ["ee.image", "ee.imageCollection", "ee.vectorImage"]  # a table draws as an ee.FeatureCollection does
    assert "USGS/SRTMGL1_003" in json.dumps(d["layers"][0]["source"])
    assert "TIGER/2018/States" in json.dumps(d["layers"][2]["source"])


def test_an_asset_that_is_not_a_layer_is_named(m, assets):
    with pytest.raises(ValueError, match="FOLDER"):
        m.addLayer("projects/x/assets/folder", {}, "F")
    with pytest.raises(ValueError, match="not found|could not be read"):
        m.addLayer("projects/x/assets/missing", {}, "M")


def test_earth_engine_objects_are_unchanged(m):
    m.addLayer(ee.Image(1), {"min": 0, "max": 1}, "One")
    assert doc(m)["layers"][0]["type"] == "ee.image"


def test_addTimeLapse_takes_asset_ids_and_services(m, assets):
    m.addTimeLapse("USGS/NLCD_RELEASES/2021_REL/NLCD", {}, "NLCD frames")
    m.addTimeLapse(LANDSAT, {"reducer": "max"}, "Landsat frames")
    d = doc(m)
    assert [l["type"] for l in d["layers"]] == ["ee.timelapse", "esri.timelapse"]
    assert d["layers"][1]["source"]["options"]["mosaicRule"]["mosaicOperation"] == "MT_MAX"
    with pytest.raises(ValueError, match="IMAGE"):
        m.addTimeLapse("USGS/SRTMGL1_003", {}, "Not a collection")


def test_an_unknown_string_names_what_is_accepted(m):
    with pytest.raises(ValueError, match="ArcGIS service URL.*tile URL.*GeoJSON"):
        m.addLayer("https://example.com/page.html", {}, "Page")


def test_a_geojson_url_needs_the_delta_skin():
    o = gv.mapper()
    o.setSkin("original")
    with pytest.raises(ValueError, match="Delta"):
        o.addLayer(GJ_URL, {}, "Parks")


def test_the_docs_send_time_series_to_addTimeLapse():
    doc_ = gv.mapper.addLayer.__doc__
    assert "addTimeLapse" in doc_ and "time-enabled" in doc_
    assert "reducer" in gv.mapper.addTimeLapse.__doc__


def test_addLayer_keeps_visible_for_every_service_kind(m):
    for url in (NFHL, FS, LANDSAT, XYZ, GJ_URL):
        m.addLayer(url, {}, url[-12:], visible=False)
    assert [l["visible"] for l in doc(m)["layers"]] == [False] * 5
