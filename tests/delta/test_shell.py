"""Delta shell: panes, grips, hamburger, theme, Street View, phone layout."""

SHELL = {"delta-test": "shell"}


def width(page, sel):
    return page.evaluate("s => document.querySelector(s).getBoundingClientRect().width", sel)


def booted(page):
    page.wait_for_function("window.__delta !== undefined")


def test_left_default_is_a_third(delta_page):
    page = delta_page(SHELL)
    assert abs(width(page, "#pane-left") - 500) <= 1


def drag_left_grip(page, to_x):
    box = page.locator(".grip[data-side=left]").bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move((x + to_x) / 2, y, steps=4)
    page.mouse.move(to_x, y, steps=4)
    return lambda: page.mouse.up()


def test_resize_and_reset(delta_page):
    page = delta_page(SHELL)
    drag_left_grip(page, 420)()
    assert abs(width(page, "#pane-left") - 420) <= 1
    page.reload()
    booted(page)
    assert abs(width(page, "#pane-left") - 420) <= 1
    page.locator(".grip[data-side=left]").dblclick()
    assert abs(width(page, "#pane-left") - 500) <= 1
    page.reload()
    booted(page)
    assert abs(width(page, "#pane-left") - 500) <= 1


def test_resize_is_clamped(delta_page):
    page = delta_page(SHELL)
    up = drag_left_grip(page, 100)
    assert abs(width(page, "#pane-left") - 240) <= 1
    page.mouse.move(1400, 300, steps=5)
    assert abs(width(page, "#pane-left") - 750) <= 1
    up()


def test_hamburger_hides_and_shows(delta_page):
    page = delta_page(SHELL)
    page.click("#hamburger")
    assert page.evaluate("__delta.store.get().panes.left.visible") is False
    assert "showSidebar=false" in page.url
    assert page.locator("#hamburger-float").is_visible()
    page.wait_for_function("document.querySelector('#pane-left').getBoundingClientRect().right <= 1")
    page.reload()
    booted(page)
    assert page.evaluate("__delta.store.get().panes.left.visible") is False
    # after a reload under load the float button can still be settling:
    # wait for it, then for the store, rather than reading at once
    page.locator("#hamburger-float").wait_for(state="visible")
    page.click("#hamburger-float")
    page.wait_for_function("__delta.store.get().panes.left.visible === true", timeout=5000)
    assert "showSidebar=false" not in page.url
    page.wait_for_function("document.querySelector('#pane-left').getBoundingClientRect().right > 499")


def test_right_pane_folds_without_tool(delta_page):
    page = delta_page(SHELL)
    page.evaluate("__delta.store.set({tool: 'distance'})")
    page.wait_for_function("Math.abs(document.querySelector('#pane-right').getBoundingClientRect().width - 330) <= 1")
    page.evaluate("__delta.store.set({tool: null})")
    page.wait_for_function("Math.abs(document.querySelector('#pane-right').getBoundingClientRect().width - 64) <= 1")
    assert abs(width(page, "#pane-right") - 64) <= 1


def test_tool_buttons_drive_the_store(delta_page):
    page = delta_page(SHELL)
    page.click("#pane-right .tool[data-tool=measure]")
    assert page.evaluate("__delta.store.get().tool") == "distance"
    page.click("#pane-right .tool[data-tool=measure]")
    assert page.evaluate("__delta.store.get().tool") is None


def test_measure_button_toggles_distance_and_area(delta_page):
    page = delta_page(SHELL)
    tool = "__delta.store.get().tool"
    measure = "#pane-right .tool[data-tool=measure]"
    # one Measure button, no separate Distance or Area buttons
    assert page.evaluate("document.querySelectorAll('#pane-right .tool[data-tool=distance], #pane-right .tool[data-tool=area]').length") == 0
    page.click(measure)
    assert page.evaluate(tool) == "distance"
    assert "on" in page.get_attribute(measure, "class")
    # its options switch between Distance and Area
    page.click("#tool-options .seg[data-k=measure] [data-v=area]")
    assert page.evaluate(tool) == "area"
    assert page.get_attribute("#tool-options .seg[data-k=measure] [data-v=area]", "aria-pressed") == "true"
    assert "on" in page.get_attribute(measure, "class")
    # clicking Measure again turns it off; once more reopens the last mode
    page.click(measure)
    assert page.evaluate(tool) is None
    page.click(measure)
    assert page.evaluate(tool) == "area"
    # a script turning on distance lights the Measure button too
    page.evaluate("__delta.store.set({tool: 'distance'}, 'test')")
    assert "on" in page.get_attribute(measure, "class")
    assert page.get_attribute("#tool-options .seg[data-k=measure] [data-v=distance]", "aria-pressed") == "true"


def test_streetview_hides_everything(delta_page):
    page = delta_page(SHELL)
    page.evaluate("__delta.store.set({tool: 'distance'})")
    for sel in ("#pane-left", "#pane-right", "#status"):
        assert page.locator(sel).is_visible()
    page.evaluate("__delta.shell.setStreetView(true)")
    for sel in ("#pane-left", "#pane-right", "#status", "#hamburger-float"):
        assert not page.locator(sel).is_visible()
    page.evaluate("__delta.shell.setStreetView(false)")
    for sel in ("#pane-left", "#pane-right", "#status"):
        assert page.locator(sel).is_visible()


