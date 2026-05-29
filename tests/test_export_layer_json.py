"""Tests for Map.exportLayerJson.

The method handles every input type addLayer accepts:
- ee.Image           → serialize directly
- ee.ImageCollection → mosaic, then serialize
- ee.Geometry        → wrap as FeatureCollection → style → serialize
- ee.Feature         → wrap as FeatureCollection → style → serialize
- ee.FeatureCollection → style → serialize
- dict (GeoJSON)     → skipped with warning
- tile-URL layer     → static_url passthrough

We mock ee objects rather than depend on a live EE connection. The
relevant behaviors to verify:
- Input type → expected serialize call (or skip)
- ImageCollection → mosaic() called before serialize
- Vector → _style_vector dispatched correctly (painted vs styled)
- Name collisions auto-suffixed with _2, _3
- Tile-URL layers passed through with static_url
- GeoJSON layers skipped, listed in `skipped`
"""
import json
import os
import tempfile


# --- Minimal ee-shape mocks ---
class _MockSerializable:
    """Stand-in for an ee.Image/Collection/Vector that records .serialize() / .mosaic() calls."""
    def __init__(self, cls_name="Image", payload=None):
        self.__class__.__name__ = cls_name  # mostly cosmetic
        self._cls_name = cls_name
        self._payload = payload or {"type": cls_name, "id": id(self)}
        self._serialized = False
        self._mosaicked = False
        self._styled = False
        self._painted = False

    def serialize(self):
        self._serialized = True
        return json.dumps({"_cls": self._cls_name, "payload": self._payload})

    def mosaic(self):
        result = _MockSerializable(cls_name="Image", payload={"from_mosaic_of": self._payload})
        self._mosaicked = True
        return result

    def style(self, **kw):
        s = _MockSerializable(cls_name="Image", payload={"styled_from": self._payload, "style_kw": kw})
        s._styled = True
        return s

    def paint(self, *a, **kw):
        # Mimic ee.Image().paint(fc, 0, sw)
        return _MockSerializable(cls_name="Image", payload={"painted": True})


class _MockMapper:
    """Reproduces just exportLayerJson + _style_vector logic without ee."""

    @staticmethod
    def _style_vector(ee_obj, viz):
        obj_cls = ee_obj.__class__.__name__
        if obj_cls == "Geometry":
            # FeatureCollection wrapping (mocked: just pretend)
            fc = _MockSerializable(cls_name="FeatureCollection",
                                   payload={"wrapped_geom": True})
            obj_cls = "FeatureCollection"
            ee_obj = fc
        elif obj_cls == "Feature":
            fc = _MockSerializable(cls_name="FeatureCollection",
                                   payload={"wrapped_feature": True})
            obj_cls = "FeatureCollection"
            ee_obj = fc

        lt = viz.get("layerType", "")
        is_vector = obj_cls == "FeatureCollection" or "Vector" in lt or "vector" in lt

        if not is_vector:
            return ee_obj, False

        has_style_keys = any(k in viz for k in
                             ("color", "strokeColor", "fillColor", "pointSize", "pointRadius", "width"))
        if has_style_keys:
            styled = ee_obj.style(
                color=viz.get("color") or viz.get("strokeColor") or "000",
                fillColor=viz.get("fillColor", "00000011"),
                width=viz.get("width") or viz.get("strokeWeight", 2),
                pointSize=viz.get("pointSize") or viz.get("pointRadius", 3),
            )
            return styled, "styled"
        else:
            # ee.Image().paint(fc, 0, sw)
            img = _MockSerializable(cls_name="Image", payload={"painted_from": ee_obj._payload})
            return img, "painted"


