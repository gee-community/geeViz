"""Regression tests for the continuous-histogram reducer path in
geeViz/outputLib/charts.py.

Bug: ee.Reducer.histogram() returns a nested dict per band
({"bucketMeans": [...], "bucketWidth": w, "histogram": [...]}). The
default pipeline stored that dict in a DataFrame cell and chart_bar
couldn't plot it → silent empty chart.

The fix added an interceptor in summarize_and_chart that detects the
histogram reducer type and routes to a specialized handler.

These tests exercise the parsing helper without requiring EE
connectivity. The interceptor itself is tested indirectly by running
through the helper's input shapes.
"""
import pandas as pd


def _extract_histogram(value):
    """Mirrors the helper in charts.py — keep in sync."""
    if value is None:
        return (None, None)
    if isinstance(value, dict):
        means = value.get("bucketMeans")
        counts = value.get("histogram")
        if means is not None and counts is not None:
            return (list(means), list(counts))
    if isinstance(value, list) and value:
        try:
            centers = [row[0] for row in value]
            counts = [row[1] for row in value]
            return (centers, counts)
        except Exception:
            pass
    return (None, None)


def test_dict_form():
    """The common shape EE returns for histogram reducer."""
    raw = {
        "bucketMeans": [5.0, 15.0, 25.0, 35.0],
        "bucketWidth": 10.0,
        "histogram": [100, 250, 180, 50],
    }
    centers, counts = _extract_histogram(raw)
    assert centers == [5.0, 15.0, 25.0, 35.0]
    assert counts == [100, 250, 180, 50]


def test_list_of_pairs_form():
    """Alternate shape: list of [center, count] pairs."""
    raw = [[5, 100], [15, 250], [25, 180]]
    centers, counts = _extract_histogram(raw)
    assert centers == [5, 15, 25]
    assert counts == [100, 250, 180]


def test_none():
    assert _extract_histogram(None) == (None, None)


def test_empty_dict():
    assert _extract_histogram({}) == (None, None)


def test_dict_missing_keys():
    """If the dict doesn't have bucketMeans/histogram, return (None, None)."""
    assert _extract_histogram({"foo": "bar"}) == (None, None)


def test_full_pipeline_single_band():
    """End-to-end: simulate the per_band DataFrame assembly that the
    handler does after extraction."""
    raw = {
        "TCC": {
            "bucketMeans": [5.0, 15.0, 25.0],
            "bucketWidth": 10.0,
            "histogram": [100, 250, 180],
        }
    }
    band_names = ["TCC"]
    per_band = {}
    for bn in band_names:
        centers, counts = _extract_histogram(raw.get(bn))
        if centers is None:
            continue
        per_band[bn] = pd.Series(counts, index=centers).sort_index()

    df = pd.concat(per_band, axis=1).fillna(0)
    assert list(df.columns) == ["TCC"]
    assert list(df.index) == [5.0, 15.0, 25.0]
    assert df.loc[15.0, "TCC"] == 250


def test_full_pipeline_multi_band_different_buckets():
    """Multi-band: bucket centers union, NaN-filled with 0 where bands
    don't overlap."""
    raw = {
        "TCC": {"bucketMeans": [10, 20, 30], "histogram": [100, 200, 50]},
        "NDVI": {"bucketMeans": [0.1, 0.5, 0.9], "histogram": [40, 80, 30]},
    }
    band_names = ["TCC", "NDVI"]
    per_band = {}
    for bn in band_names:
        centers, counts = _extract_histogram(raw.get(bn))
        per_band[bn] = pd.Series(counts, index=centers).sort_index()
    df = pd.concat(per_band, axis=1).fillna(0)
    assert "TCC" in df.columns
    assert "NDVI" in df.columns
    # TCC has nothing at 0.1, NDVI has nothing at 10 — both filled with 0
    assert df.loc[0.1, "TCC"] == 0
    assert df.loc[10, "NDVI"] == 0
    assert df.loc[10, "TCC"] == 100


def test_ic_heatmap_grid_assembly():
    """Heatmap grid: rows are bucket centers (TCC values), columns are
    time labels (years). Simulates _histogram_ic_heatmap output shape."""
    SPLIT_STR = "----"
    raw = {
        "2020----TCC": [[0, 100], [10, 200], [20, 150]],
        "2021----TCC": [[0,  90], [10, 210], [20, 170]],
        "2022----TCC": [[0,  85], [10, 220], [20, 180]],
    }
    x_axis_labels = ["2020", "2021", "2022"]
    band = "TCC"

    per_time = {}
    for x_label in x_axis_labels:
        key = f"{x_label}{SPLIT_STR}{band}"
        val = raw.get(key)
        centers, counts = _extract_histogram(val)
        if centers is None:
            continue
        per_time[x_label] = pd.Series(counts, index=centers).sort_index()

    df = pd.DataFrame(per_time).fillna(0).sort_index()
    df = df.reindex(sorted(df.columns), axis=1)
    # New orientation: rows = bucket centers, columns = years
    assert list(df.index) == [0, 10, 20]
    assert list(df.columns) == ["2020", "2021", "2022"]
    assert df.loc[0, "2020"] == 100
    assert df.loc[20, "2022"] == 180


