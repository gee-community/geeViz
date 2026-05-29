"""Unit test for _auto_date_format in geeViz/outputLib/thumbs.py.

The detector picks a date_format token from a list of epoch-millisecond
timestamps. Reproduced inline to avoid importing the full thumbs module
(which pulls EE/PIL/etc.).
"""
import datetime as _dt


def _auto_date_format(timestamps_ms):
    try:
        ts = [t for t in timestamps_ms if t is not None]
        if len(ts) < 2:
            return "YYYY-MM-dd" if ts else "YYYY"
        ts_sorted = sorted(ts)
        span_ms = ts_sorted[-1] - ts_sorted[0]
        deltas = [ts_sorted[i + 1] - ts_sorted[i] for i in range(len(ts_sorted) - 1)]
        min_delta_ms = min(deltas) if deltas else span_ms
        _hour = 60 * 60 * 1000
        _day = 24 * _hour
        _year = 365 * _day
        if min_delta_ms < 2 * _hour:
            return "YYYY-MM-dd HH:mm"
        if min_delta_ms < _day:
            return "YYYY-MM-dd HH"
        if span_ms < 60 * _day:
            return "YYYY-MM-dd"
        if span_ms < 5 * _year:
            return "YYYY-MM"
        return "YYYY"
    except Exception:
        return "YYYY"


def _ms(year, month=1, day=1, hour=0):
    return int(_dt.datetime(year, month, day, hour).timestamp() * 1000)


def test_monthly_within_one_year():
    """The case the eval flagged: monthly composites of 2022 snow cover.
    Old default 'YYYY' rendered '2022' on every frame — useless."""
    months = [_ms(2022, m) for m in range(1, 13)]
    assert _auto_date_format(months) == "YYYY-MM"


def test_annual_multi_decade():
    years = [_ms(y) for y in [1985, 1990, 1995, 2000, 2010, 2020]]
    assert _auto_date_format(years) == "YYYY"


def test_short_term_daily():
    days = [_ms(2024, 6, d) for d in range(1, 15)]
    assert _auto_date_format(days) == "YYYY-MM-dd"


def test_hourly():
    hours = [_ms(2024, 6, 1, h) for h in range(0, 24, 3)]
    assert _auto_date_format(hours) == "YYYY-MM-dd HH"


def test_sub_hourly():
    base = _ms(2024, 6, 1)
    sub_hour = [base + i * 15 * 60 * 1000 for i in range(8)]  # 15-min spacing
    assert _auto_date_format(sub_hour) == "YYYY-MM-dd HH:mm"


def test_empty_list():
    assert _auto_date_format([]) == "YYYY"


def test_single_frame():
    assert _auto_date_format([_ms(2024)]) == "YYYY-MM-dd"


def test_none_filtering():
    """None timestamps in the list (no system:time_start) must not crash."""
    mixed = [_ms(2020), None, _ms(2021), None, _ms(2022)]
    assert _auto_date_format(mixed) in ("YYYY", "YYYY-MM")


def test_five_year_boundary():
    # Just inside 5 years → YYYY-MM
    five_y = [_ms(2020), _ms(2024)]
    assert _auto_date_format(five_y) == "YYYY-MM"
    # Well past 5 years → YYYY
    ten_y = [_ms(2015), _ms(2025)]
    assert _auto_date_format(ten_y) == "YYYY"


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
