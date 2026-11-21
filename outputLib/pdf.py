"""
Print an HTML page to PDF.

geeViz builds one HTML page per report and prints it; there is no
separate PDF layout to keep in step with the HTML. :func:`html_to_pdf`
takes that page, adapts it for paper, and prints it with headless
Chromium through Playwright:

* **Charts** stay vector. Plotly runs in the page as it does on screen,
  so a chart in the PDF is the chart in the HTML, not a PNG of it.
* **Tables** break between rows, never through one. The part on the
  next page starts with a "Continued" label and the header row again.
  Scroll boxes are opened up so the whole table prints.
* **Animated GIFs** become a grid of their frames, one pane per frame.
  A pane is never split across a page break, and frames carried onto
  the next page start with a "Continued" label, as tables do.
* **Headings** stay with what follows them, and figures are not split.
* Each report section starts with a horizontal rule.
* Every page gets a footer with the page number, and a dark page is
  dark to the paper's edge.
* A table too wide for the page shrinks its text to fit.

Why Chromium: it runs the page's JavaScript, which a report needs for
its Plotly charts. WeasyPrint has the better CSS paged-media support
but runs no JavaScript at all, and wkhtmltopdf is unmaintained. Playwright
drives the browser installed on the machine (Chrome, Edge or Chromium),
so nothing extra is downloaded; ``playwright install chromium`` is only
needed where no browser is installed. Without Playwright the browser's
own ``--print-to-pdf`` is used, which prints the same page but without
page numbers and with a fixed wait for the charts.

Example::

    from geeViz.outputLib import reports as rl

    html = report.generate(format="html")
    rl.html_to_pdf(html, "report.pdf")
"""

"""
   Copyright 2026 Ian Housman

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
"""

import base64
import io
import os
import re
import shutil
import subprocess
import tempfile
import threading

# Hosts a geeViz report loads from: Plotly, D3 and d3-sankey, Google
# Fonts. A server printing HTML it did not write passes these as
# ``allowed_hosts`` so the page can reach nothing else.
REPORT_HOSTS = (
    "cdn.plot.ly", "unpkg.com", "cdn.jsdelivr.net", "cdnjs.cloudflare.com",
    "fonts.googleapis.com", "fonts.gstatic.com",
)

# Letter, 0.5in margins, a little more at the bottom for the footer.
# The viewport is the printable width in CSS pixels (96 per inch), so a
# chart that sizes itself to its container on screen has the width it
# will have on paper: Plotly does not re-lay out when the page prints.
_PAGE = {
    "report": {
        "css": "@page { size: letter portrait; margin: 0.5in 0.5in 0.7in 0.5in; }",
        "viewport": (int(7.5 * 96), int(9.8 * 96)),
        "page_height_px": int(9.8 * 96),
        "gif_columns": 3,
    },
    # The poster template sets its own 48 x 36 in page.
    "poster": {
        "css": "",
        "viewport": (int(47.2 * 96), int(35.2 * 96)),
        "page_height_px": int(35.2 * 96),
        # A poster is one page, and a GIF's frames make its column far
        # taller than the one animated image did: pack them densely.
        "gif_columns": 8,
        "one_page": True,
    },
}

_GIF_IMG = re.compile(
    r'<img\b[^>]*?\bsrc="data:image/gif;base64,([A-Za-z0-9+/=\s]+)"[^>]*>',
    re.IGNORECASE,
)

