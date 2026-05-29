"""Earth Engine workload-tag helpers.

EE workload tags surface in GCP Billing under the
``goog-earth-engine-workload-tag`` label, so tagged calls can be broken
down per user / session / source. This module builds well-formed tags
from arbitrary string parts (sanitizing each so the result is always
accepted by EE).

EE constraints (from ``ee/_state.py`` validation):

- 1 - 63 characters
- begins and ends with a lowercase alphanumeric ``[a-z0-9]``
- middle characters: ``[a-z0-9_-]`` (lowercase alphanumeric, dash, underscore)

No uppercase, no ``.``, no other punctuation. Anything outside that set
(``@``, spaces, slashes, dots, uppercase, etc.) gets sanitized to ``-``.

**Separator: ``__`` (double underscore).** Single ``-`` already appears
inside sanitized parts (e.g. ``ihousman-redcastleresources-com``), so we
reserve double underscore as the between-parts delimiter. That makes
tags trivially parseable with ``tag.split("__")``::

    agent__run_code__ihousman-redcastleresources-com__db208a06-1c49

To keep ``__`` an unambiguous separator, runs of ``_`` *within* a part
get collapsed to a single ``_`` during sanitization (so an input like
``run__code`` becomes ``run_code``). Underscores from sources like tool
names — ``run_code``, ``map_control`` — pass through intact because
they're already singletons.
"""
from __future__ import annotations
import re

_TAG_ALLOWED_CHAR = re.compile(r"[^a-z0-9_\-]")
_TAG_MAX_LEN = 63
SEPARATOR = "__"


def sanitize_workload_tag_part(s: str) -> str:
    """Sanitize a single component of a workload tag.

    - Lowercases.
    - Replaces disallowed characters with ``-``.
    - Collapses runs of ``-`` to a single ``-``.
    - Collapses runs of ``_`` to a single ``_`` so the ``__`` separator
      stays unambiguous when parts are joined.
    - Strips leading/trailing ``-`` and ``_`` (EE rejects tags that don't
      begin and end with an alphanumeric).
    """
    if not s:
        return ""
    s = s.lower()
    s = _TAG_ALLOWED_CHAR.sub("-", s)
    s = re.sub(r"-{2,}", "-", s)
    s = re.sub(r"_{2,}", "_", s)
    s = s.strip("-_")
    return s


def build_workload_tag(*parts: str) -> str:
    """Join sanitized parts with ``__`` and clamp to EE's 63-char limit.

    Empty / falsy parts are dropped. The final tag is guaranteed to satisfy
    EE's regex: ``[a-z0-9][a-z0-9_\\-]{0,61}[a-z0-9]``. Returns an empty
    string if everything was dropped — callers should treat empty as "no
    tag" and skip the workload-tag header / body field entirely.
    """
    clean = [sanitize_workload_tag_part(p) for p in parts]
    clean = [c for c in clean if c]
    if not clean:
        return ""
    tag = SEPARATOR.join(clean)[:_TAG_MAX_LEN]
    # Re-strip in case the truncation left a dangling separator at the end.
    tag = tag.rstrip("-_")
    return tag
