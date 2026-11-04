"""The lcms_summary MCP tool accepts short Forest Service names and returns every row.

The LCMS API knows a unit only by its full name ("Tonto National
Forest", "Cave Creek Ranger District") and answers anything else with
"Invalid Summary Area". Asked for a ranger district's land use change,
the agent sent ``district="Cave Creek"``, got that error, and rebuilt the
numbers from raw rasters instead. Those disagreed with the official
summaries, and the person spent a ten-minute turn asking why.

The tool also capped its result at 80 rows, a fraction of a district's
full 1985-2025 series.

Hermetic: the API call is replaced by a fake that knows only full names.
"""
import json

import pytest

FULL = {("Tonto National Forest", "Cave Creek Ranger District"),
        ("Tonto National Forest", "")}


def _fake_rows(n):
    import pandas as pd
    return pd.DataFrame([{"year": 1985 + i % 41, "class_name": f"c{i}", "acres": float(i)}
                         for i in range(n)])


@pytest.fixture
def tool(monkeypatch):
    import geeViz.mcp.server as srv
    from geeViz import fsInsights as fs
    calls = []

    def fake(product, *, state="", county="", region="", forest="", district="", year=None):
        calls.append((forest, district))
        if (forest, district) not in FULL:
            raise RuntimeError("Invalid Summary Area for LCMS Release 2025-11 "
                               f"(sent: forest={forest!r}, district={district!r})")
        return _fake_rows(459)

    monkeypatch.setattr(fs, "lcms_summary", fake)
    fn = getattr(srv.lcms_summary, "fn", srv.lcms_summary)
    return fn, calls


def test_short_district_and_forest_names_resolve(tool):
    fn, calls = tool
    out = json.loads(fn(product="Land_Use", forest="Tonto", district="Cave Creek"))
    assert "error" not in out, out
    assert out["forest"] == "Tonto National Forest"
    assert out["district"] == "Cave Creek Ranger District"
    assert calls[0] == ("Tonto", "Cave Creek"), "the name as given is tried first"


def test_short_forest_alone_resolves(tool):
    fn, _ = tool
    out = json.loads(fn(product="Change", forest="Tonto", year=2020))
    assert "error" not in out, out
    assert out["forest"] == "Tonto National Forest"


def test_full_names_go_through_in_one_call(tool):
    fn, calls = tool
    out = json.loads(fn(forest="Tonto National Forest", district="Cave Creek Ranger District"))
    assert "error" not in out
    assert len(calls) == 1


def test_unknown_name_still_errors(tool):
    fn, _ = tool
    out = json.loads(fn(forest="Nowhere", district="Nothing"))
    assert "Invalid Summary Area" in out["error"]


def test_full_series_is_not_truncated(tool):
    fn, _ = tool
    out = json.loads(fn(forest="Tonto National Forest", district="Cave Creek Ranger District"))
    assert out["count"] == 459
    assert len(out["rows"]) == 459
    assert not out.get("truncated")
