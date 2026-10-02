"""edwLib.query_features takes the geometries an EE workflow has.

Found by a live agent turn ("map the national forests in Utah"): the
agent passed ``utah.geometry()`` (an ee.Geometry) and got "Object of type
Geometry is not JSON serializable"; it then passed the GeoJSON polygon
from ``.bounds().getInfo()`` and got "EDW query error: " with an empty
message -- the polygon became Esri ``rings`` but was still declared
``esriGeometryEnvelope``. Both paths now work; the request is checked
without the network.
"""
import json

import pytest

import geeViz.edwLib as edw

UTAH_BOX = {"type": "Polygon", "coordinates": [[[-114.05, 37.0], [-109.04, 37.0],
                                                [-109.04, 42.0], [-114.05, 42.0],
                                                [-114.05, 37.0]]]}


@pytest.fixture
def sent(monkeypatch):
    box = {}

    def fake_post(url, params):
        box.update(params)
        return {"type": "FeatureCollection", "features": []}
    monkeypatch.setattr(edw, "_post_json", fake_post)
    return box


def test_a_geojson_polygon_is_sent_as_a_polygon(sent):
    edw.query_features("EDW_ForestSystemBoundaries_01", 0, geometry=UTAH_BOX)
    assert sent["geometryType"] == "esriGeometryPolygon"
    assert "rings" in json.loads(sent["geometry"])


class _FakeEEGeometry:
    """Duck type of ee.Geometry: getInfo() returns GeoJSON."""
    def getInfo(self):
        return UTAH_BOX


class _FakeEEFeature:
    def geometry(self):
        return _FakeEEGeometry()

    def getInfo(self):
        raise AssertionError("a Feature is converted via its geometry()")


@pytest.mark.parametrize("obj", [_FakeEEGeometry(), _FakeEEFeature()])
def test_ee_objects_are_converted(sent, obj):
    edw.query_features("EDW_ForestSystemBoundaries_01", 0, geometry=obj)
    assert sent["geometryType"] == "esriGeometryPolygon"
    assert json.loads(sent["geometry"])["rings"] == UTAH_BOX["coordinates"]


def test_a_bbox_string_stays_an_envelope(sent):
    edw.query_features("EDW_ForestSystemBoundaries_01", 0, geometry="-114,37,-109,42")
    assert sent["geometryType"] == "esriGeometryEnvelope"


def test_an_explicit_type_is_kept(sent):
    edw.query_features("X", 0, geometry={"x": -111.9, "y": 40.7},
                       geometry_type="esriGeometryPoint")
    assert sent["geometryType"] == "esriGeometryPoint"


def test_an_empty_error_message_still_says_something(monkeypatch):
    monkeypatch.setattr(edw, "_post_json", lambda url, params: {
        "error": {"code": 400, "message": "", "details": ["Invalid geometry."]}})
    with pytest.raises(RuntimeError, match=r"Invalid geometry\. \(code 400\)"):
        edw.query_features("X", 0, geometry=UTAH_BOX)