PRINT_CSS = """
html, body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
/* Scroll boxes print only what is scrolled into view: open them up. */
.table-wrapper, .table-scroll, .chart, .section, .poster-grid > * {
  max-height: none !important; overflow: visible !important;
}
/* A section may run across pages; its parts may not. */
.section { break-inside: auto !important; page-break-inside: auto !important; }
h1, h2, h3, h4, .matrix-title, .table-units, figcaption {
  break-after: avoid; page-break-after: avoid;
}
.chart, .thumb, figure, .js-plotly-plot, iframe, svg, img, .pdf-frame, .summary h3 {
  break-inside: avoid; page-break-inside: avoid;
}
img { max-width: 100%; max-height: 9.3in; object-fit: contain; }
/* Tables: break between rows, repeat the header on each page. */
table { break-inside: auto; page-break-inside: auto; }
thead { display: table-header-group; }
tfoot { display: table-footer-group; }
tr, th, td { break-inside: avoid; page-break-inside: avoid; }
/* Headers may wrap between words; numbers never wrap. */
th { overflow-wrap: break-word; }
td { overflow-wrap: normal; word-break: normal; white-space: nowrap; }
/* Screen-only chrome. */
.modebar, .modebar-container, .report-footer { display: none !important; }
/* An animated GIF, one pane per frame. */
.pdf-frames { display: grid; grid-template-columns: repeat(var(--pdf-cols, 3), minmax(0, 1fr));
  gap: 6px; margin: 8px 0; }
.pdf-frames.pdf-frames-1 { grid-template-columns: minmax(0, 1fr); }
.pdf-frame { margin: 0; }
.pdf-frame img { width: 100%; height: auto; display: block; border-radius: 4px; }
/* Lines break where the paginator measured them: no orphan/widow moves. */
p, li, blockquote { orphans: 1; widows: 1; }
/* A rule between report sections, in the page's own text color. */
hr.pdf-section-rule { border: 0; border-top: 1px solid currentColor; opacity: 0.35;
  margin: 22px 0 18px; break-after: avoid; page-break-after: avoid; }
/* Above the part of a table carried onto the next page. */
.pdf-continued { font-size: 11px; font-style: italic; opacity: 0.75; margin: 0 0 4px; }
"""


# ---------------------------------------------------------------------------
#  GIFs -> frame panes
# ---------------------------------------------------------------------------
def gif_frames(gif_bytes):
    """Split an animated GIF into one PNG per frame.

    Args:
        gif_bytes (bytes): The GIF file.

    Returns:
        list[bytes]: PNG bytes, one per frame, in order. A still GIF gives
        one frame.
    """
    from PIL import Image, ImageSequence

    im = Image.open(io.BytesIO(gif_bytes))
    out = []
    for frame in ImageSequence.Iterator(im):
        # Pillow composites each frame onto the ones before it, so this is
        # the frame as it is shown, not just the pixels it changed. A GIF
        # has at most 256 colors per frame: a palette PNG keeps them all
        # at a fraction of the size of an RGB one.
        rgb = frame.convert("RGB")
        buf = io.BytesIO()
        rgb.quantize(colors=256).save(buf, format="PNG", optimize=True)
        out.append(buf.getvalue())
    return out


def _frames_html(pngs, columns):
    cols = 1 if len(pngs) == 1 else min(columns, len(pngs))
    cells = "".join(
        f'<figure class="pdf-frame"><img alt="Frame {i + 1} of {len(pngs)}" '
        f'src="data:image/png;base64,{base64.b64encode(p).decode()}"></figure>'
        for i, p in enumerate(pngs)
    )
    return f'<div class="pdf-frames pdf-frames-{cols}" style="--pdf-cols:{cols}">{cells}</div>'


def prepare_html_for_pdf(html, layout="report", gif_columns=None):
    """Adapt an HTML page for printing.

    Replaces each embedded animated GIF (``data:image/gif;base64``) with a
    grid of its frames and adds the print stylesheet (:data:`PRINT_CSS`
    plus the page size). Everything else is left as it is.

    Args:
        html (str): The page.
        layout (str): ``"report"`` (Letter portrait) or ``"poster"``.
        gif_columns (int, optional): Frames per row. Defaults to 3 for a
            report and 4 for a poster.

    Returns:
        str: The page, ready to print.
    """
    page = _PAGE.get(layout, _PAGE["report"])
    cols = gif_columns or page["gif_columns"]

    def _swap(m):
        try:
            pngs = gif_frames(base64.b64decode(m.group(1)))
        except Exception as e:  # an image PIL cannot read prints as is
            print(f"  PDF: could not split a GIF into frames ({type(e).__name__}: {e}); "
                  f"printing its first frame", flush=True)
            return m.group(0)
        return _frames_html(pngs, cols)

    html = _GIF_IMG.sub(_swap, html)
    if not page.get("one_page"):
        # A rule before every section; the first section follows the
        # summary, so it gets one too. The poster lays its sections out
        # in a grid, where a rule between them would be a stray line.
        html = re.sub(r'(<div class="section"[\s>])',
                      lambda m: '<hr class="pdf-section-rule">' + m.group(1), html)
    style = f'<style id="geeviz-print">{page["css"]}\n{PRINT_CSS}</style>'
    if re.search(r"</head>", html, re.IGNORECASE):
        return re.sub(r"</head>", lambda _m: style + "</head>", html, count=1, flags=re.IGNORECASE)
    return style + html