def theme(page):
    return page.evaluate("document.documentElement.getAttribute('data-bs-theme')")


def test_theme_follows_system(delta_page):
    page = delta_page(SHELL, color_scheme="dark")
    assert theme(page) == "dark"
    page.emulate_media(color_scheme="light")
    page.wait_for_function("document.documentElement.getAttribute('data-bs-theme') === 'light'")
    page.emulate_media(color_scheme="dark")
    page.wait_for_function("document.documentElement.getAttribute('data-bs-theme') === 'dark'")


def test_theme_choice_persists(delta_page):
    page = delta_page(SHELL, color_scheme="light")
    assert theme(page) == "light"
    page.click("#theme-btn")
    assert theme(page) == "dark"
    page.reload()
    booted(page)
    assert theme(page) == "dark"
    assert page.evaluate("localStorage.getItem('delta-theme')") == "dark"
    # an explicit choice beats the system setting
    page.emulate_media(color_scheme="light")
    assert theme(page) == "dark"


def test_phone_layout(delta_page):
    page = delta_page(SHELL, viewport={"width": 390, "height": 844})
    buttons = page.locator("#mtabs [data-m]")
    assert buttons.count() == 3
    assert [t.strip() for t in buttons.all_inner_texts()] == ["Layers", "Tools", "Output"]
    layers = page.locator("#mtabs [data-m=layers]")
    layers.click()
    assert "m-layers" in page.evaluate("document.body.className")
    layers.click()
    assert "m-layers" not in page.evaluate("document.body.className")
    # only one sheet at a time
    layers.click()
    page.locator("#mtabs [data-m=tools]").click()
    cls = page.evaluate("document.body.className")
    assert "m-tools" in cls and "m-layers" not in cls


def test_phone_logo_menu_sets_theme(delta_page):
    page = delta_page(SHELL, viewport={"width": 390, "height": 844}, color_scheme="light")
    page.click("#mlogo-btn")
    labels = [t.strip() for t in page.locator("#mmenu [data-t]").all_inner_texts()]
    assert labels == ["Match phone", "Light", "Dark"]
    page.click("#mmenu [data-t=dark]")
    assert theme(page) == "dark"
    page.click("#mlogo-btn")
    page.click("#mmenu [data-t=system]")
    assert theme(page) == "light"
    assert page.evaluate("localStorage.getItem('delta-theme')") is None


def test_phone_theme_follows_the_device(delta_page):
    """On a phone the theme is automatic: the top bar has no light/dark
    switch (the logo menu still overrides), and the page follows the
    device's setting as it changes."""
    page = delta_page(SHELL, viewport={"width": 390, "height": 844}, color_scheme="dark")
    assert page.locator("#mtop .ti-sun, #mtop .ti-moon").count() == 0
    assert not page.locator("#theme-btn").is_visible()
    assert theme(page) == "dark"
    page.emulate_media(color_scheme="light")
    page.wait_for_function("document.documentElement.getAttribute('data-bs-theme') === 'light'")


def test_no_page_errors(delta_page):
    page = delta_page(SHELL)
    errs = [e for e in page.delta_errors if "Failed to load resource" not in e]
    assert errs == []


def focusable_in(page, sel):
    """Tab through the page; return True if focus ever lands inside sel."""
    page.evaluate("document.activeElement && document.activeElement.blur()")
    for _ in range(40):
        page.keyboard.press("Tab")
        if page.evaluate("s => !!document.activeElement.closest(s)", sel):
            return True
    return False


def test_hidden_left_pane_is_inert_and_restored(delta_page):
    page = delta_page(SHELL)
    page.click("#hamburger")
    assert page.evaluate("document.querySelector('#pane-left').inert") is True
    assert page.get_attribute("#pane-left", "aria-hidden") == "true"
    page.evaluate("document.querySelector('#theme-btn').focus()")
    assert page.evaluate("document.activeElement.id") != "theme-btn"
    assert not focusable_in(page, "#pane-left")
    page.click("#hamburger-float")
    assert page.evaluate("document.querySelector('#pane-left').inert") is False
    assert page.get_attribute("#pane-left", "aria-hidden") is None
    page.evaluate("document.querySelector('#theme-btn').focus()")
    assert page.evaluate("document.activeElement.id") == "theme-btn"


def test_hidden_state_survives_reload_inert(delta_page):
    page = delta_page({**SHELL, "showSidebar": "false"})
    assert page.evaluate("document.querySelector('#pane-left').inert") is True


