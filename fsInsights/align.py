"""Putting LCMS and FIA side by side, without pretending they agree.

The two answer complementary halves of one question over overlapping
geography, and almost nobody joins them because the APIs look nothing
alike. That is the opportunity. The hazard is that joining them invites
a comparison that is easy to make and easy to get wrong.

======================  ===========================  ========================
Aspect                  LCMS                         FIA
======================  ===========================  ========================
Nature                  Wall-to-wall classified map  Probability sample
Resolution              30 m, annual, 1985-2025      Plots, multi-year panels
Answers                 What changed, and where      What is there, +/- error
Uncertainty             Map accuracy                 Design-based std. error
======================  ===========================  ========================

**Map-derived area is not a design-based area estimate.** Comparing them
conflates map accuracy with sampling error, and the two can differ
substantially without either being wrong — different definitions of
"forest", different minimum mapping units, different reference dates.

So nothing here returns a blended number. Every row carries the
``source`` and ``estimator`` that produced it, and the comparison
helpers report a difference *alongside* the caveat rather than instead
of it. The goal is to make the comparison easy to look at and hard to
misread.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .fia import estimate
from .lcms import lcms_classes, lcms_summary

logger = logging.getLogger(__name__)

#: LCMS land-cover classes that carry tree cover. Used to build a
#: "treed area" figure that is *comparable in spirit* to FIA forest
#: land — not equal to it. FIA's definition is about land use and
#: stocking potential, not present canopy, so a recently harvested
#: stand stays forest land in FIA while LCMS may map it as grass or
#: barren in the same year. That divergence is real signal, and it is
#: exactly what a naive join would hide.
#:
#: The ``(AK Only)`` suffix is part of the real class name, not a
#: comment. Writing it without the suffix looks correct, matches nothing,
#: and silently drops the class — invisible in CONUS where it never
#: occurs, and an understatement of tree area everywhere in Alaska. That
#: is why :func:`lcms_tree_area` validates these names against the API's
#: class list rather than trusting this tuple.
TREE_CLASSES = (
    "Trees",
    "Tall Shrubs & Trees Mix (AK Only)",
    "Shrubs & Trees Mix",
    "Grass/Forb/Herb & Trees Mix",
    "Barren & Trees Mix",
)

#: Why LCMS and FIA can legitimately disagree. Module-level on purpose:
#: these are static facts about the two datasets, not properties of any
#: one comparison, so they must be readable even when the FIA half of a
#: comparison could not be fetched. Gating them behind a successful call
#: meant the caveats vanished exactly when a reader had one number and
#: might quote it alone.
COMPARISON_CAVEATS = (
    "LCMS area is map-derived; FIA area is a design-based estimate. The "
    "difference mixes map accuracy with sampling error and is not an "
    "error term for either.",
    "FIA 'forest land' is a land-use definition based on stocking and "
    "potential; LCMS land cover describes present canopy. A recently "
    "harvested stand stays forest land in FIA while LCMS may map it as "
    "grass or barren the same year.",
    "Reference periods differ: an FIA evaluation spans several years of "
    "panels, while an LCMS year is a single annual map.",
    "Minimum mapping unit and edge handling differ, which matters most "
    "in fragmented landscapes.",
)


#: FIA attribute 2 — "Area of forest land, in acres".
FOREST_AREA_SNUM = 2


def _warn_unknown_classes(classes, release: str = "") -> list:
    """Warn about requested class names that are not real LCMS classes.

    The distinction that matters: a class *absent from this county* is
    normal and silent, while a class *that does not exist in the product
    at all* is a typo or a rename and must be loud. Only the second is
    reported here.

    Without this, a wrong name is a silent undercount. ``'Tall Shrubs &
    Trees Mix'`` looks right but the real class carries an ``(AK Only)``
    suffix — matching nothing, invisible across CONUS where the class
    never occurs, and quietly understating tree area throughout Alaska.
    Sums that are wrong but plausible are the worst kind.

    Returns the unknown names, so callers can assert on them in tests.
    """
    try:
        official = set(lcms_classes("Land_Cover", release)["class_name"])
    except Exception:
        # Never let a validation nicety break the actual call.
        logger.debug("fsInsights.align: could not verify class names",
                     exc_info=True)
        return []

    unknown = [c for c in classes if c not in official]
    if unknown:
        logger.warning(
            "fsInsights.align: %d requested class name(s) do not exist in "
            "LCMS Land_Cover and will contribute ZERO acres: %s. Real "
            "classes: %s",
            len(unknown), unknown, sorted(official),
        )
    return unknown


def lcms_tree_area(state: str = "", county: str = "", *,
                   region: str = "", forest: str = "", district: str = "",
                   year: Optional[int] = None,
                   tree_classes: Optional[tuple] = None,
                   release: str = "") -> "Any":
    """LCMS area in tree-bearing land cover classes, by year.

    Args:
        tree_classes: Override which classes count as treed. The default
            includes the mixed classes, which matters: excluding them
            understates treed area in exactly the transitional stands
            where LCMS and FIA are most likely to disagree.

    Returns:
        ``pandas.DataFrame`` with ``year``, ``acres``, ``classes_used``,
        ``source``, ``estimator``.
    """
    classes = tuple(tree_classes or TREE_CLASSES)
    _warn_unknown_classes(classes, release)

    df = lcms_summary("Land_Cover", state=state, county=county,
                      region=region, forest=forest, district=district,
                      year=year, release=release)
    if not hasattr(df, "empty"):
        return df

    treed = df[df["class_name"].isin(classes)]
    if treed.empty:
        logger.warning(
            "fsInsights.align: no LCMS classes matched %s - present here: %s",
            classes, sorted(df["class_name"].unique()),
        )

    out = (treed.groupby("year", as_index=False)["acres"].sum()
           if not treed.empty else treed.assign(acres=0.0))
    out["classes_used"] = ", ".join(classes)
    out["source"] = "lcms"
    out["estimator"] = "wall-to-wall map (map accuracy)"
    return out


def fia_forest_area(wc: int, *, rselected: str = "",
                    snum: int = FOREST_AREA_SNUM, **kwargs) -> "Any":
    """FIA forest-land area with its sampling error.

    Thin wrapper over :func:`~geeViz.fsInsights.estimate` that stamps the
    estimator label, so a frame from here and a frame from
    :func:`lcms_tree_area` can be concatenated without losing track of
    which is which.
    """
    df = estimate(wc, snum, rselected=rselected, **kwargs)
    if hasattr(df, "assign"):
        df = df.assign(source="fia",
                       estimator="probability sample (design-based SE)")
    return df


def _select_county(fi, county: str):
    """Narrow a county-grouped FIA frame to one county.

    FIA county labels look like ``` `41013 4113 OR Crook ``` — a
    backtick-prefixed code, the state/county numeric, the state
    abbreviation, then the name — so matching is a case-insensitive
    substring test on the name rather than equality.

    The county's aggregate row is relabelled ``Total`` so the caller
    keeps ONE extraction path: without a county the state total already
    arrives as ``row == "Total"``, and with one this makes the county
    total arrive the same way. Returns the frame unchanged when the name
    matches nothing, which keeps a typo visible as "no FIA half" rather
    than silently substituting the state.
    """
    if not hasattr(fi, "empty") or getattr(fi, "empty", True):
        return fi
    name = str(county).strip().lower()
    if not name:
        return fi
    hit = fi[fi["row"].astype(str).str.lower().str.contains(name, na=False)]
    if not len(hit):
        logger.warning(
            "fsInsights.compare_area: county %r matched no FIA county row; "
            "returning the frame unfiltered rather than silently comparing "
            "against the whole state", county,
        )
        return hit  # empty -> caller reports "not enough data", not a wrong number
    # Prefer the marginal (column == 'Total'); fall back to the sole row
    # when the request had no column grouping.
    marg = hit[hit["column"].astype(str) == "Total"]
    pick = marg if len(marg) else hit
    return pick.assign(row="Total")


def compare_area(*, wc: int, state: str = "", county: str = "",
                 year: Optional[int] = None,
                 tree_classes: Optional[tuple] = None,
                 release: str = "") -> Dict[str, Any]:
    """Put an LCMS treed area and an FIA forest-land estimate side by side.

    Returns a dict rather than a single frame, because the two halves are
    not rows of one table — they are two different estimators of two
    related-but-distinct quantities, and stacking them would imply a
    comparability that does not exist.

    Keys:

    * ``lcms`` — per-year treed area frame.
    * ``fia`` — forest-land estimate with ``se_pct`` and ``plots``.
    * ``comparison`` — a small dict with both figures, their absolute
      and percentage difference, and ``caveats``, a list of the reasons
      they can legitimately disagree.

    The difference is offered as an observation, never as an error term.
    A 15% gap between these does not mean either is 15% wrong.
    """
    lc = lcms_tree_area(state=state, county=county, year=year,
                        tree_classes=tree_classes, release=release)

    # Both halves must cover the SAME footprint. ``county`` was being
    # applied to the LCMS side only, so a county request compared that
    # county's mapped acres against the WHOLE STATE's FIA estimate --
    # Crook County, OR came out as 613,203 vs 29,754,801 acres, reported
    # as a confident "-97.9% difference". Nothing errored; the number was
    # simply meaningless.
    #
    # It stayed hidden because the FIA half was returning nothing at all
    # (upstream JSON was broken), so the comparison bailed out with "Not
    # enough data to compare" instead of printing a wrong answer. Fixing
    # FIA is what exposed it.
    #
    # Group by county and keep the requested one; without a county the
    # state-level total is the right footprint and needs no grouping.
    if county:
        fi = fia_forest_area(wc, rselected="County code and name")
        fi = _select_county(fi, county)
    else:
        fi = fia_forest_area(wc)

    lcms_acres = None
    try:
        lcms_acres = float(lc["acres"].iloc[-1]) if len(lc) else None
    except Exception:
        pass

    fia_acres = fia_se = fia_plots = None
    try:
        tot = fi[(fi["row"] == "Total")]
        if len(tot):
            fia_acres = float(tot["estimate"].iloc[0])
            fia_se = float(tot["se_pct"].iloc[0])
            fia_plots = int(tot["plots"].iloc[0])
    except Exception:
        pass

    diff = pct = None
    if lcms_acres is not None and fia_acres:
        diff = lcms_acres - fia_acres
        pct = 100.0 * diff / fia_acres

    return {
        "lcms": lc,
        "fia": fi,
        "comparison": {
            "lcms_treed_acres": lcms_acres,
            "fia_forest_acres": fia_acres,
            "fia_se_pct": fia_se,
            "fia_plots": fia_plots,
            "difference_acres": diff,
            "difference_pct_of_fia": pct,
            "caveats": list(COMPARISON_CAVEATS),
        },
    }


def summarize_comparison(result: Dict[str, Any]) -> str:
    """One readable paragraph from :func:`compare_area`, caveats included.

    Written to be pasted into a report. The caveat is part of the
    sentence rather than a footnote, because a number this easy to
    quote is a number that travels without its footnotes.
    """
    c = result.get("comparison", {})
    lc, fi = c.get("lcms_treed_acres"), c.get("fia_forest_acres")
    if lc is None or fi is None:
        return "Not enough data to compare (one of the two sources returned nothing)."

    se, plots = c.get("fia_se_pct"), c.get("fia_plots")
    pct = c.get("difference_pct_of_fia")
    return (
        f"LCMS maps {lc:,.0f} acres of tree-bearing land cover. FIA "
        f"estimates {fi:,.0f} acres of forest land"
        + (f" (SE {se:.1f}%, {plots:,} plots)" if se is not None else "")
        + f", a difference of {pct:+.1f}%. These are different estimators "
        f"of related but distinct quantities - map-derived cover versus a "
        f"design-based land-use estimate - so the gap is not an error in "
        f"either. FIA counts recently harvested stands as forest land; "
        f"LCMS maps present canopy."
    )
