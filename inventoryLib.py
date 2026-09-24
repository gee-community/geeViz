"""
Design-based image inventory for landscape analysis.

The :func:`inventory_area` function samples an area (points, polygon, or
bounds), fetches Google Maps imagery at each sample point (Street View
panorama + user-selected static-map types), sends the batched images to
Gemini for interpretation, consolidates the free-form labels into a
canonical taxonomy, and returns a full statistical inventory with
sampling-design-appropriate confidence intervals and interpretation
reliability metrics.

Statistical basis
-----------------

- **Design-based estimation** (Cochran, *Sampling Techniques*): SRS,
  systematic-grid, and stratified-random supported. Estimator + variance
  formulas match the design.
- **Stratified variance** follows Olofsson et al. 2014
  (*Remote Sensing of Environment* 148:42-57), eqs. 3–4 — overall
  proportion ``Σ Wh × p̂h`` with stratum-area weights, SE via weighted
  stratum variances.
- **Wilson score CIs** for individual proportions (better than Wald at
  small n or near 0/100 %).
- **Bootstrap percentile CIs** (Efron & Tibshirani) for statistics
  without a closed-form variance — derived counts, totals extrapolated
  to area.
- **Sison–Glaz 1995** simultaneous CIs for the multinomial vector
  (approximate; falls back to per-category Wilson if the Sison–Glaz
  helper is not installed).
- **Interpretation reliability** via a re-interpreted subset at higher
  temperature — Cohen's κ on category presence, ICC on category counts.
  (Krippendorff's α is more general but overkill for our 2-rater case.)

Uses the ``google-genai`` async client so batched Gemini calls run
concurrently. Image fetches parallelize on a ``ThreadPoolExecutor``.

Copyright 2026 Ian Housman.

Licensed under the Apache License, Version 2.0.
"""
from __future__ import annotations

import asyncio
import base64 as _b64
import concurrent.futures
import io as _io
import json as _json
import math as _math
import os as _os
import random as _rand
import re as _re
import statistics as _stats
import threading as _threading
import time as _time
from dataclasses import dataclass, field, asdict
from typing import Any

# LLM usage reporting. Imported at module scope on purpose: a
# call-time import of this from inside a function deadlocked the MCP
# server, whose prewarm thread holds the geeViz import lock while a
# tool call is being served. llmUsage is stdlib-only and imports
# nothing from geeViz, so this is free and cannot cycle.
from geeViz import llmUsage as _lu


def _log(msg: str, verbose: bool = True) -> None:
    """Emit a progress message with a flushed newline.

    Uses print() rather than logging so the user sees updates in real
    time inside a Jupyter cell (logging output can be buffered by the
    kernel) and inside `run_code` (the MCP server streams stdout).
    """
    if verbose:
        print(msg, flush=True)


def _fmt_dur(seconds: float) -> str:
    """Format a duration for progress lines."""
    if seconds < 1:
        return f"{seconds*1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(seconds, 60)
    return f"{int(m)}m{s:.0f}s"


def _run_async(coro):
    """Run a coroutine to completion whether or not an event loop is
    already running (Jupyter kernels, ADK/FastAPI request handlers,
    etc.). Falls back to a fresh thread + fresh loop when the caller
    is already inside a running loop — that way callers don't have to
    await, and we don't collide with the caller's loop.
    """
    try:
        asyncio.get_running_loop()
        in_loop = True
    except RuntimeError:
        in_loop = False

    if not in_loop:
        return asyncio.run(coro)

    result: dict = {}
    error: dict = {}

    def _runner():
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as e:
            error["value"] = e

    t = _threading.Thread(target=_runner, daemon=True)
    t.start()
    t.join()
    if "value" in error:
        raise error["value"]
    return result["value"]


# ---------------------------------------------------------------------------
# Public data classes
# ---------------------------------------------------------------------------

@dataclass
class SamplePoint:
    """One inventory sample. Populated in stages by the pipeline."""
    sample_id: int
    lon: float
    lat: float
    stratum: Any = None
    # Filled by metadata step
    pano_id: str | None = None
    pano_lat: float | None = None
    pano_lon: float | None = None
    pano_date: str | None = None
    pano_copyright: str | None = None
    # "pending" | "OK" | "ZERO_RESULTS" | "USER_UPLOAD" |
    # "DUPLICATE_PANO" | "ERROR: ..."
    coverage_status: str = "pending"
    # Filled by image-fetch step
    images: dict[str, bytes] = field(default_factory=dict)
    image_paths: dict[str, str] = field(default_factory=dict)
    # Filled by interpretation step
    raw_labels: list[dict] = field(default_factory=list)
    canonical_labels: list[dict] = field(default_factory=list)
    interp_error: str | None = None


# ---------------------------------------------------------------------------
# 1. Sampling
# ---------------------------------------------------------------------------

def _sample_random(lon_min: float, lat_min: float,
                    lon_max: float, lat_max: float,
                    n: int, rng: _rand.Random) -> list[tuple[float, float]]:
    """N uniform-random points within a lon/lat bounding box."""
    return [
        (rng.uniform(lon_min, lon_max), rng.uniform(lat_min, lat_max))
        for _ in range(n)
    ]


def _sample_systematic(lon_min: float, lat_min: float,
                        lon_max: float, lat_max: float,
                        n: int, rng: _rand.Random) -> list[tuple[float, float]]:
    """N systematic-grid points with a random origin jitter.

    Chooses roughly-square cell aspect. Origin jitter keeps the grid
    unbiased vs. a fixed corner start (Cochran §8).
    """
    # Aim for a grid with ceil(sqrt(n)) columns
    ncols = int(_math.ceil(_math.sqrt(n)))
    nrows = int(_math.ceil(n / ncols))
    dx = (lon_max - lon_min) / ncols
    dy = (lat_max - lat_min) / nrows
    jx = rng.uniform(0, dx)
    jy = rng.uniform(0, dy)
    pts = []
    for r in range(nrows):
        for c in range(ncols):
            pts.append((lon_min + jx + c * dx, lat_min + jy + r * dy))
            if len(pts) >= n:
                return pts
    return pts


def _sample_points_in_polygon(polygon_coords: list[tuple[float, float]],
                                n: int, rng: _rand.Random,
                                design: str = "random") -> list[tuple[float, float]]:
    """N points inside a lon/lat polygon.

    Simple rejection sampling on the bbox. Fine for reasonable-density
    polygons; if the polygon is a tiny sliver of its bbox, this can be
    slow — but typical use has fill ratios > 20 %.
    """
    lons = [p[0] for p in polygon_coords]
    lats = [p[1] for p in polygon_coords]
    bbox = (min(lons), min(lats), max(lons), max(lats))

    if design == "systematic":
        candidates = _sample_systematic(*bbox, n * 4, rng)
    else:
        candidates = _sample_random(*bbox, n * 10, rng)

    kept = []
    for pt in candidates:
        if _point_in_polygon(pt, polygon_coords):
            kept.append(pt)
            if len(kept) >= n:
                break

    # Fill remainder with any bbox points if polygon is sparse in candidates
    while len(kept) < n:
        fill = _sample_random(*bbox, n * 20, rng)
        for pt in fill:
            if _point_in_polygon(pt, polygon_coords):
                kept.append(pt)
                if len(kept) >= n:
                    break
    return kept[:n]


def _point_in_polygon(pt: tuple[float, float],
                        poly: list[tuple[float, float]]) -> bool:
    """Standard ray-casting point-in-polygon (works for simple polygons)."""
    x, y = pt
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-30) + xi):
            inside = not inside
        j = i
    return inside


def _resolve_sampling_input(
    input_data: Any,
) -> tuple[str, dict]:
    """Normalize the caller's ``input`` into (kind, params).

    Accepts:
      - list of (lon, lat) tuples → ("points", {"points": [...]})
      - dict with "polygon" key (list of (lon, lat)) → ("polygon", ...)
      - dict with "bounds": (lon_min, lat_min, lon_max, lat_max) → ("bounds", ...)
      - ee.Geometry or ee.FeatureCollection → ("polygon" or "bounds")
    """
    if isinstance(input_data, list) and input_data and \
       isinstance(input_data[0], (list, tuple)) and len(input_data[0]) == 2:
        return "points", {"points": [tuple(p) for p in input_data]}

    if isinstance(input_data, dict):
        if "polygon" in input_data:
            return "polygon", {"polygon": [tuple(p) for p in input_data["polygon"]]}
        if "bounds" in input_data:
            b = input_data["bounds"]
            return "bounds", {"bounds": (b[0], b[1], b[2], b[3])}

    # ee.Geometry / ee.FeatureCollection — extract bounds
    try:
        # Late-import ee so the module is usable without EE installed
        import ee as _ee  # noqa: F401
        if hasattr(input_data, "geometry"):
            geom = input_data.geometry()
        else:
            geom = input_data
        coords = geom.bounds().getInfo()["coordinates"][0]
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        return "bounds", {"bounds": (min(lons), min(lats), max(lons), max(lats))}
    except Exception as exc:
        raise ValueError(
            f"Unrecognised input type {type(input_data).__name__}. Pass "
            f"a list of (lon,lat), {{'polygon': [(lon,lat),...]}}, "
            f"{{'bounds': (lon_min,lat_min,lon_max,lat_max)}}, or an "
            f"ee.Geometry / ee.FeatureCollection. ({exc})"
        )


def _draw_samples(
    input_data: Any,
    n_samples: int,
    sampling: str,
    rng: _rand.Random,
    strata: Any = None,
    samples_per_class: dict[int, int] | None = None,
) -> list[SamplePoint]:
    """Draw N samples from the input using the requested design."""
    kind, params = _resolve_sampling_input(input_data)

    if kind == "points":
        # Caller already supplied the exact points. n_samples ignored.
        pts = params["points"]
        return [SamplePoint(sample_id=i, lon=lon, lat=lat)
                for i, (lon, lat) in enumerate(pts)]

    # Stratified branch (needs strata + samples_per_class)
    if sampling == "stratified":
        if strata is None:
            raise ValueError(
                "sampling='stratified' requires a `strata=` layer "
                "(ee.Image with integer class band). Falling back to "
                "'random' when strata unavailable is intentional."
            )
        return _draw_stratified(
            kind, params, strata, samples_per_class or {}, rng,
        )

    # SRS or systematic within bounds/polygon
    if kind == "polygon":
        pts = _sample_points_in_polygon(
            params["polygon"], n_samples, rng,
            design="systematic" if sampling == "systematic" else "random",
        )
    else:   # bounds
        lon_min, lat_min, lon_max, lat_max = params["bounds"]
        if sampling == "systematic":
            pts = _sample_systematic(lon_min, lat_min, lon_max, lat_max, n_samples, rng)
        else:
            pts = _sample_random(lon_min, lat_min, lon_max, lat_max, n_samples, rng)

    return [SamplePoint(sample_id=i, lon=lon, lat=lat)
            for i, (lon, lat) in enumerate(pts)]


def _draw_stratified(
    kind: str, params: dict, strata_img, samples_per_class: dict[int, int],
    rng: _rand.Random,
) -> list[SamplePoint]:
    """Stratified random sampling via ee.Image.stratifiedSample."""
    import ee as _ee
    # Build a region geometry
    if kind == "polygon":
        region = _ee.Geometry.Polygon([params["polygon"]])
    elif kind == "bounds":
        b = params["bounds"]
        region = _ee.Geometry.Rectangle([b[0], b[1], b[2], b[3]])
    else:
        raise ValueError(f"Stratified sampling requires polygon/bounds input, not {kind!r}")

    class_values = list(samples_per_class.keys())
    class_points = list(samples_per_class.values())

    fc = strata_img.stratifiedSample(
        numPoints=0,     # override per-class with classPoints
        classBand=strata_img.bandNames().get(0).getInfo()
                    if hasattr(strata_img, "bandNames") else "classification",
        region=region,
        scale=30,
        classValues=class_values,
        classPoints=class_points,
        geometries=True,
        seed=rng.randint(0, 10**9),
    )
    feats = fc.getInfo()["features"]
    samples = []
    for i, f in enumerate(feats):
        coords = f["geometry"]["coordinates"]
        stratum = f.get("properties", {}).get("classification")
        samples.append(SamplePoint(
            sample_id=i, lon=coords[0], lat=coords[1], stratum=stratum,
        ))
    return samples


# ---------------------------------------------------------------------------
# 2. Metadata + dedup + refill
# ---------------------------------------------------------------------------

def _fetch_metadata_parallel(
    samples: list[SamplePoint], radius: int, source: str,
    max_workers: int = 10,
) -> None:
    """Populate pano_id / coverage_status for each sample in-place."""
    from geeViz import googleMapsLib as _gm

    def _one(s: SamplePoint) -> None:
        try:
            m = _gm.streetview_metadata(s.lon, s.lat, radius=radius, source=source)
            if m.get("status") == "OK":
                s.pano_id = m.get("pano_id")
                loc = m.get("location") or {}
                s.pano_lat = loc.get("lat")
                s.pano_lon = loc.get("lng") or loc.get("lon")
                s.pano_date = m.get("date")
                s.pano_copyright = m.get("copyright")
                s.coverage_status = "OK"
            else:
                s.coverage_status = m.get("status", "NO_COVERAGE")
        except Exception as exc:
            s.coverage_status = f"ERROR: {exc}"

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        list(pool.map(_one, samples))


