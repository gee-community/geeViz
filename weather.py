"""Weather forecasts from ECMWF, GFS and WeatherNext, on one interface.

Four products, one vocabulary. :func:`getForecastData` is the entry
point; everything else renders or derives from what it returns.

Whichever model produced an image, three things are the same — and that
is what makes two models subtractable:

* ``system:time_start`` is the **valid** time (not the run time),
* the band is named for the variable (not for the product),
* the value is in the variable's :data:`CANONICAL_UNITS` unit, and the
  image carries a ``wx_units`` property saying so.

The models
==========

Measured against the live collections on 2026-09-14;
``test_model_table_matches_the_live_collections`` re-checks every number
here, so a provider that changes cadence fails a test rather than
quietly returning less than you asked for.

==================  ==========  =========  ========  =============  ==========  ======
model               resolution  archive    init      horizon        lead step   access
==================  ==========  =========  ========  =============  ==========  ======
``gfs``             0.25°       2015-04    every 6h  384h (16d)     1h → 3h     open
``euro``            0.25°       2024-11    every 6h  360h / 144h    3h → 6h     open
``weathernext``     0.1°        2026-01    every 1h  360h / 48h     1h          gated
``weathernext_st``  0.05°       2026-01    every 1h  360h / 48h     1h          gated
==================  ==========  =========  ========  =============  ==========  ======

* **resolution** — ``0.25°`` is about 27.8 km at the equator. Exact
  metres per model are in ``MODELS[key]["native_scale_m"]``.
* **archive** — the earliest image present. A floor, not a guarantee:
  these are near-real-time feeds and old data may be rolled off.
* **init** — how often a new run starts. All four initialize on the
  hour; GFS and ECMWF only at 00/06/12/18 UTC.
* **horizon** — how far one run reaches. Where two numbers are given the
  runs are NOT uniform; see below.
* **lead step** — spacing between successive images in a run. ``1h → 3h``
  means hourly out to lead 120, three-hourly after.

``weathernext`` is a 64-member ensemble published **pre-aggregated** as
``_mean`` and the percentiles ``_p10 _p25 _p50 _p75 _p90``; pick one with
``stat=``. The members themselves are not in the collection, so spread is
``p90 - p10`` rather than a reduction over members. ``weathernext_st``
(the 0.05° product) is station-head 2 m temperature and dewpoint only —
**no wind**.

Both WeatherNext products are **gated**, and the way that failure
presents is worth knowing before it costs you an afternoon. Earth Engine
reports a denied gated asset as::

    ImageCollection.load: ImageCollection asset
    'projects/gcp-public-data-weathernext/assets/weathernext_3_0_0_0p1deg'
    not found (does not exist or caller does not have access)

That reads as "wrong id", so the natural response is to go looking for
the right one — and the gated collections are not in the public STAC
catalog either, so ``search_datasets("weathernext")`` returns only the
v2 and deprecated products and appears to confirm it.

Access is granted **per principal**, not per project. The same asset can
load in the Code Editor (where the caller is you) and 404 from a
deployed service in the *same* GCP project (where the caller is that
service's runtime service account). If it works for you interactively
and not in a deployment, grant the runtime service account access rather
than hunting for a different asset id.

Pitfalls
========

**Runs within one collection do not all reach the same distance.**
WeatherNext interleaves two run types: the 00/06/12/18 UTC inits reach
360 hours, and the twenty interim hourly inits stop at 48. ECMWF does
the same thing less dramatically — 00 and 12 reach 360 hours, 06 and 18
stop at 144. So "the most recent run", the obvious choice for a forward
window, is usually one that cannot cover it: asking WeatherNext for two
days out returned twelve images at leads 37..48 and stopped a day and a
half short. :func:`getForecastData` picks the newest run that actually
reaches the end of the window instead. Only GFS is uniform.

**The time property TYPES differ, and Earth Engine filters do not
coerce.** Comparing an ISO string property against a number returns an
empty collection rather than raising, so getting it wrong reads as "no
data for that window" instead of as a bug.

======================  ========================  ======================
model                   run (init) time           valid time
======================  ========================  ======================
``euro``  ECMWF IFS     ``creation_time`` (ms)    ``forecast_time``
``gfs``   NOAA GFS0P25  ``creation_time`` (ms)    ``forecast_time``
``weathernext``  WN3    ``start_time`` (ISO)      ``end_time`` (ISO)
======================  ========================  ======================

Each model declares ``iso_times``, and
``test_declared_time_types_match_the_live_data`` checks every
declaration against the live collection.

**WeatherNext's ``system:time_start`` is the INIT time**, one value for
every image in a run. Anything selecting on it picks a run rather than a
moment, and a time lapse built on it collapses to a single frame.
:func:`getForecastData` restamps it to the valid time on output.

**WeatherNext's shortest lead is 1 hour**, not 0. GFS and ECMWF start at
0. Filtering ``forecast_hour == 0`` returns nothing.

**``wind_speed_10m_mean`` is NOT the magnitude of (``u_mean``,
``v_mean``).** It is the ensemble mean of speeds, while u and v are means
of components, where opposing members cancel — Jensen's inequality makes
mean-of-speeds the larger. Measured at Denver on the 2026-09-09T10:00Z
step: ``|(u_mean, v_mean)|`` = 0.9875 m/s against
``wind_speed_10m_mean`` = 1.3119, a 33% gap. A vector built from the
components and paired with the published mean speed is internally
inconsistent, so this module derives speed from the components only —
the arrow's direction and its length then describe the same wind.

**GFS's band list is not stable, and the difference is by AGE.** The
oldest images carry ``total_precipitation_surface``; recent ones carry
``precipitation_rate``. An audit that samples the head of the unfiltered
collection reports the names here as broken — they are correct for
recent data, which is what a forecast request asks for.

**ECMWF publishes no per-hour precipitation.** Its
``total_precipitation_sfc`` is a running total since the run started,
and identically zero at lead 0 — which is what a past window returns. It
is exposed as ``precipitation_accumulated``, a different quantity from
the ``precipitation`` the other models publish, and not comparable to it.

**Bicubic resampling overshoots a saturated field.** ``resample`` runs
before selection, so cloud cover measured -10.3 to 111.4 percent and
precipitation reached -1.09 mm/hr before :data:`PHYSICAL_RANGES` clamped
them. Pass ``resample=None`` for a categorical band, where interpolating
a class code invents classes that do not exist.

Terrain downscaling
===================

Four functions, all from Liston & Elder (2006) MicroMet, all doing the
same job: redistributing a coarse forecast WITHIN its own cells using
the terrain the forecast could not see. None of them adds information
about the atmosphere.

==============================  ==================================
function                        terrain term
==============================  ==================================
:func:`downscaleWind`           slope in the wind direction, and
                                curvature — needs a ``region``
:func:`downscaleTemperature`    lapse rate on height above the
                                cell mean
:func:`downscaleDewpoint`       the same, at a shallower rate
:func:`downscalePrecipitation`  orographic enhancement with height
==============================  ==================================

Only the wind one needs ``region``: its terms are normalized against the
strongest terrain in the domain, so the same mountain downscales
differently in a small box than in a continental one. The other three
depend only on how far a pixel sits above its own cell's mean elevation,
which is a local quantity.

That reference — the **cell mean**, not sea level — is the thing to get
right. A forecast's 2 m temperature is a value for its cell's mean
height, so measuring from zero gives every mountain a large, smooth,
entirely plausible cold bias.

Temperature and dewpoint have different lapse rates on purpose:
dewpoint falls more slowly with height, so relative humidity rises going
up. Downscaling temperature while leaving dewpoint alone manufactures a
mountain drier than the forecast ever said.

The precipitation form has a **pole**: its multiplier changes sign once
``chi * dz`` passes 1, around 3300 m of relief at the default. Real
terrain rarely reaches that within one 28 km cell — which is exactly why
the guard is easy to drop and hard to notice — and past it the raw
formula returns negative rain. Both the offset and the resulting ratio
are clamped.

**An empty window is not an empty collection.** It comes back as one
fully masked image carrying ``lead_hours = -1``, so downstream code
cannot die on ``.first()``. Check that property before reporting numbers.
"""

import datetime
import json
import math

import ee

from geeViz.fireLib.wind import wind_speed_direction
from geeViz.getImagesLib import fillEmptyCollections

__all__ = [
    "MODELS",
    "getForecastData",
    "windBands",
    "windImage",
    "windTiles",
    "addWindLayer",
    "addWindTimeLapse",
    "VARIABLES",
    "CANONICAL_UNITS",
    "publishes",
    "downscaleWind",
    "downscaleTemperature",
    "downscaleDewpoint",
    "downscalePrecipitation",
    "DEFAULT_LAPSE_RATE",
    "DEFAULT_DEWPOINT_LAPSE_RATE",
    "DEFAULT_PRECIP_CHI",
    "DEFAULT_DEM",
    "weatherLabURL",
    "WEATHERLAB_URL",
    "SPEED_UNITS",
    "DIRECTION_UNITS",
    "WIND_PALETTE",
    "PRECIP_PALETTE",
    "TEMPERATURE_PALETTE",
    "DEFAULT_SPEED_PALETTE",
    "DEFAULT_MAX_SPEED",
]


#: One entry per supported model. ``run_prop`` of ``None`` means the
#: collection carries no init time, so "the most recent run" is not a
#: question it can answer.
MODELS = {
    "euro": {
        "collection": "ECMWF/NRT_FORECAST/IFS/OPER",
        "uv_units": "m/s",
        "u_band": "u_component_of_wind_10m_sfc",
        "v_band": "v_component_of_wind_10m_sfc",
        "run_prop": "creation_time",
        "valid_prop": "forecast_time",
        "lead_prop": "forecast_hours",
        "iso_times": False,               # epoch millis
        # 0.25 deg, NOT the 0.4 this said for a long time. ECMWF's
        # open IFS feed is quarter-degree, same grid as GFS; the wrong
        # figure made every areaChart and reduceRegion that trusted it
        # sample ECMWF at 1.6x its actual cell.
        "native_scale_m": 27830,          # 0.25 deg
        "resolution_deg": 0.25,
        "archive_start": "2024-11-12",
        "init_interval_h": 6,             # 00/06/12/18 UTC
        # Mixed horizons: 00 and 12 reach 15 days, 06 and 18 stop at 6.
        "horizon_h": {"long": 360, "short": 144},
        "long_run_hours": [0, 12],
        "lead_step_h": [(0, 3), (144, 6)],
        "gated": False,
        "ensemble_stats": None,
        "label": "ECMWF IFS (near-real-time)",
    },
    "gfs": {
        "collection": "NOAA/GFS0P25",
        "uv_units": "m/s",
        "u_band": "u_component_of_wind_10m_above_ground",
        "v_band": "v_component_of_wind_10m_above_ground",
        "run_prop": "creation_time",
        "valid_prop": "forecast_time",
        "lead_prop": "forecast_hours",
        "iso_times": False,               # epoch millis
        "native_scale_m": 27830,          # 0.25 deg
        "resolution_deg": 0.25,
        "archive_start": "2015-04-01",
        "init_interval_h": 6,             # 00/06/12/18 UTC
        # The only model here whose every run has the same reach.
        "horizon_h": {"long": 384, "short": 384},
        "long_run_hours": [0, 6, 12, 18],
        "lead_step_h": [(0, 1), (120, 3)],
        "gated": False,
        "ensemble_stats": None,
        "label": "NOAA GFS 0.25 deg",
    },
    "weathernext": {
        "collection": ("projects/gcp-public-data-weathernext/assets/"
                       "weathernext_3_0_0_0p1deg"),
        "uv_units": "m/s",
        "u_band": "u_component_of_wind_10m_mean",
        "v_band": "v_component_of_wind_10m_mean",
        # start_time is the INITIALIZATION; end_time is the valid time.
        "run_prop": "start_time",
        "valid_prop": "end_time",
        "lead_prop": "forecast_hour",
        "iso_times": True,                # ISO 8601 strings
        "native_scale_m": 11132,          # 0.1 deg
        "resolution_deg": 0.1,
        "archive_start": "2026-01-01",
        "init_interval_h": 1,             # every hour
        # Two interleaved run types in ONE collection: the 6-hourly
        # synoptic inits reach 15 days, the 20 interim hourly inits stop
        # at 2. So "the most recent run" usually cannot cover a forward
        # window -- see _newest_run_reaching.
        "horizon_h": {"long": 360, "short": 48},
        "long_run_hours": [0, 6, 12, 18],
        "lead_step_h": [(0, 1)],
        "gated": True,
        "ensemble_stats": ["mean", "p10", "p25", "p50", "p75", "p90"],
        "label": "WeatherNext 3 (0.1 deg, ensemble mean)",
    },
    "weathernext_stations": {
        "collection": ("projects/gcp-public-data-weathernext/assets/"
                       "weathernext_3_0_0_0p05deg"),
        # The 0.05 deg product is station-head 2 m temperature and
        # dewpoint only -- no wind. Reachable through
        # getForecastData(variable='temperature_2m'); asking it for
        # wind names the models that have it rather than failing
        # obscurely on a missing band.
        "u_band": None,
        "v_band": None,
        "run_prop": "start_time",
        "valid_prop": "end_time",
        "lead_prop": "forecast_hour",
        "iso_times": True,                # ISO 8601 strings
        "native_scale_m": 5566,           # 0.05 deg
        "resolution_deg": 0.05,
        "archive_start": "2026-01-01",
        "init_interval_h": 1,
        "horizon_h": {"long": 360, "short": 48},
        "long_run_hours": [0, 6, 12, 18],
        "lead_step_h": [(0, 1)],
        "gated": True,
        "ensemble_stats": ["mean", "p10", "p25", "p50", "p75", "p90"],
        "label": "WeatherNext 3 stations (0.05 deg)",
    },
}

#: Earth Engine aborts ``sample()`` once it accumulates more than ~5000
#: elements ("Collection query aborted after accumulating over 5000
#: elements"), and it does so DURING accumulation — so a trailing
#: ``.limit()`` cannot save you, and the error surfaces at ``getInfo()``
#: rather than near the call that caused it. Every point budget here is
#: clamped below that ceiling.
MAX_SAMPLE_POINTS = 4500

#: Multiplier from metres/second.
#:
#: ``kt`` is here because it is what wind is actually reported in
#: outside of research: METAR and TAF, NWS marine forecasts, every
#: aviation product, and windy.com's own default. A knot is one nautical
#: mile per hour and a nautical mile is defined as exactly 1852 m, so
#: the multiplier is exactly 3600/1852 -- not an approximation anyone
#: should retype.
SPEED_UNITS = {
    "m/s": 1.0,
    "km/hr": 3.6,
    "mi/hr": 2.236936292054402,
    "kt": 3600.0 / 1852.0,
}

