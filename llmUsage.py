"""One shape for "this call spent LLM tokens", and one place to report it.

Three geeViz modules call Gemini directly — :mod:`geeViz.googleMapsLib`,
:mod:`geeViz.inventoryLib` and :mod:`geeViz.outputLib.reports`. Two of
them already pulled token counts off the response and returned them in a
``metadata`` dict; the third threw them away. All three used different
key names, and none of the counts reached anything that accounts for
spend, so tokens burned through the geeViz libraries were invisible to
the agent that paid for them.

This module fixes the shape and the reporting separately:

**The shape** — :func:`usage_from_response` turns a ``google-genai``
response into a dict whose keys match what the consumer already speaks
(``prompt_tokens``, ``candidates_tokens``, ``thoughts_tokens``,
``cached_tokens``, ``tool_use_prompt_tokens``, ``total_tokens``). The old
geeViz spellings — ``input_tokens``, ``output_tokens``,
``thought_tokens`` — were a second vocabulary for the same numbers, and
every hand-off between the two was a chance to drop a field silently.

**The reporting** — :func:`report` hands the record to
:data:`on_usage`, a hook that does nothing by default. geeViz is a
standalone library: it must not import an agent, hold database
credentials, or know who is being billed. A host that cares (the MCP
server, which runs as a subprocess of the agent) sets the hook at
startup and forwards what it collects.

Nothing here can raise into a caller. A failure to *account* for work
must never fail the work.

Example — a host collecting what one call spent::

    import geeViz.llmUsage as lu

    with lu.collect() as records:
        result = some_geeviz_function_that_calls_gemini()
    # records is a list of usage dicts, one per Gemini response
"""

import contextvars
import uuid
from typing import Any, Callable, Optional

#: The Gemini model every geeViz surface uses unless told otherwise.
#:
#: One constant rather than a literal per module. It was three different
#: literals — ``gemini-3.5-flash`` in googleMapsLib and inventoryLib,
#: ``gemini-3-flash-preview`` in outputLib.reports — so "the geeViz
#: default model" was not one thing, and moving it forward meant finding
#: every copy. Two of them also cost more than this one: 3.8 is priced
#: at $0.75/$3.75 per 1M tokens against 3.5's $1.50/$9.00, so this is a
#: cost reduction as well as a version bump.
#:
#: Callers may still pass any model explicitly; this is only the default.
DEFAULT_MODEL = "gemini-3.8-flash"

#: The model :class:`geeViz.outputLib.reports.Report` writes with unless
#: told otherwise. Reports are the one surface where the model writes
#: long prose a reader keeps (summaries, per-section narrative), so they
#: get the stronger Gemini 4 Hydrogen rather than the flash default.
REPORT_MODEL = "gemini-4-hydrogen"


# ── A client and a config without the log noise ──────────────────────
#
# Every geeViz Gemini call passes its key explicitly, yet google-genai
# warns "Both GOOGLE_API_KEY and GEMINI_API_KEY are set" whenever both
# variables exist, which reads like a misconfiguration and is not one.
# And with automatic function calling (AFC) on, which is the default, it
# logs about AFC on every call, though geeViz never passes tools. In the
# MCP server both land in run_code's stderr, where they look like errors.

_KEY_WARNING = "Both GOOGLE_API_KEY and GEMINI_API_KEY are set"


class _DropKeyWarning:
    """Drops only that one message; every other record passes."""

    def filter(self, record) -> bool:
        try:
            return not str(record.getMessage()).startswith(_KEY_WARNING)
        except Exception:
            return True


_key_filter = _DropKeyWarning()


def genai_client(api_key: str):
    """A ``google.genai.Client`` for ``api_key``, minus the misleading
    both-keys warning (the key used is the one passed here)."""
    import logging
    from google import genai

    lg = logging.getLogger("google_genai._api_client")
    if _key_filter not in lg.filters:
        lg.addFilter(_key_filter)
    return genai.Client(api_key=api_key)


def genai_config(**kwargs):
    """A ``GenerateContentConfig`` with automatic function calling off.

    geeViz passes no tools, so AFC does nothing but log on every call.
    """
    from google.genai import types

    kwargs.setdefault("automatic_function_calling",
                      types.AutomaticFunctionCallingConfig(disable=True))
    return types.GenerateContentConfig(**kwargs)

