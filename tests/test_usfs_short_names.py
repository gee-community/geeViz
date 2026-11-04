"""getUSFSForests / getUSFSDistricts find a unit by its short name.

The docstring has always offered ``forest_name="Lolo"``, but the filter
was an exact match on ``FORESTNAME`` ("Lolo National Forest"), so a short
name came back empty. Asked which ranger district a fire started in, the
agent called ``getUSFSDistricts(forest_name="Santa Fe")``, got an empty
list for two forests, and answered from memory without saying the
lookup had failed.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_empty_layer_warning import _ee_ok  # noqa: E402

needs_ee = pytest.mark.skipif(not _ee_ok(), reason="Earth Engine not initialized")


@needs_ee
def test_short_and_full_names_find_the_same_units():
    import ee
    import geeViz.getSummaryAreasLib as sal
    vals = ee.Dictionary({
        "forest_short": sal.getUSFSForests(forest_name="Lolo").aggregate_array("FORESTNAME"),
        "forest_full": sal.getUSFSForests(forest_name="Lolo National Forest").aggregate_array("FORESTNAME"),
        "plural": sal.getUSFSForests(forest_name="Apache-Sitgreaves").aggregate_array("FORESTNAME"),
        "districts_short": sal.getUSFSDistricts(forest_name="Santa Fe").size(),
        "districts_full": sal.getUSFSDistricts(forest_name="Santa Fe National Forest").size(),
        "district_short": sal.getUSFSDistricts(forest_name="Tonto", district_name="Cave Creek")
                             .aggregate_array("DISTRICTNA"),
        "list": sal.getUSFSForests(forest_name="Lolo,Bitterroot").aggregate_array("FORESTNAME").sort(),
    }).getInfo()
    assert vals["forest_short"] == ["Lolo National Forest"]
    assert vals["forest_full"] == ["Lolo National Forest"]
    assert vals["plural"] == ["Apache-Sitgreaves National Forests"]
    assert vals["districts_short"] > 0
    assert vals["districts_short"] == vals["districts_full"]
    assert vals["district_short"] == ["Cave Creek Ranger District"]
    assert vals["list"] == ["Bitterroot National Forest", "Lolo National Forest"]
