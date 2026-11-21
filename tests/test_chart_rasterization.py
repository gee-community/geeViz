"""Rasterizing a chart needs a browser — say so when there isn't one.

Reported from a live session: ``generate_map_chart_gif`` failed, and the
agent rebuilt a worse version of it by hand rather than reporting the
real problem. The traceback was:

    ChromeNotFoundError: Kaleido v1 and later requires Chrome to be
    installed.
      at outputLib/thumbs.py:3967 -> fig.to_image(...)

Nothing was wrong with the function. A Plotly figure is JavaScript, so
turning one into a PNG means running a browser. kaleido 0.x bundled its
own Chromium; kaleido 1.0 removed it and looks for a browser already on
the machine. ``python:3.12-slim`` has none.

geeViz declared kaleido only under the ``mcp`` extra and unpinned, so a
rebuild after 1.0 shipped silently swapped a self-contained renderer for
one with an external dependency. The same shape as starlette-admin
0.x -> 1.0 breaking the admin panel: a major version crossed on its own
and changed a runtime contract.

Four shipped features rasterize charts, so all four broke at once — and
so did ``html_to_png``, which drives a browser directly for Sankey PNGs
and had been returning None the whole time.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RENDER = (ROOT / "outputLib" / "_render.py").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def R():
    import sys
    sys.path.insert(0, str(ROOT.parent))
    from geeViz.outputLib import _render
    return _render


# ── telling a missing browser from a real render failure ───────────────

def test_a_real_render_error_is_not_reported_as_a_missing_browser(R):
    """Sending someone to install software they already have wastes
    their time and hides the actual defect."""
    assert R._is_missing_chrome(ValueError("invalid figure spec")) is False


def test_detected_by_class_name(R):
    class ChromeNotFoundError(Exception):
        pass
    assert R._is_missing_chrome(ChromeNotFoundError("x")) is True


def test_detected_through_a_cause_chain(R):
    """Plotly wraps kaleido's error, so the original arrives as
    __cause__ rather than as the exception itself."""
    class ChromeNotFoundError(Exception):
        pass
    try:
        try:
            raise ChromeNotFoundError("inner")
        except Exception as e:
            raise RuntimeError("wrapped") from e
    except Exception as e:
        assert R._is_missing_chrome(e) is True


def test_detected_by_message_when_the_class_is_unavailable(R):
    """The class lives in choreographer, kaleido's transitive
    dependency, which is not ours to import."""
    assert R._is_missing_chrome(
        Exception("Kaleido v1 requires Chrome to be installed")) is True


def test_the_cause_walk_terminates_on_a_cycle(R):
    """__context__ chains can loop; a hang here would be worse than the
    bug being diagnosed."""
    a, b = Exception("a"), Exception("b")
    a.__cause__ = b
    b.__cause__ = a
    assert R._is_missing_chrome(a) is False


# ── when to download 150 MB, and when not to ───────────────────────────

def test_a_serverless_runtime_never_downloads_on_demand(R, monkeypatch):
    """~150 MB fetched inside a request on a cold instance is how a slow
    chart becomes a gateway error. Cloud Run gets the instruction
    instead; the image is where the browser belongs."""
    monkeypatch.setenv("K_SERVICE", "geeviz-agent-prod")
    monkeypatch.delenv("GEEVIZ_AUTO_GET_CHROME", raising=False)
    assert R._may_autoget() is False


def test_an_interactive_process_may_download(R, monkeypatch):
    for v in R._SERVERLESS_VARS:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.delenv("GEEVIZ_AUTO_GET_CHROME", raising=False)
    assert R._may_autoget() is True


def test_the_env_flag_overrides_in_both_directions(R, monkeypatch):
    for v in R._SERVERLESS_VARS:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("GEEVIZ_AUTO_GET_CHROME", "0")
    assert R._may_autoget() is False
    monkeypatch.setenv("K_SERVICE", "x")
    monkeypatch.setenv("GEEVIZ_AUTO_GET_CHROME", "1")
    assert R._may_autoget() is True


def test_a_failed_download_is_not_retried_all_session(R, monkeypatch):
    """The usual causes - no network, read-only filesystem - will not
    have changed by the next chart, and each attempt is slow.

    Patches get_chrome ON the real plotly.io. An earlier version
    replaced sys.modules["plotly.io"] with a stub ModuleType, which is
    not a package, so a later ``import plotly.io._kaleido`` elsewhere in
    the suite died with ModuleNotFoundError. It passed alone and failed
    in the full run.
    """
    import plotly.io as pio
    monkeypatch.setattr(R, "_attempted", False)
    calls = []

    def _boom(*a, **k):
        calls.append(1)
        raise RuntimeError("no network")

    monkeypatch.setattr(pio, "get_chrome", _boom, raising=False)
    assert R.ensure_chrome() is False
    assert R.ensure_chrome() is False
    assert len(calls) == 1, "retried a download that had already failed"


# ── the message ────────────────────────────────────────────────────────

def test_the_message_says_why_not_just_what(R):
    """The raw traceback read like a bug in geeViz. It is a missing
    binary, and the reader cannot act until they know which."""
    hint = R._install_hint()
    assert "JavaScript" in hint
    assert "kaleido 1.0 removed it" in hint


def test_the_message_gives_a_command_for_this_platform(R):
    """A generic "install Chrome" sends the reader to a download page
    when a one-line package install would do."""
    import sys
    hint = R._install_hint()
    if sys.platform.startswith("linux"):
        assert "apt-get install -y chromium" in hint
    elif sys.platform == "win32":
        assert "winget" in hint
    elif sys.platform == "darwin":
        assert "brew" in hint


def test_the_message_offers_both_routes(R):
    hint = R._install_hint()
    assert "plotly_get_chrome" in hint
    assert "pio.get_chrome()" in hint


def test_the_message_prefers_a_system_browser_and_says_why(R):
    """kaleido's private copy does not help html_to_png, which drives a
    browser itself for Sankey PNGs."""
    hint = R._install_hint()
    assert "html_to_png" in hint


def test_the_message_says_build_time_for_containers(R):
    assert "BUILD" in R._install_hint()


# ── every rasterizing site goes through the helper ─────────────────────

@pytest.mark.parametrize("mod", ["charts.py", "thumbs.py"])
def test_no_module_calls_to_image_directly(mod):
    """Four sites failed identically because each called to_image bare.
    One helper means one place to fix the next such change.

    Accepts either entry point: thumbs.py uses the single-figure
    fig_to_png in one place and the batch figs_to_pngs in the frame
    loop, so counting "fig_to_png(" alone under-reports it.
    """
    src = (ROOT / "outputLib" / mod).read_text(encoding="utf-8")
    code = [ln for ln in src.splitlines()
            if not ln.lstrip().startswith("#")]
    bare = [ln for ln in code
            if re.search(r"\bto_image\(", ln) and "fig_to_png" not in ln]
    assert not bare, f"{mod} still calls to_image directly: {bare}"
    # The call sites alias the import (``as _fig_to_png``), so a \b
    # before "fig" never matches — the preceding underscore is a word
    # character.
    assert re.search(r"figs?_to_pngs?\(", src), (
        f"{mod} does not route through the render helper")


def test_the_frame_loop_renders_in_one_browser_session():
    """Rendering inside the loop launched a browser PER FRAME — 40 for a
    40-year collection. Slow, and each teardown is another chance to hit
    choreographer's "Couldn't close or kill browser subprocess"."""
    src = (ROOT / "outputLib" / "thumbs.py").read_text(encoding="utf-8")
    i = src.index("def generate_map_chart_gif")
    body = src[i:i + 30000]
    loop = body.index("for i in range(n):")
    after = body.index("figs_to_pngs(", loop)
    assert "fig_to_png(" not in body[loop:after], (
        "single-figure render is still inside the per-frame loop")