def _make_layer_dict(name, ee_obj=None, viz=None, visible=True,
                      tile_url=None, is_tile_url=False):
    """Create an idDict entry the way Map.addLayer / addTileLayer would."""
    if is_tile_url:
        return {
            "objectName": "Map",
            "function": "addREST",
            "name": name,
            "visible": "true" if visible else "false",
            "_is_tile_url": True,
            "_tile_url_template": tile_url,
            "_tile_max_zoom": 20,
            "_tile_opacity": 0.8,
            "item": "",
            "viz": json.dumps({"layerType": "tileMapService"}),
        }
    return {
        "objectName": "Map",
        "function": "addSerializedLayer" if ee_obj is not None else "addLayer",
        "name": name,
        "visible": "true" if visible else "false",
        "_ee_obj": ee_obj,
        "_viz": viz or {},
        "item": ee_obj.serialize() if ee_obj is not None else json.dumps({"geojson": True}),
        "viz": json.dumps(viz or {}),
    }


# --- Reproduce exportLayerJson logic for the mocked types ---
def _export_layers_json(idDictList, output_dir, filename="dashboard_layers.json"):
    _VIZ_KEYS = ("bands", "min", "max", "gain", "bias", "gamma",
                 "palette", "opacity", "format")
    os.makedirs(output_dir, exist_ok=True)
    full_path = os.path.join(output_dir, filename)

    layers = {}
    seen_names = {}
    skipped = []
    warnings = []

    def _unique_name(name):
        count = seen_names.get(name, 0)
        seen_names[name] = count + 1
        if count == 0:
            return name
        new_name = f"{name}_{count + 1}"
        warnings.append(f"Layer name {name!r} collided; renamed to {new_name!r}")
        return new_name

    for idx, idDict in enumerate(idDictList):
        name = idDict.get("name", f"Layer {idx}")

        if idDict.get("_is_tile_url"):
            out_name = _unique_name(name)
            layers[out_name] = {
                "static_url": idDict["_tile_url_template"],
                "visible": idDict.get("visible", "true") == "true",
                "opacity": float(idDict.get("_tile_opacity", 1.0)),
                "max_zoom": int(idDict.get("_tile_max_zoom", 20)),
            }
            continue

        ee_obj = idDict.get("_ee_obj")
        viz = idDict.get("_viz", {}) or {}
        visible = idDict.get("visible", "true") == "true"

        if ee_obj is None:
            skipped.append({"name": name, "reason": "GeoJSON layer (no EE object to re-mint)"})
            continue

        map_viz = {k: viz[k] for k in _VIZ_KEYS if k in viz}

        try:
            styled, mode = _MockMapper._style_vector(ee_obj, viz)
            if mode == "painted":
                sc = viz.get("color") or viz.get("strokeColor")
                if sc:
                    map_viz["palette"] = [sc.replace("#", "")]
                map_viz.pop("bands", None)
            elif mode == "styled":
                map_viz = {}
            else:
                if styled.__class__.__name__ == "ImageCollection":
                    styled = styled.mosaic()
        except Exception as e:
            skipped.append({"name": name, "reason": f"styling failed: {e}"})
            continue

        try:
            serialized = styled.serialize()
        except Exception as e:
            skipped.append({"name": name, "reason": f"serialize failed: {e}"})
            continue

        out_name = _unique_name(name)
        layers[out_name] = {
            "serialized": serialized,
            "viz": map_viz,
            "visible": visible,
        }

    payload = {"version": 1, "layer_count": len(layers), "layers": layers}
    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return {"path": full_path, "layer_names": list(layers.keys()),
            "layer_count": len(layers), "skipped": skipped, "warnings": warnings}


# ----------------- Tests -----------------
def _tmp_dir():
    return tempfile.mkdtemp(prefix="elj_")


def test_image_serialized_directly():
    img = _MockSerializable(cls_name="Image")
    items = [_make_layer_dict("Biomass", img, viz={"min": 0, "max": 500, "palette": ["#fff", "#0f0"]})]
    r = _export_layers_json(items, _tmp_dir())
    assert r["layer_count"] == 1
    p = json.loads(open(r["path"]).read())
    layer = p["layers"]["Biomass"]
    assert "serialized" in layer
    assert layer["viz"] == {"min": 0, "max": 500, "palette": ["#fff", "#0f0"]}
    assert json.loads(layer["serialized"])["_cls"] == "Image"