def _is_user_upload(copyright_str: str | None) -> bool:
    """Return True if a Street View pano's copyright looks user-uploaded.

    Google's `source="outdoor"` filter should exclude user PhotoSpheres
    but doesn't always — some indoor 360 tours (business lobbies, tourist
    associations) get through with an outdoor flag. The copyright text
    is the most reliable tell: Google's own captures always contain
    "Google" (e.g. "© Google"), user contributions carry a person or
    business name (e.g. "© Visit Salt Lake").
    """
    if not copyright_str:
        # Empty or missing — err on the side of accepting so we don't
        # over-filter when the API omits the field.
        return False
    return "google" not in copyright_str.lower()


def _dedup_and_refill(
    input_data: Any, n_samples: int, sampling: str, rng: _rand.Random,
    radius: int, source: str, max_iterations: int,
    strata=None, samples_per_class=None, verbose: bool = True,
    require_google_copyright: bool = True,
) -> tuple[list[SamplePoint], dict]:
    """Draw samples, dedup by pano_id, top up if we came under.

    Returns (unique_samples_list, dedup_stats). Stops after
    ``max_iterations`` regardless.
    """
    unique: dict[str, SamplePoint] = {}   # keyed by pano_id
    all_drawn: list[SamplePoint] = []
    iterations = 0

    for it in range(1, max_iterations + 1):
        iterations = it
        needed = n_samples - len(unique)
        if needed <= 0:
            break
        _log(f"[sampling] Iteration {it}/{max_iterations} — drawing {needed} "
             f"candidate point(s) ({sampling}) and fetching Street View metadata...",
             verbose)
        t0 = _time.time()
        batch = _draw_samples(
            input_data, needed, sampling, rng,
            strata=strata, samples_per_class=samples_per_class,
        )
        # Re-key sample_ids to be globally unique across iterations
        offset = len(all_drawn)
        for i, s in enumerate(batch):
            s.sample_id = offset + i
        all_drawn.extend(batch)
        _fetch_metadata_parallel(batch, radius=radius, source=source)
        new_unique = 0
        dupes = 0
        misses = 0
        user_uploads = 0
        for s in batch:
            if s.coverage_status != "OK":
                misses += 1
                continue
            if (require_google_copyright
                    and _is_user_upload(s.pano_copyright)):
                s.coverage_status = "USER_UPLOAD"
                user_uploads += 1
                continue
            if s.pano_id and s.pano_id not in unique:
                unique[s.pano_id] = s
                new_unique += 1
            elif s.pano_id in unique:
                s.coverage_status = "DUPLICATE_PANO"
                dupes += 1
        _log(f"[sampling]   +{new_unique} unique pano(s), {dupes} duplicate(s), "
             f"{user_uploads} user-upload(s), {misses} no-coverage. "
             f"Running total: {len(unique)}/{n_samples} "
             f"({_fmt_dur(_time.time() - t0)})", verbose)

    result = list(unique.values())
    # Re-number for downstream stability
    for i, s in enumerate(result):
        s.sample_id = i
    stats = {
        "requested": n_samples,
        "drawn_total": len(all_drawn),
        "unique_panos": len(result),
        "iterations": iterations,
        "hit_iteration_cap": (iterations >= max_iterations
                              and len(result) < n_samples),
        "no_coverage_count": sum(
            1 for s in all_drawn
            if s.coverage_status not in ("OK", "DUPLICATE_PANO", "USER_UPLOAD")
        ),
        "duplicate_count": sum(
            1 for s in all_drawn if s.coverage_status == "DUPLICATE_PANO"
        ),
        "user_upload_count": sum(
            1 for s in all_drawn if s.coverage_status == "USER_UPLOAD"
        ),
    }
    if stats["hit_iteration_cap"]:
        _log(f"[sampling] ! Reached max iterations ({max_iterations}) with "
             f"{len(result)}/{n_samples} unique panoramas — running with what we got.",
             verbose)
    else:
        _log(f"[sampling] ✓ Dedup complete — {len(result)} unique panoramas "
             f"from {len(all_drawn)} draws over {iterations} iteration(s)",
             verbose)
    return result, stats


# ---------------------------------------------------------------------------
# 3. Image fetching (parallel)
# ---------------------------------------------------------------------------

def _fetch_all_images(
    samples: list[SamplePoint],
    image_types: tuple[str, ...],
    streetview_fov: float,
    zoom_satellite: int,
    zoom_hybrid: int,
    zoom_roadmap: int,
    zoom_terrain: int,
    size: str = "640x480",
    output_dir: str | None = None,
    max_workers: int = 10,
    verbose: bool = True,
    radius: int = 200,
    source: str = "outdoor",
) -> None:
    """Fetch all requested image types for every sample in parallel.

    Populates ``s.images[image_type] = bytes`` and optionally
    ``s.image_paths[image_type] = filesystem path`` when output_dir is
    provided.

    ``radius`` and ``source`` are forwarded to the Street View calls so
    the pano the caller sees matches the pano the metadata step
    selected. Passing them was previously omitted, which meant the
    fetch used ``radius=50m, source="default"`` regardless of the
    metadata search — so on tightly-spaced samples the image could
    come from a *different* nearby pano (potentially indoor, if
    Google's outdoor flag is wrong on an indoor pano nearer than 50m).
    """
    from geeViz import googleMapsLib as _gm

    tasks: list[tuple[SamplePoint, str]] = []
    for s in samples:
        for typ in image_types:
            tasks.append((s, typ))

    def _fetch_one(task):
        s, typ = task
        try:
            if typ in ("streetview-pano", "streetview"):
                # Both types honor streetview_fov (default 360). The
                # underlying streetview_panorama fetches a single frame
                # via the Street View Static API when fov <= 120 and
                # stitches multiple frames otherwise, so this one path
                # covers both narrow-fov "streetview" and full "streetview-pano"
                # use cases. Old behavior — hardcoded fov=90 for plain
                # "streetview" — silently ignored the param and gave a
                # tight-angle image no matter what the caller asked for.
                b = _gm.streetview_panorama(
                    s.lon, s.lat, heading=0, fov=streetview_fov,
                    size=size, radius=radius, source=source,
                )
            elif typ == "satellite":
                b = _gm.get_static_map(s.lon, s.lat, zoom=zoom_satellite,
                                        size=size, maptype="satellite")
            elif typ == "hybrid":
                b = _gm.get_static_map(s.lon, s.lat, zoom=zoom_hybrid,
                                        size=size, maptype="hybrid")
            elif typ == "roadmap":
                b = _gm.get_static_map(s.lon, s.lat, zoom=zoom_roadmap,
                                        size=size, maptype="roadmap")
            elif typ == "terrain":
                b = _gm.get_static_map(s.lon, s.lat, zoom=zoom_terrain,
                                        size=size, maptype="terrain")
            else:
                return
            if b:
                s.images[typ] = b
                if output_dir:
                    _os.makedirs(output_dir, exist_ok=True)
                    ext = "jpg" if typ.startswith("streetview") else "png"
                    fname = f"sample_{s.sample_id:03d}_{typ}.{ext}"
                    fpath = _os.path.join(output_dir, fname)
                    with open(fpath, "wb") as f:
                        f.write(b)
                    s.image_paths[typ] = fpath
        except Exception:
            # A single missing image is not fatal — log via coverage state
            pass

    _log(f"[fetch] Downloading {len(tasks)} image(s) — "
         f"{len(samples)} sample(s) × {len(image_types)} type(s) "
         f"({', '.join(image_types)}) in parallel (max_workers={max_workers})...",
         verbose)
    t0 = _time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        list(pool.map(_fetch_one, tasks))
    got = sum(len(s.images) for s in samples)
    dt = _time.time() - t0
    _log(f"[fetch] ✓ {got}/{len(tasks)} images fetched ({_fmt_dur(dt)})",
         verbose)


# ---------------------------------------------------------------------------
# 3b. Sample location map (static hybrid with pins)
# ---------------------------------------------------------------------------

def _auto_zoom_from_span(lon_span: float, lat_span: float,
                          size_wh: tuple[int, int] = (640, 480)) -> int:
    """Pick a Google-Maps zoom level that fits both spans into the image.

    Uses the classical Web Mercator equation: at zoom z, 256 pixels
    correspond to 360/2^z degrees of longitude at the equator. Solve
    for z such that our span×padding fits in the image with some margin.
    """
    import math
    w, h = size_wh
    span = max(lon_span, lat_span * 1.4)   # lat is ~1.4× tighter per degree at 40°N
    if span <= 0:
        return 18
    # Add ~40% padding so pins aren't at the edges
    padded_span = span * 1.4
    # Fit padded_span degrees into `w` pixels: pixels_per_deg = w / padded_span
    # Web Mercator: pixels_per_deg_at_zoom_z = 256 * 2^z / 360
    # → 2^z = pixels_per_deg * 360 / 256 = (w / padded_span) * 360 / 256
    z = math.log2(w * 360 / (padded_span * 256))
    return max(1, min(20, int(math.floor(z))))


def _build_sample_map(
    samples: list[SamplePoint], output_dir: str, size: str = "640x480",
    maptype: str = "hybrid", verbose: bool = True,
) -> str | None:
    """Fetch a static hybrid map with a pin at each sample location.

    Uses the sample bounding box to pick center + zoom automatically.
    Returns the written path or None on failure.
    """
    from geeViz import googleMapsLib as _gm
    if not samples:
        return None
    lons = [s.lon for s in samples]
    lats = [s.lat for s in samples]
    c_lon = sum(lons) / len(lons)
    c_lat = sum(lats) / len(lats)
    lon_span = max(lons) - min(lons)
    lat_span = max(lats) - min(lats)
    try:
        w, h = (int(x) for x in size.lower().split("x"))
    except Exception:
        w, h = 640, 480
    zoom = _auto_zoom_from_span(lon_span, lat_span, (w, h))
    _log(f"[map] Rendering sample-location map: {len(samples)} pin(s), "
         f"center=({c_lat:.5f}, {c_lon:.5f}), zoom={zoom}, "
         f"maptype={maptype}...", verbose)
    try:
        img = _gm.get_static_map(
            c_lon, c_lat,
            zoom=zoom, size=size, maptype=maptype,
            markers=[(s.lon, s.lat) for s in samples],
        )
    except Exception as exc:
        _log(f"[map] ✗ failed: {exc}", verbose)
        return None
    if not img:
        _log(f"[map] ✗ static-map API returned no bytes", verbose)
        return None
    _os.makedirs(output_dir, exist_ok=True)
    path = _os.path.join(output_dir, "sample_map.png")
    with open(path, "wb") as f:
        f.write(img)
    _log(f"[map] ✓ {path} ({len(img):,} bytes)", verbose)
    return path


# ---------------------------------------------------------------------------
# 4. Gemini interpretation (async batches)
# ---------------------------------------------------------------------------

_INVENTORY_PROMPT = """\
You are performing a rigorous visual inventory of the following image samples from Google Maps. Each sample consists of one or more images (may include a 360-degree Street View panorama, a satellite/nadir aerial view, a hybrid map, etc.) captured at a specific longitude/latitude.

For EACH sample, produce an object inventory: list every distinct feature type visible in ANY of that sample's images, with a numeric count of instances observed.

Guidance:
- Be specific — 'brick ranch house' not just 'building'; 'white sedan' not just 'vehicle'.
- Count instances, not image occurrences. If the same rooftop appears in both the satellite and hybrid views, count it once.
- If a sample has both nadir imagery (satellite) and ground imagery (Street View), the nadir view gives roof/parking counts and the ground view gives ground-level detail (signage, vehicles, pedestrians) — combine them into one inventory.
- Include category `notes` when a distinctive attribute is worth preserving (color, material, condition).
{indoor_directive}{categories_directive}

Return ONLY valid JSON with this exact structure:
{{"samples":[{{"sample_id":<int>,"labels":[{{"category":"<name>","count":<int>,"notes":"<optional>"}}, ...]}}, ...]}}

Do NOT include narrative text, markdown fences, or comments — ONLY the JSON object.
"""


_INDOOR_EXCLUDE_DIRECTIVE = """
CRITICAL — OUTDOOR / PUBLIC-RIGHT-OF-WAY ONLY:
- Ignore anything visible through storefront windows, glass facades, or open
  doorways: restaurant tables, chairs, chandeliers, bar counters, retail
  interiors, wall art, kitchen equipment, indoor plants.
- Ignore anything inside a building lobby that Street View passed through
  (turnstiles, mezzanine railings, marble columns, indoor staircases,
  patterned carpet, ceiling ducts, security desks).
- Ignore rooftop-visible HVAC vents, skylights, and mechanical equipment
  from satellite/nadir views UNLESS you specifically care to track them.
- KEEP: rooftops, buildings, roads, sidewalks, driveways, parking lots, cars
  (any type), trucks, buses, pedestrians, cyclists, streetlights, signs,
  traffic lights, benches, trees, planters (outdoor), fences, walls, water,
  vegetation, bare ground, dumpsters/waste bins, utility poles.
- When in doubt whether a feature is inside or outside a building, EXCLUDE it.
"""


