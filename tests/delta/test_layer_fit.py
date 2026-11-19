"""Delta layer rows: the opacity slider never cuts off the layer name. When a
row's content changes (the loading spinner appears, the name changes), the row
is fitted again: stacked if the name no longer fits inline, inline again once
it does.

Offline: the shell stub, rows built through the store.
"""

SHELL = {"delta-test": "shell"}
NAME = "LCMS Land Cover timelapse"

ROW = """(n) => {
  const r = Array.from(document.querySelectorAll('#layer-list .layer')).find(x => x.querySelector('.lname').textContent === n);
  const name = r.querySelector('.lname'); const spin = r.querySelector('.spin');
  return {stack: r.classList.contains('stack'), cut: name.scrollWidth > name.clientWidth + 1,  // fitRows' 1px rounding allowance
          slack: name.clientWidth - name.scrollWidth, spinner: spin.getClientRects().length > 0};
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


def test_spinner_restacks_the_row(delta_page):
    page = delta_page(SHELL)
    page.evaluate("(n) => __delta.api.addLayer({}, {}, n)", NAME)
    settle(page)
    w = threshold(page, NAME)
    r = page.evaluate(ROW, NAME)
    assert not r["cut"] and not r["spinner"] and r["slack"] < 12, (w, r)  # the spinner (12px + gap) would not fit
    patch(page, NAME, {"loading": True})
    r = page.evaluate(ROW, NAME)
    assert r["spinner"], r
    assert not r["cut"], (w, r)
    assert r["stack"], (w, r)
    patch(page, NAME, {"loading": False})
    r = page.evaluate(ROW, NAME)
    assert not r["spinner"] and not r["stack"] and not r["cut"], (w, r)


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
