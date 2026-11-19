"""Convert an uploaded vector file to a GeoJSON FeatureCollection in EPSG:4326.

Backs ``POST <proxy base>/convert/vector`` on both servers that serve
the geeViz viewer: the eeAuth proxy app (:mod:`geeViz.eeAuth.server`,
mounted at ``/ee-api``) and geeViz's own local static server
(``geeView._GeeVizRequestHandler``, for direct-token mode). Both call
:func:`handle_upload`, so the two behave the same.

Reads with GDAL in-process through pyogrio (its wheels bundle GDAL with
the LIBKML driver); nothing is shelled out and no third-party service is
contacted. Supported: a zipped shapefile (``.zip``), KML, KMZ, GeoJSON
(``.geojson``/``.json``), GeoPackage, GPX and FlatGeobuf. Every layer is
read and merged; each feature gets a ``layer`` property naming its layer
(a source field already called ``layer`` is kept as ``layer_original``),
and the response says when layers were combined.

Uploads are untrusted, so:

- the upload, the unpacked size and the zip member count are capped
  (see the limits below);
- zips and KMZs are unpacked by this module, never by GDAL, into a fresh
  temp dir, refusing members that would land outside it (zip slip),
  symbolic links and encrypted members, and counting the bytes actually
  written; only vector files and shapefile sidecars are unpacked;
- text files carrying GDAL's VRT or streamed-algorithm markers are
  refused before GDAL opens them (both can read other local files), and
  each layer's driver must be one expected for its extension;
- raster files are refused;
- more features or vertices than the caps is an error, never a silent
  truncation;
- conversion runs in a worker thread with a timeout and at most
  ``MAX_CONCURRENT`` at once, and the temp dir is always removed.

The endpoints add no CORS headers (same as the proxy's other routes) and
refuse browser requests marked ``Sec-Fetch-Site: cross-site``.
"""
from __future__ import annotations

import datetime as _dt
import decimal
import email.parser
import email.policy
import json
import math
import os
import re
import shutil
import stat
import tempfile
import threading
import zipfile

# ---- limits (documented in eeAuth/README.md) ----
MAX_UPLOAD_BYTES = 50 * 1024 * 1024          # the uploaded file
MULTIPART_OVERHEAD_BYTES = 1024 * 1024       # form headers around it
MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024   # a zip or KMZ, unpacked
MAX_ZIP_MEMBERS = 1000
MAX_FEATURES = 50_000
MAX_VERTICES = 2_000_000
MAX_OUTPUT_BYTES = 150 * 1024 * 1024         # the GeoJSON response
TIMEOUT_SECONDS = 60
MAX_CONCURRENT = 2

ENDPOINT = "/convert/vector"

# extension -> GDAL drivers allowed to read it
_DRIVERS = {
    ".shp": {"ESRI Shapefile"},
    ".geojson": {"GeoJSON"},
    ".json": {"GeoJSON", "ESRIJSON", "TopoJSON"},
    ".kml": {"LIBKML", "KML"},
    ".gpkg": {"GPKG"},
    ".gpx": {"GPX"},
    ".fgb": {"FlatGeobuf"},
}
_SIDECARS = {".shx", ".dbf", ".prj", ".cpg", ".sbn", ".sbx", ".qix", ".xml"}
_ZIPS = {".zip", ".kmz"}
_RASTERS = {
    ".tif", ".tiff", ".img", ".jp2", ".png", ".jpg", ".jpeg", ".gif", ".bmp",
    ".nc", ".hdf", ".h5", ".grib", ".grb", ".grb2", ".asc", ".dem", ".vrt",
    ".sid", ".ecw", ".bil", ".dt0", ".dt1", ".dt2", ".cog", ".webp",
}
SUPPORTED = "a .zip shapefile, .kml, .kmz, .geojson, .json, .gpkg, .gpx or .fgb file"
# GDAL formats that can reference other files or run GDAL commands.
_DANGEROUS_MARKERS = (b"<OGRVRTDataSource", b"<VRTDataset", b"gdal_streamed_alg")
# Binary formats must start with their own signature.
_MAGIC = {".gpkg": b"SQLite format 3\x00", ".fgb": b"fgb", ".shp": b"\x00\x00\x27\x0a"}

