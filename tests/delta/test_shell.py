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
    x, y = box["x"] + box["width"] / 2, box["y"] + 200
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
    page.click("#hamburger-float")
    assert page.evaluate("__delta.store.get().panes.left.visible") is True
    assert "showSidebar=false" not in page.url
    page.wait_for_function("document.querySelector('#pane-left').getBoundingClientRect().right > 499")


def test_right_pane_folds_without_tool(delta_page):
    page = delta_page(SHELL)
    page.evaluate("__delta.store.set({tool: 'query'})")
    page.wait_for_function("Math.abs(document.querySelector('#pane-right').getBoundingClientRect().width - 330) <= 1")
    page.evaluate("__delta.store.set({tool: null})")
    page.wait_for_function("Math.abs(document.querySelector('#pane-right').getBoundingClientRect().width - 64) <= 1")
    assert abs(width(page, "#pane-right") - 64) <= 1


def test_tool_buttons_drive_the_store(delta_page):
    page = delta_page(SHELL)
    page.click("#pane-right .tool[data-tool=area]")
    assert page.evaluate("__delta.store.get().tool") == "area"
    page.click("#pane-right .tool[data-tool=area]")
    assert page.evaluate("__delta.store.get().tool") is None


def test_streetview_hides_everything(delta_page):
    page = delta_page(SHELL)
    page.evaluate("__delta.store.set({tool: 'query'})")
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
    assert buttons.count() == 2
    assert [t.strip() for t in buttons.all_inner_texts()] == ["Layers", "Tools"]
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
    page.goto(delta_server + "/delta.html?delta-test=shell")
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