#: Multiplier from degrees.
DIRECTION_UNITS = {
    "degrees": 1.0,
    "radians": math.pi / 180.0,
}


def _ms(d):
    """Epoch milliseconds from anything date-like, without a round trip.

    The past/future/spanning branch in :func:`getForecastData` is a
    CLIENT-side decision, so this value has to exist in Python. Parsing
    it here rather than asking Earth Engine keeps the whole function at
    zero round trips before it builds its graph -- ``ee.Date(s).millis()
    .getInfo()`` was a fifth of a second each, three times per call, for
    arithmetic ``datetime`` does for free.

    ``ee.Date`` is the one input form that still costs a fetch, because
    its value genuinely lives on the server. Pass a string, a
    ``datetime`` or epoch millis to avoid it.
    """
    if isinstance(d, (int, float)):
        return int(d)
    if isinstance(d, ee.Date):
        return int(d.millis().getInfo())     # the only unavoidable fetch
    if isinstance(d, datetime.datetime):
        if d.tzinfo is None:
            d = d.replace(tzinfo=datetime.timezone.utc)
        return int(d.timestamp() * 1000)
    if isinstance(d, datetime.date):
        d = datetime.datetime(d.year, d.month, d.day,
                              tzinfo=datetime.timezone.utc)
        return int(d.timestamp() * 1000)
    return int(_parse_iso(str(d)).timestamp() * 1000)


def _parse_iso(text):
    """``YYYY-MM-DD`` or any ISO 8601 instant, as an aware datetime.

    ``fromisoformat`` before 3.11 rejects a trailing ``Z``, which is the
    form every one of these collections publishes, so it is translated
    rather than relied upon.
    """
    t = text.strip().replace("/", "-")
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    try:
        out = datetime.datetime.fromisoformat(t)
    except ValueError:
        raise ValueError(
            f"cannot read {text!r} as a date — use 'YYYY-MM-DD', an ISO "
            f"8601 instant, a datetime, or epoch milliseconds")
    if out.tzinfo is None:
        out = out.replace(tzinfo=datetime.timezone.utc)
    return out