# ---------------------------------------------------------------------------
#  Footer
# ---------------------------------------------------------------------------
def page_footer(content_html="", color="#777777", bg=None):
    """Build a Chromium page-footer template with page numbers.

    Args:
        content_html (str): What goes on the left of every footer. Images
            must be ``data:`` URIs; the footer cannot load anything.
        color (str): Text color.
        bg (str, optional): Footer background, for dark pages.

    Returns:
        str: The template for ``footer_template=`` in :func:`html_to_pdf`.
    """
    bg_css = f"background:{bg};" if bg else ""
    return (
        f'<div style="width:100%;font-size:8px;font-family:Arial,sans-serif;color:{color};'
        f'{bg_css}-webkit-print-color-adjust:exact;padding:4px 0.5in 0 0.5in;'
        f'display:flex;align-items:center;gap:6px;">'
        f'<div style="display:flex;align-items:center;gap:6px;">{content_html}</div>'
        f'<div style="margin-left:auto;white-space:nowrap;">Page <span class="pageNumber"></span>'
        f' of <span class="totalPages"></span></div></div>'
    )


# ---------------------------------------------------------------------------
#  Printing
# ---------------------------------------------------------------------------
def _find_browser():
    from geeViz.outputLib.charts import _find_browser as _fb
    return _fb()


# Wait until every Plotly chart has drawn (and Plotly itself, if the page
# uses it, has loaded), then size each chart to its printed width.
_CHARTS_DRAWN = """() => {
  const divs = [...document.querySelectorAll('.plotly-graph-div')];
  if (!divs.length) return true;
  if (!window.Plotly) return false;
  return divs.every(d => d.querySelector('.main-svg'));
}"""
_RESIZE_CHARTS = """async () => {
  if (!window.Plotly) return;
  for (const d of document.querySelectorAll('.plotly-graph-div')) {
    try { await window.Plotly.Plots.resize(d); } catch (e) {}
  }
}"""

# Last touches that need the laid-out page:
# * The page margins take the page's own background, so a dark report
#   is dark to the paper's edge instead of framed in white.
# * Charts drawn in iframes (the D3 Sankey) lose their on-screen buttons.
# * A table wider than the page shrinks its text until it fits, down to
#   6px, rather than being cut off at the margin.
# * Nothing that must not split is taller than a page: a chart, iframe or
#   image taller than the printable height is resized to it. Otherwise
#   ``break-inside: avoid`` cannot be honored and the browser cuts it.
_BEFORE_PRINT = """async ([pageH, onePage]) => {
  const bg = getComputedStyle(document.body).backgroundColor;
  const htmlBg = getComputedStyle(document.documentElement).backgroundColor;
  const paper = (bg && bg !== 'rgba(0, 0, 0, 0)') ? bg : htmlBg;
  if (paper && paper !== 'rgba(0, 0, 0, 0)') {
    const st = document.createElement('style');
    st.textContent = '@page { background: ' + paper + '; }';
    document.head.appendChild(st);
  }
  for (const f of document.querySelectorAll('iframe')) {
    try {
      const d = f.contentDocument;
      if (!d) continue;
      const st = d.createElement('style');
      st.textContent = 'button, #btn-png, .modebar, .modebar-container { display: none !important; }';
      (d.head || d.documentElement).appendChild(st);
    } catch (e) {}
  }
  for (const t of document.querySelectorAll('table')) {
    const box = t.parentElement;
    if (!box) continue;
    let px = parseFloat(getComputedStyle(t).fontSize) || 11;
    while (t.scrollWidth > box.clientWidth + 1 && px > 6) {
      px -= 0.5;
      t.style.fontSize = px + 'px';
      for (const c of t.querySelectorAll('th, td')) {
        c.style.fontSize = px + 'px';
        c.style.padding = '2px 3px';
      }
    }
  }
  const room = pageH - 24;
  for (const d of document.querySelectorAll('.plotly-graph-div')) {
    if (d.offsetHeight > room && window.Plotly) {
      try { await window.Plotly.relayout(d, {height: room}); } catch (e) {}
    }
  }
  for (const f of document.querySelectorAll('iframe')) {
    if (f.offsetHeight > room) f.style.height = room + 'px';
  }
  for (const im of document.querySelectorAll('img')) {
    if (im.offsetHeight > room) { im.style.maxHeight = room + 'px'; im.style.width = 'auto'; }
  }
  // A one-page layout (the poster) that came out taller than its page
  // is scaled down to fit rather than clipped at the bottom edge.
  if (onePage) {
    for (const el of [document.documentElement, document.body]) {
      el.style.height = 'auto'; el.style.overflow = 'visible';
    }
    const h = document.body.scrollHeight;
    if (h > pageH) document.body.style.zoom = String(Math.floor(pageH / h * 1000) / 1000);
  }
}"""


