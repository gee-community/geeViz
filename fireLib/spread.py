"""Fire spread without a timestep loop.

The instinct when modeling spread on a raster is to iterate: dilate the
burned area, advance a timestep, repeat a few hundred times. On Earth
Engine that is the expensive path, and not by a little. Each neighborhood
operation expands the footprint a tile must fetch by one pixel, so a
hundred nested ones need a **hundred-pixel halo** on every tile. The
engine will either crawl or refuse.

The native primitive does it in one call. ``ee.Image.cumulativeCost``
computes, for each pixel, the minimum accumulated cost to reach it from a
source. Set cost to *time per unit distance* and least-accumulated-cost
**is** minimum travel time — the same quantity FlamMap's MTT computes,
and the solution to the Eikonal equation ``|grad T| = 1 / ROS``::

    cost    = ee.Image(1).divide(ros)
    arrival = cost.cumulativeCost(ignition, maxDistance=50000)

The hundred animation frames people wanted from the loop are a hundred
*thresholds of that single image*. No halo growth, no graph depth,
trivially parallel.

**The limitation, stated plainly: this is isotropic.** ``cumulativeCost``
assigns cost per *pixel*, not per *edge*, so it cannot express "cheap
downwind, expensive upwind". A single call gives fuel- and
terrain-modulated spread that is directionally neutral — no elliptical
head-fire elongation.

:func:`spread_with_wind_blocks` works around that by iterating
*coarsely* instead of finely: chain one call per wind period, each using
that period's wind. Twenty chained calls for a five-day fire is very
manageable, and it captures **wind shifts**, which is what drives the
large runs operationally. Within-block anisotropy is still lost. That
trade is fine for planning and risk; it is not fine for operational
head-fire prediction, and the difference should be stated in any product
built on this.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

#: Guards a runaway cumulativeCost. It bounds the search, so an
#: unreachable target does not walk the whole landscape.
DEFAULT_MAX_DISTANCE_M = 50_000


#: Whether ``cumulativeCost`` measures distance on the curved Earth
#: rather than in the map projection's plane.
#:
#: **This must stay True for anything in geographic coordinates**, and
#: the reason is measurable. With ``geodeticDistance=False`` on an
#: EPSG:4326 image, a degree of longitude is treated as the same ground
#: distance as a degree of latitude. It is not — it is shorter by
#: ``cos(latitude)`` — so east-west travel is inflated by
#: ``1 / cos(latitude)``.
#:
#: Measured at 44.2 deg N with a uniform 1 m/s spread rate, comparing
#: modeled arrival time against the analytic answer:
#:
#: ======================  =====  =====  ========
#: setting                 east   north  diagonal
#: ======================  =====  =====  ========
#: geodeticDistance=False  1.386  0.996  1.261
#: geodeticDistance=True   0.997  0.993  1.053
#: ======================  =====  =====  ========
#:
#: 1/cos(44.2 deg) = 1.394, which is the 1.386 almost exactly. A fire
#: would have spread 39% too slowly east-west and correctly north-south
#: — a systematic *directional* error that looks entirely plausible on a
#: map and gets worse toward the poles (2x at 60 deg N).
#:
#: The residual ~5% on the diagonal is the grid-path overhead: cost
#: accumulates between pixel centres, so the discrete shortest path is
#: slightly longer than the straight line.
GEODETIC_DISTANCE = True


def travel_time(ros_m_s, ignition, *,
                max_distance_m: int = DEFAULT_MAX_DISTANCE_M,
                min_ros_m_s: float = 1e-4,
                geodetic: bool = GEODETIC_DISTANCE):
    """Fire arrival time, in seconds, from an ignition source.

    Args:
        ros_m_s: Rate of spread in **metres per second** as an
            ``ee.Image``. Use :func:`~geeViz.fireLib.behavior.ros_metric`
            to convert from Rothermel's ft/min.
        ignition: ``ee.Image`` whose non-zero pixels are sources, or an
            ``ee.Geometry`` / ``ee.FeatureCollection`` to rasterize.
        max_distance_m: Search radius. Also the cost ceiling — pixels
            beyond it are masked rather than assigned a huge time.
        min_ros_m_s: Floor applied to the spread rate before inverting.
            Non-burnable fuel has ROS exactly zero, and ``1/0`` is
            infinite cost, which is *correct* but propagates as a
            masked pixel that can sever otherwise-connected paths. The
            floor makes non-fuel effectively impassable (a very large
            but finite cost) while keeping the cost surface defined.

    Returns:
        ``ee.Image`` band ``arrival_s`` — seconds for the fire to reach
        each pixel.

    Note:
        Cost-unit question, now settled empirically: ``cumulativeCost``
        accumulates cost **per metre**, so a cost band in seconds-per-
        metre yields arrival times in seconds. Verified by doubling a
        uniform spread rate and confirming arrival times halved exactly
        — the feared factor-of-30 per-pixel interpretation is ruled out.

        Accuracy against the analytic answer, uniform 1 m/s at 44.2 deg
        N: 0.997 due east, 0.993 due north, 1.053 on the diagonal. The
        diagonal residual is grid-path overhead and is not worth
        correcting for; the directional bias that *was* worth fixing is
        described on :data:`GEODETIC_DISTANCE`.
    """
    import ee

    src = ignition
    if not hasattr(src, "bandNames"):
        # A geometry or feature collection: burn it into a raster.
        fc = (src if hasattr(src, "reduceToImage")
              else ee.FeatureCollection([ee.Feature(src)]))
        src = ee.Image().paint(fc, 1)
    src = ee.Image(src).gt(0).selfMask()

    ros = ee.Image(ros_m_s).max(min_ros_m_s)
    cost = ee.Image(1).divide(ros).rename("cost_s_per_m")

    arrival = cost.cumulativeCost(
        source=src, maxDistance=max_distance_m, geodeticDistance=geodetic)
    return arrival.rename("arrival_s")


def isochrones(arrival_s, *, n_frames: int = 100,
               step_seconds: Optional[float] = None,
               total_seconds: Optional[float] = None):
    """Turn one arrival-time surface into an animation-ready collection.

    This is the payoff of not iterating. Each frame is a *threshold of
    the same image*, so a hundred frames cost a hundred cheap comparisons
    rather than a hundred rounds of neighborhood growth.

    Args:
        arrival_s: Output of :func:`travel_time`.
        n_frames: Number of frames.
        step_seconds: Seconds per frame. Defaults to
            ``total_seconds / n_frames``.
        total_seconds: Burn period. Defaults to 24 hours.

    Returns:
        ``ee.ImageCollection`` of masked burned-extent frames, each with
        ``t_seconds`` and ``t_hours`` properties — ready for geeViz's
        existing timelapse machinery.
    """
    import ee

    total = float(total_seconds if total_seconds is not None else 24 * 3600)
    step = float(step_seconds if step_seconds is not None
                 else total / max(int(n_frames), 1))

    arr = ee.Image(arrival_s)
    frames = []
    for i in range(1, int(n_frames) + 1):
        t = step * i
        frames.append(
            arr.lte(t).selfMask().rename("burned")
            .set({"t_seconds": t, "t_hours": t / 3600.0, "frame": i})
        )
    return ee.ImageCollection(frames)


def spread_with_wind_blocks(fuels, terrain, blocks, ignition, *,
                            ros_fn=None,
                            max_distance_m: int = DEFAULT_MAX_DISTANCE_M):
    """Chained cost-distance spread across changing wind.

    Iterates *coarsely* -- one ``cumulativeCost`` per wind period rather
    than one per timestep. A five-day fire at six-hourly wind is about
    twenty calls, which Earth Engine handles comfortably, and it captures
    the wind **shifts** that drive large runs. Within a block the spread
    is still isotropic.

    Args:
        blocks: Sequence of dicts, each with ``wind_speed`` (mi/h),
            optionally ``moisture_1h``, and ``duration_s``.
        ros_fn: Callable ``(fuels, terrain, **block) -> ee.Image`` in
            m/s. Defaults to Rothermel via
            :mod:`~geeViz.fireLib.behavior`.

    Returns:
        ``ee.Image`` band ``burned`` — final perimeter after all blocks.
    """
    import ee

    from .behavior import rate_of_spread, ros_metric

    def _default_ros(f, t, **blk):
        return ros_metric(rate_of_spread(
            f, t,
            wind_speed_20ft=blk.get("wind_speed", 5.0),
            moisture_1h=blk.get("moisture_1h", 0.06),
        ))

    ros_fn = ros_fn or _default_ros

    perim = ignition
    if not hasattr(perim, "bandNames"):
        fc = (perim if hasattr(perim, "reduceToImage")
              else ee.FeatureCollection([ee.Feature(perim)]))
        perim = ee.Image().paint(fc, 1)
    # unmask(0) is load-bearing, not tidying. An image from ``paint`` is
    # MASKED everywhere except the painted geometry, and Earth Engine
    # intersects masks on a binary op — so ``perim.Or(grown)`` inherits
    # the ignition point's one-pixel mask and the union collapses back to
    # the ignition. Measured: ``grown`` covered 1,650 ha while the Or of
    # it returned 0.6 ha. A valid image, a plausible small number, and
    # completely wrong.
    perim = ee.Image(perim).gt(0).unmask(0)

    for blk in blocks:
        ros = ros_fn(fuels, terrain, **blk)
        arr = travel_time(ros, perim.selfMask(),
                          max_distance_m=max_distance_m)
        grown = arr.lte(float(blk.get("duration_s", 6 * 3600)))
        # Union: already-burned stays burned. Without this the perimeter
        # would be replaced rather than extended, and a block with slow
        # wind could shrink the fire.
        perim = perim.unmask(0).Or(grown.unmask(0))

    return perim.rename("burned")


def transmission_matrix(fuels, terrain, ignitions, units, *,
                        wind_speed_20ft=8.0,
                        burn_period_s: float = 24 * 3600,
                        scale: int = 30,
                        max_distance_m: int = DEFAULT_MAX_DISTANCE_M):
    """Which unit's ignitions burn which unit's land.

    Cross-boundary fire transmission, and it falls out of the same
    primitive nearly free. Every ignition is independent, so this maps
    onto Earth Engine cleanly where a timestep loop does not.

    Args:
        ignitions: ``ee.FeatureCollection`` of ignition points, each
            carrying the property named by ``source_prop``.
        units: ``ee.FeatureCollection`` of ownership or community
            polygons with a ``unit`` property.

    Returns:
        ``ee.FeatureCollection``, one feature per (ignition, unit) pair
        carrying burned area in hectares.
    """
    import ee

    from .behavior import rate_of_spread, ros_metric

    ros = ros_metric(rate_of_spread(
        fuels, terrain, wind_speed_20ft=wind_speed_20ft))

    def _one(feat):
        feat = ee.Feature(feat)
        arr = travel_time(ros, feat.geometry(),
                          max_distance_m=max_distance_m)
        burned = arr.lte(burn_period_s).selfMask()
        areas = (ee.Image.pixelArea().updateMask(burned)
                 .reduceRegions(collection=units,
                                reducer=ee.Reducer.sum(),
                                scale=scale))
        return areas.map(lambda u: ee.Feature(u).set({
            "ignition_id": feat.id(),
            "burned_ha": ee.Number(ee.Feature(u).get("sum")).divide(10000),
        }))

    return ee.FeatureCollection(ee.FeatureCollection(ignitions)
                                .map(_one)).flatten()


def calibrate_cost_units(ros_m_s, ignition, known_distance_m: float,
                         known_time_s: float, *, scale: int = 30):
    """Check whether arrival times come back in the units you expect.

    Runs :func:`travel_time` over a landscape of *uniform* spread rate,
    where the answer is known analytically: reaching a point ``d`` metres
    away at ``r`` m/s must take ``d / r`` seconds.

    Returns a dict with the expected and observed times and their ratio.
    **A ratio near the pixel size means cost is accumulating per pixel
    rather than per metre** — a factor-of-30 error at 30 m that leaves
    every number plausible and every number wrong. Run this once against
    a fire with known progression before publishing anything derived
    from arrival times.
    """
    import ee

    arr = travel_time(ros_m_s, ignition)
    pt = ee.Geometry(ignition).buffer(known_distance_m).bounds()
    observed = arr.reduceRegion(
        reducer=ee.Reducer.percentile([50]),
        geometry=pt, scale=scale, maxPixels=1e12, bestEffort=True,
    ).getInfo()

    obs = next((v for v in (observed or {}).values() if v is not None), None)
    ratio = (obs / known_time_s) if (obs and known_time_s) else None
    return {
        "expected_s": known_time_s,
        "observed_s": obs,
        "ratio": ratio,
        "interpretation": (
            "ratio ~1 => cost accumulates per metre (expected); "
            "ratio ~pixel-size => cost accumulates per pixel, so the "
            "cost band must be seconds-per-pixel instead"
        ),
    }