def _fmt_time(ms, iso):
    """A window bound in whatever type the collection's property uses.

    Earth Engine filters do not coerce: comparing an ISO string property
    against a number returns an EMPTY collection rather than raising, so
    a bound of the wrong type reads as "no data for that window" instead
    of as a bug.
    """
    if not iso:
        return ms
    return datetime.datetime.fromtimestamp(
        ms / 1000, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _model(model):
    key = (model or "").strip().lower()
    if key not in MODELS:
        raise ValueError(
            f"unknown model {model!r} — choose one of "
            f"{sorted(MODELS)}")
    return key, MODELS[key]


def _min_lead(collection, lead_p):
    """The shortest lead present in ``collection``, as an ``ee.Number``.

    Server-side and un-cached, by design. "Analysis" means lead 0 for
    GFS and ECMWF, but WeatherNext's ``forecast_hour`` runs 1..360 and
    never reaches 0 -- so hard-coding 0 hands back an empty collection
    for it, which reads as "no data" rather than as a wrong constant.

    Reduced over the ALREADY-WINDOWED collection rather than over the
    whole archive: the window bounds the scan, so there is nothing to
    cache and nothing expensive to avoid. The value stays an
    ``ee.Number`` and goes straight into ``ee.Filter.eq``, which accepts
    computed values -- one graph, no round trip.

    ``reduceColumns`` returns null for an empty collection rather than
    raising, so the ``If`` gives an empty window a harmless 0 instead of
    a filter against null.
    """
    lead = collection.reduceColumns(ee.Reducer.min(), [lead_p]).get("min")
    return ee.Number(ee.Algorithms.If(lead, lead, 0))


CANONICAL_UNITS = {
    "u": "m/s",
    "v": "m/s",
    "temperature_2m": "C",
    "dewpoint_2m": "C",
    "sea_surface_temperature": "C",
    "relative_humidity_2m": "%",
    # NOT a percent. Specific humidity is a mass fraction, and the
    # meteorological convention for it is g/kg -- writing 0.66% where
    # every textbook says 6.6 g/kg is a unit that is technically correct
    # and universally misread.
    "specific_humidity_2m": "g/kg",
    "precipitation": "mm/hr",
    "precipitation_accumulated": "mm",
    "total_cloud_cover": "%",
    "mean_sea_level_pressure": "hPa",
    "wind_speed_10m": "m/s",
}
"""The unit every variable comes back in, whichever model produced it.

The products disagree: WeatherNext publishes Kelvin where GFS and ECMWF
publish Celsius, cloud cover is a fraction in one and a percent in
another, pressure is Pascals everywhere and hectopascals nowhere. A
chart of two models with one of them unconverted does not look like a
unit bug -- it looks like one model blowing up.
"""


PHYSICAL_RANGES = {
    "relative_humidity_2m": (0.0, 100.0),
    "total_cloud_cover": (0.0, 100.0),
    "precipitation": (0.0, None),
    "precipitation_accumulated": (0.0, None),
    "specific_humidity_2m": (0.0, None),
    "wind_speed_10m": (0.0, None),
}
"""Bounds a variable cannot physically leave, in its canonical unit.

Needed because ``resample`` runs before selection and bicubic OVERSHOOTS
at a saturated edge -- measured over CONUS on one GFS image: cloud cover
-10.3 to 111.4 percent, relative humidity to 101.6, and precipitation
to **-1.09 mm/hr**. Negative rain is not a rounding artifact anyone
should have to notice downstream; it breaks masks, area sums and
palettes quietly, and it looks like data.

Temperature, dewpoint, pressure and the wind components are left alone:
they are bounded too, in principle, but never within a hundred units of
it, so a clamp could only ever hide a real problem.
"""


# (from, to) -> (scale, offset), applied as value * scale + offset.
#
# A pair that is not in here RAISES rather than passing the value
# through. That is the point: a new variable whose unit nobody thought
# about fails at the call instead of rendering plausible, finite, wrong
# numbers on a map.
_CONVERSIONS = {
    ("C", "C"): (1.0, 0.0),
    ("K", "C"): (1.0, -273.15),
    ("%", "%"): (1.0, 0.0),
    ("fraction", "%"): (100.0, 0.0),
    ("kg/kg", "g/kg"): (1000.0, 0.0),
    # An instantaneous rate: kg/m^2/s is mm/s of depth, so x3600 is
    # mm/hr. Numerically the same quantity as an hourly accumulation.
    ("kg/m^2/s", "mm/hr"): (3600.0, 0.0),
    # A one-hour accumulation in metres -- depth in the hour ending at
    # the valid time, which IS mm/hr.
    ("m/1hr", "mm/hr"): (1000.0, 0.0),
    ("m", "mm"): (1000.0, 0.0),
    ("Pa", "hPa"): (0.01, 0.0),
    ("m/s", "m/s"): (1.0, 0.0),
}


def _conversion(frm, to):
    """``(scale, offset)`` to get from ``frm`` to ``to``, or raise."""
    try:
        return _CONVERSIONS[(frm, to)]
    except KeyError:
        raise ValueError(
            f"no conversion from {frm!r} to {to!r}. Add it to "
            f"_CONVERSIONS — a missing pair raises rather than silently "
            f"passing the raw value through as if it were converted.")


def _apply_units(img, conversions):
    """Rescale each band to its canonical unit, in place, by name."""
    for band, (scale, offset) in conversions.items():
        if scale == 1.0 and offset == 0.0:
            continue
        img = img.addBands(
            img.select(band).multiply(scale).add(offset).rename(band),
            None, True)
    return img


def _clamp_physical(img, names):
    """Hold each band inside :data:`PHYSICAL_RANGES`."""
    for name in names:
        rng = PHYSICAL_RANGES.get(name)
        if rng is None:
            continue
        lo, hi = rng
        band = img.select(name)
        band = band.max(lo) if hi is None else band.clamp(lo, hi)
        img = img.addBands(band.rename(name), None, True)
    return img


def publishes(variable, model):
    """Does ``model`` publish ``variable``?

    Availability is "the table holds a ``(band, unit)`` pair", NOT
    truthiness -- an entry may instead be a string explaining why the
    model's version of the quantity is not usable, and a non-empty
    string is truthy.
    """
    entry = VARIABLES.get(variable)
    if entry is None:
        return False
    return isinstance(entry.get(_model(model)[0]), tuple)


def _resolve_bands(key, spec, variable, stat, start_ms=None):
    """Which bands to select, what to rename them, which are Kelvin.

    ``variable`` is one of:

    * ``"wind"`` (default) -- the u/v components, renamed ``u``/``v``.
      What ``addWindLayer`` and ``downscaleWind`` expect.
    * a :data:`VARIABLES` key, or a list of them -- selected and renamed
      to the key, so ``temperature_2m`` means the same band name across
      three products that spell it three ways.
    * ``None`` -- every band the product publishes, untouched. The
      escape hatch for the 100-odd WeatherNext bands this table does not
      name.

    Returns ``(selectors, names, conversions)``, where ``conversions``
    maps an output band name to the ``(scale, offset)`` that puts it in
    its :data:`CANONICAL_UNITS` unit. ``selectors`` of ``None`` means
    "take the image as published" -- the raw escape hatch, which is
    also the one path that does NOT normalize units, because there is no
    table entry saying what the raw bands are in.
    """
    if variable is None:
        return None, [], {}

    if variable == "wind":
        if not spec.get("u_band"):
            raise ValueError(
                f"{key!r} publishes no wind components — it is a "
                f"{spec['label']}. Use 'gfs', 'euro' or 'weathernext', "
                f"or ask for a variable it does publish: "
                f"{_published(key)}.")
        u_b, v_b = spec["u_band"], spec["v_band"]
        if key.startswith("weathernext") and stat != "mean":
            u_b = u_b.replace("_mean", f"_{stat}")
            v_b = v_b.replace("_mean", f"_{stat}")
        # Every product happens to publish components in m/s today, but
        # "happens to" is not a guarantee -- downscaleWind and the
        # particle tiles both hard-code m/s thresholds, so the unit is
        # read from the model and converted like any other.
        uv = spec.get("uv_units", "m/s")
        conv = {"u": _conversion(uv, CANONICAL_UNITS["u"]),
                "v": _conversion(uv, CANONICAL_UNITS["v"])}
        return [u_b, v_b], ["u", "v"], conv

    wanted = variable if isinstance(variable, (list, tuple)) else [variable]
    sel, names, conv = [], [], {}
    for v in wanted:
        entry = VARIABLES.get(v)
        if entry is None:
            # "wind" is valid, but only on its own -- it returns u/v
            # rather than a named variable, so it cannot share a list.
            # Saying just "choose from ..., 'wind'" here sends people
            # straight back to the thing that did not work.
            if v == "wind":
                raise ValueError(
                    "'wind' cannot be combined with other variables — it "
                    "returns the u/v components, not a named band. Ask for "
                    "it in its own call: getForecastData(..., "
                    "variable='wind').")
            raise ValueError(
                f"unknown variable {v!r} — choose from {sorted(VARIABLES)}, "
                f"'wind', or None for every band as published")
        band = entry.get(key)
        if not isinstance(band, tuple):
            have = [m for m in MODELS if isinstance(entry.get(m), tuple)]
            # A string in the table is a REASON, not a band name: the
            # model publishes something of that name which cannot be
            # made comparable to the others. Saying so beats "does not
            # publish", which is not true and sends people looking for a
            # band that is right there.
            why = f" {band}" if isinstance(band, str) else ""
            raise ValueError(
                f"{key!r} does not publish {v!r} in a usable form.{why} "
                f"Models that do: {have or 'none'}.")
        name, units = band

        # Does this band exist for the window being asked for?
        #
        # Checked against the START of the window, not the end: the
        # collection is mapped band-by-band, so ONE image without the
        # band fails the whole request. A window that straddles the
        # boundary is just as broken as one entirely before it, and
        # saying so here beats an Earth Engine error raised from inside
        # a map() over an image the caller never named.
        gate = BAND_AVAILABLE_FROM.get((v, key))
        if gate is not None and start_ms is not None:
            since, advice = gate
            if start_ms < _ms(since):
                raise ValueError(
                    f"{key!r} has no {name!r} band that far back: it "
                    f"enters the record on {since}, and the window asked "
                    f"for starts before that. {advice}")

        if key.startswith("weathernext") and stat != "mean":
            name = name.replace("_mean", f"_{stat}")
        sel.append(name)
        names.append(v)
        conv[v] = _conversion(units, CANONICAL_UNITS[v])
    return sel, names, conv


def _published(key):
    """The variable keys a model actually has, for an error message."""
    out = [v for v, e in VARIABLES.items() if isinstance(e.get(key), tuple)]
    if MODELS[key].get("u_band"):
        out.append("wind")
    return sorted(out)


def getForecastData(startDate, endDate, model="gfs", variable="wind",
                    now=None, lookback_days=4, stat="mean",
                    normalize_units=True, resample="bicubic"):
    """Forecast images for ``[startDate, endDate]``, per model, one interface.

    Every model marks run and valid time differently -- GFS and ECMWF use
    ``creation_time`` / ``forecast_time`` in epoch millis, WeatherNext
    uses ``start_time`` / ``end_time`` as ISO 8601 strings. Reconciling
    that is what this function is for.

    It is not a wind function. ``variable`` selects what comes back:
    ``"wind"`` (the default, u/v components), any :data:`VARIABLES` key
    or list of them, or ``None`` for every band as published. A
    :data:`VARIABLES` key is renamed to the key and unit-normalised, so
    ``temperature_2m`` means the same band name and the same units
    across three products that spell it three ways and two of which
    publish Kelvin.

    What it returns depends on where the window sits relative to now,
    because "the forecast for last Tuesday" and "the forecast for next
    Tuesday" are different questions:

    * **Entirely past** -- the SHORTEST-LEAD image from every run
      initialized inside the window. That is each model's best estimate
      of what the atmosphere actually did, stitched across runs: a fresh
      analysis every cycle rather than one old run projecting forward.
    * **Entirely future** -- one run, the most recent, filtered to the
      window. Mixing runs inside a forward window makes the field jump
      where two runs disagree.
    * **Spanning now** -- both, split at the most recent run's
      initialization: shortest-lead analyses up to that moment
      (exclusive), then that run's forecast from there on.

    "Shortest lead" rather than literally lead 0 because WeatherNext's
    ``forecast_hour`` starts at 1; GFS and ECMWF start at 0. The value is
    read from the collection, not hard-coded.

    Args:
        startDate, endDate: ``str``, ``datetime``, ``ee.Date`` or epoch ms.
        model: ``"euro"``, ``"gfs"``, ``"weathernext"`` or
            ``"weathernext_stations"`` (the 0.05 deg product, which is
            station-head temperature and dewpoint only -- no wind).
        variable: ``"wind"`` (default), a :data:`VARIABLES` key, a list
            of them, or ``None`` for every band untouched. Asking a
            model for something it does not publish raises, and names
            the models that do -- better than a band-not-found twenty
            lines later, or an empty layer that reads as "no weather".
        normalize_units: put every band in its
            :data:`CANONICAL_UNITS` unit -- u/v in m/s, temperature and
            dewpoint in C, precipitation in mm/hr, humidity in percent,
            pressure in hPa. Pass ``False`` for the product's own units,
            which is rarely what you want and never what a chart across
            two models wants. Has no effect when ``variable`` is
            ``None``: nothing says what those bands are in.
        resample: applied BEFORE selection, so a layer drawn straight
            from this collection is smooth at map zooms rather than
            blocky -- these products are 11-28 km, which is several
            screen-fulls per cell once you are past zoom 8. Pass
            ``None`` to keep nearest-neighbour, which is what a
            categorical band wants; interpolating a class code produces
            classes that do not exist.
        now: Override the clock. Testing seam.
        lookback_days: How far back to hunt for a run. Bounds the scan --
            an unbounded search for the newest run walks every image ever
            published and times out.
        stat: WeatherNext only -- ``"mean"`` (default) or a percentile
            (``"p10"`` ... ``"p90"``).

    Returns:
        ``ee.ImageCollection`` carrying ``valid_time`` (ms),
        ``lead_hours``, ``wx_model``, a ``system:time_start`` set to the
        VALID time, and ``wx_units`` mapping each band to its unit.
        Bands are ``u``/``v`` for ``"wind"``, the variable keys for a
        variable request, or the product's own names when ``variable``
        is ``None``.

        Three things are therefore the same no matter which model
        produced the image: **the time stamp** means the valid time,
        **the band name** is the variable key, and **the unit** is the
        one in :data:`CANONICAL_UNITS`. That is what makes two models
        subtractable.
    """
    key, spec = _model(model)

    # The window is parsed FIRST now, because resolving a band depends
    # on it: some bands enter a collection partway through its record
    # (see BAND_AVAILABLE_FROM) and whether one exists is a question
    # about the dates. Still just parsing and comparison -- nothing here
    # touches the network, and the run search below is unchanged.
    t0, t1 = _ms(startDate), _ms(endDate)
    if t1 < t0:
        raise ValueError(f"endDate precedes startDate ({startDate} .. {endDate})")

    # What to select, and what to call it. Resolved before anything
    # touches the clock, so an unavailable variable fails immediately
    # rather than after the run search.
    sel, names, conv = _resolve_bands(key, spec, variable, stat, start_ms=t0)
    # Stamped on every image so a reader does not have to know the table.
    units_prop = ({n: CANONICAL_UNITS[n] for n in names}
                  if (names and normalize_units) else {})
    tn = _ms(now) if now is not None else int(
        datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)

    ic = ee.ImageCollection(spec["collection"])
    valid_p, lead_p, run_p = spec["valid_prop"], spec["lead_prop"], spec["run_prop"]
    # Both time properties of a given product share one representation,
    # so one flag covers the run bound and the valid bound alike.
    iso = run_iso = spec["iso_times"]

    def _v(ms):
        return _fmt_time(ms, iso)

    def _r(ms):
        return _fmt_time(ms, run_iso)

    def _norm(img):
        # Restamp system:time_start to the VALID time. WeatherNext
        # otherwise carries the init time there -- one value for a whole
        # run -- and any time lapse collapses to a single frame.
        vt = ee.Date(img.get(valid_p)).millis()
        if resample:
            img = img.resample(resample)
        out = img if sel is None else img.select(sel, names)
        if normalize_units:
            out = _apply_units(out, conv)
            # After conversion, so the bounds are in canonical units.
            out = _clamp_physical(out, names)
        # system:time_start is the VALID time, not the run time.
        # WeatherNext stamps the initialization there natively -- one
        # value for a whole run -- so any time lapse or chart over a raw
        # collection collapses to a single point.
        return (out.set({"valid_time": vt,
                         "lead_hours": img.get(lead_p),
                         "wx_model": key,
                         "wx_units": units_prop,
                         "system:time_start": vt}))

    def _analyses(lo_ms, hi_ms):
        """Shortest-lead image from every run initialized in the window.

        Everything published in the window is pulled first, then reduced
        to its own minimum lead. The window is the bound, so the reduce
        is cheap and the answer describes the data actually in hand
        rather than a constant read off some other slice of the archive.
        """
        win = ic.filter(ee.Filter.And(ee.Filter.gte(run_p, _r(lo_ms)),
                                      ee.Filter.lte(run_p, _r(hi_ms))))
        return win.filter(ee.Filter.eq(lead_p, _min_lead(win, lead_p)))

    def _from_run(run_val, lo_ms, hi_ms):
        return (ic.filter(ee.Filter.eq(run_p, run_val))
                  .filter(ee.Filter.And(ee.Filter.gte(valid_p, _v(lo_ms)),
                                        ee.Filter.lte(valid_p, _v(hi_ms)))))

    def _out(coll):
        """Normalize, order, and never hand back an empty collection.

        An empty result is not merely unhelpful — it is a crash waiting
        a few lines later, where ``addWindLayer`` reads band names off
        ``.first()`` and gets ``Image.bandNames: Parameter 'image' is
        required``. ``fillEmptyCollections`` substitutes one fully
        masked u/v image instead, which renders as nothing and queries
        as nothing, and carries ``lead_hours = -1`` so a caller can tell
        "no data" from "calm".
        """
        # The sentinel has to carry the SAME bands the real images do,
        # or a caller that selects by name dies on the empty case.
        dummy_names = names if names else ["forecast"]
        dummy = (ee.Image([0] * len(dummy_names)).rename(dummy_names).float()
                   .set({"valid_time": t0, "lead_hours": -1,
                         "wx_model": key, "wx_units": units_prop,
                         "system:time_start": t0}))
        return fillEmptyCollections(
            coll.map(_norm).sort("valid_time"), dummy)

    look_ms = int(lookback_days * 86400 * 1000)

    def _latest_run_at_or_before(ref_ms):
        def _win(span):
            return ic.filter(ee.Filter.And(
                ee.Filter.gt(run_p, _r(ref_ms - span)),
                ee.Filter.lte(run_p, _r(ref_ms))))
        near, wide = _win(look_ms), _win(look_ms * 10)
        return ee.Algorithms.If(near.size().gt(0),
                                near.aggregate_max(run_p),
                                wide.aggregate_max(run_p))

    # ---- entirely past: analyses only ---------------------------------
    if t1 <= tn:
        return _out(_analyses(t0, t1))

    def _newest_run_reaching(end_ms):
        """Newest run that actually has an image valid near ``end_ms``.

        Not simply the newest run. WeatherNext interleaves 6-hourly inits
        reaching 360 h with interim hourly inits that stop at 48 h, so
        the most recent initialization is frequently one that cannot
        cover a forward window at all: asking for two days out returned
        twelve images at leads 37..48 and stopped a day and a half short.

        Choosing among the runs that reach the far end keeps the "one
        run" property while actually spanning what was asked for. It is
        a no-op where every run has the same horizon, i.e. GFS and ECMWF.
        """
        # At or PAST the end, not merely near it. A window ending
        # 09-13 was previously served by an hourly init whose 48-hour
        # reach stopped at 09-12 11:00 — that image fell inside a
        # "within 24 hours of the end" band, so the run looked like it
        # covered the request and the result silently stopped a day
        # short. Requiring an image at or beyond the end makes coverage
        # a fact rather than an approximation.
        span = 24 * 3600 * 1000
        reaching = ic.filter(ee.Filter.And(
            ee.Filter.gte(valid_p, _v(end_ms)),
            ee.Filter.lte(valid_p, _v(end_ms + span))))
        return ee.Algorithms.If(reaching.size().gt(0),
                                reaching.aggregate_max(run_p),
                                _latest_run_at_or_before(tn))

    latest_run = _newest_run_reaching(t1)

    # ---- entirely future: one run ------------------------------------
    if t0 >= tn:
        return _out(_from_run(latest_run, t0, t1))

    # ---- spanning: analyses up to the run, then the run --------------
    #
    # The seam is the most recent initialization, not "now". Before it,
    # a fresh analysis exists for every cycle and is the better record;
    # from it onward, that single run is the forecast. Splitting at now
    # instead would ask the latest run for hours it did not produce, or
    # discard analyses newer than the split.
    run_ms = ee.Date(latest_run).millis()
    # The seam, expressed in whatever type the valid-time property uses.
    # ``iso`` is known here, so this is a plain branch rather than an
    # ee.Algorithms.If — one less node, and it reads as what it is.
    seam = (ee.Date(run_ms).format("YYYY-MM-dd'T'HH:mm:ss'Z'")
            if iso else run_ms)
    before = _analyses(t0, t1).filter(ee.Filter.lt(valid_p, seam))
    after = ic.filter(ee.Filter.eq(run_p, latest_run)).filter(
        ee.Filter.And(ee.Filter.gte(valid_p, seam),
                      ee.Filter.lte(valid_p, _v(t1))))
    return _out(before.merge(after))


def _uv_image(image, viz):
    """The u/v pair, selected and resampled, ready to render.

    Both callers need exactly this and had identical copies of it. The
    resampling is the part worth keeping in one place: the CLIENT does
    no interpolation of its own, so whatever smoothing the field gets,
    it gets here. Dropping it makes the particles advect across a
    visibly blocky field -- measured on a GFS tile at zoom 10, the
    unresampled version runs to 176 identical pixels in a row against 45
    for the bicubic one.

    Bicubic rather than bilinear because it costs nothing at this point:
    it is evaluated once per tile, server-side, and cached in the PNG.
    """
    viz = viz or {}
    u_b, v_b = _uv(viz)
    img = ee.Image(image).select([u_b, v_b], ["u", "v"])
    rs = viz.get("resample", "bicubic")
    if rs:
        img = img.resample(rs)
    return img


#: The u/v stretch baked into the particle tiles, in m/s.
#:
#: HARD-CODED on purpose, and identical in ``wind-particles.js``. The
#: tiles are 8-bit PNGs: u is encoded in red, v in green, each linearly
#: mapped from this range onto 0..255. The client can only invert that
#: if it knows the exact range, and a range that travelled as data could
#: drift out of sync with the encoder -- silently, because wrong-but-
#: plausible winds look like weather rather than like a bug.
#:
#: +/-40 m/s (about 145 km/h) covers everything short of a major
#: cyclone's core, at a quantization of 80/255 = 0.31 m/s per step. That
#: is far finer than any forecast's real precision, and advection is
#: insensitive to it. Values beyond the range clamp rather than wrap.
WIND_TILE_MIN_MS = -40.0
WIND_TILE_MAX_MS = 40.0

#: Sensible full-scale wind for the speed raster, per unit. A stretch
#: that does not follow the unit is the fastest way to a map that is
#: entirely dark blue (0..15 read as km/h) or entirely red (0..54 read
#: as m/s).
#:
#: Each is the same physical wind (~15 m/s) rounded to a clean number in
#: its own unit; ``test_default_stretch_follows_the_unit`` holds them
#: within 2 m/s of each other, so a unit added here without a default --
#: or with a careless one -- fails rather than painting a flat map.
#:
#: Note this is roughly HALF windy.com's default full scale of 60 kt.
#: The palette is shared with them (:data:`WIND_PALETTE`) but the
#: stretch is not, so the same field reads about twice as windy here:
#: an 8.7 m/s wind sits 58% up this ramp and 28% up windy's. That is a
#: deliberate choice -- it spends more of the ramp on the speeds most
#: maps actually contain -- but pass ``viz["max"]`` of 30 m/s, 111 km/h,
#: 69 mi/h or 60 kt when the point is to compare the two side by side.
DEFAULT_MAX_SPEED = {"m/s": 15.0, "km/hr": 54.0, "mi/hr": 34.0, "kt": 30.0}

def _hex(rgb):
    """``(r, g, b)`` 0-255 to ``#rrggbb``.

    Same result as ``geeViz.geeView.RGB_to_hex``, done locally so this
    module does not import the viewer -- ``geeView`` imports THIS module
    to serve ``Map.addWindLayer``, and a top-level import back would
    make the cycle depend on which one the user happens to import first.
    """
    return "#%02x%02x%02x" % tuple(int(round(c)) for c in rgb)


#: Wind speed, read off windy.com's own legend so a geeViz wind map and
#: a windy map of the same hour are comparable at a glance.
#:
#: Calibrated against windy's scale, whose labelled stops are 0, 3, 5,
#: 10, 15, 20 and 30 m/s -- so the palette is designed for a 0..30 m/s
#: stretch. :data:`DEFAULT_MAX_SPEED` is deliberately tighter than that
#: (15 m/s), which spends more of the ramp on the speeds most maps
#: actually contain; pass ``viz["max"]`` to widen it back out.
WIND_PALETTE = tuple(_hex(c) for c in [
    (61, 110, 163), (74, 148, 170), (74, 146, 148), (77, 142, 124),
    (76, 164, 76), (103, 164, 54), (162, 135, 64), (162, 109, 92),
    (141, 63, 92), (151, 75, 145), (95, 100, 160), (91, 136, 161),
    (91, 136, 161)])

#: Precipitation, same source. Blue through cyan and green to orange
#: and deep red.
PRECIP_PALETTE = tuple(_hex(c) for c in [
    (63, 123, 234), (41, 188, 237), (37, 210, 209), (41, 230, 176),
    (193, 238, 52), (247, 168, 43), (211, 49, 4), (138, 11, 3),
    (138, 11, 3)])

#: Temperature, same source. Violet and pale blue through green to
#: amber and dark red.
TEMPERATURE_PALETTE = tuple(_hex(c) for c in [
    (149, 137, 212), (150, 209, 216), (128, 204, 197), (102, 179, 186),
    (95, 143, 197), (80, 140, 61), (122, 146, 28), (171, 161, 14),
    (223, 177, 6), (243, 150, 6), (236, 94, 21), (190, 65, 18),
    (138, 42, 10)])

#: What an unconfigured wind layer paints with.
DEFAULT_SPEED_PALETTE = WIND_PALETTE


def windBands(image, viz=None):
    """Resolve which two bands are the u/v (dx/dy) components.

    Args:
        image: ``ee.Image`` to read band names from. Costs one round
            trip, and only in the default case.
        viz: ``viz["bands"]`` may be a list or a comma-separated string.

    Mirrors ``Map.addLayer``: ``viz["bands"]`` may be a list or a
    comma-separated string. Absent, the FIRST TWO bands are used in
    order -- dx then dy.

    Two bands by position rather than a guess by name, because every
    product names them differently (``u_component_of_wind_10m_sfc`` vs
    ``..._above_ground`` vs ``..._mean``) and a name-sniffing heuristic
    that quietly picks the 100 m wind instead of the 10 m wind is worse
    than an explicit parameter.
    """
    b = _uv(viz)
    if b == [0, 1]:
        b = ee.Image(image).bandNames().slice(0, 2).getInfo()
    return [str(b[0]), str(b[1])]


def _rgb_of(color):
    """``#rgb`` / ``#rrggbb`` / ``rrggbb`` to an ``(r, g, b)`` triple.

    Only used to build the legend swatch. The CLIENT parses
    ``particleColor`` itself for drawing, so this is a second reader of
    the same value rather than the authority on it -- which is why it
    falls back to white rather than raising: a legend chip is not worth
    failing a map layer over.
    """
    c = str(color).strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    try:
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, IndexError):
        return (255, 255, 255)