# Place every page break before printing, so that the browser never has
# to choose one. That is what lets a table carried onto the next page
# start with a "Continued" label: the browser can repeat a header row,
# but it cannot say a table is continued, and it does not say where it
# broke one. So the page is walked top to bottom in its print layout
# (the viewport is the printable width, and the page height is known):
#
# * a table that crosses the page bottom is split at the first row that
#   does not fit; the rest becomes a second table, with the header row
#   cloned and the same column widths, under a "Continued" label that
#   starts the next page;
# * a grid of GIF frame panes is split the same way, by row, under the
#   same label;
# * a chart, image, iframe, row or heading that does not fit moves whole
#   to the next page, and the headings and section rule just above it go
#   with it, so no page ends on a heading;
# * a paragraph breaks between lines, at the line that does not fit;
# * any other box is walked into.
#
# Each page then holds at most a page of content, so the browser's own
# fragmentation never kicks in and its breaks are exactly these.
_PAGINATE = """(pageH) => {
  const PH = pageH - 6;                     // room for rounding
  const Y = () => window.scrollY;
  const top = el => el.getBoundingClientRect().top + Y();
  const bot = el => el.getBoundingClientRect().bottom + Y();
  const ATOMIC = '.chart, .thumb, figure, .js-plotly-plot, .plotly-graph-div, iframe, svg, img, '
    + 'canvas, video, tr, h1, h2, h3, h4, h5, h6, hr, .matrix-title, .table-units, '
    + '.pdf-frame, .pdf-continued, pre, .report-header';
  const KEEP_WITH_NEXT = 'h1, h2, h3, h4, h5, h6, hr.pdf-section-rule, .matrix-title, '
    + '.table-units, .pdf-continued';
  const TEXT = 'p, li, blockquote, dd, dt, figcaption';
  let pageTop = 0;
  const flow = [];                          // items placed so far, in order

  const skip = el => {
    if (['SCRIPT', 'STYLE', 'TEMPLATE', 'NOSCRIPT'].includes(el.tagName)) return true;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.position === 'absolute' || cs.position === 'fixed') return true;
    return el.getClientRects().length === 0;
  };
  const mt = el => parseFloat(getComputedStyle(el).marginTop) || 0;

  // Start a page at el, or at the run of headings just above it.
  function breakBefore(el) {
    let target = el;
    for (let k = flow.length - 1; k >= 0; k--) {
      const it = flow[k];
      if (it.contains(el)) continue;
      if (!it.matches(KEEP_WITH_NEXT) || top(it) - mt(it) <= pageTop + 1) break;
      target = it;
    }
    if (top(target) - mt(target) <= pageTop + 1) {
      target = el;                          // el already starts the page
      if (top(target) - mt(target) <= pageTop + 1) return;
    }
    target.style.breakBefore = 'page';
    target.style.pageBreakBefore = 'always';
    pageTop = top(target) - mt(target);
  }
  // An item taller than a page is sliced by the browser.
  function advancePast(el, extra) {
    while (bot(el) + extra > pageTop + PH + 0.5) pageTop += PH;
  }

  function splitTable(t, extra) {
    for (let guard = 0; guard < 500; guard++) {
      const rows = [...t.tBodies].flatMap(b => [...b.rows]);
      if (!rows.length) { flow.push(t); return; }
      const last = rows[rows.length - 1];
      const tail = Math.max(0, bot(t) - bot(last)) + extra;
      const limit = pageTop + PH;
      const i = rows.findIndex((r, k) => bot(r) + (k === rows.length - 1 ? tail : 0) > limit + 0.5);
      if (i < 0) { flow.push(t); return; }
      if (i === 0) {
        // Not even one row fits: the table starts the next page.
        const before = pageTop;
        breakBefore(t);
        if (pageTop !== before) continue;
        advancePast(rows[0], 0);            // one row taller than a page
        flow.push(t);
        return;
      }
      // Fix column widths so both parts line up.
      const ref = (t.tHead && t.tHead.rows.length) ? t.tHead.rows[t.tHead.rows.length - 1] : rows[0];
      const widths = [...ref.cells].map(c => c.getBoundingClientRect().width);
      const tableW = t.getBoundingClientRect().width;
      const rest = t.cloneNode(false);
      rest.removeAttribute('id');
      for (const cg of t.querySelectorAll(':scope > colgroup')) rest.appendChild(cg.cloneNode(true));
      if (t.tHead) rest.appendChild(t.tHead.cloneNode(true));
      const tb = document.createElement('tbody');
      for (const r of rows.slice(i)) tb.appendChild(r);
      rest.appendChild(tb);
      if (t.tFoot) rest.appendChild(t.tFoot);
      for (const b of [...t.tBodies]) if (!b.rows.length) b.remove();
      for (const tbl of [t, rest]) {
        tbl.style.width = tableW + 'px';
        const h = (tbl.tHead && tbl.tHead.rows.length) ? tbl.tHead.rows[tbl.tHead.rows.length - 1] : null;
        if (h) [...h.cells].forEach((c, k) => { if (widths[k]) c.style.width = widths[k] + 'px'; });
      }
      const label = document.createElement('div');
      label.className = 'pdf-continued';
      label.textContent = 'Continued';
      t.after(label, rest);
      flow.push(t);
      label.style.breakBefore = 'page';
      label.style.pageBreakBefore = 'always';
      pageTop = top(label) - mt(label);
      flow.push(label);
      t = rest;
    }
  }

  function splitGrid(g, extra) {
    for (let guard = 0; guard < 500; guard++) {
      const cells = [...g.children].filter(c => !skip(c));
      if (!cells.length) return;
      const limit = pageTop + PH;
      const tail = Math.max(0, bot(g) - Math.max(...cells.map(bot))) + extra;
      const lastTop = top(cells[cells.length - 1]);
      const bad = cells.find(c => bot(c) + (top(c) >= lastTop - 1 ? tail : 0) > limit + 0.5);
      if (!bad) { flow.push(g); return; }
      const rowTop = top(bad);
      const first = cells.findIndex(c => Math.abs(top(c) - rowTop) < 2);
      if (first <= 0) {
        const before = pageTop;
        breakBefore(g);
        if (pageTop !== before) continue;
        advancePast(cells[0], 0);
        flow.push(g);
        return;
      }
      const rest = g.cloneNode(false);
      for (const c of cells.slice(first)) rest.appendChild(c);
      const label = document.createElement('div');
      label.className = 'pdf-continued';
      label.textContent = 'Continued';
      g.after(label, rest);
      flow.push(g);
      label.style.breakBefore = 'page';
      label.style.pageBreakBefore = 'always';
      pageTop = top(label) - mt(label);
      flow.push(label);
      g = rest;
    }
  }

  function splitText(el, extra) {
    const range = document.createRange();
    range.selectNodeContents(el);
    const lines = [...range.getClientRects()].filter(r => r.height > 0);
    if (!lines.length) { breakBefore(el); advancePast(el, extra); flow.push(el); return; }
    const limit = pageTop + PH;
    const tail = Math.max(0, bot(el) - Math.max(...lines.map(r => r.bottom + Y()))) + extra;
    const lastTop = Math.max(...lines.map(r => r.top + Y()));
    const over = lines.filter(r => r.bottom + Y() + (r.top + Y() >= lastTop - 1 ? tail : 0) > limit + 0.5);
    if (!over.length) { flow.push(el); return; }
    const nextTop = Math.min(...over.map(r => r.top + Y()));
    const firstTop = Math.min(...lines.map(r => r.top + Y()));
    if (nextTop <= firstTop + 1) { breakBefore(el); advancePast(el, extra); flow.push(el); return; }
    pageTop = nextTop;                      // the browser breaks between these lines
    advancePast(el, extra);
    flow.push(el);
  }

  function walk(el, extra) {
    if (skip(el)) return;
    if (bot(el) + extra <= pageTop + PH + 0.5) { flow.push(el); return; }
    if (el.tagName === 'TABLE') return splitTable(el, extra);
    if (el.classList.contains('pdf-frames')) return splitGrid(el, extra);
    // A figure or thumb holding a GIF's frame grid is walked into, so the
    // grid splits by row under a "Continued" label; whole, the browser
    // would slice it at whatever row the page ended on.
    if (el.matches(ATOMIC) && !el.querySelector('.pdf-frames')) {
      breakBefore(el); advancePast(el, extra); flow.push(el); return;
    }
    const kids = [...el.children].filter(c => !skip(c));
    const loose = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (el.matches(TEXT) || loose || !kids.length) return splitText(el, extra);
    kids.forEach((c, k) => {
      const more = k === kids.length - 1 ? Math.max(0, bot(el) - bot(c)) + extra : 0;
      walk(c, more);
    });
  }

  for (const c of [...document.body.children]) walk(c, 0);
  return document.querySelectorAll('.pdf-continued').length;
}"""


