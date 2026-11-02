"""HRRR (High-Resolution Rapid Refresh) weather in Earth Engine, on demand.

HRRR is NOAA's 3 km, hourly-updating model for the lower 48 states. It
is not in the Earth Engine catalog. NOAA publishes it as GRIB2 in the
public bucket ``gs://high-resolution-rapid-refresh`` (2014-07-30 to now),
which Earth Engine cannot read. :func:`getHRRR` bridges the two: for a
region and a time window it

1. works out which HRRR runs and forecast hours cover the window,
2. downloads only the fields asked for, using each file's ``.idx`` byte
   index (about 1.5 MB per field per hour instead of a 160 MB file),
3. crops them to the region, converts units and writes one small Cloud
   Optimized GeoTIFF per hour to a bucket you own, and
4. returns an ``ee.ImageCollection`` that reads those files in place with
   ``ee.Image.loadGeoTIFF``. Nothing is ingested, so there is no wait.

Files are cached by run, forecast hour, variables and region, so
asking again costs nothing.

It follows :mod:`geeViz.weather`'s conventions, so an HRRR image can be
compared with a GFS or ECMWF one from :func:`geeViz.weather.getForecastData`:

* ``system:time_start`` is the **valid** time, not the run time,
* bands are named for the variable (:data:`VARIABLES` keys; ``"wind"``
  gives ``u`` and ``v``),
* values are in canonical units, and ``wx_units`` says which.

Which data each hour comes from
===============================

For every hour in ``[startDate, endDate)``:

* **Hours that have passed** use the run that started at that hour, at
  forecast hour 0: HRRR's own analysis, the best estimate of what
  happened. Precipitation has no hour-0 value, so it comes from the
  previous run's first forecast hour (the hour ending at that time).
* **Hours still ahead** come from ONE run, the newest that reaches the
  end of the window. Most runs reach 18 hours; the 00, 06, 12 and 18 UTC
  runs reach 48. Hours before that run's start come from analyses.
* A window that ends beyond 48 hours from the newest long run raises,
  saying where coverage ends. Use :func:`geeViz.weather.getForecastData`
  (GFS reaches 16 days) for longer.

Pitfalls
========

**HRRR's u and v are relative to its grid, not to north.** The GRIB2
component flag says so and GDAL does not correct for it. On HRRR's
Lambert grid the error grows with distance from 97.5 W: about 5 degrees
at Denver and 15 at Seattle. :func:`getHRRR` rotates them to
east/north (:func:`rotate_to_earth`).

**Earth Engine caches a file by its path.** A file overwritten with
different content can keep returning the old values. Cache names here
are fully determined by their content (run, hour, variables, region,
:data:`CACHE_VERSION`), so a name never changes meaning.

**loadGeoTIFF reads LZW, JPEG, ZLIB, PACKBITS and DEFLATE only.** ZSTD
and LERC files are refused, so files are written with DEFLATE.

**Earth Engine must be able to read your bucket.** Files are written
with your Google Cloud credentials and read by Earth Engine with the
credentials it runs under. If those differ, grant the Earth Engine
account read access to the bucket.

Requires ``rasterio`` (with GDAL's GRIB driver, included in its wheels),
``google-cloud-storage`` and ``numpy``; ``tqdm`` for the status bar outside
notebooks.
"""

import concurrent.futures
import datetime
import hashlib
import os
import tempfile
import threading
import time
import urllib.error
import urllib.request

import ee

SOURCE_URL = "https://storage.googleapis.com/high-resolution-rapid-refresh"
ARCHIVE_START = datetime.datetime(2014, 7, 30, 18)
CACHE_VERSION = "v1"
LONG_RUN_HOURS = (0, 6, 12, 18)
LONG_HORIZON = 48
SHORT_HORIZON = 18
# One worker's time per hour, measured: fetch ~3 s, decode and write ~3 s,
# upload ~4 s, whatever the area. ``workers`` run at once.
SECONDS_PER_HOUR_ESTIMATE = 12

# Lambert conformal grid HRRR is published on: standard parallel 38.5 N,
# central meridian 97.5 W. The wind rotation depends on both.
STANDARD_PARALLEL = 38.5
CENTRAL_MERIDIAN = -97.5

