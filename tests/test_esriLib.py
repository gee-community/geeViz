"""Tests for geeViz.esriLib — Esri / ArcGIS REST bridge.

All HTTP calls are mocked via ``unittest.mock.patch`` so no network access
is required.  The tests cover:

- Portal short-name resolution and full-URL pass-through
- searchPortal: URL construction, data_only exclusion string, raw_q override
- searchPortal: response parsing into normalized dicts
- getServiceMetadata: URL construction and response pass-through
- _detect_service_type: URL-based detection (fast path, no HTTP)
- addEsriImageService: tile URL shape and addTileLayer call
- addEsriMapService: delegates to addEsriImageService
- addEsriFeatureService: pre-flight count, GeoJSON fetch, addLayer call
- addEsriFeatureService: ValueError on count overflow
- addEsriFeatureService: auto-appends /0 to FeatureServer root URLs
- addEsriService: auto-dispatches by detected type
"""

import json
import sys
import types
import unittest
import urllib.error
from unittest.mock import MagicMock, call, patch

# ---------------------------------------------------------------------------
# Isolate import: stub out geeViz.geeView so we don't need EE credentials.
#
# Strategy: install the stub ONLY for "geeViz.geeView".  The real "geeViz"
# package must remain importable (it's a real directory package), so we do
# NOT touch sys.modules["geeViz"].  We only pre-populate "geeViz.geeView"
# before importing esriLib, which causes Python to skip the real geeView.py
# (and its EE initialization) when esriLib does `import geeViz.geeView as gv`.
# ---------------------------------------------------------------------------

_mock_map = MagicMock()
_mock_gv = types.ModuleType("geeViz.geeView")
_mock_gv.Map = _mock_map

# Pre-install the stub before esriLib is imported
sys.modules["geeViz.geeView"] = _mock_gv

import geeViz.esriLib as el  # noqa: E402  (after stubs are installed)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_response(data: dict) -> bytes:
    """Encode *data* as UTF-8 JSON bytes, as urlopen would return."""
    return json.dumps(data).encode("utf-8")


def _make_urlopen_ctx(data: dict):
    """Return a context-manager mock whose .read() returns JSON bytes."""
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=ctx)
    ctx.__exit__ = MagicMock(return_value=False)
    ctx.read = MagicMock(return_value=_json_response(data))
    return ctx


# ---------------------------------------------------------------------------
# PORTALS constant
# ---------------------------------------------------------------------------

class TestPortalsConstant(unittest.TestCase):
    def test_required_keys_present(self):
        for key in ("iipp", "agol", "usgs", "noaa", "usfs", "nasa"):
            self.assertIn(key, el.PORTALS, f"PORTALS missing key {key!r}")

    def test_all_values_are_https(self):
        for key, url in el.PORTALS.items():
            self.assertTrue(
                url.startswith("https://"),
                f"PORTALS[{key!r}] does not start with https: {url!r}",
            )


# ---------------------------------------------------------------------------
# _resolve_portal
# ---------------------------------------------------------------------------

class TestResolvePortal(unittest.TestCase):
    def test_short_name_iipp(self):
        url = el._resolve_portal("iipp")
        self.assertEqual(url, "https://imagery.geoplatform.gov/iipp")

    def test_short_name_agol(self):
        url = el._resolve_portal("agol")
        self.assertEqual(url, "https://www.arcgis.com")

    def test_trailing_slash_stripped(self):
        # Add a portal with trailing slash and check it's stripped
        el.PORTALS["_test_slash"] = "https://example.com/portal/"
        url = el._resolve_portal("_test_slash")
        self.assertEqual(url, "https://example.com/portal")
        del el.PORTALS["_test_slash"]

    def test_full_url_passthrough(self):
        url = el._resolve_portal("https://gis.myagency.gov/portal")
        self.assertEqual(url, "https://gis.myagency.gov/portal")

    def test_full_url_trailing_slash_stripped(self):
        url = el._resolve_portal("https://gis.myagency.gov/portal/")
        self.assertEqual(url, "https://gis.myagency.gov/portal")

    def test_unknown_short_name_raises(self):
        with self.assertRaises(KeyError):
            el._resolve_portal("nonexistent_portal_xyz")

    def test_error_message_lists_known_portals(self):
        try:
            el._resolve_portal("nonexistent_portal_xyz")
        except KeyError as exc:
            msg = str(exc)
            self.assertIn("iipp", msg)
            self.assertIn("agol", msg)


