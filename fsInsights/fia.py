"""FIADB-API client — Forest Inventory and Analysis estimates.

Wraps **EVALIDator**, the USFS tool behind ``fiadb-api/fullreport``.
EVALIDator is the name people know this service by, so it is said
here in prose: an agent searching the codebase for "EVALIDator"
found nothing but a test, because the word lived only in comments.

FIA is a **probability sample** of forest plots, not a census. Every
estimate it produces is a design-based estimate with a sampling error,
and this client is built around refusing to let you forget that.

A real query illustrates why. Forest area by county and forest type
group for Alabama returns, among 4,241 plots:

===============================  ===========  ======  =====
Forest type group                      Acres  SE (%)  Plots
===============================  ===========  ======  =====
Total                             22,963,960    0.51   4241
Longleaf / slash pine group        1,184,334    6.07    258
White / red / jack pine group         15,748   54.92      4
===============================  ===========  ======  =====

That last row is a number with a 54.9% standard error resting on four
plots. Rendered as a bare value in a chart it reads as fact. So
:func:`estimate` returns ``se_pct`` and ``plots`` on every row, and
flags the ones too thin to report.

Why plot count as well as standard error, when SE already grows as the
sample shrinks: there are three regimes where SE cannot police itself.
At ``n = 0`` it is zero or undefined — reading as *maximum precision*
when it means *no information*, which is the dangerous inversion. At
``n = 1`` no variance estimate exists at all. And at small ``n`` the SE
is itself estimated from that same tiny sample, so a small value can be
luck rather than precision. There is a fourth, quieter problem: an SE
is normally consumed as ``estimate ± 1.96·SE``, which assumes
approximate normality — at small ``n`` that interval *undercovers*, in
the direction of overconfidence.

See Bechtold & Patterson, *The Enhanced Forest Inventory and Analysis
Program* (GTR-SRS-80), for the estimation design itself.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ._http import get_json
from .vocab import FIA_BASE, get_attribute, get_evaluation, load_catalog

logger = logging.getLogger(__name__)

#: Flag a cell whose standard error exceeds this percentage.
DEFAULT_MAX_SE_PCT = 30.0

#: Flag a cell resting on fewer than this many plots. 30 is the
#: conventional floor for the normal approximation that turns an SE into
#: a confidence interval — which is exactly the assumption ``± 1.96·SE``
#: relies on.
DEFAULT_MIN_PLOTS = 30

#: Evaluation types that require growth accounting on the evaluation.
#: Asking for mortality against an evaluation without it fails upstream
#: with a message that does not name the real problem.
_NEEDS_GROWTH_ACCT = frozenset({"EXPGROW", "EXPMORT", "EXPREMV", "EXPCHNG"})

#: Forest land definitions. FIA and RPA produce *different areas*, and
#: the API silently defaults to RPADEF — so a caller who never thinks
#: about it gets numbers that quietly disagree with someone else's
#: EVALIDator pull.
FOREST_DEFINITIONS = ("FIADEF", "RPADEF")


class FIAValidationError(ValueError):
    """A request that would fail upstream, caught locally first.

    Every check here is cheap and offline. Turning an opaque server
    error into a specific local one matters most for agents, where a
    rejected call costs a whole turn.
    """


def validate(wc: int, snum: int) -> None:
    """Check an attribute is answerable by an evaluation. Raises if not.

    Pre-flight for the EVALIDator request, so a bad pairing fails here
    with a named reason instead of arriving as EVALIDator's own "Key
    Error / Received an Error" HTML page.

    Attributes declare the evaluation type they need (``EXPCURR``,
    ``EXPVOL``, ``EXPGROW``, ``EXPMORT``, ``EXPREMV``, ``EXPCHNG``,
    ``EXPDWM``); evaluations advertise whether they support growth
    accounting. The pairing is knowable before the request leaves.
    """
    ev = get_evaluation(wc)
    if ev is None:
        raise FIAValidationError(
            f"no evaluation with wc={wc}. Use find_evaluations('<state>') "
            f"to list them."
        )
    attr = get_attribute(snum)
    if attr is None:
        raise FIAValidationError(
            f"no attribute with snum={snum}. Use find_attributes('<term>') "
            f"to search the 752 available."
        )

    eval_typ = str(attr.get("EVAL_TYP", "")).upper()
    if eval_typ in _NEEDS_GROWTH_ACCT:
        if str(ev.get("GROWTH_ACCT", "")).upper() != "Y":
            raise FIAValidationError(
                f"attribute {snum} ({attr.get('ATTRIBUTE_DESCR')!r}) needs "
                f"evaluation type {eval_typ}, which requires growth "
                f"accounting, but evaluation {wc} "
                f"({ev.get('STATE')}) has GROWTH_ACCT="
                f"{ev.get('GROWTH_ACCT')!r}. Use "
                f"find_evaluations('{ev.get('STATE')}', growth_only=True)."
            )


def _check_grouping(which: str, label: str) -> None:
    """Refuse a grouping label EVALIDator does not know. Raises if so.

    EVALIDator does not reject an unknown ``rselected`` / ``cselected`` /
    ``pselected``: it drops it and answers ungrouped. So "Forest-type
    group" (the real label is "Forest type group") came back as the state
    total, shaped like a one-row breakdown, with nothing to say the
    grouping was ignored -- an agent then reports it as the answer by
    forest type. Labels are display strings matched character for
    character, so they are checked against the catalog here, with the
    nearest real labels in the error.
    """
    labels = [str(r.get("LABEL_VAR") or "") for r in load_catalog("rselected")]
    if label in labels:
        return
    import difflib
    near = difflib.get_close_matches(label, labels, n=3, cutoff=0.5)
    hint = (f" Did you mean {', '.join(repr(n) for n in near)}?" if near
            else " Use find_groupings('<term>') to search them.")
    raise FIAValidationError(
        f"{which}={label!r} is not an FIA grouping label (labels are matched "
        f"exactly; EVALIDator would silently ignore it and return ungrouped "
        f"totals).{hint}"
    )


def estimate(wc: int, snum: int, *,
             rselected: str = "",
             cselected: str = "",
             pselected: str = "",
             sdenom: Optional[int] = None,
             forest_definition: str = "FIADEF",
             str_filter: str = "",
             max_se_pct: float = DEFAULT_MAX_SE_PCT,
             min_plots: int = DEFAULT_MIN_PLOTS,
             validate_first: bool = True) -> "Any":
    """Run an FIA estimate and return it tidy, with its sampling error.

    This is the EVALIDator ``fullreport`` call.

    Args:
        wc: Evaluation group — see :func:`~geeViz.fsInsights.find_evaluations`.
        snum: Estimate attribute — see
            :func:`~geeViz.fsInsights.find_attributes`.
        rselected: Row grouping, as the exact display string from
            :func:`~geeViz.fsInsights.find_groupings`.
        cselected: Column grouping. Optional.
        pselected: Page grouping. Optional.
        sdenom: Denominator attribute, to produce a ratio estimate.
        forest_definition: ``"FIADEF"`` or ``"RPADEF"``. Defaults to
            ``FIADEF`` and is always sent explicitly — the API's own
            default is RPADEF, and leaving it implicit is how two people
            pull "the same" number and disagree.

            **Caveat, unresolved.** In testing, sending
            ``FIAorRPA=FIADEF`` still produced the echo *"RPADEF as the
            forest land definition."* — so the parameter may be ignored,
            or may need a different spelling than the documentation
            gives. That is why the returned ``forest_definition`` column
            carries the API's **echo** rather than what was requested:
            whatever the server actually applied is what a saved frame
            should record. Compare the two before publishing a number
            that depends on the distinction.
        str_filter: SQL-style filter passed through as ``strFilter``.
            Qualify columns with the FULL table name — ``plot.unitcd``,
            ``cond.owncd``, ``tree.spcd``. The short aliases that appear
            in FIA documentation and in the ``db_column`` values from
            :func:`find_groupings` (``P.``, ``C.``, ``PG.``) are NOT
            accepted here: EVALIDator answers ``p.unitcd in (0, 1, 2)``
            with HTTP 200 carrying an "Internal Server Error - SQL
            Error" page, which says nothing about the alias being the
            problem. Two separate agent sessions burned several turns
            guessing before landing on ``plot.``.

            Example — western Oregon survey units only::

                estimate(wc=412022, snum=98, rselected="Unit code",
                         str_filter="plot.unitcd in (0, 1, 2)")
        max_se_pct: Flag cells whose standard error exceeds this.
        min_plots: Flag cells resting on fewer plots than this.
        validate_first: Check attribute/evaluation compatibility locally
            before sending. Turn off only to probe the API directly.

    Returns:
        ``pandas.DataFrame`` with one row per cell: ``row``, ``column``,
        ``estimate``, ``se_pct``, ``plots``, ``units``, ``unreliable``,
        ``unreliable_reason``, plus ``attribute``, ``evaluation`` and
        ``forest_definition`` for provenance.

    Raises:
        FIAValidationError: The request would fail upstream.
        UpstreamError / UpstreamUnavailable: The API refused or could
            not be reached.
    """
    if validate_first:
        validate(wc, snum)
        for _which, _label in (("rselected", rselected), ("cselected", cselected),
                               ("pselected", pselected)):
            if _label:
                _check_grouping(_which, _label)

    fd = str(forest_definition).upper()
    if fd not in FOREST_DEFINITIONS:
        raise FIAValidationError(
            f"forest_definition must be one of {FOREST_DEFINITIONS}, "
            f"got {forest_definition!r}"
        )

    params: Dict[str, Any] = {
        "wc": wc,
        "snum": snum,
        # NJSON, not JSON. ``/fullreport`` with outputFormat=JSON is broken
        # server-side: EVALIDator raises "Key Error / Received an Error:
        # 'row'" while building the nested row/column structure and hands
        # back an HTML error page under HTTP 200. Confirmed against API
        # v2.1.7 (2026-07-30) / FIADB_1.9.4.00 -- the SAME query returns a
        # full report as HTML, NHTML, CSV, XML or NJSON, so this is a bug
        # in that one serializer rather than an outage or a bad request.
        #
        # NJSON is also the better shape for us: a flat ``estimates`` list
        # carrying SE_PERCENT and PLOT_COUNT directly, instead of
        # cellSE/cellPlotNumerator nested two levels deep.
        #
        # Note the asymmetry -- the PARAMETER endpoints
        # (/fullreport/parameters/<name>, used by vocab.py) are the
        # reverse: JSON works there and NJSON returns an error page. Do
        # not "unify" these two on one format.
        "outputFormat": "NJSON",
        "FIAorRPA": fd,
    }
    if rselected:
        params["rselected"] = rselected
    if cselected:
        params["cselected"] = cselected
    if pselected:
        params["pselected"] = pselected
    if sdenom is not None:
        params["sdenom"] = sdenom
    if str_filter:
        params["strFilter"] = str_filter

    payload = get_json(f"{FIA_BASE}/fullreport", params=params)
    return _to_frame(payload, max_se_pct=max_se_pct, min_plots=min_plots,
                     snum_hint=snum,
                     selections=(bool(pselected), bool(rselected),
                                 bool(cselected)))


def _reason(se_pct, plots, max_se_pct, min_plots) -> str:
    """Why a cell should not be reported, or '' when it is fine.

    ``n = 0`` and ``n = 1`` get their own reasons rather than being
    folded into "high error", because their standard errors are not
    merely large — they are meaningless, and a zero SE on an empty cell
    looks like the most precise number on the page.
    """
    if plots is None:
        return "no plot count reported"
    if plots == 0:
        return "no plots - estimate carries no information"
    if plots == 1:
        return "single plot - no variance estimate possible"
    if plots < min_plots:
        return (f"only {plots} plots (< {min_plots}); normal approximation "
                f"for a confidence interval does not hold")
    if se_pct is not None and se_pct > max_se_pct:
        return f"standard error {se_pct:.1f}% exceeds {max_se_pct:.0f}%"
    return ""


def _grp_assignment(selections: Optional[tuple]) -> Dict[str, Optional[str]]:
    """Map page/row/column onto the GRP keys NJSON will actually use.

    NJSON numbers its grouping columns GRP1..GRPn over the selections
    that were SENT, in p, r, c order — not into fixed slots. So with
    ``rselected`` and ``cselected`` but no ``pselected``, the row lands
    in ``GRP1`` and the column in ``GRP2``.

    ``selections`` is ``(has_p, has_r, has_c)``. When it is None (a
    caller invoking ``_to_frame`` directly, or a recorded payload in a
    test) fall back to the all-three layout, which is what the raw key
    names suggest.
    """
    if selections is None:
        return {"page": "GRP1", "row": "GRP2", "column": "GRP3"}
    has_p, has_r, has_c = (bool(x) for x in selections)
    out: Dict[str, Optional[str]] = {"page": None, "row": None, "column": None}
    n = 0
    for key, present in (("page", has_p), ("row", has_r), ("column", has_c)):
        if present:
            n += 1
            out[key] = f"GRP{n}"
    return out


def _to_frame(payload: Any, *, max_se_pct: float, min_plots: int,
              snum_hint: Any = None,
              selections: Optional[tuple] = None) -> "Any":
    """Flatten an FIA report into tidy rows.

    Handles both response shapes:

    * **NJSON** (what ``estimate`` now requests) — a flat object with an
      ``estimates`` list at the top level and no wrapper.
    * **legacy JSON** — everything nested under ``EVALIDatorOutput`` as a
      row/column tree.
    """
    if not isinstance(payload, dict):
        raise ValueError(
            "unexpected FIA response shape — expected a JSON object, "
            f"got {type(payload).__name__}"
        )

    # NJSON has no wrapper; fall back to the payload itself so the shared
    # extraction below works for both. Requiring 'EVALIDatorOutput' here
    # is what made the NJSON switch fail with a confusing "got dict".
    out = payload.get("EVALIDatorOutput")
    if not isinstance(out, dict):
        if "estimates" not in payload:
            raise ValueError(
                "unexpected FIA response shape — expected either an "
                "'EVALIDatorOutput' object (legacy JSON) or a top-level "
                f"'estimates' list (NJSON), got keys: "
                f"{sorted(payload.keys())[:8]}"
            )
        out = payload

    meta_early = out.get("metadata") or {}
    attr_name = (out.get("numeratorName")
                 or str(meta_early.get("numEstDesc") or "") or "")
    # NJSON does not echo the attribute number, so fall back to the snum
    # the caller asked for. Without this, attr_nbr is None -> _units_for
    # returns "" and every row loses its units label.
    attr_nbr = out.get("numeratorAttributeNumber")
    if attr_nbr is None:
        attr_nbr = snum_hint
    inventories = out.get("selectedInventories") or {}
    states = inventories.get("stateInventory") or []
    # The API echoes back the definition it actually applied, e.g.
    # "RPADEF as the forest land definition." Carrying it through means
    # a saved frame is self-describing about which definition produced
    # it, rather than depending on the caller's memory.
    fd_echo = str(out.get("FIAorRPAfilter") or "")
    units = _units_for(attr_nbr)

    records: List[dict] = []

    # ── NJSON (current) ─────────────────────────────────────────────────
    # Flat ``estimates`` list keyed GRP1..GRPn.
    #
    # The GRP numbers are POSITIONAL OVER THE GROUPINGS ACTUALLY SENT, in
    # p, r, c order -- they are not fixed slots. Verified against live
    # responses:
    #
    #   pselected + rselected + cselected -> GRP1=p, GRP2=r, GRP3=c
    #   rselected + cselected (no p)      -> GRP1=r, GRP2=c
    #   rselected only                    -> GRP1=r
    #
    # Assuming fixed slots is wrong the moment pselected is omitted --
    # which is the common case. It put the COLUMN value in ``row`` and
    # left ``column`` empty, silently transposing the table while still
    # producing plausible-looking numbers. Caught by the example
    # notebook, whose cells came back with column=None.
    grp_for = _grp_assignment(selections)
    estimates = out.get("estimates")
    if isinstance(estimates, list) and estimates:
        meta = out.get("metadata") or {}
        # NJSON reports the applied definition as metadata.FIAorRPA;
        # legacy put it at top level as FIAorRPAfilter.
        fd_echo = str(meta.get("FIAorRPA") or fd_echo or "")
        eval_grps = meta.get("evalGrps")
        eval_label = ("; ".join(str(g) for g in eval_grps)
                      if isinstance(eval_grps, list) and eval_grps
                      else "; ".join(str(s) for s in states))
        for r in estimates:
            if not isinstance(r, dict):
                continue
            est = r.get("ESTIMATE")
            # SE_PERCENT is already a percentage -- the reliability floors
            # compare against max_se_pct, so do NOT substitute the
            # absolute SE field here.
            se = r.get("SE_PERCENT")
            plots = r.get("PLOT_COUNT")
            est = float(est) if est is not None else None
            se = float(se) if se is not None else None
            plots = int(plots) if plots is not None else None
            reason = _reason(se, plots, max_se_pct, min_plots)
            records.append({
                "row": r.get(grp_for["row"]) if grp_for["row"] else None,
                "column": r.get(grp_for["column"]) if grp_for["column"] else None,
                "page": r.get(grp_for["page"]) if grp_for["page"] else None,
                "estimate": est,
                "se_pct": se,
                "plots": plots,
                "units": units,
                "unreliable": bool(reason),
                "unreliable_reason": reason,
                "attribute": attr_name,
                "snum": attr_nbr,
                "evaluation": eval_label,
                "forest_definition": fd_echo,
            })

        # ── Totals and marginals ────────────────────────────────────────
        # Legacy JSON carried a "Total" row inline; NJSON moves them to
        # separate ``totals`` (grand total) and ``subtotals`` (per-group
        # marginals) keys. Callers filtering ``df['row'] == 'Total'`` --
        # which the example notebook does -- got an empty frame until
        # these were re-emitted.
        def _add(row_label, col_label, rec):
            if not isinstance(rec, dict):
                return
            e = rec.get("ESTIMATE")
            s_ = rec.get("SE_PERCENT")
            p_ = rec.get("PLOT_COUNT")
            e = float(e) if e is not None else None
            s_ = float(s_) if s_ is not None else None
            p_ = int(p_) if p_ is not None else None
            why = _reason(s_, p_, max_se_pct, min_plots)
            records.append({
                "row": row_label, "column": col_label, "page": None,
                "estimate": e, "se_pct": s_, "plots": p_, "units": units,
                "unreliable": bool(why), "unreliable_reason": why,
                "attribute": attr_name, "snum": attr_nbr,
                "evaluation": eval_label, "forest_definition": fd_echo,
            })

        subs = out.get("subtotals")
        if isinstance(subs, dict):
            # A marginal over the ROW grouping varies by row and is
            # totalled across columns -> column='Total', and vice versa.
            if grp_for["row"]:
                for rec in subs.get(grp_for["row"]) or []:
                    _add(rec.get(grp_for["row"]), "Total", rec)
            if grp_for["column"]:
                for rec in subs.get(grp_for["column"]) or []:
                    _add("Total", rec.get(grp_for["column"]), rec)

        for rec in out.get("totals") or []:
            _add("Total", "Total", rec)

        return _frame(records)

    # ── Legacy nested row/column (outputFormat=JSON) ────────────────────
    # Retained as a fallback: if the upstream JSON serializer is repaired,
    # or a deployment pins the older format, this still parses correctly.
    for row in out.get("row", []) or []:
        row_label = row.get("content")
        cols = row.get("column") or [row]
        for col in cols:
            est = col.get("cellValueNumerator")
            se = col.get("cellSE")
            plots = col.get("cellPlotNumerator")
            est = float(est) if est is not None else None
            se = float(se) if se is not None else None
            plots = int(plots) if plots is not None else None
            reason = _reason(se, plots, max_se_pct, min_plots)
            records.append({
                "row": row_label,
                "column": col.get("content"),
                "estimate": est,
                "se_pct": se,
                "plots": plots,
                "units": units,
                "unreliable": bool(reason),
                "unreliable_reason": reason,
                "attribute": attr_name,
                "snum": attr_nbr,
                "evaluation": "; ".join(str(s) for s in states),
                "forest_definition": fd_echo,
            })
    return _frame(records)


def _units_for(snum) -> str:
    try:
        attr = get_attribute(int(snum))
        return str((attr or {}).get("ESTN_UNITS_DISPLAY") or "")
    except Exception:
        return ""


def reliable(df) -> "Any":
    """Drop cells flagged unreliable.

    Separate from :func:`estimate` on purpose. The data layer returns
    everything with a reason attached; discarding is the caller's
    decision, and a silent drop at fetch time would hide how much of a
    cross-tabulation is too thin to use.
    """
    try:
        return df[~df["unreliable"]]
    except Exception:
        return df


def _frame(records: List[dict]):
    try:
        import pandas as pd
        return pd.DataFrame(records)
    except Exception:  # pragma: no cover
        return records
