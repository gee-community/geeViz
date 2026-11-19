"""Vector file conversion: ``geeViz.eeAuth.vector_convert`` and the
``POST /ee-api/convert/vector`` endpoint on both servers that serve the
viewer (the eeAuth proxy app and geeView's local static server).

Fixtures are built here, in a temp dir, with geopandas/pyogrio and
zipfile; nothing binary is checked in.
"""
import io
import json
import os
import socketserver
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile

import pytest

gpd = pytest.importorskip("geopandas")
pytest.importorskip("pyogrio")
from shapely.geometry import Polygon, mapping  # noqa: E402

from geeViz.eeAuth import vector_convert as vc  # noqa: E402

# A square in Utah, lon/lat.
SQUARE = [(-111.62, 40.59), (-111.59, 40.59), (-111.59, 40.615), (-111.62, 40.615), (-111.62, 40.59)]


def _gdf(crs="EPSG:4326", n=1):
    polys = [Polygon([(x + i * 0.1, y) for x, y in SQUARE]) for i in range(n)]
    return gpd.GeoDataFrame({"name": [f"unit {i}" for i in range(n)], "acres": [10.5 + i for i in range(n)]}, geometry=polys, crs="EPSG:4326").to_crs(crs)


def _zip_bytes(members):
    """members: [(name, bytes)] or [(ZipInfo, bytes)]."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members:
            zf.writestr(name, data)
    return buf.getvalue()


def _shapefile_zip(tmp_path, crs="EPSG:5070", n=1, drop=()):
    folder = tmp_path / "shp_src"
    folder.mkdir(exist_ok=True)
    _gdf(crs, n).to_file(folder / "units.shp", engine="pyogrio")
    members = [(p.name, p.read_bytes()) for p in sorted(folder.iterdir()) if p.suffix.lower() not in drop]
    return _zip_bytes(members)


KML_TWO_FOLDERS = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>units</name>
<Folder><name>East</name><Placemark><name>A</name><Polygon><outerBoundaryIs><LinearRing><coordinates>
-111.62,40.59,0 -111.59,40.59,0 -111.59,40.615,0 -111.62,40.615,0 -111.62,40.59,0
</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></Folder>
<Folder><name>West</name><Placemark><name>B</name><Polygon><outerBoundaryIs><LinearRing><coordinates>
-112.62,40.59,0 -112.59,40.59,0 -112.59,40.615,0 -112.62,40.615,0 -112.62,40.59,0
</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></Folder>
</Document></kml>"""


def _ring(feature):
    g = feature["geometry"]
    ring = g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0]
    return [tuple(c[:2]) for c in ring]


def _assert_ring_close(got, want, tol=1e-6):
    # Shapefiles store outer rings clockwise, so compare vertices, not order.
    assert len(got) == len(want), (got, want)
    for (gx, gy), (wx, wy) in zip(sorted(got), sorted(want)):
        assert abs(gx - wx) < tol and abs(gy - wy) < tol, (got, want)


@pytest.fixture
def clean_tmp(tmp_path, monkeypatch):
    """Route the converter's temp dirs into a folder the test can inspect."""
    root = tmp_path / "convert_tmp"
    root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(root))
    return root


# ---------------------------------------------------------------- converter


def test_zipped_shapefile_in_albers_reprojects_to_4326(tmp_path, clean_tmp):
    data = _shapefile_zip(tmp_path, crs="EPSG:5070")
    # the fixture really is projected: its coordinates are meters, not degrees
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        assert "units.prj" in zf.namelist()
        assert "Albers" in zf.read("units.prj").decode()
    fc = vc.convert_bytes("units.zip", data)
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 1
    f = fc["features"][0]
    _assert_ring_close(_ring(f), SQUARE)
    assert f["properties"]["name"] == "unit 0"
    assert f["properties"]["acres"] == 10.5
    assert f["properties"]["layer"] == "units"
    assert any("EPSG:4326" in n for n in fc["notes"])
    # temp files are gone
    assert list(clean_tmp.iterdir()) == []


def test_shapefile_without_prj_in_lon_lat_is_read_as_wgs84_and_says_so(tmp_path):
    data = _shapefile_zip(tmp_path, crs="EPSG:4326", drop=(".prj",))
    fc = vc.convert_bytes("units.zip", data)
    _assert_ring_close(_ring(fc["features"][0]), SQUARE)
    assert any(".prj" in n for n in fc["notes"])


def test_shapefile_without_prj_in_meters_is_refused(tmp_path):
    data = _shapefile_zip(tmp_path, crs="EPSG:5070", drop=(".prj",))
    with pytest.raises(vc.ConvertError) as e:
        vc.convert_bytes("units.zip", data)
    assert ".prj" in e.value.error + e.value.hint


