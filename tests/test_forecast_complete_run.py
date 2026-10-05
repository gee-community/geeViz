"""A forward forecast comes from the newest COMPLETE run, chosen server-side.

EE ingests a GFS/ECMWF run over hours; the newest run was used regardless,
so for hours after each cycle a forecast had holes (2026-10-02: GFS 12Z
held 60 of 209 images). _most_complete_run scores recent runs on what
they hold in the window against what a complete run holds there, all in
one EE expression.
"""
import inspect
import re

import pytest


def _wx():
    # Imported at run time: geeViz.weather initializes Earth Engine on
    # import, which must not happen during collection.
    from geeViz import weather
    return weather


def test_expected_leads_match_a_complete_run():
    wx = _wx()
    long_l, short_l = wx._expected_leads("gfs")
    # 209 images in a complete GFS run, lead 0 among them; lead 0 is not
    # EXPECTED (WeatherNext has none), so 208 here.
    assert len(long_l) == 208 and long_l[:3] == (1, 2, 3) and long_l[-1] == 384
    assert 120 in long_l and 121 not in long_l and 123 in long_l
    e_long, e_short = wx._expected_leads("euro")
    assert e_long[-1] == 360 and e_short[-1] == 144 and 150 in e_long
    wn_long, wn_short = wx._expected_leads("weathernext")
    # A complete WeatherNext run holds leads 1..360 -- 360 images.
    assert len(wn_long) == 360 and len(wn_short) == 48 and wn_long[0] == 1


def test_expected_leads_are_cached():
    wx = _wx()
    assert wx._expected_leads("gfs") is wx._expected_leads("gfs")


def _code(fn):
    src = inspect.getsource(fn)
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    return "\n".join(l.split("#", 1)[0] for l in src.splitlines())


def test_run_choice_never_calls_the_server():
    wx = _wx()
    code = _code(wx._most_complete_run)
    assert "getInfo" not in code and "evaluate(" not in code


def test_getForecastData_uses_the_complete_run_choice():
    wx = _wx()
    code = _code(wx.getForecastData)
    assert "_most_complete_run(" in code
    assert "_newest_run_reaching(" not in code


def test_the_forecast_part_starts_at_the_window_not_the_run():
    """The chosen run can be hours older than t0; its earlier steps are
    outside the window."""
    wx = _wx()
    code = _code(wx.getForecastData)
    i = code.index("after = ic.filter(ee.Filter.eq(run_p, latest_run))")
    assert "ee.Filter.gte(valid_p, _v(t0))" in code[i:i + 400]
