"""The u/v tile stretch must be identical in Python and JavaScript.

Earth Engine renders the wind components into the red and green channels
of ordinary PNG tiles, linearly stretched from a fixed m/s range onto
0..255; the browser inverts that stretch to recover the numbers. Both
sides must use the SAME range.

A mismatch does not raise. It yields wind that is wrong by a scale
factor and an offset -- which still looks like weather, still animates,
and still flows plausibly around terrain. There is no symptom to notice,
which is exactly why it is pinned here.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "geeViz" / "geeView" / "src" / "js" / "wind-particles.js"


CACHE_PROBE = Path(__file__).with_name("wind_tilecache_probe.js")


@pytest.fixture(scope="module")
def cache():
    """The real tile fetch and field build, run in node.

    These behaviors were pinned by asserting exact source lines. That
    breaks on any move and, worse, says nothing about whether the thing
    still works -- the in-flight accounting here is arithmetic, and
    arithmetic deserves to be run.
    """
    exe = shutil.which("node")
    if not exe:
        pytest.skip("node not available")
    out = subprocess.run([exe, str(CACHE_PROBE), str(JS)],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _js_const(name):
    src = JS.read_text(encoding="utf-8")
    # Strip comments first: the file explains the constants at length,
    # and this repo's tests have repeatedly matched their own prose.
    code = "\n".join(
        ln for ln in src.splitlines()
        if not ln.lstrip().startswith(("*", "//", "/*"))
    )
    m = re.search(r"\bvar\s+" + name + r"\s*=\s*(-?[0-9.]+)", code)
    assert m, f"{name} not found in {JS.name}"
    return float(m.group(1))


def test_the_client_reads_the_stretch_from_viz():
    """Python is the single source of truth for the stretch.

    Both halves existed for a while and only one was live: weather.py
    sent windTileMin/windTileMax in viz, and the JS ignored them in
    favour of its own constants. That is a mismatch waiting to happen,
    and a mismatch does not throw -- it yields winds wrong by a scale
    and an offset, which still look like weather.
    """
    src = JS.read_text(encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines()
                     if not ln.lstrip().startswith(("*", "//", "/*")))
    assert "windTileMin" in code and "windTileMax" in code, (
        "the client must take the stretch from viz, not only from its "
        "own constants")
    # The cfg KEYS must exist, not merely the expressions that feed them.
    # Renaming `tileMin:` to anything else leaves `windTileMin` in the
    # source and `cfg.tileMin` in sampleUV, both assertions still true,
    # while the decode silently reads undefined and yields NaN.
    for key in ("tileMin", "tileMax"):
        assert re.search(r"\b" + key + r"\s*:", code), (
            f"cfg has no {key} key — sampleUV would read undefined")
    # And the decode must USE those, not the module fallbacks. The
    # decode lives in pixelUV -- sampleUV interpolates between four of
    # its results and no longer touches the byte values itself.
    body = _strip_js_comments(_js_fn_body("pixelUV"))
    assert "cfg.tileMin" in body and "cfg.tileMax" in body, (
        "pixelUV still decodes with the hard-coded fallback")


def test_the_decoder_reads_red_then_green():
    """u out of red, v out of green — the order the encoder wrote.

    The encoder's order is pinned elsewhere; this pins the other half.
    Swapping the two here rotates every vector by 90 degrees, and a
    rotated wind field still looks like a wind field: particles still
    stream, still curl around terrain, still look plausible. Nothing
    would report it.
    """
    body = _strip_js_comments(_js_fn_body("pixelUV"))
    m = re.search(r"return\s*\[\s*lo\s*\+\s*\(data\[(i[^\]]*)\]", body)
    assert m, "could not find the decode return in pixelUV"
    assert m.group(1).strip() == "i", (
        f"u is decoded from data[{m.group(1)}]; red is data[i]")
    m2 = re.search(r"lo\s*\+\s*\(data\[i \+ 1\]", body)
    assert m2, "v must be decoded from data[i + 1] (green)"
    # sampleUV must pass them through in order, not swap them.
    samp = _strip_js_comments(_js_fn_body("sampleUV"))
    assert "return [uv[0], uv[1]," in samp, (
        "sampleUV reorders u and v, which rotates every vector 90 "
        "degrees while still looking like a wind field")


def test_the_fallback_matches_python():
    import geeViz.weather as wx
    assert _js_const("TILE_MIN") == wx.WIND_TILE_MIN_MS, (
        "the JS fallback TILE_MIN disagrees with weather.WIND_TILE_MIN_MS "
        "— only reached when viz lacks the value, but wrong there too")
    assert _js_const("TILE_MAX") == wx.WIND_TILE_MAX_MS, (
        "wind-particles.js TILE_MAX disagrees with weather.WIND_TILE_MAX_MS "
        "— decoded winds will be wrong by a scale factor, silently")


def test_the_stretch_covers_real_winds():
    """Values outside the range clamp, so the range has to be wide enough
    that clamping never happens in practice. 40 m/s is ~145 km/h."""
    import geeViz.weather as wx
    assert wx.WIND_TILE_MIN_MS <= -35 and wx.WIND_TILE_MAX_MS >= 35


def test_quantization_is_finer_than_the_forecast():
    """8 bits over the range. If this ever gets coarse enough to see, the
    range grew too wide."""
    import geeViz.weather as wx
    step = (wx.WIND_TILE_MAX_MS - wx.WIND_TILE_MIN_MS) / 255.0
    assert step < 0.5, f"{step:.3f} m/s per level is too coarse"


def test_python_encodes_into_red_and_green():
    """Order matters: u in red, v in green. Swapping them rotates every
    vector by 90 degrees, which still looks like a wind field."""
    import inspect
    import geeViz.weather as wx
    src = inspect.getsource(wx.windTiles)
    m = re.search(r'bands=\[([^\]]+)\]', src)
    assert m, "no visualize(bands=...) call"
    assert [b.strip().strip('"\'') for b in m.group(1).split(",")] == ["u", "v", "z"]


def test_knots_are_nautical_not_statute():
    """The one wind unit with a trap in it.

    A knot is one NAUTICAL mile per hour, and a nautical mile is defined
    as exactly 1852 m -- 15% longer than the statute mile behind
    ``mi/hr``. Confusing the two is a 15% error in wind speed, which is
    the sort of wrong that looks completely reasonable on a map and
    matters on an aviation or marine forecast, where knots is the unit
    the answer is expected in.
    """
    import geeViz.weather as wx
    kt = wx.SPEED_UNITS["kt"]
    # Exact by definition, not a retyped decimal.
    assert kt == 3600.0 / 1852.0
    assert abs(1.0 / kt - 0.514444) < 1e-5, "1 kt is 0.514444 m/s"
    assert kt != wx.SPEED_UNITS["mi/hr"], "knots are not miles per hour"
    # The ratio between them IS the ratio of the two miles.
    assert abs(wx.SPEED_UNITS["mi/hr"] / kt - 1852.0 / 1609.344) < 1e-9
    # Windy's full scale, which is what makes kt worth having here.
    assert abs(60.0 / kt - 30.87) < 0.01, "60 kt is 30.87 m/s"


def test_every_speed_unit_survives_a_round_trip():
    """SPEED_UNITS is a multiplier FROM m/s. A unit added with the
    reciprocal would look plausible everywhere except the numbers."""
    import geeViz.weather as wx
    for unit, mult in wx.SPEED_UNITS.items():
        assert mult > 0, unit
        assert abs((10.0 * mult) / mult - 10.0) < 1e-9, unit
    # m/s is the reference and must be exactly 1, or every conversion in
    # the module is off by a constant nobody would spot.
    assert wx.SPEED_UNITS["m/s"] == 1.0
    # Ordered by how fast the number grows, which is a cheap way to
    # catch a reciprocal: 1 m/s is 1, 1.94 kt, 2.24 mph, 3.6 km/h.
    assert (wx.SPEED_UNITS["m/s"] < wx.SPEED_UNITS["kt"]
            < wx.SPEED_UNITS["mi/hr"] < wx.SPEED_UNITS["km/hr"])


def test_default_stretch_follows_the_unit():
    """A 0..15 stretch read as km/h paints the map one flat colour."""
    import geeViz.weather as wx
    d = wx.DEFAULT_MAX_SPEED
    assert set(d) == set(wx.SPEED_UNITS)
    for unit, mult in wx.SPEED_UNITS.items():
        # Each default should be the same physical wind, give or take.
        assert abs(d[unit] / mult - d["m/s"]) < 2.0, (
            f"{unit} default {d[unit]} is not ~{d['m/s']} m/s")


# ── the stretch must always reach the client ───────────────────────────

def test_addlayer_always_stamps_the_stretch():
    """Any wind-particle layer leaves geeViz carrying the tile stretch.

    Not just the ones built by weather.addWindLayer. The browser cannot
    decode the u/v tiles without knowing the range they were encoded
    with, and if it falls back to its own copy the two can drift —
    silently, because the result is still a plausible-looking wind.
    """
    import json
    import geeViz.geeView as gv
    import geeViz.weather as wx

    Map = gv.mapper()
    # A hand-rolled particle layer that does NOT pass the stretch.
    img = gv.ee.Image.constant([1, 2, 0]).rename(["u", "v", "z"]).toFloat()
    Map.addLayer(img, {"windParticles": True}, "hand rolled", True)

    stamped = [json.loads(d["viz"]) for d in Map.idDictList if d.get("name")]
    assert stamped, "no layer was registered"
    v = stamped[0]
    assert v["windTileMin"] == wx.WIND_TILE_MIN_MS
    assert v["windTileMax"] == wx.WIND_TILE_MAX_MS


def test_an_explicit_stretch_is_not_overwritten():
    """setdefault, not assignment: a caller who deliberately encoded a
    different range must keep it, or their tiles decode wrongly."""
    import json
    import geeViz.geeView as gv

    Map = gv.mapper()
    img = gv.ee.Image.constant([1, 2, 0]).rename(["u", "v", "z"]).toFloat()
    Map.addLayer(img, {"windParticles": True,
                       "windTileMin": -25.0, "windTileMax": 25.0},
                 "custom stretch", True)
    v = json.loads([d for d in Map.idDictList if d.get("name")][0]["viz"])
    assert v["windTileMin"] == -25.0 and v["windTileMax"] == 25.0


def test_ordinary_layers_are_not_stamped():
    """The keys are meaningless on a normal layer and would be noise in
    every serialized viz dict."""
    import json
    import geeViz.geeView as gv

    Map = gv.mapper()
    img = gv.ee.Image.constant(1).rename(["b1"]).toFloat()
    Map.addLayer(img, {"min": 0, "max": 1}, "ordinary", True)
    v = json.loads([d for d in Map.idDictList if d.get("name")][0]["viz"])
    assert "windTileMin" not in v and "windTileMax" not in v


# ── particle count scales with zoom ────────────────────────────────────

def _strip_js_comments(src):
    """Drop // and /* */ comments.

    Source assertions that match their own explanatory comments pass
    vacuously — and worse, an assertion that a construct is ABSENT fails
    the moment a comment explains why it was removed, which is exactly
    what happened to the ``destination-in`` check here. String literals
    are left alone; this only has to be right for this one file.
    """
    out, i, n = [], 0, len(src)
    while i < n:
        if src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
        else:
            out.append(src[i])
            i += 1
    return "".join(out)


def test_the_comment_stripper_works():
    """A stripper that silently does nothing turns every source
    assertion below into a tautology."""
    assert _strip_js_comments("a // b\nc") == "a \nc"
    assert _strip_js_comments("a /* b */ c") == "a  c"
    assert _strip_js_comments("/* x */") == ""
    assert _strip_js_comments("keep") == "keep"
    assert "destination-in" not in _strip_js_comments(
        "/* the destination-in fade */ x")


def _js_fn_body(name):
    """The whole function body, brace-matched.

    A fixed-length slice silently truncates: the 900-character window
    this used to take stopped short of ``frame()``'s stroke loop, so an
    assertion about it reported "0 occurrences" and read as a real
    regression rather than as a short window.
    """
    src = JS.read_text(encoding="utf-8")
    i = src.index("function " + name)
    start = src.index("{", i)
    depth, j = 0, start
    while j < len(src):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
        j += 1
    raise AssertionError("unbalanced braces reading " + name)


def test_each_particle_gets_its_own_lifetime():
    """Trail length is how much history the fade still shows, so a young
    particle draws a stub and a mature one draws a full streak.

    With a single shared ``cfg.maxAge`` nearly every particle sits in
    the mature part of its life at any instant and the field renders as
    one uniform comb — which is exactly how it looked next to windy.com.
    The lifetime has to be PER PARTICLE for short and long streaks to
    coexist.
    """
    body = _js_fn_body("respawn")
    assert "p.maxAge = cfg.minAge + Math.random() * (cfg.maxAge - cfg.minAge)" in body, (
        "respawn no longer draws a per-particle lifetime — every trail "
        "will mature to the same length")
    src = JS.read_text(encoding="utf-8")
    assert "if (p.age > cfg.maxAge)" not in src, (
        "the age check still compares against the SHARED maxAge, so the "
        "per-particle lifetime is computed and then ignored")
    assert src.count("p.age > p.maxAge") == 2, (
        "both age checks (no-data and normal advection) must use the "
        "particle's own lifetime")


def test_initial_ages_are_staggered():
    """Otherwise the whole field is born together, dies together, and
    the map visibly pulses once per lifetime."""
    body = _js_fn_body("respawn")
    assert "randomAge ? Math.random() * p.maxAge : 0" in body


def test_python_sends_the_lifetime_range():
    """The client defaults are a fallback, not the contract — geeViz
    stamps both ends so the viewer does not have to guess."""
    import geeViz.weather as wx
    sent = {}

    class FakeMap:
        def addLayer(self, image, viz=None, name=None, visible=True):
            sent[name] = viz or {}

    import ee
    img = ee.Image([1, 2]).rename(["u", "v"])
    wx.addWindLayer(FakeMap(), img, {}, "W", True)
    # Found by what the viz SAYS, not by the layer's name. Grouped --
    # the default -- there is one layer called "W" and it is the
    # particle layer; ungrouped there are two and only one of them is.
    # Matching on the name pinned an arrangement rather than a contract.
    particles = [v for v in sent.values() if v.get("windParticles")]
    assert particles, f"no particle layer was added; got {list(sent)}"
    v = particles[0]
    assert v["particleMaxAge"] == 45
    assert v["particleMinAge"] == 11.25, (
        f"particleMinAge is {v.get('particleMinAge')!r}; without it the "
        f"client falls back and the range is never actually chosen here")


def test_setting_max_age_moves_the_min_with_it():
    """``particleMinAge`` defaults to a QUARTER of whatever max is in
    effect. A user who only raises the max should get proportionally
    longer streaks, not a range that silently widens to the old
    fraction of 90."""
    import ee
    import geeViz.weather as wx
    sent = {}

    class FakeMap:
        def addLayer(self, image, viz=None, name=None, visible=True):
            sent[name] = viz or {}

    img = ee.Image([1, 2]).rename(["u", "v"])
    wx.addWindLayer(FakeMap(), img, {"particleMaxAge": 200}, "W", True)
    v = [x for k, x in sent.items() if x.get("particleMaxAge")][0]
    assert v["particleMinAge"] == 50.0, (
        f"min is {v['particleMinAge']} for a max of 200 — it did not "
        f"track the max")


# ---------------------------------------------------------------------------
# Palettes
# ---------------------------------------------------------------------------


def _js_literal_defaults():
    """Every ``particleX`` default in ``cfgFrom`` that is a literal.

    Two forms appear: ``v.particleX || 4000`` and
    ``v.particleX !== undefined ? v.particleX : 7``. Defaults derived
    from another value (``weight * 0.45``) are deliberately skipped —
    they are checked by relationship instead.
    """
    import re as _re
    src = _strip_js_comments(_js_fn_body("cfgFrom"))
    out = {}
    pat = (r"v\.(particle[A-Za-z]+)\s*(?:\|\|\s*|"
           r"!== undefined\s*\?\s*v\.particle[A-Za-z]+\s*:\s*)"
           r"(-?[\d.]+|\"[a-z]+\")")
    for name, raw in _re.findall(pat, src):
        out[name] = raw.strip('"') if raw.startswith('"') else float(raw)
    return out


def _stamped_viz():
    import ee
    import geeViz.weather as wx
    sent = {}

    class FakeMap:
        def addLayer(self, image, viz=None, name=None, visible=True):
            sent[name] = viz or {}

    wx.addWindLayer(FakeMap(), ee.Image([1, 2]).rename(["u", "v"]), {}, "W")
    return [x for x in sent.values() if x.get("windParticles")][0]


def test_every_client_default_matches_what_python_sends():
    """Two copies of the same numbers, checked wholesale rather than by
    a hand-picked list.

    geeViz stamps all of these onto the layer, so a client fallback that
    disagreed would only show up for a hand-built layer — the hardest
    case to notice. The earlier version of this test named five keys
    explicitly and silently stopped covering the rest as the set grew.
    """
    js = _js_literal_defaults()
    assert len(js) >= 9, (
        f"only parsed {len(js)} defaults out of cfgFrom — the parser has "
        f"drifted from the source and is no longer checking anything")
    viz = _stamped_viz()
    missing, wrong = [], []
    for key, default in js.items():
        if key == "particleLineWidth":
            continue          # back-compat alias, resolved in Python
        if key == "windMaxSpeedMs":
            # DERIVED from the raster stretch, so python sends a value
            # that depends on viz['max'] and units rather than a
            # constant. The client keeps a literal only as a fallback
            # for a hand-built layer. test_the_speed_ceiling_follows_
            # the_stretch covers the real contract.
            continue
        if key not in viz:
            missing.append(key)
        elif isinstance(default, float):
            if abs(float(viz[key]) - default) > 1e-9:
                wrong.append(f"{key}: python={viz[key]} client={default}")
        elif viz[key] != default:
            wrong.append(f"{key}: python={viz[key]!r} client={default!r}")
    assert not missing, f"python never sends: {missing}"
    assert not wrong, "defaults drifted — " + "; ".join(wrong)


def test_derived_sizes_track_their_base():
    """``particleMinWidth`` / ``particleMaxWidth`` default to fractions of
    ``particleStrokeWeight``, so raising the weight alone rescales the
    whole taper instead of leaving a half-scaled one. Same contract as
    ``particleMinAge`` tracking ``particleMaxAge``."""
    import ee
    import geeViz.weather as wx
    sent = {}

    class FakeMap:
        def addLayer(self, image, viz=None, name=None, visible=True):
            sent[name] = viz or {}

    img = ee.Image([1, 2]).rename(["u", "v"])
    wx.addWindLayer(FakeMap(), img, {"particleStrokeWeight": 4.0}, "W")
    v = [x for x in sent.values() if x.get("windParticles")][0]
    assert v["particleMinWidth"] == 4.0 * 0.45
    assert v["particleMaxWidth"] == 4.0 * 1.5
    assert v["particleMinWidth"] < v["particleMaxWidth"], (
        "a comet is thin at the tail and fat at the tip")

    # the old name still works
    sent.clear()
    wx.addWindLayer(FakeMap(), img, {"particleLineWidth": 3.0}, "W")
    v = [x for x in sent.values() if x.get("windParticles")][0]
    assert v["particleStrokeWeight"] == 3.0, (
        "particleLineWidth is the old name for particleStrokeWeight and "
        "must keep working")

    # and an explicit size wins over the derived one
    sent.clear()
    wx.addWindLayer(FakeMap(), img,
                    {"particleStrokeWeight": 4.0, "particleMaxWidth": 9.0}, "W")
    v = [x for x in sent.values() if x.get("windParticles")][0]
    assert v["particleMaxWidth"] == 9.0


def test_the_size_ramp_is_used_in_frame():
    """Configured is not applied. The width must interpolate minSize to
    maxSize across the trail — the head then needs no special case,
    because at t = 1 it already IS maxSize."""
    body = _strip_js_comments(_js_fn_body("frame"))
    assert "cfg.minWidth + (cfg.maxWidth - cfg.minWidth) * t" in body, (
        "frame() does not ramp the width between the configured sizes")
    assert "cfg.lineCap" in body, "particleLineCap is configured but unused"


def test_wind_palette_is_windys_legend():
    """Read off windy.com's own legend so a geeViz wind map and a windy
    map of the same hour are comparable at a glance. Pinned as RGB
    because that is the form the legend publishes."""
    import geeViz.geeView as gv
    import geeViz.weather as wx
    expected = [(61, 110, 163), (74, 148, 170), (74, 146, 148),
                (77, 142, 124), (76, 164, 76), (103, 164, 54),
                (162, 135, 64), (162, 109, 92), (141, 63, 92),
                (151, 75, 145), (95, 100, 160), (91, 136, 161),
                (91, 136, 161)]
    assert list(wx.WIND_PALETTE) == [gv.RGB_to_hex(list(c)) for c in expected]
    assert wx.DEFAULT_SPEED_PALETTE is wx.WIND_PALETTE, (
        "an unconfigured wind layer must paint with the windy ramp")


def test_local_hex_matches_geeviz_rgb_to_hex():
    """``weather`` converts colours locally rather than importing the
    viewer, because ``geeView`` imports ``weather`` to serve
    ``Map.addWindLayer`` — a top-level import back would make the cycle
    depend on which module the user happened to import first. Local, but
    it must agree."""
    import geeViz.geeView as gv
    import geeViz.weather as wx
    for c in [(0, 0, 0), (255, 255, 255), (61, 110, 163), (7, 8, 9)]:
        assert wx._hex(c) == gv.RGB_to_hex(list(c))


def test_precip_and_temperature_palettes_are_present():
    """Same source, so a multi-variable weather map is coherent."""
    import geeViz.weather as wx
    assert len(wx.PRECIP_PALETTE) == 9
    assert len(wx.TEMPERATURE_PALETTE) == 13
    for pal in (wx.WIND_PALETTE, wx.PRECIP_PALETTE, wx.TEMPERATURE_PALETTE):
        for c in pal:
            assert re.fullmatch(r"#[0-9a-f]{6}", c), c


# ---------------------------------------------------------------------------
# The agent can actually reach any of this.
# ---------------------------------------------------------------------------


def test_weather_is_bound_in_the_run_code_namespace():
    """A library the agent cannot import is a library that does not
    exist. ``wx`` has to be BOUND, not merely importable — the sandbox
    namespace is what ``run_code`` executes against."""
    src = (ROOT / "geeViz" / "mcp" / "server.py").read_text(encoding="utf-8")
    assert "import geeViz.weather as wx" in src
    assert '"wx": wx,' in src and '"weather": wx,' in src, (
        "both spellings, so search_codebase resolves whichever the "
        "agent tries")


def test_the_agent_instructions_cover_wind_layers():
    """Docstrings reach the agent through search_codebase, but only if
    it knows to look. The instructions are what send it there."""
    md = (ROOT / "geeViz" / "mcp" /
          "agent-instructions.md").read_text(encoding="utf-8")
    for needle in ("Map.addWindLayer", "wx.getForecastData",
                   'search_codebase(module="weather")', "WIND_PALETTE"):
        assert needle in md, f"agent instructions never mention {needle}"


def test_every_particle_param_is_documented():
    """Documented in all three places, checked against the real set.

    Driven from the viz dict ``addWindLayer`` actually stamps, so adding
    a knob without documenting it fails here rather than shipping an
    undiscoverable parameter. Naming the places explicitly because each
    reaches a different audience: the docstring is what
    ``search_codebase`` serves the agent, the instructions are what tell
    it to look, and the notebook is what a person reads.
    """
    import geeViz.weather as wx
    params = sorted(k for k in _stamped_viz() if k.startswith("particle"))
    assert len(params) >= 14, (
        f"only {len(params)} particle params found — the introspection "
        f"has drifted and this test is no longer checking much")

    doc = wx.addWindLayer.__doc__
    md = (ROOT / "geeViz" / "mcp" /
          "agent-instructions.md").read_text(encoding="utf-8")
    nb = (ROOT / "geeViz" / "examples" /
          "weather_forecast_examples.ipynb").read_text(encoding="utf-8")

    for where, text in (("addWindLayer docstring", doc),
                        ("agent-instructions.md", md),
                        ("weather_forecast_examples.ipynb", nb)):
        missing = [p for p in params if p not in text]
        assert not missing, f"{where} does not mention: {missing}"


def test_the_units_caveat_travels_with_the_speed_bounds():
    """``particleMinSpeed`` / ``particleMaxSpeed`` change APPARENT speed
    only. Anywhere they are documented has to say so, or someone will
    read a streak length as a wind speed — the raster and the click
    query are the numbers, the streaks are not.
    """
    import geeViz.weather as wx
    md = (ROOT / "geeViz" / "mcp" /
          "agent-instructions.md").read_text(encoding="utf-8")
    for where, text in (("addWindLayer docstring", wx.addWindLayer.__doc__),
                        ("agent-instructions.md", md)):
        # Collapse whitespace first: these phrases straddle a line wrap
        # in the docstring, and a docs test that fails whenever a
        # paragraph is rewrapped teaches people to delete the test.
        low = " ".join(text.lower().split())
        assert "direction is untouched" in low or "direction is preserved" in low, (
            f"{where}: the speed bounds are documented without saying "
            f"direction survives them")
        assert "true value" in low, (
            f"{where}: nothing says the raster and query still carry the "
            f"true speed")


def test_the_head_is_brighter_than_the_tail():
    """The comet shape. Ranks are stroked oldest-first at
    ``opacity * t^taper``, and the newest gets ``headBoost``.

    A single multiplicative canvas fade cannot do this: one slow enough
    to leave a long trail is nearly flat across its first twenty frames
    (0.965^20 = 0.49), so the streak reads as a uniform bar. That was
    the whole reason for keeping an explicit history.
    """
    import re as _re
    src = _strip_js_comments(JS.read_text(encoding="utf-8"))
    # Scoped to frame(): refreshRunState also clears the canvas when a
    # layer is switched off, so asserting against the whole file passed
    # even with the per-frame clear deleted.
    body = _strip_js_comments(_js_fn_body("frame"))
    assert "ctx.clearRect(0, 0, st.w, st.h);" in body, (
        "frame() must clear the canvas — an accumulate-and-fade canvas "
        "cannot produce a bright head")
    assert "destination-in" not in src, (
        "the old fade is back; it and the explicit history are two "
        "different trail models and must not both run")
    taper = float(_re.search(
        r"v\.particleTaper !== undefined \? v\.particleTaper : ([\d.]+)",
        src).group(1))
    boost = float(_re.search(
        r"v\.particleHeadBoost !== undefined \? v\.particleHeadBoost : ([\d.]+)",
        src).group(1))
    assert taper > 1.0, (
        f"taper {taper} is linear or inverted — the fade must stretch "
        f"toward the tail for the shape to read as a comet")
    assert boost > 1.0, f"headBoost {boost} does not brighten the head"

    # The alpha ramp itself: tail near nothing, head at full.
    opacity, n = 0.9, 26
    tail = opacity * (1 / (n - 1)) ** taper
    mid = opacity * (0.5) ** taper
    head = min(1.0, opacity * boost)
    assert tail < 0.02, f"tail alpha {tail:.3f} is still visible"
    assert head / mid > 4, (
        f"head is only {head / mid:.1f}x the midpoint — not a comet")


def test_the_encoded_raster_is_detached_and_stays_detached():
    """Unchecking and re-checking the layer made the RGB reappear.

    The viewer rebuilds the ImageMapType and calls
    ``overlayMapTypes.setAt(...)`` on every visibility change. ``scan()``
    skips anything already adopted, so nothing took it back off and the
    encoding — flat red and green, not a picture — sat on the map.
    Detaching therefore has to run on the refresh tick, not only at
    adoption.
    """
    src = _strip_js_comments(JS.read_text(encoding="utf-8"))
    assert "function detach(L)" in src
    scan = _strip_js_comments(_js_fn_body("scan"))
    assert "detach(L)" in scan, "adoption no longer detaches the raster"
    refresh = _strip_js_comments(_js_fn_body("refreshRunState"))
    # The exact guarded call, not just the symbol: `if (false) detach(L)`
    # keeps the name in the file while doing nothing, and an assertion
    # that only looked for "detach(L)" passed on it.
    assert "if (L) { detach(L); reportProgress(st); applyStacking(st); }" in refresh, (
        "detach must RUN on the refresh tick, or re-checking the layer "
        "puts the encoded RGB back on the map for good")


def test_tile_progress_is_reported_from_the_real_queue():
    """The layer's loading state must track the tiles actually in flight.

    The viewer sets ``layer.loading = true`` inside its own
    ``getTileUrl`` and clears it when the ImageMapType fires
    ``tilesloaded``. This module calls ``getTileUrl`` directly and has
    taken the map type off the map, so that event never fires — both
    halves are ours, so reporting is too.

    The first fix simply forced ``loading = false`` once. That stopped
    the endless spinner but pinned the layer to "done" forever: panning
    to fresh ground fetches a new batch and the status bar showed
    nothing. Derived from the in-flight count, it falls off 100 on a pan
    and climbs back as the batch lands.
    """
    src = _strip_js_comments(JS.read_text(encoding="utf-8"))
    assert "function settleSpinner" not in src, (
        "the one-shot suppressor is back; it pins the layer to 'done' "
        "and a pan never reports loading again")
    assert "function reportProgress(st)" in src

    body = _strip_js_comments(_js_fn_body("reportProgress"))
    assert "var loading = visible && inflight > 0;" in body, (
        "loading must be derived from the queue (and visibility), not "
        "pinned")
    assert "L.percent = percent;" in body and ": 100);" in body, (
        "percent must reach 100 when the queue drains and the layer is "
        "visible")
    assert "-spinner2" in body, "the spinner element is never toggled"
    assert "-layer-container" in body, (
        "the white progress fill across the layer row is never repainted")
    assert "-webkit-linear-gradient(left, #FFF, #FFF " in body, (
        "the fill must use the viewer's own gradient, or this row looks "
        "unlike every other layer")
    assert "global.updateProgress" not in body, (
        "the viewer's updateProgress is a per-layer CLOSURE; the global "
        "of that name is a different function and calling it did nothing")
    assert "if (loading) sp.show(); else sp.hide();" in body, (
        "the spinner must be shown again on a new batch, not only hidden")
    assert ('if (typeof global.updateGEETileLayersDownloading === "function")'
            in body), (
        "the status-bar counter must be recomputed by the viewer, or "
        "'Number of map layers loading' never returns to zero")


def test_both_tile_outcomes_leave_the_queue(cache):
    """A failed tile must decrement the in-flight count too.

    Counting only successes leaves the layer loading forever the first
    time a tile 404s or is blocked — which is the exact bug class this
    replaced, reintroduced from the other side.
    """
    assert cache["loadInflightDuring"] == 1
    assert cache["loadInflightAfter"] == 0, "a tile that loaded never left"
    assert cache["loadDecoded"], "the tile loaded but its pixels were not kept"

    assert cache["errInflightDuring"] == 1
    assert cache["errInflightAfter"] == 0, (
        "a tile that 404d stayed in the queue — the layer spins forever")
    assert cache["errCachedFalse"]

    # A URL that never becomes a request must not be counted either.
    assert cache["throwInflight"] == 0, (
        "a getTileUrl that threw was counted as in flight, and nothing "
        "will ever decrement it")
    assert cache["throwCachedFalse"], (
        "a getTileUrl that throws must mark the tile dead, or it is "
        "retried forever")
    assert cache["throwQueued"] == 0


def test_adoption_settles_a_probe_set_flag():
    """``findTileUrlFn`` calls the viewer's own ``getTileUrl`` to find
    it, which flips ``loading = true`` as a side effect. A layer that
    then never requests a tile — switched off, say — would spin
    forever."""
    scan = _strip_js_comments(_js_fn_body("scan"))
    assert "reportProgress(st);" in scan, (
        "adoption must settle the flag the URL probe set")


def _probe_field():
    """Run countFor and fieldAt for real."""
    import json
    import subprocess
    exe = _node()
    if not exe:
        pytest.skip("node not available")
    r = subprocess.run([exe, str(FIELD_PROBE), str(JS)],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"field probe failed: {r.stderr[:800]}"
    return json.loads(r.stdout)


PROBE = Path(__file__).parent / "wind_sampler_probe.js"
FIELD_PROBE = Path(__file__).parent / "wind_field_probe.js"
LAYOUT_PROBE = Path(__file__).parent / "wind_layout_probe.js"


def _probe_layout():
    import json
    import subprocess
    exe = _node()
    if not exe:
        pytest.skip("node not available")
    r = subprocess.run([exe, str(LAYOUT_PROBE), str(JS)],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"layout probe failed: {r.stderr[:800]}"
    return json.loads(r.stdout)


def _probe_field():
    """Run countFor and fieldAt for real."""
    import json
    import subprocess
    exe = _node()
    if not exe:
        pytest.skip("node not available")
    r = subprocess.run([exe, str(FIELD_PROBE), str(JS)],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"field probe failed: {r.stderr[:800]}"
    return json.loads(r.stdout)


def _node():
    """A real Node.js, or None.

    Probed by asking for ``process.versions.node`` rather than trusting
    ``shutil.which`` — on this machine ``which`` has previously turned up
    a WSL relay that answers the name but not the semantics, and a guard
    test that silently skips is worse than one that fails.
    """
    import shutil
    import subprocess
    exe = shutil.which("node")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "-e", "process.stdout.write(process.versions.node)"],
                             capture_output=True, text=True, timeout=30)
    except Exception:
        return None
    return exe if re.fullmatch(r"\d+\.\d+\.\d+", out.stdout.strip() or "") else None


def _probe():
    import json
    import subprocess
    exe = _node()
    if not exe:
        pytest.skip("node not available")
    r = subprocess.run([exe, str(PROBE), str(JS)],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"probe failed: {r.stderr[:800]}"
    return json.loads(r.stdout)


def test_the_sampler_decodes_exactly():
    """Nearest sampling must reproduce the encoder's bytes exactly.

    With no client-side blend, a sample IS a stored byte run back
    through the stretch — so a walk across a synthetic ramp should
    produce a clean staircase whose steps are exactly one byte of the
    stretch, and nothing in between. Anything else means the decode has
    drifted from the encoding.
    """
    d = _probe()
    per = d["perPixel"]
    assert d["maxStep"] <= per + 1e-9, (
        f"a step of {d['maxStep']:.5f} exceeds one byte of the stretch "
        f"({per:.5f}) — the decode does not match the encoding")
    assert d["monotonic"], "a monotonic ramp did not decode monotonically"
    # A staircase, not a ramp: far fewer distinct values than samples.
    assert d["nDistinct"] < d["nSamples"] / 2, (
        f"{d['nDistinct']} distinct values from {d['nSamples']} samples "
        f"— that is interpolated, and the client should not be "
        f"interpolating")


def test_the_sampler_returns_magnitude_and_stays_in_range():
    """The third element must be the true magnitude, and no blend may
    push a decoded value outside the stretch it was encoded with — an
    out-of-range wind is silently wrong rather than visibly broken."""
    d = _probe()
    assert d["tupleLen"] == 3, "sampleUV must return [u, v, magnitude]"
    assert d["magOk"], "the returned magnitude is not hypot(u, v)"
    assert d["decodedLo"] >= -40.0 - 1e-9, d["decodedLo"]
    assert d["decodedHi"] <= 40.0 + 1e-9, d["decodedHi"]


def test_the_tile_service_resamples_server_side():
    """``windTiles`` must keep resampling — the client stopped.

    This became LOAD-BEARING when the client-side blend was removed.
    Earth Engine's bicubic is what makes the field smooth; measured on a
    GFS tile at zoom 10, the unresampled version runs to 176 identical
    pixels in a row against 45 for the bicubic one, with a maximum step
    of 6 against 2. Drop it and the particles advect across a visibly
    blocky field, with nothing downstream left to hide it.

    Bicubic rather than bilinear because it costs nothing here — it is
    computed once per tile, server-side, and cached in the PNG.
    """
    import ee
    import geeViz.weather as wx
    img = ee.Image([1, 2]).rename(["u", "v"])

    src = (ROOT / "geeViz" / "weather.py").read_text(encoding="utf-8")

    def _fn_source(name):
        """A top-level function's source, by AST.

        This used to slice between the name of whichever function
        happened to follow, and to assume a fixed character width. Both
        boundaries broke the moment a neighbour was deleted and a
        docstring grew -- silently, because a slice that lands somewhere
        harmless still passes.
        """
        import ast
        for node in ast.parse(src).body:
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return ast.get_source_segment(src, node)
        raise AssertionError(f"{name}() is gone from weather.py")

    # windImage and windTiles held identical copies of the select +
    # resample block; it lives in one helper now, so exactly one place
    # decides how the field gets smoothed.
    body = _fn_source("_uv_image")
    code = "\n".join(ln for ln in body.splitlines()
                     if not ln.strip().startswith("#"))
    assert 'viz.get("resample", "bicubic")' in code, (
        "_uv_image no longer defaults to bicubic; the client does not "
        "interpolate, so nothing else will smooth the field")
    assert "img = img.resample(rs)" in code, (
        "the resample mode is read but never applied")

    # And both renderers must go through it rather than re-rolling it.
    for fn in ("windImage", "windTiles"):
        seg = _fn_source(fn)
        assert "_uv_image(image, viz)" in seg, (
            f"{fn}() does not use the shared helper")
        assert "img.resample(" not in seg, (
            f"{fn}() resamples on its own again — two copies is "
            f"how they drift apart")

    # And it must survive into the graph, not just the source.
    served = wx.windTiles(img).serialize()
    assert "resample" in served.lower(), (
        "the rendered tile image carries no resample step")


def test_the_client_does_not_interpolate_the_forecast():
    """``sampleUV`` reads the nearest tile pixel and stops.

    Earth Engine already smoothed the tile (``resample('bicubic')``),
    and what remains after that is 8-bit quantization — 0.31 m/s per
    level. Interpolating between two equal bytes returns the same byte,
    so a blend here recovers nothing.

    Interpolating the FIELD GRID is a different matter and is done: that
    grid is a subsampling this module chose, so smoothing it back is
    undoing our own coarseness, not second-guessing the forecast.
    """
    body = _strip_js_comments(_js_fn_body("sampleUV"))
    for corner in ("g10", "g01", "g11", "wa", "wb", "wc", "wd"):
        assert corner not in body, (
            f"sampleUV is interpolating the forecast again ({corner}); "
            f"the tile arrives bicubic-resampled and the rest is "
            f"quantization")
    assert body.count("pixelUV(") == 1, (
        "one tile read per sample; more means a blend crept back in")
    # ...but the grid read must interpolate, or the flow facets at the
    # spacing we chose.
    grid = _strip_js_comments(_js_fn_body("fieldAt"))
    assert "wa" in grid and "wd" in grid, (
        "fieldAt no longer interpolates the grid — the flow will facet "
        "at particleFieldSpacing")


def test_the_hot_path_does_no_geography():
    """``frame`` must not project, trigonometry, or touch a tile.

    That is the whole point of the prebuilt field. At 3000 particles and
    60fps this loop runs 180,000 times a second; buildField runs its
    equivalent ~32,000 times per VIEW CHANGE and not at all while the
    map sits still.
    """
    body = _strip_js_comments(_js_fn_body("frame"))
    for banned in ("fromLatLngToDivPixel", "fromDivPixelToLatLng",
                   "Math.cos", "Math.sqrt", "sampleUV(", "getTile(",
                   "p.lat", "p.lon", "zoomScale"):
        assert banned not in body, (
            f"frame() still does {banned} per particle — it belongs in "
            f"buildField, once per cell per view")
    assert "fieldAt(st, p.x, p.y)" in body, (
        "frame() must read the prebuilt grid")
    assert "p.x += d[0];" in body and "p.y += d[1];" in body, (
        "the field already carries pixels per frame; advancing is an add")


def test_buildfield_does_the_work_frame_used_to():
    """Everything that left the hot path has to have landed here."""
    body = _strip_js_comments(_js_fn_body("buildField"))
    for needed in ("fromDivPixelToLatLng", "sampleUV(",
                   "cfg.minSpeed", "cfg.maxSpeed", "cfg.speed"):
        assert needed in body, f"buildField never does {needed}"
    # Math.cos is deliberately ABSENT -- see
    # test_screen_speed_does_not_vary_with_latitude.
    # Zoom must NOT appear. The old form divided
    # `speedFactor * 2**(zoomRef - zoom)` by a metres-per-pixel that is
    # itself `156543 * cos(lat) / 2**zoom`, so the powers of two
    # cancelled exactly -- keeping either term back would reintroduce
    # the bug where streaks doubled in length per zoom level.
    for gone in ("getZoom()", "Math.pow(2,", "156543", "Math.cos"):
        assert gone not in body, (
            f"buildField still references {gone}; the zoom terms cancel "
            f"and must not be reintroduced")
    assert "f[i + 1] = -v * scale;" in body, (
        "screen y grows downward while v is northward — without the "
        "sign flip the whole field is mirrored north/south")


def test_the_field_is_rebuilt_when_the_view_moves():
    """A pan invalidates every cached vector: canvas pixel (0, 0) means
    a different place on the globe afterwards. Rebuilding is keyed to
    the view, and tied to idle so it happens once when movement stops
    rather than during the drag."""
    src = _strip_js_comments(JS.read_text(encoding="utf-8"))
    key = _strip_js_comments(_js_fn_body("viewKey"))
    # The key is the geometry draw() positioned the canvases for, not
    # map.getCenter(), which runs ahead of draw() during a pan with
    # momentum (see test_wind_raster_anchor.py).
    assert "st.viewGeom" in key and "getCenter" not in key
    geom = src[src.index("st.viewGeom = ["):][:200]
    for part in ("getZoom()", "lat()", "lng()", " w,", " h]"):
        assert part in geom, (
            f"the view key ignores {part}; the field will go stale without "
            f"anything noticing")
    ensure = _strip_js_comments(_js_fn_body("ensureField"))
    assert "st.fieldKey === viewKey(st)" in ensure
    assert 'addListener("idle"' in src
    idle = src[src.index('addListener("idle"'):][:400]
    assert "fieldKey = null" in idle, "idle does not invalidate the field"
    # ...but it must drop the KEY, not the arrays. Reallocating a
    # ~32,000-cell pair on every pan is churn for no gain: the grid is
    # the same shape, only the places it refers to changed.
    assert "field = null;" not in idle, (
        "idle throws the field arrays away; only the key should go")
    build = _strip_js_comments(_js_fn_body("buildField"))
    # Reallocation is bounded to a CANVAS resize -- a ~34,000-cell pair
    # rebuilt on every pan is churn for no gain. Asserted on the scratch
    # buffer, which is what buildField now fills.
    assert "st.fieldBW !== gw || st.fieldBH !== gh" in build, (
        "buildField reallocates unconditionally — it should only do so "
        "when the CANVAS resizes")
    assert "st.fieldOkB.fill(0)" in build, (
        "a reused ok-mask must be cleared, or last view's cells read as "
        "valid where this one has no data")


def test_particle_count_comes_from_canvas_width():
    """After windy.js: a wider canvas has more room to fill.

    It used to compound with zoom, which was really compensating for
    streak length growing with zoom — fixed at the source now, so the
    zoom term only thinned the field where it was already densest.
    """
    body = _strip_js_comments(_js_fn_body("countFor"))
    assert "width * cfg.density" in body, (
        "the count no longer derives from canvas width")
    assert "cfg.zoomFactor" not in body and "zoomRef" not in body, (
        "count must not depend on zoom any more")
    assert "cfg.count !== null" in body, (
        "an explicit particleCount must still win outright")


def test_python_does_not_pin_the_count():
    """Stamping a default would defeat the width derivation entirely —
    the client would see a number and never measure the canvas. This is
    the one particle key deliberately absent by default."""
    viz = _stamped_viz()
    assert "particleCount" not in viz, (
        "weather.py sends a particleCount, so the canvas width is never "
        "consulted")
    assert viz["particleDensity"] == 1.2
    # ...but an explicit request still travels.
    import ee
    import geeViz.weather as wx
    sent = {}

    class FakeMap:
        def addLayer(self, image, viz=None, name=None, visible=True):
            sent[name] = viz or {}

    wx.addWindLayer(FakeMap(), ee.Image([1, 2]).rename(["u", "v"]),
                    {"particleCount": 900}, "W")
    v = [x for x in sent.values() if x.get("windParticles")][0]
    assert v["particleCount"] == 900


def test_the_count_and_grid_maths_run():
    """Numbers, executed rather than read."""
    d = _probe_field()
    assert d["w1700"] == 2975, (
        f"a 1700px canvas gives {d['w1700']} particles; expected ~3000")
    # No clamps any more: width x density is the answer at any size.
    assert d["clampLo"] == 175, d["clampLo"]
    assert d["clampHi"] == 174998, d["clampHi"]
    assert d["explicit"] == 900
    # The grid read must ramp linearly across a cell.
    assert d["ramp"] == [1.0, 1.25, 1.5, 1.75, 2.0], d["ramp"]
    assert d["outside"] is None, "fieldAt must reject an out-of-grid sample"
    # BOTH corners: a check that only looks at the near one still rejects
    # a missing near corner, so testing that alone cannot tell a full
    # check from a partial one.
    assert d["missingNear"] is None, (
        "a missing NEAR corner must reject the sample")
    assert d["missingCorner"] is None, (
        "a missing FAR corner must reject the sample too — blending a "
        "zero in drags the vector toward calm at every data edge")


# ---------------------------------------------------------------------------
# One speed number, and a fade rather than a pop.
# ---------------------------------------------------------------------------


def test_speed_is_one_number_with_no_zoom_term():
    """``particleSpeed`` is pixels/frame per m/s at the equator.

    It replaced a speed factor AND a reference zoom. Screen speed was
    ``speedFactor * 2**(zoomRef - zoom) / metresPerPixel``, and
    metres-per-pixel is ``156543 * cos(lat) / 2**zoom`` -- the powers of
    two cancel exactly, so the pair reduces to a constant over cos(lat)
    and zoom drops out of the expression entirely. That is the same
    statement as "a streak is the same size on screen at every zoom",
    which is what two separate knobs were being used to arrange.
    """
    import re as _re
    src = _strip_js_comments(JS.read_text(encoding="utf-8"))
    assert "particleSpeedFactor" not in src and "particleZoomRef" not in src, (
        "the two collapsed knobs are back")
    speed = float(_re.search(
        r"v\.particleSpeed !== undefined \? v\.particleSpeed : ([\d.]+)",
        src).group(1))
    # A sane magnitude, not an exact value -- the number is tuned by
    # eye and lives in the group checked by
    # test_the_frame_rate_and_trail_defaults_are_one_group.
    assert 0.1 < speed < 1.5, (
        f"particleSpeed {speed} px/frame per m/s is outside any usable "
        f"range; at the capped frame rate this is motion of "
        f"{speed * 30:.0f} px/s for a 1 m/s wind")
    build = _strip_js_comments(_js_fn_body("buildField"))
    assert "var scale = cfg.speed;" in build, (
        "the per-cell scale must be cfg.speed alone — no zoom term and "
        "no latitude term")


def test_streak_length_still_reads_at_both_ends():
    """Readable in a calm cell, bounded in a hurricane -- now computed
    straight from particleSpeed, with no zoom anywhere in it."""
    import math
    import re as _re
    src = _strip_js_comments(JS.read_text(encoding="utf-8"))

    def num(pat):
        m = _re.search(pat, src)
        assert m, pat
        return float(m.group(1))

    speed = num(r"v\.particleSpeed !== undefined \? v\.particleSpeed : ([\d.]+)")
    length = num(r"v\.particleTrailLength \|\| ([\d.]+)")
    floor = num(r"v\.windMinSpeedMs !== undefined \? v\.windMinSpeedMs : ([\d.]+)")
    ceil_ = num(r"v\.windMaxSpeedMs !== undefined \? v\.windMaxSpeedMs : ([\d.]+)")

    def px(wind, lat=29.0):
        return (min(max(wind, floor), ceil_) * speed
                / math.cos(math.radians(lat))) * length

    # The bug this guards is a ONE-PIXEL DOT, not a short dash. The
    # threshold was 10px when the floor was 3 m/s; the floor is 1 m/s
    # now, which deliberately lets calm areas read as calm instead of
    # holding every cell up to the same artificial length.
    assert px(0.5) > 4, (
        f"a calm cell draws {px(0.5):.1f}px — the minSpeed floor has "
        f"stopped holding the low end up at all")
    assert 20 < px(4.0) < 60, f"4 m/s gives {px(4.0):.1f}px"
    assert px(80.0) < 500, f"80 m/s gives {px(80.0):.1f}px"
    # And it cannot vary with zoom, because zoom is not in the formula.
    assert "getZoom" not in _strip_js_comments(_js_fn_body("buildField"))


def test_the_field_grid_and_tile_cap_are_not_viz_knobs():
    """Both are internal constants now.

    Neither has a use the caller can reason about: an 8 px cell is
    already finer than a 0.25 degree forecast grid at every map zoom,
    and the tile cap only governs waste past zoom 10. Exposing them
    invited tuning where there is nothing to tune.
    """
    src = _strip_js_comments(JS.read_text(encoding="utf-8"))
    assert "particleFieldSpacing" not in src
    assert "particleMaxTileZoom" not in src
    assert "var FIELD_SPACING = 8;" in src
    assert "var MAX_TILE_ZOOM = 10;" in src
    assert "Math.min(MAX_TILE_ZOOM" in src, "the tile cap is not applied"
    build = _strip_js_comments(_js_fn_body("buildField"))
    assert "var sp = FIELD_SPACING;" in build

    import geeViz.weather as wx
    viz = _stamped_viz()
    for gone in ("particleFieldSpacing", "particleMaxTileZoom",
                 "particleMinCount", "particleMaxCount",
                 "particleZoomRef", "particleSpeedFactor"):
        assert gone not in viz, f"python still sends {gone}"


def test_a_spent_particle_keeps_flying_while_it_fades():
    """The fade must run in the same direction the particle moves.

    The first version FROZE the particle and pulled its trail into the
    stationary head. That consumes the tail first, which is the right
    order -- but a motionless streak surrounded by moving ones reads as
    drifting backwards, because everything around it is still going
    forward. Keeping it flying while only its trail allowance shrinks
    puts the motion of the fade and the motion of the particle in the
    same direction.
    """
    body = _strip_js_comments(_js_fn_body("frame"))
    branch = body[body.index("if (p.retiring) {"):]
    branch = branch[:branch.index("}") + 1]

    assert "p.retire -= 1;" in branch, (
        "retirement must count DOWN a trail allowance")
    assert "p.xs.shift()" not in branch, (
        "the retirement branch must not retract the trail itself — that "
        "is what froze the particle; the normal trim handles it")
    assert "continue;" in branch and "p.dead = true" in branch, (
        "a fully faded particle must respawn")

    # The particle still advances: the branch must fall THROUGH to the
    # field read rather than skipping it.
    after = body[body.index("if (p.retiring) {"):]
    assert after.index("fieldAt(st, p.x, p.y)") > 0, (
        "a retiring particle never reaches the advection — it is frozen "
        "again")

    # ...and the trim is tail-first, with a shrinking cap.
    assert "var cap = p.retiring ? p.retire : n;" in body, (
        "the trail allowance must shrink only while retiring")
    assert "while (p.xs.length > cap) { p.xs.shift(); p.ys.shift(); }" in body, (
        "the trim must drop the OLDEST points — pop() would eat the head "
        "and the streak would retract backwards")


def test_retirement_starts_from_the_trail_it_actually_has():
    """A particle that died young has a short trail; fading it over the
    full trailLength would leave it frozen-but-alive for frames with
    nothing to draw."""
    body = _strip_js_comments(_js_fn_body("frame"))
    assert body.count("p.retire = p.xs.length;") == 2, (
        "both retirement entries -- old age and no-data -- must size the "
        f"fade to the current trail; found {body.count('p.retire = p.xs.length;')}")
    # BOTH exits, counted. Asserting mere presence passed with the
    # guard stripped from one of them, because the other still had it.
    assert body.count("&& !p.retiring") == 2, (
        f"{body.count('&& !p.retiring')} of the 2 retirement entries "
        f"guard against re-arming; an unguarded one resets p.retire "
        f"every frame and the particle never dies")


# ---------------------------------------------------------------------------
# Seeding layouts
# ---------------------------------------------------------------------------


def test_the_three_layouts_are_available():
    """``random`` scatters, ``grid`` is a strict lattice, ``randomGrid``
    is that lattice under ONE random offset -- even spacing without the
    rows landing identically every time."""
    src = _strip_js_comments(JS.read_text(encoding="utf-8"))
    assert 'v.particleLayout === "grid" || v.particleLayout === "randomGrid"' in src, (
        "the layout is not validated; an unknown value should fall back "
        "to random rather than producing an empty field")
    body = _strip_js_comments(_js_fn_body("layout"))
    assert 'cfg.layout === "randomGrid" ? Math.random() * dx : dx / 2' in body, (
        "randomGrid must offset the WHOLE lattice; offsetting each cell "
        "separately is just `random` with extra steps")
    assert "Math.sqrt((w * h) / n)" in body, (
        "the lattice must use square cells, or the spacing differs "
        "between the axes")


def test_python_sends_the_layout():
    """``particleLayout`` is a string, so it escapes the numeric
    default-parity check that covers the rest of the set -- a deletion
    here would otherwise pass everything."""
    viz = _stamped_viz()
    assert viz.get("particleLayout") == "random", (
        f"python sends {viz.get('particleLayout')!r}; the client would "
        f"fall back to its own default and the two could drift")
    import ee
    import geeViz.weather as wx
    sent = {}

    class FakeMap:
        def addLayer(self, image, viz=None, name=None, visible=True):
            sent[name] = viz or {}

    wx.addWindLayer(FakeMap(), ee.Image([1, 2]).rename(["u", "v"]),
                    {"particleLayout": "randomGrid"}, "W")
    v = [x for x in sent.values() if x.get("windParticles")][0]
    assert v["particleLayout"] == "randomGrid", "an explicit layout is dropped"


def test_a_lattice_particle_returns_to_its_cell():
    """Respawning a grid particle at a random point erodes the pattern
    into noise within a lifetime or two, which defeats the point of
    asking for a grid."""
    body = _strip_js_comments(_js_fn_body("respawn"))
    assert 'p.hx === undefined || cfg.layout === "random"' in body
    assert "p.x = p.hx;" in body and "p.y = p.hy;" in body


def test_the_layout_maths_run():
    """Executed, not grepped."""
    d = _probe_layout()
    assert d["randomCount"] == 2975, d["randomCount"]
    # A lattice lands near the requested count, not exactly on it.
    assert abs(d["gridCount"] - 2975) < 2975 * 0.05, d["gridCount"]
    assert d["cols"] * d["rows"] == d["gridCount"]
    # Square cells, uniform spacing (float noise only).
    assert d["dxSpread"] < 1e-9, d["dxSpread"]
    assert abs(d["dx"] - d["dy"]) < 1.0, (d["dx"], d["dy"])
    # randomGrid keeps the spacing and moves the phase.
    assert d["offsetsDiffer"], "randomGrid produced the same offset twice"
    assert d["randomGridCount"] == d["gridCount"]


# ---------------------------------------------------------------------------
# The two tile-cache bugs
# ---------------------------------------------------------------------------


def test_an_incomplete_field_is_not_cached(cache):
    """A field built while tiles were still in flight must be rebuilt.

    This stamped the view key whenever a SINGLE cell had data, so a
    build that ran mid-load was cached as final and ensureField returned
    true forever after -- leaving large regions permanently blank over a
    map whose loading counter honestly read zero, because the tiles
    really had finished. The field was frozen before they arrived.
    """
    assert cache["incompleteInflight"], "the probe never got a tile in flight"
    assert cache["incompleteKey"] is None, (
        "the field was cached while tiles were still in flight; the "
        "regions those tiles cover stick empty for the life of the page")
    assert cache["completeKeyStamped"], (
        "a field built with everything decoded was still not cached, so "
        "it rebuilds ~34,000 cells on every animation frame")
    assert cache["completeFieldAny"]
    assert cache["ensureSkipsRebuild"], (
        "ensureField rebuilt a field whose view key still matched")


def test_a_failed_tile_is_retried_but_not_forever():
    """One 404 or decode error left a tile-shaped hole in the wind for
    the life of the page, because `false` was cached and `hit !==
    undefined` returned it unconditionally."""
    body = _strip_js_comments(_js_fn_body("getTile"))
    assert "if (hit === false) {" in body, (
        "a failed tile is still cached permanently")
    assert "if (fails >= TILE_RETRIES) return false;" in body, (
        "retries must be bounded, or a genuinely missing tile is "
        "requested on every frame forever")
    assert "hit = undefined;" in body, "the retry never refetches"
    src = _strip_js_comments(JS.read_text(encoding="utf-8"))
    assert "var TILE_RETRIES = 3;" in src
    assert "tileFails: Object.create(null)" in src, (
        "nothing tracks the failure count, so the bound cannot hold")


# ---------------------------------------------------------------------------
# Cost. The renderer has to fit in a frame.
# ---------------------------------------------------------------------------


def test_the_trail_is_stroked_in_bands_not_per_segment():
    """One pass per BAND, not per trail segment.

    Stroking by segment walked every particle once per rank and emitted
    an isolated moveTo+lineTo for each: 145,000 canvas path operations a
    frame at the old defaults, 8.7 million a second. That is what made
    the animation choppy. A band draws a contiguous run as a POLYLINE at
    one alpha, so the moveTo is paid once per band instead of once per
    segment.
    """
    body = _strip_js_comments(_js_fn_body("frame"))
    assert "for (var rank = 1; rank < n; rank++)" not in body, (
        "the per-segment stroke loop is back")
    assert "for (var b = 0; b < bands; b++)" in body
    assert "for (var k = i0 + 1; k <= i1; k++) ctx.lineTo(" in body, (
        "a band must be drawn as a polyline; one moveTo per segment is "
        "the cost this replaced")
    src = _strip_js_comments(JS.read_text(encoding="utf-8"))
    assert "var TRAIL_BANDS = 8;" in src
    # The band COUNT must come from that constant. Pinning it to 1 would
    # draw every trail at one flat alpha -- no taper, no bright head, no
    # comet at all -- while leaving the band loop and the polyline in
    # place for every other assertion here to pass.
    assert "var bands = Math.min(segs, TRAIL_BANDS);" in body, (
        "the band count is not derived from TRAIL_BANDS; a constant "
        "here silently flattens the taper")


def test_the_band_cut_is_hoisted_out_of_the_particle_loop():
    """Almost every trail is full length.

    Computing the band's index range per particle cost two divisions and
    two floors on every visit -- 47,600 a frame -- and made the banded
    version measurably SLOWER than the per-segment one it replaced.
    Cutting the common case once per band fixed it.
    """
    body = _strip_js_comments(_js_fn_body("frame"))
    i_hoist = body.index("var fi0 = Math.floor((b * segs) / bands);")
    i_loop = body.index("for (var j = 0; j < ps.length; j++)")
    assert i_hoist < i_loop, (
        "the full-length band cut must happen before the particle loop")
    assert "if (own === segs) {" in body, (
        "the hoisted values are computed but never used")


def test_the_animation_is_frame_capped():
    """rAF fires at the display rate; we render at FRAME_MS.

    windy.js runs its loop at 30fps for the same reason. A steady 30
    also reads better than an unsteady 50 -- irregular frame times are
    what the eye registers as choppy.
    """
    src = _strip_js_comments(JS.read_text(encoding="utf-8"))
    assert "var FRAME_MS = 1000 / 30;" in src
    body = _strip_js_comments(_js_fn_body("tick"))
    assert "if (now - lastFrameAt >= FRAME_MS) {" in body, (
        "tick renders on every rAF; the cap does nothing")
    assert "lastFrameAt = now;" in body
    # rAF's own timestamp, not a wall clock that can jump.
    assert "function tick(ts)" in body and "ts ||" in body, (
        "the cap should use the monotonic timestamp rAF passes in")
    # ...and rAF must still be rescheduled on the skipped frames, or the
    # loop stops after one tick.
    assert body.rindex("requestAnimationFrame(tick)") > body.index("}"), (
        "rescheduling must sit outside the FRAME_MS branch")


def test_the_frame_rate_and_trail_defaults_are_one_group():
    """Four numbers that only make sense together.

    Streak length is ``trailLength * speed`` and apparent motion is
    ``speed * frameRate``. At a fixed frame rate the trail cannot be
    shortened without speeding the field up, so halving the rate,
    doubling the step and halving the trail is the only change that
    leaves both length and motion exactly as they were -- while drawing
    a quarter as many segments a second. Lifetimes are counted in
    frames, so they halve with the rate too or particles live twice as
    long in wall-clock time.
    """
    import re as _re
    src = _strip_js_comments(JS.read_text(encoding="utf-8"))

    def num(pat):
        m = _re.search(pat, src)
        assert m, pat
        return float(m.group(1))

    # FRAME_MS is written `1000 / 30`, so the captured number IS the
    # frame rate. Dividing it into 1000 again gives 33, not 30 -- which
    # is exactly the slip this assertion then reported.
    fps = num(r"var FRAME_MS = 1000 / ([\d.]+);")
    speed = num(r"v\.particleSpeed !== undefined \? v\.particleSpeed : ([\d.]+)")
    trail = num(r"v\.particleTrailLength \|\| ([\d.]+)")
    max_age = num(r"var maxAge = v\.particleMaxAge \|\| ([\d.]+);")

    # These are TUNED BY EYE, so the test pins the relationship and a
    # sane range rather than three exact numbers -- pinning the numbers
    # just means re-editing the test every time the look is adjusted,
    # which teaches people to edit it without thinking.
    #
    # What must hold: a streak long enough to read and short enough not
    # to smear, motion quick enough to be alive and slow enough to
    # follow, and a lifetime measured in seconds rather than frames.
    length = trail * speed          # px per m/s of wind
    motion = speed * fps            # px/s per m/s of wind
    life = max_age / fps            # seconds

    assert 4.0 < length < 12.0, (
        f"streak length {length:.2f} px per m/s — under ~4 a 4 m/s "
        f"breeze is a dot, over ~12 a gale smears")
    assert 10.0 < motion < 30.0, (
        f"apparent motion {motion:.1f} px/s per m/s — the field either "
        f"crawls or races")
    assert 1.0 < life < 4.0, (
        f"a particle lives {life:.2f}s; much less churns, much more and "
        f"the field goes static")

    # And the coupling itself: lifetimes are counted in FRAMES, so a
    # frame-rate change that does not scale them changes how long a
    # particle lives in wall-clock time.
    assert max_age > trail, (
        f"maxAge {max_age} is not longer than the trail {trail}; every "
        f"particle would retire before its trail ever filled")


def test_the_per_second_cost_is_bounded():
    """A budget, in the units that actually matter.

    The renderer draws ``particles x (trail - 1)`` segments a frame, at
    the capped rate. The old defaults came to 8.7 million canvas path
    operations a second, which no 2D canvas holds at 60fps -- and that
    is measured against a rewrite that was 25x the cost of the fade
    renderer it replaced.
    """
    import math
    import re as _re
    src = _strip_js_comments(JS.read_text(encoding="utf-8"))

    def num(pat):
        return float(_re.search(pat, src).group(1))

    # FRAME_MS is written `1000 / 30`, so the captured number IS the
    # frame rate. Dividing it into 1000 again gives 33, not 30 -- which
    # is exactly the slip this assertion then reported.
    fps = num(r"var FRAME_MS = 1000 / ([\d.]+);")
    trail = num(r"v\.particleTrailLength \|\| ([\d.]+)")
    bands = num(r"var TRAIL_BANDS = ([\d.]+);")
    density = num(r"v\.particleDensity !== undefined \? v\.particleDensity : ([\d.]+)")

    n = 1700 * density                       # a typical canvas
    segs = trail - 1
    # One moveTo per band plus one lineTo per segment.
    ops = n * (segs + min(segs, bands))
    per_sec = ops * fps
    assert per_sec < 3e6, (
        f"{per_sec:,.0f} canvas path operations a second on a 1700px "
        f"canvas — the old design measured 8.7M and was visibly choppy")


# ---------------------------------------------------------------------------
# The particle speed ceiling follows the raster stretch.
# ---------------------------------------------------------------------------


def _wind_viz(viz):
    import ee
    import geeViz.weather as wx
    sent = {}

    class FakeMap:
        def addLayer(self, image, viz=None, name=None, visible=True):
            sent[name] = viz or {}

    wx.addWindLayer(FakeMap(), ee.Image([1, 2]).rename(["u", "v"]), viz, "W")
    return [x for x in sent.values() if x.get("windParticles")][0]


def test_the_speed_ceiling_follows_the_stretch():
    """``particleMaxSpeed`` defaults to ``max``, converted to m/s.

    These used to be unrelated numbers: the stretch is expressed in
    ``units`` while the particle bounds are m/s, so ``units='km/hr',
    max=30`` saturated the colour ramp at 8.3 m/s while the particles
    went on lengthening to a fixed 45. Past ``max`` the raster is one
    flat colour, and a streak that keeps growing there is claiming a
    difference the map has stopped showing.
    """
    import geeViz.weather as wx
    cases = [
        ({}, wx.DEFAULT_MAX_SPEED["km/hr"] / wx.SPEED_UNITS["km/hr"]),
        ({"units": "mi/hr", "max": 100}, 100 / wx.SPEED_UNITS["mi/hr"]),
        ({"units": "km/hr", "max": 30}, 30 / wx.SPEED_UNITS["km/hr"]),
        ({"units": "m/s", "max": 20}, 20.0),
    ]
    for viz, expected in cases:
        got = _wind_viz(dict(viz))["windMaxSpeedMs"]
        assert abs(got - expected) < 1e-6, (
            f"{viz or 'defaults'}: ceiling {got:.2f} m/s against a "
            f"stretch that saturates at {expected:.2f} m/s")


def test_both_bounds_are_derived_from_the_stretch():
    """``particleSpeed`` is the only speed knob.

    The floor and ceiling come from ``min`` and ``max``, converted from
    ``units`` to m/s, so the streaks start and stop growing exactly
    where the colour ramp does. Two hand-set m/s constants alongside a
    stretch in some other unit was a contradiction waiting to be found:
    ``units='km/hr', max=30`` saturated the ramp at 8.3 m/s while the
    particles kept lengthening to a fixed 45.
    """
    import geeViz.weather as wx
    cases = [
        # viz                                        floor   ceiling
        ({"units": "km/hr", "min": 5, "max": 30},     5 / 3.6, 30 / 3.6),
        ({"units": "m/s", "min": 2, "max": 20},       2.0,     20.0),
        ({"units": "mi/hr", "min": 10, "max": 100},
         10 / wx.SPEED_UNITS["mi/hr"], 100 / wx.SPEED_UNITS["mi/hr"]),
    ]
    for viz, floor, ceil_ in cases:
        v = _wind_viz(dict(viz))
        assert abs(v["windMinSpeedMs"] - floor) < 1e-6, (
            f"{viz}: floor {v['windMinSpeedMs']:.2f} != {floor:.2f} m/s")
        assert abs(v["windMaxSpeedMs"] - ceil_) < 1e-6, (
            f"{viz}: ceiling {v['windMaxSpeedMs']:.2f} != {ceil_:.2f} m/s")


def test_a_zero_floor_becomes_one_metre_per_second():
    """``min`` is 0 on nearly every wind map, which would leave no floor
    at all -- and length is proportional to speed, so a light breeze
    draws a one-pixel dot and a calm map reads as broken.

    One METRE PER SECOND specifically, not one of whatever ``units``
    happens to be: the bounds are m/s throughout, and 1 mi/hr is 0.45
    m/s, which would put the dots back.
    """
    for units in ("m/s", "km/hr", "mi/hr"):
        v = _wind_viz({"units": units, "min": 0, "max": 100})
        assert v["windMinSpeedMs"] == 1.0, (
            f"units={units}: a zero stretch floor gave "
            f"{v['windMinSpeedMs']}, not 1 m/s")
    # A negative floor is not a speed; it clamps to zero and then to 1.
    assert _wind_viz({"units": "m/s", "min": -5, "max": 20})["windMinSpeedMs"] == 1.0


def test_a_degenerate_stretch_does_not_invert_the_clamp():
    """A stretch whose max falls below the 1 m/s substitute would give a
    floor above the ceiling, and ``min(max(mag, floor), ceil)`` then
    pins every cell to the ceiling regardless of wind -- a field that
    animates uniformly and looks like data."""
    v = _wind_viz({"units": "m/s", "min": 0, "max": 0.4})
    assert v["windMinSpeedMs"] <= v["windMaxSpeedMs"], (
        f"floor {v['windMinSpeedMs']} exceeds ceiling "
        f"{v['windMaxSpeedMs']}")


def test_there_are_no_speed_bound_parameters():
    """The floor and ceiling are not settable, by design.

    Two loose m/s numbers beside a stretch expressed in some other unit
    is the contradiction this whole thing replaced -- ``units='km/hr',
    max=30`` saturating the ramp at 8.3 m/s while particles lengthened
    to a fixed 45. There is nothing left to set that ``min``, ``max``
    and ``units`` do not already say, so widening the stretch is how you
    widen the range the streaks respond over.
    """
    # The old names are gone from the wire entirely.
    viz = _stamped_viz()
    for gone in ("particleMinSpeed", "particleMaxSpeed"):
        assert gone not in viz, f"{gone} is still sent"
    # Passing one has no effect -- the stretch decides.
    v = _wind_viz({"units": "mi/hr", "max": 100, "particleMaxSpeed": 60})
    assert abs(v["windMaxSpeedMs"] - 100 / 2.236936292054402) < 1e-6, (
        "a stray particleMaxSpeed overrode the stretch; it should be "
        "inert")
    # And the client reads the renamed keys, not the old ones.
    src = _strip_js_comments(JS.read_text(encoding="utf-8"))
    assert "v.particleMinSpeed" not in src and "v.particleMaxSpeed" not in src
    assert "v.windMinSpeedMs" in src and "v.windMaxSpeedMs" in src


def test_the_units_conversion_is_the_right_way_round():
    """``SPEED_UNITS`` holds the multiplier FROM m/s, so a stretch is
    DIVIDED by it. Multiplying instead turns 100 mi/hr into 224 m/s --
    a ceiling no wind reaches, i.e. no ceiling at all, and nothing would
    look wrong until a hurricane smeared across the screen."""
    import geeViz.weather as wx
    got = _wind_viz({"units": "mi/hr", "max": 100})["windMaxSpeedMs"]
    assert 44 < got < 45, f"100 mi/hr came to {got:.1f} m/s; it is 44.7"
    assert got < 100 * wx.SPEED_UNITS["mi/hr"]


def test_the_notebooks_stated_defaults_are_true():
    """The example annotates each knob with "default N". Check the N.

    The notebook deliberately shows some NON-default values (mi/hr, a
    0..100 stretch), so its literals are not the contract -- but its
    parenthetical claims about the defaults are, and they are exactly
    the sort of thing that rots silently as the defaults are retuned.
    Nothing else in this file compares them.
    """
    import json
    import re as _re
    nb = json.loads((ROOT / "geeViz" / "examples" /
                     "weather_forecast_examples.ipynb").read_text(encoding="utf-8"))
    cell = None
    for c in nb["cells"]:
        src = "".join(c["source"])
        if "addWindLayer" in src and "particleSpeed" in src:
            cell = src
            break
    assert cell, "the wind-layer cell is gone from the notebook"

    viz = _stamped_viz()
    # Split into one block per parameter, then read the claim out of the
    # comment that follows it.
    entries = _re.split(r"\n(?=\s*#?\s*'particle)", cell)
    claims, checked = {}, 0
    for e in entries:
        m = _re.search(r"'(particle[A-Za-z]+)'\s*:", e)
        if not m:
            continue
        d = _re.search(r"default\s+([0-9.]+)", e)
        if not d:
            continue
        claims[m.group(1)] = float(d.group(1).rstrip("."))

    assert len(claims) >= 8, (
        f"only found {len(claims)} 'default N' claims in the notebook — "
        f"the parser has drifted and is checking almost nothing")

    wrong = []
    for key, claimed in claims.items():
        if key not in viz:
            continue          # particleCount is deliberately not sent
        actual = float(viz[key])
        # particleMinAge/MaxSize are derived from another default, so
        # compare loosely; everything else is exact.
        if abs(actual - claimed) > 1e-6:
            wrong.append(f"{key}: notebook says {claimed}, actual {actual}")
        checked += 1
    assert checked >= 8, f"only compared {checked} claims"
    assert not wrong, "notebook documents stale defaults — " + "; ".join(wrong)


def test_screen_speed_does_not_vary_with_latitude():
    """No cos(lat) in the advection.

    It used to divide by it, because Mercator genuinely does stretch a
    fixed ground speed into more pixels toward the poles. True, but it
    made the Arctic unreadable: in a world view spanning -60..+80 the
    streaks at the top ran SIX TIMES those at the equator in the same
    frame, and past 85 degrees the factor diverges.

    Dropping it costs nothing geometric. Mercator is conformal, so at
    any point the projection scales u and v by the SAME factor --
    dividing the whole vector field by a scalar field leaves the
    direction at every point unchanged, and therefore leaves the shape
    of every streamline unchanged. Only the speed ALONG a streamline
    differs. The streaks trace exactly the same curves at an even rate.

    It is also the consistent choice: length stopped representing ground
    speed the moment it was made zoom-invariant, so keeping one
    projection term after dropping the other was the odd state.
    """
    body = _strip_js_comments(_js_fn_body("buildField"))
    assert "Math.cos" not in body, (
        "the latitude term is back; a world view will blow up at the "
        "poles again")
    assert "cosLat" not in body
    assert "var scale = cfg.speed;" in body


def test_width_and_length_are_named_for_what_they_measure():
    """WIDTH across the streak, LENGTH along it. ``size`` said neither."""
    src = _strip_js_comments(JS.read_text(encoding="utf-8"))
    for gone in ("particleMinSize", "particleMaxSize", "cfg.minSize",
                 "cfg.maxSize"):
        assert gone not in src, f"{gone} survived the rename"
    for want in ("particleMinWidth", "particleMaxWidth", "cfg.minWidth",
                 "cfg.maxWidth", "particleTrailLength"):
        assert want in src, f"{want} missing"
    viz = _stamped_viz()
    assert "particleMinWidth" in viz and "particleMaxWidth" in viz
    assert "particleMinSize" not in viz and "particleMaxSize" not in viz


def test_a_hidden_layer_clears_its_progress_fill():
    """Unchecking the layer must blank the white fill across its row.

    The viewer sets ``layer.percent = 0`` wherever it hides a layer, and
    the fill is painted from that. Reporting a flat 100 whenever nothing
    was in flight left this one row painted while every other unchecked
    layer went blank -- a small thing, but it makes the particle layer
    look like it is still doing something.
    """
    body = _strip_js_comments(_js_fn_body("reportProgress"))
    assert "var visible = L.visible !== false;" in body, (
        "progress is reported without consulting visibility")
    assert "var percent = !visible ? 0" in body, (
        "a hidden layer must report 0 percent, not 100")
    assert "var loading = visible && inflight > 0;" in body, (
        "a hidden layer must not report as loading either — the spinner "
        "would spin on a layer nobody is looking at")


def test_the_canvas_is_restacked_when_layers_are_reordered():
    """Dragging a raster above the particles must actually reorder them.

    ``overlayLayer`` is documented as the pane holding "polylines,
    polygons, ground overlays and TILE LAYER OVERLAYS" -- so
    ``map.overlayMapTypes`` and this canvas share one pane, and a
    z-index orders them against each other. ``layerId`` is the index the
    viewer passes to ``overlayMapTypes.setAt``, so matching it puts the
    particles into the same stack the rasters use.

    The z-index must be RE-APPLIED rather than written once. Dragging
    runs the viewer's updateMapLayerOrder, which reassigns every
    ``layer.layerId`` and re-adds the rasters at their new index; a
    value written at adoption keeps whatever order the list had when the
    layer was created, and the drag appears to do nothing.
    """
    src = _strip_js_comments(JS.read_text(encoding="utf-8"))
    assert "function applyStacking(st, canvas)" in src
    body = _strip_js_comments(_js_fn_body("applyStacking"))
    assert "L.layerId" in body, (
        "the stack position must come from layerId — that is the index "
        "the rasters are placed at")
    assert "c.style.zIndex = z;" in body

    # Applied on the refresh tick, not only at adoption.
    refresh = _strip_js_comments(_js_fn_body("refreshRunState"))
    assert "applyStacking(st)" in refresh, (
        "the z-index is never refreshed, so a drag cannot reorder the "
        "particles")
    # ...and still set on first paint, so the first frame is not wrong.
    add = _strip_js_comments(JS.read_text(encoding="utf-8"))
    assert "applyStacking(st, c);" in add, (
        "onAdd no longer stacks the canvas; the first paint would sit "
        "at the default position")


def test_the_canvas_stays_in_the_tile_overlay_pane():
    """``mapPane``, not ``overlayLayer``.

    This test used to assert the opposite, on the stated grounds that
    "mapPane is below the tile overlays entirely". Measured in a browser,
    with a wind layer and the satellite Labels overlay on one map, that
    is backwards: ``map.overlayMapTypes`` render as containers INSIDE
    mapPane, stacked with small z-indexes, and the OverlayView panes sit
    above all of them --

        mapPane      100   <- every tile layer lives in here
        overlayLayer 101   <- where the canvases used to go
        overlayShadow 102, markerLayer 103, ...

    -- so a canvas in overlayLayer was above every raster no matter what
    the layer list said, and the z-index ``applyStacking`` maintains
    ordered the two wind canvases against each other and nothing else.
    The visible symptom was the satellite labels, which
    ``addLabelOverlay`` deliberately parks at the top index so place
    names stay readable, sitting under the wind.

    Kept as a source check because it is cheap and names the pane
    exactly; ``test_wind_pane_stacking.py`` is the behavioral one, and
    it reports which pane the canvases were actually appended to.
    """
    src = _strip_js_comments(JS.read_text(encoding="utf-8"))
    assert "getPanes().mapPane" in src, (
        "the canvas left the pane the tile layers are in; z-index can no "
        "longer order it against them")
    assert "getPanes().overlayLayer" not in src, (
        "a canvas is still going to overlayLayer, which floats it above "
        "every tile layer including the labels overlay")


# ---------------------------------------------------------------------------
# Keeping a time lapse fluid
# ---------------------------------------------------------------------------


def test_a_frame_change_does_not_blank_the_field(cache):
    """The particles must keep moving while the next hour loads.

    buildField used to fill straight into the field being drawn,
    blanking it first. On a time lapse that is a freeze on every step:
    the instant the hour advances none of the new frame's tiles are
    decoded, the build resolves nothing, fieldAny goes false, tick()
    skips the draw entirely — and the flow stops dead until the tiles
    land. At the viewer's 666 ms per frame that is most of the time,
    which is what "the particles don't update quickly enough" is.
    """
    assert cache["beforeStepFieldAny"], "the probe never got a field up"
    assert cache["afterStepEnsureTrue"], (
        "ensureField went false on a frame change, so tick() stops "
        "drawing and the particles freeze until tiles arrive")
    assert cache["afterStepFieldAny"], "the field went empty on a frame change"
    assert cache["afterStepKeptSameBuffer"], (
        "the live field buffer was replaced before the new frame was "
        "ready")
    assert cache["afterStepSampleUnchanged"], (
        "the field being drawn was overwritten with a half-built one")


def test_the_new_frame_takes_over_once_its_tiles_land(cache):
    """The other half. Holding the old field is only right until the
    new one is complete — past that it would be the frame-0 bug again,
    a flow that animates through a field that never changes."""
    assert cache["afterTilesSwapped"], (
        "the new frame's field never replaced the old one")
    assert cache["afterTilesFieldAny"]
    assert cache["afterTilesKeyStamped"]


def test_an_incomplete_build_backs_off(cache):
    """buildField is ~34,000 cells, each an inverse projection plus a
    tile lookup. Retrying at the animation rate while tiles stream in
    spends more main thread on rebuilding than on drawing — which reads
    as the whole map going sluggish and gets blamed on the GPU."""
    assert cache["incompleteBackoffArmed"], (
        "an incomplete build did not arm the back-off; it will rebuild "
        "every animation frame")
    assert cache["throttleHeld"], "the back-off did not hold"
    assert cache["throttleReleased"], (
        "the back-off never released — the field would never finish")
    assert cache["completeBackoffCleared"], (
        "a completed build left the back-off armed")


def test_the_next_frames_are_warmed_before_they_are_needed(cache):
    """A lapse arriving at each hour with an empty cache is the cold
    start that makes it lag. Warming the hours ahead while the current
    one plays means the step finds its tiles already decoded."""
    assert cache["warmedFrames"] == ["f1", "f2"], (
        f"warmed {cache['warmedFrames']}, expected the two frames after "
        f"the one on screen")
    # 3x3 per frame, not 2x2. The grid is counted out from the canvas's
    # NW CORNER, which starts partway into a tile, so a 512 px view at
    # 256 px tiles touches three columns and three rows. Deriving the
    # rect from the two corners' longitudes gave 2x2 -- and could not
    # cross the dateline at all, which is why it is gone.
    assert cache["warmedCount"] == 18, (
        f"warmed {cache['warmedCount']} tiles; a 512 px view touches a "
        f"3x3 tile rect, so two frames is 18")


def test_warming_never_enters_the_in_flight_queue(cache):
    """The load-bearing asymmetry.

    buildField reads st.inflight as "the frame ON SCREEN is not resolved
    yet". Counting a prefetch for a later hour there would leave every
    build looking incomplete: the field key would never be stamped, the
    field would rebuild on every animation frame forever, and the
    back-off would never disarm. Faster prefetching would have made the
    thing slower.
    """
    assert cache["warmQueued"] == 1, "the warm fetch never happened"
    assert cache["warmInflight"] == 0, (
        "a prefetch entered the in-flight queue; the current frame will "
        "never count as complete")
    assert cache["warmInflightAfter"] == 0
    assert cache["warmInflightStillZero"] == 0, (
        "warmNextFrames left tiles in the in-flight queue")
    assert cache["warmDecodedUnderOwnKey"], (
        "the warmed tile was not cached under its own frame's key, so "
        "the frame it was fetched for will fetch it again")
    assert cache["warmDidNotTouchCurrentFrame"], (
        "warming wrote into the showing frame's cache slot")
