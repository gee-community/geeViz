"""Discovery: can the agent FIND what geeViz can do?

From a real session. The user said "run e validator on this" — EVALIDator
being the USFS tool behind the FIA API that ``fsInsights`` wraps. The
agent ran four searches before finding anything usable:

    search_codebase(query="validator")   -> 1 hit, a TEST function
    search_codebase(query="validate")    -> 3 hits, a TEST first
    search_codebase(query="evalidator")  -> 1 hit, the same TEST
    search_codebase(module="fia")        -> finally, the real API

Four causes, all fixed here and pinned below:

1. Test modules were indexed, so ``test_legacy_evalidator_output_still_
   parses`` outranked the API it tests — the term was in the test's NAME
   and only in the BODY of the real docstrings.
2. Matching looked at names and FIRST DOCSTRING LINES only, so a word
   that appears in the body of a docstring was unfindable. "carbon"
   returned zero.
3. Results were unranked, so a partial name match and an incidental
   prose mention sorted identically.
4. ``search_codebase(module="fsInsights")`` returned ``count: 0``. A
   package's spec.origin is its ``__init__.py``, which here has no defs
   of its own — so AST extraction found nothing and the most obvious
   query dead-ended.

And the content half of the same bug: "EVALIDator" appeared in fia.py
only in COMMENTS and one private docstring, so no index improvement
could have surfaced it. The word a user actually types has to be in the
public prose.

server.py is inspected as source rather than imported — importing it
initializes Earth Engine, which the rest of this suite does not require.
The existing test_search_codebase_repl.py makes the same trade for the
same reason. Comments are stripped before matching, because several of
these fixes carry explanatory comments that quote the very strings
being asserted on; without stripping, the tests would pass on their own
documentation.
"""
import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "mcp" / "server.py"
SRC = SERVER.read_text(encoding="utf-8")


def _code_only(text: str) -> str:
    """Source with comments and docstrings removed.

    Three tests earlier in this project passed by matching their own
    explanatory comments. Anything asserted on below has to be live
    code.
    """
    out = []
    for line in text.splitlines():
        # Strip trailing comments, but not a '#' inside a string literal.
        in_s, quote, buf = False, "", []
        for i, ch in enumerate(line):
            if in_s:
                buf.append(ch)
                if ch == quote and (i == 0 or line[i - 1] != "\\"):
                    in_s = False
            elif ch in "\"'":
                in_s, quote = True, ch
                buf.append(ch)
            elif ch == "#":
                break
            else:
                buf.append(ch)
        out.append("".join(buf))
    stripped = "\n".join(out)
    # Drop docstrings via AST where possible.
    try:
        tree = ast.parse(stripped)
    except SyntaxError:
        return stripped
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef, ast.Module)):
            body = getattr(node, "body", None)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                docs.add(body[0].value.value)
    for d in docs:
        stripped = stripped.replace(d, "")
    return stripped


CODE = _code_only(SRC)


def _func(name: str, text: str = None) -> str:
    """Source of one top-level function, to its next sibling."""
    text = CODE if text is None else text
    m = re.search(rf"^def {re.escape(name)}\(.*?(?=^def |\Z)", text,
                  re.S | re.M)
    assert m, f"could not locate def {name} in the stripped source"
    return m.group(0)


def test_the_stripper_actually_strips():
    """If _code_only silently returned the input, every test below would
    pass vacuously on comments."""
    sample = 'x = 1  # EVALIDator mentioned only in a comment\n'
    assert "EVALIDator" not in _code_only(sample)
    assert "x = 1" in _code_only(sample)


# ── 1. tests are not API ───────────────────────────────────────────────

def test_test_modules_are_not_indexed():
    body = _func("_build_module_tree")
    assert 'leaf.startswith("test_")' in body, (
        "test modules are still indexed — a test function will keep "
        "outranking the API it tests")
    assert '".tests"' in body or "'.tests'" in body, (
        "a tests/ subpackage is still indexed")


# ── 2 + 3. whole-docstring matching, ranked ────────────────────────────

def test_the_whole_docstring_is_searched():
    """Assert on the BINDING and its USE, not on the substring
    'm.get("docstring"' — that also appears in the unrelated name-lookup
    branch, so the loose version of this test passed even with body
    matching torn out."""
    body = _func("search_codebase")
    assert re.search(r'body_l\s*=\s*m\.get\("docstring", ""\)\.lower\(\)', body), (
        "the docstring body is never read into the match variable")
    assert re.search(r"elif\s+q\s+in\s+body_l\s*:", body), (
        "body_l is bound but never consulted, so a term that appears "
        "only in a docstring body stays unfindable")


