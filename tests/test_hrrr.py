"""geeViz.hrrr: which files serve each hour, the wind rotation, and the guards.

Offline: nothing here touches NOAA's bucket, Cloud Storage or Earth
Engine. The live end-to-end run is the example notebook,
examples/hrrr_examples.ipynb.
"""
import ast
import datetime
import inspect
import io
import math
import re
import tokenize

import numpy as np
import pytest

from geeViz import hrrr

D = datetime.datetime


def _code(fn):
    """Source of ``fn`` with comments and docstrings removed."""
    src = inspect.getsource(fn)
    out = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            continue
        out.append(tok)
    stripped = tokenize.untokenize(out)
    tree = ast.parse(stripped.lstrip() if not stripped.startswith(" ") else "if 1:\n" + stripped)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.body and \
                isinstance(node.body[0], ast.Expr) and isinstance(getattr(node.body[0], "value", None), ast.Constant):
            node.body = node.body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def test_the_stripper_drops_comments_and_docstrings():
    def sample():
        """rotate_to_earth in a docstring"""
        # rotate_to_earth in a comment
        return 1
    code = _code(sample)
    assert "rotate_to_earth" not in code
    assert "return 1" in code


# ---------------------------------------------------------------- hours

def test_window_is_start_inclusive_end_exclusive_like_filterDate():
    hours = hrrr.valid_hours("2026-08-07T18:00", "2026-08-07T22:00")
    assert hours == [D(2026, 8, 7, h) for h in (18, 19, 20, 21)]


def test_a_start_between_hours_rounds_up_and_hourStep_thins():
    hours = hrrr.valid_hours("2026-08-07T18:30", "2026-08-08T00:00", hourStep=2)
    assert hours == [D(2026, 8, 7, 19), D(2026, 8, 7, 21), D(2026, 8, 7, 23)]


def test_offsets_are_converted_to_utc():
    assert hrrr.valid_hours("2026-08-07T12:00-06:00", "2026-08-07T13:00-06:00") == [D(2026, 8, 7, 18)]


@pytest.mark.parametrize("start,end,step", [
    ("2026-08-07T18:00", "2026-08-07T18:00", 1),
    ("2026-08-07T18:10", "2026-08-07T18:50", 1),
    ("2026-08-07T18:00", "2026-08-07T20:00", 0),
    ("2026-08-07T18:00", "2026-08-07T20:00", 1.5),
])
def test_empty_or_malformed_windows_raise(start, end, step):
    with pytest.raises(ValueError):
        hrrr.valid_hours(start, end, step)


def test_horizon_is_48_hours_for_synoptic_runs_and_18_otherwise():
    assert [hrrr.horizon(D(2026, 8, 7, h)) for h in (0, 6, 12, 18)] == [48] * 4
    assert [hrrr.horizon(D(2026, 8, 7, h)) for h in (1, 5, 13, 23)] == [18] * 4


# ---------------------------------------------------------------- plan

def _always(run, fhour):
    return True


def test_past_hours_use_each_hours_own_analysis():
    hours = [D(2026, 8, 7, h) for h in (18, 19, 20)]
    steps = hrrr.plan(hours, latest=D(2026, 11, 2, 18), check_published=_always)
    assert [(s["run"], s["fhour"], s["source"]) for s in steps] == [
        (h, 0, "analysis") for h in hours]
    # Precipitation has no hour 0: the previous run's first hour ends at the valid time.
    assert [(s["precip_run"], s["precip_fhour"]) for s in steps] == [
        (h - datetime.timedelta(hours=1), 1) for h in hours]


def test_a_window_within_18_hours_comes_from_the_newest_run():
    latest = D(2026, 11, 2, 13)
    hours = [latest + datetime.timedelta(hours=k) for k in range(-1, 4)]
    steps = hrrr.plan(hours, latest, check_published=_always)
    assert [s["source"] for s in steps] == ["analysis", "analysis", "forecast", "forecast", "forecast"]
    assert {s["run"] for s in steps if s["source"] == "forecast"} == {latest}
    assert [s["fhour"] for s in steps] == [0, 0, 1, 2, 3]
    assert [(s["precip_run"], s["precip_fhour"]) for s in steps][2:] == [(latest, 1), (latest, 2), (latest, 3)]


