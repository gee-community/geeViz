"""Delta Chart area and the tool strip (Task 11i): Map view by default, the
empty state's list of chartable layers that are off, Select only with select
layers, Chart area and Query shown only when a layer can use them, and the
Sankey transition period editor (port of setupTransitionPeriodUI).

Offline: the shell stub (no Earth Engine); layers come from the Map API and
the layers' years are set in the store as the charter sets them.
"""
import json

import pytest

SHELL = {"delta-test": "shell"}


def settle(page, ms=30):
    page.evaluate("(ms) => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, ms))))", ms)


def st(page, key):
    return page.evaluate("(k) => __delta.store.get()[k]", key)


def shown_tools(page):
    return page.evaluate("() => Array.from(document.querySelectorAll('#pane-right .tool[data-tool]')).filter(b => !b.hidden && b.getClientRects().length).map(b => b.dataset.tool)")


def sources(page):
    return page.evaluate("() => Array.from(document.querySelectorAll('#tool-options [data-k=src] button')).map(b => b.dataset.v)")


def add(page, js):
    page.evaluate("() => { " + js + " }")
    settle(page)


CHARTABLE = "__delta.api.addLayer({}, {canAreaChart: true}, 'Land cover', true);"


@pytest.fixture
def page(delta_page):
    return delta_page(SHELL)


def show_as(page):
    return page.evaluate("() => document.querySelector('#tool-options [data-k=showas] button.on').dataset.v")


def url_show_as(page):
    return page.evaluate("new URL(location.href).searchParams.get('areaChartFormat')")


def test_show_as_defaults_to_percent_and_remembers_the_users_pick(page):
    add(page, CHARTABLE)
    page.click("#pane-right .tool[data-tool=chart]")
    settle(page)
    assert st(page, "showAs") == "pct" and show_as(page) == "pct"
    assert url_show_as(page) is None  # the default is not written
    page.click("#tool-options [data-k=showas] [data-v=area]")
    settle(page)
    assert url_show_as(page) == "Hectares"
    # the unit it shows follows the Units switch
    page.click("#pane-right .units [data-u=imperial]")
    settle(page)
    assert url_show_as(page) == "Acres"
    # this map, reloaded: the user's pick stays
    page.reload()
    page.wait_for_function("window.__delta !== undefined")
    assert st(page, "showAs") == "area"
    page.evaluate("__delta.store.set({showAs: 'pct'}, 'showAs')")
    settle(page)
    assert url_show_as(page) == "Percentage"


def test_area_from_defaults_to_map_view(page):
    assert st(page, "areaFrom") == "view"
    add(page, CHARTABLE)
    page.click("#pane-right .tool[data-tool=chart]")
    settle(page)
    assert st(page, "tool") == "chart" and st(page, "areaFrom") == "view"
    on = page.evaluate("() => document.querySelector('#tool-options [data-k=src] button.on').dataset.v")
    assert on == "view"
    page.evaluate("__delta.api.turnOnUserDefinedAreaCharting()")
    settle(page)
    assert [st(page, "tool"), st(page, "areaFrom")] == ["chart", "draw"]
    page.evaluate("__delta.api.turnOnAutoAreaCharting()")
    settle(page)
    assert st(page, "areaFrom") == "view"


def test_empty_state_lists_chartable_layers_that_are_off(page):
    add(page, CHARTABLE + "__delta.api.addLayer({}, {canAreaChart: true}, 'Tree canopy', false); __delta.api.addLayer({}, {}, 'Roads', false);")
    page.evaluate("__delta.store.set({tool: 'chart'}, 'test')")
    settle(page)
    page.evaluate("__delta.store.set({where: 'Map view', results: [], charting: false}, 'test')")
    settle(page)
    assert "No visible layer can be charted here" in page.inner_text("#results-mount")
    rows = page.locator("#results-mount [data-role=chartable-off] .layer")
    assert rows.count() == 1 and rows.locator(".lname").inner_text() == "Tree canopy"
    assert rows.locator(".tgl").get_attribute("aria-pressed") == "false"
    rows.locator(".tgl").click()
    settle(page)
    assert page.evaluate("__delta.store.get().layers.find(l => l.name === 'Tree canopy').visible") is True
    # the Layers row follows
    assert "off" not in page.get_attribute("#layer-list .layer:has(.lname:text-is('Tree canopy'))", "class")
    # nothing left to turn on: the list goes
    assert page.locator("#results-mount [data-role=chartable-off]").count() == 0