def _request_allowed(url, page_url, allowed_hosts=None):
    """Whether the printing browser may load ``url``.

    The page is a local file, and a ``file://`` page may read any other
    local file: an ``<iframe src="file:///etc/passwd">`` would print that
    file into the PDF. So the only file it may load is itself. Loopback,
    private and link-local addresses (the cloud metadata server among
    them) are refused too, since a page printed on a server runs inside
    that server's network. ``allowed_hosts``, when given, narrows the
    rest to those hosts.
    """
    import ipaddress
    from urllib.parse import urlsplit

    u = urlsplit(url)
    scheme = u.scheme.lower()
    if scheme in ("data", "blob", "about"):
        return True
    if scheme == "file":
        return url.split("#", 1)[0] == page_url
    if scheme not in ("http", "https"):
        return False
    host = (u.hostname or "").lower().rstrip(".")
    if not host or host == "localhost" or host.endswith((".localhost", ".internal")) \
            or host == "metadata" or host == "metadata.google.internal":
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and (ip.is_private or ip.is_loopback or ip.is_link_local
                           or ip.is_reserved or ip.is_unspecified or ip.is_multicast):
        return False
    if allowed_hosts is not None:
        return host in {h.lower() for h in allowed_hosts}
    return True


def _print_playwright(html_path, pdf_path, layout, footer, timeout_s, allowed_hosts=None):
    from playwright.sync_api import sync_playwright

    page_cfg = _PAGE.get(layout, _PAGE["report"])
    w, h = page_cfg["viewport"]
    exe = _find_browser()
    page_url = "file:///" + os.path.abspath(html_path).replace(os.sep, "/")
    with sync_playwright() as p:
        browser = p.chromium.launch(**({"executable_path": exe} if exe else {}))
        try:
            page = browser.new_page(viewport={"width": w, "height": h})

            def _guard(route):
                if _request_allowed(route.request.url, page_url, allowed_hosts):
                    route.continue_()
                else:
                    route.abort("blockedbyclient")

            page.route("**/*", _guard)
            page.goto(page_url, wait_until="networkidle", timeout=timeout_s * 1000)
            page.emulate_media(media="print")
            try:
                page.wait_for_function(_CHARTS_DRAWN, timeout=timeout_s * 1000)
            except Exception:
                print("  PDF: some charts had not drawn when the page printed", flush=True)
            page.evaluate(_RESIZE_CHARTS)
            page.evaluate(_BEFORE_PRINT, [page_cfg["page_height_px"], bool(page_cfg.get("one_page"))])
            page.wait_for_timeout(300)
            if not page_cfg.get("one_page"):
                page.evaluate(_PAGINATE, page_cfg["page_height_px"])
            page.pdf(
                path=pdf_path,
                print_background=True,
                prefer_css_page_size=True,
                format="Letter",
                display_header_footer=bool(footer),
                header_template="<span></span>",
                footer_template=footer or "<span></span>",
            )
        finally:
            browser.close()


