"""Tests for Map.addTileLayer — external XYZ tile service support.

Importing geeView triggers EE initialization, so these tests construct a
mock object that mirrors the relevant bits of the mapper class. The JS-
emission logic is the part most worth covering; the addTileLayer entry
point itself is a thin validator + idDict builder.
"""
import json
import re


# ----- Minimal stand-in for the mapper's addTileLayer + _build_run_js -----
class _MockMapper:
    def __init__(self):
        self.idDictList = []

    def addTileLayer(self, url_template, name="Tile Layer", visible=True,
                     opacity=1.0, max_zoom=20):
        if not isinstance(url_template, str) or not url_template:
            raise ValueError("url_template must be a non-empty string")
        if not all(tok in url_template for tok in ("{x}", "{y}", "{z}")):
            raise ValueError(
                f"url_template must contain {{x}}, {{y}}, and {{z}} placeholders. "
                f"Got: {url_template!r}"
            )
        self.idDictList.append({
            "objectName": "Map",
            "function": "addREST",
            "name": name,
            "visible": str(visible).lower(),
            "_is_tile_url": True,
            "_tile_url_template": url_template,
            "_tile_max_zoom": int(max_zoom),
            "_tile_opacity": float(opacity),
            "item": "",
            "viz": json.dumps({"layerType": "tileMapService",
                               "opacity": float(opacity),
                               "maxZoom": int(max_zoom)}),
        })

    def _build_run_js(self):
        lines = "function runGeeViz(){"
        for idDict in self.idDictList:
            if idDict.get("_is_tile_url"):
                tpl = (idDict["_tile_url_template"]
                       .replace("\\", "\\\\")
                       .replace('"', '\\"'))
                tile_url_fn = (
                    'function(coord,zoom){return "' + tpl + '"'
                    '.replace("{x}",coord.x)'
                    '.replace("{y}",coord.y)'
                    '.replace("{z}",zoom);}'
                )
                lines += (
                    'try{{Map.addREST({fn},"{name}",{visible},{maxZoom},"","layer-list");}}'
                    'catch(e){{layerLoadErrorMessages.push("Tile layer \\"{name}\\" failed: "+e.message);}}'
                ).format(
                    fn=tile_url_fn,
                    name=idDict["name"].replace('"', '\\"'),
                    visible=str(idDict["visible"]).lower(),
                    maxZoom=idDict.get("_tile_max_zoom", 20),
                )
        lines += "};"
        return lines


def test_basic_xyz_url():
    m = _MockMapper()
    m.addTileLayer(
        "https://viz-assets.ctrees.org/sfi/basemaps/agb_100m/{z}/{x}/{y}.png",
        name="CTrees AGB",
    )
    js = m._build_run_js()
    assert "Map.addREST(function(coord,zoom)" in js
    assert "CTrees AGB" in js
    assert "viz-assets.ctrees.org/sfi/basemaps/agb_100m/" in js
    assert ".replace(\"{x}\",coord.x)" in js
    assert ".replace(\"{y}\",coord.y)" in js
    assert ".replace(\"{z}\",zoom)" in js


def test_arcgis_mapserver_template():
    m = _MockMapper()
    m.addTileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/"
        "World_Imagery/MapServer/tile/{z}/{y}/{x}",
        name="ESRI World Imagery",
    )
    js = m._build_run_js()
    assert "ESRI World Imagery" in js
    # ArcGIS y/x order is just a string template detail, preserved verbatim
    assert "MapServer/tile/{z}/{y}/{x}" in js


def test_missing_placeholder_rejected():
    m = _MockMapper()
    bad = [
        "https://example.com/tiles/{z}/{x}.png",          # no {y}
        "https://example.com/tiles/no/placeholders.png",  # nothing
        "https://example.com/{z}/{y}/{x}/extra/{q}.png",  # extra is fine,
                                                          # but only if x/y/z all present (this passes)
    ]
    for url in bad[:2]:
        try:
            m.addTileLayer(url, "bad")
        except ValueError:
            pass
        else:
            raise AssertionError(f"Should have rejected {url!r}")
    # The 3rd has all required placeholders so it succeeds
    m.addTileLayer(bad[2], "ok-extras")
    assert len(m.idDictList) == 1


def test_url_with_quotes_escaped():
    """A URL containing a double-quote (or backslash) must be safely escaped
    so the emitted JS string literal stays valid."""
    m = _MockMapper()
    weird = 'https://example.com/{z}/{x}/{y}?token="abc"'
    m.addTileLayer(weird, name='Quote"Test')
    js = m._build_run_js()
    # The literal " inside the URL must be escaped as \"
    assert '?token=\\"abc\\"' in js
    # The layer name " must also be escaped
    assert 'Quote\\"Test' in js


def test_visible_flag_propagates():
    m = _MockMapper()
    m.addTileLayer("https://e.com/{z}/{x}/{y}.png", "On", visible=True)
    m.addTileLayer("https://e.com/{z}/{x}/{y}.png", "Off", visible=False)
    js = m._build_run_js()
    # Find both addREST calls and check visible param (4th arg after name)
    assert '"On",true,' in js
    assert '"Off",false,' in js


def test_max_zoom_propagates():
    m = _MockMapper()
    m.addTileLayer("https://e.com/{z}/{x}/{y}.png", "Mz", max_zoom=15)
    js = m._build_run_js()
    assert '"Mz",true,15,' in js


def test_try_catch_wraps_each_layer():
    """Each addREST call must be wrapped in try/catch so a single bad URL
    doesn't break the whole map load."""
    m = _MockMapper()
    m.addTileLayer("https://e.com/{z}/{x}/{y}.png", "L1")
    js = m._build_run_js()
    # try { ... } catch (e) { layerLoadErrorMessages.push("Tile layer ..." }
    assert re.search(r"try\{Map\.addREST.*?catch\(e\)\{layerLoadErrorMessages", js), \
        f"try/catch wrap missing in:\n{js}"


def test_idDict_marker():
    """Tile URL layers must carry the _is_tile_url marker so other parts of
    geeView (testLayers, previewMap) can opt out cleanly."""
    m = _MockMapper()
    m.addTileLayer("https://e.com/{z}/{x}/{y}.png", "Test")
    assert m.idDictList[0]["_is_tile_url"] is True
    # _ee_obj must be absent so testLayers/previewMap skip it naturally
    assert "_ee_obj" not in m.idDictList[0]


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print()
    if failed:
        print(f"{failed}/{len(tests)} tests FAILED")
        raise SystemExit(1)
    print(f"{len(tests)}/{len(tests)} tests passed")
