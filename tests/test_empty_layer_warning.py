"""A layer that is masked everywhere in view must not validate silently.

From an askterra prod session (flash flooding near Ruidoso, NM): the
post-storm Sentinel-2 scenes were 97-99% cloudy, so the cloud-masked
median had no pixels at all. ``getMapId`` still succeeds on such an image,
``map_control(export)`` printed "PASS" for every layer, and the agent
described scour and inundation the map could not show. The user answered
"no layers are present in the map", then "the road layer loaded but
nothing else".

``testLayers`` now samples each image layer over the centered extent and
warns when nothing is unmasked; ``map_control`` prints those warnings
(it used to print only PASS/FAIL and drop every warning).
"""
import pytest


def _gv():
    # test_esriLib leaves a stub in sys.modules["geeViz.geeView"]; import
    # the real module around it without disturbing the stub (same approach
    # as test_api_spellings._real_geeview).
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


def _ee_ok():
    try:
        import ee
        ee.Number(1).getInfo()
        return True
    except Exception:
        try:
            _gv().robustInitializer()
            import ee
            ee.Number(1).getInfo()
            return True
        except Exception:
            return False


def _warnings(m, name):
    row = next(r for r in m.testLayers()["layers"] if r["name"] == name)
    assert row["status"] == "ok", row.get("error")
    return row.get("warnings") or []


def test_fully_masked_layer_warns_and_visible_layer_does_not():
    if not _ee_ok():
        pytest.skip("Earth Engine not reachable")
    import ee
    m = _gv().mapper()
    area = ee.Geometry.Point([-105.667, 33.331]).buffer(15000)
    m.addLayer(ee.Image.constant(1).updateMask(0), {"min": 0, "max": 1}, "all clouds")
    m.addLayer(ee.Image.constant(1), {"min": 0, "max": 1}, "visible")
    m.centerObject(area)
    assert any("No visible pixels" in w for w in _warnings(m, "all clouds"))
    assert not any("No visible pixels" in w for w in _warnings(m, "visible"))


def test_masked_outside_view_is_not_flagged_without_a_center():
    """With no centerObject there is no extent to judge; stay quiet."""
    if not _ee_ok():
        pytest.skip("Earth Engine not reachable")
    import ee
    m = _gv().mapper()
    m.addLayer(ee.Image.constant(1).updateMask(0), {"min": 0, "max": 1}, "all clouds")
    assert not any("No visible pixels" in w for w in _warnings(m, "all clouds"))


def test_map_control_export_prints_layer_warnings(tmp_path):
    import contextlib
    import io
    import geeViz.mcp.server as srv

    class _Map:
        idDictList = [{"name": "Post-Flood True Color"}]
        mapCommandList = []

        def testLayers(self):
            return {"pass": True, "layers": [{
                "name": "Post-Flood True Color", "status": "ok", "error": None,
                "warnings": ["No visible pixels in the map's centered extent"]}]}

        def export_html(self, path):
            return path

    class _Sess:
        output_dir = str(tmp_path)
        session_id = "t"

    for act in ("export", "view"):
        # The server replaces sys.stdout with a thread-local proxy, which
        # capsys cannot see; swap in our own buffer for the call.
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                srv._map_control_inner(_Map(), act, _Sess(), False,
                                       str(tmp_path / "m.html"), None)
            except Exception:
                pass  # `view` goes on to open a viewer; only the printed validation matters
        out = buf.getvalue()
        assert "PASS: Post-Flood True Color" in out, act
        assert "WARN: No visible pixels" in out, f"{act} dropped the layer warning:\n{out}"
