"""Report PDFs are the report HTML, printed (2026-11-17).

Reports used to have two renderings: interactive HTML, and a separate PDF
layout with kaleido PNG charts and an extra Earth Engine filmstrip per GIF,
printed by whichever of Chrome's CLI or wkhtmltopdf was found. Now there
is one: geeViz.outputLib.pdf.html_to_pdf prints the HTML with Playwright,
after replacing each GIF with a grid of its frames and adding print CSS
(tables break between rows and repeat their header, figures stay whole,
dark pages stay dark to the edge, page numbers in the footer).
"""
import base64
import io
import re
import warnings
from pathlib import Path

import pytest
from PIL import Image

from geeViz.outputLib import pdf
from geeViz.outputLib import reports as rl

ROOT = Path(__file__).resolve().parents[1]
INSTR = (ROOT / "mcp" / "agent-instructions.md").read_text(encoding="utf-8")


def _gif(n=3, size=(40, 30)):
    colors = [(200, 30, 30), (30, 200, 30), (30, 30, 200), (220, 220, 30)]
    frames = [Image.new("RGB", size, colors[i % 4]) for i in range(n)]
    buf = io.BytesIO()
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:], duration=200, loop=0)
    return buf.getvalue()


def _page(gif_bytes, rows=0, bg="#ffffff"):
    b64 = base64.b64encode(gif_bytes).decode()
    table = ""
    if rows:
        body = "".join(f"<tr><td>{i}</td><td>{i * 1.5:.2f}</td></tr>" for i in range(rows))
        table = f'<div class="table-wrapper"><table><thead><tr><th>RowHeader</th><th>Value</th></tr></thead><tbody>{body}</tbody></table></div>'
    return (f'<!DOCTYPE html><html><head><style>body{{background:{bg}}}</style></head><body>'
            f'<h1>Test</h1><figure class="gif-container"><img src="data:image/gif;base64,{b64}">'
            f'<figcaption>Animated</figcaption></figure>'
            f'<img src="data:image/png;base64,iVBORw0KGgo=" id="still">{table}</body></html>')


def test_a_gif_splits_into_one_png_per_frame_in_order():
    pngs = pdf.gif_frames(_gif(3))
    assert len(pngs) == 3
    firsts = [Image.open(io.BytesIO(p)).convert("RGB").getpixel((5, 5)) for p in pngs]
    assert firsts[0][0] > 150 and firsts[1][1] > 150 and firsts[2][2] > 150


def test_the_gif_becomes_a_grid_of_frame_panes_and_other_images_stay():
    out = pdf.prepare_html_for_pdf(_page(_gif(4)))
    assert "data:image/gif" not in out
    assert out.count('class="pdf-frame"') == 4
    assert "<figcaption>Animated</figcaption>" in out          # caption kept
    assert 'id="still"' in out                                  # PNGs untouched
    assert '<style id="geeviz-print">' in out and out.index("geeviz-print") < out.index("</head>")


def test_one_frame_is_one_column_and_columns_never_exceed_frames():
    assert "pdf-frames-1" in pdf.prepare_html_for_pdf(_page(_gif(1)))
    assert "--pdf-cols:2" in pdf.prepare_html_for_pdf(_page(_gif(2)))
    assert "--pdf-cols:3" in pdf.prepare_html_for_pdf(_page(_gif(9)))
    # A poster is one page: its frames pack eight to a row.
    assert "--pdf-cols:8" in pdf.prepare_html_for_pdf(_page(_gif(9)), layout="poster")


def test_print_css_breaks_tables_between_rows_and_keeps_panes_whole():
    css = re.sub(r"/\*[\s\S]*?\*/", "", pdf.PRINT_CSS)
    assert "thead { display: table-header-group; }" in css
    assert "tr, th, td { break-inside: avoid;" in css
    assert ".pdf-frame" in css.split("break-inside: avoid")[0].rsplit("}", 1)[-1]
    assert "max-height: none !important; overflow: visible !important;" in css
    # A section is allowed to run across pages; the old template forbade it.
    assert ".section { break-inside: auto !important;" in css