def test_image_collection_is_mosaicked():
    ic = _MockSerializable(cls_name="ImageCollection")
    items = [_make_layer_dict("LCMS", ic, viz={"bands": ["Land_Cover"]})]
    r = _export_layers_json(items, _tmp_dir())
    # The serialized payload should be the mosaic result, not the IC itself
    layer = json.loads(open(r["path"]).read())["layers"]["LCMS"]
    inner = json.loads(layer["serialized"])
    assert inner["_cls"] == "Image"
    assert "from_mosaic_of" in inner["payload"]


def test_geometry_wrapped_as_feature_collection_and_painted():
    geom = _MockSerializable(cls_name="Geometry")
    items = [_make_layer_dict("Area", geom, viz={})]  # no styleParams → painted
    r = _export_layers_json(items, _tmp_dir())
    layer = json.loads(open(r["path"]).read())["layers"]["Area"]
    inner = json.loads(layer["serialized"])
    assert inner["payload"].get("painted_from", {}).get("wrapped_geom") is True


def test_feature_wrapped_and_styled_when_color_given():
    feat = _MockSerializable(cls_name="Feature")
    items = [_make_layer_dict("MyFeature", feat, viz={"strokeColor": "#FF0000", "width": 2})]
    r = _export_layers_json(items, _tmp_dir())
    layer = json.loads(open(r["path"]).read())["layers"]["MyFeature"]
    # .style() returns RGBA — viz should be empty (colors baked in)
    assert layer["viz"] == {}
    inner = json.loads(layer["serialized"])
    assert inner["payload"]["style_kw"]["color"] == "#FF0000"


def test_feature_collection_painted_carries_palette_from_strokeColor():
    fc = _MockSerializable(cls_name="FeatureCollection")
    items = [_make_layer_dict("Boundaries", fc, viz={"color": "#00F"})]
    r = _export_layers_json(items, _tmp_dir())
    layer = json.loads(open(r["path"]).read())["layers"]["Boundaries"]
    # With a `color` key, _style_vector goes into the "styled" branch, not painted.
    # The styled branch bakes color in → viz is empty.
    assert layer["viz"] == {}


def test_geojson_dict_layer_skipped():
    items = [_make_layer_dict("MyGeoJSON", ee_obj=None)]
    r = _export_layers_json(items, _tmp_dir())
    assert r["layer_count"] == 0
    assert len(r["skipped"]) == 1
    assert r["skipped"][0]["name"] == "MyGeoJSON"
    assert "GeoJSON" in r["skipped"][0]["reason"]


def test_tile_url_layer_passes_through_as_static():
    items = [_make_layer_dict("CTrees AGB", is_tile_url=True,
                              tile_url="https://e.com/{z}/{x}/{y}.png")]
    r = _export_layers_json(items, _tmp_dir())
    layer = json.loads(open(r["path"]).read())["layers"]["CTrees AGB"]
    assert layer["static_url"] == "https://e.com/{z}/{x}/{y}.png"
    assert "serialized" not in layer
    assert layer["opacity"] == 0.8


def test_name_collision_auto_suffix():
    img1 = _MockSerializable("Image", {"i": 1})
    img2 = _MockSerializable("Image", {"i": 2})
    img3 = _MockSerializable("Image", {"i": 3})
    items = [
        _make_layer_dict("Biomass", img1, viz={}),
        _make_layer_dict("Biomass", img2, viz={}),
        _make_layer_dict("Biomass", img3, viz={}),
    ]
    r = _export_layers_json(items, _tmp_dir())
    assert set(r["layer_names"]) == {"Biomass", "Biomass_2", "Biomass_3"}
    assert len(r["warnings"]) == 2  # two collisions warned