# ---------------------------------------------------------------------------
# searchPortal — URL construction
# ---------------------------------------------------------------------------

class TestSearchPortalUrlConstruction(unittest.TestCase):
    """Verify that the correct search URL and params are constructed."""

    def _run_search(self, **kwargs):
        """Run searchPortal with a mocked urlopen, return the captured URL."""
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.read = MagicMock(return_value=_json_response({"results": []}))
            return ctx

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            el.searchPortal(**kwargs)

        return captured["url"]

    def test_iipp_default_portal(self):
        url = self._run_search(query="naip")
        self.assertIn("imagery.geoplatform.gov/iipp/sharing/rest/search", url)

    def test_agol_portal(self):
        url = self._run_search(query="fire", portal="agol")
        self.assertIn("arcgis.com/sharing/rest/search", url)

    def test_custom_url_portal(self):
        url = self._run_search(query="hydro",
                               portal="https://gis.mystate.gov/portal")
        self.assertIn("gis.mystate.gov/portal/sharing/rest/search", url)

    def test_data_only_appends_exclusions(self):
        url = self._run_search(query="test", data_only=True)
        # The exclusion list should contain at least one -type: token
        self.assertIn("-type%3A", url)  # URL-encoded -type:"
        # "Style" is in the exclusion list
        self.assertIn("Style", url)

    def test_data_only_false_no_exclusions(self):
        url = self._run_search(query="test", data_only=False)
        # Should not contain exclusion syntax
        self.assertNotIn("-type%3A", url)

    def test_raw_q_overrides_query(self):
        url = self._run_search(query="ignored",
                               raw_q='type:"Feature Service" owner:USGS',
                               data_only=True)
        # raw_q value should be in the URL
        self.assertIn("Feature+Service", url)
        # "ignored" should NOT appear (was overridden by raw_q)
        self.assertNotIn("ignored", url)
        # data_only exclusions should NOT appear (raw_q fully overrides)
        self.assertNotIn("-type%3A", url)

    def test_limit_clamped_to_100(self):
        url = self._run_search(query="x", limit=999)
        self.assertIn("num=100", url)

    def test_limit_respected(self):
        url = self._run_search(query="x", limit=5)
        self.assertIn("num=5", url)

    def test_token_appended(self):
        url = self._run_search(query="x", token="abc123")
        self.assertIn("token=abc123", url)

    def test_no_token_by_default(self):
        url = self._run_search(query="x")
        self.assertNotIn("token=", url)


# ---------------------------------------------------------------------------
# searchPortal — response parsing
# ---------------------------------------------------------------------------

class TestSearchPortalParsing(unittest.TestCase):
    _SAMPLE_ITEM = {
        "id": "abc123",
        "title": "NAIP 2022",
        "type": "Image Service",
        "snippet": "NAIP imagery for 2022",
        "tags": ["NAIP", "imagery"],
        "url": "https://naip.services.arcgis.com/Uw60GSwW8tEHzOAQ/arcgis/rest/services/NAIP_2022/ImageServer",
        "owner": "usda_fpac",
        "created": 1672531200000,
        "modified": 1680000000000,
        "thumbnail": "thumbnail/ago_downloaded.png",
    }

    def _search_with_item(self, item: dict) -> list[dict]:
        """Run searchPortal returning a single item."""
        def fake_urlopen(req, timeout=None):
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.read = MagicMock(return_value=_json_response({"results": [item]}))
            return ctx

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            return el.searchPortal("naip")

    def test_returns_list(self):
        results = self._search_with_item(self._SAMPLE_ITEM)
        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 1)

    def test_id_parsed(self):
        r = self._search_with_item(self._SAMPLE_ITEM)[0]
        self.assertEqual(r["id"], "abc123")

    def test_title_parsed(self):
        r = self._search_with_item(self._SAMPLE_ITEM)[0]
        self.assertEqual(r["title"], "NAIP 2022")

    def test_type_parsed(self):
        r = self._search_with_item(self._SAMPLE_ITEM)[0]
        self.assertEqual(r["type"], "Image Service")

    def test_url_parsed(self):
        r = self._search_with_item(self._SAMPLE_ITEM)[0]
        self.assertIn("ImageServer", r["url"])

    def test_tags_is_list(self):
        r = self._search_with_item(self._SAMPLE_ITEM)[0]
        self.assertIsInstance(r["tags"], list)

    def test_thumbnail_is_full_url(self):
        r = self._search_with_item(self._SAMPLE_ITEM)[0]
        # Should be expanded to a full URL
        self.assertTrue(r["thumbnail"].startswith("https://"))
        self.assertIn("abc123", r["thumbnail"])

    def test_raw_preserved(self):
        r = self._search_with_item(self._SAMPLE_ITEM)[0]
        self.assertIn("_raw", r)
        self.assertEqual(r["_raw"]["id"], "abc123")

    def test_empty_results(self):
        def fake_urlopen(req, timeout=None):
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.read = MagicMock(return_value=_json_response({"results": []}))
            return ctx

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            results = el.searchPortal("nothing")
        self.assertEqual(results, [])

    def test_missing_url_key_returns_empty_string(self):
        item = {**self._SAMPLE_ITEM}
        del item["url"]
        r = self._search_with_item(item)[0]
        self.assertEqual(r["url"], "")

    def test_missing_thumbnail_returns_none(self):
        item = {**self._SAMPLE_ITEM, "thumbnail": None}
        r = self._search_with_item(item)[0]
        self.assertIsNone(r["thumbnail"])