def test_closed_phone_sheets_are_inert(delta_page):
    page = delta_page(SHELL, viewport={"width": 390, "height": 844})
    inert = lambda sel: page.evaluate("s => document.querySelector(s).inert", sel)
    assert inert("#pane-left") and inert("#pane-right")
    page.click("#mtabs [data-m=layers]")
    assert not inert("#pane-left") and inert("#pane-right")
    page.click("#mtabs [data-m=tools]")
    assert inert("#pane-left") and not inert("#pane-right")
    page.click("#mtabs [data-m=tools]")
    assert inert("#pane-left") and inert("#pane-right")
    # back to desktop width: both panes are live again
    page.set_viewport_size({"width": 1500, "height": 900})
    assert not inert("#pane-left") and not inert("#pane-right")


def test_theme_applied_before_module_runs(delta_server, _browser):
    ctx = _browser.new_context(color_scheme="dark")
    ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(delta_server) else r.abort())
    page = ctx.new_page()
    # block the module so only the inline head script can set the theme
    page.route("**/delta/js/main.js", lambda r: r.abort())
    page.goto(delta_server + "/geoview.html?delta-test=shell")
    assert theme(page) == "dark"
    ctx.close()


def test_stored_width_is_clamped_on_load_and_resize(delta_page, delta_server):
    page = delta_page(SHELL)
    page.evaluate("localStorage.setItem('delta-left', '5000')")
    page.reload()
    booted(page)
    assert abs(width(page, "#pane-left") - 750) <= 1
    page.set_viewport_size({"width": 800, "height": 900})
    page.wait_for_function("Math.abs(document.querySelector('#pane-left').getBoundingClientRect().width - 400) <= 1")
    # the stored preference itself is untouched
    assert page.evaluate("localStorage.getItem('delta-left')") == "5000"


# ---- pane resize drag (Task 11d): one update per frame, store commit on release ----

import pytest  # noqa: E402


def rect(page, sel):
    return page.evaluate("s => { const b = document.querySelector(s).getBoundingClientRect(); return {left: b.left, right: b.right, width: b.width}; }", sel)


def frames(page, n=2):
    page.evaluate("(n) => new Promise(r => { const f = (k) => k ? requestAnimationFrame(() => f(k - 1)) : r(); f(n); })", n)


@pytest.mark.parametrize("scheme", ["dark", "light"])
def test_drag_left_smaller_and_back(delta_page, scheme):
    page = delta_page(SHELL, color_scheme=scheme)
    page.evaluate("__delta.api.addLayer({}, {}, 'Forest canopy cover change')")
    assert abs(width(page, "#pane-left") - 500) <= 1
    for target, stacked in ((260, True), (500, False)):
        box = page.locator(".grip[data-side=left]").bounding_box()
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(target, y, steps=30)
        page.mouse.up()
        frames(page)
        w = width(page, "#pane-left")
        assert abs(w - target) <= 2, (target, w)
        assert page.evaluate("localStorage.getItem('delta-left')") == str(round(w))
        assert page.evaluate("__delta.store.get().panes.left.width") == round(w)
        # the status bar spans the window below the map; no pane reaches it
        assert abs(rect(page, "#status")["left"]) <= 1
        # steady state is store driven again: no live inline width left behind
        assert page.evaluate("document.querySelector('#pane-left').style.width") == ""
        assert "resizing" not in page.evaluate("document.body.className")
        # layer rows end fitted to the final width (opacity inline only when the name fits)
        row = page.evaluate("() => { const r = document.querySelector('#layer-list .layer'); const n = r.querySelector('.lname'); return {stack: r.classList.contains('stack'), cut: n.scrollWidth > n.clientWidth + 1}; }")
        assert row["stack"] is stacked and not (not row["stack"] and row["cut"]), (target, row)


DRAG = """async ({side, xs}) => {
  const { store } = __delta;
  const grip = document.querySelector('.grip[data-side=' + side + ']');
  const counts = { updates: 0, rootMutations: 0 };
  const off = store.on('change:panes', (v, s, reason) => { if (reason === 'pane-width') counts.updates++; });
  const mo = new MutationObserver((recs) => { counts.rootMutations += recs.length; });
  mo.observe(document.documentElement, { attributes: true, attributeFilter: ['style'] });
  const ev = (type, x) => grip.dispatchEvent(new PointerEvent(type, { bubbles: true, cancelable: true, pointerId: 7, clientX: x, clientY: 300 }));
  const frame = () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  const flush = () => new Promise((r) => setTimeout(r, 0));
  const out = {};
  ev('pointerdown', xs[0]);
  out.resizingAtDown = document.body.classList.contains('resizing');
  const t0 = performance.now();
  for (const x of xs) ev('pointermove', x);
  out.moveMs = performance.now() - t0;
  await flush();
  out.duringUpdates = counts.updates;
  await frame();
  out.duringRootMutations = counts.rootMutations;
  out.duringUpdatesAfterFrame = counts.updates;
  out.duringWidth = document.querySelector('#pane-' + side).getBoundingClientRect().width;
  out.resizingDuring = document.body.classList.contains('resizing');
  out.backdropDuring = getComputedStyle(document.querySelector('#pane-' + side)).backdropFilter;
  out.mapPointerDuring = getComputedStyle(document.querySelector('#map')).pointerEvents;
  out.userSelectDuring = getComputedStyle(document.body).userSelect;
  ev('pointerup', xs[xs.length - 1]);
  await flush();
  out.afterUpdates = counts.updates;
  out.afterRootMutations = counts.rootMutations;
  out.resizingAfter = document.body.classList.contains('resizing');
  out.backdropAfter = getComputedStyle(document.querySelector('#pane-' + side)).backdropFilter;
  await frame();
  out.finalWidth = document.querySelector('#pane-' + side).getBoundingClientRect().width;
  out.stored = localStorage.getItem('delta-' + side);
  off(); mo.disconnect();
  return out;
}"""


