"""A layer whose every pixel is outside its stretch draws as one flat color.

From an askterra prod session (a wildland-urban interface map): Sentinel-2
surface reflectance from ``gil.superSimpleGetS2`` (0-10000) was drawn
with a 0.02-0.25 stretch meant for 0-1 reflectance. Every pixel was above
the max, the layer rendered solid white, ``map_control(export)`` printed
PASS, and the user had to come back with "the Sentinel-2 natural color
isn't showing".

``testLayers`` now warns when nearly every visible pixel in view is above
the stretch max on every displayed band, or below the min.
"""
import pytest

from test_empty_layer_warning import _ee_ok, _gv

AREA = (-95.42, 30.05, -95.38, 30.09)


@pytest.fixture(autouse=True)
def _need_ee():
    if not _ee_ok():
        pytest.skip("Earth Engine not reachable")


def _warnings(img, viz):
    import ee
    m = _gv().mapper()
    m.addLayer(img, viz, "layer")
    m.centerObject(ee.Geometry.Rectangle(list(AREA)))
    row = next(r for r in m.testLayers()["layers"] if r["name"] == "layer")
    assert row["status"] == "ok", row.get("error")
    return [w for w in (row.get("warnings") or []) if "stretch" in w]


def _rgb(value):
    import ee
    return ee.Image.constant([value, value, value]).rename(["red", "green", "blue"])


def test_reflectance_scaled_to_10000_with_a_0_to_1_stretch_warns():
    w = _warnings(_rgb(1500), {"min": 0.02, "max": 0.25, "bands": "red,green,blue"})
    assert w and "above" in w[0]


def test_matching_stretch_is_quiet():
    assert not _warnings(_rgb(1500), {"min": 0, "max": 2000, "bands": ["red", "green", "blue"]})


def test_everything_below_the_min_warns():
    import ee
    w = _warnings(ee.Image.constant(0.1), {"min": 1000, "max": 3000, "palette": ["000000", "ffffff"]})
    assert w and "below" in w[0]


def test_per_band_max_lists_are_honored():
    assert not _warnings(_rgb(1500), {"min": 0, "max": [2000, 2000, 2000], "bands": "red,green,blue"})


def test_a_binary_layer_at_its_max_is_quiet():
    import ee
    assert not _warnings(ee.Image.constant(1).selfMask(), {"min": 1, "max": 1, "palette": ["ff0000"]})
    assert not _warnings(ee.Image.constant(1), {"min": 0, "max": 1, "palette": ["000000", "ff0000"]})


def test_partly_in_range_is_quiet():
    import ee
    lon = ee.Image.pixelLonLat().select("longitude")
    assert not _warnings(lon, {"min": -95.40, "max": -95.30})


def test_one_band_out_of_range_is_a_tint_not_a_flat_color():
    import ee
    img = ee.Image.constant([5000, 500, 500]).rename(["red", "green", "blue"])
    assert not _warnings(img, {"min": 0, "max": 2000, "bands": "red,green,blue"})


def test_autoviz_layers_are_not_checked():
    import ee
    img = ee.Image.constant(5).rename("c").set(
        {"c_class_values": [5], "c_class_names": ["five"], "c_class_palette": ["ff0000"]})
    assert not _warnings(img, {"autoViz": True, "min": 0, "max": 1})


def test_the_warning_reports_the_values_in_view():
    w = _warnings(_rgb(1500), {"min": 0.02, "max": 0.25, "bands": "red,green,blue"})
    assert "values in view: 1500 to 1500" in w[0]


def test_below_the_min_points_at_masking_mostly_zero_data():
    import ee
    w = _warnings(ee.Image.constant(0), {"min": 0.2, "max": 20, "palette": ["ffffff", "0000ff"]})
    assert w and "mask" in w[0]


def test_a_one_color_palette_is_flat_on_purpose():
    import ee
    severe = ee.Image.constant(0.9)
    assert not _warnings(severe, {"min": -0.5, "max": 0.66, "palette": ["ff0000"]})


def test_bounds_the_check_cannot_pair_with_bands_keep_the_empty_check():
    # Three bounds and no "bands": Earth Engine draws the three bands, but
    # the range check cannot pair them client-side and must skip itself
    # rather than fail the shared sample.
    import ee
    m = _gv().mapper()
    masked = _rgb(1500).updateMask(0)
    m.addLayer(masked, {"min": [0, 0, 0], "max": [1, 1, 1]}, "layer")
    m.centerObject(ee.Geometry.Rectangle(list(AREA)))
    row = next(r for r in m.testLayers()["layers"] if r["name"] == "layer")
    assert any("No visible pixels" in x for x in (row.get("warnings") or []))


def test_a_band_shown_three_times_keeps_the_empty_check():
    # Gray RGB from one band is valid for getMapId, but select() refuses
    # the repeated name; that must not take the empty check down with it.
    import ee
    m = _gv().mapper()
    masked = ee.Image.constant(5).rename("elevation").updateMask(0)
    m.addLayer(masked, {"min": 0, "max": 1, "bands": "elevation,elevation,elevation"}, "layer")
    m.centerObject(ee.Geometry.Rectangle(list(AREA)))
    row = next(r for r in m.testLayers()["layers"] if r["name"] == "layer")
    assert row["status"] == "ok", row.get("error")
    assert any("No visible pixels" in x for x in (row.get("warnings") or []))
