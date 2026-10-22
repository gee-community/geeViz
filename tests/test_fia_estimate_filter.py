"""fia_estimate can ask FIA for one total over several rows.

Asked for a region made of three FIA survey units, the agent could only
get the units as separate rows (the tool had no filter), so it summed
the estimates and combined their standard errors in quadrature. Rows of
one evaluation share its strata and are not independent: the reported
SE came out a third too wide (1.66% where FIA's own total for the same
plots is 1.25%). The tool now passes ``str_filter`` through, and its
docstring says the combined SE comes from the Total row.
"""
import json

import pandas as pd

import geeViz.mcp.server as srv
from geeViz import fsInsights


def _fake_estimate(calls):
    def fake(**kw):
        calls.append(kw)
        return pd.DataFrame([{"row": "Total", "estimate": 1.0, "se_pct": 1.25,
                              "plots": 4913, "unreliable": False,
                              "forest_definition": "FIADEF"}])
    return fake


def test_str_filter_reaches_estimate(monkeypatch):
    calls = []
    monkeypatch.setattr(fsInsights, "estimate", _fake_estimate(calls))
    out = json.loads(srv.fia_estimate(wc=412024, snum=55000, rselected="Unit code",
                                      str_filter="plot.unitcd in (0, 1, 2)"))
    assert "error" not in out, out
    assert calls and calls[0].get("str_filter") == "plot.unitcd in (0, 1, 2)"


def test_no_filter_by_default(monkeypatch):
    calls = []
    monkeypatch.setattr(fsInsights, "estimate", _fake_estimate(calls))
    srv.fia_estimate(wc=412024, snum=55000, rselected="Unit code")
    assert calls[0].get("str_filter", "") == ""


def test_docstring_says_combined_se_comes_from_fia():
    doc = srv.fia_estimate.__doc__ or ""
    assert "str_filter" in doc
    assert "Total" in doc and "need not be independent" in doc


def test_filter_matching_nothing_gets_a_hint(monkeypatch):
    def fake(**kw):
        raise fsInsights.UpstreamError("Estimate Error: Parameters resulted in "
                                       "no data being retrieved.. This is upstream")
    monkeypatch.setattr(fsInsights, "estimate", fake)
    out = json.loads(srv.fia_estimate(wc=412024, snum=2, rselected="Unit code",
                                      str_filter="plot.unitcd in (4100)"))
    assert "stored codes" in out.get("hint", "")
    out = json.loads(srv.fia_estimate(wc=412024, snum=2, rselected="Unit code"))
    assert "hint" not in out