__all__ = [
    "DEFAULT_MODEL",
    "REPORT_MODEL",
    "CANONICAL_FIELDS",
    "usage_from_response",
    "report",
    "collect",
    "on_usage",
    "mint_call_id",
]


# The record. Every field is present on every record — a reader that has
# to test for a key cannot tell "zero tokens" from "this producer forgot
# to report that field", and the first is normal while the second is a
# bug.
#
# Names match geeViz_agent's ``gemini_usage`` table and
# ``cdu.gemini_usage_to_cdus`` exactly, so a record crosses into the
# agent's accounting without a translation step. The translation step is
# what this module exists to delete.
CANONICAL_FIELDS = (
    "model",                   # which model ran — CDU pricing is per-model
    "prompt_tokens",           # input
    "candidates_tokens",       # output
    "thoughts_tokens",         # internal reasoning, 0 when not exposed
    "cached_tokens",           # subset of prompt_tokens served from cache
    "tool_use_prompt_tokens",  # tool schemas + tool results
    "total_tokens",
    "response_id",             # idempotency key — see mint_call_id
    "source",                  # which geeViz surface spent it
)

# Modality detail geeViz collects and the agent does not. Kept separate
# from CANONICAL_FIELDS so a consumer can ignore it wholesale, and named
# off ``prompt_`` for consistency with the field it subdivides.
MODALITY_FIELDS = ("prompt_text_tokens", "prompt_image_tokens")


def mint_call_id(response: Any = None) -> str:
    """A stable id for one Gemini call, for de-duplication.

    Gemini populates ``response_id`` on some responses and leaves it
    empty on others (streaming, in particular). The consumer uses it as
    an idempotency key, so an empty one means the record cannot be
    recognized as a repeat.

    That matters less than it sounds for *retries* — a retried Gemini
    call really did cost money twice and should be counted twice. What
    it protects against is the same record being submitted twice: a tool
    result replayed out of conversation history, a delivery retried, a
    collector drained twice. Those must not bill anybody a second time.

    So: use Gemini's id when there is one, mint a ``geeviz-`` prefixed
    UUID when there is not. Either way the id is fixed at the moment the
    response is read, which is what makes a later replay recognizable.
    """
    rid = ""
    if response is not None:
        try:
            rid = getattr(response, "response_id", "") or ""
        except Exception:
            rid = ""
    return str(rid) or f"geeviz-{uuid.uuid4().hex}"


def _int(value: Any) -> int:
    """A token count, or 0. Never None.

    ``usage_metadata`` fields are absent rather than zero when a model
    does not expose them, and the old code let those Nones through into
    the returned dict — where ``f"{n:,}"`` then raised on a display path
    far away from the cause.
    """
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def usage_from_response(response: Any, *, model: str = "",
                        source: str = "") -> dict:
    """Canonical usage record for one ``google-genai`` response.

    ``model`` is taken from the response when it carries one and falls
    back to the argument, because CDU pricing is per-model and a record
    with the wrong model name is billed at the wrong rate — a failure
    that produces plausible numbers rather than an error.

    Returns a record whose token counts are all zero if the response
    exposes no ``usage_metadata``; the caller can still report it, and a
    zero-token record is correctly free rather than absent.
    """
    um = getattr(response, "usage_metadata", None)

    resolved_model = ""
    try:
        resolved_model = getattr(response, "model_version", "") or ""
    except Exception:
        resolved_model = ""
    resolved_model = str(resolved_model or model or "")

    rec = {
        "model": resolved_model,
        "prompt_tokens": _int(getattr(um, "prompt_token_count", 0)),
        "candidates_tokens": _int(getattr(um, "candidates_token_count", 0)),
        "thoughts_tokens": _int(getattr(um, "thoughts_token_count", 0)),
        "cached_tokens": _int(getattr(um, "cached_content_token_count", 0)),
        "tool_use_prompt_tokens": _int(
            getattr(um, "tool_use_prompt_token_count", 0)),
        "total_tokens": _int(getattr(um, "total_token_count", 0)),
        "response_id": mint_call_id(response),
        "source": str(source or ""),
    }

    # total_tokens is what most display paths print. Gemini omits it on
    # some responses, and a report reading "0 tokens" under a paragraph
    # the model clearly wrote is worse than an approximation.
    if not rec["total_tokens"]:
        rec["total_tokens"] = (rec["prompt_tokens"]
                               + rec["candidates_tokens"]
                               + rec["thoughts_tokens"])

    # Modality split, when the response carries it. prompt_tokens_details
    # is a list of (modality, token_count) entries.
    text_tokens = image_tokens = 0
    try:
        for d in (getattr(um, "prompt_tokens_details", None) or []):
            modality = str(getattr(d, "modality", "") or "").upper()
            count = _int(getattr(d, "token_count", 0))
            if "TEXT" in modality:
                text_tokens += count
            elif "IMAGE" in modality:
                image_tokens += count
    except Exception:
        pass
    rec["prompt_text_tokens"] = text_tokens
    rec["prompt_image_tokens"] = image_tokens

    return rec


