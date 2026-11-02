"""getAdminBoundaries reaches units below a city and names at levels 3-4.

Session 043eb0b6 (2026-11-01): asked about one urban district of a large
city. Countries number their admin levels differently, and in that one
level 2 is the whole city, so every level-2 source returned the city (or
"Name Unknown"). The agent went on to analyze a box typed from memory
twice the district's size. Locally, the agent tried every source and
level ``getAdminBoundaries`` offered, found nothing, and spent 25 to 39
tool calls hunting for a boundary that the community geoBoundaries
high-precision collection holds at level 3.

Two faults:

* No source reached geoBoundaries' high-precision levels 3-4 (now
  ``source="geobhp"``).
* With the default source, levels 3-4 fall back to FieldMaps assets but
  filtered ``name`` on geoBoundaries' ``shapeName``, a property FieldMaps
  does not have, so a level-3 name lookup always came back empty.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_empty_layer_warning import _ee_ok  # noqa: E402

needs_ee = pytest.mark.skipif(not _ee_ok(), reason="Earth Engine not initialized")

# A point inside an urban district that geoBoundaries' high-precision
# collection holds at level 3 and the level-2 sources lump into its city.
URBAN_DISTRICT = (116.315, 39.9999)


@needs_ee
def test_geobhp_reaches_a_district_below_its_city():
    import ee
    import geeViz.getSummaryAreasLib as sal
    pt = ee.Geometry.Point(URBAN_DISTRICT)
    vals = ee.Dictionary({
        "l2": sal.getAdminBoundaries(pt, level=2, source="geob").aggregate_array("shapeName"),
        "l3": sal.getAdminBoundaries(pt, level=3, source="geobhp").aggregate_array("shapeName"),
        "km2": sal.getAdminBoundaries(pt, level=3, source="geobhp").geometry().area(10).divide(1e6),
    }).getInfo()
    assert len(vals["l3"]) == 1
    assert vals["l3"] != vals["l2"], "level 3 must be finer than the city-wide level 2"
    assert 300 < vals["km2"] < 600


@needs_ee
def test_geobhp_name_lookup():
    import geeViz.getSummaryAreasLib as sal
    names = sal.getAdminBoundaries(level=3, source="geobhp", name="Haidian") \
               .aggregate_array("shapeName").getInfo()
    assert names == ["Haidian District"]


def test_geobhp_name_property_is_shapename():
    import geeViz.getSummaryAreasLib as sal
    for level in range(5):
        assert sal.getAdminNameProperty(level=level, source="geobhp") == "shapeName"


def test_fallback_level_filters_on_the_fallback_sources_name_property(monkeypatch):
    """Default source at level 3 uses FieldMaps, so the name filter must
    use FieldMaps' ``adm3_name``, not geoBoundaries' ``shapeName``."""
    import geeViz.getSummaryAreasLib as sal

    seen = []

    class _FC:
        def __init__(self, asset):
            self.asset = asset

        def filter(self, f):
            seen.append(str(f))
            return self

        def size(self):
            return self

        def gt(self, _):
            return self

    class _Filter:
        @staticmethod
        def eq(prop, val):
            return f"eq:{prop}"

        @staticmethod
        def stringContains(prop, val):
            return f"contains:{prop}"

    class _EE:
        Filter = _Filter
        FeatureCollection = staticmethod(lambda x: x)

        class Algorithms:
            @staticmethod
            def If(c, a, b):
                return a

    monkeypatch.setattr(sal, "ee", _EE)
    monkeypatch.setattr(sal, "_filter_bounds", lambda asset, area=None: _FC(asset))
    sal.getAdminBoundaries(level=3, name="Somewhere")
    assert seen and all(s.endswith(":adm3_name") for s in seen), seen
