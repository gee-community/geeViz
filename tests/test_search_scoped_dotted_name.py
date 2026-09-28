"""A dotted name must resolve when a module is ALSO given.

From askterra prod sessions: the agent called

    search_codebase(name="mapper.addLayer", module="geeView")

and was told "'mapper.addLayer' not found in geeView." -- about a method
every map in the product calls. Same for mapper.exportLayerJson and
mapper.export_html. Without ``module=`` the same name resolved, so the two
spellings disagreed about whether the function exists, and the agent
concluded it didn't and started guessing. The module-scoped branch did a
single ``getattr(module, "mapper.addLayer")`` -- a dotted string is never
an attribute name, so it could not succeed.

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
    return json.loads(fn(**kw))


@pytest.mark.parametrize("name,module", [
    ("mapper.addLayer", "geeView"),
    ("mapper.exportLayerJson", "geeView"),
    ("mapper.export_html", "geeView"),
    ("mapper.addLayer", "geeViz.geeView"),
    ("geeView.mapper.addLayer", "geeView"),      # name repeats the module
    ("addEsriFeatureService", "esriLib"),         # plain name still works
])
def test_a_scoped_dotted_name_resolves(srv, name, module):
    out = _search(srv, name=name, module=module)
    assert "error" not in out, out.get("error")
    assert out.get("signature") or out.get("docstring")


def test_scoped_and_unscoped_lookups_agree(srv):
    """The two spellings must never disagree about whether a thing exists."""
    a = _search(srv, name="mapper.addLayer")
    b = _search(srv, name="mapper.addLayer", module="geeView")
    assert ("error" in a) == ("error" in b)
    assert a.get("signature") == b.get("signature")


def test_a_missing_scoped_name_still_says_not_found(srv):
    out = _search(srv, name="mapper.noSuchMethodAnywhere", module="geeView")
    assert "not found" in out.get("error", "")