def test_kmz_with_two_folders_merges_with_layer_property(clean_tmp):
    data = _zip_bytes([("doc.kml", KML_TWO_FOLDERS.encode())])
    fc = vc.convert_bytes("units.kmz", data)
    layers = sorted(f["properties"]["layer"] for f in fc["features"])
    assert layers == ["East", "West"]
    by = {f["properties"]["layer"]: f for f in fc["features"]}
    _assert_ring_close(_ring(by["East"]), SQUARE)
    assert [l["name"] for l in fc["layers"]] == ["East", "West"]
    assert any("Combined 2 layers" in n for n in fc["notes"])
    assert list(clean_tmp.iterdir()) == []


def test_kml_is_converted_on_the_server_too():
    fc = vc.convert_bytes("units.kml", KML_TWO_FOLDERS.encode())
    assert len(fc["features"]) == 2


def test_geojson_passthrough():
    gj = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"name": "Test unit", "n": 3}, "geometry": mapping(Polygon(SQUARE))}]}
    fc = vc.convert_bytes("test unit.geojson", json.dumps(gj).encode())
    assert len(fc["features"]) == 1
    _assert_ring_close(_ring(fc["features"][0]), SQUARE)
    assert fc["features"][0]["properties"]["name"] == "Test unit"
    assert fc["features"][0]["properties"]["n"] == 3


def test_geopackage_with_two_layers_merges(tmp_path):
    p = tmp_path / "two.gpkg"
    _gdf("EPSG:5070").to_file(p, layer="a", engine="pyogrio")
    _gdf("EPSG:4326", n=2).to_file(p, layer="b", engine="pyogrio")
    fc = vc.convert_bytes("two.gpkg", p.read_bytes())
    assert sorted(f["properties"]["layer"] for f in fc["features"]) == ["a", "b", "b"]
    a = [f for f in fc["features"] if f["properties"]["layer"] == "a"][0]
    _assert_ring_close(_ring(a), SQUARE)


@pytest.mark.parametrize(
    "member, why",
    [
        ("../evil.shp", "outside"),
        ("sub/../../evil.shp", "outside"),
        ("/abs/evil.shp", "outside"),
        ("C:/evil.shp", "outside"),
        ("C:evil.shp", "outside"),
    ],
)
def test_zip_slip_member_rejected(member, why, clean_tmp):
    data = _zip_bytes([(member, b"x"), ("ok.dbf", b"x")])
    with pytest.raises(vc.ConvertError) as e:
        vc.convert_bytes("units.zip", data)
    assert why in e.value.error
    assert list(clean_tmp.iterdir()) == []
    assert not (clean_tmp.parent / "evil.shp").exists()


def test_zip_symlink_member_rejected():
    info = zipfile.ZipInfo("units.shp")
    info.create_system = 3  # unix
    info.external_attr = (0o120777 << 16)  # S_IFLNK
    data = _zip_bytes([(info, b"/etc/passwd")])
    with pytest.raises(vc.ConvertError) as e:
        vc.convert_bytes("units.zip", data)
    assert "link" in e.value.error


def test_zip_member_count_capped(monkeypatch):
    monkeypatch.setattr(vc, "MAX_ZIP_MEMBERS", 3)
    data = _zip_bytes([(f"f{i}.dbf", b"x") for i in range(4)])
    with pytest.raises(vc.ConvertError) as e:
        vc.convert_bytes("units.zip", data)
    assert "more than 3 files" in e.value.error


def test_zip_uncompressed_size_capped(monkeypatch, tmp_path):
    monkeypatch.setattr(vc, "MAX_UNCOMPRESSED_BYTES", 1000)
    data = _zip_bytes([("big.geojson", b" " * 5000)])
    with pytest.raises(vc.ConvertError) as e:
        vc.convert_bytes("units.zip", data)
    assert e.value.status == 413
    assert "unpack" in e.value.error


def test_oversize_upload_rejected(monkeypatch):
    monkeypatch.setattr(vc, "MAX_UPLOAD_BYTES", 100)
    with pytest.raises(vc.ConvertError) as e:
        vc.convert_bytes("units.geojson", b"{" + b" " * 200 + b"}")
    assert e.value.status == 413
    assert "larger than" in e.value.error


def test_raster_rejected():
    with pytest.raises(vc.ConvertError) as e:
        vc.convert_bytes("dem.tif", b"II*\x00" + b"\x00" * 64)
    assert e.value.status == 415
    assert "raster" in e.value.error


def test_zip_of_rasters_rejected():
    data = _zip_bytes([("dem.tif", b"II*\x00" + b"\x00" * 64), ("dem.tfw", b"30\n0\n0\n-30\n0\n0\n")])
    with pytest.raises(vc.ConvertError) as e:
        vc.convert_bytes("dem.zip", data)
    assert "raster" in e.value.error