VARIABLES = {
    "temperature_2m": {"grib": ("TMP", "2 m above ground"), "units": "C",
                       "scale": 1.0, "offset": -273.15, "label": "2 m temperature"},
    "dewpoint_2m": {"grib": ("DPT", "2 m above ground"), "units": "C",
                    "scale": 1.0, "offset": -273.15, "label": "2 m dewpoint"},
    "relative_humidity_2m": {"grib": ("RH", "2 m above ground"), "units": "%",
                             "label": "2 m relative humidity"},
    "u": {"grib": ("UGRD", "10 m above ground"), "units": "m/s",
          "label": "10 m wind, eastward"},
    "v": {"grib": ("VGRD", "10 m above ground"), "units": "m/s",
          "label": "10 m wind, northward"},
    "wind_gust": {"grib": ("GUST", "surface"), "units": "m/s", "label": "Surface wind gust"},
    # A one-hour accumulation in kg/m^2, which is mm of water in the hour
    # ending at the valid time: numerically mm/hr.
    "precipitation": {"grib": ("APCP", "surface"), "units": "mm/hr",
                      "accumulated": True, "label": "Precipitation"},
    "total_cloud_cover": {"grib": ("TCDC", "entire atmosphere"), "units": "%",
                          "label": "Total cloud cover"},
    # HRRR-Smoke near-surface concentration of wildfire smoke.
    "smoke_near_surface": {"grib": ("MASSDEN", "8 m above ground"), "units": "ug/m3",
                           "scale": 1e9, "label": "Near-surface smoke"},
}
"""What :func:`getHRRR` can return. Keys match :data:`geeViz.weather.VARIABLES`
where the quantity is the same. ``"wind"`` is shorthand for ``u`` and ``v``."""

DEFAULT_VARIABLES = ("temperature_2m", "relative_humidity_2m", "wind", "wind_gust")


# --------------------------------------------------------------------------
# Time handling
# --------------------------------------------------------------------------

def _to_utc(value):
    """A naive UTC datetime from a str, datetime, date or epoch ms."""
    if isinstance(value, (int, float)):
        return datetime.datetime.fromtimestamp(value / 1000.0, datetime.timezone.utc).replace(tzinfo=None)
    if isinstance(value, str):
        value = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    elif isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
        value = datetime.datetime(value.year, value.month, value.day)
    if not isinstance(value, datetime.datetime):
        raise TypeError(f"Expected a date string, datetime or epoch ms, got {type(value).__name__}")
    if value.tzinfo is not None:
        value = value.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return value


def _ceil_hour(t):
    floor = t.replace(minute=0, second=0, microsecond=0)
    return floor if floor == t else floor + datetime.timedelta(hours=1)


def _ms(t):
    return int((t - datetime.datetime(1970, 1, 1)).total_seconds() * 1000)


def valid_hours(startDate, endDate, hourStep=1):
    """Every whole UTC hour in ``[startDate, endDate)``, ``hourStep`` apart."""
    start, end = _to_utc(startDate), _to_utc(endDate)
    if end <= start:
        raise ValueError(f"endDate ({end}) must be after startDate ({start}).")
    if int(hourStep) != hourStep or hourStep < 1:
        raise ValueError(f"hourStep must be a whole number of hours, 1 or more, got {hourStep}.")
    out, t = [], _ceil_hour(start)
    while t < end:
        out.append(t)
        t += datetime.timedelta(hours=int(hourStep))
    if not out:
        raise ValueError(f"No whole hour falls in [{start}, {end}).")
    return out


def horizon(run):
    """How many forecast hours an HRRR run reaches."""
    return LONG_HORIZON if run.hour in LONG_RUN_HOURS else SHORT_HORIZON


# --------------------------------------------------------------------------
# NOAA's bucket
# --------------------------------------------------------------------------

def grib_url(run, fhour):
    return (f"{SOURCE_URL}/hrrr.{run:%Y%m%d}/conus/"
            f"hrrr.t{run:%H}z.wrfsfcf{fhour:02d}.grib2")


def _get(url, byte_range=None, retries=4):
    headers = {"Range": f"bytes={byte_range[0]}-{byte_range[1]}"} if byte_range else {}
    for attempt in range(retries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60).read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise FileNotFoundError(url) from None
            if attempt == retries - 1:
                raise
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            if attempt == retries - 1:
                raise
        time.sleep(1 + attempt)