# ---------------------------------------------------------------------------
# _detect_service_type — URL-based fast path
# ---------------------------------------------------------------------------

class TestDetectServiceType(unittest.TestCase):
    def test_imageserver_url(self):
        self.assertEqual(
            el._detect_service_type("https://example.com/rest/services/NAIP/ImageServer"),
            "ImageServer",
        )

    def test_featureserver_url(self):
        self.assertEqual(
            el._detect_service_type("https://example.com/rest/services/Fires/FeatureServer/0"),
            "FeatureServer",
        )

    def test_mapserver_url(self):
        self.assertEqual(
            el._detect_service_type("https://server.arcgisonline.com/ArcGIS/rest/services/"
                                    "World_Imagery/MapServer/tile/{z}/{y}/{x}"),
            "MapServer",
        )

    def test_case_insensitive(self):
        self.assertEqual(
            el._detect_service_type("https://example.com/rest/services/X/imageserver"),
            "ImageServer",
        )

    def test_unknown_returns_unknown_without_metadata(self):
        # When URL has no recognizable segment AND metadata fetch fails, should
        # return "Unknown" without raising
        with patch("geeViz.esriLib.getServiceMetadata", side_effect=Exception("no network")):
            result = el._detect_service_type("https://example.com/some/other/endpoint")
        self.assertEqual(result, "Unknown")

    def test_fields_key_in_meta_implies_featureserver(self):
        meta = {"fields": [{"name": "OBJECTID"}]}
        with patch("geeViz.esriLib.getServiceMetadata", return_value=meta):
            result = el._detect_service_type("https://example.com/other")
        self.assertEqual(result, "FeatureServer")

    def test_bandcount_in_meta_implies_imageserver(self):
        meta = {"bandCount": 4, "pixelType": "U8"}
        with patch("geeViz.esriLib.getServiceMetadata", return_value=meta):
            result = el._detect_service_type("https://example.com/other")
        self.assertEqual(result, "ImageServer")


# ---------------------------------------------------------------------------
# _resolve_url
# ---------------------------------------------------------------------------

class TestResolveUrl(unittest.TestCase):
    def test_string_passthrough(self):
        self.assertEqual(
            el._resolve_url("https://example.com/ImageServer"),
            "https://example.com/ImageServer",
        )

    def test_trailing_slash_stripped(self):
        self.assertEqual(
            el._resolve_url("https://example.com/ImageServer/"),
            "https://example.com/ImageServer",
        )

    def test_dict_with_url_key(self):
        result = {"url": "https://example.com/FeatureServer/0", "title": "X"}
        self.assertEqual(
            el._resolve_url(result),
            "https://example.com/FeatureServer/0",
        )

    def test_dict_without_url_raises(self):
        with self.assertRaises(ValueError):
            el._resolve_url({"id": "abc", "title": "No URL"})

    def test_wrong_type_raises(self):
        with self.assertRaises(TypeError):
            el._resolve_url(42)


# ---------------------------------------------------------------------------
# addEsriImageService
# ---------------------------------------------------------------------------

