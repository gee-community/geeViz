"""The Delta skin's map script carries Earth Engine workload tags as data.

Delta loads Earth Engine only when a map needs it, after the map script has
run, so the script cannot call ``ee.data`` itself: a call made before Earth
Engine loads is lost, and the layer's tag with it. The default tag goes
through ``Map.setDefaultWorkloadTag`` and each layer's tag rides in its viz.
The original skin's script is unchanged.

Needs Earth Engine (the layers are real ee objects; nothing is computed).
"""
import json
import re

import pytest

import geeViz.geeView as gv


@pytest.fixture
def tagged_map(monkeypatch):
    def make(skin, upstream=None):
        monkeypatch.setattr(gv, "_EE_API_UPSTREAM", upstream)
        m = gv.mapper()
        m.setSkin(skin)
        m.addLayer(gv.ee.Image(1), {"min": 0, "max": 1}, "One")
        m.idDictList[-1]["workloadTag"] = "wl_test"
        return m._build_run_js()
    return make


def layer_viz(js):
    # the viz argument of the one addSerializedLayer call
    m = re.search(r"addSerializedLayer\((.*)\);", js)
    assert m, js[:400]
    call = m.group(1)
    # item and viz are JSON objects: decode the first two in order
    dec = json.JSONDecoder()
    item, end = dec.raw_decode(call)
    viz, _ = dec.raw_decode(call[end + 1:])
    return viz


def test_delta_run_script_has_no_top_level_ee_calls(tagged_map):
    js = tagged_map("geoview")
    assert "ee.data." not in js
    assert layer_viz(js)["workloadTag"] == "wl_test"
    assert js.count("Map.setDefaultWorkloadTag(") == 1


def test_original_run_script_is_unchanged(tagged_map):
    js = tagged_map("original")
    assert "ee.data.setDefaultWorkloadTag(" in js
    assert 'ee.data.setWorkloadTag("wl_test")' in js
    assert "workloadTag" not in layer_viz(js)
    assert "Map.setDefaultWorkloadTag(" not in js


def test_no_layer_tag_under_a_proxy(tagged_map):
    js = tagged_map("geoview", upstream="https://proxy.example/ee-api")
    assert "wl_test" not in js
    assert "ee.data." not in js


def test_a_delta_script_still_runs_in_the_original_viewer(tagged_map, tmp_path):
    """Map.view() rewrites the shared runGeeViz.js the original viewer loads,
    and a saved map can be refreshed into the original skin: a Delta-built
    script must still add its layers where Map has no setDefaultWorkloadTag."""
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node not found")
    js = tagged_map("geoview")
    harness = tmp_path / "run.js"
    harness.write_text(
        "var added = []; var mode = 'geeViz'; var staticTemplates = {loadingModal: {}};"
        "function showMessage(){} function $(){return {click(){}};} var localStorage = {};"
        "var window = {location: {origin: 'http://x'}}; var authProxyAPIURL = '';"
        "var Map = {addSerializedLayer: function(i, v, n){ added.push(n); }, setCenter(){}, turnOnInspector(){}};"
        "global.setTimeout = function(){};"
        + js
        + "\nrunGeeViz(); console.log(JSON.stringify(added));",
        encoding="utf-8",
    )
    out = subprocess.run([node, str(harness)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == '["One"]', (out.stdout, out.stderr)