def published(run, fhour):
    """True when NOAA has published this run's forecast hour."""
    try:
        req = urllib.request.Request(grib_url(run, fhour) + ".idx", method="HEAD")
        urllib.request.urlopen(req, timeout=30)
        return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise


def latest_run(now, search_hours=6):
    """The newest run whose hour 0 is published, at or before ``now``."""
    run = now.replace(minute=0, second=0, microsecond=0)
    for _ in range(search_hours + 1):
        if published(run, 0):
            return run
        run -= datetime.timedelta(hours=1)
    raise RuntimeError(f"No HRRR run published in the {search_hours} hours before {now:%Y-%m-%d %H:%M} UTC.")


def parse_idx(text):
    """``.idx`` lines as dicts with byte ``start`` and ``end`` (inclusive; None at EOF)."""
    rows = [line.split(":") for line in text.splitlines() if line.strip()]
    out = []
    for i, p in enumerate(rows):
        end = int(rows[i + 1][1]) - 1 if i + 1 < len(rows) else None
        out.append({"start": int(p[1]), "end": end, "var": p[3], "level": p[4], "step": p[5]})
    return out


def find_field(idx, var, level, step=None):
    """The idx entry for one field. ``step`` pins e.g. ``"2-3 hour acc fcst"``."""
    for row in idx:
        if row["var"] == var and row["level"] == level and (step is None or row["step"] == step):
            return row
    return None


# --------------------------------------------------------------------------
# Planning: which file serves each hour
# --------------------------------------------------------------------------

