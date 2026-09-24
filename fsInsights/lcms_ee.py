"""Earth Engine access to the LCMS products.

The LCMS API serves 3,643 *precomputed* summary areas and nothing else —
``bbox``, ``geojson`` and ``geometry`` are rejected, and ``POST`` returns
403. So an arbitrary polygon has to be computed rather than requested,
and the same products are published as Earth Engine assets.

This module is the bridge. It is imported lazily by
:func:`geeViz.fsInsights.lcms.lcms_summary`, so the API-only path keeps
working on a machine with no Earth Engine credentials — which is the
normal case for the MCP tool and for anyone who just wants a county
summary.

Convenient alignment worth knowing: the EE **band names are the same
strings as the API product names** (``Change``, ``Land_Cover``,
``Land_Use``), and the asset version tracks the API release (``2025-11``
on both). So a product name is portable across both backends without a
translation table.

For *display*, prefer geeViz's built-in thematic handling::

    Map.addLayer(lcms_ee_collection("Land_Cover").mosaic(),
                 {"autoViz": True}, "LCMS Land Cover")

The assets carry ``<Product>_class_names`` / ``_class_values`` /
``_class_palette`` properties, which ``autoViz`` reads directly.
:func:`geeViz.fsInsights.lcms.lcms_vis_params` exists for the cases
``autoViz`` cannot cover — charting API results, or building a legend
outside geeViz.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

#: Current published collection. Release-pinned on purpose: resolving
#: "latest" at call time means an old analysis silently changes answers
#: when a new version lands.
_CURRENT = "projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11"

#: Earlier releases, for reproducing a prior analysis. Newer releases
#: moved out of the ``USFS/GTAC`` namespace, so this is a lookup rather
#: than a formatted path.
#:
#: Worth knowing before pinning: **study-area coverage is not
#: monotonic.** ``2024-10`` covers CONUS, AK, HAWAII and PRUSVI, while
#: the newer ``2025-11`` covers only CONUS and AK. Work in Hawaii or
#: Puerto Rico has to pin an OLDER release — the opposite of the usual
#: advice, and easy to get wrong by reaching for "latest".
#:
#: ``2025-6`` is absent on purpose: it is a tree-canopy release with no
#: Change / Land_Cover / Land_Use products.
_BY_RELEASE = {
    "2025-11": _CURRENT,
    "2024-10": "USFS/GTAC/LCMS/v2024-10",
    "2023-9": "USFS/GTAC/LCMS/v2023-9",
    "2022-8": "USFS/GTAC/LCMS/v2022-8",
    "2021-7": "USFS/GTAC/LCMS/v2021-7",
    "2020-5": "USFS/GTAC/LCMS/v2020-5",
    "2020-6": "USFS/GTAC/LCMS/v2020-6",
}

#: Study areas per release, for the coverage question above. Only the
#: releases whose coverage differs from the current one are listed.
RELEASE_STUDY_AREAS = {
    "2025-11": ("CONUS", "AK"),
    "2025-6":  ("CONUS", "AK"),
    "2024-10": ("CONUS", "AK", "HAWAII", "PRUSVI"),
    "2023-9":  ("CONUS", "SEAK", "HAWAII", "PRUSVI"),
    "2022-8":  ("CONUS", "SEAK", "PRUSVI"),
}

#: Thematic bands carried by the LCMS product releases. Everything else
#: in those assets is a per-class raw probability or the QA bitmask,
#: none of which belong in a class-area summary.
#:
#: Note this is NOT every product the LCMS *API* publishes. Release
#: ``2025-6`` is a tree-canopy release carrying only
#: ``NLCD_Percent_Tree_Canopy_Cover``, which is continuous rather than
#: thematic and lives in a different Earth Engine collection — it is
#: served by the API path, not by this module.
PRODUCTS = ("Change", "Land_Cover", "Land_Use")


def lcms_asset_id(release: str = "") -> str:
    """Asset id for a release. Defaults to the current one."""
    if not release or release == "latest":
        return _CURRENT
    try:
        return _BY_RELEASE[release]
    except KeyError:
        raise ValueError(
            f"no Earth Engine asset known for LCMS release {release!r}; "
            f"available: {sorted(_BY_RELEASE)}"
        ) from None


def lcms_ee_collection(product: str, release: str = "",
                       study_area: Optional[str] = None):
    """An ``ee.ImageCollection`` of one LCMS product, one image per year.

    Args:
        product: ``"Change"``, ``"Land_Cover"`` or ``"Land_Use"``.
        release: Release version; defaults to current.
        study_area: Restrict to one study area (e.g. ``"CONUS"``,
            ``"AK"``, ``"PRUSVI"``). Leave unset to keep all of them —
            they do not overlap, so a geometry naturally selects the
            right one and a reduction over the union is correct.

    Returns:
        ``ee.ImageCollection`` where each image has a single band named
        after the product and a ``year`` property.
    """
    import ee

    if product not in PRODUCTS:
        raise ValueError(
            f"unknown LCMS product {product!r}; expected one of {PRODUCTS}"
        )

    coll = ee.ImageCollection(lcms_asset_id(release))
    if study_area:
        coll = coll.filter(ee.Filter.eq("study_area", study_area))

    # Select only the thematic band. The assets also carry per-class raw
    # probability bands and a QA bitmask; carrying them into a grouped
    # area reduction would be wasted transfer at best and a wrong answer
    # at worst.
    return coll.select([product])


def lcms_class_properties(product: str, release: str = "") -> dict:
    """Class names, values, and palette straight off the asset.

    A second source of truth for the class table, independent of the
    API. Useful when Earth Engine is reachable but the API is not, and
    as a cross-check that the two backends agree about what the pixel
    values mean — if they ever disagree, that is worth knowing loudly
    rather than discovering through a mislabeled map.
    """
    import ee

    img = ee.Image(ee.ImageCollection(lcms_asset_id(release)).first())
    props = img.toDictionary().getInfo() or {}

    def _listify(v):
        # These are stored as comma-separated strings on some releases
        # and as real lists on others.
        if isinstance(v, str):
            return [p.strip() for p in v.split(",") if p.strip()]
        return list(v or [])

    out = {
        "names": _listify(props.get(f"{product}_class_names")),
        "values": _listify(props.get(f"{product}_class_values")),
        "palette": _listify(props.get(f"{product}_class_palette")),
    }

    # Splitting NAMES on commas is not always safe, and this is the
    # "loudly" the docstring promises.
    #
    # ``values`` and ``palette`` never contain a comma, so splitting them
    # is exact. A class NAME can: LCMS 2025-11 publishes
    # ``Change_class_names`` containing "Insect, Disease, or Drought
    # Stress", so a comma split yields 18 parts for 16 classes. Nothing
    # errors -- the names simply shift against the values from that entry
    # on, and every class after it gets labelled as its neighbour. That is
    # exactly the mislabeled map this function exists to prevent, and it
    # cannot be undone from the string alone: which commas are separators
    # and which are part of a name is not recoverable.
    #
    # So say so, and flag it, rather than hand back a confident mapping
    # that is wrong in the middle.
    n_values = len(out["values"])
    if n_values and len(out["names"]) != n_values:
        out["names_unreliable"] = True
        logger.warning(
            "lcms_class_properties: %s on %s has %d class values but the "
            "class_names string splits into %d parts, so at least one name "
            "contains a comma and names cannot be matched to values. "
            "Treat 'names' as unreliable here and label from 'values' "
            "instead.",
            product, lcms_asset_id(release), n_values, len(out["names"]),
        )
    else:
        out["names_unreliable"] = False
    return out
