"""Sankey transition periods: a year, or a list taken as a range of years.

``areaChartParams["sankeyTransitionPeriods"]`` takes years (the simple way:
``[1985, 2000, 2023]``), lists (``[[1985, 1988], [2021, 2023]]``, as before),
or both mixed. Each entry becomes a ``[start, end]`` pair; a range charts its
years' most common class. Only the first entry used to be checked, so a mixed
list kept its bare years, or had its ranges duplicated.

Needs Earth Engine for the ee objects.
"""
import pytest

import geeViz.geeView as gv
from georest.view._document import validate

ee = gv.ee
MIXED = [[1985, 1988], 1990, 2000, [2021, 2023]]
WANT = [[1985, 1988], [1990, 1990], [2000, 2000], [2021, 2023]]


def periods_of(m, name):
    d = validate(m._build_document())
    layer = next(l for l in d["layers"] if l["name"] == name)
    return layer["viz"]["areaChartParams"]["sankeyTransitionPeriods"]


@pytest.fixture
def m():
    m = gv.mapper()
    m.setSkin("geoview")
    return m


@pytest.mark.parametrize("given, want", [
    (MIXED, WANT),
    ([1990, [2021, 2023]], [[1990, 1990], [2021, 2023]]),
    ([1985, 2024], [[1985, 1985], [2024, 2024]]),
    ([[1985, 1987], [2020, 2022]], [[1985, 1987], [2020, 2022]]),
    ([(1985, 1986, 1987), "2020"], [[1985, 1987], [2020, 2020]]),
])
def test_transition_periods_are_years_or_ranges(given, want):
    assert gv._transition_periods(given) == want


def test_an_entry_that_is_not_a_year_is_named():
    with pytest.raises(TypeError, match="dict"):
        gv._transition_periods([1985, {"a": 1}])


def test_addLayer_and_addTimeLapse_take_mixed_periods(m):
    lc = ee.ImageCollection("projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11").select(["Land_Cover"])
    params = lambda: {"areaChartParams": {"sankey": True, "sankeyTransitionPeriods": list(MIXED)}}
    m.addLayer(lc, {"canAreaChart": True, **params()}, "Layer")
    m.addTimeLapse(lc, {"canAreaChart": True, **params()}, "Time lapse")
    assert periods_of(m, "Layer") == WANT
    assert periods_of(m, "Time lapse") == WANT