def plan(hours, latest, check_published=published):
    """For each valid hour, the run and forecast hour that serve it.

    Returns a list of dicts: ``valid``, ``run``, ``fhour``, ``source``
    (``"analysis"`` or ``"forecast"``) and ``precip_run``/``precip_fhour``,
    the file whose one-hour accumulation ends at ``valid``.
    """
    end = hours[-1]
    forecast_run = None
    if end > latest:
        candidates = [latest - datetime.timedelta(hours=k) for k in range(0, 24)]
        for run in candidates:
            lead = int((end - run).total_seconds() // 3600)
            if lead <= horizon(run) and check_published(run, lead):
                forecast_run = run
                break
        if forecast_run is None:
            reach = max((r + datetime.timedelta(hours=horizon(r)) for r in candidates
                         if r.hour in LONG_RUN_HOURS), default=latest)
            raise ValueError(
                f"HRRR does not reach {end:%Y-%m-%d %H:%M} UTC yet. The newest published "
                f"run is {latest:%Y-%m-%d %H}z; the newest long run reaches "
                f"{reach:%Y-%m-%d %H:%M} UTC at most (48 hours from 00/06/12/18z, 18 from "
                f"other runs). End the window earlier, or use "
                f"geeViz.weather.getForecastData(..., model='gfs'), which reaches 16 days.")
    split = forecast_run if forecast_run is not None else latest
    out = []
    for t in hours:
        if t < ARCHIVE_START:
            raise ValueError(f"HRRR's archive on Google Cloud starts {ARCHIVE_START:%Y-%m-%d %H}z; "
                             f"{t:%Y-%m-%d %H}z is earlier.")
        if t <= split:
            out.append({"valid": t, "run": t, "fhour": 0, "source": "analysis",
                        "precip_run": t - datetime.timedelta(hours=1), "precip_fhour": 1})
        else:
            lead = int((t - split).total_seconds() // 3600)
            out.append({"valid": t, "run": split, "fhour": lead, "source": "forecast",
                        "precip_run": split, "precip_fhour": lead})
    return out


# --------------------------------------------------------------------------
# Grid work
# --------------------------------------------------------------------------

def rotate_to_earth(u, v, lon):
    """Rotate HRRR's grid-relative ``u``/``v`` to eastward/northward.

    On a Lambert conformal grid, grid north turns away from true north by
    ``sin(standard parallel) * (lon - central meridian)``. The same
    rotation as NCL's ``wrf_uvmet`` and NCEP's ``wgrib2 -new_grid_winds earth``.
    """
    import numpy as np

    alpha = np.deg2rad(np.sin(np.deg2rad(STANDARD_PARALLEL)) * (lon - CENTRAL_MERIDIAN))
    cos, sin = np.cos(alpha), np.sin(alpha)
    return u * cos + v * sin, v * cos - u * sin


def _bounds(region):
    """``(west, south, east, north)`` from a geometry, feature, collection or list."""
    if isinstance(region, (list, tuple)) and len(region) == 4:
        return tuple(float(x) for x in region)
    if isinstance(region, (ee.Feature, ee.FeatureCollection)):
        region = region.geometry()
    if isinstance(region, ee.Geometry):
        ring = region.bounds(1, "EPSG:4326").coordinates().get(0).getInfo()
        xs, ys = [p[0] for p in ring], [p[1] for p in ring]
        return min(xs), min(ys), max(xs), max(ys)
    raise TypeError("region must be an ee.Geometry, ee.Feature, ee.FeatureCollection "
                    "or [west, south, east, north].")


def grid_window(src, bbox, pad=2):
    """The HRRR grid window (col0, row0, col1, row1) covering ``bbox``, padded by ``pad`` cells."""
    import numpy as np
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds

    b = transform_bounds("EPSG:4326", src.crs, *bbox, densify_pts=21)
    w = from_bounds(*b, transform=src.transform)
    col0 = max(int(np.floor(w.col_off)) - pad, 0)
    row0 = max(int(np.floor(w.row_off)) - pad, 0)
    col1 = min(int(np.ceil(w.col_off + w.width)) + pad, src.width)
    row1 = min(int(np.ceil(w.row_off + w.height)) + pad, src.height)
    if col1 <= col0 or row1 <= row0:
        raise ValueError(f"Region {bbox} is outside HRRR's CONUS domain.")
    return col0, row0, col1, row1


def _expand(variables):
    if variables is None:
        variables = DEFAULT_VARIABLES
    if isinstance(variables, str):
        variables = [variables]
    bands = []
    for name in variables:
        for b in (("u", "v") if name == "wind" else (name,)):
            if b not in VARIABLES:
                raise ValueError(f"Unknown HRRR variable {name!r}. Choose from 'wind' or "
                                 f"{', '.join(repr(k) for k in VARIABLES)}.")
            if b not in bands:
                bands.append(b)
    return bands


# --------------------------------------------------------------------------
# One hour: fetch, decode, crop, write, upload
# --------------------------------------------------------------------------

def _messages(step, bands, idx_cache):
    """Byte ranges to fetch for one planned hour, grouped by file."""
    groups = {}
    for b in bands:
        spec = VARIABLES[b]
        var, level = spec["grib"]
        if spec.get("accumulated"):
            run, fh = step["precip_run"], step["precip_fhour"]
            want = f"{fh - 1}-{fh} hour acc fcst"
        else:
            run, fh, want = step["run"], step["fhour"], None
        url = grib_url(run, fh)
        if url not in idx_cache:
            idx_cache[url] = parse_idx(_get(url + ".idx").decode())
        row = find_field(idx_cache[url], var, level, want)
        if row is None:
            raise ValueError(f"{run:%Y-%m-%d %H}z f{fh:02d} has no {var} at {level}"
                             f"{' (' + want + ')' if want else ''}, needed for {b!r}. "
                             f"HRRR's fields changed over its versions; this one may "
                             f"not exist that far back.")
        groups.setdefault(url, []).append((b, row))
    return groups


def _in_notebook():
    try:
        from IPython import get_ipython

        shell = get_ipython()
        return shell is not None and "IPKernelApp" in shell.config
    except Exception:
        return False


class _NotebookBar:
    """A status bar drawn as a display that updates in place.

    Unlike a widget, the saved notebook keeps its final state, so the
    file shows what happened rather than a bar stuck at 0%.
    """

    def __init__(self, total, desc):
        from IPython.display import display

        self.total, self.desc, self.n = total, desc, 0
        self.postfix = ""
        self.start = time.time()
        self.handle = display(self, display_id=True)

    def update(self, n=1):
        self.n += n

    def set_postfix_str(self, text, refresh=True):
        self.postfix = text
        if refresh:
            self.handle.update(self)

    def close(self):
        self.handle.update(self)

    def _numbers(self):
        elapsed = time.time() - self.start
        left = elapsed / self.n * (self.total - self.n) if self.n else None
        timing = f"{elapsed:.1f} s" + (f", about {left:.0f} s left" if left else "")
        return f"{self.n}/{self.total} hours, {timing}"

    def __repr__(self):
        filled = int(round(20 * self.n / max(self.total, 1)))
        return f"{self.desc} [{'#' * filled}{'.' * (20 - filled)}] {self._numbers()} | {self.postfix}"

    def _repr_html_(self):
        from html import escape

        return (f'<div style="font-family:monospace;font-size:12px;line-height:1.6">'
                f'<b>{escape(self.desc)}</b> <progress value="{self.n}" max="{self.total}" '
                f'style="width:220px;vertical-align:middle"></progress> {escape(self._numbers())}'
                f'<br>{escape(self.postfix)}</div>')


def _status_bar(total, desc="HRRR"):
    if _in_notebook():
        return _NotebookBar(total, desc)
    from tqdm import tqdm

    return tqdm(total=total, desc=desc, unit="hour")


class _Status:
    """Counts shown in the status bar, shared by the worker threads."""

    def __init__(self, bar):
        self.bar = bar
        self.lock = threading.Lock()
        self.stage = {"fetching": 0, "decoding": 0, "uploading": 0}
        self.fetched = self.written = 0
        self.last = ""

    def enter(self, stage):
        with self.lock:
            self.stage[stage] += 1
            self._show()

    def leave(self, stage):
        with self.lock:
            self.stage[stage] -= 1

    def done(self, note, fetched=0, written=0):
        with self.lock:
            self.fetched += fetched
            self.written += written
            self.last = note
            if self.bar is not None:
                self.bar.update(1)
            self._show()

    def _show(self):
        if self.bar is None:
            return
        busy = ", ".join(f"{k} {v}" for k, v in self.stage.items() if v)
        self.bar.set_postfix_str(
            f"{busy or 'idle'} | {self.fetched / 1e6:.1f} MB fetched, "
            f"{self.written / 1e6:.2f} MB written | last done: {self.last or 'none yet'}", refresh=True)


def _prepare_hour(step, bands, bbox, bucket, blob_name, idx_cache, status):
    import numpy as np
    import rasterio
    from rasterio.warp import transform as warp_transform
    from rasterio.windows import Window

    status.enter("fetching")
    try:
        groups = _messages(step, bands, idx_cache)
        payload = {url: [(b, _get(url, (row["start"], row["end"]))) for b, row in rows]
                   for url, rows in groups.items()}
    finally:
        status.leave("fetching")
    fetched = sum(len(data) for rows in payload.values() for _, data in rows)

    with tempfile.TemporaryDirectory() as tmp:
        status.enter("decoding")
        try:
            layers = {}
            with rasterio.Env(GRIB_NORMALIZE_UNITS="NO"):
                for k, (url, rows) in enumerate(payload.items()):
                    path = os.path.join(tmp, f"{k}.grib2")
                    with open(path, "wb") as f:
                        f.write(b"".join(data for _, data in rows))
                    with rasterio.open(path) as src:
                        col0, row0, col1, row1 = grid_window(src, bbox)
                        win = Window(col0, row0, col1 - col0, row1 - row0)
                        arr = src.read(window=win).astype("float32")
                        crs, transform = src.crs, src.window_transform(win)
                    for i, (b, _) in enumerate(rows):
                        spec = VARIABLES[b]
                        layers[b] = arr[i] * spec.get("scale", 1.0) + spec.get("offset", 0.0)
            if "u" in layers and "v" in layers:
                h, w = layers["u"].shape
                cols, rows_ = np.meshgrid(np.arange(w) + 0.5, np.arange(h) + 0.5)
                xs, ys = transform * (cols.ravel(), rows_.ravel())
                lon = np.array(warp_transform(crs, "EPSG:4326", xs, ys)[0]).reshape(h, w)
                layers["u"], layers["v"] = rotate_to_earth(layers["u"], layers["v"], lon)
            stack = np.stack([layers[b] for b in bands]).astype("float32")
            out = os.path.join(tmp, "hour.tif")
            profile = dict(driver="COG", width=stack.shape[2], height=stack.shape[1],
                           count=len(bands), dtype="float32", crs=crs, transform=transform,
                           compress="DEFLATE", zlevel=1, predictor=3, num_threads="ALL_CPUS")
            with rasterio.open(out, "w", **profile) as dst:
                dst.write(stack)
                dst.descriptions = tuple(bands)
            written = os.path.getsize(out)
        finally:
            status.leave("decoding")
        status.enter("uploading")
        try:
            bucket.blob(blob_name).upload_from_filename(out)
        finally:
            status.leave("uploading")
    return fetched, written


# --------------------------------------------------------------------------
# The entry point
# --------------------------------------------------------------------------

_CLIENT = []


def _storage_client():
    """One Cloud Storage client per process: resolving credentials takes seconds."""
    if not _CLIENT:
        from google.cloud import storage

        # project=None: reading and writing objects needs no project, and
        # looking one up is most of the client's start-up time.
        _CLIENT.append(storage.Client(project=None))
    return _CLIENT[0]


def _duration(seconds):
    return f"{seconds:.0f} seconds" if seconds < 90 else f"{seconds / 60:.0f} minutes"


def _split_bucket(bucket):
    path = bucket[len("gs://"):] if bucket.startswith("gs://") else bucket
    name, _, prefix = path.partition("/")
    return name, prefix.strip("/") or "hrrr"


def getHRRR(region, startDate, endDate, variables=None, bucket=None, hourStep=1,
            now=None, max_hours=72, workers=8, verbose=True):
    """HRRR weather for a region and time window, as an ``ee.ImageCollection``.

    Downloads only the fields and area asked for from NOAA's public HRRR
    bucket, writes one Cloud Optimized GeoTIFF per hour to ``bucket``,
    and returns images that Earth Engine reads from there directly. See
    the module docstring for how each hour's data is chosen.

    Args:
        region: Where. An ``ee.Geometry``, ``ee.Feature``,
            ``ee.FeatureCollection`` or ``[west, south, east, north]``
            in degrees. Required: only this area (plus 2 cells) is
            written, which is what keeps a request to seconds.
        startDate, endDate: The window, ``[startDate, endDate)`` like
            ``filterDate``. A date string, ``datetime`` or epoch ms;
            UTC unless the value carries an offset
            (``"2026-08-07T12:00-06:00"``).
        variables: :data:`VARIABLES` keys, ``"wind"`` (``u`` and ``v``),
            or a list. Defaults to temperature, relative humidity, wind
            and gusts.
        bucket: ``"gs://bucket/prefix"`` (or a bucket name) you can
            write to and Earth Engine can read. Defaults to the
            ``GEEVIZ_HRRR_BUCKET`` environment variable.
        hourStep: Take every Nth hour of the window.
        now: Override the clock (UTC), for replaying a past forecast.
        max_hours: Refuse windows with more hours than this. Each hour
            takes about 12 s of one worker's time whatever the area
            (8 run at once by default). For long look-backs,
            ``NOAA/NWS/RTMA`` (2.5 km hourly analysis, already in Earth
            Engine) is the better source.
        workers: Hours prepared in parallel.
        verbose: Print the plan and show a status bar.

    Returns:
        ``ee.ImageCollection``. Each image carries ``system:time_start``
        (the valid time), ``valid_time``, ``run_time`` (ms),
        ``lead_hours``, ``hrrr_source`` (``"analysis"`` or
        ``"forecast"``), ``wx_model`` (``"hrrr"``) and ``wx_units``.

    >>> import geeViz.geeView as gv
    >>> from geeViz.hrrr import getHRRR
    >>> boulder = [-105.70, 39.91, -105.05, 40.27]
    >>> hrrr = getHRRR(boulder, "2026-08-07T18:00", "2026-08-07T22:00",
    ...                bucket="gs://my-bucket/hrrr")  # doctest: +SKIP
    >>> hrrr.size().getInfo()  # doctest: +SKIP
    4
    """
    t_start = time.time()
    bucket = bucket or os.environ.get("GEEVIZ_HRRR_BUCKET")
    if not bucket:
        raise ValueError("Pass bucket='gs://your-bucket/prefix' (or set GEEVIZ_HRRR_BUCKET): "
                         "a bucket you can write to and Earth Engine can read.")
    bucket_name, prefix = _split_bucket(bucket)
    bands = _expand(variables)
    bbox = _bounds(region)
    hours = valid_hours(startDate, endDate, hourStep)
    if len(hours) > max_hours:
        raise ValueError(
            f"{len(hours)} hours requested; max_hours is {max_hours}. That would take about "
            f"{_duration(len(hours) * SECONDS_PER_HOUR_ESTIMATE / max(workers, 1))}. "
            f"Use hourStep to thin the window, raise max_hours, or, for a long look-back, "
            f"use NOAA/NWS/RTMA, which is already in Earth Engine.")

    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)
    clock = _to_utc(now)
    latest = latest_run(clock)
    steps = plan(hours, latest)

    band_sig = hashlib.sha1(",".join(bands).encode()).hexdigest()[:8]
    bbox_sig = hashlib.sha1(",".join(f"{x:.4f}" for x in bbox).encode()).hexdigest()[:8]
    for s in steps:
        tag = f"{s['run']:%Y%m%d%H}_f{s['fhour']:02d}"
        if "precipitation" in bands:
            tag += f"_p{s['precip_run']:%Y%m%d%H}f{s['precip_fhour']:02d}"
        s["blob"] = f"{prefix}/{CACHE_VERSION}/{tag}_{band_sig}_{bbox_sig}.tif"
        s["label"] = (f"{s['valid']:%m-%d %H}Z ({s['source']}, "
                      f"{s['run']:%H}z run f{s['fhour']:02d})")

    if verbose:
        analyses = [s for s in steps if s["source"] == "analysis"]
        forecasts = [s for s in steps if s["source"] == "forecast"]
        print(f"HRRR: {len(steps)} hour(s), {hours[0]:%Y-%m-%d %H:%M} to "
              f"{hours[-1]:%Y-%m-%d %H:%M} UTC, every {hourStep} h")
        print(f"  region   {bbox[0]:.3f}, {bbox[1]:.3f}, {bbox[2]:.3f}, {bbox[3]:.3f} (W, S, E, N)")
        print(f"  bands    {', '.join(bands)}")
        print(f"  newest   {latest:%Y-%m-%d %H}z run published")
        if analyses:
            print(f"  past     {len(analyses)} hour(s) from each hour's own analysis (f00)")
        if forecasts:
            r = forecasts[0]["run"]
            print(f"  ahead    {len(forecasts)} hour(s) from the {r:%Y-%m-%d %H}z run, "
                  f"f{forecasts[0]['fhour']:02d} to f{forecasts[-1]['fhour']:02d}")

    bucket_obj = _storage_client().bucket(bucket_name)
    with concurrent.futures.ThreadPoolExecutor(workers) as ex:
        cached = list(ex.map(lambda s: bucket_obj.blob(s["blob"]).exists(), steps))
    todo = [s for s, hit in zip(steps, cached) if not hit]
    if verbose:
        print(f"  cache    {len(steps) - len(todo)} of {len(steps)} hour(s) already prepared; "
              f"{len(todo)} to fetch")

    bar = None
    if verbose and todo:
        bar = _status_bar(len(todo))
    status = _Status(bar)
    idx_cache = {}

    def work(s):
        fetched, written = _prepare_hour(s, bands, bbox, bucket_obj, s["blob"], idx_cache, status)
        status.done(f"{s['label']}, {written / 1e3:.0f} KB", fetched, written)

    try:
        if todo:
            with concurrent.futures.ThreadPoolExecutor(workers) as ex:
                for f in concurrent.futures.as_completed([ex.submit(work, s) for s in todo]):
                    f.result()
    finally:
        if bar is not None:
            bar.close()

    units = {b: VARIABLES[b]["units"] for b in bands}
    images = []
    for s in steps:
        uri = f"gs://{bucket_name}/{s['blob']}"
        images.append(ee.Image.loadGeoTIFF(uri).rename(bands).set({
            "system:time_start": _ms(s["valid"]),
            "valid_time": _ms(s["valid"]),
            "run_time": _ms(s["run"]),
            "lead_hours": s["fhour"],
            "hrrr_source": s["source"],
            "wx_model": "hrrr",
            "wx_units": units,
        }))
    if verbose:
        print(f"Done in {time.time() - t_start:.1f} s: {len(todo)} hour(s) prepared, "
              f"{len(steps) - len(todo)} from cache; fetched {status.fetched / 1e6:.1f} MB "
              f"of GRIB2, wrote {status.written / 1e6:.2f} MB.")
    return ee.ImageCollection(images)
