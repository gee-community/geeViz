"""Map.addLayer takes Earth Engine's own argument order.

The Code Editor's ``Map.addLayer(eeObject, visParams, name, shown,
opacity)`` is what the agent writes from habit; geeViz stopped at
``shown``, so a fifth positional argument raised
``addLayer() takes from 2 to 5 positional arguments but 6 were given``
and cost the turn a retry.
"""
import json


def _gv():
    # test_esriLib leaves a stub in sys.modules["geeViz.geeView"]; import
    # the real module around it without disturbing the stub (same approach
    # as test_empty_layer_warning._gv).
    import importlib
    import sys
    import geeViz
    mod = sys.modules.get("geeViz.geeView")
    if mod is not None and hasattr(mod, "mapper"):
        return mod
    saved = sys.modules.pop("geeViz.geeView", None)
    had = hasattr(geeViz, "geeView")
    prev = getattr(geeViz, "geeView", None)
    try:
        return importlib.import_module("geeViz.geeView")
    finally:
        if saved is not None:
            sys.modules["geeViz.geeView"] = saved
        if had:
            geeViz.geeView = prev
        elif hasattr(geeViz, "geeView"):
            del geeViz.geeView


# A GeoJSON layer goes through addLayer without touching Earth Engine.
_GEOJSON = {"type": "FeatureCollection", "features": []}


def _viz(m):
    return json.loads(m.idDictList[-1]["viz"])


def test_fifth_positional_argument_is_opacity():
    m = _gv().mapper()
    m.addLayer(_GEOJSON, {"palette": ["000000"]}, "hillshade", True, 0.4)
    assert _viz(m)["opacity"] == 0.4
    assert m.idDictList[-1]["visible"] == "true"


def test_opacity_keyword_overrides_viz():
    m = _gv().mapper()
    m.addLayer(_GEOJSON, {"opacity": 0.9}, "x", opacity=0.25)
    assert _viz(m)["opacity"] == 0.25


def test_without_opacity_viz_is_unchanged():
    m = _gv().mapper()
    m.addLayer(_GEOJSON, {"opacity": 0.7}, "x")
    assert _viz(m)["opacity"] == 0.7
    m.addLayer(_GEOJSON, {}, "y")
    assert "opacity" not in _viz(m)
