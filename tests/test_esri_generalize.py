"""Esri Feature Service layers are thinned to display resolution.

addEsriFeatureService fetches GeoJSON and embeds it in the map page. A
USFS Region 6 landtype-association layer -- 1,619 polygons, 1.76 million
vertices at 15 decimal places, about 0.7 m apart -- made a 70.8 MB page
that the agent silently refused to attach, so the user never saw a map.
Nobody can see sub-meter detail on a web map, so by default ("auto") a
layer over its byte budget is rounded and Douglas-Peucker simplified at
increasing tolerances until it fits; a layer already under budget is left
exactly as fetched.
"""
import json

import pytest


def _el():
    # Run-time import, and the SAME module object everyone else holds --
    # re-importing a fresh copy would strand other tests' patches.
    import geeViz.esriLib as el
    return el


def _wiggly_ring(n, cx=-120.0, cy=44.0, r=0.05):
    """A closed ring with n near-collinear vertices plus real corners."""
    import math
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        # square-ish outline with sub-meter jitter the eye can't see
        jitter = 1e-6 * ((i * 7919) % 13 - 6)
        pts.append([cx + r * math.cos(a) + jitter, cy + r * math.sin(a) + jitter])
    pts.append(list(pts[0]))
    return pts


def _fc(n_polys=40, verts=4000):
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"id": i},
         "geometry": {"type": "Polygon",
                      "coordinates": [_wiggly_ring(verts, cx=-120 + i * 0.2)]}}
        for i in range(n_polys)]}


def _size(gj):
    return len(json.dumps(gj, separators=(",", ":")))


def test_generalize_keeps_rings_valid():
    el = _el()
    out = el._generalize_geojson(_fc(3, 5000), tolerance_m=30, precision=6)
    for f in out["features"]:
        ring = f["geometry"]["coordinates"][0]
        assert len(ring) >= 4, "a polygon ring needs at least 4 positions"
        assert ring[0] == ring[-1], "ring must stay closed"
        assert len(ring) < 5000


def test_auto_leaves_a_small_layer_untouched():
    el = _el()
    small = _fc(2, 20)
    out, note = el._fit_geojson_for_display(small, simplify="auto",
                                            budget_bytes=5_000_000)
    assert out == small and note is None, "under budget must be byte-identical"


def test_auto_shrinks_a_large_layer_under_budget():
    el = _el()
    big = _fc(40, 4000)
    budget = _size(big) // 10
    out, note = el._fit_geojson_for_display(big, simplify="auto",
                                            budget_bytes=budget)
    assert _size(out) <= budget
    assert note and "m" in note, "must say what resolution it simplified to"
    assert len(out["features"]) == len(big["features"]), "never drops features"


def test_simplify_false_never_alters_geometry():
    el = _el()
    big = _fc(10, 4000)
    out, note = el._fit_geojson_for_display(big, simplify=False, budget_bytes=10)
    assert out == big and note is None


def test_properties_survive_simplification():
    el = _el()
    big = _fc(5, 4000)
    out, _ = el._fit_geojson_for_display(big, simplify=30, budget_bytes=10**9)
    assert [f["properties"] for f in out["features"]] == \
           [f["properties"] for f in big["features"]]


class _FakeMap:
    def __init__(self):
        self.added = []

    def addLayer(self, obj, viz, name):
        self.added.append((obj, viz, name))


def test_addEsriFeatureService_applies_it(monkeypatch):
    """Wiring: the fetch result must actually pass through the thinning."""
    el = _el()
    from georest.restesri import services as gs
    big = _fc(40, 4000)
    monkeypatch.setattr(gs, "queryFeatureService", lambda *a, **k: big)
    monkeypatch.setattr(el, "_check_url", lambda u: None)
    m = _FakeMap()
    budget = _size(big) // 10
    el.addEsriFeatureService("https://example.test/arcgis/rest/services/X/FeatureServer/0",
                             name="LTAs", target_map=m,
                             max_layer_mb=budget / (1024 * 1024))
    (obj, viz, name), = m.added
    assert _size(obj) <= budget
    assert viz["layerType"] == "geoJSONVector"


def test_addEsriService_feature_branch_honors_target_map(monkeypatch):
    """The dispatcher forwarded everything to addEsriFeatureService EXCEPT
    target_map, so an auto-dispatched feature layer landed on the global
    gv.Map instead of the map it was asked to go on."""
    el = _el()
    from georest.restesri import services as gs
    monkeypatch.setattr(gs, "queryFeatureService", lambda *a, **k: _fc(1, 10))
    monkeypatch.setattr(el, "_check_url", lambda u: None)
    monkeypatch.setattr(el, "_detect_service_type", lambda u: "FeatureServer")
    m = _FakeMap()
    el.addEsriService("https://example.test/arcgis/rest/services/X/FeatureServer/0",
                      name="LTAs", target_map=m, bbox="-121,43,-119,45")
    assert len(m.added) == 1, "layer did not reach the requested map"


def _real_geeview():
    """The real geeView module even while test_esriLib's stub is installed
    (it is, if this runs before that file's teardown)."""
    import importlib
    import sys
    mod = sys.modules.get("geeViz.geeView")
    if mod is not None and hasattr(mod, "mapper"):
        return mod
    import geeViz
    saved = sys.modules.pop("geeViz.geeView", None)
    had_attr = hasattr(geeViz, "geeView")
    saved_attr = getattr(geeViz, "geeView", None)
    try:
        return importlib.import_module("geeViz.geeView")
    finally:
        # Put BOTH back. Importing a submodule also rebinds it as an
        # attribute on the package, and `import geeViz.geeView as gv`
        # resolves through that attribute -- restoring only sys.modules
        # left test_esriLib reaching the real module past its stub.
        if saved is not None:
            sys.modules["geeViz.geeView"] = saved
        # test_esriLib stubs sys.modules only, so the package usually had
        # NO geeView attribute before this import. Put that absence back
        # too, or the real module stays reachable through it.
        if had_attr:
            geeViz.geeView = saved_attr
        elif hasattr(geeViz, "geeView"):
            del geeViz.geeView


def test_mapper_wrappers_accept_the_new_options():
    import inspect
    gv = _real_geeview()
    for fn in (gv.mapper.addEsriFeatureService, gv.mapper.addEsriService):
        params = inspect.signature(fn).parameters
        assert "simplify" in params and "bbox" in params, fn.__name__