def test_select_only_with_select_layers(page):
    add(page, CHARTABLE)
    page.evaluate("__delta.store.set({tool: 'chart'}, 'test')")
    settle(page)
    assert sources(page) == ["draw", "view", "upload"]
    add(page, "__delta.api.addSelectLayer({}, {}, 'Fires', false);")
    assert sources(page) == ["draw", "view", "upload", "select"]
    page.click("#tool-options [data-k=src] button[data-v=select]")
    settle(page)
    assert st(page, "areaFrom") == "select"
    # the last select layer goes: back to Map view
    page.evaluate("__delta.store.update(s => ({...s, layers: s.layers.filter(l => l.kind !== 'select'), order: s.order}), 'test')")
    settle(page)
    assert st(page, "areaFrom") == "view"
    assert sources(page) == ["draw", "view", "upload"]


def test_tool_strip_shows_tools_with_layers_to_use(page):
    assert shown_tools(page) == ["measure"]
    add(page, "__delta.api.addLayer({}, {canQuery: false}, 'Basemap', true);")
    assert shown_tools(page) == ["measure"]
    add(page, "__delta.api.addLayer({}, {canQuery: false, canAreaChart: true}, 'Cover', true);")
    assert shown_tools(page) == ["measure", "chart"]
    add(page, "__delta.api.addLayer({}, {}, 'Elevation', true);")
    assert shown_tools(page) == ["measure", "query", "chart"]
    # the active tool's layers go: no tool, the right pane folds
    page.click("#pane-right .tool[data-tool=query]")
    settle(page)
    assert st(page, "tool") == "query"
    page.evaluate("__delta.store.update(s => ({...s, layers: s.layers.filter(l => l.name !== 'Elevation')}), 'test')")
    settle(page)
    assert st(page, "tool") is None and "query" not in shown_tools(page)
    assert "no-tool" in page.evaluate("document.body.className")
    # timelapses and chart-only layers count for Chart area
    page.evaluate("__delta.store.update(s => ({...s, layers: []}), 'test')")
    settle(page)
    assert "chart" not in shown_tools(page)
    add(page, "__delta.api.addTimeLapse({}, {canAreaChart: true}, 'TL');")
    assert "chart" in shown_tools(page)
    page.evaluate("__delta.store.update(s => ({...s, layers: []}), 'test')")
    settle(page)
    add(page, "__delta.api.areaChart.addLayer({}, {}, 'Chart only', true);")
    assert "chart" in shown_tools(page)


def test_script_requests_wait_for_their_layers(page):
    # the generated run script adds layers first, then turns tools on
    page.evaluate("() => { __delta.api.addLayer({}, {canAreaChart: true}, 'Cover', true); __delta.api.turnOnInspector(); }")
    settle(page)
    assert st(page, "tool") == "query"
    page.evaluate("__delta.store.set({tool: null}, 'tool-button')")
    page.evaluate("__delta.store.update(s => ({...s, layers: []}), 'test')")
    settle(page)
    # the other order, across tasks: the request waits for a qualifying layer
    page.evaluate("__delta.api.turnOnAutoAreaCharting()")
    settle(page)
    assert st(page, "tool") is None and "chart" not in shown_tools(page)
    add(page, "__delta.api.addLayer({}, {canQuery: false}, 'Not chartable', true);")
    assert st(page, "tool") is None
    add(page, "__delta.api.addLayer({}, {canAreaChart: true, canQuery: false}, 'Cover', true);")
    assert [st(page, "tool"), st(page, "areaFrom")] == ["chart", "view"]
    # Select asked for before its select layer
    page.evaluate("__delta.store.set({tool: null}, 'tool-button')")
    page.evaluate("__delta.api.turnOnSelectionAreaCharting()")
    settle(page)
    assert [st(page, "tool"), st(page, "areaFrom")] == ["chart", "view"]
    add(page, "__delta.api.addSelectLayer({}, {}, 'Fires', false);")
    assert [st(page, "tool"), st(page, "areaFrom")] == ["chart", "select"]
    # a hidden tool is never shown by the script
    page.evaluate("__delta.store.set({tool: null}, 'tool-button')")
    page.evaluate("__delta.api.turnOnInspector()")
    settle(page)
    assert st(page, "tool") is None and "query" not in shown_tools(page)


# ---- Sankey transition period editor ----

SANKEY = "__delta.api.addLayer({}, {canAreaChart: true, areaChartParams: {sankey: true}}, 'LCMS', true);"