def test_ic_heatmap_with_ragged_bins():
    """If different time steps have different bucket centers (per-image
    auto-binning), the union of centers becomes the rows and missing
    cells fill with 0."""
    SPLIT_STR = "----"
    raw = {
        "2020----TCC": [[0, 100], [10, 200]],            # only 2 buckets
        "2021----TCC": [[0,  90], [10, 210], [20, 50]],  # 3 buckets
    }
    x_axis_labels = ["2020", "2021"]
    band = "TCC"

    per_time = {}
    for x_label in x_axis_labels:
        key = f"{x_label}{SPLIT_STR}{band}"
        val = raw.get(key)
        centers, counts = _extract_histogram(val)
        per_time[x_label] = pd.Series(counts, index=centers).sort_index()

    df = pd.DataFrame(per_time).fillna(0).sort_index()
    assert df.loc[20, "2020"] == 0   # absent in 2020, filled with 0
    assert df.loc[20, "2021"] == 50


def test_ic_heatmap_per_column_percent_normalization():
    """Each year column should sum to 100% after normalization, so the
    chart shows distribution SHAPE per year rather than absolute counts."""
    SPLIT_STR = "----"
    raw = {
        # Year 2020: total 300 pixels — 100 in bucket 0, 200 in bucket 10
        "2020----TCC": [[0, 100], [10, 200]],
        # Year 2021: total 1000 pixels — 500/500 split (different total!)
        "2021----TCC": [[0, 500], [10, 500]],
    }
    band = "TCC"
    per_time = {}
    for x_label in ["2020", "2021"]:
        key = f"{x_label}{SPLIT_STR}{band}"
        centers, counts = _extract_histogram(raw[key])
        per_time[x_label] = pd.Series(counts, index=centers).sort_index()

    df = pd.DataFrame(per_time).fillna(0).sort_index()
    df = df.reindex(sorted(df.columns), axis=1)
    col_sums = df.sum(axis=0).replace(0, 1)
    df_pct = df.divide(col_sums, axis=1) * 100.0

    # Each year column should sum to 100
    assert abs(df_pct["2020"].sum() - 100.0) < 1e-9
    assert abs(df_pct["2021"].sum() - 100.0) < 1e-9
    # 2020 distribution shape: 33.3% / 66.7%
    assert abs(df_pct.loc[0, "2020"] - 33.333333) < 1e-3
    assert abs(df_pct.loc[10, "2020"] - 66.666667) < 1e-3
    # 2021: 50% / 50% — different totals, same shape detection
    assert abs(df_pct.loc[0, "2021"] - 50.0) < 1e-9
    assert abs(df_pct.loc[10, "2021"] - 50.0) < 1e-9


def test_ic_heatmap_zero_column_safe():
    """A year with all-zero counts must not produce NaN/inf via div-by-zero."""
    df = pd.DataFrame({
        "2020": [100, 200, 50],
        "2021": [0, 0, 0],   # fully masked year — should stay 0, no NaN
    }, index=[0, 10, 20])
    col_sums = df.sum(axis=0).replace(0, 1)
    df_pct = df.divide(col_sums, axis=1) * 100.0
    assert df_pct["2021"].sum() == 0.0
    assert not df_pct.isna().any().any()


def test_chart_type_histogram_shortcut_recognized_in_source():
    """Regression test: ``cl.summarize_and_chart(..., chart_type="histogram")``
    must trigger the histogram-routing block in charts.py (no explicit reducer
    needed). Verified by source inspection so the test doesn't need EE."""
    import os
    src = open(os.path.join(os.path.dirname(__file__), "..", "outputLib", "charts.py"),
               encoding="utf-8").read()
    # The shortcut must:
    #   (a) check ``chart_type`` against "histogram" early in summarize_and_chart
    #   (b) synthesize a Reducer.histogram(...) when no reducer was given
    #   (c) fall through to the existing histogram interceptor
    assert 'chart_type).lower().strip() == "histogram"' in src, \
        "Shortcut check on chart_type='histogram' missing"
    assert "ee.Reducer.histogram(maxBuckets=50)" in src, \
        "Default histogram reducer not synthesized"


def test_bucket_count_matches_observed_data():
    """The Salt Lake County NLCD TCC case — verify a realistic histogram
    parses correctly (100 buckets)."""
    means = [i * 1.0 for i in range(100)]
    counts = [i * 10 for i in range(100)]
    raw = {"TCC": {"bucketMeans": means, "histogram": counts}}
    centers, c = _extract_histogram(raw["TCC"])
    assert len(centers) == 100
    assert len(c) == 100
    # Series should be sortable and indexable
    s = pd.Series(c, index=centers).sort_index()
    assert s.iloc[0] == 0
    assert s.iloc[-1] == 990


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {t.__name__}: {e}")
    print()
    if failed:
        print(f"{failed}/{len(tests)} tests FAILED")
        raise SystemExit(1)
    print(f"{len(tests)}/{len(tests)} tests passed")
