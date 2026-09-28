"""Text a user or an agent supplies must never break the generated viewer script.

``mapper._build_run_js`` writes one JavaScript file that defines
``runGeeViz()`` and adds every layer. Layer names, the map title and a few
query settings were interpolated into JS string literals with no escaping,
so a single apostrophe ended the string early:

    Map.addSerializedLayer(..., 'Peak Nor'easter Wind & Streamlines (kt)', true);

The file then fails to PARSE, ``runGeeViz`` is never defined, and the viewer
throws ``ReferenceError: runGeeViz is not defined`` -- so not one layer
loads, including all the ones with ordinary names. Server-side validation
(``test_layers``) calls ``getMapId`` per layer and never runs this script,
so it reported PASS on a map that showed nothing. That is how a Nor'easter
map came up blank three times in a row on prod.

These tests drive the REAL ``_build_run_js`` (not a stand-in), parse its
output with Node, and execute it against stubs to prove every name
arrives byte-for-byte.
"""
import json
import shutil
import subprocess

import pytest

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not available")

# Every shape of text that has, or plausibly could, break a JS literal.
HOSTILE_NAMES = [
    "Peak Nor'easter Wind & Streamlines (kt)",   # the one that broke prod
    'Say "hello"',
    "back\\slash C:\\temp\\",
    "trailing backslash \\",
    "line\nbreak",
    "carriage\rreturn",
    "tab\there",
    "</script><script>alert(1)</script>",
    "unicode ✓ – Nor’easter — 雨",
    "line separator \u2028 and \u2029 paragraph",
    "${template} `backtick`",
]


def _mapper():
    # Imported at RUN time, not at the top of the file. test_esriLib puts a
    # stub module at sys.modules["geeViz.geeView"] while pytest is still
    # collecting, so a top-level import here captured the stub (no
    # ``mapper``) and every test in this file failed in a full run while
    # passing alone. By run time its teardown has restored the real module.
    import geeViz.geeView as gv

    m = gv.mapper()
    m.idDictList = []
    m.mapCommandList = []
    return m


def _layer(name, visible=True):
    return {
        "objectName": "Map",
        "function": "addSerializedLayer",
        "item": "{}",
        "viz": "{}",
        "name": name,
        "visible": visible,
    }


_HARNESS = r"""
const fs = require("fs");
const src = fs.readFileSync(0, "utf8");
const added = [], commands = [];
const Map = new Proxy({}, { get: (_, fn) => (...a) => {
  if (fn === "addSerializedLayer" || fn === "addSerializedTimeLapse"
      || fn === "addSerializedSelectLayer" || fn === "addLayer") {
    added.push(a[2]);
  } else { commands.push([fn, a]); }
}});
const ee = { data: new Proxy({}, { get: () => () => {} }) };
const showMessage = () => {}, $ = () => ({ click() {} });
const staticTemplates = { loadingModal: {} }, mode = "geeViz";
const localStorage = {}, window = { location: { origin: "" } };
function addDynamicToMap(b1, b2, e1, e2, z1, z2, name) { added.push(name); }
let queryWindowMode, yLabelMaxLength;
setTimeout = () => {};
eval(src + ";runGeeViz();");
process.stdout.write(JSON.stringify({ added, commands }));
"""


def _run(js):
    """Parse AND execute the generated script; return what it did."""
    chk = subprocess.run([NODE, "--check", "-"], input=js, text=True,
                         capture_output=True, encoding="utf-8")
    assert chk.returncode == 0, (
        "generated runGeeViz.js does not parse -- every layer would fail "
        f"to load:\n{chk.stderr}")
    out = subprocess.run([NODE, "-e", _HARNESS], input=js, text=True,
                         capture_output=True, encoding="utf-8")
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@pytest.mark.parametrize("name", HOSTILE_NAMES)
def test_a_layer_name_cannot_break_the_script(name):
    m = _mapper()
    m.idDictList = [_layer("before"), _layer(name), _layer("after")]
    got = _run(m._build_run_js())
    assert got["added"] == ["before", name, "after"], (
        "a layer name was altered or dropped on its way into the viewer")


def test_the_prod_failure_exactly():
    """The six-layer Nor'easter map: one apostrophe, zero layers."""
    names = [
        "ECMWF Sea Level Pressure (hPa)",
        "GFS 48-Hr Accumulated Rainfall (mm)",
        "Peak Nor'easter Wind & Streamlines (kt)",
        "Coastal Surge Exposure Zones",
        "NYC Metro Coastal Counties",
    ]
    m = _mapper()
    m.idDictList = [_layer(n) for n in names]
    assert _run(m._build_run_js())["added"] == names


@pytest.mark.parametrize("name", HOSTILE_NAMES)
def test_tile_and_dynamic_esri_layers_are_safe_too(name):
    m = _mapper()
    tile = _layer(name)
    tile.update(_is_tile_url=True,
                _tile_url_template="https://x.test/{z}/{x}/{y}.png")
    esri = _layer(name)
    esri.update(_is_dynamic_esri=True, _dyn_base_url_1="https://a.test/",
                _dyn_base_url_2="", _dyn_ending_1="", _dyn_ending_2="",
                _dyn_min_zoom_1=0, _dyn_min_zoom_2=0)
    m.idDictList = [tile, esri]
    assert _run(m._build_run_js())["added"] == [name, name]


@pytest.mark.parametrize("text", HOSTILE_NAMES)
def test_map_commands_carrying_free_text_are_safe(text):
    m = _mapper()
    m.setMapTitle(text)
    m.setQueryCRS(text)
    m.setQueryDateFormat(text)
    m.setQueryBoxColor(text)
    cmds = _run(m._build_run_js())["commands"]
    seen = {fn: args[0] for fn, args in cmds if args}
    assert seen.get("setTitle") == text
    assert seen.get("setQueryCRS") == text
    assert seen.get("setQueryDateFormat") == text
    assert seen.get("setQueryBoxColor") == text


def test_script_close_tag_cannot_escape_an_inline_script():
    """export_html can inline this script into a <script> element, where
    the HTML parser ends the element at the first '</script' regardless of
    JS string quoting."""
    m = _mapper()
    m.idDictList = [_layer("</script><b>x</b>")]
    m.setMapTitle("</SCRIPT>")
    js = m._build_run_js()
    assert "</script" not in js.lower()
