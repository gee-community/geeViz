"""The map check nudges thematic layers to autoViz and year series to a time lapse.

Session e4561fe2 (2026-10-22), "make me a map showing the changes in
sugarcane growing areas over time": the agent added four single-year
layers, each a ``.eq(20).selfMask()`` mask drawn with a hand-picked
``{'palette': ['ffd700']}``. Asked for a time lapse, it drew that with
``{'min': 1, 'max': 1, 'palette': ['32cd32']}``. autoViz arrived only when
the user asked for it. The instructions already said thematic data always
gets autoViz; nothing said so while the map was being built.

``testLayers`` (which ``map_control`` runs before showing a map) now warns
when a layer is styled by hand as one class, when an image with class
properties is drawn without autoViz, and when three or more single-year
layers of one series could be one time lapse.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_empty_layer_warning import _ee_ok, _gv, _warnings  # noqa: E402


# --- one class, drawn by hand ------------------------------------------------

@pytest.mark.parametrize("viz", [
    {"palette": ["ffd700"]},
    {"palette": "32cd32"},
    {"min": 1, "max": 1, "palette": ["32cd32"], "canAreaChart": True},
])
def test_a_one_class_style_is_flagged(viz):
    w = _gv()._hand_styled_class_warning(viz)
    assert w and "autoViz" in w and "_class_values" in w


@pytest.mark.parametrize("viz", [
    {"autoViz": True, "canAreaChart": True},
    {"min": 0, "max": 3000, "palette": ["000000", "ffffff"]},
    {"min": 0, "max": 1, "palette": ["ff0000"] * 1 + ["00ff00"]},
    {"bands": "red,green,blue", "min": 0, "max": 0.3},
    {},
])
def test_ordinary_styles_are_not_flagged(viz):
    assert _gv()._hand_styled_class_warning(viz) is None


def test_the_selfmask_case_names_the_unmask_setting():
    assert "shouldUnmask" in _gv()._hand_styled_class_warning({"palette": ["ffd700"]})


# --- single-year series ------------------------------------------------------

SUGARCANE = [
    ("Sugarcane Expansion Eras (1995 - 2023)", False),
    ("Sugarcane Extent (1995)", False),
    ("Sugarcane Extent (2005)", False),
    ("Sugarcane Extent (2015)", False),
    ("Sugarcane Extent (2023)", False),
]


def test_the_sugarcane_years_are_one_series():
    groups = _gv()._year_layer_groups(SUGARCANE)
    assert set(groups) == {n for n, _ in SUGARCANE[1:]}
    assert groups["Sugarcane Extent (1995)"] == ["1995", "2005", "2015", "2023"]


def test_a_range_in_a_name_is_not_a_single_year():
    assert "Sugarcane Expansion Eras (1995 - 2023)" not in _gv()._year_layer_groups(SUGARCANE)


def test_two_years_are_a_comparison_not_a_series():
    assert _gv()._year_layer_groups(SUGARCANE[1:3]) == {}


def test_different_things_in_the_same_years_are_not_grouped():
    layers = [("NDVI 2001", False), ("Fire 2005", False), ("Roads 2010", False)]
    assert _gv()._year_layer_groups(layers) == {}


def test_a_time_lapse_is_never_part_of_a_series():
    layers = [(n, True) for n, _ in SUGARCANE[1:]]
    assert _gv()._year_layer_groups(layers) == {}


def test_the_warning_points_at_add_time_lapse_with_auto_viz():
    w = _gv()._year_layer_warning(["1995", "2005", "2015"])
    assert "Map.addTimeLapse" in w and "'autoViz': True" in w
    assert "1995, 2005, 2015" in w
    assert "without waiting to be asked" in w


# --- wired into testLayers ---------------------------------------------------

needs_ee = pytest.mark.skipif(not _ee_ok(), reason="Earth Engine not initialized")


def _mask(year):
    import ee
    return ee.Image(1).rename("sugarcane").set("system:time_start",
                                               ee.Date.fromYMD(year, 7, 1).millis())


@needs_ee
def test_the_sugarcane_map_gets_both_warnings():
    m = _gv().mapper()
    m.clearMap()
    for y in (1995, 2005, 2015):
        m.addLayer(_mask(y), {"palette": ["ffd700"]}, f"Sugarcane Extent ({y})")
    w = _warnings(m, "Sugarcane Extent (2005)")
    assert any("single class" in x for x in w)
    assert any("Map.addTimeLapse" in x for x in w)


@needs_ee
def test_the_hand_styled_time_lapse_is_flagged():
    import ee
    m = _gv().mapper()
    m.clearMap()
    ic = ee.ImageCollection([_mask(y) for y in (1995, 2005, 2015)])
    m.addTimeLapse(ic, {"min": 1, "max": 1, "palette": ["32cd32"]}, "Sugarcane Timelapse")
    w = _warnings(m, "Sugarcane Timelapse")
    assert any("single class" in x for x in w)
    assert not any("Map.addTimeLapse" in x for x in w)


@needs_ee
def test_an_auto_viz_time_lapse_gets_neither_warning():
    import ee
    m = _gv().mapper()
    m.clearMap()
    ic = ee.ImageCollection([
        _mask(y).set({"sugarcane_class_values": [1], "sugarcane_class_names": ["Sugarcane"],
                      "sugarcane_class_palette": ["32cd32"]})
        for y in (1995, 2005, 2015)])
    m.addTimeLapse(ic, {"autoViz": True, "canAreaChart": True}, "Sugarcane Timelapse")
    w = _warnings(m, "Sugarcane Timelapse")
    assert not any("single class" in x or "Map.addTimeLapse" in x or "autoViz is off" in x
                   for x in w)


@needs_ee
def test_class_properties_without_auto_viz_are_flagged():
    m = _gv().mapper()
    m.clearMap()
    img = _mask(2020).set({"sugarcane_class_values": [1], "sugarcane_class_names": ["Sugarcane"],
                           "sugarcane_class_palette": ["32cd32"]})
    m.addLayer(img, {"min": 0, "max": 1, "palette": ["000000", "32cd32"]}, "Cane")
    assert any("autoViz is off" in x for x in _warnings(m, "Cane"))
