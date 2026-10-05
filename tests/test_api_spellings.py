"""Spellings people actually use must work, not raise.

Both from askterra prod sessions, both costing the agent a failed call and
a retry:

* ``units='mph'`` raised ``units must be one of ['km/hr', 'kt', 'm/s',
  'mi/hr']``. "mph" is how every weather product and every person writes
  it; "mi/hr" is the spelling nobody types first.
* ``Map.addEsriMapService(url, name=..., visible=False)`` raised
  ``unexpected keyword argument 'visible'`` -- every other ``add*`` on the
  map takes ``visible``, so the agent reasonably assumed this one did.
"""
import inspect

import pytest


def _real_geeview():
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


@pytest.fixture(scope="module")
def wx():
    """geeViz.weather builds Earth Engine objects at import time, so EE has
    to be initialized first -- in a full run nothing may have done that yet.
    Same approach as the other weather tests; imported here, not at the top,
    because test_esriLib stubs geeViz.geeView during collection."""
    import ee
    try:
        ee.Number(1).getInfo()
    except Exception:
        # Through _real_geeview(): this file sorts BEFORE test_esriLib, whose
        # stub is still installed here, so a plain import finds no
        # robustInitializer -- and that was being read as "EE unavailable",
        # silently skipping every test that uses this fixture.
        try:
            _real_geeview().robustInitializer()
            ee.Number(1).getInfo()
        except Exception as exc:
            pytest.skip(f"Earth Engine not available: {exc}")
    import geeViz.weather as _wx
    return _wx



@pytest.mark.parametrize("given,canonical", [
    ("mph", "mi/hr"), ("MPH", "mi/hr"), ("mi/h", "mi/hr"), ("mi/hr", "mi/hr"),
    ("kph", "km/hr"), ("km/h", "km/hr"), ("kmh", "km/hr"), ("km/hr", "km/hr"),
    ("knots", "kt"), ("knot", "kt"), ("kts", "kt"), ("kn", "kt"), ("kt", "kt"),
    ("mps", "m/s"), ("m/s", "m/s"), ("M/S", "m/s"),
])
def test_speed_unit_aliases(wx, given, canonical):
    assert wx._speed_units(given) == canonical


def test_an_unknown_unit_still_raises_and_lists_what_works(wx):
    with pytest.raises(ValueError) as ei:
        wx._speed_units("furlongs/fortnight")
    assert "mph" in str(ei.value), "the error should show the friendly spellings"


def test_both_wind_entry_points_use_the_normalizer(wx):
    """windImage and addWindLayer each validated units on their own; a
    fix to one would leave the other raising."""
    src = inspect.getsource(wx)
    body = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    assert "if units not in SPEED_UNITS" not in body, (
        "a hand-rolled units check remains; route it through _speed_units")


def test_addEsriMapService_accepts_visible():
    gv = _real_geeview()
    import geeViz.esriLib as el
    for fn in (gv.mapper.addEsriMapService, el.addEsriMapService):
        assert "visible" in inspect.signature(fn).parameters, fn.__qualname__


def test_visible_reaches_the_layer(monkeypatch):
    """Wiring: an explicit visible= must end up where viz_params' did."""
    import geeViz.esriLib as el
    seen = {}

    def fake_image_service(url, name=None, token=None, viz_params=None, target_map=None, **_kw):
        seen["viz"] = dict(viz_params or {})

    from georest.restesri import portal as gp
    monkeypatch.setattr(el, "_check_url", lambda u: None)
    monkeypatch.setattr(gp, "getServiceMetadata",
                        lambda *a, **k: {"singleFusedMapCache": True})
    monkeypatch.setattr(el, "addEsriImageService", fake_image_service)
    el.addEsriMapService("https://example.test/arcgis/rest/services/X/MapServer",
                         name="FEMA", visible=False)
    assert seen["viz"].get("visible") is False