def test_the_old_pdf_layout_is_gone():
    src = Path(rl.__file__).read_text(encoding="utf-8")
    code = re.sub(r'"""[\s\S]*?"""', "", src)
    code = re.sub(r"(?m)#.*$", "", code)
    for gone in ("_render_pdf", "static_charts", "thumb_filmstrip_html", "pdfkit",
                 "_fig_to_static_img", "PDF_HTML_TEMPLATE", "generate_filmstrip(\n                        sec.ee_obj, geom,\n                        columns=kw.get(\"thumb_columns\", default_cols)"):
        assert gone not in code, gone
    assert rl.html_to_pdf is pdf.html_to_pdf


# ---------------------------------------------------------------------------
#  Report wiring, with printing stubbed
# ---------------------------------------------------------------------------
@pytest.fixture
def report(monkeypatch):
    r = rl.Report(title="T", theme="dark")
    monkeypatch.setattr(r, "_compute_all_parallel", lambda: None)
    monkeypatch.setattr(r, "_generate_executive_summary", lambda: None)
    monkeypatch.setattr(r, "_render_html", lambda: "<html><head></head><body>R</body></html>")
    calls = []

    def fake(html, output_path=None, **kw):
        calls.append((html, output_path, kw))
        if output_path:
            Path(output_path).write_bytes(b"%PDF-fake")
            return output_path
        return b"%PDF-fake"

    monkeypatch.setattr(rl._pdf, "html_to_pdf", fake)
    r._calls = calls
    return r


def test_generate_with_a_path_writes_the_pdf_beside_the_html(report, tmp_path):
    out = report.generate(format="html", output_path=str(tmp_path / "a.html"))
    assert out == str(tmp_path / "a.html")
    assert report.pdf_path == str(tmp_path / "a.pdf") and (tmp_path / "a.pdf").exists()
    html, path, kw = report._calls[0]
    assert html.startswith("<html>") and kw["layout"] == "report"
    assert "pageNumber" in kw["footer_template"]


def test_pdf_false_and_markdown_write_no_pdf(report, tmp_path):
    report.generate(format="html", output_path=str(tmp_path / "a.html"), pdf=False)
    report.generate(format="md", output_path=str(tmp_path / "a.md"))
    assert report._calls == [] and report.pdf_path is None


def test_to_pdf_prints_the_last_html_and_returns_bytes(report):
    with pytest.raises(RuntimeError, match="generate"):
        report.to_pdf()
    report.generate(format="html")
    assert report.to_pdf() == b"%PDF-fake"
    assert report._calls[-1][0] == "<html><head></head><body>R</body></html>"