def _particle_swatch(rgb, opacity, taper, head_boost, max_width,
                     palette=None, ramp_opacity=0.5, wide=False):
    """A CSS background that draws the particle itself, in miniature.

    The viewer renders a class legend entry as
    ``<span style='border:...;background:<value>'>``, and ``addColorHash``
    passes any value that is not a bare hex straight through. So a
    gradient reaches the swatch through the EXISTING legend path — no
    new rendering code, and the entry keeps the border and spacing every
    other legend row has.

    The stops come from the same numbers ``wind-particles.js`` draws
    with, so the key cannot drift from the map: alpha along the trail is
    ``opacity * t**taper``, and the leading band is boosted to
    ``opacity * headBoost``, which is what makes the tip read as a
    highlight rather than merely the widest part.

Underneath it sits the layer's own SPEED RAMP, at low opacity. That
    is not decoration either -- it is the second half of what the layer
    shows. On the map the particles are always drawn over that ramp, so
    a swatch on a flat ground shows the comet in a context it never
    actually appears in, and a white comet on the legend's white ground
    shows nothing at all. Low opacity because the ramp here is a
    backdrop, not a reading: the speed raster has its own color-bar
    entry and that is the one to measure against.

    Args:
        rgb: the particle color, as an ``(r, g, b)`` triple.
        opacity, taper, head_boost, max_width: the same numbers
            ``wind-particles.js`` draws the trail with, so the key
            cannot drift from the map.
        palette: the speed ramp, as hex strings. Falls back to a flat
            dark chip when absent.
        ramp_opacity: alpha on that ramp, 0-1. 0.5 by default, chosen
            by rendering the alternatives: below about 0.4 the ramp
            stops reading as the ramp and a white comet -- the default
            color -- loses its contrast against it, while at 1.0 the
            swatch is indistinguishable from the speed layer's own
            color bar and invites being read as one.
    """
    r, g, b = rgb

    def _rgba(a):
        return f"rgba({r},{g},{b},{min(1.0, max(0.0, a)):.2f})"

    # Tail at 8% so the streak is inset from the border, head at 88%.
    stops = []
    for pct in (8, 30, 50, 70, 84):
        t = (pct - 8) / (88 - 8)
        stops.append(f"{_rgba(opacity * (t ** taper))} {pct}%")
    stops.insert(0, f"{_rgba(0)} 0%")
    stops.append(f"{_rgba(min(1.0, opacity * head_boost))} 88%")
    stops.append(f"{_rgba(0)} 92%")

    # The streak's thickness IS particleMaxWidth, floored at 2 so a
    # hairline default is still visible in a 12 px tall swatch.
    thick = max(2, int(round(max_width)))
    comet = (f"linear-gradient(90deg, {', '.join(stops)}) "
             f"center / 100% {thick}px no-repeat")

    # When this entry IS the color bar -- the grouped layer has only
    # one -- it needs a bar's proportions, not a chip's.
    #
    # The width rides through the same value slot as the background,
    # because that slot is the only thing this side controls: the
    # viewer writes `background:${value};` into the span's style, so a
    # value that closes with `; width: ...` contributes further
    # declarations to the same rule. Blunt, but it keeps the legend
    # entirely in the layer's own hands rather than requiring a
    # stylesheet change in a bundle shared with every other viewer.
    tail = "; width: 132px; height: 13px; vertical-align: middle" if wide else ""

    # Accept either shape. `speed_viz["palette"]` is a COMMA STRING --
    # that is what Earth Engine's viz wants -- while windSpeedPalette is
    # a list. Iterating the string yields single CHARACTERS, each of
    # which _rgb_of reads as an invalid hex and answers white for, so
    # the swatch came out blank with no error anywhere. Splitting first
    # makes the caller's choice stop mattering.
    if isinstance(palette, str):
        palette = palette.split(",")
    pal = [c for c in (palette or []) if str(c).strip()]
    if len(pal) < 2:
        return f"{comet}, #24303a{tail}"

    # The ramp, spread across the swatch in the same order the color
    # bar runs. Alpha is baked per stop rather than set on the element:
    # the comet has to stay at full strength, and one opacity on the
    # span would fade both.
    n = len(pal) - 1
    ramp = ", ".join(
        "rgba({},{},{},{:.2f}) {:.0f}%".format(
            *_rgb_of(c), ramp_opacity, i * 100.0 / n)
        for i, c in enumerate(pal))
    return f"{comet}, linear-gradient(90deg, {ramp}){tail}"



#: Environmental lapse rate, degrees C per METRE. Negative: air cools
#: with height.
#:
#: -6.5 C/km is the standard atmosphere's mean, and MicroMet uses
#: month- and latitude-varying values around it -- roughly -4 C/km in
#: mid-winter to -8 C/km in midsummer over the northern mid-latitudes,
#: because a shallow winter inversion flattens the profile and can even
#: reverse it. Pass ``lapse_rate`` to use a value for your season; the
#: default is the annual mean, which is the honest choice when the
#: month is not known.
DEFAULT_LAPSE_RATE = -0.0065

#: Dewpoint lapse rate, degrees C per metre.
#:
#: Shallower than the temperature lapse rate, so relative humidity
#: generally RISES with elevation -- which is why downscaling
#: temperature alone and keeping humidity fixed produces a drier
#: mountain than the forecast implies.
DEFAULT_DEWPOINT_LAPSE_RATE = -0.0020

#: Orographic precipitation adjustment factor, per metre.
#:
#: The coefficient in the Thornton et al. (1997) form MicroMet adopts.
#: MicroMet varies it by month, larger in winter when orographic
#: enhancement is strongest; values are of order 1e-4 per metre. This
#: default sits in that range and is deliberately conservative: over
#: 1000 m of relief it gives about a 1.6x enhancement, not a 5x one.
#: Pass your own for a specific season or range.
DEFAULT_PRECIP_CHI = 3.0e-4


def _cell_mean_elevation(dem, image, agg_scale=1000):
    """Mean DEM elevation over each of the forecast's own cells.

    This is the reference the correction is measured FROM, and getting
    it wrong is the classic way to break an elevation adjustment: the
    forecast's 2 m temperature is not a sea-level value, it is a value
    for that cell's mean height. Subtracting the fine elevation from
    zero instead of from the cell mean gives every mountain a 20 C
    error at 3000 m, uniformly, which reads as a plausible cold bias
    rather than as a bug.

    ``reduceResolution`` has a hard input-pixel limit, so the DEM is
    first put on an intermediate grid: 1 km into 28 km is 773 pixels,
    comfortably under it, where 30 m into 28 km would be 860,000 and
    simply fail. ``agg_scale`` is that intermediate grid and has nothing
    to do with the output resolution.
    """
    dem = ee.Image(dem).select(0)
    coarse = (dem.setDefaultProjection(dem.projection().atScale(agg_scale))
                 .reduceResolution(ee.Reducer.mean(), True, 65535)
                 .reproject(ee.Image(image).projection()))
    # Interpolated the SAME way the forecast itself is, and that is the
    # whole point rather than a refinement.
    #
    # reproject() leaves this piecewise CONSTANT on the forecast grid:
    # measured over Utah, the step between adjacent 500 m pixels was
    # 0.002 m almost everywhere and up to 986 m at a cell edge. But
    # getForecastData resamples the forecast BICUBIC, so the temperature
    # being corrected crosses those same edges smoothly. Subtracting a
    # blocky reference from a smooth field prints the forecast grid onto
    # the output -- a visible checkerboard, ~8 C between neighbouring
    # pixels at the default lapse rate, which reads as terrain nobody
    # can find on a map.
    #
    # With this, dz's roughness matches the DEM's (p99 266 m against the
    # DEM's 269 m), i.e. every remaining discontinuity is real terrain.
    return coarse.resample("bicubic")


def _elevation_delta(image, dem, scale, agg_scale=1000):
    """``(z_fine - z_coarse, dem)`` -- how far above its own cell mean
    each fine pixel sits."""
    dem = ee.Image(DEFAULT_DEM if dem is None else dem).select(0)
    dem = dem.resample("bicubic")
    coarse = _cell_mean_elevation(dem, image, agg_scale)
    return dem.subtract(coarse), dem


def _finish(out, image, dem, scale):
    """Stamp the fine projection and carry the forecast's identity.

    Without ``setDefaultProjection`` the result inherits the WIND
    field's 28 km projection, so a map tile computes every terrain term
    at 28 km and upsamples it -- real in the arithmetic, invisible on
    the map. ``setDefaultProjection`` rather than ``reproject`` so a
    zoomed-out view is not forced to compute at ``scale`` everywhere.
    """
    out = out.setDefaultProjection(dem.projection().atScale(scale))
    return ee.Image(out.copyProperties(
        ee.Image(image),
        ["system:time_start", "valid_time", "lead_hours", "wx_model",
         "wx_units"]))


def downscaleTemperature(image, dem=None, scale=500, band=None,
                         lapse_rate=None, agg_scale=1000):
    """Sharpen a coarse temperature field with elevation, after MicroMet.

    The companion to :func:`downscaleWind`, from the same paper (Liston
    & Elder 2006) and with the same standing: it is the first-order
    terrain signal, not new information about the atmosphere.

    Temperature's terrain signal is much simpler than wind's, and much
    stronger. A 28 km GFS cell reports ONE temperature for its mean
    elevation; inside that cell a valley floor and a ridge 1500 m above
    it differ by about 10 C for no other reason than height. So::

        T_fine = T_coarse + lapse_rate * (z_fine - z_coarse)

    where ``z_coarse`` is the mean elevation of the forecast cell, not
    sea level.

    Unlike the wind adjustment this needs no ``region``: the correction
    depends only on how far a pixel sits above its own cell's mean, so
    there is nothing domain-relative to normalise against.

    **What it does not do.** Cold-air pooling, valley inversions and
    slope/aspect radiation are exactly where a single lapse rate is
    worst, and they are also when mountain temperature matters most --
    a clear winter night can invert the profile outright, making the
    valley colder than the ridge while this makes it warmer. A constant
    lapse rate has no way to express that.

    Args:
        image: ``ee.Image`` carrying a temperature band, as
            ``getForecastData(variable='temperature_2m')`` returns.
        dem: elevation ``ee.Image``; defaults to :data:`DEFAULT_DEM`.
        scale: metres for the output's default projection.
        band: which band to adjust. Defaults to the first, which is the
            only band when the image came from a single-variable
            request.
        lapse_rate: degrees C per metre, negative.
            :data:`DEFAULT_LAPSE_RATE` if not given.
        agg_scale: intermediate grid for computing the cell-mean
            elevation. Not the output resolution.

    Returns:
        ``ee.Image`` with the same band name, at ``scale``, carrying the
        input's time and model properties.
    """
    img = ee.Image(image)
    band = band or img.bandNames().get(0)
    lapse = DEFAULT_LAPSE_RATE if lapse_rate is None else lapse_rate
    dz, dem = _elevation_delta(img, dem, scale, agg_scale)
    out = img.select([band]).add(dz.multiply(lapse)).rename([band])
    return _finish(out, img, dem, scale)


def downscaleDewpoint(image, dem=None, scale=500, band=None,
                      lapse_rate=None, agg_scale=1000):
    """As :func:`downscaleTemperature`, with the dewpoint lapse rate.

    Separate because the rate is different, and the difference is the
    point: dewpoint falls more slowly with height than temperature
    does, so the two converge going up and relative humidity rises.
    Downscaling temperature while leaving dewpoint alone manufactures a
    mountain drier than the forecast ever said.

    Args:
        image: ``ee.Image`` carrying a dewpoint band, as
            ``getForecastData(variable='dewpoint_2m')`` returns.
        dem: elevation ``ee.Image``; defaults to :data:`DEFAULT_DEM`.
        scale: metres for the output's default projection.
        band: which band to adjust; the first by default.
        lapse_rate: degrees C per metre, negative.
            :data:`DEFAULT_DEWPOINT_LAPSE_RATE` if not given.
        agg_scale: intermediate grid for the cell-mean elevation. Not
            the output resolution.

    Returns:
        ``ee.Image`` with the same band name, at ``scale``, carrying the
        input's time and model properties.
    """
    return downscaleTemperature(
        image, dem=dem, scale=scale, band=band,
        lapse_rate=(DEFAULT_DEWPOINT_LAPSE_RATE if lapse_rate is None
                    else lapse_rate),
        agg_scale=agg_scale)