_CONVERT_PATH = re.compile(r"^/ee-api(?:/t/[^/]+)?/convert/vector/?$")
_SLOTS = threading.BoundedSemaphore(MAX_CONCURRENT)


class ConvertError(Exception):
    """A conversion that cannot be done; ``error`` and ``hint`` go to the user."""

    def __init__(self, error, hint="", status=400):
        super().__init__(error)
        self.error = error
        self.hint = hint
        self.status = status

    def payload(self):
        return {"error": self.error, "hint": self.hint}


def _mb(n):
    return f"{n / (1024 * 1024):g} MB"


def is_convert_path(path, prefix="/ee-api"):
    """True for ``<prefix>/convert/vector`` and ``<prefix>/t/<tenant>/convert/vector``."""
    p = path.split("?", 1)[0]
    if prefix != "/ee-api":
        if not p.startswith(prefix):
            return False
        p = "/ee-api" + p[len(prefix):]
    return bool(_CONVERT_PATH.match(p))


# ---------------------------------------------------------------- staging


def _ext(name):
    return os.path.splitext(name)[1].lower()


def _safe_name(name):
    base = os.path.basename(str(name).replace("\\", "/"))
    stem, ext = os.path.splitext(base)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._") or "upload"
    return stem[:100] + ext.lower()


def _member_path(raw):
    """A zip member's relative path, or raise if it would escape the folder."""
    n = raw.replace("\\", "/")
    parts = n.split("/")
    if n.startswith("/") or ".." in parts or ":" in parts[0] or re.match(r"^[A-Za-z]:", n):
        raise ConvertError(
            "The .zip has a file that would land outside its folder",
            "Zip the files again without absolute paths or '..' in their names.",
        )
    clean = [_safe_name(p) for p in parts if p not in ("", ".")]
    return clean


def _unpack(path, dest):
    """Unpack the vector files of a zip or KMZ at ``path`` into ``dest``."""
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError):
        raise ConvertError(f"The {_ext(path)} file could not be opened as a zip archive",
                           "Check that the file downloaded completely.")
    seen = []
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_ZIP_MEMBERS:
            raise ConvertError(f"The archive has more than {MAX_ZIP_MEMBERS} files",
                               "Zip only the files that make up the layer.", 413)
        declared = 0
        for i in infos:
            _member_path(i.filename)
            if stat.S_ISLNK(i.external_attr >> 16):
                raise ConvertError("The archive has a symbolic link in it",
                                   "Zip the files themselves, not links to them.")
            if i.flag_bits & 0x1:
                raise ConvertError("The archive is encrypted", "Zip the files without a password.")
            declared += i.file_size
        if declared > MAX_UNCOMPRESSED_BYTES:
            raise ConvertError(f"The archive would unpack to more than {_mb(MAX_UNCOMPRESSED_BYTES)}",
                               "Upload a smaller area or fewer layers.", 413)
        written = 0
        root = os.path.realpath(dest)
        for i in infos:
            if i.is_dir():
                continue
            parts = _member_path(i.filename)
            if not parts:
                continue
            seen.append(_ext(parts[-1]))
            if _ext(parts[-1]) not in set(_DRIVERS) | _SIDECARS:
                continue
            out = os.path.realpath(os.path.join(dest, *parts))
            if os.path.commonpath([root, out]) != root:
                raise ConvertError("The .zip has a file that would land outside its folder",
                                   "Zip the files again without absolute paths or '..' in their names.")
            os.makedirs(os.path.dirname(out), exist_ok=True)
            # Count what is really written: a zip's headers can lie.
            with zf.open(i) as src, open(out, "wb") as dst:
                while True:
                    chunk = src.read(1 << 20)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > MAX_UNCOMPRESSED_BYTES:
                        raise ConvertError(
                            f"The archive would unpack to more than {_mb(MAX_UNCOMPRESSED_BYTES)}",
                            "Upload a smaller area or fewer layers.", 413)
                    dst.write(chunk)
    return seen