@pytest.mark.parametrize("scheme", ["dark", "light"])
def test_drag_updates_store_once_on_release(delta_page, scheme):
    page = delta_page(SHELL, color_scheme=scheme)
    xs = [500 - i * 4 for i in range(60)]  # 500 down to 264
    m = page.evaluate(DRAG, {"side": "left", "xs": xs})
    # no store update and no :root custom property change while dragging
    assert m["duringUpdates"] == 0 and m["duringUpdatesAfterFrame"] == 0, m
    assert m["duringRootMutations"] == 0, m
    # but the pane follows the pointer within a frame
    assert abs(m["duringWidth"] - xs[-1]) <= 1, m
    # one commit on release
    assert m["afterUpdates"] == 1, m
    assert m["afterRootMutations"] >= 1, m
    assert abs(m["finalWidth"] - xs[-1]) <= 1, m
    assert m["stored"] == str(xs[-1]), m
    # resizing only between down and up: no blur, no map pointer events, no text selection
    assert m["resizingAtDown"] and m["resizingDuring"] and not m["resizingAfter"], m
    assert m["backdropDuring"] == "none" and m["backdropAfter"] != "none", m
    assert m["mapPointerDuring"] == "none" and m["userSelectDuring"] == "none", m


def test_drag_right_pane_once_on_release(delta_page):
    page = delta_page(SHELL)
    page.evaluate("__delta.store.set({tool: 'distance'})")
    page.wait_for_function("Math.abs(document.querySelector('#pane-right').getBoundingClientRect().width - 330) <= 1")
    xs = [1500 - 330 - i * 3 for i in range(60)]
    m = page.evaluate(DRAG, {"side": "right", "xs": xs})
    assert m["duringUpdates"] == 0 and m["duringRootMutations"] == 0, m
    want = 1500 - xs[-1]
    assert abs(m["duringWidth"] - want) <= 1 and abs(m["finalWidth"] - want) <= 1, m
    assert m["afterUpdates"] == 1, m
    # map controls track the right pane when it reaches down to them; the status bar spans the window
    cls = page.evaluate("document.body.className")
    ctl = rect(page, "#mapctl")
    want_ctl = want + 6 if "right-over-ctl" in cls else 6
    assert abs((1500 - ctl["right"]) - want_ctl) <= 1, (cls, ctl)
    assert abs(rect(page, "#status")["right"] - 1500) <= 1, cls


# ---- the drag always ends (Task 11d fix round 1) ----

END_DRAG = """async ({how, xs}) => {
  const { store } = __delta;
  const grip = document.querySelector('.grip[data-side=left]');
  let updates = 0;
  const off = store.on('change:panes', (v, s, reason) => { if (reason === 'pane-width') updates++; });
  const pe = (type, x, id = 9) => new PointerEvent(type, { bubbles: true, cancelable: true, pointerId: id, clientX: x, clientY: 300 });
  const frame = () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  grip.dispatchEvent(pe('pointerdown', xs[0]));
  // pointer capture did not take: the moves land on whatever is under the pointer
  for (const x of xs) document.body.dispatchEvent(pe('pointermove', x));
  await frame();
  const during = { resizing: document.body.classList.contains('resizing'), width: document.querySelector('#pane-left').getBoundingClientRect().width };
  const last = xs[xs.length - 1];
  if (how === 'up-document') document.dispatchEvent(pe('pointerup', last));
  else if (how === 'up-window') window.dispatchEvent(pe('pointerup', last));
  else if (how === 'cancel') window.dispatchEvent(pe('pointercancel', last));
  else if (how === 'lost') grip.dispatchEvent(pe('lostpointercapture', last));
  else if (how === 'blur') window.dispatchEvent(new Event('blur'));
  else if (how === 'escape') document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  else if (how === 'other-pointer-up') document.dispatchEvent(pe('pointerup', last, 3));
  await frame();
  const out = {
    during,
    resizing: document.body.classList.contains('resizing'),
    drag: grip.classList.contains('drag'),
    storeWidth: store.get().panes.left.width,
    stored: localStorage.getItem('delta-left'),
    width: document.querySelector('#pane-left').getBoundingClientRect().width,
    updates,
  };
  off();
  return out;
}"""