def test_matches_are_ranked_not_just_filtered():
    body = _func("search_codebase")
    assert "RANK_EXACT" in body and "RANK_BODY" in body
    assert "results.sort(" in body, "results are returned unranked"


def test_rank_order_is_best_first():
    """An exact name must sort ahead of an incidental prose mention.
    Reversing these constants would silently invert the results."""
    body = _func("search_codebase")
    m = re.search(r"RANK_EXACT,\s*RANK_NAME,\s*RANK_SUMMARY,\s*RANK_BODY\s*=\s*"
                  r"(\d+),\s*(\d+),\s*(\d+),\s*(\d+)", body)
    assert m, "could not find the rank constants"
    vals = [int(g) for g in m.groups()]
    assert vals == sorted(vals), f"rank constants are not ascending: {vals}"


def test_a_module_can_itself_be_the_answer():
    body = _func("search_codebase")
    assert 'module_doc' in body, (
        "module docstrings are not searched, so 'which module talks to "
        "EVALIDator' cannot be answered with the module")


# ── the cap is honest ──────────────────────────────────────────────────

def test_a_capped_result_set_says_so():
    """Whole-docstring matching makes common words match a lot. Serving
    the top slice as if it were everything is the failure mode this
    project already hit with fia_estimate's silent max_results."""
    body = _func("search_codebase")
    assert '"truncated": True' in body
    assert '"total_matches"' in body, (
        "the caller cannot tell how much was withheld")


# ── 4. a package points at its submodules ──────────────────────────────

def test_a_package_lists_its_submodules():
    body = _func("_build_module_tree")
    assert 'entry.get("is_pkg")' in body, (
        "packages with a re-export-only __init__ still answer count: 0")


# ── fs reaches the REPL ────────────────────────────────────────────────

def test_fsinsights_is_in_the_repl_namespace():
    """Every other geeViz lib has a handle (gil, sal, cl, tl, rl). This
    one did not, so the full FIA API — including the seven estimate()
    parameters the MCP tool does not expose — was reachable only by
    guessing the import path."""
    assert 'from geeViz import fsInsights as fs' in CODE
    assert '_ns_update["fs"] = fs' in CODE


def test_a_failed_fsinsights_import_does_not_put_none_in_the_namespace():
    """Matches the gm treatment: a None under an importable-looking name
    turns a clear NameError into an AttributeError on every call."""
    assert "if fs is not None:" in CODE


# ── the content half: the word has to be in the prose ──────────────────

FIA = (ROOT / "fsInsights" / "fia.py").read_text(encoding="utf-8")