def _datasets(folder, kind, seen):
    """The vector datasets unpacked into ``folder`` (``kind`` is .zip or .kmz)."""
    found = []
    for r, _, names in os.walk(folder):
        for n in sorted(names):
            found.append(os.path.join(r, n))
    found.sort()
    if kind == ".kmz":
        kmls = [p for p in found if _ext(p) == ".kml"]
        if not kmls:
            raise ConvertError("The .kmz has no .kml file", "A KMZ is a zip with a doc.kml inside.")
        return kmls
    lower = {p.lower(): p for p in found}
    shps = [p for p in found if _ext(p) == ".shp"]
    for shp in shps:
        stem = os.path.splitext(shp)[0]
        for side in (".shx", ".dbf"):
            if (stem + side).lower() not in lower:
                raise ConvertError(
                    f"The .zip has {os.path.basename(shp)} but no {os.path.basename(stem)}{side}",
                    "A shapefile needs its .shp, .shx, .dbf and .prj files together in the .zip.")
    others = [p for p in found if _ext(p) in _DRIVERS and _ext(p) != ".shp"]
    if shps or others:
        return shps + others
    if any(e in _RASTERS for e in seen):
        raise ConvertError("Unsupported format: the .zip holds raster data, not vector features",
                           "Upload " + SUPPORTED + ".", 415)
    raise ConvertError("The .zip has no .shp file",
                       "A shapefile needs its .shp, .shx, .dbf and .prj files together in the .zip.")


def _sniff(path):
    """Refuse GDAL formats that can reach other files, before GDAL opens them."""
    with open(path, "rb") as fh:
        head = fh.read(1 << 16)
    magic = _MAGIC.get(_ext(path))
    if (magic and not head.startswith(magic)) or any(m.lower() in head.lower() for m in _DANGEROUS_MARKERS):
        raise ConvertError(f"Unsupported format: {os.path.basename(path)} is not plain " +
                           ("GeoJSON" if _ext(path) in (".json", ".geojson") else _ext(path)[1:].upper()),
                           "Upload " + SUPPORTED + ".", 415)


# ---------------------------------------------------------------- reading


def _clean_msg(e, folder):
    s = str(e).replace(folder, "").replace(folder.replace("\\", "/"), "")
    s = re.sub(r"[\x00-\x1f]+", " ", s).strip()
    return s[:300]


def _is_4326(crs):
    try:
        return crs.equals("EPSG:4326") or crs.equals("OGC:CRS84")
    except Exception:
        return False


def _read(paths, folder, notes):
    """[(layer name, GeoDataFrame in EPSG:4326)] for every layer of every dataset."""
    import geopandas as gpd
    import pyogrio
    import shapely

    out = []
    total = 0
    vertices = 0
    for p in paths:
        _sniff(p)
        label = os.path.basename(p)
        try:
            layers = [str(row[0]) for row in pyogrio.list_layers(p)]
        except Exception as e:
            raise ConvertError(f"{label} could not be read: {_clean_msg(e, folder)}",
                               "Check that the file is " + SUPPORTED + " and not damaged.", 422)
        for layer in layers:
            try:
                info = pyogrio.read_info(p, layer=layer)
            except Exception as e:
                raise ConvertError(f"{label} could not be read: {_clean_msg(e, folder)}",
                                   "Check that the file is not damaged.", 422)
            if info.get("driver") not in _DRIVERS[_ext(p)]:
                raise ConvertError(f"Unsupported format: {label} was read as {info.get('driver')}",
                                   "Upload " + SUPPORTED + ".", 415)
            if not info.get("geometry_type"):
                continue  # an attribute table without shapes
            n = info.get("features", -1)
            if n is not None and n >= 0 and total + n > MAX_FEATURES:
                raise _too_many_features()
            try:
                gdf = pyogrio.read_dataframe(p, layer=layer, max_features=MAX_FEATURES - total + 1)
            except Exception as e:
                raise ConvertError(f"{label} could not be read: {_clean_msg(e, folder)}",
                                   "Check that the file is not damaged.", 422)
            if not isinstance(gdf, gpd.GeoDataFrame) or gdf.empty:
                continue
            total += len(gdf)
            if total > MAX_FEATURES:
                raise _too_many_features()
            vertices += int(shapely.get_num_coordinates(gdf.geometry.values).sum())
            if vertices > MAX_VERTICES:
                raise ConvertError(f"The file has more than {MAX_VERTICES:,} vertices",
                                   "Simplify the shapes or upload a smaller area.", 422)
            gdf = _to_4326(gdf, label, layer, notes)
            out.append((layer, gdf))
    if not out:
        raise ConvertError("The file has no features", "Upload a file with at least one shape.", 422)
    return out