def open_editor(page, years=(2015, 2023)):
    add(page, SANKEY)
    page.evaluate("(y) => { const id = __delta.store.get().layers.find(l => l.name === 'LCMS').id; __delta.store.set({chartYears: {[id]: y}}, 'test'); }", list(years))
    page.evaluate("__delta.store.set({tool: 'chart'}, 'test')")
    settle(page)
    page.click("#tool-options [data-act=chart-settings]")
    settle(page)


def rows(page):
    # a row reads "2015" (one year) or "2015-2016" (a range, the older way)
    return page.evaluate("""() => Array.from(document.querySelectorAll('#tool-options .cset-periods .cset-prow')).map(r =>
      { const t = r.querySelector('input.cset-year').value.trim(); if (t === '') return [null, null];
        const p = t.split('-').map(Number); return [p[0], p[p.length - 1]]; })""")


def errors(page):
    return page.evaluate("() => Array.from(document.querySelectorAll('#tool-options .cset-err')).map(e => e.textContent)")


def click(page, act):
    page.click("#tool-options [data-act=%s]" % act)
    settle(page)


def test_transition_years_only_with_a_sankey_layer(page):
    add(page, CHARTABLE)
    page.evaluate("__delta.store.set({tool: 'chart'}, 'test')")
    settle(page)
    page.click("#tool-options [data-act=chart-settings]")
    settle(page)
    assert page.locator("#tool-options .cset").count() == 1
    assert page.locator("#tool-options [data-role=periods]").count() == 0
    title = page.get_attribute("#tool-options [data-act=chart-settings]", "title")
    assert "Sankey" not in title
    # a Sankey layer arrives: the editor shows in the open panel
    add(page, SANKEY)
    assert page.locator("#tool-options [data-role=periods]").count() == 1
    assert "Sankey" in page.get_attribute("#tool-options [data-act=chart-settings]", "title")


def test_periods_default_to_single_years_at_the_range_ends(page):
    open_editor(page)
    assert rows(page) == [[2015, 2015], [2023, 2023]]
    attrs = page.evaluate("() => { const i = document.querySelector('#tool-options .cset-year'); return [i.type, i.title]; }")
    assert attrs == ["text", "Enter a year (or a range, such as 2015-2017) within the valid range (2015-2023)"]
    assert errors(page) == []


def test_periods_never_default_outside_the_range(page):
    # a stale url value: clipped to the range, periods entirely outside dropped
    page.evaluate("history.replaceState(null, '', location.pathname + '?delta-test=shell&transitionChartingYears=' + encodeURIComponent('[[1990,2016],[2000,2001],[2020,2030]]'))")
    page.reload()
    page.wait_for_function("window.__delta !== undefined")
    open_editor(page)
    # a range from the url shows as that range
    assert rows(page) == [[2015, 2016], [2020, 2023]]
    assert page.input_value("#tool-options .cset-prow[data-i='0'] input.cset-year") == "2015-2016"


def test_a_range_row_applies_as_a_range(page):
    open_editor(page)
    page.fill("#tool-options .cset-prow[data-i='0'] input.cset-year", "2015-2017")
    page.fill("#tool-options .cset-prow[data-i='1'] input.cset-year", "2021-2023")
    settle(page)
    assert errors(page) == []
    click(page, "apply-periods")
    assert st(page, "chartPeriods") == [[2015, 2017], [2021, 2023]]
    # a range the wrong way round is an error, not reordered
    page.fill("#tool-options .cset-prow[data-i='0'] input.cset-year", "2017-2015")
    settle(page)
    assert "One or more rows have a first year that is greater than the last year." in errors(page)


def test_plus_inserts_in_the_middle_minus_and_x_remove(page):
    open_editor(page)
    click(page, "add-period")
    assert rows(page) == [[2015, 2015], [2019, 2019], [2023, 2023]]
    click(page, "add-period")
    assert rows(page) == [[2015, 2015], [2017, 2017], [2019, 2019], [2023, 2023]]
    click(page, "add-period")
    assert rows(page) == [[2015, 2015], [2017, 2017], [2019, 2019], [2021, 2021], [2023, 2023]]
    assert errors(page) == []
    # "-" removes the second to last, keeping the first and last
    click(page, "remove-last-period")
    assert rows(page) == [[2015, 2015], [2017, 2017], [2019, 2019], [2023, 2023]]
    # each row's x removes that row
    page.click("#tool-options .cset-prow[data-i='1'] [data-act=remove-period]")
    settle(page)
    assert rows(page) == [[2015, 2015], [2019, 2019], [2023, 2023]]


