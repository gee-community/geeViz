"""inspect_asset answers a repeated lookup from memory, safely.

An uncached Sentinel-2 lookup took ~10 s every time (its image count runs
into the 10 s timeout), and the same few datasets are looked up all day.
Results are kept in-process for 24 hours. Public catalog ids share one
entry; anything that could be private is keyed by tenant and user, so
one user's private asset is never served to another. Errors are never
kept; a count that timed out is kept for an hour at most.
"""
import json

import pytest

import geeViz.mcp.server as srv
from geeViz.eeAuth.client import CURRENT_TENANT, CURRENT_USER_EMAIL


@pytest.fixture(autouse=True)
def empty_cache(monkeypatch):
    monkeypatch.setattr(srv, "_INSPECT_CACHE", srv._ia_collections.OrderedDict())
    yield


@pytest.fixture
def lookups(monkeypatch):
    """Replace the real lookup with a counter; return the call log."""
    calls = []

    def fake(asset_id, start_date, end_date, region_var, session_id):
        calls.append((asset_id, CURRENT_USER_EMAIL.get()))
        return json.dumps({"asset_id": asset_id, "n": len(calls),
                           "bands": [{"id": "B1"}]})

    monkeypatch.setattr(srv, "_inspect_asset_uncached", fake)
    return calls


def _as(user, fn, *a, **k):
    tok = CURRENT_USER_EMAIL.set(user)
    tok2 = CURRENT_TENANT.set("askterra")
    try:
        return fn(*a, **k)
    finally:
        CURRENT_USER_EMAIL.reset(tok)
        CURRENT_TENANT.reset(tok2)


def test_inspect_asset_answers_a_repeat_from_the_cache(lookups):
    a = srv.inspect_asset("COPERNICUS/S2_SR_HARMONIZED", session_id="s1")
    b = srv.inspect_asset("COPERNICUS/S2_SR_HARMONIZED", session_id="s2")
    assert a == b
    assert len(lookups) == 1


def test_a_public_dataset_is_shared_between_users(lookups):
    _as("a@example.com", srv.inspect_asset, "USGS/SRTMGL1_003")
    _as("b@example.com", srv.inspect_asset, "USGS/SRTMGL1_003")
    assert len(lookups) == 1


def test_a_private_asset_is_never_served_to_another_user(lookups):
    aid = "projects/someones-project/assets/private_parcels"
    _as("a@example.com", srv.inspect_asset, aid)
    _as("a@example.com", srv.inspect_asset, aid)
    assert len(lookups) == 1                       # the same user: cached
    _as("b@example.com", srv.inspect_asset, aid)
    assert lookups[-1] == (aid, "b@example.com")   # another user: looked up
    assert len(lookups) == 2


@pytest.mark.parametrize("aid,public", [
    ("COPERNICUS/S2_SR_HARMONIZED", True),
    ("USGS/SRTMGL1_003", True),
    ("projects/earthengine-public/assets/COPERNICUS/S2", True),
    ("bigquery-public-data.overture_maps.place", True),
    ("projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11", False),
    ("users/someone/my_asset", False),
    ("my-project.my_dataset.my_table", False),
])
def test_which_ids_count_as_public(aid, public):
    assert srv._inspect_is_public(aid) is public


def test_without_a_user_private_entries_are_kept_per_session(lookups):
    aid = "users/someone/my_asset"
    srv.inspect_asset(aid, session_id="s1")
    srv.inspect_asset(aid, session_id="s2")
    assert len(lookups) == 2


def test_a_region_filtered_lookup_is_not_cached(lookups):
    srv.inspect_asset("COPERNICUS/S2_SR_HARMONIZED", region_var="aoi", session_id="s1")
    srv.inspect_asset("COPERNICUS/S2_SR_HARMONIZED", region_var="aoi", session_id="s1")
    assert len(lookups) == 2


def test_date_filters_are_part_of_the_key(lookups):
    srv.inspect_asset("COPERNICUS/S2_SR_HARMONIZED", start_date="2024-06-01", end_date="2024-09-01")
    srv.inspect_asset("COPERNICUS/S2_SR_HARMONIZED", start_date="2023-06-01", end_date="2023-09-01")
    assert len(lookups) == 2


@pytest.mark.parametrize("field", ["error", "detail_error", "image_count_error"])
def test_errors_are_not_cached(monkeypatch, field):
    calls = []

    def failing(*a):
        calls.append(1)
        return json.dumps({field: "boom", "asset_id": a[0]})

    monkeypatch.setattr(srv, "_inspect_asset_uncached", failing)
    srv.inspect_asset("USGS/SRTMGL1_003")
    srv.inspect_asset("USGS/SRTMGL1_003")
    assert len(calls) == 2


def test_a_timed_out_count_is_kept_for_an_hour_at_most():
    out = json.dumps({"image_count": "timeout (large collection)"})
    assert srv._inspect_cache_ttl(out) == min(srv._INSPECT_CACHE_TTL, 3600.0)
    assert srv._inspect_cache_ttl(json.dumps({"bands": []})) == srv._INSPECT_CACHE_TTL


def test_entries_expire(lookups, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(srv._ia_time, "monotonic", lambda: now[0])
    srv.inspect_asset("USGS/SRTMGL1_003")
    now[0] += srv._INSPECT_CACHE_TTL - 1
    srv.inspect_asset("USGS/SRTMGL1_003")
    assert len(lookups) == 1
    now[0] += 2
    srv.inspect_asset("USGS/SRTMGL1_003")
    assert len(lookups) == 2


def test_the_cache_is_bounded(lookups, monkeypatch):
    monkeypatch.setattr(srv, "_INSPECT_CACHE_MAX", 3)
    for i in range(5):
        srv.inspect_asset(f"USGS/ASSET_{i}")
    assert len(srv._INSPECT_CACHE) == 3
    srv.inspect_asset("USGS/ASSET_0")              # evicted: looked up again
    assert len(lookups) == 6


def test_a_ttl_of_zero_turns_it_off(lookups, monkeypatch):
    monkeypatch.setattr(srv, "_INSPECT_CACHE_TTL", 0)
    srv.inspect_asset("USGS/SRTMGL1_003")
    srv.inspect_asset("USGS/SRTMGL1_003")
    assert len(lookups) == 2