def downscalePrecipitation(image, dem=None, scale=500, band=None,
                           chi=None, max_ratio=5.0, agg_scale=1000):
    """Sharpen a coarse precipitation field with elevation, after MicroMet.

    Orographic enhancement: air forced up a slope cools, condenses and
    rains out, so precipitation rises with elevation over a cell. The
    form MicroMet adopts (from Thornton et al. 1997) is::

        P_fine = P_coarse * (1 + chi*dz) / (1 - chi*dz)

    with ``dz = z_fine - z_coarse``. It is multiplicative and symmetric
    in the right way: the same ``|dz|`` up and down gives reciprocal
    factors, so a cell's high ground gains exactly what its low ground
    loses in ratio terms.

    Two things about that formula are traps, and both are handled here.
    It has a **pole** at ``chi*dz = 1`` -- around 3300 m of relief at
    the default ``chi`` -- beyond which it changes sign and returns
    NEGATIVE precipitation. And even short of the pole it grows without
    bound. So ``dz`` is clamped to keep ``chi*dz`` inside +/-0.9 and the
    resulting ratio is clamped to ``[1/max_ratio, max_ratio]``.

    **This is a redistribution, not a rain model.** There is no wind
    direction in it, so it cannot know a windward slope from a lee one
    and will enhance both equally -- and rain shadow is the single
    largest orographic effect there is. Read it as "wetter up high
    within this cell", which is true on average and wrong on any
    particular lee slope.

    Args:
        image: ``ee.Image`` with a precipitation band, as
            ``getForecastData(variable='precipitation')`` returns.
        dem: elevation ``ee.Image``; defaults to :data:`DEFAULT_DEM`.
        scale: metres for the output's default projection.
        band: which band to adjust; the first by default.
        chi: adjustment factor per metre; :data:`DEFAULT_PRECIP_CHI` if
            not given. Larger means stronger enhancement.
        max_ratio: hard cap on the multiplier, both ways.
        agg_scale: intermediate grid for the cell-mean elevation. Not
            the output resolution.

    Returns:
        ``ee.Image`` with the same band name, never negative.
    """
    img = ee.Image(image)
    band = band or img.bandNames().get(0)
    k = DEFAULT_PRECIP_CHI if chi is None else chi
    dz, dem = _elevation_delta(img, dem, scale, agg_scale)

    # Keep chi*dz away from the pole at 1 BEFORE forming the ratio.
    x = dz.multiply(k).clamp(-0.9, 0.9)
    ratio = x.add(1).divide(ee.Image(1).subtract(x)) \
             .clamp(1.0 / max_ratio, max_ratio)
    out = img.select([band]).multiply(ratio).max(0).rename([band])
    return _finish(out, img, dem, scale)


def _uv(viz):
    """The two u/v selectors to hand to ``select()`` — names or indices.

    ``ee.Image.select`` takes positions as happily as names, so the
    default case resolves to ``[0, 1]`` and never asks the server what
    the bands are called. :func:`windBands` exists for callers who want
    the actual NAMES and is welcome to spend a round trip on them; the
    rendering path has no use for them and does not.
    """
    viz = viz or {}
    b = viz.get("bands")
    if isinstance(b, str):
        b = [x.strip() for x in b.split(",") if x.strip()]
    if not b:
        return [0, 1]
    if len(b) != 2:
        raise ValueError(
            f"wind needs exactly two bands (dx, dy); got {list(b)}. Pass "
            'viz={"bands": ["u_band", "v_band"]}.')
    return [b[0], b[1]]


def windImage(image, viz=None):
    """``speed`` and ``direction`` bands from the u/v components.

    These are the QUERY bands — the half of a wind layer that carries
    NUMBERS. geeViz lets a layer's rendering and its query source be
    different objects, and wind is the case that needs it: what you want
    to SEE is a flowing arrow field, and what you want to CLICK is a
    direction and a speed.

    Direction is meteorological by default — the bearing the wind blows
    FROM, so 270 is a westerly — because that is what forecast products
    and barb charts mean by "wind direction".

    .. note::
       This carries no time stamp. ``Map.addTimeLapse`` builds its frame
       list from ``system:time_start``, so re-set it from the source
       image or every frame formats to the same date and the lapse is
       one frame long.

    Args:
        image: ``ee.Image`` whose first two bands are the u/v
            components, as :func:`getForecastData` returns. In m/s —
            :data:`WIND_TILE_MIN_MS` and the downscaler both assume it.
        viz: same spirit as ``Map.addLayer``'s viz dict:

            * ``bands`` — the two components, if not the first two.
            * ``units`` — one of :data:`SPEED_UNITS`, default
              ``"km/hr"``.
            * ``directionConvention`` — ``"from"`` (default) or
              ``"to"``, the way the air is moving, which is what a
              spread model wants.
            * ``directionUnits`` — one of :data:`DIRECTION_UNITS`,
              default ``"degrees"``.

    Returns:
        ``ee.Image`` with bands ``speed`` and ``direction``, carrying
        ``wind_units``, ``wind_direction_convention`` and
        ``wind_direction_units`` so a chart can label itself.
    """
    viz = viz or {}
    u_b, v_b = _uv(viz)
    units = viz.get("units", "km/hr")
    if units not in SPEED_UNITS:
        raise ValueError(f"units must be one of {sorted(SPEED_UNITS)}")
    conv = viz.get("directionConvention", "from")
    if conv not in ("from", "to"):
        raise ValueError('directionConvention must be "from" or "to"')
    dir_units = viz.get("directionUnits", "degrees")
    if dir_units not in DIRECTION_UNITS:
        raise ValueError(
            f"directionUnits must be one of {sorted(DIRECTION_UNITS)}")

    img = _uv_image(image, viz)

    # Reuses fireLib rather than restating the maths: that helper carries
    # the bearing = 90 - math_angle REFLECTION, which is right on the
    # diagonals and wrong on all four cardinals if you get it wrong by
    # adding an offset instead.
    sd = wind_speed_direction(img, "u", "v")
    speed = sd.select("speed").multiply(SPEED_UNITS[units]).rename("speed")
    direction = (sd.select("direction_" + conv)
                   .multiply(DIRECTION_UNITS[dir_units]).rename("direction"))
    return (speed.addBands(direction)
            .set({"wind_units": units,
                  "wind_direction_convention": conv,
                  "wind_direction_units": dir_units}))


def windTiles(image, viz=None):
    """u/v encoded as an RGB image, for the particle tile service.

    Args:
        image: ``ee.Image`` whose first two bands are u/v, **in m/s** —
            the stretch below is absolute, not relative to the image.
        viz: ``bands`` picks the components; nothing else is read. The
            encoding is deliberately not configurable.

    Red carries u, green carries v, each stretched from
    :data:`WIND_TILE_MIN_MS` .. :data:`WIND_TILE_MAX_MS` onto 0..255.
    Blue is a constant; it exists only because ``visualize`` wants three
    bands for an RGB rendering.

    This is what lets the particles work anywhere instead of only inside
    a region fixed at call time. The previous design shipped a JSON
    lattice sampled once, so panning past its edge simply stopped the
    animation. Tiles stream with the view: the client fetches the
    squares it is looking at, decodes them, and advects.
    """
    viz = viz or {}
    u_b, v_b = _uv(viz)
    img = _uv_image(image, viz)
    rgb = img.addBands(ee.Image.constant(0).rename("z").toFloat())
    return rgb.visualize(bands=["u", "v", "z"],
                         min=WIND_TILE_MIN_MS, max=WIND_TILE_MAX_MS)