def test_unknown_format_rejected():
    with pytest.raises(vc.ConvertError) as e:
        vc.convert_bytes("notes.docx", b"PK")
    assert e.value.status == 415
    assert "Unsupported format" in e.value.error


def test_missing_shp_error_message(tmp_path):
    data = _shapefile_zip(tmp_path, drop=(".shp",))
    with pytest.raises(vc.ConvertError) as e:
        vc.convert_bytes("units.zip", data)
    assert e.value.error == "The .zip has no .shp file"
    assert ".shx" in e.value.hint and ".dbf" in e.value.hint


def test_shp_without_dbf_names_the_missing_file(tmp_path):
    data = _shapefile_zip(tmp_path, drop=(".dbf",))
    with pytest.raises(vc.ConvertError) as e:
        vc.convert_bytes("units.zip", data)
    assert "units.dbf" in e.value.error


def test_bare_shp_asks_for_a_zip(tmp_path):
    with pytest.raises(vc.ConvertError) as e:
        vc.convert_bytes("units.shp", b"\x00\x00\x27\x0a")
    assert ".zip" in e.value.hint


def test_feature_cap_is_an_error_not_a_truncation(monkeypatch):
    monkeypatch.setattr(vc, "MAX_FEATURES", 2)
    gj = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": mapping(Polygon(SQUARE))} for _ in range(3)]}
    with pytest.raises(vc.ConvertError) as e:
        vc.convert_bytes("units.geojson", json.dumps(gj).encode())
    assert "more than 2 features" in e.value.error


def test_vertex_cap_is_an_error(monkeypatch):
    monkeypatch.setattr(vc, "MAX_VERTICES", 4)
    gj = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": mapping(Polygon(SQUARE))}]}
    with pytest.raises(vc.ConvertError) as e:
        vc.convert_bytes("units.geojson", json.dumps(gj).encode())
    assert "vertices" in e.value.error


@pytest.mark.parametrize(
    "name, marker",
    [
        ("units.json", "<OGRVRTDataSource>"),
        ("units.kml", "<OGRVRTDataSource>"),
        ("units.gpkg", "<OGRVRTDataSource>"),
        ("units.json", '{"type": "gdal_streamed_alg"}'),
    ],
)
def test_vrt_and_gdalg_content_refused_before_gdal_opens_it(name, marker, monkeypatch):
    opened = []
    import pyogrio

    monkeypatch.setattr(pyogrio, "list_layers", lambda *a, **k: opened.append(a) or [])
    with pytest.raises(vc.ConvertError) as e:
        vc.convert_bytes(name, marker.encode())
    assert "Unsupported format" in e.value.error
    assert opened == []


def test_unreadable_file_is_a_clean_error_without_temp_paths(clean_tmp):
    with pytest.raises(vc.ConvertError) as e:
        vc.convert_bytes("units.geojson", b"this is not json")
    assert "could not be read" in e.value.error
    assert str(clean_tmp) not in e.value.error + e.value.hint
    assert list(clean_tmp.iterdir()) == []


