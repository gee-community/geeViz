"""Delta panes on desktop: as tall as their content, at most the window, the
content area scrolls under a pinned header (brand and search on the left, the
tool strip on the right). The map is live below a short pane.

Offline: the shell stub.
"""
import pytest

SHELL = {"delta-test": "shell"}
VH = 900
# panes stop above the status bar (26) and Google's strip (24) below the map
CAP = VH - 26 - 24

R = "(s) => { const b = document.querySelector(s).getBoundingClientRect(); return {top: b.top, bottom: b.bottom, height: b.height, left: b.left, right: b.right}; }"


def r(page, sel):
    return page.evaluate(R, sel)


def settle(page):
    page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")


def add_layers(page, n, start=0):
    page.evaluate("([n, s]) => { for (let i = s; i < s + n; i++) __delta.api.addLayer({}, {}, 'Layer ' + i); }", [n, start])
    settle(page)


def scrolls(page, sel):
    return page.evaluate("(s) => { const e = document.querySelector(s); return e.scrollHeight > e.clientHeight + 1 && ['auto', 'scroll'].includes(getComputedStyle(e).overflowY); }", sel)


@pytest.mark.parametrize("scheme", ["dark", "light"])
def test_left_pane_fits_content_then_caps_and_scrolls(delta_page, scheme):
    page = delta_page(SHELL, color_scheme=scheme)
    add_layers(page, 2)
    pane, mount = r(page, "#pane-left"), r(page, "#layers-mount")
    assert pane["top"] == 0 and pane["height"] < VH / 2, pane
    assert abs(pane["bottom"] - mount["bottom"] - 1) <= 2, (pane, mount)  # the content plus the bottom border
    assert not scrolls(page, "#layers-mount")
    # a visible end: bottom border in the line token, rounded outer corner, shadow
    end = page.evaluate("""() => { const c = getComputedStyle(document.querySelector('#pane-left'));
      const d = document.createElement('div'); d.style.color = 'var(--dz-line)'; document.body.appendChild(d); const line = getComputedStyle(d).color; d.remove();
      return {bw: c.borderBottomWidth, bc: c.borderBottomColor, line, br: parseFloat(c.borderBottomRightRadius), bl: parseFloat(c.borderBottomLeftRadius), shadow: c.boxShadow}; }""")
    assert end["bw"] == "1px" and end["bc"] == end["line"] and end["br"] > 0 and end["bl"] == 0 and end["shadow"] != "none", end
    # grows with its content
    add_layers(page, 3, 2)
    assert r(page, "#pane-left")["height"] > pane["height"] + 50
    # capped at the window; the layer list scrolls under the pinned brand and search rows
    add_layers(page, 60, 5)
    pane = r(page, "#pane-left")
    assert abs(pane["height"] - CAP) <= 1, pane
    assert scrolls(page, "#layers-mount")
    page.evaluate("() => { const m = document.querySelector('#layers-mount'); m.scrollTop = m.scrollHeight; }")
    settle(page)
    brand = r(page, "#pane-left .brand")
    assert brand["top"] >= 0 and page.evaluate("([x, y]) => document.querySelector('#pane-left .brand').contains(document.elementFromPoint(x, y))", [brand["left"] + 60, brand["top"] + brand["height"] / 2])
    assert page.locator("#pane-left .search").is_visible()
    assert page.evaluate("document.scrollingElement.scrollTop") == 0


def test_map_is_live_below_a_short_pane(delta_page):
    page = delta_page(SHELL)
    add_layers(page, 2)
    pane = r(page, "#pane-left")
    x, y = (pane["left"] + pane["right"]) / 2, pane["bottom"] + 40
    assert page.evaluate("([x, y]) => document.querySelector('#map').contains(document.elementFromPoint(x, y))", [x, y])
    page.evaluate("() => { window.__mapClicks = 0; document.querySelector('#map').addEventListener('click', () => window.__mapClicks++); }")
    page.mouse.click(x, y)
    assert page.evaluate("window.__mapClicks") == 1


def test_right_pane_heights(delta_page):
    page = delta_page(SHELL)
    # no tool: folded, the tool strip only
    pane, tools = r(page, "#pane-right"), r(page, "#pane-right .tools")
    assert abs(pane["bottom"] - tools["bottom"] - 1) <= 2 and pane["height"] < VH / 2, (pane, tools)
    page.evaluate("__delta.store.set({tool: 'distance'})")
    page.wait_for_function("Math.abs(document.querySelector('#pane-right').getBoundingClientRect().width - 330) <= 1")
    short = r(page, "#pane-right")
    assert short["height"] < VH / 2, short
    end = page.evaluate("() => { const c = getComputedStyle(document.querySelector('#pane-right')); return [c.borderBottomWidth, parseFloat(c.borderBottomLeftRadius), parseFloat(c.borderBottomRightRadius)]; }")
    assert end[0] == "1px" and end[1] > 0 and end[2] == 0, end
    add = "(n) => { const m = document.querySelector('#results-mount'); for (let i = 0; i < n; i++) { const d = document.createElement('div'); d.className = 'card-r'; d.style.height = '120px'; m.appendChild(d); } }"
    page.evaluate(add, 2)
    settle(page)
    grown = r(page, "#pane-right")
    assert grown["height"] > short["height"] + 200 and grown["height"] < VH, (short, grown)
    page.evaluate(add, 12)
    settle(page)
    capped = r(page, "#pane-right")
    assert abs(capped["height"] - CAP) <= 1, capped
    body = page.evaluate("() => document.querySelector('#results-mount').closest('.pane-body') ? '#pane-right .pane-body' : null")
    assert body and scrolls(page, body)
    page.evaluate("(s) => { const m = document.querySelector(s); m.scrollTop = m.scrollHeight; }", body)
    settle(page)
    tools = r(page, "#pane-right .tools")
    assert tools["top"] >= 0 and tools["top"] < 20, tools  # the tool strip stays pinned


def test_grips_follow_pane_height(delta_page):
    page = delta_page(SHELL)
    add_layers(page, 3)
    page.evaluate("__delta.store.set({tool: 'distance'})")
    page.wait_for_function("Math.abs(document.querySelector('#pane-right').getBoundingClientRect().width - 330) <= 1")
    for side in ("left", "right"):
        p, g = r(page, "#pane-" + side), r(page, ".grip[data-side=%s]" % side)
        assert p["height"] < VH and abs(g["top"] - p["top"]) <= 1 and abs(g["height"] - p["height"]) <= 1, (side, p, g)
        assert abs((g["right"] - g["left"]) - 14) <= 0.5
