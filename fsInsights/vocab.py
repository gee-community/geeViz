"""Cached, searchable vocabularies for the FIA and LCMS APIs.

FIADB-API's ``/fullreport`` takes an estimate attribute, a row grouping,
a column grouping, and an evaluation. Live counts, measured against the
API:

=====================  =====  =========================================
Parameter              Count  What it selects
=====================  =====  =========================================
``snum`` / ``sdenom``    752  Estimate attribute (numerator/denominator)
``rselected`` etc.        96  Grouping variable (row / column / page)
``wc``                  1143  Evaluation (state + year + eval group)
=====================  =====  =========================================

That is a combinatorial space no one memorizes, and the published docs
still say "This page is under construction". Nothing in the official
documentation mentions that the parameter endpoints accept
``outputFormat=JSON`` — but they do, and that is what makes discovery
possible at all: the entire vocabulary is machine-readable, ~1.4 MB
total, and changes per *release* rather than per query.

So it is cached, and search runs locally. The caching policy mirrors
the MCP dataset catalog's — bundled snapshot, user cache, ~30-day
stale-while-revalidate — for the practical reason that one caching idea
in a codebase is easier to reason about than two.

**Failure is always backward, never forward.** A vocabulary lookup falls
from user cache, to bundled snapshot, to an empty result — it does not
raise, and it does not block on the network. Discovery is what people
do *before* they know what they want; making it fragile makes the whole
subpackage feel fragile.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ._http import UpstreamError, UpstreamUnavailable, get_json

logger = logging.getLogger(__name__)

FIA_BASE = "https://apps.fs.usda.gov/fiadb-api"
LCMS_BASE = "https://lcms-dashboard.fs2c.usda.gov/lcms/api"

#: FIA parameter catalogs, by the query-parameter name they populate.
#: ``sdenom`` shares ``snum``'s vocabulary and ``cselected``/``pselected``
#: share ``rselected``'s, so only the distinct ones are fetched.
FIA_CATALOGS = ("snum", "rselected", "wc")

#: Aliases onto the three fetched catalogs.
FIA_CATALOG_ALIASES = {
    "sdenom": "snum",
    "cselected": "rselected",
    "pselected": "rselected",
}

#: Refresh interval. These change when FIA publishes a new evaluation
#: cycle or LCMS cuts a release — an annual-ish cadence — so 30 days is
#: frequent enough to pick changes up well before anyone notices, and
#: rare enough that the network is essentially never on the hot path.
CACHE_TTL_SECONDS = 30 * 24 * 60 * 60

_BUNDLED_DIR = Path(__file__).parent / "data"
_MEM_CACHE: Dict[str, List[dict]] = {}


def cache_dir() -> Path:
    """Directory for refreshed catalogs.

    Sits alongside the workload-tag store under ``~/.geeViz`` so geeViz
    keeps exactly one place where it writes user state. Overridable with
    ``GEEVIZ_FSINSIGHTS_CACHE`` for tests and for locked-down machines
    where the home directory is not writable.
    """
    override = os.environ.get("GEEVIZ_FSINSIGHTS_CACHE", "").strip()
    base = Path(override) if override else Path.home() / ".geeViz" / "fsInsights"
    return base


def _cache_path(name: str) -> Path:
    return cache_dir() / f"{name}.json"


def _bundled_path(name: str) -> Path:
    return _BUNDLED_DIR / f"{name}.json"


def _read_json_file(path: Path) -> Optional[List[dict]]:
    try:
        if not path.is_file():
            return None
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else None
    except Exception:
        logger.debug("fsInsights: unreadable cache file %s", path, exc_info=True)
        return None


def _write_json_file(path: Path, rows: List[dict]) -> None:
    """Write atomically so an interrupted refresh cannot leave a truncated
    catalog that then reads as a valid-but-empty vocabulary."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(rows, fh)
        tmp.replace(path)
    except Exception:
        logger.debug("fsInsights: could not write cache %s", path, exc_info=True)


def _is_stale(path: Path) -> bool:
    try:
        return (time.time() - path.stat().st_mtime) > CACHE_TTL_SECONDS
    except Exception:
        return True


def _fetch_fia_catalog(name: str) -> List[dict]:
    """Pull one FIA parameter catalog as JSON.

    ``outputFormat=JSON`` is the undocumented part. Without it these
    endpoints serve an HTML table intended for a browser.
    """
    payload = get_json(f"{FIA_BASE}/fullreport/parameters/{name}",
                       params={"outputFormat": "JSON"})
    if not isinstance(payload, list):
        raise UpstreamError(
            f"unexpected shape for FIA catalog {name!r}: "
            f"{type(payload).__name__}"
        )
    return payload