def _build_batch_prompt(batch: list[SamplePoint],
                          categories: list[str] | None,
                          exclude_indoor: bool = True) -> str:
    """Build a labeled prompt describing which images belong to which sample."""
    if categories:
        cat_str = ", ".join(f"'{c}'" for c in categories)
        directive = (
            f"\nRESTRICT categories to this list: {cat_str}. "
            "Anything you notice that does not fit these categories "
            "goes into a single 'other' bucket (with a `notes` field "
            "describing what it actually is)."
        )
    else:
        directive = ""

    indoor_directive = _INDOOR_EXCLUDE_DIRECTIVE if exclude_indoor else ""
    prompt = _INVENTORY_PROMPT.format(
        indoor_directive=indoor_directive,
        categories_directive=directive,
    )

    # Per-sample header
    prompt += "\nSample manifest:\n"
    for s in batch:
        img_list = ", ".join(sorted(s.images.keys()))
        prompt += (
            f"  sample_id={s.sample_id}: lon={s.lon:.6f}, lat={s.lat:.6f}"
        )
        if s.pano_date:
            prompt += f", pano_date={s.pano_date}"
        prompt += f", images=[{img_list}]\n"
    prompt += ("\nThe images below are provided in the order shown above, "
                "sample-by-sample. Within each sample, images are in "
                "alphabetical order by image type.\n")
    return prompt


def _build_batch_content(batch: list[SamplePoint], prompt: str) -> list:
    """Assemble the multimodal `contents` for a Gemini call."""
    from google.genai import types
    contents: list = [prompt]
    for s in batch:
        for typ in sorted(s.images):
            mime = "image/jpeg" if typ.startswith("streetview") else "image/png"
            contents.append(types.Part.from_bytes(
                data=s.images[typ], mime_type=mime,
            ))
    return contents


async def _call_gemini_batch(
    batch: list[SamplePoint], prompt: str, model: str, temperature: float,
    client,
) -> tuple[list[dict], dict]:
    """Single async Gemini batch call. Returns (per-sample records, meta)."""
    from google.genai import types

    contents = _build_batch_content(batch, prompt)
    try:
        response = await client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=temperature,
                response_mime_type="application/json",
            ),
        )
    except Exception as exc:
        return [], {"error": f"api_error: {exc}"}

    text = response.text or ""
    records = _parse_inventory_json(text)
    # Token counts, in the one vocabulary the whole stack speaks. These
    # were ``input_tokens`` / ``output_tokens`` / ``thought_tokens``
    # here and something else again in googleMapsLib, for the same four
    # numbers off the same response object.
    _usage = _lu.report(_lu.usage_from_response(
        response, model=model, source="geeviz.inventory.batch"))
    meta = {
        **_usage,
        "sample_count": len(batch),
        "sample_ids": [s.sample_id for s in batch],
        # Full raw prompt + response for downstream transparency
        # (LLMs / humans can re-parse or audit what Gemini actually saw
        # and returned).
        "prompt": prompt,
        "raw_response": text,
        "records_parsed": len(records),
    }
    if not records:
        meta["error"] = "empty_or_unparseable_response"
    return records, meta


def _parse_inventory_json(text: str) -> list[dict]:
    """Parse Gemini's inventory JSON. Robust to markdown fences + minor slop."""
    if not text or not text.strip():
        return []
    raw = text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        _lines = raw.splitlines()
        if len(_lines) >= 3:
            raw = "\n".join(_lines[1:-1])
    # First-pass strict parse
    try:
        obj = _json.loads(raw)
    except _json.JSONDecodeError:
        # Repair pass: fix stray commas before ] or }, and stray quotes
        # before object opens (the same failure mode we handle in label_image).
        rep = _re.sub(r',\s*"\s*(\{\s*"sample_id")', r', \1', raw)
        rep = _re.sub(r',(\s*[\]\}])', r'\1', rep)
        try:
            obj = _json.loads(rep)
        except _json.JSONDecodeError:
            return []
    return obj.get("samples", []) if isinstance(obj, dict) else []


async def _close_genai_client(client) -> None:
    """Best-effort async cleanup of a google-genai Client.

    The SDK wraps an ``httpx.AsyncClient`` under
    ``client.aio._api_client._async_httpx_client``. If we don't ``aclose``
    it before the loop tears down, asyncio prints
    ``Task was destroyed but it is pending!`` — cosmetic but noisy in
    Jupyter. Swallow any exception because SDK internals may rename.
    """
    for path in (
        ("aio", "_api_client", "_async_httpx_client"),
        ("aio", "_api_client", "_httpx_client"),
    ):
        try:
            obj = client
            for attr in path:
                obj = getattr(obj, attr)
            if hasattr(obj, "aclose"):
                await obj.aclose()
                return
        except Exception:
            continue


async def _run_all_batches(
    samples: list[SamplePoint],
    max_samples_per_call: int,
    prompt_categories: list[str] | None,
    model: str, temperature: float, concurrency: int,
    stage: str = "interp", verbose: bool = True,
    exclude_indoor: bool = True,
) -> tuple[dict[int, list[dict]], list[dict]]:
    """Fire all batch calls concurrently (bounded by ``concurrency``)."""
    from google import genai
    from geeViz import googleMapsLib as _gm

    api_key = _gm._get_gemini_key()
    client = genai.Client(api_key=api_key)

    try:
        # Chunk samples into batches
        batches = [
            samples[i : i + max_samples_per_call]
            for i in range(0, len(samples), max_samples_per_call)
        ]
        _log(f"[{stage}] Sending {len(batches)} batch(es) to Gemini "
             f"({len(samples)} sample(s), max {max_samples_per_call}/call, "
             f"model={model}, T={temperature}, concurrency={concurrency})...",
             verbose)
        t_stage = _time.time()

        sem = asyncio.Semaphore(concurrency)
        async def _guarded_call(batch, batch_idx):
            async with sem:
                t0 = _time.time()
                _log(f"[{stage}]   → batch {batch_idx+1}/{len(batches)}: "
                     f"{len(batch)} sample(s), {sum(len(s.images) for s in batch)} "
                     f"image(s)...", verbose)
                prompt = _build_batch_prompt(
                    batch, prompt_categories,
                    exclude_indoor=exclude_indoor,
                )
                records, meta = await _call_gemini_batch(
                    batch, prompt, model, temperature, client,
                )
                # Stamp batch identity so downstream renderers can
                # distinguish primary from reliability batches.
                meta["stage"] = stage
                meta["batch_index"] = batch_idx
                meta["batch_number"] = batch_idx + 1
                meta["temperature"] = temperature
                dt = _time.time() - t0
                meta["duration_s"] = round(dt, 2)
                if meta.get("error"):
                    _log(f"[{stage}]   ✗ batch {batch_idx+1}/{len(batches)} "
                         f"failed: {meta['error']} ({_fmt_dur(dt)})", verbose)
                else:
                    _log(f"[{stage}]   ✓ batch {batch_idx+1}/{len(batches)}: "
                         f"{len(records)} sample records, "
                         f"in={meta.get('prompt_tokens') or 0:,} "
                         f"out={meta.get('candidates_tokens') or 0:,} "
                         f"thoughts={meta.get('thoughts_tokens') or 0:,} "
                         f"total={meta.get('total_tokens') or 0:,} "
                         f"({_fmt_dur(dt)})", verbose)
                return records, meta

        results = await asyncio.gather(
            *(_guarded_call(b, i) for i, b in enumerate(batches)),
            return_exceptions=False,
        )

        # Merge per-sample records
        by_sample: dict[int, list[dict]] = {}
        meta_list: list[dict] = []
        for (records, meta), batch in zip(results, batches):
            meta_list.append(meta)
            for rec in records:
                sid = rec.get("sample_id")
                if sid is None:
                    continue
                by_sample.setdefault(sid, []).extend(rec.get("labels", []))
            # Attach interp_error for samples with no records
            found_sids = {r.get("sample_id") for r in records}
            if meta.get("error"):
                for s in batch:
                    if s.sample_id not in found_sids:
                        s.interp_error = meta.get("error")
        total_labels = sum(len(v) for v in by_sample.values())
        total_tokens = sum((m.get("total_tokens") or 0) for m in meta_list)
        _log(f"[{stage}] ✓ All batches complete — {len(by_sample)} sample(s) "
             f"interpreted, {total_labels} raw label(s), {total_tokens:,} tokens "
             f"({_fmt_dur(_time.time() - t_stage)})", verbose)
        return by_sample, meta_list
    finally:
        await _close_genai_client(client)


# ---------------------------------------------------------------------------
# 5. Taxonomy consolidation
# ---------------------------------------------------------------------------

_CONSOLIDATE_PROMPT = """\
You are consolidating a set of free-form category labels emitted by an image inventory system. Different images used different phrasings for the same underlying feature (e.g. 'car'/'sedan'/'vehicle', 'brick house'/'residential building'/'home').

Return a mapping from each raw label to a CANONICAL label. Preserve useful distinctions — 'sedan'/'SUV'/'pickup truck' are different vehicles, but 'car'/'automobile'/'vehicle'/'passenger vehicle' all collapse to 'car'. Similarly 'brick house'/'residential building'/'single-family home' → 'house'.

Rules:
- Keep canonical labels short (1-3 words), lowercase, singular.
- Do NOT merge visually distinct categories (dont collapse trees and shrubs).
- If a label is already canonical, map it to itself.
- Return ONLY a JSON object of {{raw_label: canonical_label}} — no narrative.

Raw labels:
{labels_list}
"""


async def _consolidate_taxonomy(
    raw_labels: set[str], model: str, client,
) -> dict[str, str]:
    """One text-only Gemini call to canonicalize labels."""
    if not raw_labels:
        return {}
    if len(raw_labels) <= 2:
        # No consolidation needed
        return {lbl: lbl for lbl in raw_labels}

    from google.genai import types
    prompt = _CONSOLIDATE_PROMPT.format(
        labels_list="\n".join(f"  - {lbl}" for lbl in sorted(raw_labels))
    )
    try:
        response = await client.aio.models.generate_content(
            model=model,
            contents=[prompt],
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
            ),
        )
        text = (response.text or "").strip()
        if text.startswith("```"):
            _lines = text.splitlines()
            if len(_lines) >= 3:
                text = "\n".join(_lines[1:-1])
        # Reported even though this helper returns only the mapping:
        # a call whose tokens are never mentioned is a call nobody is
        # billed for, and consolidation runs on every inventory.
        _lu.report(_lu.usage_from_response(
            response, model=model, source="geeviz.inventory.consolidate"))
        mapping = _json.loads(text)
        if isinstance(mapping, dict):
            return {k: str(v).strip().lower() for k, v in mapping.items()}
    except Exception:
        pass
    # Fallback: identity mapping (no consolidation)
    return {lbl: lbl for lbl in raw_labels}


# ---------------------------------------------------------------------------
# 6. Statistics
# ---------------------------------------------------------------------------

