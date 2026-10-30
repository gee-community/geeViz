"""getBuildings drops footprints drawn inside out.

Session da1c39ec (2026-10-29), a tree-scale wildfire-risk map from building
footprints: the buildings, painted to a mask, covered every pixel, so every
tree came out as touching a house. The VIDA US collection holds footprints
whose rings wind the wrong way. Earth Engine reads each one as the whole
Earth minus a building (about 5.1e14 m2), so ``filterBounds`` returns them
for any area anywhere. Around one point in Texas, 29 of the 34 footprints
returned were these, belonging to buildings in another state.

``getBuildings`` now drops any footprint larger than a building could be.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_empty_layer_warning import _ee_ok  # noqa: E402

needs_ee = pytest.mark.skipif(not _ee_ok(), reason="Earth Engine not initialized")

TEXAS = (-95.4, 30.0)


def _areas(fc):
    import ee
    return fc.map(lambda f: ee.Feature(None, {"a": f.geometry().area(1000)})) \
             .aggregate_array("a").getInfo()


@needs_ee
def test_no_footprint_covers_the_globe():
    import ee
    import geeViz.getSummaryAreasLib as sal
    areas = _areas(sal.getBuildings(ee.Geometry.Point(TEXAS).buffer(300)))
    assert areas, "expected real buildings near this point"
    assert max(areas) < 1e7


@needs_ee
def test_the_mask_is_not_flooded():
    import ee
    import geeViz.getSummaryAreasLib as sal
    area = ee.Geometry.Point(TEXAS).buffer(300)
    mask = ee.Image(0).byte().paint(sal.getBuildings(area), 1)
    share = mask.reduceRegion(ee.Reducer.mean(), area, 2).get("constant").getInfo()
    assert share < 0.5
