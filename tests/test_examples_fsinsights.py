"""The shipped examples must use the API the way a reader should.

fsInsights_examples.ipynb is the only example that touches fsInsights —
audited across geeViz/examples, where the other apparent matches were
URLs (``apps.fs.usda.gov``, ``lcms-dashboard.fs2c.usda.gov`` contain
"fs." ) and the word "align" used for text alignment.

Being the only one is exactly why it needs pinning: there is no second
example to notice when it drifts, and it doubles as the package's
documentation.

Three things it got wrong before, each of which taught readers to do
the same:

1. It reached past the package — ``from geeViz.fsInsights import
   align`` — because __init__ never imported align or lcms_ee, so the
   submodule path was the ONLY thing that worked. Copying that is how a
   reader ends up depending on a private layout.
2. It pinned LCMS years to 2024 while the current release reached 2025.
3. Deprecated ``USFS/GTAC/LCMS/*`` ids, which still resolve but emit a
   DeprecationWarning and silently cost a year of data.
"""
import ast
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
NB = EXAMPLES / "fsInsights_examples.ipynb"


def _cells(kind):
    nb = json.loads(NB.read_text(encoding="utf-8"))
    return [(i, "".join(c["source"])) for i, c in enumerate(nb["cells"])
            if c["cell_type"] == kind]


CODE = "\n".join(s for _, s in _cells("code"))
PROSE = "\n".join(s for _, s in _cells("markdown"))


def _strip_comments(text: str) -> str:
    """Drop ``#`` comments so a test greps CODE, not commentary.

    Crude on purpose: a ``#`` inside a string literal goes too, which
    costs nothing here because every caller is looking for an identifier
    that would appear outside a string anyway.
    """
    # chr(10) rather than a newline escape: this file has been edited
    # through shell heredocs that mangle backslashes, and a literal
    # newline inside the quotes is a SyntaxError that only shows up at
    # collection time.
    return chr(10).join(ln.split("#", 1)[0] for ln in text.splitlines())


def test_the_notebook_exists():
    assert NB.is_file()


def test_it_is_still_the_only_example_using_fsinsights():
    """If a second one appears, it needs the same checks — this test is
    the reminder to extend the file rather than a claim that one example
    is the right number."""
    users = []
    for f in list(EXAMPLES.glob("*.py")) + list(EXAMPLES.glob("*.ipynb")):
        txt = f.read_text(encoding="utf-8", errors="replace")
        # Comments first, or this matches prose ABOUT fsInsights as
        # though it were a use of it. areaChart_examples explains that
        # geeViz normalizes LCMS class properties the same way
        # fsInsights.lcms_class_properties does, and that sentence alone
        # failed this test. The house rule is to strip comments before
        # asserting on source, and this is exactly why it exists.
        txt = _strip_comments(txt)
        # "fs.usda" / "fs2c" are URLs, not the fs handle.
        if re.search(r"\bfsInsights\b", txt) and "fsInsights_examples" not in f.name:
            users.append(f.name)
    assert not users, (
        f"new example(s) use fsInsights and are unaudited: {users}")


def test_every_fs_reference_is_a_public_export():
    """A reader copying ``fs.<thing>`` must land on supported API."""
    from geeViz import fsInsights as fs
    refs = sorted(set(re.findall(r"\bfs\.([A-Za-z_][A-Za-z0-9_]*)", CODE)))
    assert refs, "no fs.* references found — did the notebook change shape?"
    missing = [n for n in refs if not hasattr(fs, n)]
    unexported = [n for n in refs if hasattr(fs, n)
                  and n not in getattr(fs, "__all__", [])]
    assert not missing, f"notebook calls nonexistent fs.{missing}"
    assert not unexported, (
        f"notebook relies on fs.{unexported}, which is reachable but not "
        f"in __all__ — that is an accident waiting to be tidied away")


def test_it_does_not_reach_past_the_package():
    reach = re.findall(r"from geeViz\.fsInsights import \w+|"
                       r"geeViz\.fsInsights\.\w+", CODE)
    assert not reach, (
        f"example reaches into submodules instead of the fs handle: {reach}")


def test_no_deprecated_lcms_collection():
    dep = re.findall(r"USFS/GTAC/LCMS/v[\d-]+", CODE)
    assert not dep, f"deprecated LCMS ids in example code: {dep}"


def test_lcms_years_are_not_behind_the_data():
    """An example that stops a year short of the release reads as
    unmaintained. The current Land_Cover release runs through 2025."""
    years = sorted({int(y) for y in re.findall(r"year=(\d{4})", CODE)})
    assert years, "no year= arguments found"
    assert min(years) >= 2025, (
        f"example pins LCMS to {years}; the current release reaches 2025")


@pytest.mark.parametrize("cell_index,src", _cells("code"))
def test_every_code_cell_parses(cell_index, src):
    ast.parse(src)


def test_the_tree_canopy_trap_is_still_demonstrated():
    """release='2025-6' appearing in code is DELIBERATE — it is the
    'asking a tree-canopy release for land cover' demo, and a future
    sweep that 'fixes' it to the current release would delete the
    lesson."""
    assert "2025-6" in CODE, "the tree-canopy release trap demo is gone"


def test_prose_counts_match_the_bundled_catalogs():
    """The combinatorics line is the notebook's headline justification
    for why discovery matters. 1,129 is the FULL evaluation catalog —
    find_evaluations() defaults to most_recent=True and returns 59, so
    check against the catalog, not the default view."""
    from geeViz.fsInsights import vocab
    m = re.search(r"\*\*([\d,]+) x ([\d,]+) x ([\d,]+) x ([\d,]+)\*\*", PROSE)
    assert m, "the 752 x 96 x 96 x 1129 line is gone from the prose"
    attrs, grp1, grp2, evals = (int(x.replace(",", "")) for x in m.groups())
    assert grp1 == grp2, "the two grouping slots should be the same count"
    assert len(vocab.load_catalog("snum")) == attrs
    assert len(vocab.load_catalog("rselected")) == grp1
    assert len(vocab.load_catalog("wc")) == evals