def test_a_failed_print_still_leaves_the_html(report, tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no browser")
    monkeypatch.setattr(rl._pdf, "html_to_pdf", boom)
    out = report.generate(format="html", output_path=str(tmp_path / "a.html"))
    assert Path(out).exists() and report.pdf_path is None


def test_format_pdf_is_deprecated_and_writes_both(report, tmp_path):
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        out = report.generate(format="pdf", output_path=str(tmp_path / "b.pdf"))
    assert any(issubclass(x.category, DeprecationWarning) for x in w)
    assert out == str(tmp_path / "b.pdf")
    assert (tmp_path / "b.html").exists() and (tmp_path / "b.pdf").exists()


def test_the_agent_saves_a_pdf_with_every_report():
    assert 'save_file("report.pdf", report.to_pdf(), mode="wb")' in INSTR
    assert 'format="pdf"' not in INSTR.replace('no `format="pdf"`', "")


# ---------------------------------------------------------------------------
#  A real print (needs Chrome, Edge or Chromium)
# ---------------------------------------------------------------------------
def _browser():
    from geeViz.outputLib.charts import _find_browser
    return _find_browser()


@pytest.mark.skipif(not _browser(), reason="no Chrome/Edge/Chromium to print with")
def test_a_real_print_repeats_table_headers_numbers_pages_and_keeps_dark_edges(tmp_path):
    pypdf = pytest.importorskip("pypdf")
    pytest.importorskip("playwright")
    out = pdf.html_to_pdf(_page(_gif(5), rows=160, bg="#202020"), str(tmp_path / "t.pdf"))
    reader = pypdf.PdfReader(out)
    pages = [p.extract_text() for p in reader.pages]
    assert len(pages) >= 3
    # thead repeats on every page the table continues onto
    assert sum("RowHeader" in t for t in pages) >= 2
    assert all(f"Page {i + 1} of {len(pages)}" in t for i, t in enumerate(pages))
    # five frame panes, as five images, none of them the GIF
    n_images = sum(len(p.images) for p in reader.pages)
    assert n_images >= 5
    # the page background was copied into the page margins (@page)
    # (a Letter page is 816 x 1056 CSS px; Chromium fills it first).
    raw = reader.pages[0].get_contents().get_data()
    assert re.search(rb"\.125\d* \.125\d* \.125\d* rg\s+(?:/\w+ gs\s+)?0 0 816 1056 re", raw)


# ---------------------------------------------------------------------------
#  The run_code sandbox: geeViz may print, model-written code may not
#  drive a browser (its requests would bypass the socket audit hook).
# ---------------------------------------------------------------------------
def _sandbox(code):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_sandbox_trust import _run_under_sandbox
    return _run_under_sandbox(code)


def test_model_code_cannot_import_playwright():
    res, out = _sandbox("from playwright.sync_api import sync_playwright")
    assert res.startswith("SANDBOX_RESULT: BLOCKED") and "playwright" in res, out


@pytest.mark.skipif(not _browser(), reason="no Chrome/Edge/Chromium to print with")
def test_report_pdfs_still_print_inside_the_sandbox():
    pytest.importorskip("playwright")
    res, out = _sandbox(
        "from geeViz.outputLib import reports as rl\n"
        "b = rl.html_to_pdf('<html><head></head><body>x</body></html>')\n"
        "assert b[:4] == b'%PDF'\n"
    )
    assert res == "SANDBOX_RESULT: ALLOWED", out
    assert "Playwright unavailable" not in out, out


# ---------------------------------------------------------------------------
#  Nothing is cut at a page break
# ---------------------------------------------------------------------------
def _placements(path):
    """``(page, x0, y0, x1, y1, page_w, page_h)`` in pt for every image or
    form drawn. A pane cut by a page break is drawn twice, each time
    partly outside the printable area, clipped."""
    pypdf = pytest.importorskip("pypdf")
    out = []
    for i, page in enumerate(pypdf.PdfReader(path).pages):
        W, H = float(page.mediabox.width), float(page.mediabox.height)

        def before(op, args, cm, tm, _i=i, _W=W, _H=H):
            if op == b"Do":
                a, b, c, d, e, f = cm
                xs, ys = [e, e + a, e + c, e + a + c], [f, f + b, f + d, f + b + d]
                out.append((_i + 1, min(xs), min(ys), max(xs), max(ys), _W, _H))
        page.extract_text(visitor_operand_before=before)
    return out


def _cut(path, margins=(36, 36, 50.4, 36), tol=1.0, footer_below=60):
    """Placements that leave the Letter report's printable area (top,
    right, bottom, left margins in pt). The footer logo, in the bottom
    margin, is not content."""
    t, r, b, l = margins
    return [p for p in _placements(path) if p[4] > footer_below and (
        p[1] < l - tol or p[3] > p[5] - r + tol or p[2] < b - tol or p[4] > p[6] - t + tol)]


def _forty_year_gif(w=300, h=560):
    from PIL import ImageDraw
    frames = []
    for i in range(40):
        im = Image.new("RGB", (w, h), (20, 60 + i * 4, 40))
        d = ImageDraw.Draw(im)
        d.text((10, 10), str(1985 + i), fill="white")
        d.rectangle((40, 80, w - 40, h - 60), outline="yellow", width=4)
        frames.append(im)
    buf = io.BytesIO()
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:], duration=200, loop=0)
    return buf.getvalue()


@pytest.mark.skipif(not _browser(), reason="no Chrome/Edge/Chromium to print with")
def test_a_forty_year_gif_prints_forty_whole_panes(tmp_path):
    pytest.importorskip("playwright")
    b64 = base64.b64encode(_forty_year_gif()).decode()
    html = (f'<html><head></head><body><h1>t</h1><p>{"words " * 300}</p>'
            f'<figure class="gif-container"><img src="data:image/gif;base64,{b64}"></figure>'
            f'<p>{"after " * 200}</p></body></html>')
    out = pdf.html_to_pdf(html, str(tmp_path / "g.pdf"))
    # Zero-area placements are form groups (the "Continued" label's text
    # on each carried-over page), not images.
    panes = [p for p in _placements(out) if p[4] > 60 and p[3] - p[1] > 1 and p[4] - p[2] > 1]
    assert len(panes) == 40
    assert len({p[0] for p in panes}) >= 2          # it does run across pages
    assert _cut(out) == []