# ── reporting ─────────────────────────────────────────────────────────

# Set by a host that wants to hear about LLM spend. Signature:
# ``on_usage(record: dict) -> None``. Default does nothing, which is the
# right behavior for a notebook, a script, or anyone using geeViz
# without an agent in front of it.
on_usage: Optional[Callable[[dict], None]] = None

# Collectors are per-context, via contextvars rather than a
# thread-local. Two reasons, and the second is not a preference:
#
# 1. A ContextVar is per-TASK, which is what an asyncio server actually
#    needs — a thread-local would hand one collector to every coroutine
#    sharing the event-loop thread. A new thread starts with a fresh
#    context, so thread isolation still holds.
#
# 2. The ``threading`` module is on the MCP sandbox's blocked-import
#    list (``_AUDIT_BLOCKED_IMPORTS``). This module is imported at
#    module scope by outputLib.reports, googleMapsLib and inventoryLib,
#    so importing ANY of those from inside sandboxed ``run_code``
#    tripped the audit hook — and it did not fail cleanly, it HUNG the
#    server: the tool logged OK, its result was never returned, and the
#    agent sat on a spinner with no error logged anywhere.
_stack = contextvars.ContextVar("geeviz_llm_usage_stack", default=None)


def report(record: dict) -> dict:
    """Announce one usage record. Returns it, so call sites can inline.

    Never raises: accounting must not be able to fail the work it is
    accounting for. A broken hook is logged nowhere and dropped, because
    the alternative is a geeViz function failing for a reason that has
    nothing to do with what it was asked to do.
    """
    if not record:
        return record

    stack = _stack.get()
    if stack:
        try:
            stack[-1].append(record)
        except Exception:
            pass

    hook = on_usage
    if hook is not None:
        try:
            hook(record)
        except Exception:
            pass
    return record


class collect:
    """Context manager gathering every record reported inside it.

    Nests: an inner collector receives the records reported within it,
    and on exit hands them up to the enclosing one. Without that, a host
    collecting around a whole tool call would lose everything reported
    inside a geeViz function that collected around part of its own work.
    """

    def __init__(self):
        self.records: list = []

    def __enter__(self) -> list:
        stack = _stack.get()
        if stack is None:
            stack = []
            _stack.set(stack)
        stack.append(self.records)
        return self.records

    def __exit__(self, *exc) -> bool:
        stack = _stack.get() or []
        if stack and stack[-1] is self.records:
            stack.pop()
            if stack:
                stack[-1].extend(self.records)
        return False


def totals(records) -> dict:
    """Sum a list of records into one, for a summary line.

    ``model`` and ``response_id`` are dropped rather than guessed at —
    a total over two models belongs to neither, and inventing a single
    id for a sum would let it be mistaken for a billable record.
    """
    out = {f: 0 for f in CANONICAL_FIELDS if f.endswith("_tokens")}
    out.update({f: 0 for f in MODALITY_FIELDS})
    out["calls"] = 0
    for r in (records or []):
        out["calls"] += 1
        for key in list(out):
            if key == "calls":
                continue
            try:
                out[key] += int(r.get(key) or 0)
            except (TypeError, ValueError, AttributeError):
                pass
    return out