def test_beyond_18_hours_it_falls_back_to_the_newest_long_run():
    latest = D(2026, 11, 2, 13)
    hours = [D(2026, 11, 2, 11), D(2026, 11, 2, 12), D(2026, 11, 2, 13), D(2026, 11, 3, 18)]
    steps = hrrr.plan(hours, latest, check_published=_always)
    # 13z reaches only 18 hours; the 12z run reaches 48, and hours from 12z on use it.
    assert [(s["run"], s["fhour"], s["source"]) for s in steps] == [
        (D(2026, 11, 2, 11), 0, "analysis"),
        (D(2026, 11, 2, 12), 0, "analysis"),
        (D(2026, 11, 2, 12), 1, "forecast"),
        (D(2026, 11, 2, 12), 30, "forecast"),
    ]


def test_an_unpublished_forecast_hour_moves_to_an_older_run():
    latest = D(2026, 11, 2, 12)
    # The 12z run's hour 40 is not out yet; 06z reaches 46 from its start.
    published = lambda run, fh: not (run == latest and fh > 30)
    steps = hrrr.plan([D(2026, 11, 4, 4)], latest, check_published=published)
    assert (steps[0]["run"], steps[0]["fhour"]) == (D(2026, 11, 2, 6), 46)


def test_a_window_past_every_runs_reach_raises_and_points_to_gfs():
    with pytest.raises(ValueError, match="getForecastData") as e:
        hrrr.plan([D(2026, 11, 5, 0)], D(2026, 11, 2, 13), check_published=_always)
    assert "2026-11-05 00:00" in str(e.value)


def test_hours_before_the_archive_raise():
    with pytest.raises(ValueError, match="archive"):
        hrrr.plan([D(2014, 1, 1)], D(2026, 11, 2, 13), check_published=_always)


# ---------------------------------------------------------------- idx

IDX = """1:0:d=2026080712:REFC:entire atmosphere:6 hour fcst:
2:100:d=2026080712:TMP:2 m above ground:6 hour fcst:
3:250:d=2026080712:APCP:surface:0-6 hour acc fcst:
4:300:d=2026080712:APCP:surface:5-6 hour acc fcst:
5:420:d=2026080712:UGRD:10 m above ground:6 hour fcst:
"""


def test_idx_rows_end_one_byte_before_the_next_and_the_last_is_open():
    rows = hrrr.parse_idx(IDX)
    assert [(r["start"], r["end"]) for r in rows] == [(0, 99), (100, 249), (250, 299), (300, 419), (420, None)]


def test_precipitation_picks_the_one_hour_accumulation_not_the_run_total():
    rows = hrrr.parse_idx(IDX)
    assert hrrr.find_field(rows, "APCP", "surface", "5-6 hour acc fcst")["start"] == 300
    assert hrrr.find_field(rows, "TMP", "2 m above ground")["start"] == 100
    assert hrrr.find_field(rows, "DPT", "2 m above ground") is None


def test_messages_ask_for_the_one_hour_precip_of_the_right_file(monkeypatch):
    calls = []
    monkeypatch.setattr(hrrr, "_get", lambda url, byte_range=None: calls.append(url) or IDX.encode())
    step = {"run": D(2026, 8, 7, 12), "fhour": 6, "precip_run": D(2026, 8, 7, 12), "precip_fhour": 6}
    groups = hrrr._messages(step, ["temperature_2m", "precipitation"], {})
    (url, rows), = groups.items()
    assert url.endswith("hrrr.20260807/conus/hrrr.t12z.wrfsfcf06.grib2")
    assert [(b, r["start"]) for b, r in rows] == [("temperature_2m", 100), ("precipitation", 300)]


def test_a_field_missing_from_the_file_names_the_variable(monkeypatch):
    monkeypatch.setattr(hrrr, "_get", lambda url, byte_range=None: IDX.encode())
    step = {"run": D(2026, 8, 7, 12), "fhour": 6, "precip_run": D(2026, 8, 7, 12), "precip_fhour": 6}
    with pytest.raises(ValueError, match="dewpoint_2m"):
        hrrr._messages(step, ["dewpoint_2m"], {})


# ---------------------------------------------------------------- wind

def test_no_rotation_on_the_central_meridian():
    u, v = hrrr.rotate_to_earth(np.array([3.0]), np.array([4.0]), np.array([hrrr.CENTRAL_MERIDIAN]))
    assert np.allclose([u[0], v[0]], [3.0, 4.0])