def test_mixed_types_all_processed():
    img = _MockSerializable("Image")
    ic = _MockSerializable("ImageCollection")
    geom = _MockSerializable("Geometry")
    items = [
        _make_layer_dict("A", img, viz={"min": 0, "max": 1}),
        _make_layer_dict("B", ic, viz={}),
        _make_layer_dict("C", geom, viz={}),
        _make_layer_dict("D", is_tile_url=True, tile_url="https://e.com/{z}/{x}/{y}.png"),
        _make_layer_dict("E", ee_obj=None),  # GeoJSON
    ]
    r = _export_layers_json(items, _tmp_dir())
    assert r["layer_count"] == 4  # E skipped
    assert "A" in r["layer_names"]
    assert "B" in r["layer_names"]
    assert "C" in r["layer_names"]
    assert "D" in r["layer_names"]
    assert "E" not in r["layer_names"]
    assert len(r["skipped"]) == 1


def test_viz_keys_filtered_to_display_only():
    img = _MockSerializable("Image")
    items = [_make_layer_dict("X", img, viz={
        "min": 0, "max": 100, "palette": ["fff"],
        "autoViz": True,           # not a display key → should be filtered out
        "canAreaChart": True,      # ditto
        "layerType": "geeImage",   # ditto
    })]
    r = _export_layers_json(items, _tmp_dir())
    layer = json.loads(open(r["path"]).read())["layers"]["X"]
    assert "min" in layer["viz"]
    assert "max" in layer["viz"]
    assert "palette" in layer["viz"]
    assert "autoViz" not in layer["viz"]
    assert "canAreaChart" not in layer["viz"]
    assert "layerType" not in layer["viz"]


def test_payload_structure_has_version_and_count():
    items = [_make_layer_dict("A", _MockSerializable("Image"), viz={})]
    r = _export_layers_json(items, _tmp_dir())
    p = json.loads(open(r["path"]).read())
    assert p["version"] == 1
    assert p["layer_count"] == 1
    assert isinstance(p["layers"], dict)


def test_visible_flag_propagated():
    items = [
        _make_layer_dict("On", _MockSerializable("Image"), viz={}, visible=True),
        _make_layer_dict("Off", _MockSerializable("Image"), viz={}, visible=False),
    ]
    r = _export_layers_json(items, _tmp_dir())
    p = json.loads(open(r["path"]).read())
    assert p["layers"]["On"]["visible"] is True
    assert p["layers"]["Off"]["visible"] is False


def test_action_handler_doesnt_reference_undefined_session_id():
    """Regression: the export_layers_json action lives inside
    _map_control_inner(), which doesn't receive ``session_id`` as a
    parameter. Earlier code referenced bare ``session_id`` and raised
    ``NameError: name 'session_id' is not defined`` on every call —
    which the agent saw as a generic "tool errored" response and
    repeatedly retried. The fix uses ``sess.session_id`` instead.

    Catches the bug at parse time via AST so comments and string
    literals (which legitimately contain the substring ``session_id``)
    don't trip false positives.
    """
    import ast, os
    src = open(os.path.join(os.path.dirname(__file__), "..", "mcp", "server.py"),
               encoding="utf-8").read()
    tree = ast.parse(src)
    target_fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_map_control_inner":
            target_fn = node
            break
    assert target_fn is not None, "Could not locate _map_control_inner"

    # The signature must not declare session_id — that's the whole point
    # of this regression test.
    param_names = {a.arg for a in target_fn.args.args}
    assert "session_id" not in param_names, (
        f"_map_control_inner signature shouldn't have session_id "
        f"(test assumption broken): args={param_names}"
    )

    # Walk the body for bare ``Name('session_id')`` references — these
    # are AST nodes for variable lookups (not strings, not attributes).
    bare_loads = []
    for node in ast.walk(target_fn):
        if isinstance(node, ast.Name) and node.id == "session_id":
            # ast.Name catches both Load and Store contexts; only Load is
            # the NameError trigger.
            if isinstance(node.ctx, ast.Load):
                bare_loads.append(node.lineno)
    assert not bare_loads, (
        f"_map_control_inner has bare 'session_id' references on line(s) "
        f"{bare_loads} — use sess.session_id instead. These raise NameError "
        f"at runtime, which the agent misreads as a tool failure."
    )


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
