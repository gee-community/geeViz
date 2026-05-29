"""Smoke test for the unified apply_theme dispatcher and the theme()
context manager. These don't require Earth Engine, only matplotlib /
plotly being importable.

The matplotlib tests are guarded so they skip cleanly when mpl isn't
installed (e.g., in a lean test environment).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from geeViz.outputLib import themes as _t


def test_set_and_get_default_theme():
    _t.set_default_theme("dark")
    assert _t.get_default_theme() == "dark"
    _t.set_default_theme("light")
    assert _t.get_default_theme() == "light"
    _t.set_default_theme("dark")


def test_apply_theme_plotly():
    import plotly.graph_objects as go
    fig = go.Figure(data=[go.Bar(x=[1, 2, 3], y=[1, 4, 9])])
    out = _t.apply_theme(fig, theme="dark")
    assert out is fig
    assert out.layout.paper_bgcolor == "#272822"


def test_apply_theme_uses_default_when_none():
    import plotly.graph_objects as go
    _t.set_default_theme("dark")
    fig = go.Figure(data=[go.Bar(x=[1, 2], y=[3, 4])])
    out = _t.apply_theme(fig)  # no explicit theme arg
    assert out.layout.paper_bgcolor == "#272822"


def test_apply_theme_unknown_type_returns_unchanged():
    class FakeChart:
        pass
    c = FakeChart()
    out = _t.apply_theme(c)  # should print warning, return c
    assert out is c


def test_apply_matplotlib_theme():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  (skip: matplotlib not installed)")
        return
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [1, 4, 9])
    ax.set_title("Test")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    _t.apply_matplotlib_theme(fig, theme="dark")
    # Figure background ≈ #272822 (39/255, 40/255, 34/255, 1.0)
    fc = fig.get_facecolor()
    assert abs(fc[0] - 39 / 255) < 0.01, f"figure facecolor wrong: {fc}"
    # Title color set on the Text object — accept any format that
    # normalizes to the theme text color.
    from matplotlib import colors as mcolors
    title_rgba = mcolors.to_rgba(ax.title.get_color())
    expected_rgba = mcolors.to_rgba("#f8f8f2")
    for i in range(3):  # ignore alpha
        assert abs(title_rgba[i] - expected_rgba[i]) < 0.01, \
            f"title color wrong: {title_rgba} vs {expected_rgba}"
    plt.close(fig)


def test_apply_theme_dispatch_to_matplotlib():
    """Test the dispatcher correctly routes mpl Figures to the mpl themer."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  (skip: matplotlib not installed)")
        return
    fig, ax = plt.subplots()
    ax.plot([1], [1])
    out = _t.apply_theme(fig)  # dispatch
    assert out is fig
    fc = fig.get_facecolor()
    assert abs(fc[0] - 39 / 255) < 0.01
    plt.close(fig)


def test_theme_context_manager_sets_and_restores_rcparams():
    try:
        import matplotlib as mpl
        mpl.use("Agg")
    except ImportError:
        print("  (skip: matplotlib not installed)")
        return
    before = mpl.rcParams["figure.facecolor"]
    with _t.theme("dark"):
        assert mpl.rcParams["figure.facecolor"] == "#272822"
    # Restored to whatever it was before
    assert mpl.rcParams["figure.facecolor"] == before


def test_palettes_attr_and_dict_access():
    from geeViz import geePalettes as p
    assert p.cmocean["Algae"] == p.cmocean.Algae
    assert "Algae" in p.cmocean
    # AttributeError on missing
    try:
        p.cmocean.NotAReal
    except AttributeError as e:
        assert "NotAReal" in str(e)
    else:
        assert False, "Expected AttributeError"


def test_cl_reexports():
    """apply_theme / theme / set_default_theme should be reachable from cl.

    Importing charts.py triggers EE initialization, which prompts for a
    project ID in a bare test env. Read the source for the re-export lines
    instead — this verifies the wiring without firing up Earth Engine.
    """
    src = open(os.path.join(os.path.dirname(__file__), "..", "outputLib", "charts.py"),
               encoding="utf-8").read()
    for name in ("apply_theme", "theme", "set_default_theme",
                 "get_default_theme", "apply_matplotlib_theme"):
        assert name in src, f"{name} not re-exported in charts.py"


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