def _wilson_ci(x: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Wilson score CI for a binomial proportion."""
    if n == 0:
        return (0.0, 0.0)
    from math import sqrt
    # Two-sided z for confidence
    _z_TABLE = {0.90: 1.6449, 0.95: 1.96, 0.99: 2.5758}
    z = _z_TABLE.get(confidence, 1.96)
    p = x / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _bootstrap_stats(
    per_sample_counts: dict[int, dict[str, int]],
    categories: list[str],
    n_boot: int = 2000,
    confidence: float = 0.95,
    rng: _rand.Random | None = None,
) -> dict[str, dict[str, float]]:
    """Percentile-bootstrap CIs for per-category proportion and mean count.

    Returns {category: {prop_low, prop_high, mean_low, mean_high}}.
    """
    if rng is None:
        rng = _rand.Random(42)
    sample_ids = list(per_sample_counts.keys())
    n = len(sample_ids)
    if n == 0:
        return {c: {"prop_low": 0.0, "prop_high": 0.0,
                      "mean_low": 0.0, "mean_high": 0.0} for c in categories}

    alpha = (1 - confidence) / 2
    lo_pct = alpha * 100
    hi_pct = (1 - alpha) * 100

    boot_props: dict[str, list[float]] = {c: [] for c in categories}
    boot_means: dict[str, list[float]] = {c: [] for c in categories}
    for _ in range(n_boot):
        idxs = [rng.choice(sample_ids) for _ in range(n)]
        for cat in categories:
            present = sum(1 for sid in idxs
                          if per_sample_counts[sid].get(cat, 0) > 0)
            total = sum(per_sample_counts[sid].get(cat, 0) for sid in idxs)
            boot_props[cat].append(present / n)
            boot_means[cat].append(total / n)

    out: dict[str, dict[str, float]] = {}
    for cat in categories:
        prop_sorted = sorted(boot_props[cat])
        mean_sorted = sorted(boot_means[cat])
        def _pct(arr, p):
            k = max(0, min(len(arr) - 1, int(p / 100 * len(arr))))
            return arr[k]
        out[cat] = {
            "prop_low":  round(_pct(prop_sorted, lo_pct), 4),
            "prop_high": round(_pct(prop_sorted, hi_pct), 4),
            "mean_low":  round(_pct(mean_sorted, lo_pct), 4),
            "mean_high": round(_pct(mean_sorted, hi_pct), 4),
        }
    return out


def _compute_inventory_stats(
    per_sample_counts: dict[int, dict[str, int]],
    area_km2: float | None,
    n_bootstrap: int,
    rng: _rand.Random,
) -> "list[dict]":
    """Build the wide-form inventory row per canonical category.

    Columns: category, samples_with, count_total, mean_per_sample,
             proportion_of_samples, se_prop, ci95_prop_wilson_low,
             ci95_prop_wilson_high, ci95_prop_boot_low,
             ci95_prop_boot_high, ci95_mean_boot_low,
             ci95_mean_boot_high, est_total_area_extrapolated
    """
    from math import sqrt

    n = len(per_sample_counts)
    if n == 0:
        return []

    all_cats = sorted({
        c for counts in per_sample_counts.values() for c in counts
    })
    boot = _bootstrap_stats(per_sample_counts, all_cats,
                              n_boot=n_bootstrap, rng=rng)

    rows = []
    for cat in all_cats:
        cnts = [per_sample_counts[sid].get(cat, 0) for sid in per_sample_counts]
        samples_with = sum(1 for c in cnts if c > 0)
        count_total = sum(cnts)
        mean = count_total / n
        prop = samples_with / n
        se = sqrt(prop * (1 - prop) / n) if 0 < prop < 1 else 0.0
        wlo, whi = _wilson_ci(samples_with, n)
        row = {
            "category": cat,
            "samples_with": samples_with,
            "count_total": count_total,
            "mean_per_sample": round(mean, 4),
            "proportion_of_samples": round(prop, 4),
            "se_proportion": round(se, 4),
            "ci95_prop_wilson_low":  round(wlo, 4),
            "ci95_prop_wilson_high": round(whi, 4),
            "ci95_prop_boot_low":    boot[cat]["prop_low"],
            "ci95_prop_boot_high":   boot[cat]["prop_high"],
            "ci95_mean_boot_low":    boot[cat]["mean_low"],
            "ci95_mean_boot_high":   boot[cat]["mean_high"],
        }
        if area_km2 is not None:
            row["est_total_extrapolated"] = round(mean * area_km2, 2)
            row["est_total_ci95_low"] = round(boot[cat]["mean_low"] * area_km2, 2)
            row["est_total_ci95_high"] = round(boot[cat]["mean_high"] * area_km2, 2)
        rows.append(row)
    rows.sort(key=lambda r: -r["count_total"])
    return rows


def _reliability_kappa_icc(
    original: dict[int, dict[str, int]],
    repeat: dict[int, dict[str, int]],
) -> dict:
    """Cohen's κ on category presence + ICC(1,1) on category counts.

    ICC(1,1) approximated as 1 - MSW/MST where MSW is within-subject
    variance (between the two ratings) and MST is total variance.
    """
    common_ids = sorted(set(original) & set(repeat))
    if not common_ids:
        return {"kappa_presence": None, "icc_counts": None,
                 "n_repeated": 0, "message": "no overlapping repeats"}

    all_cats = sorted({
        c for sid in common_ids
        for c in (list(original[sid]) + list(repeat[sid]))
    })

    # Cohen's kappa over presence/absence, over (sample × category) cells
    pairs = []   # (orig_present, repeat_present)
    for sid in common_ids:
        for cat in all_cats:
            o = 1 if original[sid].get(cat, 0) > 0 else 0
            r = 1 if repeat[sid].get(cat, 0) > 0 else 0
            pairs.append((o, r))
    n_pairs = len(pairs)
    po = sum(1 for a, b in pairs if a == b) / n_pairs
    p_o = sum(1 for a, _ in pairs if a == 1) / n_pairs
    p_r = sum(1 for _, b in pairs if b == 1) / n_pairs
    pe = p_o * p_r + (1 - p_o) * (1 - p_r)
    kappa = (po - pe) / (1 - pe) if pe < 1 else 1.0

    # ICC(1,1) — one-way random-effects, single measurement.
    # Between-subject variance vs residual (within-subject) variance.
    # Compute per-sample means and residuals across the two ratings.
    ratings_by_sample: dict[int, list[float]] = {}
    for sid in common_ids:
        vals = []
        for cat in all_cats:
            vals.append(float(original[sid].get(cat, 0)))
            vals.append(float(repeat[sid].get(cat, 0)))
        ratings_by_sample[sid] = vals

    # Flatten: k = 2 raters (orig, repeat). Treat each (sample, category)
    # combination as its own "target" for ICC — this is what we care about.
    # See McGraw & Wong 1996 for definitions.
    values_pairs = []   # list of (orig_ct, repeat_ct)
    for sid in common_ids:
        for cat in all_cats:
            values_pairs.append((
                float(original[sid].get(cat, 0)),
                float(repeat[sid].get(cat, 0)),
            ))
    # ICC(1,1) = (BMS - WMS) / (BMS + (k-1)*WMS)  where k = 2
    subject_means = [(a + b) / 2 for a, b in values_pairs]
    grand_mean = _stats.fmean(subject_means) if subject_means else 0.0
    bms = 2 * sum((sm - grand_mean) ** 2 for sm in subject_means) / max(
        1, len(subject_means) - 1
    )
    wms = sum(((a - sm) ** 2 + (b - sm) ** 2) / 2
              for (a, b), sm in zip(values_pairs, subject_means)) / max(
        1, len(values_pairs)
    )
    icc = ((bms - wms) / (bms + wms)) if (bms + wms) > 0 else None

    return {
        "kappa_presence": round(kappa, 4),
        "icc_counts": round(icc, 4) if icc is not None else None,
        "n_repeated": len(common_ids),
        "n_categories": len(all_cats),
    }


# ---------------------------------------------------------------------------
# 7. Rendering: HTML, JSON, MD
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8">
<title>Inventory Report - {title}</title>
<script>
  // Theme sync — read ``?theme=light|dark`` off the iframe URL and
  // stamp ``data-theme`` on <html> BEFORE the stylesheet parses, so
  // the report matches whatever theme the chat UI is showing. Runs
  // sync (no await) to avoid a flash of the wrong theme. Falls back
  // silently to ``prefers-color-scheme`` when no query param is set.
  (function() {{
    try {{
      var q = new URLSearchParams(location.search).get('theme');
      if (q === 'light' || q === 'dark') {{
        document.documentElement.setAttribute('data-theme', q);
      }}
    }} catch (e) {{ /* no-op */ }}
  }})();
</script>
<style>
  /* Theme-aware — the report renders inside the chat's iframe, which
     may be dark or light. Variables + prefers-color-scheme let the
     browser propagate the parent theme automatically. When opened
     stand-alone (download / new tab), the same media query still
     applies based on the user's OS theme. */
  :root {{
    color-scheme: light dark;
    --bg:            #ffffff;
    --fg:            #1f2328;
    --fg-muted:      #57606a;
    --fg-dim:        #6e7781;
    --link:          #0969da;
    --border:        #d0d7de;
    --border-soft:   #eaeef2;
    --surface:       #f6f8fa;
    --surface-alt:   #eaeef2;
    --code-bg:       #eff1f3;
    --row-hover:     #f6f8fa;
    --callout-bg:    #ddf4ff;
    --callout-border:#0969da;
    --accent:        #0969da;
  }}
  /* Dark tokens live in one place — both the OS-level media query
     and the caller-forced ``data-theme="dark"`` root selector pick
     them up. The chat wrapper stamps ``data-theme`` from its own
     theme toggle so the report matches even when the OS setting
     disagrees with the user's in-app preference. */
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --bg:            #0d1117;
      --fg:            #e6edf3;
      --fg-muted:      #b7bfc9;
      --fg-dim:        #8b949e;
      --link:          #58a6ff;
      --border:        #30363d;
      --border-soft:   #21262d;
      --surface:       #161b22;
      --surface-alt:   #21262d;
      --code-bg:       #1e242c;
      --row-hover:     #161b22;
      --callout-bg:    #0d2f4a;
      --callout-border:#58a6ff;
      --accent:        #58a6ff;
    }}
  }}
  :root[data-theme="dark"] {{
    --bg:            #0d1117;
    --fg:            #e6edf3;
    --fg-muted:      #b7bfc9;
    --fg-dim:        #8b949e;
    --link:          #58a6ff;
    --border:        #30363d;
    --border-soft:   #21262d;
    --surface:       #161b22;
    --surface-alt:   #21262d;
    --code-bg:       #1e242c;
    --row-hover:     #161b22;
    --callout-bg:    #0d2f4a;
    --callout-border:#58a6ff;
    --accent:        #58a6ff;
  }}
  html, body {{ background: var(--bg); color: var(--fg); }}
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif;
          margin: 24px; max-width: 1200px;
          line-height: 1.45; }}
  a {{ color: var(--link); }}
  h1 {{ font-size: 24px; margin-bottom: 4px; color: var(--fg); }}
  h2 {{ font-size: 18px; margin-top: 32px; color: var(--fg);
        border-bottom: 1px solid var(--border-soft); padding-bottom: 4px; }}
  h3 {{ font-size: 14px; margin-top: 20px; color: var(--fg-muted); }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px;
           margin-top: 8px; }}
  th, td {{ padding: 6px 10px; border-bottom: 1px solid var(--border-soft);
            text-align: left; vertical-align: top; }}
  th {{ background: var(--surface); color: var(--fg); }}
  tr:hover td {{ background: var(--row-hover); }}
  .meta {{ font-size: 13px; color: var(--fg-muted);
           background: var(--surface); padding: 12px 16px;
           border-radius: 6px; margin: 10px 0; }}
  .stat {{ display: inline-block; margin-right: 24px; }}
  .stat strong {{ color: var(--accent); }}
  .agent-guide {{ background: var(--callout-bg);
                   border-left: 4px solid var(--callout-border);
                   color: var(--fg);
                   padding: 10px 14px; margin: 10px 0; font-size: 13px; }}
  code {{ background: var(--code-bg); color: var(--fg);
          padding: 1px 5px; border-radius: 3px; font-size: 12px; }}
  pre {{ background: var(--surface); color: var(--fg);
         padding: 10px; border-radius: 6px;
         font-size: 12px; overflow-x: auto; max-height: 320px; }}
  details {{ margin: 8px 0; }}
  details summary {{ cursor: pointer; padding: 6px 10px;
                     background: var(--surface); color: var(--fg);
                     border-radius: 4px;
                     font-size: 13px; user-select: none; }}
  details[open] summary {{ background: var(--surface-alt); }}
  .sample-map img {{ max-width: 100%; border: 1px solid var(--border);
                     border-radius: 6px; }}
  .gallery {{ display: flex; flex-wrap: wrap; gap: 12px;
              margin-top: 12px; }}
  .gallery figure {{ margin: 0; text-align: center; font-size: 11px;
                     color: var(--fg-muted); max-width: 220px; }}
  .gallery img {{ max-width: 220px; max-height: 220px;
                  border: 1px solid var(--border); border-radius: 4px; }}
</style></head><body>
<h1>{title}</h1>
<p style="color:var(--fg-muted); font-size:13px; margin-top:0;">
  Design-based image inventory generated by
  <code>geeViz.inventoryLib.inventory_area</code>.
  Sampling per Cochran (1977); estimation follows Olofsson et al. 2014.
</p>

<div class="agent-guide">
  <strong>For AI agents / humans reading this report:</strong>
  the sections below are structured so you can answer questions about
  what was found and how confident to be. Start with the <em>Executive
  summary</em> for the top-line, then check <em>Inventory</em> for
  category counts + CIs, <em>Reliability</em> for interpretation
  agreement, and <em>Raw Gemini responses</em> if you need to audit
  what the model actually returned.
</div>

<div class="meta">
  <div class="stat">Model: <strong>{model}</strong></div>
  <div class="stat">Samples: <strong>{n_used}</strong> unique panos
    (from {n_drawn} draws, {iterations} iterations)</div>
  <div class="stat">Categories: <strong>{n_cats}</strong></div>
  <div class="stat">Duration: <strong>{duration_s:.1f}s</strong></div>
  <div class="stat">Tokens: <strong>{total_tokens:,}</strong></div>
  <div class="stat">Indoor filter: <strong>{exclude_indoor}</strong></div>
</div>

<h2>Executive summary</h2>
<div class="agent-guide">{exec_summary}</div>

<h2>Sample locations</h2>
{sample_map_html}

<h2>Composition</h2>
<p style="font-size:12px; color:var(--fg-muted);">
  Donut shows share of total instance count. Horizontal bars show
  <em>presence proportion</em> (fraction of samples containing the
  category at least once) with Wilson 95 % CI whiskers. Colors are
  auto-assigned semantically (green for vegetation, grey for pavement,
  blue for water, warm tones for vehicles, …) — same colors reused in
  every chart and in the table below when they render.
</p>
{composition_html}

<h2>Inventory table</h2>
<p style="font-size:12px; color:var(--fg-muted);">
  <strong>How to read:</strong>
  <code>count_total</code> is total instance count across all samples;
  <code>mean_per_sample</code> is count ÷ n_samples;
  <code>proportion_of_samples</code> is the fraction of samples where at least
  one instance appeared (per-sample presence);
  <code>ci95_prop_wilson_*</code> are Wilson score 95 % CIs for that proportion;
  <code>ci95_prop_boot_*</code> and <code>ci95_mean_boot_*</code> are
  percentile-bootstrap 95 % CIs.
</p>
{inventory_table}

<h2>Per-sample records</h2>
{per_sample_html}

<h2>Interpretation reliability</h2>
{reliability_html}

<h2>Taxonomy mapping (raw → canonical)</h2>
<details><summary>Show {n_mapping} label mapping(s)</summary>
{taxonomy_table}
</details>

<h2>Raw Gemini responses (per batch)</h2>
<p style="font-size:12px; color:var(--fg-muted);">
  Every batch call is preserved verbatim below — prompt sent + raw JSON
  emitted by Gemini + token counts. Use this to audit interpretation
  quality or diagnose parse errors.
</p>
{batches_html}

<h2>Full run metadata</h2>
<details><summary>Show full metadata JSON</summary>
<pre>{metadata_pretty}</pre>
</details>

{gallery_html}

</body></html>
"""


def _rows_to_html_table(rows: list[dict]) -> str:
    if not rows:
        return "<p><em>No categories detected.</em></p>"
    cols = list(rows[0].keys())
    head = "".join(f"<th>{c}</th>" for c in cols)
    body = "".join(
        "<tr>" + "".join(f"<td>{_html_escape(str(r.get(c, '')))}</td>"
                          for c in cols) + "</tr>"
        for r in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _html_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;")
             .replace("'", "&#39;"))


def _file_to_data_uri(path: str) -> str | None:
    """Return a ``data:image/<ext>;base64,<b64>`` URI for an image file.

    Embedding as data URIs makes the HTML report self-contained — it
    opens correctly when shared standalone (email, chat, deploy) even
    if the sibling ``images/`` folder is missing.
    """
    if not path or not _os.path.isfile(path):
        return None
    ext = path.rsplit(".", 1)[-1].lower()
    mime = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png",  "gif": "image/gif",
        "webp": "image/webp",
    }.get(ext, "application/octet-stream")
    with open(path, "rb") as f:
        b64 = _b64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _rows_to_md_table(rows: list[dict]) -> str:
    if not rows:
        return "_No categories detected._"
    cols = list(rows[0].keys())
    head = "| " + " | ".join(cols) + " |\n"
    head += "|" + "|".join("---" for _ in cols) + "|\n"
    body = "\n".join(
        "| " + " | ".join(str(r.get(c, "")) for c in cols) + " |"
        for r in rows
    )
    return head + body