class TestAddEsriImageService(unittest.TestCase):
    def setUp(self):
        _mock_map.reset_mock()

    def test_tile_url_has_arcgis_order(self):
        """ArcGIS tile URL must use {z}/{y}/{x}, not {z}/{x}/{y}."""
        el.addEsriImageService("https://example.com/rest/services/X/ImageServer")
        call_args = _mock_map.addTileLayer.call_args
        tile_url = call_args[0][0]  # first positional arg
        self.assertIn("{z}/{y}/{x}", tile_url)

    def test_tile_url_base(self):
        el.addEsriImageService("https://example.com/rest/services/X/ImageServer")
        tile_url = _mock_map.addTileLayer.call_args[0][0]
        self.assertTrue(tile_url.startswith("https://example.com/rest/services/X/ImageServer/tile/"))

    def test_name_kwarg_forwarded(self):
        el.addEsriImageService("https://example.com/X/ImageServer", name="My Layer")
        call_kwargs = _mock_map.addTileLayer.call_args[1]
        self.assertEqual(call_kwargs["name"], "My Layer")

    def test_token_appended_to_tile_url(self):
        el.addEsriImageService("https://example.com/X/ImageServer", token="tok123")
        tile_url = _mock_map.addTileLayer.call_args[0][0]
        self.assertIn("token=tok123", tile_url)

    def test_no_token_no_query_string(self):
        el.addEsriImageService("https://example.com/X/ImageServer")
        tile_url = _mock_map.addTileLayer.call_args[0][0]
        self.assertNotIn("token=", tile_url)

    def test_viz_params_opacity(self):
        el.addEsriImageService("https://example.com/X/ImageServer",
                               viz_params={"opacity": 0.5})
        call_kwargs = _mock_map.addTileLayer.call_args[1]
        self.assertAlmostEqual(call_kwargs["opacity"], 0.5)

    def test_viz_params_max_zoom(self):
        el.addEsriImageService("https://example.com/X/ImageServer",
                               viz_params={"max_zoom": 18})
        call_kwargs = _mock_map.addTileLayer.call_args[1]
        self.assertEqual(call_kwargs["max_zoom"], 18)

    def test_dict_result_url_extracted(self):
        result = {"url": "https://example.com/X/ImageServer", "title": "X"}
        el.addEsriImageService(result, name="From Dict")
        tile_url = _mock_map.addTileLayer.call_args[0][0]
        self.assertIn("example.com/X/ImageServer/tile/", tile_url)


# ---------------------------------------------------------------------------
# addEsriMapService
# ---------------------------------------------------------------------------

class TestAddEsriMapService(unittest.TestCase):
    def setUp(self):
        _mock_map.reset_mock()

    def test_delegates_to_image_service(self):
        """MapServer and ImageServer share the same tile path."""
        el.addEsriMapService("https://server.arcgisonline.com/ArcGIS/rest/services/"
                              "World_Imagery/MapServer")
        tile_url = _mock_map.addTileLayer.call_args[0][0]
        self.assertIn("{z}/{y}/{x}", tile_url)
        self.assertIn("MapServer/tile/", tile_url)


# ---------------------------------------------------------------------------
# addEsriFeatureService
# ---------------------------------------------------------------------------

def _mock_feature_urlopen(count_data: dict, geojson_data: dict):
    """Return a urlopen side_effect that serves count then geojson."""
    call_num = {"n": 0}

    def fake_urlopen(req, timeout=None):
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=ctx)
        ctx.__exit__ = MagicMock(return_value=False)
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "returnCountOnly=true" in url:
            ctx.read = MagicMock(return_value=_json_response(count_data))
        else:
            ctx.read = MagicMock(return_value=_json_response(geojson_data))
        return ctx

    return fake_urlopen


_SAMPLE_GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-111.89, 40.77]},
         "properties": {"name": "Test Point"}},
    ],
}