def test_timeout(monkeypatch):
    monkeypatch.setattr(vc, "TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(vc, "convert_bytes", lambda name, data: time.sleep(2))
    status, body = vc.handle_upload({"content-type": "multipart/form-data; boundary=b"}, _multipart("a.kml", b"x"))
    assert status == 504
    assert "longer than" in json.loads(body)["error"]


# ---------------------------------------------------------------- request layer


def _multipart(filename, data, field="file", boundary="b"):
    return (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{filename}\"\r\n"
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()


def test_parse_multipart_round_trips_binary():
    data = bytes(range(256)) * 4
    name, got = vc.parse_multipart("multipart/form-data; boundary=b", _multipart("x y.zip", data))
    assert name == "x y.zip" and got == data


def test_parse_multipart_without_a_file_is_an_error():
    with pytest.raises(vc.ConvertError):
        vc.parse_multipart("multipart/form-data; boundary=b", b"--b\r\nContent-Disposition: form-data; name=\"x\"\r\n\r\n1\r\n--b--\r\n")
    with pytest.raises(vc.ConvertError):
        vc.parse_multipart("application/json", b"{}")


def test_is_convert_path():
    assert vc.is_convert_path("/ee-api/convert/vector")
    assert vc.is_convert_path("/ee-api/t/default/convert/vector")
    assert vc.is_convert_path("/ee-api/t/a%20b/convert/vector?x=1")
    assert not vc.is_convert_path("/ee-api/v1/projects/p/value:compute")
    assert not vc.is_convert_path("/geeView/convert/vector")
    assert not vc.is_convert_path("/ee-api/t/a/b/convert/vector")


# ---------------------------------------------------------------- eeAuth proxy app


class _NoEE:
    """A credential source that fails the test if conversion reaches EE."""

    def get_token(self, *a, **k):
        raise AssertionError("conversion must not mint an Earth Engine token")

    def list(self):
        return []


@pytest.fixture
def proxy_client():
    from fastapi.testclient import TestClient
    from geeViz.eeAuth.server import create_proxy_app

    return TestClient(create_proxy_app(creds=_NoEE(), serve_geeview=False))


@pytest.mark.parametrize("path", ["/ee-api/convert/vector", "/ee-api/t/default/convert/vector"])
def test_proxy_endpoint_converts_a_zipped_shapefile(proxy_client, path, tmp_path):
    data = _shapefile_zip(tmp_path)
    r = proxy_client.post(path, files={"file": ("units.zip", data, "application/zip")})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/json")
    fc = r.json()
    _assert_ring_close(_ring(fc["features"][0]), SQUARE)
    # no wider CORS than the proxy's other endpoints (none)
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}


def test_proxy_endpoint_errors_are_json_with_hint(proxy_client, tmp_path):
    data = _shapefile_zip(tmp_path, drop=(".shp",))
    r = proxy_client.post("/ee-api/convert/vector", files={"file": ("units.zip", data, "application/zip")})
    assert r.status_code == 400
    assert r.json() == {"error": "The .zip has no .shp file", "hint": r.json()["hint"]}
    assert r.json()["hint"]


def test_proxy_endpoint_refuses_cross_site_posts(proxy_client):
    r = proxy_client.post(
        "/ee-api/convert/vector",
        files={"file": ("a.geojson", b"{}", "application/json")},
        headers={"Sec-Fetch-Site": "cross-site"},
    )
    assert r.status_code == 403
    assert "error" in r.json()


def test_proxy_endpoint_refuses_oversize_by_content_length(proxy_client, monkeypatch):
    monkeypatch.setattr(vc, "MAX_UPLOAD_BYTES", 10)
    monkeypatch.setattr(vc, "MULTIPART_OVERHEAD_BYTES", 10)
    r = proxy_client.post("/ee-api/convert/vector", files={"file": ("a.geojson", b"{" + b" " * 100 + b"}", "application/json")})
    assert r.status_code == 413
    assert "larger than" in r.json()["error"]


def test_proxy_endpoint_only_takes_post(proxy_client):
    r = proxy_client.get("/ee-api/convert/vector")
    assert r.status_code == 405


# ---------------------------------------------------------------- geeView local server


@pytest.fixture
def geeview_server():
    from geeViz import geeView

    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), geeView._GeeVizRequestHandler)
    srv.daemon_threads = True
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        # no upstream proxy: direct-token mode must still convert
        geeView._set_ee_api_upstream(None)
        yield "http://127.0.0.1:%d" % srv.server_address[1]
    finally:
        srv.shutdown()
        srv.server_close()


def _post(url, filename, data, headers=None):
    body = _multipart(filename, data)
    h = {"Content-Type": "multipart/form-data; boundary=b"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=body, method="POST", headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


@pytest.mark.parametrize("path", ["/ee-api/convert/vector", "/ee-api/t/default/convert/vector"])
def test_geeview_server_converts_without_a_proxy(geeview_server, path, tmp_path):
    status, headers, body = _post(geeview_server + path, "units.zip", _shapefile_zip(tmp_path))
    assert status == 200, body
    assert headers["Content-Type"].startswith("application/json")
    fc = json.loads(body)
    _assert_ring_close(_ring(fc["features"][0]), SQUARE)
    assert "Access-Control-Allow-Origin" not in headers


def test_geeview_server_errors_are_json(geeview_server):
    status, _, body = _post(geeview_server + "/ee-api/convert/vector", "dem.tif", b"II*\x00")
    assert status == 415
    j = json.loads(body)
    assert "raster" in j["error"] and j["hint"]


def test_geeview_server_refuses_cross_site_and_oversize(geeview_server, monkeypatch):
    status, _, _ = _post(geeview_server + "/ee-api/convert/vector", "a.geojson", b"{}", {"Sec-Fetch-Site": "cross-site"})
    assert status == 403
    monkeypatch.setattr(vc, "MAX_UPLOAD_BYTES", 10)
    monkeypatch.setattr(vc, "MULTIPART_OVERHEAD_BYTES", 10)
    status, _, body = _post(geeview_server + "/ee-api/convert/vector", "a.geojson", b"{" + b" " * 100 + b"}")
    assert status == 413
    assert "larger than" in json.loads(body)["error"]