def _build_exec_summary(result: dict) -> str:
    """One-paragraph plain-English summary of the top findings.

    Written so a downstream LLM can quote it directly to a user without
    re-reading the whole report.
    """
    inv = result["inventory_rows"]
    md = result["metadata"]
    n_samples = md.get("n_unique_panos", 0)
    if not inv:
        return f"No categories were detected across {n_samples} sample(s)."
    top = inv[:5]
    parts = []
    for r in top:
        parts.append(
            f"<strong>{_html_escape(r['category'])}</strong> "
            f"(total {r['count_total']}, present in "
            f"{r['samples_with']}/{n_samples} samples, "
            f"proportion {r['proportion_of_samples']:.2f} "
            f"[95% CI {r['ci95_prop_wilson_low']:.2f}–"
            f"{r['ci95_prop_wilson_high']:.2f}])"
        )
    return (
        f"Across {n_samples} unique panorama location(s), {len(inv)} "
        f"canonical feature categor(ies) were detected. Top-5 by total "
        f"count: " + "; ".join(parts) + "."
    )


# ── Visual-aid helpers: colors + SVG charts ─────────────────────────────
# Self-contained: no external JS, no CDN, no extra deps. All charts render
# as inline SVG so the report stays a single portable HTML file.

_FALLBACK_PALETTE = (
    # Kelly's max-distinct palette (22 colors, minus black/white) —
    # readable on both light and dark backgrounds. Used when Gemini
    # semantic coloring fails or isn't invoked.
    "#F3C300", "#875692", "#F38400", "#A1CAF1", "#BE0032",
    "#C2B280", "#848482", "#008856", "#E68FAC", "#0067A5",
    "#F99379", "#604E97", "#F6A600", "#B3446C", "#DCD300",
    "#882D17", "#8DB600", "#654522", "#E25822", "#2B3D26",
)


def _hash_color(name: str) -> str:
    """Deterministic HSL color from a category name. Golden-angle
    stepping keeps consecutive picks maximally separated even for
    similar-hashing names."""
    import hashlib
    h = int(hashlib.sha1(name.encode("utf-8")).hexdigest()[:8], 16)
    hue = (h * 137.508) % 360   # golden-angle step
    sat = 55 + (h % 30)          # 55-85 %
    light = 45 + ((h // 100) % 20)  # 45-65 %
    return f"hsl({hue:.0f} {sat}% {light}%)"


def _generate_category_colors(
    categories: list[str],
    model: str = _lu.DEFAULT_MODEL,
) -> dict[str, str]:
    """Ask Gemini for a semantic hex color per category (green for
    plants, grey for pavement, blue for water, …). Failure — network,
    API key missing, unparseable — falls back to a deterministic palette
    so charts always render. Returns ``{category: "#RRGGBB"}``.

    Runs a single low-token call, ~200 tokens for 30 categories, T=0.
    """
    if not categories:
        return {}
    # Deterministic fallback first — used verbatim if Gemini fails.
    fallback = {
        c: (_FALLBACK_PALETTE[i % len(_FALLBACK_PALETTE)] if i < len(_FALLBACK_PALETTE)
             else _hash_color(c))
        for i, c in enumerate(categories)
    }
    try:
        from google import genai
        import geeViz.googleMapsLib as _gm_local
        client = genai.Client(api_key=_gm_local._get_gemini_key())
        cats_json = _json.dumps(list(categories))
        prompt = (
            "You color-code data-visualization categories so a chart "
            "reader can guess what each slice means from color alone. "
            "For each category below, return an intuitive semantic hex "
            "color (green tones for vegetation/trees/grass, grey for "
            "pavement/road/sidewalk, blue for water/sky, warm reds/"
            "oranges for vehicles, browns for soil/bare-ground, etc.). "
            "Use varied hues across categories that don't have an "
            "obvious semantic mapping. Colors must be readable on both "
            "light and dark backgrounds — avoid near-black and "
            "near-white.\n\n"
            f"Categories: {cats_json}\n\n"
            "Return ONLY a JSON object mapping each category (verbatim) "
            'to a hex color like "#4CAF50". No narrative, no code fences.'
        )
        # google-genai SDK — same import surface as the rest of the file
        resp = client.models.generate_content(
            model=model,
            contents=prompt,
            config={"temperature": 0.0, "response_mime_type": "application/json"},
        )
        # Small call, but it runs once per inventory report and was the
        # last geeViz Gemini call reporting nothing.
        _lu.report(_lu.usage_from_response(
            resp, model=model, source="geeviz.inventory.colors"))
        text = (getattr(resp, "text", None) or "").strip()
        parsed = _json.loads(text)
        result_colors = {}
        for cat in categories:
            v = parsed.get(cat)
            if isinstance(v, str) and v.startswith("#") and len(v) in (4, 7):
                result_colors[cat] = v
            else:
                result_colors[cat] = fallback[cat]
        return result_colors
    except Exception:
        # Any failure — fall back silently. Report still gets charts.
        return fallback


def _render_donut_svg(rows: list[dict], colors: dict[str, str],
                       max_show: int = 12, size: int = 300) -> str:
    """Render a donut chart of composition by ``count_total``. Categories
    beyond ``max_show`` are rolled into an ``other`` slice. Returns a
    self-contained SVG string."""
    if not rows:
        return "<p><em>No categories to chart.</em></p>"
    top = rows[:max_show]
    others = rows[max_show:]
    slices = [(r["category"], r["count_total"], colors.get(r["category"], "#888"))
              for r in top if r["count_total"] > 0]
    if others:
        others_sum = sum(r["count_total"] for r in others)
        if others_sum > 0:
            slices.append((f"other ({len(others)})", others_sum, "#B0B7BF"))
    total = sum(v for _, v, _ in slices)
    if total <= 0:
        return "<p><em>All category counts are zero.</em></p>"
    cx = cy = size / 2
    r_outer = size / 2 - 4
    r_inner = r_outer * 0.55
    import math
    parts = []
    cursor_deg = -90.0  # 12 o'clock start
    legend_rows = []
    for label, val, color in slices:
        frac = val / total
        sweep = frac * 360.0
        a1 = math.radians(cursor_deg)
        a2 = math.radians(cursor_deg + sweep)
        x1o, y1o = cx + r_outer * math.cos(a1), cy + r_outer * math.sin(a1)
        x2o, y2o = cx + r_outer * math.cos(a2), cy + r_outer * math.sin(a2)
        x1i, y1i = cx + r_inner * math.cos(a1), cy + r_inner * math.sin(a1)
        x2i, y2i = cx + r_inner * math.cos(a2), cy + r_inner * math.sin(a2)
        large = 1 if sweep > 180 else 0
        d = (f"M {x1o:.2f} {y1o:.2f} "
             f"A {r_outer:.2f} {r_outer:.2f} 0 {large} 1 {x2o:.2f} {y2o:.2f} "
             f"L {x2i:.2f} {y2i:.2f} "
             f"A {r_inner:.2f} {r_inner:.2f} 0 {large} 0 {x1i:.2f} {y1i:.2f} Z")
        parts.append(
            f'<path d="{d}" fill="{color}" stroke="#fff" stroke-width="1">'
            f'<title>{_html_escape(label)}: {val} ({frac*100:.1f}%)</title>'
            f'</path>'
        )
        legend_rows.append(
            f'<div style="display:flex; align-items:center; margin:2px 0; '
            f'font-size:12px; line-height:1.3;">'
            f'<span style="display:inline-block; width:12px; height:12px; '
            f'background:{color}; border:1px solid #999; margin-right:6px; '
            f'flex:0 0 12px;"></span>'
            f'<span style="flex:1;">{_html_escape(label)}</span>'
            f'<span style="color:var(--fg-muted); margin-left:8px;">{val} ({frac*100:.1f}%)</span>'
            f'</div>'
        )
        cursor_deg += sweep
    center_label = (
        f'<text x="{cx}" y="{cy - 4}" text-anchor="middle" '
        f'style="font-size:22px; font-weight:600; fill:#333;">{len(slices)}</text>'
        f'<text x="{cx}" y="{cy + 14}" text-anchor="middle" '
        f'style="font-size:11px; fill:#666;">categories</text>'
    )
    svg = (
        f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}" '
        f'role="img" aria-label="Composition by count">'
        + "".join(parts) + center_label + "</svg>"
    )
    return (
        '<div style="display:flex; flex-wrap:wrap; gap:16px; align-items:flex-start;">'
        f'<div style="flex:0 0 auto;">{svg}</div>'
        f'<div style="flex:1 1 260px; min-width:260px;">{"".join(legend_rows)}</div>'
        '</div>'
    )


def _render_composition_bar_svg(rows: list[dict], colors: dict[str, str],
                                  max_show: int = 15, width: int = 600) -> str:
    """Horizontal bar chart of ``proportion_of_samples`` with Wilson
    95 % CI whiskers. Categories are sorted by proportion desc; anything
    beyond ``max_show`` is dropped from this view (the table below shows
    everything)."""
    if not rows:
        return ""
    ranked = sorted(rows, key=lambda r: -r.get("proportion_of_samples", 0))[:max_show]
    if not ranked:
        return ""
    bar_h = 22
    label_w = 150
    pad = 8
    axis_h = 24
    plot_w = max(200, width - label_w - pad - 30)
    height = axis_h + len(ranked) * bar_h + pad
    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'role="img" aria-label="Presence proportion with 95% Wilson CI">'
    ]
    # Axis gridlines at 0, .25, .5, .75, 1
    for x_frac in (0, 0.25, 0.5, 0.75, 1.0):
        x = label_w + pad + x_frac * plot_w
        parts.append(
            f'<line x1="{x}" y1="{axis_h}" x2="{x}" y2="{height - pad}" '
            f'stroke="#e5e5e5" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{x}" y="{axis_h - 4}" text-anchor="middle" '
            f'style="font-size:10px; fill:#888;">{int(x_frac*100)}%</text>'
        )
    # Rows
    for i, r in enumerate(ranked):
        cat = r["category"]
        prop = r.get("proportion_of_samples", 0) or 0
        lo = r.get("ci95_prop_wilson_low", prop) or 0
        hi = r.get("ci95_prop_wilson_high", prop) or 0
        color = colors.get(cat, "#888")
        y = axis_h + i * bar_h + 3
        bar_w = prop * plot_w
        x0 = label_w + pad
        parts.append(
            f'<text x="{label_w - 4}" y="{y + bar_h * 0.62}" text-anchor="end" '
            f'style="font-size:12px; fill:#333;">'
            f'{_html_escape(cat[:20])}</text>'
        )
        parts.append(
            f'<rect x="{x0}" y="{y}" width="{bar_w:.1f}" '
            f'height="{bar_h - 6}" fill="{color}" opacity="0.85">'
            f'<title>{_html_escape(cat)}: {prop*100:.1f}% '
            f'(95% CI {lo*100:.1f}–{hi*100:.1f}%)</title>'
            f'</rect>'
        )
        # CI whisker line + caps
        lo_x = x0 + lo * plot_w
        hi_x = x0 + hi * plot_w
        cy = y + (bar_h - 6) / 2
        parts.append(
            f'<line x1="{lo_x:.1f}" y1="{cy}" x2="{hi_x:.1f}" y2="{cy}" '
            f'stroke="#333" stroke-width="1.5"/>'
            f'<line x1="{lo_x:.1f}" y1="{cy - 4}" x2="{lo_x:.1f}" y2="{cy + 4}" '
            f'stroke="#333" stroke-width="1.5"/>'
            f'<line x1="{hi_x:.1f}" y1="{cy - 4}" x2="{hi_x:.1f}" y2="{cy + 4}" '
            f'stroke="#333" stroke-width="1.5"/>'
        )
        parts.append(
            f'<text x="{x0 + plot_w + 4}" y="{y + bar_h * 0.62}" '
            f'style="font-size:11px; fill:#555;">'
            f'{prop*100:.0f}% ({r.get("samples_with", 0)})</text>'
        )
    parts.append("</svg>")
    return (
        '<div style="margin-top:8px;">'
        '<div style="font-size:12px; color:var(--fg-muted); margin-bottom:6px;">'
        f'Presence in samples (bars) with Wilson 95 % CI (whiskers); '
        f'top {len(ranked)} of {len(rows)} categories.'
        '</div>' + "".join(parts) + '</div>'
    )