def test_keyboard_reorder_and_validation_messages(page):
    open_editor(page)
    click(page, "add-period")
    page.focus("#tool-options .cset-prow[data-i='0'] .cset-grip")
    page.keyboard.press("ArrowDown")
    settle(page)
    assert rows(page) == [[2019, 2019], [2015, 2015], [2023, 2023]]
    assert page.evaluate("document.activeElement.closest('.cset-prow').dataset.i") == "1"
    assert errors(page) == ["Please ensure all transition periods have values, are in succession of one another and do not overlap."]
    assert page.locator("#tool-options [data-act=apply-periods]").is_disabled()
    page.keyboard.press("ArrowUp")
    settle(page)
    assert rows(page) == [[2015, 2015], [2019, 2019], [2023, 2023]] and errors(page) == []

    def set_year(i, v):
        page.fill("#tool-options .cset-prow[data-i='%d'] input.cset-year" % i, v)

    # one input per row
    assert page.locator("#tool-options .cset-prow[data-i='1'] input").count() == 1
    set_year(1, "")
    assert "One or more blank values found." in errors(page)
    set_year(1, "2010")
    assert "Found years outside the available year range. Please ensure all years are >= 2015 and <= 2023." in errors(page)
    set_year(1, "2024")
    assert errors(page), errors(page)
    set_year(1, "2018")
    assert errors(page) == []
    click(page, "remove-last-period")
    click(page, "remove-last-period")
    assert len(rows(page)) == 1
    assert errors(page) == ["No year pairs provided. Please add at least two rows of years."]


def test_apply_charts_once_and_round_trips_the_url(page, delta_page):
    open_editor(page)
    click(page, "add-period")
    changes = page.evaluate("() => { window.__pc = 0; __delta.store.on('change:chartPeriods', () => window.__pc++); return 0; }")
    page.fill("#tool-options .cset-prow[data-i='1'] input.cset-year", "2020")
    assert page.evaluate("window.__pc") == 0  # typing does not chart
    click(page, "apply-periods")
    assert page.evaluate("window.__pc") == 1
    want = [[2015, 2015], [2020, 2020], [2023, 2023]]
    assert st(page, "chartPeriods") == want and st(page, "chartPeriodsUser") is True
    url = page.url
    assert json.loads(page.evaluate("new URL(location.href).searchParams.get('transitionChartingYears')")) == want
    # reload: the rows come back
    page.goto(url)
    page.wait_for_function("window.__delta !== undefined")
    open_editor(page)
    assert rows(page) == want


def test_rows_drag_to_reorder(delta_page, delta_server):
    page = delta_page(SHELL)
    # SortableJS comes from the CDN the shell tests block: let it through here
    ctx = page.context
    ctx.unroute("**/*")
    ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith((delta_server, "https://cdn.jsdelivr.net/npm/sortablejs")) else r.abort())
    page.reload()
    page.wait_for_function("window.__delta !== undefined && !!window.Sortable")
    open_editor(page)
    click(page, "add-period")
    assert rows(page) == [[2015, 2015], [2019, 2019], [2023, 2023]]
    page.locator("#tool-options .cset-prow[data-i='0'] .cset-grip").drag_to(page.locator("#tool-options .cset-prow[data-i='2']"), target_position={"x": 40, "y": 20})
    settle(page, 300)
    got = rows(page)
    assert got != [[2015, 2015], [2019, 2019], [2023, 2023]] and sorted(got) == [[2015, 2015], [2019, 2019], [2023, 2023]], got
    assert any("do not overlap" in e for e in errors(page))


def test_a_long_card_subtitle_never_crushes_the_title(page):
    # a narrow right pane: the subtitle moves under the title instead of
    # squeezing it to a word per line (or splitting a word)
    page.set_viewport_size({"width": 1100, "height": 800})
    add(page, CHARTABLE)
    page.evaluate("__delta.store.set({tool: 'chart'}, 'test')")
    page.evaluate("""__delta.store.set({where: 'Map view', results: [{id: 'r', title: 'LCMS Land Cover transitions',
      meta: '1985-1987 to 2020-2022, 1920 m', kind: 'measure', data: {lines: [['Distance', '1 km']], text: ''}, actions: []}]}, 'test')""")
    settle(page)
    words = page.evaluate("""() => { const b = document.querySelector('#results-mount .card-r .h b');
      const r = document.createRange(); r.selectNodeContents(b);
      const lh = parseFloat(getComputedStyle(b).lineHeight) || 20;
      return [Math.round(b.getBoundingClientRect().height / lh), b.getBoundingClientRect().width]; }""")
    lines, width = words
    assert lines <= 2, words
    assert width > 150, words