@pytest.mark.parametrize("how", ["up-document", "up-window", "cancel", "lost", "blur", "escape"])
def test_drag_ends_however_the_pointer_is_released(delta_page, how):
    page = delta_page(SHELL)
    xs = [500 - i * 5 for i in range(40)]  # to 305
    m = page.evaluate(END_DRAG, {"how": how, "xs": xs})
    assert m["during"]["resizing"] and abs(m["during"]["width"] - xs[-1]) <= 1, m
    assert not m["resizing"] and not m["drag"], m
    assert m["storeWidth"] == xs[-1] and m["stored"] == str(xs[-1]) and m["updates"] == 1, m
    assert abs(m["width"] - xs[-1]) <= 1, m
    assert page.evaluate("getComputedStyle(document.querySelector('#map')).pointerEvents") != "none"


def test_drag_ignores_other_pointers(delta_page):
    page = delta_page(SHELL)
    m = page.evaluate(END_DRAG, {"how": "other-pointer-up", "xs": [500, 450]})
    assert m["resizing"] and m["drag"] and m["updates"] == 0, m
    page.evaluate("document.dispatchEvent(new PointerEvent('pointerup', {bubbles: true, pointerId: 9, clientX: 450}))")
    frames(page)
    assert "resizing" not in page.evaluate("document.body.className")
    assert page.evaluate("__delta.store.get().panes.left.width") == 450


def test_new_pointerdown_ends_the_old_drag(delta_page):
    page = delta_page(SHELL)
    out = page.evaluate("""async () => {
      const grip = document.querySelector('.grip[data-side=left]');
      const pe = (type, x, id) => new PointerEvent(type, { bubbles: true, cancelable: true, pointerId: id, clientX: x, clientY: 300 });
      grip.dispatchEvent(pe('pointerdown', 500, 1));
      document.body.dispatchEvent(pe('pointermove', 400, 1));
      grip.dispatchEvent(pe('pointerdown', 400, 2));
      const mid = __delta.store.get().panes.left.width;
      document.body.dispatchEvent(pe('pointermove', 350, 1));  // the old drag no longer moves the pane
      document.body.dispatchEvent(pe('pointermove', 380, 2));
      document.dispatchEvent(pe('pointerup', 380, 2));
      await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
      return { mid, end: __delta.store.get().panes.left.width, resizing: document.body.classList.contains('resizing') };
    }""")
    assert out == {"mid": 400, "end": 380, "resizing": False}, out


def test_click_on_grip_keeps_width(delta_page):
    page = delta_page(SHELL)
    page.evaluate("__delta.store.update(s => ({...s, panes: {...s.panes, left: {...s.panes.left, width: 420}}}), 'test')")
    box = page.locator(".grip[data-side=left]").bounding_box()
    page.mouse.click(box["x"] + 2, box["y"] + box["height"] / 2)
    frames(page)
    assert page.evaluate("__delta.store.get().panes.left.width") == 420
    assert "resizing" not in page.evaluate("document.body.className")


def test_real_drag_released_over_the_map(delta_page):
    page = delta_page(SHELL)
    # As seen on the running demo: pointer capture does not take, so the moves
    # and the release reach whatever is under the pointer (here the map, past the 750px cap).
    page.evaluate("Element.prototype.setPointerCapture = function () { throw new DOMException('no capture', 'NotFoundError'); }; null")
    box = page.locator(".grip[data-side=left]").bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(1000, y, steps=20)
    over = page.evaluate("(p) => document.elementFromPoint(p[0], p[1]).id", [1000, y])
    page.mouse.up()
    frames(page)
    assert over in ("map", ""), over  # not the pane, not the grip
    assert abs(width(page, "#pane-left") - 750) <= 1
    assert page.evaluate("__delta.store.get().panes.left.width") == 750
    assert page.evaluate("localStorage.getItem('delta-left')") == "750"
    assert "resizing" not in page.evaluate("document.body.className")
    assert page.evaluate("document.querySelector('.grip[data-side=left]').classList.contains('drag')") is False


@pytest.mark.parametrize("side", ["left", "right"])
def test_press_just_outside_the_grip_resizes_and_never_reaches_the_map(delta_page, side):
    """As the user saw: a press a few pixels out on the map panned the map
    instead of resizing. The edge zone claims it before the map hears it."""
    page = delta_page(SHELL)
    page.evaluate("__delta.store.set({tool: 'distance'})")
    page.wait_for_timeout(350)  # the right pane's width transition
    page.evaluate("window.__mapHeard = []; ['pointerdown', 'pointermove', 'mousedown'].forEach(t => document.querySelector('#map').addEventListener(t, () => __mapHeard.push(t)))")
    box = page.locator(".grip[data-side=%s]" % side).bounding_box()
    y = box["y"] + min(100, box["height"] / 2)
    x = box["x"] + box["width"] + 4 if side == "left" else box["x"] - 4
    assert page.evaluate("(p) => document.elementFromPoint(p[0], p[1]).id", [x, y]) == "map"
    w0 = page.evaluate("(s) => document.querySelector('#pane-' + s).getBoundingClientRect().width", side)
    to = x + 80 if side == "left" else x - 80
    page.mouse.move(x, y)
    page.evaluate("__mapHeard.length = 0")  # hovering there is the map's; the press is not
    page.mouse.down()
    page.mouse.move(to, y, steps=10)
    page.mouse.up()
    frames(page)
    w1 = page.evaluate("(s) => document.querySelector('#pane-' + s).getBoundingClientRect().width", side)
    assert abs((w1 - w0) - 80) <= 2, (w0, w1)  # follows the pointer, no jump
    assert page.evaluate("__mapHeard") == []
    # a press well out on the map is the map's
    page.mouse.click(700, 400)
    assert "pointerdown" in page.evaluate("__mapHeard")