def _clamp01(value, name):
    """An opacity, as a float in [0, 1].

    Out-of-range is worth catching rather than clamping silently: 0-100
    is the other convention people arrive with, and ``opacity=80`` would
    otherwise pin to 1 and look exactly like the bug this whole change
    fixes -- a value that was set and did nothing.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError(
            f"{name} must be a number between 0 and 1, got {value!r}")
    if not 0.0 <= v <= 1.0:
        raise ValueError(
            f"{name} must be between 0 and 1, got {v!r}"
            + (" (opacities here are fractions, not percentages)"
               if v > 1 else ""))
    return v


def _wind_vizzes(viz):
    """The two viz dicts ``addWindLayer`` and ``addWindTimeLapse`` share.

    Pure: no ``Map``, no ``ee`` call. Extracted so the single-frame
    and time-lapse entry points cannot drift apart -- the particle
    dict carries the tile encoding bounds the client decodes with,
    and a copy of that in two places would not throw when it
    diverged, it would yield winds wrong by a scale and offset,
    which still look like weather.

    Returns ``(speed_viz, particle_viz)``.
    """
    viz = dict(viz or {})
    # Two bases the rest of the particle defaults hang off. Resolved
    # here so that setting only the base moves everything derived from
    # it, rather than leaving a half-scaled taper or lifetime range.
    # particleLineWidth is the old name for particleStrokeWeight and is
    # still honored.
    stroke_weight = viz.get("particleStrokeWeight",
                            viz.get("particleLineWidth", 1.1))
    max_age = viz.get("particleMaxAge", 45)
    units = viz.get("units", "km/hr")
    if units not in SPEED_UNITS:
        raise ValueError(f"units must be one of {sorted(SPEED_UNITS)}")
    vmin = viz.get("min", 0)
    vmax = viz.get("max", DEFAULT_MAX_SPEED[units])
    # The particle speed bounds ARE the raster stretch.
    #
    # They used to be two separate numbers in m/s while the stretch was
    # in `units`, so `units='km/hr', max=30` saturated the color ramp at
    # 8.3 m/s while particles went on lengthening to a fixed 45. Past
    # `max` the raster is one flat color, and a streak still growing
    # there claims a difference the map has stopped showing; below `min`
    # the same in reverse. Deriving both leaves one speed knob --
    # `particleSpeed`, in pixels per frame per m/s -- and the stretch
    # decides where the ramp starts and stops.
    #
    # SPEED_UNITS holds the multiplier FROM m/s, so dividing converts
    # back: 100 mi/hr -> 44.7 m/s, 54 km/hr -> 15 m/s.
    vmax_ms = float(vmax) / SPEED_UNITS[units]
    vmin_ms = float(vmin) / SPEED_UNITS[units]

    # A stretch starting at 0 -- which is nearly every wind map -- would
    # mean no floor at all, and length is proportional to speed, so a
    # light breeze draws a one-pixel dot and a calm map reads as broken.
    # 1 m/s in that case, not 1 of whatever `units` happens to be: the
    # bounds are m/s throughout, and 1 mi/hr would put the dots back.
    #
    # The `> 0` also catches a negative `min`, which is not a speed --
    # no separate clamp needed for it.
    floor_ms = vmin_ms if vmin_ms > 0 else 1.0
    # An inverted or degenerate stretch must not invert the clamp.
    floor_ms = min(floor_ms, vmax_ms)

    palette = viz.get("palette", DEFAULT_SPEED_PALETTE)
    if isinstance(palette, str):
        palette = [c.strip() for c in palette.split(",")]
    pal_csv = ",".join(c.lstrip("#") for c in palette)

    # ---- opacity -------------------------------------------------------
    # A wind layer draws TWO things, so a single number has to say which
    # one it means. ``opacity`` is the master and means both: it is where
    # each of the two dimmers starts, so ``opacity=0.8`` shows a speed
    # field and a flow that are each at 0.8, which is what anyone setting
    # it on an ordinary layer would expect.
    #
    # Neither of these dicts used to carry ``opacity`` at all, so a
    # caller's value was dropped on the floor here and the viewer
    # defaulted both to 1 -- setting it appeared to do nothing whatsoever.
    #
    # ``windSpeedOpacity`` overrides it for the raster alone, and is the
    # counterpart to ``particleOpacity``: one per thing drawn.
    #
    # Clamped, because the canvas alpha and the slider both live in
    # [0, 1] and an out-of-range value silently pins to an end rather
    # than reporting itself.
    master_opacity = _clamp01(viz.get("opacity", 1), "opacity")
    speed_opacity = _clamp01(viz.get("windSpeedOpacity", master_opacity),
                             "windSpeedOpacity")

    speed_viz = {
        "layerType": "geeImage",
        "bands": "speed",
        "min": vmin, "max": vmax,
        "palette": pal_csv,
        "opacity": speed_opacity,
        "canQuery": True,
        "addToLegend": True,
        "yLabel": "Wind speed (" + units + ")",
        "legendLabelLeftBefore": "Calm",
        "legendLabelRightAfter": " " + units,
    }

    # 2. The particle layer. A real geeImage layer, so the viewer mints
    #    tiles for it and gives it a panel entry -- but the RGB is never
    #    shown. wind-particles.js hides it and reads those tiles
    #    numerically instead.

    particle_viz = {
        "layerType": "geeImage",
        "windParticles": True,
        "windTileMin": WIND_TILE_MIN_MS,
        "windTileMax": WIND_TILE_MAX_MS,
        "windUnits": units,
        # The master, not ``speed_opacity``. Ungrouped, this IS the
        # particle layer's own opacity slider.
        "opacity": master_opacity,
        "canQuery": False,          # the speed raster answers clicks
        # One swatch, in the particle color.
        #
        # The layer had no legend entry at all, which left an animated
        # field on the map with nothing in the key explaining it -- and
        # two wind layers up at once were indistinguishable. The viewer
        # builds a class entry per key of classLegendDict for any
        # non-vector layer, which is exactly one line here.
        #
        # The value is a CSS background rather than a hex, so the swatch
        # is a small comet in the particle's own color instead of a
        # flat chip. ``addColorHash`` only prepends '#' to a bare hex,
        # so this reaches the span untouched.
        "addToLegend": True,
        "classLegendDict": {
            viz.get("particleLegendLabel", "Wind direction (animated)"):
                _particle_swatch(
                    _rgb_of(viz.get("particleColor", "#fff")),
                    viz.get("particleOpacity", 0.9),
                    viz.get("particleTaper", 2.1),
                    viz.get("particleHeadBoost", 1.6),
                    viz.get("particleMaxWidth", stroke_weight * 1.5),
                    palette=palette,
                    ramp_opacity=viz.get("particleLegendRampOpacity", 0.5)),
        },
        # ---- color ---------------------------------------------
        "particleColor": viz.get("particleColor", "#fff"),
        "particleOpacity": viz.get("particleOpacity", 0.9),

        # ---- count ---------------------------------------------
        # Derived from canvas WIDTH, not from zoom: a wider canvas has
        # more room to fill, and that is the whole of it. ~3000 on a
        # 1700 px canvas. The count used to compound with zoom, which
        # was really compensating for streak length growing with zoom;
        # length is held constant on screen now, so density should be
        # too, and the zoom term only thinned the field where it was
        # already densest.
        #
        # NOT sent unless the caller asked for it -- stamping a number
        # here would pin the count and the width derivation would never
        # run. This is the one particle key that is deliberately absent
        # by default.
        **({"particleCount": viz["particleCount"]}
           if viz.get("particleCount") is not None else {}),
        "particleDensity": viz.get("particleDensity", 1.2),
        # Where particles START. "random" (default) scatters them, which
        # is what a flow field usually wants -- the eye reads the
        # streaks, not their origins. "grid" is a strict lattice and
        # "randomGrid" the same lattice under one random offset, both of
        # which trade that for even coverage, the way a barb or quiver
        # plot is laid out.
        "particleLayout": viz.get("particleLayout", "random"),

        # ---- size ----------------------------------------------
        # strokeWeight is the base; min/max size are absolute pixel
        # widths at tail and head, defaulting to a fraction of it so
        # changing the weight alone scales the whole taper.
        "particleStrokeWeight": stroke_weight,
        # WIDTH is across the streak; LENGTH along it is
        # particleTrailLength. Named for what they measure.
        "particleMinWidth": viz.get("particleMinWidth", stroke_weight * 0.45),
        "particleMaxWidth": viz.get("particleMaxWidth", stroke_weight * 1.5),

        # ---- shape ---------------------------------------------
        # trailLength * the per-frame step IS the streak length. It
        # replaced a canvas fade constant, which could give length or a
        # bright head but never both: a fade slow enough for a long
        # trail is nearly flat over its first twenty frames.
        "particleTrailLength": viz.get("particleTrailLength", 13),
        "particleTaper": viz.get("particleTaper", 2.1),
        "particleHeadBoost": viz.get("particleHeadBoost", 1.6),
        "particleLineCap": viz.get("particleLineCap", "round"),

        # ---- speed ---------------------------------------------
        # Pixels per frame per m/s of wind, at the equator. One number
        # where there were two: screen speed was
        # speedFactor * 2**(zoomRef - zoom) / metresPerPixel, and
        # metresPerPixel is 156543 * cos(lat) / 2**zoom -- the powers of
        # two cancel exactly, leaving a constant over cos(lat). Zoom does
        # not appear, which is the same thing as saying a streak is the
        # same size on screen at every zoom.
        "particleSpeed": viz.get("particleSpeed", 0.5),
        # Apparent-speed floor and ceiling in m/s, applied to the
        # advection only. Streak length is proportional to wind speed,
        # so without a floor a light breeze draws a one-pixel dot and a
        # calm map reads as a broken map; without a ceiling a cyclone
        # core smears across the screen. Direction is untouched, and the
        # speed raster and click query still carry the truth.
        # The stretch, in m/s, for the client to clamp advection with.
        # NOT particle parameters -- there is nothing to set here that
        # `min`, `max` and `units` do not already say, and two loose m/s
        # numbers beside a stretch in some other unit is exactly the
        # contradiction this replaced. The name carries the unit because
        # the viz dict's own min/max are in `units`, not m/s.
        "windMinSpeedMs": floor_ms,
        "windMaxSpeedMs": vmax_ms,

        # The COLOR ramp, for a client that draws the speed field itself
        # rather than putting a second Earth Engine layer under the
        # particles -- see addWindTimeLapse. Deliberately not `min`,
        # `max` and `palette`: those reach getMapId, and the image these
        # ride on is already `visualize`d, so they would re-stretch an
        # RGB that is finished.
        #
        # Unclamped, unlike windMinSpeedMs above: the 1 m/s floor is an
        # advection floor, and applying it to the ramp would shift every
        # color on a stretch that starts at zero.
        "windRampMinMs": vmin_ms,
        "windRampMaxMs": vmax_ms,
        "windSpeedPalette": palette,

        # The same stretch in DISPLAY units, for the legend's end
        # labels. The m/s pair above is what the renderer clamps with;
        # these are what a reader sees, and deriving one from the other
        # in the client would mean shipping the unit conversion twice.
        "windRampMin": vmin,
        "windRampMax": vmax,

        # ---- lifetime ------------------------------------------
        # Each particle draws its own lifetime from
        # [particleMinAge, particleMaxAge], so short, medium and long
        # streaks coexist instead of one uniform comb. Set them equal
        # for a uniform look.
        "particleMaxAge": max_age,
        "particleMinAge": viz.get("particleMinAge", max_age * 0.25),
    }

    return speed_viz, particle_viz


def addWindLayer(Map, image, viz=None, name="Wind", visible=True,
                 groupWindLayers=True):
    """Add a wind field: a queryable speed raster plus animated particles.

    Two layers, in the style of windy.com -- a smooth speed raster
    carrying the reading, with particle trails over it showing the flow.

    Args:
        Map: the geeViz ``Map`` object to add the two layers to.
        image: ``ee.Image`` whose bands include the wind components,
            **in m/s** — the particle tile encoding and the default
            speed stretch are both absolute.
        name: base name for the pair; the layers appear as
            ``"<name> speed"`` and ``"<name> particles"``.
        visible: whether the layer starts switched on.
        groupWindLayers: ``True`` (the default) draws the whole thing as
            ONE layer. :func:`windTiles` already carries everything the
            picture needs -- u in red, v in green, speed is
            ``sqrt(u**2 + v**2)`` -- so the client paints the colored
            speed field and the trails from the same decoded bytes. That
            halves the tiles, gives the two halves independent opacity
            sliders, and leaves one entry in the layer list. Clicks
            still report real speed and direction: the query is pointed
            at the speed image rather than at the encoding.

            ``False`` restores the original two layers, where Earth
            Engine renders the speed raster instead of the client. That
            is the only thing grouping gives up.
        viz: Same spirit as ``Map.addLayer``'s viz dict.

            * ``bands`` (list or comma string) -- the dx/dy components.
              Defaults to the image's FIRST TWO bands, in order.
            * ``units`` -- ``"km/hr"`` (default), ``"m/s"``,
              ``"mi/hr"`` or ``"kt"``. Knots is what aviation, marine
              forecasts and windy.com use.
            * ``min`` / ``max`` -- speed stretch. ``max`` defaults to a
              value chosen FOR THE UNIT (15 m/s, 54 km/h, 34 mi/h), so
              switching units cannot leave the raster all one color.
            * ``palette`` -- speed ramp. Defaults to
              :data:`WIND_PALETTE`, taken from windy.com's legend.
            * ``particleColor`` -- trail color, default ``"#fff"``.
            * ``particleOpacity`` (0.9) -- alpha at the head. A LOOK,
              not a dimmer: it shapes the comet together with
              ``particleTaper`` and ``particleHeadBoost``. To fade the
              whole flow, use ``opacity``.

            **Opacity.** A wind layer draws two things, so it has two
            dimmers -- and ``opacity`` (1) is the master that sets where
            both of them start, so ``{"opacity": 0.8}`` gives a speed
            field and a flow that are each at 0.8.
            ``windSpeedOpacity`` overrides it for the speed raster
            alone, and is the counterpart to ``particleOpacity``: one
            number per thing drawn::

                {"opacity": 0.8}                          # both at 0.8
                {"opacity": 0.8, "windSpeedOpacity": 0.3} # a faint
                                                          # field under
                                                          # bright trails

            Fractions in [0, 1], not percentages -- ``80`` raises rather
            than quietly meaning 1. Grouped, each value lands on one of
            the two opacity sliders in the layer panel and both keep
            working afterwards; these only say where they start.

            **Width.** Across the streak; LENGTH along it is
            ``particleTrailLength``. ``particleStrokeWeight`` (1.1) is
            the base, and ``particleMinWidth`` / ``particleMaxWidth``
            are the absolute pixel widths at the tail and the head,
            defaulting to 0.45x and 1.5x the weight so changing the
            weight alone rescales the whole taper. Equal min and max
            give a constant-width ribbon instead of a comet.
            ``particleLineWidth`` is the old name for
            ``particleStrokeWeight`` and still works.

            **Shape.** ``particleTrailLength`` (13) is how many frames
            of history each trail draws -- that, times the per-frame
            step, IS the streak length. ``particleTaper`` (2.1) is the
            exponent on the tail fade: 1 is a linear wedge, higher
            stretches the faint part out. ``particleHeadBoost`` (1.6)
            brightens the leading segment. ``particleLineCap``
            (``"round"``, or ``"butt"`` for blunt tips).

            **Speed.** ``particleSpeed`` (0.5) is pixels per frame
            for each m/s of wind, at the equator -- so it sets both how
            fast the field moves and, since length is proportional to
            it, how long the streaks are. Zoom does not enter into it:
            a streak is the same size on screen however far in you are.
            That is the ONLY speed knob. The floor and ceiling on
            apparent speed are taken from ``min`` and ``max``, converted
            from ``units`` to m/s, so the streaks start and stop
            growing exactly where the color ramp does. Past ``max`` the
            raster is one flat color and a longer streak there claims a
            difference the map has stopped showing; the same in reverse
            below ``min``.

            A stretch starting at 0 -- nearly every wind map -- would
            leave no floor, so 0 becomes 1 m/s: length is proportional
            to speed, and without a floor a light breeze draws a
            one-pixel dot and a calm map reads as broken.

            The bounds apply to the ADVECTION only. Direction is
            untouched, and the speed raster and the click query still
            report the true value, so never read a wind speed off a
            streak. There are no separate floor/ceiling parameters:
            widen ``min`` / ``max`` to widen the range the streaks
            respond over.

            NOTE ``particleSpeed``, ``particleTrailLength``,
            ``particleMaxAge`` and the renderer's 30fps cap are ONE
            group. Streak length is ``trailLength * speed`` and apparent
            motion is ``speed * frameRate``, so at a fixed rate the
            trail cannot be shortened without speeding the field up, and
            lifetimes are counted in frames so they scale with the rate
            too. Changing one of the four alone changes the look.

            **Lifetime.** ``particleMinAge`` / ``particleMaxAge``
            (11.25 and 45) -- the range each particle's lifetime is drawn
            from. A young particle has laid down less trail, so
            spreading lifetimes is what puts short streaks alongside
            long ones. Equal values give one uniform length. At the end
            of its life a particle stops advancing and its trail
            RETRACTS over ``particleTrailLength`` frames, so the streak
            slides away rather than blinking out.

            **Layout.** ``particleLayout`` -- where particles start.
            ``"random"`` (default) scatters them, which is what a flow
            field usually wants: the eye reads the streaks, not their
            origins. ``"grid"`` is a strict lattice and ``"randomGrid"``
            the same lattice under one random offset -- both trade
            scatter for even coverage, the way a barb or quiver plot is
            laid out, and a lattice particle respawns in its own cell so
            the pattern does not erode into noise.

            **Count.** Derived from canvas WIDTH:
            ``particleDensity`` (1.2) particles per pixel of width, so
            about 2000 on a 1700 px canvas. Pass ``particleCount`` to
            override it outright. There is no floor or ceiling --
            width times density cannot run away, and a phone and a 5K
            display each get the right number for their screen.

            * ``directionConvention`` -- ``"from"`` (default) or ``"to"``.

    Returns:
        ``(speed_direction_image, encoded_tiles_image)``. Grouped, only
        the second goes on the map; the first is what clicks are
        answered from.
    """
    viz = dict(viz or {})
    speed_viz, particle_viz = _wind_vizzes(viz)

    q = windImage(image, viz)
    tiles = windTiles(image, viz)

    if groupWindLayers:
        # ONE layer. windTiles already carries everything the picture
        # needs -- u in red, v in green, speed is sqrt(u^2 + v^2) -- so
        # a second Earth Engine layer underneath would double the tiles
        # for data already on the wire. The client paints the speed
        # field and the trails from the same decoded bytes, which is
        # also what makes their opacities independent.
        Map.addLayer(tiles, _merged_viz(viz, speed_viz, particle_viz, q),
                     name, visible)
        return q, tiles

    # Two layers, the original arrangement. Kept because the speed
    # raster is rendered by Earth Engine here rather than by the client,
    # which is the one thing the grouped form gives up.
    #
    # 1. The speed raster, and the layer a click reads. Both derived
    #    bands ride along so a query reports direction beside speed.
    Map.addLayer(q, speed_viz, name + " speed", visible)

    # 2. The particle layer. A real geeImage layer, so the viewer mints
    #    tiles for it and gives it a panel entry -- but the RGB is never
    #    shown. wind-particles.js hides it and reads those tiles
    #    numerically instead.
    Map.addLayer(tiles, particle_viz, name + " particles", visible)

    return q, tiles


def _merged_viz(viz, speed_viz, particle_viz, query_obj, date_format=None):
    """The viz for ONE layer that draws the speed field and the flow.

    Shared by :func:`addWindLayer` and :func:`addWindTimeLapse` so the
    grouped form cannot drift between the single frame and the lapse.

    Built on ``particle_viz``, not ``speed_viz``, and that matters:
    ``bands``, ``min``, ``max`` and ``palette`` are forwarded to
    ``getMapId``, and the image underneath is already ``visualize``d --
    a finished 8-bit RGB. Applying a palette to it is an error in Earth
    Engine ("palette can only be used with single-band images"), and a
    re-stretch would corrupt the very u/v bytes the client decodes. The
    ramp travels under client-only names instead; see ``_wind_vizzes``.
    """
    merged = dict(particle_viz)

    # The client draws the colored speed field from the same tiles.
    merged["windSpeedRaster"] = True

    # ---- the two dimmers ------------------------------------------
    # Grouped, there is one layer and two sliders. The viewer builds one
    # of them from ``opacity`` and it drives the SPEED RASTER, so that is
    # the value that goes there. The particle slider is ours, and it
    # starts wherever the master says.
    #
    # Both are live controls; these only say where they start. Keeping
    # each slider the single source of truth for its own canvas is why
    # they are two numbers rather than one number and a multiplier -- a
    # multiplier would put the handle at 0.8 while the thing it controls
    # renders at 0.4.
    merged["opacity"] = speed_viz["opacity"]
    merged["windParticleDim"] = particle_viz["opacity"]

    # The click query still reads real weather. The viewer keeps the
    # queried object separate from the drawn one, so the inspector can
    # be pointed at speed/direction while the map shows the encoding --
    # without this a click would report bytes as if they were wind.
    #
    # Serialized because viz travels as JSON: an ee object here raises
    # "not JSON serializable" at Map.view() time. wind-particles.js
    # decodes it onto queryObj once the panel exists.
    merged["windQueryItem"] = query_obj.serialize()
    merged["canQuery"] = True
    merged["yLabel"] = speed_viz["yLabel"]
    if date_format:
        merged["queryDateFormat"] = date_format

    # ONE legend entry, because there is now one layer.
    #
    # _particle_swatch already draws the comet OVER the speed ramp --
    # which is exactly what the map shows -- so the grouped layer needs
    # nothing else. At full ramp opacity it reads as the color bar it
    # has to stand in for, rather than as a backdrop behind the comet.
    merged["classLegendDict"] = {
        _speed_ramp_label(viz): _particle_swatch(
            _rgb_of(viz.get("particleColor", "#fff")),
            particle_viz["particleOpacity"],
            particle_viz["particleTaper"],
            particle_viz["particleHeadBoost"],
            particle_viz["particleMaxWidth"],
            # The LIST, not speed_viz["palette"] -- that one is the
            # comma string Earth Engine's viz takes.
            palette=particle_viz["windSpeedPalette"],
            ramp_opacity=1.0,
            wide=True,
        )
    }
    merged["addToLegend"] = True
    return merged


def _speed_ramp_label(viz):
    """The color bar's label: the stretch and the unit it is in."""
    units = viz.get("units", "km/hr")
    vmin = viz.get("min", 0)
    vmax = viz.get("max", DEFAULT_MAX_SPEED[units])
    return f"Wind speed {_trim(vmin)}-{_trim(vmax)} {units}"


