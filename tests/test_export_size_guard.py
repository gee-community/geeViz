"""export_html must refuse a page too large to ever reach the browser.

A map with one ArcGIS Feature Service layer -- 1,619 landtype polygons at
full resolution -- exported to a 70.8 MB HTML file. The agent drops any
artifact over 64 MiB, logged a warning nobody saw, and attached nothing.
The model had been told "Map exported with 8 layer(s)", so it told the
user the map was above; the user saw no map, twice. Even under the
agent's cap, prod serves the page through Cloud Run, which refuses a
response over 32 MiB.

So the size is checked where the page is built, and an oversized export
raises -- which map_control hands straight back to the model as an
error it can act on, instead of a success that never renders.
"""
import json
import os

import pytest


def _mapper():
    # Imported at run time: test_esriLib stubs sys.modules["geeViz.geeView"]
    # during collection, so a module-level import captures the stub.
    import geeViz.geeView as gv

    m = gv.mapper()
    m.idDictList = []
    m.mapCommandList = []
    return m


def _geojson_layer(name, n_bytes):
    """A geoJSONVector layer whose embedded payload is about n_bytes."""
    coords = [[round(-120 + i * 1e-5, 6), 44.0] for i in range(max(4, n_bytes // 24))]
    gj = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {},
         "geometry": {"type": "LineString", "coordinates": coords}}]}
    return {"objectName": "Map", "function": "addLayer",
            "item": json.dumps(gj), "viz": json.dumps({"layerType": "geoJSONVector"}),
            "name": name, "visible": True}


def test_an_oversized_export_raises_and_writes_nothing(tmp_path):
    m = _mapper()
    m.idDictList = [_geojson_layer("Small", 2_000),
                    _geojson_layer("Region 6 Landtype Associations", 3_000_000)]
    out = tmp_path / "map.html"
    with pytest.raises(ValueError) as ei:
        m.export_html(str(out), max_bytes=1_000_000)
    msg = str(ei.value)
    assert not out.exists(), "an oversized page must not be written"
    assert "Region 6 Landtype Associations" in msg, "must name the heavy layer"
    assert "MB" in msg
    # Actionable: tells the caller how to get under the limit.
    assert "where" in msg and "bbox" in msg


def test_a_normal_export_is_unaffected(tmp_path):
    m = _mapper()
    m.idDictList = [_geojson_layer("Small", 2_000)]
    out = tmp_path / "map.html"
    path = m.export_html(str(out), max_bytes=1_000_000)
    assert os.path.exists(path)


def test_the_default_limit_is_below_what_prod_can_serve():
    """Cloud Run refuses a response over 32 MiB, and the agent drops an
    artifact over 64 MiB. The default has to sit below both, or the guard
    lets through exactly the page that silently disappears."""
    import geeViz.geeView as gv

    assert gv._EXPORT_MAX_BYTES_DEFAULT < 32 * 1024 * 1024


def test_the_limit_can_be_set_from_the_environment(tmp_path, monkeypatch):
    m = _mapper()
    m.idDictList = [_geojson_layer("Medium", 300_000)]
    monkeypatch.setenv("GEEVIZ_EXPORT_MAX_MB", "0.1")
    with pytest.raises(ValueError):
        m.export_html(str(tmp_path / "a.html"))
    monkeypatch.setenv("GEEVIZ_EXPORT_MAX_MB", "50")
    assert os.path.exists(m.export_html(str(tmp_path / "b.html")))


def test_zero_disables_the_guard(tmp_path):
    m = _mapper()
    m.idDictList = [_geojson_layer("Big", 300_000)]
    assert os.path.exists(m.export_html(str(tmp_path / "c.html"), max_bytes=0))