# ---- grips are easy to grab (Task 11f) ----

HIT = """([x, y]) => { const e = document.elementFromPoint(x, y); return e ? (e.classList.contains('grip') ? 'grip:' + e.dataset.side : (e.id || e.className || e.tagName)) : null; }"""


def test_grip_hit_area_and_neighbors(delta_page):
    page = delta_page(SHELL)
    page.evaluate("__delta.store.set({tool: 'distance'})")
    page.wait_for_function("Math.abs(document.querySelector('#pane-right').getBoundingClientRect().width - 330) <= 1")
    for i in range(40):
        page.evaluate("(i) => __delta.api.addLayer({}, {}, 'Layer ' + i)", i)
    settle = "() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))"
    page.evaluate(settle)
    # panes are as tall as their content: probe each grip at its own middle
    mid = lambda side: page.evaluate("(s) => { const b = document.querySelector(s).getBoundingClientRect(); return b.top + b.height / 2; }", ".grip[data-side=%s]" % side)
    left_edge = rect(page, "#pane-left")["right"]
    right_edge = rect(page, "#pane-right")["left"]
    for d in (-6, -3, 0, 3, 6):
        assert page.evaluate(HIT, [left_edge + d, mid("left")]) == "grip:left", d
        assert page.evaluate(HIT, [right_edge + d, mid("right")]) == "grip:right", d
    for side, edge in (("left", left_edge), ("right", right_edge)):
        g = rect(page, ".grip[data-side=%s]" % side)
        assert abs(g["width"] - 14) <= 0.5 and abs((g["left"] + g["right"]) / 2 - edge) <= 0.5, (side, g, edge)
        assert page.evaluate("(s) => getComputedStyle(document.querySelector(s)).cursor", ".grip[data-side=%s]" % side) == "col-resize"
    # the layer list scrolls, and its scrollbar is not under the grip
    sc = page.evaluate("() => { const s = document.querySelector('#layers-mount'); const b = s.getBoundingClientRect(); return {over: s.scrollHeight > s.clientHeight, right: b.right, bar: s.offsetWidth - s.clientWidth}; }")
    # (headless Chromium may draw overlay scrollbars, width 0; the bar sits at the box's right edge either way)
    assert sc["over"], sc
    assert sc["right"] <= rect(page, ".grip[data-side=left]")["left"] + 0.5, sc
    # the layer row's controls and the map controls beside the right pane stay clickable
    for sel in ("#layer-list .layer .tgl", "#layer-list .layer .legbtn", "#mapctl [data-act=zoom-in]", "#mapctl .bm.on"):
        page.evaluate("(s) => document.querySelector(s).classList.remove('none')", sel)
        b = page.evaluate("(s) => { const r = document.querySelector(s).getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2, r.right - 1]; }", sel)
        for x in (b[0], b[2]):
            assert page.evaluate("([x, y, s]) => document.querySelector(s).contains(document.elementFromPoint(x, y))", [x, b[1], sel]), (sel, x)


@pytest.mark.parametrize("scheme", ["dark", "light"])
def test_grip_affordance_on_hover_and_drag(delta_page, scheme):
    page = delta_page(SHELL, color_scheme=scheme)
    pill = "(s) => { const c = getComputedStyle(document.querySelector(s), '::before'); return {op: c.opacity, bg: c.backgroundColor, h: parseFloat(c.height), w: parseFloat(c.width)}; }"
    teal = page.evaluate("() => { const d = document.createElement('div'); d.style.color = 'var(--dz-teal)'; document.body.appendChild(d); const c = getComputedStyle(d).color; d.remove(); return c; }")
    g = ".grip[data-side=left]"
    assert page.evaluate(pill, g)["op"] == "0"
    box = page.locator(g).bounding_box()
    page.mouse.move(box["x"] + 7, box["y"] + box["height"] / 2)
    page.wait_for_function("(s) => getComputedStyle(document.querySelector(s), '::before').opacity === '1'", arg=g)
    p = page.evaluate(pill, g)
    assert p["bg"] == teal and p["h"] >= 24 and 2 <= p["w"] <= 6, (p, teal)
    page.mouse.down()
    page.mouse.move(box["x"] - 50, box["y"] + box["height"] / 2, steps=5)
    assert page.evaluate(pill, g)["op"] == "1"  # still shown while dragging, pointer off the grip or not
    page.mouse.up()