def _print_cli(html_path, pdf_path, timeout_s):
    exe = _find_browser()
    if not exe:
        raise RuntimeError(
            "No browser to print the PDF with. Install Chrome, Edge or Chromium, "
            "or `pip install playwright` and `playwright install chromium`."
        )
    cmd = [
        exe, "--headless", "--disable-gpu", "--no-pdf-header-footer",
        "--run-all-compositor-stages-before-draw", "--virtual-time-budget=15000",
        f"--print-to-pdf={os.path.abspath(pdf_path)}",
        "file:///" + os.path.abspath(html_path).replace(os.sep, "/"),
    ]
    r = subprocess.run(cmd, capture_output=True, timeout=timeout_s)
    if r.returncode != 0 or not os.path.exists(pdf_path):
        raise RuntimeError(f"Browser could not print the PDF: {r.stderr.decode(errors='replace')}")


def html_to_pdf(html, output_path=None, layout="report", footer_template=None,
                gif_columns=None, timeout=180, allowed_hosts=None):
    """Print an HTML page to PDF.

    The page is adapted for paper first (see :func:`prepare_html_for_pdf`):
    GIFs become grids of frame panes, tables break between rows and
    repeat their header, and figures and headings are kept whole. Then
    headless Chromium prints it, with its JavaScript run, so Plotly charts
    come out as vector graphics.

    Args:
        html (str): The page, or the path to an ``.html`` file.
        output_path (str, optional): Where to write the PDF. If None, the
            PDF bytes are returned instead.
        layout (str): ``"report"`` (Letter portrait, the default) or
            ``"poster"`` (the page size the poster's own CSS sets).
        footer_template (str, optional): Chromium footer template, as made
            by :func:`page_footer`. Defaults to page numbers alone.
        gif_columns (int, optional): Frames per row for GIFs.
        timeout (int): Seconds to wait for the page and its charts.
        allowed_hosts (list[str], optional): Hosts the page may load
            anything from, for printing HTML you did not write (a server
            passes :data:`REPORT_HOSTS`). Without Playwright there is no
            way to enforce it, so the print fails rather than falling
            back to the browser's own unguarded ``--print-to-pdf``. Local
            files other than the page, and private and loopback addresses,
            are refused either way.

    Returns:
        str | bytes: ``output_path`` if given, otherwise the PDF bytes.

    Raises:
        RuntimeError: No browser could be found or the print failed.
    """
    if isinstance(html, str) and len(html) < 4096 and html.lower().endswith((".html", ".htm")) \
            and os.path.exists(html):
        with open(html, encoding="utf-8") as f:
            html = f.read()
    prepared = prepare_html_for_pdf(html, layout=layout, gif_columns=gif_columns)
    footer = footer_template if footer_template is not None else page_footer()

    tmp = tempfile.mkdtemp(prefix="geeviz_pdf_")
    try:
        html_path = os.path.join(tmp, "page.html")
        pdf_path = os.path.join(tmp, "page.pdf")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(prepared)

        err = []

        def _run():
            try:
                _print_playwright(html_path, pdf_path, layout, footer, timeout, allowed_hosts)
            except BaseException as e:  # reported below, then the fallback runs
                err.append(e)

        try:
            import playwright  # noqa: F401
            # Playwright's sync API refuses to run on a thread with an
            # asyncio loop (Jupyter, the MCP server). A thread of its own
            # never has one.
            t = threading.Thread(target=_run, daemon=True)
            t.start()
            t.join(timeout + 60)
            if t.is_alive():
                err.append(TimeoutError(f"printing took more than {timeout + 60}s"))
        except ImportError as e:
            err.append(e)

        if err or not os.path.exists(pdf_path):
            why = f"{type(err[0]).__name__}: {err[0]}" if err else "no PDF written"
            if allowed_hosts is not None:
                raise RuntimeError(f"Could not print the PDF ({why})")
            print(f"  PDF: Playwright unavailable ({why}); printing with the browser "
                  f"directly, without page numbers", flush=True)
            _print_cli(html_path, pdf_path, timeout)

        with open(pdf_path, "rb") as f:
            data = f.read()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if output_path is None:
        return data
    d = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(d, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(data)
    print(f"PDF saved to: {output_path}", flush=True)
    return output_path