@pytest.mark.skipif(not _browser(), reason="no Chrome/Edge/Chromium to print with")
def test_an_image_taller_than_a_page_is_fitted_not_cut(tmp_path):
    """break-inside: avoid cannot keep a block whole when it is taller than
    the page; the browser then slices it. _BEFORE_PRINT fits it first.
    (Checked: with the fit and max-height removed, this image is drawn
    across pages 2 and 3 and _cut reports both.)"""
    pytest.importorskip("playwright")
    buf = io.BytesIO()
    Image.new("RGB", (500, 1800), (200, 30, 30)).save(buf, format="PNG")
    html = (f'<html><head></head><body><p>{"words " * 300}</p>'
            f'<img src="data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"></body></html>')
    out = pdf.html_to_pdf(html, str(tmp_path / "t.pdf"))
    assert len([p for p in _placements(out) if p[4] > 60]) == 1
    assert _cut(out) == []


def test_the_poster_page_size_is_valid_css():
    """"48in 36in landscape" is invalid (no orientation keyword after
    lengths); Chromium dropped the rule and printed posters on Letter."""
    from geeViz.outputLib import _templates
    src = Path(_templates.__file__).read_text(encoding="utf-8")
    assert "@page { size: 48in 36in; margin: 0.4in; }" in src
    assert "48in 36in landscape" not in src.split("/*")[0]


@pytest.mark.skipif(not _browser(), reason="no Chrome/Edge/Chromium to print with")
def test_a_poster_taller_than_its_page_is_scaled_onto_one_page(tmp_path):
    pypdf = pytest.importorskip("pypdf")
    pytest.importorskip("playwright")
    b64 = base64.b64encode(_forty_year_gif()).decode()
    gif = f'<figure class="gif-container"><img src="data:image/gif;base64,{b64}"></figure>'
    html = ('<html><head><style>@media print { @page { size: 48in 36in; margin: 0.4in; } '
            'html, body { height: 100%; overflow: hidden; } }</style></head><body>'
            + gif * 4 + '<p id="last">END-OF-POSTER</p></body></html>')
    out = pdf.html_to_pdf(html, str(tmp_path / "p.pdf"), layout="poster")
    r = pypdf.PdfReader(out)
    assert len(r.pages) == 1
    assert (float(r.pages[0].mediabox.width), float(r.pages[0].mediabox.height)) == (48 * 72, 36 * 72)
    assert "END-OF-POSTER" in r.pages[0].extract_text()   # the bottom was not clipped
    assert len([p for p in _placements(out) if p[4] > 60]) == 160
    assert _cut(out, margins=(28.8, 28.8, 28.8, 28.8)) == []


# ---------------------------------------------------------------------------
#  2026-11-17: "Continued" tables, section rules, the Sankey's width, and
#  the report model.
# ---------------------------------------------------------------------------
def _sections_page(rows):
    body = "".join(f"<tr><td>r{i}x</td><td>{i * 1.5:.2f}</td></tr>" for i in range(rows))
    table = (f'<div class="table-wrapper"><table><thead><tr><th>RowHeader</th><th>Value</th>'
             f'</tr></thead><tbody>{body}</tbody></table></div>')
    para = "<p>" + " ".join(["Words that fill a paragraph."] * 40) + "</p>"
    return ('<!DOCTYPE html><html><head></head><body><div class="report">'
            '<div class="summary"><h2>Executive Summary</h2>' + para + '</div>'
            '<div class="section"><h2>First section</h2>' + para + table + '</div>'
            '<div class="section"><h2>Second section</h2>' + para + '</div>'
            '</div></body></html>')


