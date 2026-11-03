"""Map.addEsri* document themselves instead of pointing at esriLib.

From the daily review of 2026-11-03: the agent instructions say to draw
ArcGIS services with ``Map.addEsri*`` and never to import the deprecated
``geeViz.esriLib``. But ``search_codebase(name="Map.addEsriFeatureService")``
answered only "See ``geeViz.esriLib.addEsriFeatureService``. Delegates.",
so to learn ``where=``, ``bbox=`` or ``max_features=`` the agent had to look
the function up in esriLib, whose examples then show
``import geeViz.esriLib as el``. The regression case for drawing WFIGS
perimeters failed 3 runs of 3 on that detour.

Drives the real tool, not a copy of its logic.
"""
import json

import pytest

WRAPPERS = ["addEsriFeatureService", "addEsriMapService",
            "addEsriImageService", "addEsriService"]


@pytest.fixture(scope="module")
def srv():
    import geeViz.mcp.server as _srv
    _srv._build_module_tree()
    return _srv


def _doc(srv, name):
    fn = getattr(srv.search_codebase, "fn", srv.search_codebase)
    res = json.loads(fn(name=f"Map.{name}"))
    return res.get("docstring") or ""


@pytest.mark.parametrize("name", WRAPPERS)
def test_the_map_method_does_not_send_the_reader_to_esrilib(srv, name):
    doc = _doc(srv, name)
    assert doc, f"Map.{name} has no docstring in search_codebase"
    assert "esriLib" not in doc, (
        f"Map.{name}'s docstring names esriLib, the deprecated module the "
        f"instructions forbid importing: {doc[:200]!r}")


@pytest.mark.parametrize("name", WRAPPERS)
def test_the_map_method_documents_its_own_arguments(srv, name):
    import inspect
    import geeViz.geeView as gv
    doc = _doc(srv, name)
    params = [p for p in inspect.signature(getattr(gv.mapper, name)).parameters
              if p != "self"]
    # An Args entry ("    where (str, optional): ..."), not the word
    # appearing anywhere: "name" and "where" turn up in any prose.
    import re
    missing = [p for p in params
               if not re.search(rf"^\s+{p} \(", doc, re.MULTILINE)]
    assert not missing, f"Map.{name} does not document {missing}"


@pytest.mark.parametrize("name", WRAPPERS)
def test_the_example_calls_it_on_map(srv, name):
    assert f"Map.{name}(" in _doc(srv, name)