def _render_composition_charts_html(rows: list[dict],
                                      colors: dict[str, str]) -> str:
    """Combine donut + bar into one composition section."""
    if not rows:
        return "<p><em>No categories detected — nothing to chart.</em></p>"
    donut = _render_donut_svg(rows, colors)
    bars = _render_composition_bar_svg(rows, colors)
    return (
        f'<div style="margin-bottom:10px;">{donut}</div>'
        f'{bars}'
    )


def _render_html_report(result: dict, output_path: str) -> str:
    """Write the standalone HTML report. Returns the path."""
    inv = result["inventory_rows"]
    rel = result["reliability"]
    md = result["metadata"]
    out_dir = _os.path.dirname(output_path)

    reliability_html = (
        f"<div class='meta'>"
        f"<div class='stat'>Cohen's κ (presence): <strong>{rel.get('kappa_presence')}</strong></div>"
        f"<div class='stat'>ICC (counts): <strong>{rel.get('icc_counts')}</strong></div>"
        f"<div class='stat'>n repeated: <strong>{rel.get('n_repeated', 0)}</strong></div>"
        f"<div class='stat'>n categories compared: <strong>{rel.get('n_categories', '—')}</strong></div>"
        f"</div>"
        + "<p style='font-size:12px; color:var(--fg-muted);'>"
          "Cohen's κ interpretation: &lt;0 worse than chance; 0-0.2 slight; "
          "0.2-0.4 fair; 0.4-0.6 moderate; 0.6-0.8 substantial; 0.8-1 almost perfect. "
          "At small n_repeated (&lt;5) κ is noisy — treat as directional, not conclusive."
          "</p>"
        if rel and rel.get("n_repeated") else
        "<p><em>Reliability subset disabled (reliability_fraction=0).</em></p>"
    )

    # ── Sample map (base64-embedded for a self-contained report) ──
    sample_map_html = "<p><em>Sample map not generated.</em></p>"
    if result.get("sample_map_path"):
        _map_uri = _file_to_data_uri(result["sample_map_path"])
        if _map_uri:
            sample_map_html = (
                f"<div class='sample-map'><img src='{_map_uri}' "
                f"alt='Sample locations on hybrid map'></div>"
            )

    # ── Per-sample records (with embedded thumbnails per image type) ──
    per_sample_html = "<table><thead><tr>"
    for h in ("sample_id", "lon / lat", "pano_id", "pano_date",
              "copyright", "coverage_status", "labels", "images"):
        per_sample_html += f"<th>{h}</th>"
    per_sample_html += "</tr></thead><tbody>"
    for s in result["samples"]:
        labels_summary = ", ".join(
            f"{l['category']}({l['count']})"
            for l in s.get("canonical_labels", [])[:10]
        )
        if len(s.get("canonical_labels", [])) > 10:
            labels_summary += f" … +{len(s['canonical_labels']) - 10} more"
        # Thumbnails per image type — data URIs so nothing external is needed.
        thumbs_html = ""
        for typ, path in sorted(s.get("image_paths", {}).items()):
            uri = _file_to_data_uri(path)
            if uri:
                thumbs_html += (
                    f"<figure style='display:inline-block; margin:2px; "
                    f"text-align:center;'>"
                    f"<img src='{uri}' alt='{_html_escape(typ)}' "
                    f"style='max-height:96px; max-width:128px; "
                    f"border:1px solid #ddd; border-radius:3px;'>"
                    f"<figcaption style='font-size:10px; color:var(--fg-muted);'>"
                    f"{_html_escape(typ)}</figcaption></figure>"
                )
        per_sample_html += (
            "<tr>"
            f"<td>{_html_escape(str(s.get('sample_id')))}</td>"
            f"<td>{s.get('lon'):.6f}<br>{s.get('lat'):.6f}</td>"
            f"<td><code>{_html_escape(str(s.get('pano_id') or ''))}</code></td>"
            f"<td>{_html_escape(str(s.get('pano_date') or ''))}</td>"
            f"<td style='font-size:11px;'>{_html_escape(str(s.get('pano_copyright') or ''))}</td>"
            f"<td>{_html_escape(str(s.get('coverage_status')))}</td>"
            f"<td style='max-width:280px;'>"
            f"<strong>{len(s.get('canonical_labels', []))}</strong> label(s):<br>"
            f"<span style='font-size:11px;'>{_html_escape(labels_summary)}</span>"
            f"</td>"
            f"<td>{thumbs_html or '<em>(no images)</em>'}</td>"
            "</tr>"
        )
    per_sample_html += "</tbody></table>"

    # ── Taxonomy mapping ──
    mapping = result.get("taxonomy_mapping", {})
    if mapping:
        # Sort by canonical then raw
        tax_rows = sorted(mapping.items(), key=lambda kv: (kv[1], kv[0]))
        taxonomy_table = "<table><thead><tr><th>Raw label (Gemini)</th><th>Canonical</th></tr></thead><tbody>"
        for raw, canon in tax_rows:
            taxonomy_table += (
                f"<tr><td>{_html_escape(raw)}</td>"
                f"<td><strong>{_html_escape(canon)}</strong></td></tr>"
            )
        taxonomy_table += "</tbody></table>"
    else:
        taxonomy_table = "<p><em>No mapping (fixed-category mode).</em></p>"

    # ── Batches (raw prompts + responses) ──
    batches = result.get("batches", []) or []
    batches_html_parts = []
    for i, b in enumerate(batches):
        stage = b.get("stage", "?")
        bn = b.get("batch_number", i + 1)
        sids = b.get("sample_ids", [])
        toks = (f"in={b.get('prompt_tokens') or 0:,} "
                f"out={b.get('candidates_tokens') or 0:,} "
                f"thoughts={b.get('thoughts_tokens') or 0:,} "
                f"total={b.get('total_tokens') or 0:,}")
        err = b.get("error")
        summary = (
            f"batch {bn} · stage=<code>{stage}</code> · "
            f"T={b.get('temperature')} · samples={sids} · "
            f"{toks} · {b.get('duration_s', 0)}s"
            + (f" · <span style='color:#c00'>error: {_html_escape(str(err))}</span>" if err else "")
        )
        raw = b.get("raw_response") or ""
        prompt = b.get("prompt") or ""
        batches_html_parts.append(
            f"<details><summary>{summary}</summary>"
            f"<h3>Prompt sent</h3>"
            f"<pre>{_html_escape(prompt)}</pre>"
            f"<h3>Raw Gemini response</h3>"
            f"<pre>{_html_escape(raw)}</pre>"
            f"</details>"
        )
    batches_html = "\n".join(batches_html_parts) or "<p><em>No batches.</em></p>"

    # ── Sample-image gallery ──
    gallery_html = ""
    if md.get("include_gallery"):
        rows_g = ""
        for s in result["samples"]:
            for typ, path in s.get("image_paths", {}).items():
                uri = _file_to_data_uri(path)
                if not uri:
                    continue
                rows_g += (f"<figure><img src='{uri}'>"
                            f"<figcaption>#{s['sample_id']} "
                            f"{_html_escape(typ)}</figcaption>"
                            f"</figure>")
        if rows_g:
            gallery_html = f"<h2>Sample images</h2><div class='gallery'>{rows_g}</div>"

    # Semantic auto-colors via Gemini (with hash-based fallback). Cached
    # into the result dict so the JSON dump and any downstream consumers
    # can reuse them (e.g. matching swatches in a UI table).
    _cats = [r["category"] for r in inv]
    _colors = result.get("category_colors")
    if not _colors:
        _colors = _generate_category_colors(_cats, model=md.get("model", _lu.DEFAULT_MODEL))
        result["category_colors"] = _colors
        md["category_colors"] = _colors
    composition_html = _render_composition_charts_html(inv, _colors)

    html = _HTML_TEMPLATE.format(
        title=md.get("title", "Image inventory"),
        exec_summary=_build_exec_summary(result),
        n_used=md["n_unique_panos"],
        n_drawn=md["n_samples_drawn"],
        iterations=md["dedup_iterations"],
        n_cats=len(inv),
        model=md.get("model", ""),
        duration_s=md.get("duration_s", 0.0),
        total_tokens=md.get("total_tokens", 0) or 0,
        exclude_indoor=md.get("exclude_indoor", True),
        sample_map_html=sample_map_html,
        composition_html=composition_html,
        inventory_table=_rows_to_html_table(inv),
        per_sample_html=per_sample_html,
        reliability_html=reliability_html,
        n_mapping=len(mapping),
        taxonomy_table=taxonomy_table,
        batches_html=batches_html,
        metadata_pretty=_html_escape(_json.dumps(md, indent=2, default=str)),
        gallery_html=gallery_html,
    )
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    return output_path


