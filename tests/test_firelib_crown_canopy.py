"""Crown-fire initiation needs a canopy to initiate into.

From an askterra prod session (fire behavior across a national forest):
``crown_fire_initiation`` compared flame length with canopy base height
and nothing else. LANDFIRE codes "no canopy" as canopy cover 0, and often
as canopy base height 0, so every grass and grass-shrub pixel "torched".
The answer reported torching across ~90% of a forest that is ~64% grass
and grass-shrub; about a quarter of the flagged acres had no canopy.
"""
import pytest

from test_empty_layer_warning import _ee_ok


def _crown(cbh, cc=None, flame_ft=20.0):
    import ee
    from geeViz.fireLib import behavior

    fuels = ee.Image.constant(cbh).rename("CBH")
    if cc is not None:
        fuels = fuels.addBands(ee.Image.constant(cc).rename("CC"))
    out = behavior.crown_fire_initiation(fuels, ee.Image.constant(flame_ft))
    return out.reduceRegion(
        ee.Reducer.first(), ee.Geometry.Point([-111.6, 35.2]), 30
    ).get("crown_initiation").getInfo()


@pytest.fixture(autouse=True)
def _need_ee():
    if not _ee_ok():
        pytest.skip("Earth Engine not reachable")


def test_no_canopy_cover_never_torches_even_with_a_base_height():
    # A grass pixel can carry a nonzero CBH in LANDFIRE while CC is 0.
    assert _crown(cbh=30, cc=0) == 0


def test_zero_base_height_is_no_canopy_not_a_canopy_at_the_ground():
    assert _crown(cbh=0, cc=0) == 0
    assert _crown(cbh=0, cc=40) == 0


def test_flames_above_a_low_canopy_base_torch():
    # CBH 30 = 3.0 m = 9.8 ft, below 20 ft flames.
    assert _crown(cbh=30, cc=40) == 1


def test_flames_below_a_high_canopy_base_do_not_torch():
    # CBH 100 = 10 m = 32.8 ft, above 20 ft flames.
    assert _crown(cbh=100, cc=40) == 0


def test_fuels_without_a_canopy_cover_band_still_work():
    assert _crown(cbh=30) == 1
    assert _crown(cbh=0) == 0