def load_catalog(name: str, *, refresh: bool = False) -> List[dict]:
    """Return one vocabulary, from memory, cache, bundle, or the network.

    Args:
        name: A catalog or alias — any of ``snum``, ``sdenom``,
            ``rselected``, ``cselected``, ``pselected``, ``wc``.
        refresh: Force a network fetch, ignoring TTL. Still falls back
            to cached data if the fetch fails.

    Returns:
        List of records. Empty only when every source failed, which
        means discovery degrades rather than breaking.
    """
    name = FIA_CATALOG_ALIASES.get(name, name)
    if name not in FIA_CATALOGS:
        raise ValueError(
            f"unknown catalog {name!r}; expected one of "
            f"{sorted(set(FIA_CATALOGS) | set(FIA_CATALOG_ALIASES))}"
        )

    if not refresh and name in _MEM_CACHE:
        return _MEM_CACHE[name]

    cached = _read_json_file(_cache_path(name))
    need_fetch = refresh or cached is None or _is_stale(_cache_path(name))

    if need_fetch:
        try:
            rows = _fetch_fia_catalog(name)
            _write_json_file(_cache_path(name), rows)
            _MEM_CACHE[name] = rows
            return rows
        except (UpstreamError, UpstreamUnavailable) as exc:
            # Serve stale rather than fail. A vocabulary that is a month
            # out of date is enormously more useful than an exception,
            # and the caller is usually mid-exploration.
            logger.info(
                "fsInsights: catalog %r refresh failed (%s) — using "
                "cached/bundled copy", name, exc,
            )

    rows = cached if cached is not None else _read_json_file(_bundled_path(name))
    if rows is None:
        logger.warning(
            "fsInsights: no data for catalog %r — network unavailable and "
            "no bundled snapshot found; discovery will return nothing",
            name,
        )
        rows = []
    _MEM_CACHE[name] = rows
    return rows


def refresh_all(*, quiet: bool = False) -> Dict[str, int]:
    """Force-refresh every catalog. Returns ``{name: record_count}``.

    The escape hatch for "a new release just dropped and I do not want
    to wait out the TTL". Normal use should never need it.
    """
    out: Dict[str, int] = {}
    for name in FIA_CATALOGS:
        rows = load_catalog(name, refresh=True)
        out[name] = len(rows)
        if not quiet:
            print(f"  {name:12s} {len(rows):5d} records")
    return out


# ── Search ───────────────────────────────────────────────────────────────

def _score(text: str, terms: List[str]) -> int:
    """Count how many terms appear in ``text``, weighting whole words.

    Substring matching alone ranks "carbon" equally against
    "carbon" and "hydrocarbon-adjacent"; the word-boundary bonus keeps
    the obvious hit on top without needing a real index.
    """
    t = text.lower()
    score = 0
    for term in terms:
        if term in t:
            score += 1
            if f" {term} " in f" {t} " or t.startswith(term):
                score += 2
    return score


def find_attributes(query: str = "", *, land_basis: str = "",
                    eval_typ: str = "", limit: int = 25) -> "Any":
    """Search the 752 FIA estimate attributes.

    Args:
        query: Free text matched against description and group, e.g.
            ``"carbon"``, ``"net growth volume"``, ``"mortality"``.
        land_basis: Restrict to ``"Forest land"`` or ``"Timberland"``.
        eval_typ: Restrict to an evaluation type — ``EXPCURR``,
            ``EXPVOL``, ``EXPGROW``, ``EXPMORT``, ``EXPREMV``,
            ``EXPCHNG``, ``EXPDWM``.
        limit: Maximum rows returned.

    Returns:
        A ``pandas.DataFrame`` with the columns that matter for choosing
        an attribute — number, description, units, and the evaluation
        type it requires. The full record is available via
        :func:`get_attribute`.

    Note:
        **FIA's own catalog contains duplicate descriptions** — 7 of the
        752 appear more than once. ``snum`` 209 and 956, for instance,
        are identical across description, estimate group, evaluation
        type, estimation basis and tree portion. Both are returned
        rather than silently de-duplicated, because they are distinct
        attribute numbers upstream and collapsing them would hide a real
        property of the catalog. Where descriptions match on every
        field, either number should produce the same estimate.
    """
    rows = load_catalog("snum")
    terms = [t for t in query.lower().split() if t]

    hits = []
    for r in rows:
        if land_basis and str(r.get("LAND_BASIS", "")).lower() != land_basis.lower():
            continue
        if eval_typ and str(r.get("EVAL_TYP", "")).upper() != eval_typ.upper():
            continue
        blob = f"{r.get('ATTRIBUTE_DESCR', '')} {r.get('ESTIMATE_GRP_DESCR', '')}"
        s = _score(blob, terms) if terms else 1
        if s:
            hits.append((s, r))

    hits.sort(key=lambda x: (-x[0], x[1].get("ATTRIBUTE_NBR", 0)))
    return _frame([{
        "snum": r.get("ATTRIBUTE_NBR"),
        "description": r.get("ATTRIBUTE_DESCR"),
        "group": r.get("ESTIMATE_GRP_DESCR"),
        "land_basis": r.get("LAND_BASIS"),
        "units": r.get("ESTN_UNITS_DISPLAY"),
        "eval_typ": r.get("EVAL_TYP"),
        "basis": r.get("CONDTREESEED"),
    } for _, r in hits[:limit]])


