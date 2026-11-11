"""fl.burn_change and its parts: windows, classes, the one-call result.

The everyday fire request ("a simple two-date change map of the Monroe
Canyon fire") used to take the agent 7-21 tool calls hunting for a
perimeter and its dates. burn_change does it in one: NIFC perimeter and
dates (georest.nifc), pre/post composites, dNBR, severity. These tests
pin the parts that decide what the map shows: which dates are compared,
which pixels get which class, and that the result says what is derived.
"""
import datetime as dt
import re
from pathlib import Path

import pytest

from geeViz.fireLib import burn

D = dt.date


# ── the windows ────────────────────────────────────────────────────────

def test_pre_is_the_weeks_before_discovery_post_the_weeks_after_containment():
    w = burn.burn_windows("2025-07-13", "2025-09-04", 60, lat=38.6, today=D(2026, 11, 4))
    assert (w["startDatePre"], w["endDatePre"]) == ("2025-05-13", "2025-07-12")
    assert (w["startDatePost"], w["endDatePost"]) == ("2025-09-05", "2025-11-04")
    assert w["post_rule"].startswith("the 60 days after")


def test_a_mostly_winter_post_window_moves_to_the_same_season_a_year_on():
    # Dixie 2021: contained Oct 25 at 40 N; Oct 26 - Dec 25 is snow.
    w = burn.burn_windows("2021-07-14", "2021-10-25", 60, lat=40.0, today=D(2026, 1, 1))
    assert (w["startDatePost"], w["endDatePost"]) == ("2022-05-14", "2022-07-13")
    assert "winter" in w["post_rule"]


def test_a_few_winter_days_do_not_move_it():
    # Monroe Canyon: Sep 5 - Nov 4 has only Nov 1-4 in winter.
    w = burn.burn_windows("2025-07-13", "2025-09-04", 60, lat=38.6, today=D(2026, 11, 4))
    assert w["startDatePost"] == "2025-09-05"


def test_winter_at_a_low_latitude_stays_immediate():
    # Palisades 2025, 34 N: winter there is not snow.
    w = burn.burn_windows("2025-01-07", None, 60, lat=34.07, today=D(2026, 1, 1))
    assert w["startDatePost"] == "2025-02-07"     # 30 days after discovery, plus one
    assert "no containment date" in w["post_rule"]


def test_the_post_window_is_cut_at_today_and_refused_before_it_starts():
    w = burn.burn_windows("2026-09-01", "2026-10-01", 60, lat=30, today=D(2026, 10, 20))
    assert w["endDatePost"] == "2026-10-20"
    with pytest.raises(ValueError, match="no post-fire imagery yet"):
        burn.burn_windows("2026-10-01", "2026-10-30", 60, lat=30, today=D(2026, 10, 20))


def test_a_leap_day_window_survives_the_year_shift():
    assert burn._shift_year(D(2024, 2, 29)) == D(2025, 2, 28)


def test_center_latitude_is_read_from_any_geometry_shape():
    gj = {"features": [{"geometry": {"type": "MultiPolygon", "coordinates": [
        [[[-112, 38], [-111, 38], [-111, 39], [-112, 38]]], [[[-110, 40], [-109, 40], [-109, 41], [-110, 40]]]]}}]}
    assert burn._center_lat(gj) == pytest.approx(39.5)
    assert burn._center_lat({"features": []}) is None


# ── the classes ────────────────────────────────────────────────────────

def test_severity_thresholds_are_key_and_benson_and_contiguous():
    lows = [c[2] for c in burn.SEVERITY_CLASSES]
    highs = [c[3] for c in burn.SEVERITY_CLASSES]
    assert lows == [100, 270, 440, 660]
    assert highs[:-1] == lows[1:] and highs[-1] is None
    assert [c[0] for c in burn.SEVERITY_CLASSES] == [1, 2, 3, 4]


# ── the one call ───────────────────────────────────────────────────────

def _src(fn) -> str:
    import inspect
    s = inspect.getsource(fn)
    s = re.sub(r'"""[\s\S]*?"""', "", s)
    return "\n".join(re.sub(r"#.*$", "", line) for line in s.splitlines())


def test_the_stripper_strips():
    def f():
        """doc"""
        return 1  # note
    assert "doc" not in _src(f) and "note" not in _src(f)


def test_burn_change_takes_its_dates_from_the_fire():
    src = _src(burn.burn_change)
    assert 'burn_windows(info["discovered"], info.get("contained") or info.get("fire_out")' in src
    assert "_center_lat(p[\"geojson\"])" in src


def test_layer_names_say_what_is_derived():
    src = _src(burn.burn_change)
    assert 'dNBR (derived)' in src
    assert 'burn severity (derived from dNBR)' in src
    assert "not MTBS's official severity" in src


def test_stdout_is_never_swapped_process_wide():
    """redirect_stdout replaces sys.stdout for every thread. Two overlapping
    burn_change runs in one MCP server restored each other's stand-in and
    left stdout on a dead buffer: every later run_code printed nothing, and
    the agent re-ran its prints three and four times to see its results."""
    import inspect as _i
    src = _i.getsource(burn)
    code = "\n".join(re.sub(r"#.*$", "", line) for line in src.splitlines())
    assert "redirect_stdout(" not in code and "sys.stdout =" not in code


def test_it_is_on_fl_and_in_the_mcp_namespace():
    import geeViz.fireLib as fl
    assert fl.burn_change is burn.burn_change and fl.fire_perimeter is burn.fire_perimeter
    server = Path(__file__).resolve().parents[1] / "mcp" / "server.py"
    s = server.read_text(encoding="utf-8")
    assert '"fl": _fl_mod,' in s
    assert '"fl":               "fireLib",' in s


@pytest.mark.parametrize("bad", [dict(), dict(area="x")])
def test_it_needs_a_fire_or_an_area_with_dates(bad):
    with pytest.raises(ValueError):
        burn.burn_change(**bad)
