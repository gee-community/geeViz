"""Forest Service FIA and LCMS data: now :mod:`georest.usfs`.

The FIA (Forest Inventory and Analysis) and LCMS (Landscape Change
Monitoring System) clients that lived here moved to georest, RedCastle's
library of geospatial REST clients, in georest 0.5.0. This package is
the front door that keeps the geeViz names working: every function, the
submodules (``geeViz.fsInsights.fia`` is ``georest.usfs.fia``, the same
module object) and the errors (``FSInsightsError`` is
``georest.usfs.USFSError``). New code can import georest directly::

    from georest.usfs import fia, lcms
    fia.estimate(wc=412022, snum=2, rselected="County code and name")
    lcms.lcms_summary(state="Oregon", county="Crook")

Quick start, through geeViz::

    from geeViz import fsInsights as fs
    fs.find_attributes("carbon")            # what can I estimate?
    fs.find_evaluations("Oregon")           # which inventory? -> wc=412022
    fs.estimate(wc=412022, snum=2,          # run it
                rselected="County code and name")
    fs.lcms_summary(state="Oregon", county="Crook")

Two things worth knowing before trusting a number out of here:

* **FIA estimates always carry their sampling error.** ``estimate()``
  returns ``se_pct`` and ``plots`` alongside every value and flags cells
  that are too thin to report. An FIA estimate without its error is not
  a fact: a real query for white/red/jack pine in Alabama returns
  15,748 acres with a **54.9% standard error from four plots**.
* **LCMS and FIA are not directly comparable.** One is a classified map,
  the other a probability sample. Comparing map-derived area to a
  design-based estimate conflates map accuracy with sampling error.
  ``compare_area`` makes the comparison and labels it; it will not hand
  you a single blended number that hides which is which.
"""
import importlib as _importlib
import sys as _sys

from georest.usfs import USFSError as FSInsightsError
from georest.usfs import UpstreamError, UpstreamUnavailable
from georest.usfs.lcms import (
    lcms_classes,
    lcms_products,
    lcms_releases,
    lcms_summary,
    lcms_summary_areas,
    lcms_vis_params,
    latest_release,
    release_products,
)
from georest.usfs.fia import (
    FIAValidationError,
    estimate,
    reliable,
    validate,
)
from georest.usfs.align import (
    COMPARISON_CAVEATS,
    compare_area,
    fia_forest_area,
    lcms_tree_area,
    summarize_comparison,
)
from georest.usfs.lcms_ee import (
    lcms_asset_id,
    lcms_class_properties,
    lcms_ee_collection,
)
from georest.usfs.vocab import (
    cache_dir,
    describe_grouping,
    find_attributes,
    find_evaluations,
    find_groupings,
    get_attribute,
    get_evaluation,
    refresh_all,
)

# ``import geeViz.fsInsights.fia`` and ``from geeViz.fsInsights.vocab
# import ...`` resolve to georest's modules themselves, not copies, so
# patching one patches the other.
for _name in ("fia", "lcms", "lcms_ee", "align", "vocab", "_http"):
    _module = _importlib.import_module(f"georest.usfs.{_name}")
    _sys.modules[f"{__name__}.{_name}"] = _module
    globals()[_name] = _module
del _name, _module

__all__ = [
    # FIA discovery
    "find_attributes",
    "get_attribute",
    "find_groupings",
    "describe_grouping",
    "find_evaluations",
    "get_evaluation",
    # FIA estimates
    "estimate",
    "validate",
    "reliable",
    "FIAValidationError",
    # LCMS
    "lcms_releases",
    "lcms_products",
    "lcms_classes",
    "lcms_summary_areas",
    "lcms_summary",
    "lcms_vis_params",
    "latest_release",
    "release_products",
    # FIA <-> LCMS comparison
    "COMPARISON_CAVEATS",
    "compare_area",
    "fia_forest_area",
    "lcms_tree_area",
    "summarize_comparison",
    # LCMS in Earth Engine
    "lcms_asset_id",
    "lcms_ee_collection",
    "lcms_class_properties",
    # Cache management
    "refresh_all",
    "cache_dir",
    # Errors
    "FSInsightsError",
    "UpstreamError",
    "UpstreamUnavailable",
]

__version__ = "2026.9.4"