class TestAddEsriFeatureService(unittest.TestCase):
    def setUp(self):
        _mock_map.reset_mock()

    def test_normal_fetch_calls_addlayer(self):
        with patch("urllib.request.urlopen",
                   side_effect=_mock_feature_urlopen({"count": 1}, _SAMPLE_GEOJSON)):
            el.addEsriFeatureService("https://example.com/FeatureServer/0")
        _mock_map.addLayer.assert_called_once()

    def test_geojson_passed_to_addlayer(self):
        with patch("urllib.request.urlopen",
                   side_effect=_mock_feature_urlopen({"count": 1}, _SAMPLE_GEOJSON)):
            el.addEsriFeatureService("https://example.com/FeatureServer/0",
                                     name="Test Layer")
        args = _mock_map.addLayer.call_args[0]
        geojson_arg = args[0]
        self.assertEqual(geojson_arg["type"], "FeatureCollection")
        self.assertIn("features", geojson_arg)

    def test_overflow_raises_valueerror(self):
        with patch("urllib.request.urlopen",
                   side_effect=_mock_feature_urlopen({"count": 5000}, _SAMPLE_GEOJSON)):
            with self.assertRaises(ValueError) as ctx:
                el.addEsriFeatureService("https://example.com/FeatureServer/0",
                                         max_features=1000)
        msg = str(ctx.exception)
        self.assertIn("5,000", msg)
        self.assertIn("max_features=1,000", msg)
        self.assertIn("where", msg)  # remediation hint

    def test_overflow_message_mentions_chunk_size(self):
        with patch("urllib.request.urlopen",
                   side_effect=_mock_feature_urlopen({"count": 9999}, _SAMPLE_GEOJSON)):
            with self.assertRaises(ValueError) as ctx:
                el.addEsriFeatureService("https://example.com/FeatureServer/0",
                                         max_features=500)
        self.assertIn("chunk_size", str(ctx.exception))

    def test_exactly_at_max_features_succeeds(self):
        geojson = {**_SAMPLE_GEOJSON,
                   "features": [_SAMPLE_GEOJSON["features"][0]] * 1000}
        with patch("urllib.request.urlopen",
                   side_effect=_mock_feature_urlopen({"count": 1000}, geojson)):
            # Should NOT raise
            el.addEsriFeatureService("https://example.com/FeatureServer/0",
                                     max_features=1000)
        _mock_map.addLayer.assert_called_once()

    def test_featureserver_root_appends_zero(self):
        """URL ending in FeatureServer should become FeatureServer/0."""
        captured_urls = []

        def fake_urlopen(req, timeout=None):
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            url = req.full_url if hasattr(req, "full_url") else str(req)
            captured_urls.append(url)
            if "returnCountOnly=true" in url:
                ctx.read = MagicMock(return_value=_json_response({"count": 1}))
            else:
                ctx.read = MagicMock(return_value=_json_response(_SAMPLE_GEOJSON))
            return ctx

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            el.addEsriFeatureService("https://example.com/FeatureServer")
        # Both requests should hit /FeatureServer/0/query
        for u in captured_urls:
            self.assertIn("/FeatureServer/0/query", u)

    def test_where_clause_forwarded(self):
        captured = []

        def fake_urlopen(req, timeout=None):
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            url = req.full_url if hasattr(req, "full_url") else str(req)
            captured.append(url)
            if "returnCountOnly=true" in url:
                ctx.read = MagicMock(return_value=_json_response({"count": 1}))
            else:
                ctx.read = MagicMock(return_value=_json_response(_SAMPLE_GEOJSON))
            return ctx

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            el.addEsriFeatureService("https://example.com/FeatureServer/0",
                                     where="STATE='UT'")
        # Both URLs should encode the where clause
        for u in captured:
            self.assertIn("where=", u)
            self.assertIn("STATE", u)

    def test_token_forwarded_in_both_requests(self):
        captured = []

        def fake_urlopen(req, timeout=None):
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            url = req.full_url if hasattr(req, "full_url") else str(req)
            captured.append(url)
            if "returnCountOnly=true" in url:
                ctx.read = MagicMock(return_value=_json_response({"count": 1}))
            else:
                ctx.read = MagicMock(return_value=_json_response(_SAMPLE_GEOJSON))
            return ctx

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            el.addEsriFeatureService("https://example.com/FeatureServer/0",
                                     token="my_token")
        for u in captured:
            self.assertIn("token=my_token", u)

    def test_outsr_is_4326(self):
        """GeoJSON query must request WGS84 so the viewer renders it correctly."""
        captured_geojson_urls = []

        def fake_urlopen(req, timeout=None):
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "returnCountOnly=true" in url:
                ctx.read = MagicMock(return_value=_json_response({"count": 1}))
            else:
                captured_geojson_urls.append(url)
                ctx.read = MagicMock(return_value=_json_response(_SAMPLE_GEOJSON))
            return ctx

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            el.addEsriFeatureService("https://example.com/FeatureServer/0")
        self.assertTrue(captured_geojson_urls, "No GeoJSON fetch URL captured")
        self.assertIn("outSR=4326", captured_geojson_urls[0])

    def test_service_error_response_raises(self):
        error_resp = {"error": {"code": 400, "message": "Invalid where clause"}}

        def fake_urlopen(req, timeout=None):
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.read = MagicMock(return_value=_json_response(error_resp))
            return ctx

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with self.assertRaises(ValueError) as ctx_mgr:
                el.addEsriFeatureService("https://example.com/FeatureServer/0")
        self.assertIn("400", str(ctx_mgr.exception))

    def test_network_error_raises_connection_error(self):
        with patch("urllib.request.urlopen",
                   side_effect=urllib.error.URLError("connection refused")):
            with self.assertRaises(ConnectionError):
                el.addEsriFeatureService("https://unreachable.example.com/FeatureServer/0")


