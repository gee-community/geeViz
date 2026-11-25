"""Result cards in the Output pane. Offline: the shell stub, results set
directly in the store.
"""
SHELL = {"delta-test": "shell"}

EMPTY = {"id": "e-t0", "layerId": "e", "title": "Empty layer", "meta": "No features here", "kind": "table",
         "data": {"rows": []}, "actions": ["copy", "csv"]}
NODATA = {"id": "n-v", "layerId": "n", "title": "No data layer", "meta": "No data", "kind": "value",
          "data": {"bands": []}, "actions": ["copy"]}
FULL = {"id": "f-t0", "layerId": "f", "title": "Full layer", "meta": "Attribute table", "kind": "table",
        "data": {"rows": [["name", "Horsetooth"]]}, "actions": ["copy", "csv"]}


def _cards(page):
    return page.evaluate("""() => [...document.querySelectorAll('#results-mount .card-r')].map(c => {
      const h = c.querySelector('.h'), b = c.querySelector('.b');
      return {rid: c.dataset.rid, empty: c.classList.contains('empty'), role: h.getAttribute('role'),
              expanded: h.getAttribute('aria-expanded'), chevron: !!c.querySelector('.h .ti-chevron-down'),
              body: !!b && b.getClientRects().length > 0, text: h.innerText};
    })""")


def test_a_result_with_nothing_shows_only_its_heading(delta_page):
    page = delta_page(SHELL)
    page.evaluate("__delta.api.addLayer({}, {}, 'A layer')")
    page.evaluate("__delta.store.set({tool: 'query'})")
    page.evaluate("(rs) => __delta.store.set({where: 'here', results: rs})", [EMPTY, NODATA, FULL])
    empty, nodata, full = _cards(page)
    for c in (empty, nodata):
        # as though collapsed, with no way to expand it
        assert c["empty"] and not c["body"] and not c["chevron"], c
        assert c["role"] is None and c["expanded"] is None, c
    assert "No features here" in empty["text"] and "No data" in nodata["text"]
    assert full["body"] and full["chevron"] and full["role"] == "button" and not full["empty"], full
    # a click on the heading does nothing
    page.click('#results-mount .card-r[data-rid="e-t0"] .h')
    assert _cards(page)[0] == empty


def test_no_jump_buttons_above_the_results(delta_page):
    page = delta_page(SHELL)
    page.evaluate("(rs) => __delta.store.set({where: 'here', results: rs})", [EMPTY, NODATA, FULL])
    assert page.evaluate("document.querySelectorAll('#chips .chip').length") == 0
    shown = page.evaluate("(() => { const e = document.querySelector('#chips'); return !!e && e.getClientRects().length > 0 && e.getBoundingClientRect().height > 0; })()")
    assert not shown
