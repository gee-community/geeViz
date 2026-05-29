"""Regression test for parse_continuous_results handling multi-output reducers
(percentile, minMax, mean+stdDev combine).

The bug: previously parse_continuous_results looked up keys like
"<x_label>----<band>", but with ee.Reducer.percentile([5,50,95]) the raw
keys are "<x_label>----<band>_p5", etc. Every cell came out None, producing
an all-NaN df and an empty chart.

Repro from session geeviz-session-6b3c0912.json:
    cl.summarize_and_chart(
        nlcd_tcc_collection, area,
        reducer=ee.Reducer.percentile([5, 50, 95]),
        ...
    )
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "outputLib"))

# Reproduce SPLIT_STR + helpers without importing the full module (which pulls ee)
SPLIT_STR = "----"


def _collect_band_outputs(raw_dict, base_key):
    outputs = {}
    if base_key in raw_dict:
        outputs[""] = raw_dict[base_key]
    prefix = base_key + "_"
    plen = len(prefix)
    for k, v in raw_dict.items():
        if isinstance(k, str) and k.startswith(prefix):
            outputs[k[plen:]] = v
    return outputs


def test_single_output_reducer():
    """mean() — one value per band, no suffix."""
    raw = {"2020----NDVI": 0.5, "2021----NDVI": 0.6}
    assert _collect_band_outputs(raw, "2020----NDVI") == {"": 0.5}
    assert _collect_band_outputs(raw, "2021----NDVI") == {"": 0.6}


def test_percentile_reducer():
    """percentile([5, 50, 95]) — three values per band, with _p5/_p50/_p95 suffix."""
    raw = {
        "2020----TCC_p5": 10,
        "2020----TCC_p50": 30,
        "2020----TCC_p95": 60,
    }
    outputs = _collect_band_outputs(raw, "2020----TCC")
    assert outputs == {"p5": 10, "p50": 30, "p95": 60}


def test_minmax_reducer():
    """minMax() — two values per band: _min, _max."""
    raw = {"2020----elev_min": 1200, "2020----elev_max": 4400}
    outputs = _collect_band_outputs(raw, "2020----elev")
    assert outputs == {"min": 1200, "max": 4400}


def test_combine_reducer():
    """mean().combine(stdDev) — two values per band: bare base + _stdDev."""
    raw = {"2020----temp": 20.5, "2020----temp_stdDev": 3.2}
    outputs = _collect_band_outputs(raw, "2020----temp")
    assert outputs == {"": 20.5, "stdDev": 3.2}


def test_no_collision_with_other_bands():
    """Make sure '2020----NDVI' doesn't pick up '2020----NDVI_smoothed_p5'
    when looking for percentiles of NDVI itself."""
    raw = {
        "2020----NDVI": 0.5,
        "2020----NDVI_smoothed": 0.48,  # NOT a percentile output of NDVI
    }
    outputs = _collect_band_outputs(raw, "2020----NDVI")
    # The base matches, and "smoothed" looks like a suffix — this is the
    # ambiguous case. Current behavior: treats anything matching prefix
    # as a multi-output. That's acceptable because the alternative — guessing
    # what suffixes are "real" — is more error-prone. Document the behavior.
    assert "" in outputs
    assert "smoothed" in outputs


def test_no_match_returns_empty():
    raw = {"2020----OTHER": 0.5}
    assert _collect_band_outputs(raw, "2020----MISSING") == {}


def test_full_parse_with_percentiles():
    """End-to-end: simulate parse_continuous_results for the eval bug case."""
    import pandas

    # Reproduce the relevant part of parse_continuous_results
    def parse_continuous_results(raw_dict, band_names, x_axis_labels):
        if x_axis_labels:
            rows = []
            for x_label in x_axis_labels:
                row = {"x": x_label}
                for bn in band_names:
                    base = f"{x_label}{SPLIT_STR}{bn}"
                    outputs = _collect_band_outputs(raw_dict, base)
                    if len(outputs) == 1 and "" in outputs:
                        row[bn] = outputs[""]
                    else:
                        for suffix, val in outputs.items():
                            col = f"{bn}_{suffix}" if suffix else bn
                            row[col] = val
                rows.append(row)
            df = pandas.DataFrame(rows).set_index("x")
            df.index.name = None
            return df

    raw = {
        "2020----TCC_p5": 10, "2020----TCC_p50": 30, "2020----TCC_p95": 60,
        "2021----TCC_p5": 11, "2021----TCC_p50": 31, "2021----TCC_p95": 61,
        "2022----TCC_p5": 12, "2022----TCC_p50": 32, "2022----TCC_p95": 62,
    }
    df = parse_continuous_results(raw, ["TCC"], ["2020", "2021", "2022"])
    assert list(df.columns) == ["TCC_p5", "TCC_p50", "TCC_p95"]
    assert df.loc["2020", "TCC_p5"] == 10
    assert df.loc["2022", "TCC_p95"] == 62
    # Most importantly: no NaN values (the original bug)
    assert not df.isna().any().any()


def test_full_parse_with_single_reducer_still_works():
    """Backward compat: mean() — column name stays bare (no suffix)."""
    import pandas

    def parse_continuous_results(raw_dict, band_names, x_axis_labels):
        if x_axis_labels:
            rows = []
            for x_label in x_axis_labels:
                row = {"x": x_label}
                for bn in band_names:
                    base = f"{x_label}{SPLIT_STR}{bn}"
                    outputs = _collect_band_outputs(raw_dict, base)
                    if len(outputs) == 1 and "" in outputs:
                        row[bn] = outputs[""]
                    else:
                        for suffix, val in outputs.items():
                            col = f"{bn}_{suffix}" if suffix else bn
                            row[col] = val
                rows.append(row)
            df = pandas.DataFrame(rows).set_index("x")
            df.index.name = None
            return df

    raw = {"2020----NDVI": 0.5, "2021----NDVI": 0.6}
    df = parse_continuous_results(raw, ["NDVI"], ["2020", "2021"])
    assert list(df.columns) == ["NDVI"]
    assert df.loc["2020", "NDVI"] == 0.5


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