@pytest.mark.skipif(not _browser(), reason="no Chrome/Edge/Chromium to print with")
def test_a_table_carried_onto_the_next_page_starts_with_continued(tmp_path):
    """The browser repeats a header row but cannot say a table goes on, so
    the printer splits the table where the page ends and labels the rest."""
    pypdf = pytest.importorskip("pypdf")
    pytest.importorskip("playwright")
    out = pdf.html_to_pdf(_sections_page(150), str(tmp_path / "t.pdf"))
    reader = pypdf.PdfReader(out)
    pages = [p.extract_text() for p in reader.pages]
    with_rows = [i for i, t in enumerate(pages) if re.search(r"\br\d+x\b", t)]
    assert len(with_rows) >= 3, "the table should run over several pages"
    for i in with_rows[1:]:
        t = pages[i]
        assert "Continued" in t, f"page {i + 1} carries the table on without saying so"
        assert t.count("Continued") == 1

    assert "Continued" not in pages[with_rows[0]]
    # Every row printed exactly once: nothing lost or doubled at a split.
    seen = [int(n) for n in re.findall(r"\br(\d+)x\b", "\n".join(pages))]
    assert sorted(seen) == list(range(150))
    # ...and in order from page to page: each part continues the last.
    firsts = [int(re.search(r"\br(\d+)x\b", pages[i]).group(1)) for i in with_rows]
    assert firsts == sorted(firsts)


def test_every_report_section_starts_with_a_rule_but_the_poster_has_none():
    page = ('<html><head></head><body><div class="summary">s</div>'
            '<div class="section">a</div><div class="section">b</div></body></html>')
    rep = pdf.prepare_html_for_pdf(page, layout="report")
    assert rep.count('<hr class="pdf-section-rule"><div class="section">') == 2
    assert "pdf-section-rule" not in pdf.prepare_html_for_pdf(page, layout="poster").split("</style>")[-1]
    css = re.sub(r"/\*[\s\S]*?\*/", "", pdf.PRINT_CSS)
    assert re.search(r"hr\.pdf-section-rule\s*\{[^}]*border-top", css)


def test_the_paginator_runs_for_reports_and_not_for_the_one_page_poster():
    import inspect
    src = inspect.getsource(pdf._print_playwright)
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    i = code.index("page.evaluate(_PAGINATE")
    assert 'if not page_cfg.get("one_page"):' in code[i - 120:i]
    assert code.index("page.evaluate(_BEFORE_PRINT") < i < code.index("page.pdf(")
    assert "label.textContent = 'Continued'" in pdf._PAGINATE


def test_the_d3_sankey_scales_to_its_frame():
    """It drew at a fixed 800px; in a 720px PDF column its last column
    (the final year) was clipped off the right edge."""
    from geeViz.outputLib import _templates as T
    js = re.sub(r"(?m)^\s*//.*$", "", T.D3_SANKEY_TEMPLATE)
    i = js.index("d3.select('#sankey')")
    chain = js[i:js.index(".append('g')", i)]
    assert ".attr('viewBox'" in chain
    assert ".style('width', '100%')" in chain
    assert ".style('height', 'auto')" in chain


def test_reports_write_with_gemini_4_hydrogen():
    from geeViz import llmUsage as lu
    import inspect
    assert lu.REPORT_MODEL == "gemini-4-hydrogen"
    assert inspect.signature(rl.Report.__init__).parameters["model"].default == "gemini-4-hydrogen"
    # Only reports moved: the shared default is unchanged.
    assert lu.DEFAULT_MODEL != lu.REPORT_MODEL


# ---------------------------------------------------------------------------
#  GIF frames carried onto the next page, other themes, and the printing
#  browser's network.
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not _browser(), reason="no Chrome/Edge/Chromium to print with")
def test_gif_frames_carried_onto_the_next_page_start_with_continued(tmp_path):
    pypdf = pytest.importorskip("pypdf")
    pytest.importorskip("playwright")
    out = pdf.html_to_pdf(_page(_forty_year_gif()), str(tmp_path / "g.pdf"))
    reader = pypdf.PdfReader(out)
    with_frames = [i for i, p in enumerate(reader.pages) if len(p.images)]
    assert len(with_frames) >= 2, "forty tall frames should run over several pages"
    for i in with_frames[1:]:
        assert reader.pages[i].extract_text().count("Continued") == 1, f"page {i + 1}"
    assert "Continued" not in reader.pages[with_frames[0]].extract_text()
    assert _cut(out) == []