def _trim(x):
    """5.0 -> '5'. A color-bar label is not the place for a float tail."""
    f = float(x)
    return str(int(f)) if f == int(f) else f"{f:g}"


def addWindTimeLapse(Map, collection, viz=None, name="Wind", visible=True,
                     dateFormat=None, advanceInterval=None, mosaic=False,
                     groupWindLayers=True):
    """Add an animated wind field that is itself a time lapse.

    The same two layers :func:`addWindLayer` adds -- a queryable speed
    raster and the particle flow over it -- but each is a time lapse, so
    the slider scrubs the field while the particles keep flowing through
    it.

    Why this works without a new frame format: :func:`windTiles` already
    packs u and v into ONE RGB image (u->R, v->G), so a "paired" wind
    frame is a single ``ee.Image`` by the time the viewer sees it. There
    is nothing to pair up at the frame level; mapping the same encoder
    over the collection is the whole server side.

    Args:
        Map: the geeViz ``Map`` object.
        collection: ``ee.ImageCollection`` whose images carry the wind
            components **in m/s**, with ``system:time_start`` set --
            that is what the slider reads. :func:`getForecastData`
            returns this shape.
        viz: exactly what :func:`addWindLayer` accepts; see that
            docstring. Both layers are built from one call to
            ``_wind_vizzes`` so the encoding the client decodes with
            cannot drift between the two entry points.
        name: base name; layers appear as ``"<name> speed"`` and
            ``"<name> particles"``.
        visible: whether the layer starts switched on.
        groupWindLayers: ``True`` (the default) animates the whole thing
            as ONE time lapse -- each frame carries the speed field and
            the particles, from one set of tiles. See
            :func:`addWindLayer` for what that buys and what it costs.
        dateFormat: slider label format. Defaults to ``"YYYYMMdd HH"`` --
            forecast wind is hourly-to-three-hourly, and the annual
            ``"YYYY"`` default of :meth:`addTimeLapse` would collapse
            every frame onto one label.
        advanceInterval: frame step. Defaults to ``"hour"`` for the same
            reason.
        mosaic: passed through; ``True`` reduces multiple images per
            step with ``lastNonNull``.

    Returns:
        ``(speed_collection, tiles_collection)`` -- the two mapped
        ImageCollections, for inspection or re-use.

    Example:
        >>> ic = wx.getForecastData("2026-09-18", "2026-09-20",
        ...                         model="gfs", variable="wind")
        >>> wx.addWindTimeLapse(Map, ic, {"units": "kt"}, "GFS wind")
        >>> Map.view()
    """
    viz = dict(viz or {})
    speed_viz, particle_viz = _wind_vizzes(viz)

    # Hourly by default. addTimeLapse defaults to annual, which is right
    # for land cover and wrong for weather: every frame of a two-day
    # forecast would carry the same "2026" label and the slider would
    # read as broken.
    tl = {
        "dateFormat": dateFormat or "YYYYMMdd HH",
        "advanceInterval": advanceInterval or "hour",
        "mosaic": mosaic,
    }

    collection = ee.ImageCollection(collection)

    # 1. Speed raster, per frame. windImage is pure server-side -- no
    #    getInfo anywhere in _uv / _uv_image / windImage -- so it maps.
    def _stamped(fn):
        """Map ``fn`` and put ``system:time_start`` back.

        windImage and windTiles both build a NEW image (speed/direction,
        or the u/v RGB encoding), and a new image carries no time. The
        viewer builds its frame list from the distinct dates present, so
        an unstamped collection formats every frame to the same label
        and the lapse collapses to ONE frame -- silently, with no error.
        """
        def _inner(img):
            img = ee.Image(img)
            return ee.Image(fn(img, viz)).set(
                "system:time_start", img.get("system:time_start"))
        return _inner

    speed_ic = collection.map(_stamped(windImage))
    tiles_ic = collection.map(_stamped(windTiles))

    # ONE time lapse, not two.
    #
    # The u/v frames are the only ones the viewer mints tiles for, and
    # the client draws BOTH the speed field and the particles out of
    # them. That is possible because windTiles already carries
    # everything: u in red, v in green, and speed is sqrt(u^2 + v^2).
    # Blue is a spare channel. _uv_image bicubic-resamples before
    # encoding, so the client's raster is the same resampling of the
    # same forecast grid the separate speed layer used to show.
    #
    # What this buys, beyond one entry in the layer list instead of two:
    # HALF the tiles per frame, which on a lapse is the difference
    # between arriving at each hour warm and arriving cold; and two
    # opacity controls that are genuinely independent, because one
    # client owns both renders instead of two Earth Engine layers each
    # owning one.
    if not groupWindLayers:
        # Two lapses, the original arrangement.
        Map.addTimeLapse(speed_ic, {**speed_viz, **tl},
                         name + " speed", visible)
        Map.addTimeLapse(tiles_ic, {**particle_viz, **tl},
                         name + " particles", visible)
        return speed_ic, tiles_ic

    lapse_viz = {**_merged_viz(viz, speed_viz, particle_viz, speed_ic,
                               date_format=tl["dateFormat"]), **tl}

    Map.addTimeLapse(tiles_ic, lapse_viz, name, visible)

    return speed_ic, tiles_ic


#: Global DEM for terrain downscaling. 30 m, and the only one with
#: worldwide coverage -- forecast wind is a global product, so a US-only
#: DEM would silently stop working outside CONUS.
DEFAULT_DEM = "NASA/NASADEM_HGT/001"


def downscaleWind(image, region, dem=None, scale=500, viz=None,
                  curvature_radius=None, slope_weight=0.5,
                  curvature_weight=0.5, normalize_percentile=98,
                  z0=None, z_ref=10.0):
    """Sharpen a coarse wind field with terrain, after Liston & Elder.

    A forecast wind field is 0.25 degrees for GFS -- about 28 km, which
    is an order of magnitude coarser than the terrain that actually
    steers surface wind. This applies the MicroMet topographic
    adjustment (Liston, G. E. and Elder, K., 2006, *A Meteorological
    Distribution System for High-Resolution Terrestrial Modeling
    (MicroMet)*, J. Hydrometeorology 7(2), 217-234), which is the
    standard intermediate-complexity method: cheap, no iteration, and
    defensible to cite.

    **It is not a wind model.** There is no mass conservation and no
    momentum -- a solver like WindNinja does that and cannot be
    expressed as a per-pixel Earth Engine computation. What this buys is
    the first-order terrain signal: faster over ridges and windward
    slopes, slower in valleys and lees, with the flow turned somewhat
    along the topography. Treat the result as a better-resolved
    rendering of the same forecast, not as new information about the
    atmosphere.

    The method
    ----------
    Speed is scaled by a weighted sum of two terrain terms::

        W = 1 + slope_weight * omega_s + curvature_weight * omega_c

    ``omega_s`` is the slope IN THE WIND DIRECTION,
    ``alpha * cos(theta - beta)`` for terrain slope ``alpha``, aspect
    ``beta`` and wind direction ``theta``. ``omega_c`` is terrain
    curvature: the elevation at a point minus the mean around it, so
    ridges are positive and valleys negative.

    Both are normalised to ``[-0.5, 0.5]`` over ``region``, which with
    weights summing to 1 bounds ``W`` to ``[0.5, 1.5]`` -- the factor-of
    -two-either-way limit the paper specifies, and the reason the
    normalisation is domain-dependent rather than a fixed constant.

    Direction is diverted toward the terrain by::

        theta_d = -0.5 * omega_s * sin(2 * (beta - theta))

    which is at most 0.25 rad, the paper's +/-14.3 degrees.

    Args:
        image: ``ee.Image`` with wind components (``u``, ``v`` by
            default, as :func:`getForecastData` returns).
        region: ``ee.Geometry`` the normalisation is computed over.
            REQUIRED, and not a formality: the terms are scaled by the
            largest slope and curvature present, so the same mountain
            downscales differently inside a small domain than inside a
            continental one. That is how the method is defined.
        dem: elevation ``ee.Image``. Defaults to :data:`DEFAULT_DEM`,
            bicubic-resampled -- terrain derivatives on a raw DEM give
            absurdly flat slopes and diagonal hatching.
        scale: metres, for the normalisation reduction. The output
            itself is resolution-independent; this sets how finely the
            slope and curvature extremes are measured.
        viz: as elsewhere -- ``viz["bands"]`` names the u/v pair.
        curvature_radius: metres for the curvature neighbourhood.
            Defaults to ``4 * scale``. Larger picks up whole landforms,
            smaller picks up individual gullies.
        slope_weight, curvature_weight: the paper's scale factors. They
            should sum to 1, which is what keeps ``W`` inside
            ``[0.5, 1.5]``.
        normalize_percentile: what counts as "the strongest terrain
            here", as a percentile of the absolute slope and curvature
            over ``region``. The paper says the maximum; 98 by default
            because a single canyon can run twice the 98th percentile
            and normalising by it flattens everything else. 100
            reproduces the paper exactly.
        z0: OPTIONAL roughness length image, metres. When given, a log
            wind profile also scales speed by
            ``ln(z_ref / z0) / ln(z_ref / z0_ref)`` -- rougher ground
            slows the surface wind. Terrain roughness in the sense of
            vegetation and land cover, which the DEM knows nothing
            about.
        z_ref: reference height of the wind, metres. 10 for every
            product here.

    Returns:
        ``ee.Image`` with ``u`` and ``v`` bands, downscaled. Feed it to
        :func:`addWindLayer` exactly like the input.
    """
    viz = viz or {}
    u_b, v_b = _uv(viz)
    src = ee.Image(image).select([u_b, v_b], ["u", "v"])

    # ---- the coarse field, as speed and direction --------------------
    # Reuses fireLib rather than restating the maths: that helper carries
    # the bearing = 90 - math_angle REFLECTION, which is right on the
    # diagonals and wrong on all four cardinals if you get it wrong by
    # adding an offset instead.
    sd = wind_speed_direction(src, "u", "v")
    speed = sd.select("speed")
    # Meteorological: the direction the wind blows FROM. That is what
    # Liston's theta means, so the terms below line up with the paper.
    theta = sd.select("direction_from").multiply(math.pi / 180.0)

    # ---- terrain -----------------------------------------------------
    if dem is None:
        dem = ee.Image(DEFAULT_DEM)
    # Bicubic BEFORE the derivative; a raw DEM yields flat slopes and
    # diagonal hatch artefacts. A single image already carries its own
    # projection, so nothing needs restoring.
    # First band only. NASADEM ships elevation, num and swb; without
    # this the curvature carries all three through and the rename at the
    # end fails with a band-count error that points nowhere near here.
    dem = ee.Image(dem).select(0).resample("bicubic")
    alpha = ee.Terrain.slope(dem).multiply(math.pi / 180.0)
    beta = ee.Terrain.aspect(dem).multiply(math.pi / 180.0)

    # ---- omega_s: slope in the wind direction ------------------------
    omega_s_raw = alpha.multiply(beta.subtract(theta).cos())

    # ---- omega_c: curvature ------------------------------------------
    # Elevation minus the mean around it. Liston samples four axes at a
    # fixed length; a circular mean is the same idea with one call, and
    # the normalisation below makes the constant factor irrelevant.
    radius = curvature_radius if curvature_radius is not None else scale * 4
    omega_c_raw = dem.subtract(
        dem.focalMean(radius=radius, units="meters", kernelType="circle"))

    # ---- normalise both to [-0.5, 0.5] over the region ---------------
    def _norm(img, name):
        # Scaled so the strong terrain in the domain reaches the +/-0.5
        # that bounds W to [0.5, 1.5]. Server-side: an ee.Number, no
        # round trip.
        #
        # A PERCENTILE, not the absolute maximum the paper specifies.
        # Measured over the Colorado Rockies, one canyon runs 2.1x the
        # 98th percentile of curvature, and normalising by it left a
        # typical cell reaching 8% of its adjustment budget -- the
        # terrain signal all but vanished, which is not what the method
        # is for. At p98 the same cell reaches 17%. The bound the paper
        # cares about still holds, because the result is clamped.
        mx = img.abs().reduceRegion(
            reducer=ee.Reducer.percentile([normalize_percentile]),
            geometry=region, scale=scale,
            bestEffort=True, maxPixels=1e9).values().get(0)
        mx = ee.Number(ee.Algorithms.If(mx, mx, 1))
        # A flat domain has no terrain signal; dividing by ~0 would turn
        # rounding noise into a full-strength adjustment.
        mx = ee.Number(ee.Algorithms.If(mx.gt(1e-9), mx, 1))
        return img.divide(ee.Image.constant(mx).multiply(2)).clamp(-0.5, 0.5)

    omega_s = _norm(omega_s_raw, "s")
    omega_c = _norm(omega_c_raw, "c")

    # ---- speed and direction adjustment ------------------------------
    w = (ee.Image.constant(1)
         .add(omega_s.multiply(slope_weight))
         .add(omega_c.multiply(curvature_weight)))
    speed_ds = speed.multiply(w)

    if z0 is not None:
        # Log wind profile. z0_ref is open short grass, the surface a
        # 10 m forecast wind is nominally reported over.
        z0_ref = 0.03
        z0 = ee.Image(z0).max(1e-4)
        speed_ds = speed_ds.multiply(
            ee.Image.constant(z_ref).divide(z0).log()
              .divide(math.log(z_ref / z0_ref)))

    theta_ds = theta.add(
        omega_s.multiply(-0.5).multiply(beta.subtract(theta).multiply(2).sin()))

    # ---- back to components ------------------------------------------
    # theta is the direction the wind comes FROM, so the vector points
    # the opposite way. Pinned by a round-trip test rather than trusted:
    # a sign error here still produces a plausible-looking wind field.
    u = theta_ds.sin().multiply(speed_ds).multiply(-1).rename("u")
    v = theta_ds.cos().multiply(speed_ds).multiply(-1).rename("v")
    # _finish stamps the DEM's grid at the requested scale and carries
    # the forecast's identity across. Shared with the temperature,
    # dewpoint and precipitation downscalers -- all four had the same
    # two paragraphs of reasoning about setDefaultProjection, and two
    # copies of that is how one of them ends up fixed and the rest not.
    return _finish(u.addBands(v), image, dem, scale)