def _too_many_features():
    return ConvertError(f"The file has more than {MAX_FEATURES:,} features",
                        "Upload fewer features, or dissolve them into fewer shapes first.", 422)


def _to_4326(gdf, label, layer, notes):
    crs = gdf.crs
    if crs is None:
        b = gdf.total_bounds
        if all(math.isfinite(v) for v in b) and -180 <= b[0] and b[2] <= 180 and -90 <= b[1] and b[3] <= 90:
            notes.append(f"{label} ({layer}) has no projection (.prj); its coordinates were read as longitude/latitude (EPSG:4326).")
            return gdf.set_crs("EPSG:4326")
        raise ConvertError(f"{label} has no projection (.prj) and its coordinates are not longitude/latitude",
                           "Include the .prj file in the .zip so the shapes can be placed on the map.", 422)
    if _is_4326(crs):
        return gdf
    try:
        name = crs.to_string()
        if len(name) > 60:
            name = crs.name
        out = gdf.to_crs("EPSG:4326")
    except Exception as e:
        raise ConvertError(f"{label}: its projection could not be converted to longitude/latitude",
                           str(e)[:200], 422)
    notes.append(f"Reprojected {layer} from {name} to EPSG:4326.")
    return out


# ---------------------------------------------------------------- GeoJSON


def _json_default(v):
    if isinstance(v, (_dt.datetime, _dt.date, _dt.time)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (bytes, bytearray, memoryview)):
        return None
    if hasattr(v, "item"):  # numpy scalars
        try:
            return v.item()
        except Exception:
            pass
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


def _features(layers):
    feats = []
    for layer, gdf in layers:
        cols = list(gdf.columns)
        if "layer" in cols:
            gdf = gdf.rename(columns={"layer": "layer_original"})
        for f in gdf.iterfeatures(na="null", show_bbox=False, drop_id=True):
            props = f.get("properties") or {}
            props["layer"] = layer
            for k, v in list(props.items()):
                if isinstance(v, float) and not math.isfinite(v):
                    props[k] = None
            feats.append({"type": "Feature", "properties": props, "geometry": f.get("geometry")})
    return feats


def convert_bytes(filename, data):
    """Convert one uploaded file. Returns a GeoJSON FeatureCollection dict.

    Foreign members: ``layers`` (``[{name, features}]``) and ``notes``
    (plain-language sentences: layers combined, reprojection, a missing
    projection read as longitude/latitude). Raises :class:`ConvertError`.
    """
    if len(data) > MAX_UPLOAD_BYTES:
        raise ConvertError(f"The file is larger than {_mb(MAX_UPLOAD_BYTES)}",
                           "Upload a smaller area or fewer features.", 413)
    name = _safe_name(filename or "upload")
    ext = _ext(name)
    if ext == ".shp":
        raise ConvertError("A .shp file alone cannot be read",
                           "Zip the .shp with its .shx, .dbf and .prj files and upload the .zip.")
    if ext in _RASTERS:
        raise ConvertError(f"Unsupported format: {ext} is a raster format",
                           "Upload " + SUPPORTED + ". Rasters cannot be used as an area.", 415)
    if ext not in _DRIVERS and ext not in _ZIPS:
        raise ConvertError(f"Unsupported format: {ext or name}", "Upload " + SUPPORTED + ".", 415)
    try:
        import geopandas  # noqa: F401
        import pyogrio  # noqa: F401
    except ImportError:
        raise ConvertError("Vector conversion is not available on this geeViz server",
                           "Install geopandas and pyogrio (pip install geeViz[mcp]) and restart it.", 501)

    folder = tempfile.mkdtemp(prefix="geeviz_vconv_")
    try:
        src = os.path.join(folder, "upload" + ext)
        with open(src, "wb") as fh:
            fh.write(data)
        if ext in _ZIPS:
            dest = os.path.join(folder, "unpacked")
            os.makedirs(dest)
            seen = _unpack(src, dest)
            os.remove(src)
            paths = _datasets(dest, ext, seen)
        else:
            paths = [src]
        notes = []
        layers = _read(paths, folder, notes)
        if len(layers) > 1:
            notes.insert(0, "Combined %d layers: %s. Each feature's layer property names its layer." % (
                len(layers), ", ".join(f"{n} ({len(g)})" for n, g in layers)))
        return {
            "type": "FeatureCollection",
            "features": _features(layers),
            "layers": [{"name": n, "features": len(g)} for n, g in layers],
            "notes": notes,
        }
    finally:
        shutil.rmtree(folder, ignore_errors=True)


