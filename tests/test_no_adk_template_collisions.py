"""Regression test: the final agent INSTRUCTION string must not contain
any ``{identifier}`` patterns that ADK's session-state template substitution
would try to resolve.

ADK's regex is ``{+[^{}]*}+``. When the inner content (after stripping
braces and any trailing ``?``) is a valid Python identifier, ADK looks
it up in session state and raises ``KeyError`` if not found. Examples
that have bitten us:
- ``{x}/{y}/{z}`` in XYZ tile URL examples
- ``{n}`` in a math example like ``\\frac{1}{n}``

Mirrors the same checks ADK's instructions_utils.py runs.
"""
import os
import re


def _is_identifier(name):
    return name.isidentifier()


def _is_prefixed_identifier(name):
    parts = name.split(":")
    if len(parts) != 2:
        return False
    return (parts[0] + ":") in ("app:", "user:", "temp:") and parts[1].isidentifier()


def _find_collisions(text):
    """Return list of (var_name, byte_offset) ADK would error on."""
    collisions = []
    for m in re.finditer(r"\{+[^{}]*\}+", text):
        var_name = m.group().lstrip("{").rstrip("}").strip()
        if not var_name:
            continue
        if var_name.endswith("?"):  # optional — won't raise
            continue
        if var_name.startswith("artifact."):  # artifact lookup, different path
            continue
        if _is_identifier(var_name) or _is_prefixed_identifier(var_name):
            collisions.append((var_name, m.start()))
    return collisions


def _load_full_instruction():
    """Load _ADK_RULES from agent.py + the MCP instructions .md."""
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(here, "..", ".."))
    agent_py = os.path.join(repo_root, "geeViz_agent", "geeviz_agent", "agent.py")
    md_path = os.path.join(repo_root, "geeViz", "mcp", "agent-instructions.md")
    src = open(agent_py, encoding="utf-8").read()
    m = re.search(r'_ADK_RULES\s*=\s*"""\\?\n(.*?)"""', src, re.S)
    adk_rules = m.group(1) if m else ""
    mcp_text = open(md_path, encoding="utf-8").read()
    return adk_rules + "\n\n" + mcp_text


def test_no_adk_template_collisions():
    """The final composed instruction must have zero {identifier}
    patterns ADK would try to resolve.

    If this fails, look at the printed list and either:
    1. Rewrite the offending pattern with a non-identifier (e.g. ``<x>``
       in place of ``{x}`` for documentation), OR
    2. Append a ``?`` to make it optional (``{x?}``) if you want ADK
       to expand it to empty string when unset.
    """
    full = _load_full_instruction()
    collisions = _find_collisions(full)
    if collisions:
        lines = [f"Found {len(collisions)} ADK template-variable collision(s):"]
        for name, pos in collisions[:10]:
            ctx = full[max(0, pos - 60):pos + 60].replace("\n", "\\n")
            lines.append(f"  - {{{name}}} at byte {pos}:  ...{ctx}...")
        raise AssertionError("\n".join(lines))


def test_helper_recognizes_known_bad_patterns():
    """Make sure the audit helper itself works for the patterns that
    previously caused production errors."""
    assert _find_collisions("URL: https://e.com/{z}/{x}/{y}.png")
    assert _find_collisions("formula: \\frac{1}{n}")
    assert _find_collisions("{app:foo}")  # prefixed identifier
    # Counter-examples that should NOT be flagged
    assert not _find_collisions("see https://e.com/<z>/<x>/<y>.png")
    assert not _find_collisions("optional: {x?}")
    assert not _find_collisions("{x.y}")  # not an identifier
    assert not _find_collisions("{1n}")   # leading digit, not identifier
    assert not _find_collisions("{}")     # empty


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {t.__name__}:\n{e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print()
    if failed:
        print(f"{failed}/{len(tests)} tests FAILED")
        raise SystemExit(1)
    print(f"{len(tests)}/{len(tests)} tests passed")