#: DeepMind WeatherLab. Google's own viewer for WeatherNext and its
#: cyclone models.
WEATHERLAB_URL = "https://deepmind.google.com/science/weatherlab"

#: WeatherLab names its weather layers exactly as WeatherNext names its
#: bands, so :data:`VARIABLES` is already the translation table -- a
#: geeViz ``variable`` key maps straight through.
#:
#: Checked against the layer in a shared WeatherLab link:
#: ``weather_layers=total_precipitation_1hr_mean`` is the same string
#: ``VARIABLES["precipitation"]["weathernext"]`` carries.


def weatherLabURL(center=None, zoom=None, variable=None,
                  model="weathernext3", valid_time=None, init_time=None,
                  cyclone=None, cyclone_models=None, legend_elements=None,
                  panel=None, weather=None, cyclones=None, extra=None):
    """A deep link into DeepMind's WeatherLab, at a given place and time.

    **This returns a LINK, not an embed.** WeatherLab serves
    ``X-Frame-Options: SAMEORIGIN`` and redirects to Google sign-in, so
    it cannot be put in an ``<iframe>`` from a geeViz map or any other
    origin -- the frame comes back blank with a console refusal. Opening
    the URL in a tab is the only thing that works, and the viewer needs
    a signed-in Google account with access.

    What this is for: geeViz already knows the study area, the model and
    the timestamps, so it can hand back a URL that lands on the same
    scene rather than making someone re-navigate by hand. The two
    viewers then show the same moment.

    Args:
        center: ``(lon, lat)`` -- geeViz/Earth Engine order -- or an
            ``ee.Geometry`` (its centroid is used, one round trip).
            WeatherLab's own parameter is ``lat,lon``, the other way
            round; that is handled here, because getting it backwards
            puts you silently in the wrong ocean rather than erroring.
        zoom: fractional zoom, as WeatherLab writes it.
        variable: a :data:`VARIABLES` key (``"precipitation"``), a raw
            WeatherLab layer name, or a list of either.
        model: ``"weathernext3"`` by default.
        valid_time, init_time: anything :func:`getForecastData` accepts
            -- ``str``, ``datetime``, ``ee.Date`` or epoch ms. Sent as
            epoch milliseconds, which is what WeatherLab reads.
        cyclone: a storm name, e.g. ``"NORBERT"``.
        cyclone_models: list, e.g. ``["observed", "wn2_blended"]``.
        legend_elements: list of ints for the cyclone legend.
        panel: ``"charts"`` opens the side panel.
        weather, cyclones: force the two layer groups on or off.
            Defaults: weather on when a ``variable`` is given, cyclones
            on when a ``cyclone`` or ``cyclone_models`` is.
        extra: any other query parameters, passed through untouched.
            WeatherLab is not a documented API and its parameter set is
            read off shared links, so this is the escape hatch for one
            that is not modelled here.

    Returns:
        ``str`` -- the full URL.
    """
    import urllib.parse

    params = {}

    def _flag(name, value):
        if value is not None:
            params[name] = "true" if value else "false"

    # ---- weather layers ---------------------------------------------
    layers = []
    if variable is not None:
        wanted = variable if isinstance(variable, (list, tuple)) else [variable]
        for v in wanted:
            entry = VARIABLES.get(v)
            if entry is None:
                layers.append(str(v))          # already a layer name
                continue
            wn = entry.get("weathernext")
            if wn is None:
                raise ValueError(
                    f"{v!r} is not published by WeatherNext, so WeatherLab "
                    f"has no layer for it. Published: "
                    f"{[k for k, e in VARIABLES.items() if e.get('weathernext')]}")
            layers.append(wn[0])

    _flag("weather_enabled", weather if weather is not None else bool(layers))
    if model:
        params["weather_model"] = model
    if layers:
        params["weather_layers"] = ",".join(layers)

    # ---- cyclones ----------------------------------------------------
    want_cyclones = cyclones
    if want_cyclones is None:
        want_cyclones = bool(cyclone or cyclone_models)
    _flag("cyclones_enabled", want_cyclones)
    if cyclone_models:
        params["cyclone_models"] = ",".join(str(m) for m in cyclone_models)
    if legend_elements:
        params["cyclone_legend_elements"] = ",".join(
            str(int(e)) for e in legend_elements)
    if cyclone:
        params["cyclone"] = str(cyclone)

    # ---- time --------------------------------------------------------
    # Epoch milliseconds, the same representation getForecastData works
    # in, so a window used for a geeViz layer can be reused verbatim.
    if init_time is not None:
        params["init_time"] = str(_ms(init_time))
    if valid_time is not None:
        params["valid_time"] = str(_ms(valid_time))

    # ---- view --------------------------------------------------------
    if center is not None:
        lon, lat = _center_lon_lat(center)
        # WeatherLab writes lat,lon -- the reverse of the (lon, lat) this
        # function takes, and of Earth Engine's order generally.
        params["center"] = "%.5f,%.5f" % (lat, lon)
    if zoom is not None:
        params["zoom"] = repr(float(zoom))
    if panel:
        params["panel"] = str(panel)

    if extra:
        params.update({str(k): str(v) for k, v in extra.items()})

    return WEATHERLAB_URL + "?" + urllib.parse.urlencode(params, safe=",")


def _center_lon_lat(center):
    """``(lon, lat)`` out of a pair, a string, or an ``ee.Geometry``."""
    if isinstance(center, str):
        # Accept WeatherLab's own "lat,lon" spelling so a URL can be
        # round-tripped without silently flipping hemispheres.
        lat, lon = [float(x) for x in center.split(",")]
        return lon, lat
    if isinstance(center, (list, tuple)):
        if len(center) != 2:
            raise ValueError(f"center must be (lon, lat); got {center!r}")
        return float(center[0]), float(center[1])
    # ee.Geometry / ee.Feature / ee.ImageCollection -- one round trip.
    coords = ee.Geometry(center).centroid(1).coordinates().getInfo()
    return float(coords[0]), float(coords[1])


#: Common variables per model, with the unit each product actually
#: publishes -- measured, not assumed.
#:
#: Temperature is the trap. GFS and ECMWF NRT both publish CELSIUS in
#: Earth Engine while WeatherNext publishes KELVIN. Measured at Denver
#: for the same hour: 29.46 / 27.46 / 297.40. Charting the three
#: together without normalizing puts one line 273 units off the others,
#: and it reads as a model blow-up rather than a unit mismatch.
#:
#: ``None`` means the model does not publish that variable.
#:
#: GFS does NOT have a stable band list, and it varies along TWO axes.
#:
#: By DATE, at one boundary rather than on a rolling window: bisected
#: against the live collection on 2026-09-23, an image at 2025-01-14
#: carries 9 bands and one at 2025-01-15 carries 22.
#: ``precipitation_rate``, ``dew_point_temperature_2m_above_ground``,
#: ``gust``, ``haines_index`` and ``ventilation_rate`` all arrive in
#: that one change. The names here are correct from 2025-01-15 on, which
#: is what a forecast request asks for; :data:`BAND_AVAILABLE_FROM`
#: turns an older window into a legible error rather than a server one.
#:
#: And by LEAD. A lead-0 analysis is a short image in both eras -- 6
#: bands in 2024, 15 today -- and in particular carries no
#: ``total_precipitation_surface``, because an accumulation over the
#: forecast interval is undefined at the analysis hour rather than zero.
#:
#: So an audit that samples ``.first()``, or the head of the unfiltered
#: collection, reports half this table as broken: it is looking at the
#: oldest image in the archive at lead 0, the shortest one there is.
#: Sample the window AND the lead you mean to use.
#: Bands that entered a collection partway through its record.
#:
#: ``(variable, model) -> (iso_date, advice)``. A request whose window
#: reaches back before ``iso_date`` cannot be served, and the failure is
#: worth catching HERE rather than letting Earth Engine raise it: the
#: server error arrives from inside a ``map()``, names the missing band
#: and whichever ones happen to be present, and says nothing about why
#: or what to ask for instead.
#:
#: The check is a date comparison, so it costs nothing.
#: ``getForecastData`` is otherwise fully lazy -- it builds a
#: server-side collection and makes no round trip at all (measured: 7 ms)
#: -- and a ``bandNames().getInfo()`` to look before leaping would add
#: ~0.8 s to every call to catch a case that is usually absent.
#:
#: Nothing here is substituted automatically. GFS precipitation is the
#: reason: before the boundary it is an ACCUMULATION and after it a
#: RATE -- different physical quantities in different units -- and
#: quietly swapping one for the other yields numbers wrong by whatever
#: the interval happens to be, while looking entirely plausible.
#:
#: Measured by bisecting the live collection on 2026-09-23. Both GFS
#: entries share one boundary because they arrived in one catalog
#: change: an image at 2025-01-14 carries 9 bands, 2025-01-15 carries 22.
BAND_AVAILABLE_FROM = {
    ("precipitation", "gfs"): (
        "2025-01-15",
        "GFS carried no rate band before then. It did carry "
        "'total_precipitation_surface', an accumulation -- but only at "
        "leads past the analysis hour, and this function returns the "
        "shortest lead, so that is not a substitute here. Use a window "
        "from 2025-01-15, or filter NOAA/GFS0P25 directly on "
        "forecast_hours > 0 for the accumulation. 'euro' and "
        "'weathernext' do not reach that far back either."),
    ("dewpoint_2m", "gfs"): (
        "2025-01-15",
        "Before then GFS carried no dewpoint band at all. It did publish "
        "'relative_humidity_2m' and 'specific_humidity_2m'; 'euro' and "
        "'weathernext' carry dewpoint across the whole record."),
}


VARIABLES = {
    "temperature_2m": {
        "euro": ("temperature_2m_sfc", "C"),
        "gfs": ("temperature_2m_above_ground", "C"),
        "weathernext": ("temperature_2m_mean", "K"),
        # The 0.05 deg product is station-head temperature and dewpoint
        # only -- 12 bands, all of them one of those two at six
        # statistics. Registered but unreachable until now: nothing in
        # this table named a band of it, so there was no variable to ask
        # for, and a plain request was rejected for having no wind.
        "weathernext_stations": ("station_head_temperature_2m_mean", "K"),
        "label": "2 m temperature",
    },
    "dewpoint_2m": {
        "euro": ("dewpoint_temperature_2m_sfc", "C"),
        "gfs": ("dew_point_temperature_2m_above_ground", "C"),
        "weathernext": ("dewpoint_temperature_2m_mean", "K"),
        "weathernext_stations": ("station_head_dewpoint_temperature_2m_mean", "K"),
        "label": "2 m dewpoint",
    },
    "relative_humidity_2m": {
        "euro": None,                 # publishes dewpoint, not RH
        "gfs": ("relative_humidity_2m_above_ground", "%"),
        "weathernext": None,
        "label": "2 m relative humidity",
    },
    "specific_humidity_2m": {
        "euro": None,
        "gfs": ("specific_humidity_2m_above_ground", "kg/kg"),
        "weathernext": None,
        "label": "2 m specific humidity",
    },
    # Two different physical quantities under one word, which is why a
    # bare "mm" cannot label this. GFS publishes an instantaneous RATE
    # and WeatherNext a one-hour ACCUMULATION -- numerically the same
    # thing, depth per hour. ECMWF publishes a running total since
    # initialization, which is not.
    "precipitation": {
        # Measured across one ECMWF run: the field climbs monotonically
        # with lead (mean 0 -> 0.0003 -> 0.0007 -> 0.0038 m at 0/3/6/24
        # hours) and is IDENTICALLY ZERO at lead 0. Past windows return
        # shortest-lead analyses, so asking ECMWF for precipitation used
        # to hand back an all-zero image and no warning -- a dry
        # forecast, confidently, everywhere.
        "euro": ("It publishes a running total since initialization, "
                 "which is zero at the analysis lead this returns; ask "
                 "for 'precipitation_accumulated' instead."),
        "gfs": ("precipitation_rate", "kg/m^2/s"),
        "weathernext": ("total_precipitation_1hr_mean", "m/1hr"),
        "label": "Precipitation",
    },
    "precipitation_accumulated": {
        # The same ECMWF band, read as what it actually is: depth since
        # the run started. Useful, just not per-hour, and not
        # comparable to the two above.
        "euro": ("total_precipitation_sfc", "m"),
        # GFS does publish one -- 'total_precipitation_surface', across
        # the whole record -- but ONLY at leads past the analysis hour,
        # and an accumulation at lead 0 is undefined rather than zero.
        # This function returns the SHORTEST lead in the window (see
        # _analyses), which for GFS is lead 0, so the band is absent
        # from every image it would ever select. Measured 2026-09-23:
        # lead 0 carries 6 bands in 2024 and 15 today, neither
        # including it; lead 1+ carries it in both eras.
        "gfs": ("It is published only at leads past the analysis hour, "
                "and this function returns the shortest lead, so the "
                "band is missing from every image it selects. For an "
                "hourly rate ask for 'precipitation' (GFS publishes it "
                "at every lead from 2025-01-15). For the accumulation "
                "itself, filter NOAA/GFS0P25 directly on "
                "forecast_hours > 0."),
        "weathernext": None,
        "label": "Precipitation since forecast start",
    },
    "total_cloud_cover": {
        "euro": None,
        "gfs": ("total_cloud_cover_entire_atmosphere", "%"),
        "weathernext": ("total_cloud_cover_mean", "fraction"),
        "label": "Total cloud cover",
    },
    "mean_sea_level_pressure": {
        "euro": ("mean_sea_level_pressure_sfc", "Pa"),
        "gfs": None,
        "weathernext": ("mean_sea_level_pressure_mean", "Pa"),
        "label": "Mean sea level pressure",
    },
    "sea_surface_temperature": {
        "euro": None,
        "gfs": None,
        "weathernext": ("sea_surface_temperature_mean", "K"),
        "label": "Sea surface temperature",
    },
    "wind_speed_10m": {
        # euro/gfs publish components only -- derive with windImage.
        "euro": None,
        "gfs": None,
        "weathernext": ("wind_speed_10m_mean", "m/s"),
        "label": "10 m wind speed",
    },
}
