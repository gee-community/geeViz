"""A Sankey chart shows as a chart in a notebook, not as its HTML source.

``summarize_and_chart(chart_type="sankey")["chart"]`` and ``chart_sankey_d3``
return the chart's HTML. ``display(chart)`` (or a cell ending in ``chart``)
must draw it, while it stays a ``str`` for saving and editing.
"""
import pandas

from geeViz.outputLib import charts as cl


def _sankey():
    df = pandas.DataFrame({"source": [0, 1], "target": [2, 3], "value": [60.0, 40.0]})
    return cl.chart_sankey_d3(df, ["Trees", "Grass"], ["005e00", "e6e600"], [1985, 2020], title="Test transitions", width=500, height=300)


def test_sankey_chart_renders_in_a_notebook():
    html = _sankey()
    rich = html._repr_html_()
    # an iframe (Jupyter strips <script> from plain HTML output), sized from the chart
    assert rich.startswith('<iframe src="data:text/html;base64,')
    assert "width:550px;height:380px" in rich
    assert rich == cl.sankey_iframe(str(html))


def test_sankey_chart_is_still_its_html_string():
    html = _sankey()
    assert isinstance(html, str)
    assert html.startswith("<!DOCTYPE html>")
    # str methods keep working and give plain strings back
    assert type(html.replace("Test", "X")) is str
    assert "Test transitions" in html


def _ids(html):
    import re

    return set(re.findall(r'id="([^"]+)"', html)) | set(re.findall(r"'(link-grad-[^']*?)' \+ i", html))


def test_two_sankeys_on_one_page_share_no_element_ids():
    # VS Code shows a notebook's HTML outputs in one page: with shared ids the
    # second chart drew into the first (showing only its title) and the
    # link gradients (the fade) resolved to the wrong chart
    a, b = _sankey(), _sankey()
    ids_a, ids_b = _ids(a), _ids(b)
    assert {"title", "sankey", "tooltip"}.isdisjoint(ids_a)
    assert ids_a and ids_a.isdisjoint(ids_b)
    import re

    # every id a script or style looks up is one the chart defines
    sel = set(re.findall(r"(?:getElementById\('|d3\.select\('#)([^']+)'", a))
    css = set(re.findall(r"\n  #([\w-]+)", a))
    defined = set(re.findall(r'id="([^"]+)"', a))
    assert sel and sel <= defined, sel - defined
    assert css and css <= defined, css - defined
    grad = re.findall(r"(link-grad-[\w-]*?)' \+ i", a)
    assert len(set(grad)) == 1 and len(grad) >= 2, grad  # the gradient ids and their url() match
