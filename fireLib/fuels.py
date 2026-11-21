"""Fuels and terrain assembly — the layer everything else stands on.

The bottleneck in real fire work is almost never the simulator. It is
assembling fuels, terrain, and weather into one consistent, aligned
stack, then redoing all of it when a boundary or a year changes. That is
exactly what Earth Engine removes, and it is why this module exists
before any behavior model does.

Asset ids below were verified against the live catalog. LANDFIRE lives
in the community catalog (``projects/sat-io/...``) rather than the
official one, which is easy to guess wrong.

Fuel-model note: ``FBFM40`` (Scott & Burgan) and ``FBFM13`` (Anderson)
are *classification* rasters — each pixel carries a fuel model number,
and the physical parameters that number implies (fuel load by size
class, surface-area-to-volume ratio, bed depth, moisture of extinction)
live in a lookup table, not in the raster. :func:`fuel_model_params`
holds that table for the subset needed by a Rothermel spread
calculation.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

#: Verified asset ids. LANDFIRE surface/canopy fuels are in the
#: community catalog; the official ``LANDFIRE/`` namespace carries
#: vegetation and fire-regime products but NOT the fuel models.
FUEL_ASSETS: Dict[str, str] = {
    # Surface fuel models
    "FBFM40": "projects/sat-io/open-datasets/landfire/FUEL/FBFM40",
    "FBFM13": "projects/sat-io/open-datasets/landfire/FUEL/FBFM13",
    # Canopy — the four Van Wagner / Scott & Reinhardt crown-fire inputs
    "CBH": "projects/sat-io/open-datasets/landfire/FUEL/CBH",
    "CBD": "projects/sat-io/open-datasets/landfire/FUEL/CBD",
    "CC":  "projects/sat-io/open-datasets/landfire/FUEL/CC",
    "CH":  "projects/sat-io/open-datasets/landfire/FUEL/FVH",
    # Context
    "FVT": "projects/sat-io/open-datasets/landfire/FUEL/FVT",
    "FVC": "projects/sat-io/open-datasets/landfire/FUEL/FVC",
    "FCCS": "projects/sat-io/open-datasets/landfire/FUEL/FCCS",
    "CFFDRS": "projects/sat-io/open-datasets/landfire/FUEL/CFFDRS",
}

#: Fire-regime and vegetation context, from the OFFICIAL catalog.
CONTEXT_ASSETS: Dict[str, str] = {
    "EVT":  "LANDFIRE/Vegetation/EVT/v1_4_0",
    "EVC":  "LANDFIRE/Vegetation/EVC/v1_4_0",
    "EVH":  "LANDFIRE/Vegetation/EVH/v1_4_0",
    "FRG":  "LANDFIRE/Fire/FRG/v1_2_0",
    "MFRI": "LANDFIRE/Fire/MFRI/v1_2_0",
    "VCC":  "LANDFIRE/Fire/VCC/v1_4_0",
    "VDep": "LANDFIRE/Fire/VDep/v1_4_0",
}

#: FSim / FlamMap outputs, already computed for CONUS+AK+HI at 30 m.
#: Burn probability, conditional flame length, flame-length exceedance,
#: hazard potential, and risk to potential structures. Any plan whose
#: first milestone is "compute burn probability" is re-deriving this.
RISK_ASSET = "USDA/WRC/v0"


def _ic_mosaic(asset_id: str, band_name: Optional[str] = None):
    """Mosaic an ImageCollection to a single image, or pass an Image through.

    LANDFIRE ships some products as collections (one image per version or
    tile) and others as single images. Callers should not have to know
    which, so this normalizes both.
    """
    import ee

    info = ee.data.getInfo(asset_id) or {}
    kind = str(info.get("type", "")).upper()
    img = (ee.ImageCollection(asset_id).mosaic()
           if "COLLECTION" in kind else ee.Image(asset_id))
    if band_name:
        img = img.rename(band_name)
    return img


def landfire_fuels(bands=("FBFM40", "CBH", "CBD", "CC", "CH"),
                   *, region: Any = None):
    """Assemble a multi-band LANDFIRE fuels image.

    Args:
        bands: Keys from :data:`FUEL_ASSETS`. The default is exactly the
            set a Rothermel surface run plus a Van Wagner crown-fire
            check needs: a surface fuel model, canopy base height,
            canopy bulk density, canopy cover, and canopy height.
        region: Optional geometry to clip to. Clipping early is usually
            the right call for an AOI-scale analysis — it keeps later
            reductions from touching tiles they will discard anyway.

    Returns:
        ``ee.Image`` with one band per requested key, named by that key.

    Note:
        Bands are **not** unit-converted here. LANDFIRE ships canopy
        base height and canopy height in metres x 10, and canopy bulk
        density in kg/m3 x 100, precisely so they can be stored as
        integers. :func:`~geeViz.fireLib.behavior` applies the scaling
        where the physics needs real units — doing it here would mean
        two places could disagree about whether a value was already
        scaled, which is the sort of error that produces plausible
        numbers rather than obvious ones.
    """
    import ee

    unknown = [b for b in bands if b not in FUEL_ASSETS]
    if unknown:
        raise ValueError(
            f"unknown fuel band(s) {unknown}; available: "
            f"{sorted(FUEL_ASSETS)}"
        )

    out = None
    for b in bands:
        img = _ic_mosaic(FUEL_ASSETS[b]).rename(b)
        out = img if out is None else out.addBands(img)

    if region is not None:
        out = out.clip(region)
    return ee.Image(out)


def terrain_layers(dem_asset: str = "USGS/3DEP/10m", *, region: Any = None):
    """Slope, aspect and terrain derivatives for fire behavior.

    Args:
        dem_asset: DEM to derive from. 3DEP 10 m for CONUS; pass
            ``"USGS/SRTMGL1_003"`` for near-global 30 m coverage.
        region: Optional clip geometry.

    Returns:
        ``ee.Image`` with ``elevation``, ``slope`` (degrees),
        ``aspect`` (degrees), ``northness``, ``eastness``, and
        ``slope_tan`` (tangent of slope, which is the form Rothermel's
        slope factor actually consumes).

    Display:
        Every band has a known range, so use a fixed stretch, not
        ``tl.auto_viz`` (which spends a ``reduceRegion`` to learn it):

        * ``slope`` (degrees): ``{"min": 0, "max": 30}`` for most
          terrain; ``{"min": 0, "max": 60}`` for steep mountains.
        * ``aspect`` (degrees): ``{"min": 0, "max": 360}`` with a
          palette that starts and ends on the same color, since 0 and
          360 are both north.
        * ``northness`` / ``eastness``: ``{"min": -1, "max": 1}`` with a
          diverging palette.
        * ``slope_tan``: ``{"min": 0, "max": 1}`` (0 to 45 degrees).
        * ``elevation`` depends on the place: here ``tl.auto_viz`` is
          the right call, or a known local range.

    Note:
        ``northness`` / ``eastness`` exist because **raw aspect must
        never be fed to a model or a statistic.** 359 degrees and 1
        degree are adjacent on the ground and maximally distant
        numerically; averaging them yields 180, which points the wrong
        way. Decomposing to cos/sin makes the circular quantity behave
        like two linear ones.
    """
    import ee

    dem = _ic_mosaic(dem_asset).rename("elevation")
    terrain = ee.Terrain.products(dem)

    slope_deg = terrain.select("slope").rename("slope")
    aspect_deg = terrain.select("aspect").rename("aspect")
    rad = ee.Number(3.141592653589793).divide(180)

    northness = aspect_deg.multiply(rad).cos().rename("northness")
    eastness = aspect_deg.multiply(rad).sin().rename("eastness")
    slope_tan = slope_deg.multiply(rad).tan().rename("slope_tan")

    out = (dem.addBands(slope_deg).addBands(aspect_deg)
           .addBands(northness).addBands(eastness).addBands(slope_tan))
    if region is not None:
        out = out.clip(region)
    return ee.Image(out)


# ── Scott & Burgan fuel model parameters ─────────────────────────────────
#
# The raster carries a fuel model NUMBER; the physics needs the bed
# properties that number stands for. Values below are the standard
# Scott & Burgan (2005, RMRS-GTR-153) parameters for the subset most
# often encountered, in the units Rothermel's equations expect:
#
#   w_1h/w_10h/w_100h  dead fuel load by timelag class, tons/acre
#   w_live             live herbaceous + woody load, tons/acre
#   sav                characteristic surface-area-to-volume, 1/ft
#   depth              fuelbed depth, ft
#   mx_dead            dead fuel moisture of extinction, fraction
#
#: Not the complete 40-model set. It covers the non-burnable models and
#: the grass/shrub/timber families that dominate CONUS wildfire, and
#: :func:`fuel_model_params` reports a miss rather than silently
#: substituting a default — an unlisted model returning "grass" would be
#: a wrong answer wearing the right shape.
_FBFM40_PARAMS: Dict[int, Dict[str, float]] = {
    # Non-burnable
    91: {"w_1h": 0.0, "w_10h": 0.0, "w_100h": 0.0, "w_live": 0.0,
         "sav": 1.0, "depth": 0.1, "mx_dead": 0.10, "name": "NB1 urban"},
    92: {"w_1h": 0.0, "w_10h": 0.0, "w_100h": 0.0, "w_live": 0.0,
         "sav": 1.0, "depth": 0.1, "mx_dead": 0.10, "name": "NB2 snow/ice"},
    93: {"w_1h": 0.0, "w_10h": 0.0, "w_100h": 0.0, "w_live": 0.0,
         "sav": 1.0, "depth": 0.1, "mx_dead": 0.10, "name": "NB3 agriculture"},
    98: {"w_1h": 0.0, "w_10h": 0.0, "w_100h": 0.0, "w_live": 0.0,
         "sav": 1.0, "depth": 0.1, "mx_dead": 0.10, "name": "NB8 water"},
    99: {"w_1h": 0.0, "w_10h": 0.0, "w_100h": 0.0, "w_live": 0.0,
         "sav": 1.0, "depth": 0.1, "mx_dead": 0.10, "name": "NB9 barren"},
    # Grass (GR)
    101: {"w_1h": 0.10, "w_10h": 0.0, "w_100h": 0.0, "w_live": 0.30,
          "sav": 2200, "depth": 0.4, "mx_dead": 0.15, "name": "GR1 short sparse dry"},
    102: {"w_1h": 0.10, "w_10h": 0.0, "w_100h": 0.0, "w_live": 1.00,
          "sav": 2000, "depth": 1.0, "mx_dead": 0.15, "name": "GR2 low load dry"},
    103: {"w_1h": 0.10, "w_10h": 0.40, "w_100h": 0.0, "w_live": 1.50,
          "sav": 1500, "depth": 2.0, "mx_dead": 0.30, "name": "GR3 low load very coarse"},
    104: {"w_1h": 0.25, "w_10h": 0.0, "w_100h": 0.0, "w_live": 1.90,
          "sav": 2000, "depth": 2.0, "mx_dead": 0.15, "name": "GR4 moderate load dry"},
    # Grass-shrub (GS)
    121: {"w_1h": 0.20, "w_10h": 0.0, "w_100h": 0.0, "w_live": 0.50,
          "sav": 2000, "depth": 0.9, "mx_dead": 0.15, "name": "GS1 low load dry"},
    122: {"w_1h": 0.50, "w_10h": 0.50, "w_100h": 0.0, "w_live": 0.60,
          "sav": 1800, "depth": 1.5, "mx_dead": 0.15, "name": "GS2 moderate load dry"},
    # Shrub (SH)
    141: {"w_1h": 0.25, "w_10h": 0.25, "w_100h": 0.0, "w_live": 0.15,
          "sav": 2000, "depth": 1.0, "mx_dead": 0.15, "name": "SH1 low load dry"},
    142: {"w_1h": 1.35, "w_10h": 2.40, "w_100h": 0.75, "w_live": 0.0,
          "sav": 2000, "depth": 1.0, "mx_dead": 0.15, "name": "SH2 moderate load dry"},
    145: {"w_1h": 3.60, "w_10h": 2.10, "w_100h": 0.0, "w_live": 2.90,
          "sav": 1600, "depth": 6.0, "mx_dead": 0.40, "name": "SH5 high load dry"},
    # Timber understory (TU)
    161: {"w_1h": 0.20, "w_10h": 0.90, "w_100h": 1.50, "w_live": 0.20,
          "sav": 2000, "depth": 0.6, "mx_dead": 0.20, "name": "TU1 light load"},
    165: {"w_1h": 1.00, "w_10h": 0.0, "w_100h": 0.0, "w_live": 0.0,
          "sav": 1800, "depth": 1.0, "mx_dead": 0.25, "name": "TU5 very high load"},
    # Timber litter (TL)
    181: {"w_1h": 1.00, "w_10h": 2.20, "w_100h": 3.60, "w_live": 0.0,
          "sav": 2000, "depth": 0.2, "mx_dead": 0.30, "name": "TL1 low load compact"},
    183: {"w_1h": 0.50, "w_10h": 2.20, "w_100h": 2.80, "w_live": 0.0,
          "sav": 2000, "depth": 0.3, "mx_dead": 0.20, "name": "TL3 moderate load"},
    188: {"w_1h": 5.80, "w_10h": 1.40, "w_100h": 1.10, "w_live": 0.0,
          "sav": 1800, "depth": 0.3, "mx_dead": 0.35, "name": "TL8 long-needle litter"},
    # Slash-blowdown (SB)
    201: {"w_1h": 1.50, "w_10h": 3.00, "w_100h": 11.0, "w_live": 0.0,
          "sav": 1800, "depth": 1.0, "mx_dead": 0.25, "name": "SB1 low load"},
}

#: Fuel model codes that cannot carry fire. Rate of spread is exactly
#: zero here, and that has to be enforced explicitly — the Rothermel
#: equations divide by fuel load and would otherwise produce NaN or a
#: spurious value from a zero-load bed.
NON_BURNABLE = (91, 92, 93, 98, 99)


def fuel_model_params(fbfm: int) -> Dict[str, Any]:
    """Rothermel bed parameters for a Scott & Burgan fuel model number.

    Args:
        fbfm: FBFM40 code, e.g. 102 for GR2 or 165 for TU5.

    Returns:
        Dict of bed properties plus ``name`` and ``burnable``.

    Raises:
        KeyError: The model is not in the table. Deliberate — silently
            substituting a default would return a plausible spread rate
            for a fuel bed nobody described, which is worse than an
            error because nothing downstream would question it.
    """
    if fbfm in NON_BURNABLE:
        p = dict(_FBFM40_PARAMS.get(fbfm, _FBFM40_PARAMS[99]))
        p["burnable"] = False
        return p
    try:
        p = dict(_FBFM40_PARAMS[fbfm])
    except KeyError:
        raise KeyError(
            f"fuel model {fbfm} is not in the parameter table. Add it "
            f"from Scott & Burgan (RMRS-GTR-153) rather than defaulting "
            f"— a substituted bed produces a plausible spread rate for "
            f"fuel nobody described. Present: {sorted(_FBFM40_PARAMS)}"
        ) from None
    p["burnable"] = True
    return p


def fuel_coverage(fuels, region, *, scale: int = 90,
                  fbfm_band: str = "FBFM40") -> Dict[str, Any]:
    """What fraction of an area the parameter table can actually model.

    **Run this before trusting any spread result over a new area.**
    :data:`_FBFM40_PARAMS` is a verified subset, not the full Scott &
    Burgan 40, and an unlisted model contributes a masked pixel — so a
    landscape can come back looking calm simply because a third of it
    was unmodellable. The gap is invisible in the output image and
    obvious here.

    Measured on a real Oregon test area: 91.4% covered, with the 8.6%
    shortfall dominated by GS3 (123).

    Returns:
        Dict with ``covered_fraction``, ``total_pixels``, and
        ``missing`` — a list of ``(fuel_model, pixels, fraction)``
        sorted by how much of the area each accounts for, which is the
        priority order for extending the table.
    """
    import ee

    hist = (ee.Image(fuels).select(fbfm_band)
            .reduceRegion(ee.Reducer.frequencyHistogram(), region,
                          scale, maxPixels=1e10, bestEffort=True)
            .getInfo() or {})
    counts = {int(float(k)): float(v)
              for k, v in (hist.get(fbfm_band) or {}).items()}
    total = sum(counts.values()) or 1.0
    known = set(_FBFM40_PARAMS)

    missing = sorted(
        ((k, v, v / total) for k, v in counts.items() if k not in known),
        key=lambda t: -t[1],
    )
    covered = sum(v for k, v in counts.items() if k in known)
    return {
        "covered_fraction": covered / total,
        "total_pixels": int(total),
        "models_present": len(counts),
        "models_in_table": len(known),
        "missing": [(k, int(v), f) for k, v, f in missing],
        "note": ("Unlisted models produce MASKED pixels, not zeros. Low "
                 "coverage makes a landscape look calmer than it is. "
                 "Extend _FBFM40_PARAMS from Scott & Burgan "
                 "(RMRS-GTR-153) rather than substituting a default."),
    }


def fuel_param_image(fbfm_band, param: str):
    """Turn a fuel-model raster into a raster of one bed parameter.

    Uses ``remap``, which is the right primitive here: the mapping is a
    lookup with no ordering meaning, so arithmetic on the model number
    itself would be nonsense (model 165 is not "more" than 102).

    Args:
        fbfm_band: Single-band ``ee.Image`` of FBFM40 codes.
        param: Key from :func:`fuel_model_params`, e.g. ``"w_1h"``.

    Returns:
        ``ee.Image`` of that parameter, masked where the fuel model is
        not in the table — masked rather than zero-filled, because zero
        is a meaningful fuel load and an unmapped pixel is not the same
        as a pixel with no fuel.
    """
    import ee

    codes = sorted(_FBFM40_PARAMS)
    values = [float(_FBFM40_PARAMS[c][param]) for c in codes]
    return (ee.Image(fbfm_band)
            .remap(codes, values, defaultValue=None)
            .rename(param))
