"""Unit test for _detect_empty_chart_data in geeViz/outputLib/charts.py.

The detector lives in charts.py and requires plotly/ee imports to load.
We reproduce the logic here for isolated testing.
"""
import pandas as pd


def _detect_empty_chart_data(df, context=""):
    """Reproduced from geeViz/outputLib/charts.py — keep in sync."""
    try:
        if df is None:
            return "no data"
        if df.empty:
            return "empty df"
        numeric = df.select_dtypes(include="number")
        if not numeric.empty:
            try:
                total = numeric.fillna(0).abs().sum().sum()
            except Exception:
                total = None
            if total == 0:
                return "all values are 0 or NaN"
    except Exception:
        return None
    return None


def test_none():
    assert _detect_empty_chart_data(None) is not None


def test_empty_dataframe():
    assert _detect_empty_chart_data(pd.DataFrame()) is not None


def test_all_nan_numeric():
    df = pd.DataFrame({"Severity": [float("nan")]})
    assert _detect_empty_chart_data(df) is not None


def test_all_zeros():
    df = pd.DataFrame({"A": [0, 0, 0], "B": [0, 0, 0]})
    assert _detect_empty_chart_data(df) is not None


def test_real_data_passes():
    df = pd.DataFrame({"NDVI": [0.5, 0.6, 0.7]})
    assert _detect_empty_chart_data(df) is None


def test_partial_zeros_pass():
    df = pd.DataFrame({"NDVI": [0.0, 0.5, 0.0]})
    assert _detect_empty_chart_data(df) is None


def test_string_only_passes():
    """A DataFrame with no numeric columns is not empty in the chart sense."""
    df = pd.DataFrame({"label": ["a", "b", "c"]})
    assert _detect_empty_chart_data(df) is None


def test_negative_values_pass():
    """Negative numeric values should count as real data (abs() check)."""
    df = pd.DataFrame({"temp_anomaly": [-1.5, -0.3, 2.1]})
    assert _detect_empty_chart_data(df) is None


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