def _render_md_report(result: dict, output_path: str) -> str:
    """Write a comprehensive markdown report — agent- and human-readable.

    Includes: executive summary, sample-map reference, full inventory
    table, per-sample records, taxonomy mapping, reliability, and each
    batch's raw prompt + response verbatim. Structured so an LLM agent
    can quote directly from any section.
    """
    inv = result["inventory_rows"]
    rel = result["reliability"]
    md = result["metadata"]
    out_dir = _os.path.dirname(output_path)

    L = []
    L.append(f"# {md.get('title', 'Image inventory')}\n")
    L.append(
        "> Design-based image inventory generated by "
        "`geeViz.inventoryLib.inventory_area`. "
        "Sampling per Cochran (1977); estimation follows Olofsson et al. 2014.\n"
    )

    # ── Agent guide ──
    L.append("## For agents / readers\n")
    L.append(
        "This report is structured so you can answer questions about what "
        "was found and how confident to be:\n"
    )
    L.append(
        "- **Executive summary** — top-line finding for a quick answer.\n"
        "- **Sample locations** — hybrid-map thumbnail with pins at each sample.\n"
        "- **Inventory table** — every canonical category with counts, "
        "proportions, Wilson 95 % CI, bootstrap 95 % CI.\n"
        "- **Per-sample records** — what each panorama contained.\n"
        "- **Taxonomy mapping** — how raw Gemini labels were canonicalised.\n"
        "- **Interpretation reliability** — how consistent Gemini was on a "
        "re-interpreted subset (Cohen's κ, ICC).\n"
        "- **Raw Gemini responses** — every batch's prompt + verbatim "
        "JSON response, for audit and reproducibility.\n"
    )

    # ── Executive summary (plain text, no HTML) ──
    L.append("\n## Executive summary\n")
    if not inv:
        L.append(f"No categories detected across {md['n_unique_panos']} sample(s).\n")
    else:
        n = md["n_unique_panos"]
        L.append(
            f"Across **{n} unique panorama location(s)**, "
            f"**{len(inv)} canonical feature categor(ies)** were detected. "
            "Top-5 by total count:\n"
        )
        for r in inv[:5]:
            L.append(
                f"- **{r['category']}** — total {r['count_total']}, present in "
                f"{r['samples_with']}/{n} samples (proportion "
                f"{r['proportion_of_samples']:.2f}, 95 % CI "
                f"{r['ci95_prop_wilson_low']:.2f}–{r['ci95_prop_wilson_high']:.2f})"
            )

    # ── Run metadata (compact) ──
    L.append("\n## Run metadata\n")
    L.append(f"- **Model:** `{md.get('model')}`, T={md.get('temperature')}")
    L.append(f"- **Sampling:** `{md.get('sampling')}`, seed={md.get('seed')}, "
             f"n_bootstrap={md.get('n_bootstrap')}")
    L.append(f"- **Unique panoramas:** {md['n_unique_panos']} "
             f"(from {md['n_samples_drawn']} draws, "
             f"{md['dedup_iterations']} refill iteration(s), "
             f"hit_cap={md.get('hit_iteration_cap')})")
    L.append(f"- **Coverage:** {md['no_coverage_count']} no-coverage points "
             f"dropped; {md['duplicate_count']} duplicate panos dropped")
    L.append(f"- **Image types per sample:** {md.get('image_types')}")
    L.append(f"- **Categories mode:** `{md.get('categories_mode')}` "
             f"(supplied={md.get('categories_supplied')})")
    L.append(f"- **Indoor exclusion:** `{md.get('exclude_indoor')}`")
    L.append(f"- **Reliability:** fraction={md.get('reliability_fraction')}, "
             f"T={md.get('reliability_temperature')}")
    L.append(f"- **Duration:** {md.get('duration_s', 0):.1f}s")
    L.append(f"- **Total Gemini tokens:** {md.get('total_tokens', 0) or 0:,} "
             f"across {md.get('batch_calls', 0)} batch call(s)")

    # ── Sample map (image reference) ──
    L.append("\n## Sample locations\n")
    if result.get("sample_map_path"):
        rel_map = _os.path.relpath(
            result["sample_map_path"], out_dir,
        ).replace(chr(92), "/")
        L.append(f"![Sample locations]({rel_map})\n")
        L.append(f"Hybrid map with a pin at each of the {md['n_unique_panos']} "
                 f"unique panorama locations. File: `{rel_map}`.\n")
    else:
        L.append("_(Sample map not generated — pass `output_dir=` to enable.)_\n")

    # ── Inventory table ──
    L.append("\n## Inventory\n")
    L.append(
        "How to read: `count_total` = total instance count across all "
        "samples; `mean_per_sample` = count ÷ n_samples; "
        "`proportion_of_samples` = fraction of samples where the category "
        "appeared at least once; `ci95_prop_wilson_*` = Wilson score 95 % CI "
        "for that proportion; `ci95_prop_boot_*` and `ci95_mean_boot_*` = "
        "percentile-bootstrap 95 % CIs.\n"
    )
    L.append(_rows_to_md_table(inv))

    # ── Per-sample records ──
    L.append("\n## Per-sample records\n")
    for s in result["samples"]:
        labels = s.get("canonical_labels", [])
        labels_str = ", ".join(f"{l['category']} ({l['count']})" for l in labels)
        if not labels_str:
            labels_str = "_(no labels)_"
        L.append(f"### Sample {s['sample_id']}\n")
        L.append(
            f"- **Location:** lon={s['lon']:.6f}, lat={s['lat']:.6f}"
        )
        L.append(
            f"- **Pano:** `{s.get('pano_id')}` "
            f"(date `{s.get('pano_date')}`, "
            f"copyright `{s.get('pano_copyright') or '?'}`)"
        )
        L.append(f"- **Coverage status:** `{s.get('coverage_status')}`")
        L.append(f"- **Labels ({len(labels)}):** {labels_str}")
        if s.get("interp_error"):
            L.append(f"- ⚠ **interp_error:** `{s['interp_error']}`")
        # Sample images — relative paths so MD renderers (GitHub,
        # VSCode, obsidian) show them alongside. The HTML report
        # embeds base64 for a self-contained document; the MD relies
        # on the sibling images/ folder.
        for typ, path in sorted(s.get("image_paths", {}).items()):
            rel_p = _os.path.relpath(path, out_dir).replace(chr(92), "/")
            L.append(f"\n  ![sample {s['sample_id']} — {typ}]({rel_p})")
        L.append("")   # blank separator

    # ── Reliability ──
    L.append("\n## Interpretation reliability\n")
    if rel and rel.get("n_repeated"):
        L.append(f"- **Cohen's κ (presence):** {rel.get('kappa_presence')}")
        L.append(f"- **ICC (counts):** {rel.get('icc_counts')}")
        L.append(f"- **n repeated:** {rel.get('n_repeated')}")
        L.append(f"- **n categories compared:** {rel.get('n_categories', '—')}")
        L.append(
            "\nInterpretation guide: κ <0 = worse than chance, 0–0.2 = slight, "
            "0.2–0.4 = fair, 0.4–0.6 = moderate, 0.6–0.8 = substantial, "
            "0.8–1 = almost perfect. At small n_repeated (<5), κ is noisy — "
            "treat as directional, not conclusive.\n"
        )
    else:
        L.append("_Reliability subset disabled (`reliability_fraction=0`)._")

    # ── Taxonomy mapping ──
    mapping = result.get("taxonomy_mapping", {})
    L.append("\n## Taxonomy mapping (raw → canonical)\n")
    if mapping:
        tax_rows = sorted(mapping.items(), key=lambda kv: (kv[1], kv[0]))
        L.append("| Raw label | Canonical |")
        L.append("|---|---|")
        for raw, canon in tax_rows:
            L.append(f"| {raw} | **{canon}** |")
    else:
        L.append("_No mapping (fixed-category mode)._")

    # ── Raw Gemini responses ──
    L.append("\n## Raw Gemini responses (per batch)\n")
    L.append(
        "Every batch call is preserved verbatim below — prompt sent, raw "
        "JSON emitted by Gemini, and token counts. Use this to audit "
        "interpretation quality or diagnose parse errors.\n"
    )
    batches = result.get("batches", []) or []
    for i, b in enumerate(batches):
        L.append(
            f"\n### Batch {b.get('batch_number', i+1)} "
            f"(stage=`{b.get('stage', '?')}`, T={b.get('temperature')})\n"
        )
        L.append(
            f"- Samples: {b.get('sample_ids')}"
        )
        L.append(
            f"- Tokens: in={b.get('prompt_tokens') or 0:,} "
            f"out={b.get('candidates_tokens') or 0:,} "
            f"thoughts={b.get('thoughts_tokens') or 0:,} "
            f"total={b.get('total_tokens') or 0:,}"
        )
        L.append(f"- Duration: {b.get('duration_s', 0)}s")
        if b.get("error"):
            L.append(f"- ⚠ Error: `{b['error']}`")
        L.append(f"- Records parsed: {b.get('records_parsed', '—')}")
        L.append("\n**Raw Gemini response:**\n")
        L.append("```json")
        L.append(b.get("raw_response") or "(empty)")
        L.append("```")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    return output_path


def _render_json(result: dict, output_path: str) -> str:
    with open(output_path, "w", encoding="utf-8") as f:
        _json.dump(result, f, indent=2, default=str)
    return output_path


# ---------------------------------------------------------------------------
# 8. Public API
# ---------------------------------------------------------------------------