def test_evalidator_is_named_in_public_documentation():
    """It appeared only in comments and one PRIVATE function's
    docstring, so no amount of index work could surface it under the
    name people actually use."""
    tree = ast.parse(FIA)
    mod_doc = ast.get_docstring(tree) or ""
    assert "EVALIDator" in mod_doc, "fia.py's module docstring never says it"

    public = {n.name: (ast.get_docstring(n) or "")
              for n in tree.body
              if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")}
    for fn in ("estimate", "validate"):
        assert fn in public, f"{fn} is not a public function of fia.py"
        assert "EVALIDator" in public[fn], (
            f"{fn}() never names EVALIDator in its docstring")


# ── the front door matches what search advertises ──────────────────────

@pytest.mark.parametrize("fn", [
    "compare_area", "fia_forest_area", "lcms_tree_area",
    "summarize_comparison",
    "lcms_asset_id", "lcms_ee_collection", "lcms_class_properties",
])
def test_advertised_functions_are_actually_reachable(fn):
    """search_codebase indexes align.py and lcms_ee.py by reading the
    files, but __init__ never imported them — so it advertised
    fs.compare_area while the attribute did not exist. align.py is the
    package docstring's own headline feature."""
    from geeViz import fsInsights as fs
    assert hasattr(fs, fn), f"fs.{fn} is advertised by search but missing"
    assert fn in fs.__all__, f"{fn} is reachable but not in __all__"


# ── a fully qualified name resolves ────────────────────────────────────
#
# Found by driving the real agent, not by reading code: two of five probe
# sessions called search_codebase(name="geeViz.fsInsights.fia.estimate")
# and got "not found in any geeViz module". The dotted-name branch split
# on the FIRST dot, so the module part became "geeViz" — which is not
# itself in the tree.
#
# `module=` had always accepted the prefix, so the two arguments
# disagreed about the same name. It predates the index work (
# "geeViz.getImagesLib.simpleMask" failed the same way), but making
# modules discoverable by full path is what taught the agent to produce
# the spelling.

def test_a_multi_segment_module_prefix_is_tried():
    body = _func("search_codebase")
    assert re.search(r"for _i in range\(len\(_segs\) - 1, 0, -1\)", body), (
        "the dotted-name lookup still assumes the module is one segment, "
        "so fully qualified names fail")


def test_the_prefix_walk_is_longest_first():
    """Shortest-first would bind 'geeViz.fsInsights' before
    'geeViz.fsInsights.fia' and resolve the attribute off the wrong
    module."""
    body = _func("search_codebase")
    m = re.search(r"range\(len\(_segs\) - 1, 0, (-1)\)", body)
    assert m, "prefix walk is not a descending range"


def test_the_prefix_walk_runs_after_the_original_attempt():
    """It must be additive — anything that resolved before still has to
    resolve the same way, so the walk cannot precede the single-segment
    branch."""
    body = _func("search_codebase")
    first = body.index("mod_name, attr_path = parts[0], parts[1]")
    walk = body.index("for _i in range(len(_segs) - 1, 0, -1)")
    assert first < walk, "the prefix walk shadows the original lookup"


# ── str_filter needs the full table name ───────────────────────────────
#
# Found by driving the agent: `str_filter="p.unitcd in (0, 1, 2)"` — the
# alias spelling used in FIA's own docs and in the db_column values that
# find_groupings returns (P., C., PG.) — makes EVALIDator answer HTTP 200
# with an "Internal Server Error - SQL Error" HTML page. `plot.unitcd`
# works. Verified live: plot.* returns 7 rows, p.* raises UpstreamError.
#
# The error names nothing about aliases, so two separate sessions spent
# several turns brute-forcing it. The parameter was documented as
# "SQL-style filter passed through as strFilter" and nothing more.

def test_str_filter_documents_the_table_name_requirement():
    tree = ast.parse(FIA)
    doc = ""
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name == "estimate":
            doc = ast.get_docstring(n) or ""
    assert doc, "estimate() has no docstring"
    assert "str_filter" in doc
    assert "plot.unitcd" in doc, (
        "str_filter does not show a WORKING example; the obvious "
        "spelling (p.unitcd) fails with an opaque upstream error")
    assert "NOT" in doc or "not accepted" in doc.lower(), (
        "the docstring does not warn that the short aliases fail")


# ── the agent must be pointed at a live LCMS collection ────────────────
#
# A probe session asked for the "animated map with a synced chart"
# starter prompt and the agent reached for USFS/GTAC/LCMS/v2024-10 —
# deprecated in the catalog, 1985-2024, one year short — then ran the
# whole 40-frame series and timed out. It learned the id from
# agent-instructions.md, which is read every session and also stated
# the wrong year range ("1985→2023" for a collection that ends 2024).
#
# This file's other tests are about finding things; this one is about
# being pointed at the right thing in the first place.

INSTR = (ROOT / "mcp" / "agent-instructions.md").read_text(encoding="utf-8")


def test_instructions_name_the_current_lcms_collection():
    assert "LCMS/Product_Version/2025-11" in INSTR, (
        "agent-instructions.md does not name the current LCMS collection")


def test_the_lcms_code_example_is_not_deprecated():
    """The worked example is copied verbatim more often than the table
    row is read."""
    for line in INSTR.splitlines():
        if "ee.ImageCollection(" in line and "LCMS" in line:
            assert "USFS/GTAC/LCMS" not in line, (
                f"a runnable LCMS example still uses a deprecated id: "
                f"{line.strip()[:120]}")


def test_no_lcms_year_range_ends_before_2025():
    """The defaults table was corrected to 1985→2025 but the
    "Known dataset coverage" list still said "LCMS: 1985 → 2023", telling
    an agent that 0 images for 2024 or 2025 was expected and to stop."""
    for line in INSTR.splitlines():
        if "LCMS" in line and re.search(r"1985\s*(→|->|-|–)\s*20\d\d", line):
            end = int(re.search(r"1985\s*(?:→|->|-|–)\s*(20\d\d)", line).group(1))
            assert end >= 2025, f"stale LCMS year range: {line.strip()[:120]}"


def test_the_hawaii_exception_survives():
    """Coverage is not monotonic: HAWAII and PRUSVI exist only in the
    older release, so a blanket 'always use the newest' instruction
    would break those. Deleting the caveat is the likely future
    mistake."""
    assert "v2024-10" in INSTR, (
        "the older release is no longer mentioned at all — work in "
        "Hawaii or Puerto Rico has no id to pin")
    low = INSTR.lower()
    assert "hawaii" in low or "puerto rico" in low, (
        "the non-monotonic coverage caveat is gone")