# ---------------------------------------------------------------- requests


def parse_multipart(content_type, body):
    """``(filename, bytes)`` of the one file in a multipart/form-data body."""
    if not content_type or "multipart/form-data" not in content_type.lower():
        raise ConvertError("Send the file as multipart/form-data",
                           "POST a form with one file field.", 400)
    head = b"Content-Type: " + content_type.encode("latin-1") + b"\r\nMIME-Version: 1.0\r\n\r\n"
    msg = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(head + body)
    files = []
    if msg.is_multipart():
        for part in msg.iter_parts():
            fn = part.get_filename()
            if fn:
                files.append((fn, part.get_payload(decode=True) or b""))
    if not files:
        raise ConvertError("No file was sent", "POST a form with one file field.", 400)
    if len(files) > 1:
        raise ConvertError("Send one file at a time", "Zip a shapefile's files together.", 400)
    return files[0]


def _run_with_timeout(fn, *args):
    if not _SLOTS.acquire(timeout=TIMEOUT_SECONDS):
        raise ConvertError("The server is busy converting other files", "Try again in a minute.", 503)
    box = {}

    def work():
        try:
            box["value"] = fn(*args)
        except BaseException as e:  # noqa: BLE001 - handed to the caller
            box["error"] = e
        finally:
            _SLOTS.release()

    t = threading.Thread(target=work, name="geeviz-vector-convert", daemon=True)
    t.start()
    t.join(TIMEOUT_SECONDS)
    if t.is_alive():
        raise ConvertError(f"Converting the file took longer than {TIMEOUT_SECONDS:g} seconds",
                           "Upload a smaller area or fewer features.", 504)
    if "error" in box:
        raise box["error"]
    return box["value"]


def _header(headers, name):
    for k, v in headers.items():
        if k.lower() == name:
            return v
    return None


def request_rejection(headers):
    """``(status, body)`` to send without reading the body, or ``None``.

    Refuses cross-site browser posts and declared oversize bodies.
    """
    if (_header(headers, "sec-fetch-site") or "").lower() == "cross-site":
        return _reply(ConvertError("Cross-site uploads are not accepted",
                                   "Upload from the geeViz page this server serves.", 403))
    try:
        n = int(_header(headers, "content-length") or 0)
    except ValueError:
        n = 0
    if n > max_body_bytes():
        return _reply(_too_big())
    return None


def max_body_bytes():
    return MAX_UPLOAD_BYTES + MULTIPART_OVERHEAD_BYTES


def _too_big():
    return ConvertError(f"The file is larger than {_mb(MAX_UPLOAD_BYTES)}",
                        "Upload a smaller area or fewer features.", 413)


def _reply(err):
    return err.status, json.dumps(err.payload()).encode("utf-8")


def oversize_reply():
    """``(413, body)`` for a body found to be over :func:`max_body_bytes` while reading."""
    return _reply(_too_big())


def handle_upload(headers, body):
    """Convert a request: ``(status, JSON bytes)``. Never raises.

    ``headers`` is any mapping of request headers; ``body`` the raw
    request body, read by the caller up to :func:`max_body_bytes` plus one.
    """
    rejected = request_rejection(headers)
    if rejected:
        return rejected
    if len(body) > max_body_bytes():
        return _reply(_too_big())
    try:
        filename, data = parse_multipart(_header(headers, "content-type"), body)
        fc = _run_with_timeout(convert_bytes, filename, data)
        out = json.dumps(fc, default=_json_default, allow_nan=False).encode("utf-8")
        if len(out) > MAX_OUTPUT_BYTES:
            raise ConvertError(f"The converted file is larger than {_mb(MAX_OUTPUT_BYTES)}",
                               "Upload fewer features or simpler shapes.", 422)
        return 200, out
    except ConvertError as e:
        return _reply(e)
    except Exception as e:  # noqa: BLE001 - every failure is a JSON error
        return _reply(ConvertError("The file could not be converted",
                                   re.sub(r"[\x00-\x1f]+", " ", str(e))[:300], 500))
