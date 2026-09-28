"""opacity=0 is a legitimate display setting, not an invalid layer.

In geeView ``opacity`` is where a layer's slider starts; the browser
applies it client-side and never sends it to Earth Engine. But the Python
validator, the preview renderer and the dashboard-JSON export all copied
it into getMapId's visualization params, and Earth Engine's own opacity
must be in (0, 1]:

    Image.visualize: Scale must be greater than zero and less than or
    equal to one, but was 0.0.

From an askterra prod session: the agent drew the wind speed as its own
layer and, sensibly, set ``windSpeedOpacity: 0.0`` on the wind layer
("speed is already shown by Layer 3 above"). test_layers reported that
layer as an ERROR, so the agent deleted a layer that would have rendered.
"""
import pytest


def _gv():
    # Run-time import: test_esriLib stubs this module during collection.
    import geeViz.geeView as gv
    return gv


@pytest.mark.parametrize("opacity,kept", [
    (0, False), (0.0, False), (-0.2, False), (1.5, False),
    (0.5, True), (1, True), (1.0, True),
])
def test_only_opacities_earth_engine_accepts_are_forwarded(opacity, kept):
    p = _gv()._ee_viz_params({"min": 0, "max": 1, "opacity": opacity,
                              "layerType": "geeImage", "autoViz": True})
    assert ("opacity" in p) is kept
    assert p["min"] == 0 and p["max"] == 1
    assert "layerType" not in p and "autoViz" not in p, "viewer-only keys leak"


def test_no_site_copies_opacity_into_ee_params_by_hand():
    """All three copies must go through the helper; a fourth hand-rolled
    copy would reintroduce the false failure."""
    import inspect
    import re
    src = inspect.getsource(_gv())
    body = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    hand = re.findall(r'\("bands", "min", "max", "gain", "bias", "gamma", "palette", "opacity", "format"\)', body)
    assert len(hand) <= 1, f"{len(hand)} hand-rolled viz-key copies remain; use _ee_viz_params"


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


def test_a_zero_opacity_layer_passes_validation():
    if not _ee_ok():
        pytest.skip("Earth Engine not reachable")
    import ee
    gv = _gv()
    m = gv.mapper()
    m.addLayer(ee.Image.constant(1), {"min": 0, "max": 1, "opacity": 0}, "hidden speed")
    results = m.testLayers()
    rows = results if isinstance(results, list) else results.get("layers", [])
    row = next(r for r in rows if r["name"] == "hidden speed")
    assert row["status"] == "ok", row.get("error")
