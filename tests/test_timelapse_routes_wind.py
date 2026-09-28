"""A wind collection handed to ``Map.addTimeLapse`` must still animate.

Seen in a real session: asked for "an animated map of the wind forecast
over the Gulf of Mexico", the agent called
``Map.addTimeLapse(gfs_wind, {"units": "kt", "particleDensity": 1.5})``
instead of ``Map.addWindTimeLapse``. Nothing raised. The viewer applied
``addTimeLapse``'s ``"YYYY"`` default, collapsed thirteen six-hourly
frames into one 2026 mosaic, and drew a raw u/v image with no stretch --
so the map showed the basemap and nothing else.

The viz carried keys that only mean something to the wind renderer.
``addTimeLapse`` now sees them and hands the call to
``addWindTimeLapse``. The wind helpers call ``addTimeLapse`` themselves,
always with the internal ``windParticles`` marker, and that must NOT
route or it would recurse.
"""
import pytest


def _real_geeview():
    """The real geeView module even while test_esriLib's stub is installed."""
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
        if saved is not None:
            sys.modules["geeViz.geeView"] = saved
        if had_attr:
            geeViz.geeView = saved_attr
        elif hasattr(geeViz, "geeView"):
            delattr(geeViz, "geeView")


@pytest.mark.parametrize("viz", [
    {"units": "kt", "opacity": 0.8, "particleDensity": 1.5},   # the session
    {"units": "mph"},
    {"units": "m/s"},
    {"particleColor": "#fff"},
    {"windSpeedOpacity": 0.4},
    {"directionConvention": "to"},
])
def test_wind_only_keys_mark_a_wind_lapse(viz):
    assert _real_geeview()._is_wind_timelapse_viz(viz)


@pytest.mark.parametrize("viz", [
    {},
    {"min": 0, "max": 30, "palette": "000,fff", "dateFormat": "YYYYMMdd HH"},
    {"autoViz": True, "mosaic": True},
    {"units": "mm"},                  # precipitation, not speed
    {"units": "degC"},
    # What addWindTimeLapse itself passes back into addTimeLapse: routing
    # this would recurse forever.
    {"windParticles": True, "windUnits": "kt", "particleDensity": 1.2,
     "units": "kt", "layerType": "geeImage"},
])
def test_other_lapses_and_internal_calls_do_not(viz):
    assert not _real_geeview()._is_wind_timelapse_viz(viz)


def test_addTimeLapse_hands_a_wind_viz_to_addWindTimeLapse(monkeypatch):
    """The wiring, not just the predicate: the call is delegated with the
    caller's collection, viz, name and visibility, and its result returned."""
    gv = _real_geeview()
    import geeViz.weather as wx

    seen = {}

    def fake(Map, collection, viz=None, name="Wind", visible=True, **kw):
        seen.update(Map=Map, collection=collection, viz=viz, name=name,
                    visible=visible)
        return "speed_ic", "tiles_ic"

    monkeypatch.setattr(wx, "addWindTimeLapse", fake)

    class _Self:
        """Would fail loudly if addTimeLapse fell through to its body."""
        def __getattr__(self, item):
            raise AssertionError(f"addTimeLapse body ran (touched {item!r})")

    me, coll = _Self(), object()
    viz = {"units": "kt", "opacity": 0.8, "particleDensity": 1.5}
    out = gv.mapper.addTimeLapse(me, coll, viz, "Gulf Wind Forecast (3-Day)", False)

    assert out == ("speed_ic", "tiles_ic")
    assert seen["Map"] is me and seen["collection"] is coll
    assert seen["viz"] == viz
    assert seen["name"] == "Gulf Wind Forecast (3-Day)"
    assert seen["visible"] is False