def test_real_drag_right_grip_wider_then_narrower(delta_page):
    page = delta_page(SHELL)
    page.evaluate("__delta.store.set({tool: 'distance'})")
    page.wait_for_function("Math.abs(document.querySelector('#pane-right').getBoundingClientRect().width - 330) <= 1")
    y = page.evaluate("() => { const b = document.querySelector('.grip[data-side=right]').getBoundingClientRect(); return b.top + b.height / 2; }")
    for dx, want in ((-250, 580), (250, 330)):
        edge = rect(page, "#pane-right")["left"]
        page.mouse.move(edge, y)
        page.mouse.down()
        page.mouse.move(edge + dx, y, steps=25)
        page.mouse.up()
        frames(page)
        assert abs(width(page, "#pane-right") - want) <= 2, (dx, width(page, "#pane-right"))
        assert page.evaluate("__delta.store.get().panes.right.width") == round(width(page, "#pane-right"))


# ---- status bar and map controls follow the panes' reach ----
# Panes are as tall as their content, so the status bar spans the window and the
# map controls sit at the right edge unless a pane actually comes down to them.

def _reach(page):
    return page.evaluate("""() => {
      const r = (s) => document.querySelector(s).getBoundingClientRect();
      return {status: r('#status'), right: r('#pane-right'), left: r('#pane-left'), ctl: r('#mapctl'),
              vw: innerWidth, vh: innerHeight, bg: getComputedStyle(document.querySelector('#status')).backgroundColor,
              cls: document.body.className};
    }""")


def _settle(page):
    page.wait_for_timeout(350)  # the right pane animates its width for 0.2 s
    page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")


def test_short_panes_leave_status_and_controls_at_the_edges(delta_page):
    page = delta_page(SHELL)
    page.evaluate("__delta.store.set({tool: 'distance'})")
    _settle(page)
    m = _reach(page)
    assert m["right"]["bottom"] < m["vh"] - 100, m["right"]
    assert abs(m["status"]["left"]) <= 1 and abs(m["status"]["right"] - m["vw"]) <= 1, m["status"]
    assert abs(m["ctl"]["right"] - (m["vw"] - 6)) <= 1, m["ctl"]
    # the status bar has its own background so its text reads over any map
    assert m["bg"] not in ("rgba(0, 0, 0, 0)", "transparent"), m["bg"]


GFOOT = 26 + 24  # the status bar, then Google's strip (logo, scale, credits) above it


def test_tall_right_pane_pushes_controls_and_status(delta_page):
    page = delta_page(SHELL)
    page.evaluate("__delta.store.set({tool: 'distance'})")
    page.evaluate("""() => { const d = document.createElement('div'); d.id = 'tall-test'; d.style.height = '3000px';
                             document.querySelector('#results-mount').appendChild(d); }""")
    _settle(page)
    m = _reach(page)
    # a tall right pane comes down to Google's strip (shortcuts, scale, terms), which stays clear
    assert abs(m["right"]["bottom"] - (m["vh"] - 26 - 14)) <= 1, m["right"]
    # the map controls sit 6 px from the right pane
    assert abs(m["ctl"]["right"] - (m["right"]["left"] - 6)) <= 1, (m["ctl"], m["right"])
    assert abs(m["status"]["right"] - m["vw"]) <= 1 and abs(m["status"]["left"]) <= 1, m["status"]
    # the map itself ends at the status bar, so Google's strip sits above it
    mb = page.evaluate("document.querySelector('#map').getBoundingClientRect().bottom")
    assert abs(mb - m["status"]["top"]) <= 1, (mb, m["status"])
    # the basemaps end on the same line, right on top of Google's 14 px strip
    assert abs((mb - m["ctl"]["bottom"]) - 14) <= 1, (mb, m["ctl"])
    assert abs(m["ctl"]["bottom"] - m["right"]["bottom"]) <= 1, (m["ctl"], m["right"])
    # and back when the content goes away
    page.evaluate("document.querySelector('#tall-test').remove()")
    _settle(page)
    m = _reach(page)
    assert abs(m["ctl"]["right"] - (m["vw"] - 6)) <= 1, m["ctl"]
    assert abs(m["status"]["right"] - m["vw"]) <= 1, m["status"]


PHONE = {"width": 390, "height": 844}
SHOWN = "(s) => { const e = document.querySelector(s); return !!e && e.getClientRects().length > 0 && !e.closest('[inert]'); }"


def test_phone_tools_and_output_are_separate_sheets(delta_page):
    page = delta_page(SHELL, viewport=PHONE)
    page.click("#mtabs [data-m=tools]")
    assert page.evaluate(SHOWN, "#pane-right .tools") and page.evaluate(SHOWN, "#pane-right .units")
    assert not page.evaluate(SHOWN, "#results-mount") and not page.evaluate(SHOWN, "#pane-right .out-h")
    page.click("#mtabs [data-m=output]")
    cls = page.evaluate("document.body.className")
    assert "m-output" in cls and "m-tools" not in cls
    assert page.evaluate(SHOWN, "#pane-right .out-h")
    assert not page.evaluate(SHOWN, "#pane-right .tools") and not page.evaluate(SHOWN, "#pane-right .units")
    page.click("#mtabs [data-m=output]")
    assert not page.evaluate("document.querySelector('#pane-right').inert === false")