def test_a_second_generate_in_another_theme_redraws_the_frames(report):
    """``_recompute_thumbs_for_theme`` existed and nothing called it, so a
    report generated again in another theme kept the first theme's GIF
    frames (dark frames in the light example reports)."""
    sec = rl._Section(None, None, "S", None, {}, False, False, "gif")
    sec.thumb_html = "<img>"
    report._sections = [sec]
    calls = []
    report._recompute_thumbs_for_theme = lambda: calls.append(report.theme)
    report._computed_theme = "dark"
    report.generate(format="html", pdf=False)
    assert calls == []                      # same theme: nothing to redraw
    report.theme = "light"
    report.generate(format="html", pdf=False)
    assert calls == ["light"]


def test_dark_custom_themes_restyle_charts_and_the_default_dark_does_not():
    import plotly.graph_objects as go
    from geeViz.outputLib import themes as T
    fig = go.Figure(go.Scatter(x=[1, 2], y=[1, 2]))
    r = rl.Report(title="T", theme="dark")
    assert r._themed_figure(fig) is fig
    for theme in ("teal", "#1b2a49", "light"):
        r.theme = theme
        out = r._themed_figure(fig)
        assert out is not fig
        assert out.layout.paper_bgcolor.lower() == T.get_theme(theme).bg_hex.lower(), theme


def test_the_d3_sankey_takes_the_report_theme():
    from geeViz.outputLib import themes as T
    d = T.get_theme("dark")
    html = (f'body {{ background: {d.bg_hex}; }} .node-label {{ fill: {d.text_hex}; }} '
            f'var cfg = {{"bgColor": "{d.bg_hex.upper()}", "textColor": "{d.text_hex}"}};')
    assert rl._retheme_d3_html(html, d) == html
    for theme in ("teal", "light", "#f4efe1"):
        t = T.get_theme(theme)
        out = rl._retheme_d3_html(html, t)
        assert d.bg_hex.lower() not in out.lower() and d.text_hex.lower() not in out.lower()
        assert out.count(t.bg_hex) == 2 and out.count(t.text_hex) == 2, theme


def test_the_printing_browser_reads_no_local_file_but_the_page():
    page = "file:///C:/tmp/geeviz_pdf_x/page.html"
    assert pdf._request_allowed(page, page)
    for url in ("file:///etc/passwd", "file:///C:/Users/me/.env",
                "http://169.254.169.254/computeMetadata/v1/", "http://metadata.google.internal/",
                "http://127.0.0.1:8080/apps", "http://10.0.0.5/", "https://localhost/",
                "ftp://example.com/x"):
        assert not pdf._request_allowed(url, page), url
    assert pdf._request_allowed("https://cdn.plot.ly/plotly.min.js", page, pdf.REPORT_HOSTS)
    assert pdf._request_allowed("https://example.com/x.js", page)
    assert not pdf._request_allowed("https://example.com/x.js", page, pdf.REPORT_HOSTS)


@pytest.mark.skipif(not _browser(), reason="no Chrome/Edge/Chromium to print with")
def test_a_page_cannot_print_a_local_file_into_its_pdf(tmp_path):
    """A file:// page may read other local files; the guard stops an
    iframe from printing one (a server's secrets) into the PDF."""
    pypdf = pytest.importorskip("pypdf")
    pytest.importorskip("playwright")
    secret = tmp_path / "secret.txt"
    secret.write_text("TOPSECRET-4417", encoding="utf-8")
    src = secret.resolve().as_uri()
    page = (f'<html><head></head><body><p>visible</p>'
            f'<iframe src="{src}" style="width:600px;height:200px"></iframe></body></html>')
    out = pdf.html_to_pdf(page, str(tmp_path / "s.pdf"))
    text = "".join(p.extract_text() for p in pypdf.PdfReader(out).pages)
    assert "visible" in text
    assert "TOPSECRET-4417" not in text


def test_a_guarded_print_never_falls_back_to_the_unguarded_cli(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no browser")
    cli = []
    monkeypatch.setattr(pdf, "_print_playwright", boom)
    monkeypatch.setattr(pdf, "_print_cli", lambda *a, **k: cli.append(1))
    with pytest.raises(RuntimeError, match="Could not print"):
        pdf.html_to_pdf("<html><body>x</body></html>", allowed_hosts=pdf.REPORT_HOSTS)
    assert cli == []