# ---------------------------------------------------------------------------
# addEsriService — auto-dispatch
# ---------------------------------------------------------------------------

class TestAddEsriService(unittest.TestCase):
    def setUp(self):
        _mock_map.reset_mock()

    def test_dispatches_to_image_service(self):
        with patch("geeViz.esriLib.addEsriImageService") as mock_add:
            el.addEsriService("https://example.com/rest/services/X/ImageServer")
        mock_add.assert_called_once()

    def test_dispatches_to_feature_service(self):
        with patch("geeViz.esriLib.addEsriFeatureService") as mock_add:
            el.addEsriService("https://example.com/rest/services/X/FeatureServer/0")
        mock_add.assert_called_once()

    def test_dispatches_to_map_service(self):
        with patch("geeViz.esriLib.addEsriMapService") as mock_add:
            el.addEsriService("https://example.com/rest/services/X/MapServer")
        mock_add.assert_called_once()

    def test_unknown_type_raises(self):
        with patch("geeViz.esriLib._detect_service_type", return_value="Unknown"):
            with self.assertRaises(ValueError):
                el.addEsriService("https://example.com/something/else")

    def test_kwargs_forwarded_to_feature(self):
        with patch("geeViz.esriLib.addEsriFeatureService") as mock_add:
            el.addEsriService(
                "https://example.com/FeatureServer/0",
                name="My Layer",
                where="STATE='CA'",
                max_features=500,
                token="tok",
            )
        _, kwargs = mock_add.call_args
        self.assertEqual(kwargs["name"], "My Layer")
        self.assertEqual(kwargs["where"], "STATE='CA'")
        self.assertEqual(kwargs["max_features"], 500)
        self.assertEqual(kwargs["token"], "tok")

    def test_kwargs_forwarded_to_image(self):
        with patch("geeViz.esriLib.addEsriImageService") as mock_add:
            el.addEsriService(
                "https://example.com/ImageServer",
                name="Imagery",
                viz_params={"opacity": 0.8},
                token="tok",
            )
        _, kwargs = mock_add.call_args
        self.assertEqual(kwargs["name"], "Imagery")
        self.assertAlmostEqual(kwargs["viz_params"]["opacity"], 0.8)


# ---------------------------------------------------------------------------
# getServiceMetadata
# ---------------------------------------------------------------------------

class TestGetServiceMetadata(unittest.TestCase):
    _SAMPLE_META = {
        "name": "NAIP_2022",
        "type": "Image Service",
        "bandCount": 4,
        "pixelType": "U8",
    }

    def _run(self, url, token=None):
        def fake_urlopen(req, timeout=None):
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.read = MagicMock(return_value=_json_response(self._SAMPLE_META))
            return ctx

        with patch("urllib.request.urlopen", side_effect=fake_urlopen) as m:
            result = el.getServiceMetadata(url, token=token)
            req_obj = m.call_args[0][0]
            return result, req_obj

    def test_returns_parsed_dict(self):
        result, _ = self._run("https://example.com/ImageServer")
        self.assertEqual(result["name"], "NAIP_2022")
        self.assertEqual(result["bandCount"], 4)

    def test_f_json_appended(self):
        _, req = self._run("https://example.com/ImageServer")
        self.assertIn("f=json", req.full_url)

    def test_token_appended(self):
        _, req = self._run("https://example.com/ImageServer", token="abc")
        self.assertIn("token=abc", req.full_url)

    def test_trailing_slash_stripped_in_url(self):
        _, req = self._run("https://example.com/ImageServer/")
        self.assertNotIn("ImageServer//", req.full_url)

    def test_network_error_raises_connection_error(self):
        with patch("urllib.request.urlopen",
                   side_effect=urllib.error.URLError("timeout")):
            with self.assertRaises(ConnectionError):
                el.getServiceMetadata("https://unreachable.example.com/ImageServer")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