def test_units_sit_a_little_below_the_tool_tabs(delta_page):
    # desktop gets the gap from the pane body's margin; phones, whose pane body
    # steps aside (display: contents), get the same gap on the units row
    gap = "() => document.querySelector('#pane-right .units').getBoundingClientRect().top - document.querySelector('#pane-right .tools').getBoundingClientRect().bottom"
    page = delta_page(SHELL)
    page.evaluate("__delta.store.set({tool: 'distance'})")
    desk = page.evaluate(gap)
    page = delta_page(SHELL, viewport=PHONE)
    page.click("#mtabs [data-m=tools]")
    phone = page.evaluate(gap)
    assert desk >= 7 and abs(phone - desk) < 1, (desk, phone)


def test_phone_output_dot_and_tools_stay_open_on_pick(delta_page):
    page = delta_page(SHELL, viewport=PHONE)
    dot = "document.querySelector('#mtabs .mdot').hidden"
    assert page.evaluate(dot) is True
    # picking a tool keeps the Tools sheet (and the tool tabs) open
    page.click("#mtabs [data-m=tools]")
    page.click("#pane-right .tool[data-tool=measure]")
    assert "m-tools" in page.evaluate("document.body.className")
    assert page.evaluate(SHOWN, "#pane-right .tools")
    assert page.evaluate("__delta.store.get().tool") == "distance"
    page.click("#mtabs [data-m=tools]")  # the tab bar closes it
    # output arriving with the Output sheet closed shows a dot; opening it clears it
    page.evaluate("__delta.store.set({results: [{id: 'r', title: 'R', kind: 'measure', data: {lines: [['Distance', '1 km']], text: ''}, actions: []}]}, 'measure')")
    assert page.evaluate(dot) is False
    page.click("#mtabs [data-m=output]")
    assert page.evaluate(dot) is True
    # Chart area keeps it open too
    page.evaluate("__delta.store.set({areaFrom: 'upload'})")
    page.click("#mtabs [data-m=tools]")
    page.evaluate("__delta.store.set({layers: [{id: 'c', name: 'C', kind: 'image', visible: true, chartable: true, queryable: true, viz: {}, legend: null}]})")
    page.wait_for_function("!document.querySelector('#pane-right .tool[data-tool=chart]').hidden")
    page.click("#pane-right .tool[data-tool=chart]")
    assert "m-tools" in page.evaluate("document.body.className")


def test_phone_has_street_view(delta_page):
    # zoom and full screen are the phone's own gestures, but Street View has
    # no gesture: its button stays, under the basemap button
    page = delta_page(SHELL, viewport=PHONE)
    page.wait_for_function(SHOWN, arg="#svBtn")
    for sel in ("[data-act=zoom-in]", "[data-act=fullscreen]"):
        assert not page.evaluate(SHOWN, sel), sel
    sv = page.evaluate("() => document.querySelector('#svBtn').getBoundingClientRect().toJSON()")
    bm = page.evaluate("() => document.querySelector('.basemaps').getBoundingClientRect().toJSON()")
    assert sv["width"] >= 36 and sv["height"] >= 36, sv  # a thumb-sized target
    assert abs(sv["right"] - bm["right"]) <= 1 and sv["top"] >= bm["bottom"], (sv, bm)
    # (picking a place on a real map: test_map_engine.py test_street_view_on_a_phone)


def test_phone_tools_tab_shows_the_active_tool(delta_page):
    page = delta_page(SHELL, viewport=PHONE)
    mark = "#mtabs [data-m=tools] .mtool"
    page.wait_for_function(SHOWN, arg="#mtabs [data-m=tools]")
    assert not page.evaluate(SHOWN, mark)
    # Query and Chart area are offered once the map has a layer
    page.evaluate("__delta.api.addLayer({}, {canAreaChart: true}, 'A layer')")
    for tool, icon, name in (("query", "ti-crosshair", "Query"), ("area", "ti-ruler-measure", "Measure"), ("chart", "ti-chart-area-line", "Chart area")):
        page.evaluate("(t) => __delta.store.set({tool: t})", tool)
        page.wait_for_function(SHOWN, arg=mark)
        got = page.evaluate("(s) => [document.querySelector(s + ' i').className, document.querySelector('#mtabs [data-m=tools]').getAttribute('aria-label')]", mark)
        assert icon in got[0], got
        assert got[1] == "Tools: " + name + " is on", got
        # beside the Tools icon, inside the tab
        tab = page.evaluate("() => document.querySelector('#mtabs [data-m=tools]').getBoundingClientRect().toJSON()")
        ic = page.evaluate("() => document.querySelector('#mtabs [data-m=tools] .ti-tools').getBoundingClientRect().toJSON()")
        m = page.evaluate("(s) => document.querySelector(s).getBoundingClientRect().toJSON()", mark)
        assert m["left"] >= ic["right"] - 6 and m["right"] <= tab["right"], (m, ic, tab)
    page.evaluate("__delta.store.set({tool: null})")
    page.wait_for_function("(s) => !document.querySelector(s) || document.querySelector(s).hidden", arg=mark)
    assert page.evaluate("document.querySelector('#mtabs [data-m=tools]').getAttribute('aria-label')") == "Tools"
