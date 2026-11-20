"""Delta layer rows: the opacity slider never cuts off the layer name. When a
row's name changes, the row is fitted again: stacked if the name no longer
fits inline, inline again once it does. Loading shows in the row's
background and never changes its layout.

Offline: the shell stub, rows built through the store.
"""

SHELL = {"delta-test": "shell"}
NAME = "LCMS Land Cover timelapse"

ROW = """(n) => {
  const r = Array.from(document.querySelectorAll('#layer-list .layer')).find(x => x.querySelector('.lname').textContent === n);
  const name = r.querySelector('.lname'); const s = r.querySelector('input.op').getBoundingClientRect();
  return {stack: r.classList.contains('stack'), cut: name.scrollWidth > name.clientWidth + 1,  // fitRows' 1px rounding allowance
          slack: name.clientWidth - name.scrollWidth, busy: r.classList.contains('busy'), sliderTop: Math.round(s.top),
          spinners: r.querySelectorAll('.spin').length};
}"""


def settle(page, ms=60):
    page.evaluate("(ms) => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, ms))))", ms)


def set_left_width(page, w):
    page.evaluate("(w) => __delta.store.update(s => ({...s, panes: {...s.panes, left: {...s.panes.left, width: w}}}), 'test')", w)
    settle(page)


def patch(page, name, p):
    page.evaluate(
        "([n, p]) => __delta.store.update(s => ({...s, layers: s.layers.map(l => l.name === n ? {...l, ...p} : l)}), 'test')", [name, p]
    )
    settle(page)


def threshold(page, name):
    """The narrowest pane width at which the row is inline (the name just fits)."""
    for w in range(240, 751, 2):
        set_left_width(page, w)
        if not page.evaluate(ROW, name)["stack"]:
            return w
    raise AssertionError("never inline")


def test_loading_never_moves_the_slider(delta_page):
    """As the user saw: a spinner appearing while tiles loaded pushed the
    opacity slider to a new line, and it came back when the spinner went.
    Loading is now the row's background, so the layout stays put."""
    page = delta_page(SHELL)
    page.evaluate("(n) => __delta.api.addLayer({}, {}, n)", NAME)
    settle(page)
    w = threshold(page, NAME)  # the name only just fits beside the slider
    before = page.evaluate(ROW, NAME)
    assert not before["stack"] and not before["cut"], (w, before)
    patch(page, NAME, {"loading": True})
    r = page.evaluate(ROW, NAME)
    assert r["busy"] and r["spinners"] == 0, r
    assert not r["stack"] and r["sliderTop"] == before["sliderTop"], (w, before, r)
    # tile progress: the row fills, still no layout change
    patch(page, NAME, {"progress": {"total": 10, "loaded": 4, "failed": 0}})
    r = page.evaluate(ROW, NAME)
    assert not r["busy"] and not r["stack"] and r["sliderTop"] == before["sliderTop"], r
    assert page.evaluate("(n) => [...document.querySelectorAll('#layer-list .layer')].find(x => x.textContent.includes(n)).style.getPropertyValue('--prog')", NAME) == "40%"
    patch(page, NAME, {"loading": False, "progress": {"total": 10, "loaded": 10, "failed": 0}})
    r = page.evaluate(ROW, NAME)
    assert not r["busy"] and not r["stack"], r


def test_name_change_refits_the_row(delta_page):
    page = delta_page(SHELL)
    page.evaluate("() => __delta.api.addLayer({}, {}, 'Short')")
    settle(page)
    set_left_width(page, 330)
    assert not page.evaluate(ROW, "Short")["stack"]
    longer = "Forest canopy cover change trend"  # fits on its own line, not beside the slider
    patch(page, "Short", {"name": longer})
    r = page.evaluate(ROW, longer)
    assert r["stack"] and not r["cut"], r
    patch(page, longer, {"name": "Short"})
    assert not page.evaluate(ROW, "Short")["stack"]