def inventory_area(
    input,
    n_samples: int = 30,
    sampling: str = "random",
    strata=None,
    samples_per_class: dict[int, int] | None = None,
    radius: int = 200,
    source: str = "outdoor",
    image_types: tuple[str, ...] = ("streetview-pano", "satellite", "hybrid"),
    streetview_fov: float = 360,
    zoom_satellite: int = 18,
    zoom_hybrid: int = 17,
    zoom_roadmap: int = 15,
    zoom_terrain: int = 12,
    size: str = "640x480",
    categories: list[str] | None = None,
    max_samples_per_call: int = 20,
    model: str = _lu.DEFAULT_MODEL,
    temperature: float = 0.2,
    reliability_fraction: float = 0.2,
    reliability_temperature: float = 1.0,
    max_resample_iterations: int = 5,
    concurrency: int = 6,
    n_bootstrap: int = 2000,
    seed: int = 42,
    output_dir: str | None = None,
    title: str = "Image inventory",
    include_gallery: bool = False,
    output_formats: tuple[str, ...] = ("html", "json", "md"),
    area_km2: float | None = None,
    verbose: bool = True,
    exclude_indoor: bool = True,
    require_google_copyright: bool = True,
) -> dict:
    """Sample an area, fetch imagery, and produce a rigorous LLM inventory.

    See module docstring for the statistical framework. This is the
    end-to-end orchestrator.

    Args:
        input: One of — list of ``(lon, lat)`` tuples, ``{"polygon": [...]}``,
            ``{"bounds": (lon_min, lat_min, lon_max, lat_max)}``, or an
            ``ee.Geometry`` / ``ee.FeatureCollection``.
        n_samples: Target number of unique-panorama samples. Ignored
            when ``input`` is a list of explicit points. Defaults to 30.
        sampling: ``"random"``, ``"systematic"``, or ``"stratified"``.
            Stratified requires ``strata=`` + ``samples_per_class=``.
        strata: ``ee.Image`` with an integer class band for stratified
            sampling. Ignored otherwise.
        samples_per_class: Dict mapping stratum class value → sample
            count. Only used when ``sampling="stratified"``.
        radius: Search radius (meters) for the nearest Street View
            panorama at each sample point. Defaults to ``200``.
        source: Street View source — ``"default"`` or ``"outdoor"``.
        image_types: Tuple of image types to fetch per sample. Any
            subset of ``streetview-pano``, ``streetview``, ``satellite``,
            ``hybrid``, ``roadmap``, ``terrain``.
        streetview_fov: FOV for both ``streetview`` and
            ``streetview-pano`` image types. Defaults to ``360`` (full
            pano). Values ≤ 120 fetch a single Street View Static frame;
            larger values stitch multiple frames into a wider view via
            ``streetview_panorama``.
        zoom_satellite / zoom_hybrid / zoom_roadmap / zoom_terrain: Zoom
            level per static-map type.
        size: Static-map / Street View frame size.
        categories: If given, restrict Gemini to these categories +
            ``"other"``. If None, free-form emission → taxonomy
            consolidation pass.
        max_samples_per_call: Cap on samples per Gemini batch call.
            Defaults to ``20``. Batches run concurrently.
        model: Gemini model. Defaults to
            :data:`geeViz.llmUsage.DEFAULT_MODEL`.
        temperature: Sampling temperature for the primary inventory
            call. Defaults to ``0.2`` for repeatability.
        reliability_fraction: Fraction of samples to re-interpret at
            higher temperature to estimate agreement. Defaults to
            ``0.2``. Set to ``0`` to disable.
        reliability_temperature: Temperature for the reliability
            re-interpretation. Defaults to ``1.0``.
        max_resample_iterations: After pano dedup, if unique panos <
            ``n_samples``, redraw and retry — up to this many
            iterations. Defaults to ``5``.
        concurrency: Concurrent Gemini calls. Defaults to ``6``.
        n_bootstrap: Bootstrap replicates for percentile CIs. Defaults
            to ``2000``.
        seed: Random seed for reproducibility.
        output_dir: Where to write image files + reports. If None,
            images stay in memory + no reports are written (return
            dict still populated).
        title: Report title.
        include_gallery: If True, embed sample images in the HTML report.
        output_formats: Tuple of ``"html"``, ``"json"``, ``"md"`` —
            report files to write. Ignored if ``output_dir=None``.
        area_km2: Total area (km²) for extrapolated-total estimates.
            Optional; when given, adds ``est_total_extrapolated`` +
            CI columns to the inventory.

    Returns:
        dict with keys:

        - ``inventory_df`` (pandas.DataFrame): wide-form inventory
        - ``inventory_rows`` (list[dict]): same, dict form
        - ``long_df`` (pandas.DataFrame): ``(sample_id, category, count)``
        - ``samples`` (list[dict]): per-sample records with location +
          image paths + labels
        - ``reliability`` (dict): ``kappa_presence``, ``icc_counts``,
          ``n_repeated``
        - ``metadata`` (dict): full run metadata (dedup stats, timing,
          tokens, model, sampling design, seed, ...)
        - ``reports`` (dict): file paths written when ``output_dir`` is
          given, keyed by format::

              {"html_path": "<output_dir>/inventory.html",
               "json_path": "<output_dir>/inventory.json",
               "md_path":   "<output_dir>/inventory.md"}

          Only keys corresponding to formats in ``output_formats`` are
          present. Empty dict when ``output_dir=None``.
    """
    # Tenant-scoped enable/disable — same env-var switch that gates
    # gm.interpret_image / label_image / segment_image. When disabled,
    # this raises RuntimeError with a tenant-scoped message.
    from geeViz.googleMapsLib import _check_gmaps_ai_enabled
    _check_gmaps_ai_enabled("inventory_area")

    # Minimum-n guard. Below this floor the statistics are meaningless
    # (Wilson CI at 1/3 is 6–70 %, bootstrap CIs collapse), and Gemini
    # 3.5 Flash occasionally returns empty/unparseable JSON on tiny
    # batches — leaving the caller with an "empty inventory" result that
    # LOOKS successful. Fail loud with a clear ceiling so callers pick
    # a defensible n. Ignored when the caller supplies an explicit list
    # of points (they know what they're doing) — in that case n_samples
    # is derived from the list length.
    _MIN_N_SAMPLES = 10
    _is_point_list = isinstance(input, list) and input and isinstance(input[0], (tuple, list))
    if not _is_point_list and n_samples < _MIN_N_SAMPLES:
        raise ValueError(
            f"n_samples={n_samples} is too small for a design-based inventory "
            f"(minimum {_MIN_N_SAMPLES}). Wilson 95 % CIs at n<{_MIN_N_SAMPLES} "
            f"are so wide they carry no information, bootstrap CIs collapse, "
            f"and Gemini batch interpretation is unstable at tiny sample sizes. "
            f"Use n_samples>={_MIN_N_SAMPLES} (30+ is typical for reasonably tight "
            f"CIs; 100+ for narrow CIs on rare categories). To force a small run "
            f"anyway — for testing — pass an explicit list of (lon, lat) points."
        )

    t_start = _time.time()
    rng = _rand.Random(seed)

    # ── Banner ──
    _log("", verbose)
    _log(f"[inventory_area] ▶ Starting: target N={n_samples}, "
         f"sampling='{sampling}', model='{model}', T={temperature}, "
         f"image_types={list(image_types)}", verbose)
    _log(f"[inventory_area]   dedup radius={radius}m, "
         f"require_google_copyright={require_google_copyright}, "
         f"exclude_indoor={exclude_indoor}, "
         f"max_resample_iterations={max_resample_iterations}, "
         f"reliability_fraction={reliability_fraction}, "
         f"n_bootstrap={n_bootstrap}, seed={seed}", verbose)

    # ── Sampling + metadata + dedup+refill loop ──
    unique_samples, dedup_stats = _dedup_and_refill(
        input, n_samples, sampling, rng,
        radius=radius, source=source,
        max_iterations=max_resample_iterations,
        strata=strata, samples_per_class=samples_per_class,
        verbose=verbose,
        require_google_copyright=require_google_copyright,
    )
    if not unique_samples:
        raise RuntimeError(
            "0 samples with Street View coverage after "
            f"{dedup_stats['iterations']} refill iteration(s). "
            f"Try increasing `radius=` or picking a denser area."
        )

    # ── Sample-location map (static hybrid with pins) ──
    sample_map_path = None
    if output_dir:
        sample_map_path = _build_sample_map(
            unique_samples, output_dir, size=size,
            maptype="hybrid", verbose=verbose,
        )

    # ── Image fetching (parallel) ──
    img_dir = _os.path.join(output_dir, "images") if output_dir else None
    _fetch_all_images(
        unique_samples, image_types, streetview_fov,
        zoom_satellite, zoom_hybrid, zoom_roadmap, zoom_terrain,
        size=size, output_dir=img_dir, verbose=verbose,
        radius=radius, source=source,   # match the metadata search
    )

    # ── Async Gemini interpretation ──
    # Primary batches
    by_sample, batch_metas = _run_async(
        _run_all_batches(
            unique_samples, max_samples_per_call, categories,
            model, temperature, concurrency,
            stage="interp", verbose=verbose,
            exclude_indoor=exclude_indoor,
        )
    )
    # Attach raw labels back to samples
    for s in unique_samples:
        s.raw_labels = by_sample.get(s.sample_id, [])

    # ── Reliability subset (re-interpret at higher T) ──
    reliability = {"n_repeated": 0}
    repeat_by_sample: dict[int, list[dict]] = {}
    if reliability_fraction > 0 and unique_samples:
        n_repeat = max(1, int(_math.ceil(reliability_fraction * len(unique_samples))))
        _log(f"[reliability] Re-interpreting {n_repeat}/{len(unique_samples)} "
             f"sample(s) at T={reliability_temperature} for agreement stats...",
             verbose)
        subset = rng.sample(unique_samples, n_repeat)
        repeat_by_sample, repeat_meta = _run_async(
            _run_all_batches(
                subset, max_samples_per_call, categories,
                model, reliability_temperature, concurrency,
                stage="reliability", verbose=verbose,
                exclude_indoor=exclude_indoor,
            )
        )
        batch_metas.extend(repeat_meta)
    else:
        _log(f"[reliability] Skipped (reliability_fraction=0)", verbose)

    # ── Taxonomy consolidation ──
    if categories:
        # Explicit schema — no consolidation, but normalise casing
        _log(f"[consolidate] Skipped — using caller-supplied fixed schema "
             f"of {len(categories)} categor(ies)", verbose)
        mapping = {}
        for s in unique_samples:
            for lbl in s.raw_labels:
                c = str(lbl.get("category", "")).strip().lower()
                if c:
                    mapping[c] = c
    else:
        raw_set = {
            str(lbl.get("category", "")).strip().lower()
            for s in unique_samples for lbl in s.raw_labels
            if lbl.get("category")
        }
        raw_set |= {
            str(lbl.get("category", "")).strip().lower()
            for labels in repeat_by_sample.values() for lbl in labels
            if lbl.get("category")
        }
        raw_set.discard("")
        _log(f"[consolidate] Consolidating {len(raw_set)} raw label(s) into "
             f"a canonical taxonomy (1 text-only Gemini call, T=0.0)...",
             verbose)
        t_cons = _time.time()
        from google import genai
        from geeViz import googleMapsLib as _gm

        async def _consolidate_with_cleanup():
            client = genai.Client(api_key=_gm._get_gemini_key())
            try:
                return await _consolidate_taxonomy(raw_set, model, client)
            finally:
                await _close_genai_client(client)

        mapping = _run_async(_consolidate_with_cleanup())
        n_canon = len(set(mapping.values()))
        _log(f"[consolidate] ✓ {len(raw_set)} raw → {n_canon} canonical "
             f"({_fmt_dur(_time.time() - t_cons)})", verbose)

    def _apply(labels):
        out: dict[str, int] = {}
        for lbl in labels:
            c = str(lbl.get("category", "")).strip().lower()
            canonical = mapping.get(c, c)
            if canonical:
                out[canonical] = out.get(canonical, 0) + int(lbl.get("count") or 0)
        return out

    per_sample_counts = {s.sample_id: _apply(s.raw_labels) for s in unique_samples}
    per_sample_counts_repeat = {sid: _apply(labels)
                                  for sid, labels in repeat_by_sample.items()}

    # Attach canonical labels to sample objects
    for s in unique_samples:
        counts = per_sample_counts[s.sample_id]
        s.canonical_labels = [{"category": k, "count": v} for k, v in counts.items()]

    # ── Reliability metrics ──
    if per_sample_counts_repeat:
        _log(f"[reliability] Computing Cohen's κ (presence) + ICC(1,1) "
             f"(counts) over {len(per_sample_counts_repeat)} repeated sample(s)...",
             verbose)
        t_rel = _time.time()
        reliability = _reliability_kappa_icc(
            per_sample_counts, per_sample_counts_repeat,
        )
        _log(f"[reliability] ✓ κ={reliability.get('kappa_presence')}  "
             f"ICC={reliability.get('icc_counts')}  "
             f"n_repeated={reliability.get('n_repeated')}  "
             f"({_fmt_dur(_time.time() - t_rel)})", verbose)

    # ── Statistics ──
    n_cats = len({c for counts in per_sample_counts.values() for c in counts})
    _log(f"[stats] Computing inventory stats for {n_cats} category(s) over "
         f"{len(per_sample_counts)} sample(s) — proportions, SEs, "
         f"Wilson score 95% CIs, bootstrap 95% CIs ({n_bootstrap} replicates)"
         f"{'  + area extrapolation' if area_km2 else ''}...",
         verbose)
    t_stats = _time.time()
    inv_rows = _compute_inventory_stats(
        per_sample_counts, area_km2, n_bootstrap, rng,
    )
    _log(f"[stats] ✓ {len(inv_rows)} row(s) built ({_fmt_dur(_time.time() - t_stats)})",
         verbose)

    # ── Aggregate metadata ──
    duration_s = _time.time() - t_start
    total_tokens = sum(m.get("total_tokens") or 0 for m in batch_metas)
    metadata = {
        "title": title,
        "model": model,
        "temperature": temperature,
        "sampling": sampling,
        "seed": seed,
        "n_samples_requested": n_samples,
        "n_samples_drawn": dedup_stats["drawn_total"],
        "n_unique_panos": dedup_stats["unique_panos"],
        "dedup_iterations": dedup_stats["iterations"],
        "hit_iteration_cap": dedup_stats["hit_iteration_cap"],
        "no_coverage_count": dedup_stats["no_coverage_count"],
        "duplicate_count": dedup_stats["duplicate_count"],
        "user_upload_count": dedup_stats.get("user_upload_count", 0),
        "require_google_copyright": require_google_copyright,
        "image_types": list(image_types),
        "categories_mode": "fixed" if categories else "auto",
        "categories_supplied": list(categories) if categories else None,
        "exclude_indoor": exclude_indoor,
        "reliability_fraction": reliability_fraction,
        "reliability_temperature": reliability_temperature,
        "n_bootstrap": n_bootstrap,
        "duration_s": round(duration_s, 2),
        "total_tokens": total_tokens,
        "batch_calls": len(batch_metas),
        "include_gallery": include_gallery,
    }

    # ── Assemble return payload ──
    result = {
        "inventory_rows": inv_rows,
        "samples": [
            {
                "sample_id": s.sample_id,
                "lon": s.lon,
                "lat": s.lat,
                "stratum": s.stratum,
                "pano_id": s.pano_id,
                "pano_lat": s.pano_lat,
                "pano_lon": s.pano_lon,
                "pano_date": s.pano_date,
                "pano_copyright": s.pano_copyright,
                "coverage_status": s.coverage_status,
                "image_paths": s.image_paths,
                "raw_labels": s.raw_labels,
                "canonical_labels": s.canonical_labels,
                "interp_error": s.interp_error,
            }
            for s in unique_samples
        ],
        "reliability": reliability,
        "metadata": metadata,
        "taxonomy_mapping": mapping,
        # Every Gemini batch call (primary + reliability), with full
        # prompt, raw response text, token counts, timing. Downstream
        # renderers use this; agents can re-parse for QA.
        "batches": batch_metas,
        # Path to a static hybrid map showing every sample as a pin
        # (written iff output_dir is given).
        "sample_map_path": sample_map_path,
    }

    # ── DataFrames (if pandas is available) ──
    try:
        import pandas as pd
        result["inventory_df"] = pd.DataFrame(inv_rows)
        long_rows = []
        for sid, counts in per_sample_counts.items():
            for cat, ct in counts.items():
                long_rows.append({"sample_id": sid, "category": cat, "count": ct})
        result["long_df"] = pd.DataFrame(long_rows)
    except ImportError:
        pass

    # ── Reports ──
    reports = {}
    if output_dir:
        _log(f"[reports] Writing outputs to {output_dir} "
             f"(formats={list(output_formats)}, gallery={include_gallery})...",
             verbose)
        _os.makedirs(output_dir, exist_ok=True)
        if "html" in output_formats:
            reports["html_path"] = _render_html_report(
                result, _os.path.join(output_dir, "inventory.html"),
            )
            _log(f"[reports]   ✓ HTML report → {reports['html_path']}", verbose)
        if "json" in output_formats:
            reports["json_path"] = _render_json(
                {k: v for k, v in result.items()
                 if k not in ("inventory_df", "long_df")},
                _os.path.join(output_dir, "inventory.json"),
            )
            _log(f"[reports]   ✓ JSON dump → {reports['json_path']}", verbose)
        if "md" in output_formats:
            reports["md_path"] = _render_md_report(
                result, _os.path.join(output_dir, "inventory.md"),
            )
            _log(f"[reports]   ✓ Markdown → {reports['md_path']}", verbose)
    else:
        _log(f"[reports] Skipped writing files (no output_dir given). "
             f"DataFrames + dict are still returned.", verbose)
    result["reports"] = reports

    # Surface report paths as top-level markdown so both the LLM and the
    # chat client see the same file references. Without this, the LLM
    # gets a nested ``{"reports": {"html_path": "..."}}`` in its tool
    # result and doesn't reliably mention the report in its reply — user
    # then can't tell there's a rendered report waiting for them. The
    # chat client's ``_parseFiles`` scans this string for markdown link
    # patterns and adds preview / download rows for each file.
    _md_lines = []
    _ext_labels = {
        "html_path":  ("HTML report",     True),   # inline preview
        "pdf_path":   ("PDF report",      False),  # download only
        "md_path":    ("Markdown report", False),
        "json_path":  ("JSON dump",       False),
    }
    for _key, (_label, _is_inline) in _ext_labels.items():
        _p = reports.get(_key)
        if _p and _os.path.exists(_p):
            _prefix = "!" if _is_inline else ""
            _md_lines.append(f"{_prefix}[{_label}]({_p.replace(chr(92), '/')})")
    if _md_lines:
        result["output_markdown"] = "\n".join(_md_lines)

    _log(f"[inventory_area] ▶ COMPLETE in {_fmt_dur(duration_s)} — "
         f"{len(unique_samples)} sample(s), {len(inv_rows)} categor(ies), "
         f"{total_tokens:,} tokens", verbose)
    if reports:
        _log(f"[inventory_area]   reports: {reports}", verbose)
    _log("", verbose)

    return result