def get_attribute(snum: int) -> Optional[dict]:
    """Full record for one attribute number, or None."""
    for r in load_catalog("snum"):
        if r.get("ATTRIBUTE_NBR") == snum:
            return dict(r)
    return None


def find_groupings(query: str = "", *, limit: int = 25) -> "Any":
    """Search the 96 FIA grouping variables.

    These are what ``rselected`` / ``cselected`` / ``pselected`` accept,
    and they are passed as *display strings* — so the exact ``label`` in
    this result is what the query needs, character for character.
    """
    rows = load_catalog("rselected")
    terms = [t for t in query.lower().split() if t]

    hits = []
    for r in rows:
        blob = f"{r.get('LABEL_VAR', '')} {r.get('DB_VAR', '')}"
        s = _score(blob, terms) if terms else 1
        if s:
            hits.append((s, r))

    hits.sort(key=lambda x: (-x[0], str(x[1].get("LABEL_VAR", ""))))
    return _frame([{
        "label": r.get("LABEL_VAR"),
        "db_column": r.get("DB_VAR"),
        "has_metadata": bool(r.get("PRC_METADATA")),
    } for _, r in hits[:limit]])


def describe_grouping(label: str) -> str:
    """Prose documentation for a grouping variable, codes included.

    FIA ships this as ``PRC_METADATA`` — an HTML fragment that usually
    enumerates what each code value means. It is the difference between
    a column of integers and a column you can interpret, so it is worth
    surfacing rather than leaving buried in the catalog.
    """
    import re
    for r in load_catalog("rselected"):
        if str(r.get("LABEL_VAR", "")).lower() == label.lower():
            html = r.get("PRC_METADATA") or ""
            text = re.sub(r"<[^>]+>", " ", html)
            return re.sub(r"\s+", " ", text).strip() or "(no metadata provided)"
    return f"(no grouping named {label!r} — try find_groupings())"


def find_evaluations(state: str = "", *, most_recent: bool = True,
                     growth_only: bool = False, limit: int = 25) -> "Any":
    """Search the 1,143 FIA evaluations.

    Args:
        state: State name, matched case-insensitively on a prefix.
        most_recent: Keep only each state's current evaluation. Almost
            always what you want; set False to see the back catalog.
        growth_only: Keep only evaluations with growth accounting
            (``GROWTH_ACCT == 'Y'``), which is a prerequisite for every
            growth, removals, and mortality attribute.
        limit: Maximum rows returned.
    """
    rows = load_catalog("wc")
    hits = []
    for r in rows:
        if most_recent and str(r.get("MOST_RECENT", "")).upper() != "Y":
            continue
        if growth_only and str(r.get("GROWTH_ACCT", "")).upper() != "Y":
            continue
        if state and not str(r.get("STATE", "")).lower().startswith(state.lower()):
            continue
        hits.append(r)

    hits.sort(key=lambda r: (str(r.get("STATE", "")), -int(r.get("EVAL_GRP", 0) or 0)))
    return _frame([{
        "wc": r.get("EVAL_GRP"),
        "state": r.get("STATE"),
        "statecd": r.get("STATECD"),
        "years": r.get("REPORT_YEAR_NM"),
        "growth_acct": r.get("GROWTH_ACCT"),
        "most_recent": r.get("MOST_RECENT"),
    } for r in hits[:limit]])


def get_evaluation(wc: int) -> Optional[dict]:
    """Full record for one evaluation group, or None."""
    for r in load_catalog("wc"):
        if r.get("EVAL_GRP") == wc:
            return dict(r)
    return None


def _frame(records: List[dict]):
    """Return a DataFrame, or the raw list if pandas is somehow absent.

    pandas is a core geeViz dependency, so the fallback is defensive
    rather than expected — but a vocabulary helper failing on an import
    error would be a poor first impression of the subpackage.
    """
    try:
        import pandas as pd
        return pd.DataFrame(records)
    except Exception:  # pragma: no cover
        return records