def test_a_teardown_failure_does_not_discard_rendered_images():
    """kaleido tears the browser down in __aexit__, AFTER writing the
    images, and choreographer raises there reliably on Windows.

    Treating that as a render failure threw away a complete set of good
    PNGs, re-rendered them one at a time, hit the same teardown again,
    and finally gave up — observed on a real 40-frame run, which now
    completes.
    """
    render = (ROOT / "outputLib" / "_render.py").read_text(encoding="utf-8")
    body = render[render.index("def figs_to_pngs"):]
    assert "failure = exc" in body, "the exception is not deferred"
    assert body.index("failure = exc") < body.index("for p in paths:"), (
        "images are read before the failure is deferred")
    assert "cleanup problem, not a rendering one" in body


def test_kaleido_is_a_core_dependency():
    """It backs four shipped features, so it is not optional. It was
    declared only under the ``mcp`` extra, and unpinned — which is how
    0.x -> 1.0 crossed silently."""
    setup = (ROOT.parent / "setup.py").read_text(encoding="utf-8")
    core, _, extras = setup.partition("extras_require")
    assert "kaleido" in core, "kaleido is not in install_requires"
    assert re.search(r'"kaleido>=1', core), "no version floor on kaleido"


def test_the_container_installs_a_browser():
    """The actual repair. Both rasterization paths discover a system
    browser; the slim image had none."""
    df = (ROOT.parent / "geeViz_agent" / "Dockerfile").read_text(encoding="utf-8")
    install = df[df.index("apt-get install"):df.index("rm -rf /var/lib/apt/lists")]
    assert "chromium" in install


def test_reports_do_not_rasterize_charts_at_all():
    """Since 2026-11-17 a report PDF is its HTML printed by Chromium, so
    charts stay vector Plotly and reports.py has no rasterizing site
    left (the old PDF path rendered every chart through kaleido)."""
    src = (ROOT / "outputLib" / "reports.py").read_text(encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    assert not re.search(r"\bto_image\(|figs?_to_pngs?\(|html_to_png\(", code)