def test_west_of_the_central_meridian_grid_north_turns_west():
    # Near Seattle the grid is turned about 15 degrees from true north
    # (alpha = sin(38.5) * (lon + 97.5), negative west of 97.5 W), so a
    # wind along grid north has a westward true component.
    lon = -122.3
    alpha = math.radians(math.sin(math.radians(38.5)) * (lon + 97.5))
    u, v = hrrr.rotate_to_earth(np.array([0.0]), np.array([10.0]), np.array([lon]))
    assert alpha < 0
    assert u[0] == pytest.approx(10 * math.sin(alpha))
    assert v[0] == pytest.approx(10 * math.cos(alpha))
    assert math.hypot(u[0], v[0]) == pytest.approx(10.0)


def test_the_rotation_is_applied_to_the_files_written():
    code = _code(hrrr._prepare_hour)
    assert re.search(r"layers\['u'\], layers\['v'\] = rotate_to_earth\(layers\['u'\], layers\['v'\], lon\)", code)


def test_grib_units_are_read_raw_so_kelvin_is_converted_once():
    # GDAL's GRIB driver converts K to C by default; the table's -273.15
    # would then be applied twice.
    assert "GRIB_NORMALIZE_UNITS='NO'" in _code(hrrr._prepare_hour)
    assert hrrr.VARIABLES["temperature_2m"]["offset"] == -273.15


def test_files_are_written_with_a_compression_earth_engine_reads():
    code = _code(hrrr._prepare_hour)
    assert "compress='DEFLATE'" in code
    assert "ZSTD" not in code and "LERC" not in code


# ---------------------------------------------------------------- guards

def test_wind_expands_to_u_and_v_and_unknown_names_raise():
    assert hrrr._expand(["temperature_2m", "wind"]) == ["temperature_2m", "u", "v"]
    assert hrrr._expand(None) == ["temperature_2m", "relative_humidity_2m", "u", "v", "wind_gust"]
    with pytest.raises(ValueError, match="'wind'"):
        hrrr._expand(["temperature"])


def test_too_many_hours_raises_before_any_network_call(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("contacted NOAA before checking the window")
    monkeypatch.setattr(hrrr, "latest_run", boom)
    monkeypatch.setattr(hrrr, "_storage_client", boom)
    with pytest.raises(ValueError, match="RTMA"):
        hrrr.getHRRR([-105.7, 39.9, -105.0, 40.3], "2026-08-01", "2026-08-08",
                     bucket="gs://b/p", verbose=False)


def test_a_bucket_is_required(monkeypatch):
    monkeypatch.delenv("GEEVIZ_HRRR_BUCKET", raising=False)
    with pytest.raises(ValueError, match="bucket"):
        hrrr.getHRRR([-105.7, 39.9, -105.0, 40.3], "2026-08-07T18:00", "2026-08-07T19:00",
                     verbose=False)


def test_cache_names_change_with_every_input_that_changes_the_file():
    code = _code(hrrr.getHRRR)
    assert "CACHE_VERSION" in code and "band_sig" in code and "bbox_sig" in code
    assert "precip_run" in code


# ---------------------------------------------------------------- status

def test_the_notebook_bar_saves_its_final_state_not_its_first(monkeypatch):
    shown = []

    class Handle:
        def update(self, obj):
            shown.append((repr(obj), obj._repr_html_()))

    import IPython.display
    monkeypatch.setattr(IPython.display, "display", lambda obj, display_id=None: Handle())
    bar = hrrr._NotebookBar(4, "HRRR")
    status = hrrr._Status(bar)
    status.enter("fetching")
    status.leave("fetching")
    for k in range(4):
        status.done(f"08-07 {18 + k}Z", fetched=10_000_000, written=20_000)
    bar.close()
    text, html = shown[-1]
    assert "4/4 hours" in text and "[####################]" in text
    assert "40.0 MB fetched" in text and "0.08 MB written" in text and "08-07 21Z" in text
    assert '<progress value="4" max="4"' in html


def test_outside_a_notebook_the_bar_is_tqdm(monkeypatch):
    monkeypatch.setattr(hrrr, "_in_notebook", lambda: False)
    bar = hrrr._status_bar(3)
    try:
        assert type(bar).__module__.startswith("tqdm")
    finally:
        bar.close()


def test_durations_read_naturally():
    assert hrrr._duration(63) == "63 seconds"
    assert hrrr._duration(600) == "10 minutes"
