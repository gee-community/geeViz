"""A method on a class inside pandas, numpy or ee resolves however it is spelled.

The tool's own instructions tell the model to look up
``pd.DataFrame.to_markdown`` before using it, and that spelling worked.
The two shorter spellings a model also writes did not (2026-10-26):

    search_codebase(name="DataFrame.to_markdown")        -> not found
    search_codebase(name="to_markdown", module="pd")     -> not found

Only geeViz's own classes were tried as the first segment of a dotted
name, and a module-scoped lookup only tried ``pd.to_markdown``. A "not
found" for a real method is read as "it does not exist", which is the
reason the model reaches for ``import inspect`` instead.

Drives the real tool, not a copy of its logic.
"""
import json

import pytest


@pytest.fixture(scope="module")
def srv():
    import geeViz.mcp.server as _srv
    _srv._build_module_tree()
    return _srv


def _search(srv, **kw):
    fn = getattr(srv.search_codebase, "fn", srv.search_codebase)
    return json.loads(fn(session_id="search-class-in-module", **kw))


@pytest.mark.parametrize("kw", [
    {"name": "pd.DataFrame.to_markdown"},                 # already worked
    {"name": "DataFrame.to_markdown"},
    {"name": "to_markdown", "module": "pd"},
    {"name": "to_markdown", "module": "pandas"},
    {"name": "to_markdown"},
])
def test_each_spelling_finds_the_method(srv, kw):
    out = _search(srv, **kw)
    assert "error" not in out, out
    assert "to_markdown(" in out.get("signature", ""), out


def test_the_spellings_agree(srv):
    full = _search(srv, name="pd.DataFrame.to_markdown")
    short = _search(srv, name="DataFrame.to_markdown")
    # The signature opens with the name as asked; the parameters must match.
    assert short["signature"].split("(", 1)[1] == full["signature"].split("(", 1)[1]


def test_a_method_on_several_classes_names_the_others(srv):
    out = _search(srv, name="to_markdown", module="pd")
    assert "Series.to_markdown" in out.get("also_on", []) + [out.get("name")], out


def test_an_ee_class_method_resolves_without_the_prefix(srv):
    out = _search(srv, name="Image.reduceRegion")
    assert "error" not in out, out
    assert "reduceRegion" in json.dumps(out)


def test_a_geeviz_function_still_wins_over_a_loaded_module(srv):
    out = _search(srv, name="simpleMask")
    assert out.get("module") == "getImagesLib", out


def test_a_missing_method_still_says_not_found(srv):
    for kw in ({"name": "DataFrame.noSuchMethod"},
               {"name": "noSuchMethodAnywhere", "module": "pd"},
               {"name": "noSuchMethodAnywhere"}):
        assert "not found" in _search(srv, **kw).get("error", ""), kw
