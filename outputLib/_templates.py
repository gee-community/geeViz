"""
HTML / JS / CSS templates for geeViz output libraries.

All visual templates live here so they can be edited in one place.
Templates use placeholder tokens (``__BG_COLOR__``, ``__TEXT_COLOR__``, etc.)
that are substituted at render time from a :class:`~geeViz.outputLib.themes.Theme`.

Render helpers accept a ``Theme`` object and return ready-to-use strings.
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

import textwrap


# ===================================================================
#  Chart templates  (from chartingLib)
# ===================================================================

def render_chart_style(theme):
    """Return a ``<style>`` tag for chart HTML pages.

    Args:
        theme: A :class:`~geeViz.outputLib.themes.Theme` instance.

    Returns:
        str: HTML ``<style>`` block.
    """
    return (
        f"<style>\n"
        f"  body {{ background: {theme.bg_hex}; margin: 0; }}\n"
        f"  .plotly-graph-div {{ margin: 0 auto; }}\n"
        f"</style>"
    )


# ---------------------------------------------------------------------------
#  Plotly Sankey gradient injection JS
# ---------------------------------------------------------------------------
# Placeholder tokens:
#   __FLAT_TO_GRADIENT_JSON__  - JSON map of "r,g,b" -> [src_hex, tgt_hex]
#   __LINK_OPACITY__           - float opacity for gradient stops
#   __LINK_STROKE_COLOR__      - rgba string for link edge stroke
#   __PLOTLY_BG_COLOR__        - hex bg color for PNG export fill

SANKEY_GRADIENT_JS = r"""
<script>
(function() {
    var flatToGrad = __FLAT_TO_GRADIENT_JSON__;
    var linkOpacity = __LINK_OPACITY__;
    var linkStroke = '__LINK_STROKE_COLOR__';
    var bgColor = '__PLOTLY_BG_COLOR__';
    var ns = 'http://www.w3.org/2000/svg';
    // Persistent map: element -> gradientId  (survives hover resets)
    var assigned = new Map();
    var gradCount = 0;

    function rgbKey(s) {
        if (!s) return null;
        var m = s.match(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/);
        return m ? (m[1] + ',' + m[2] + ',' + m[3]) : null;
    }

    function ensureDefs(svg) {
        var defs = svg.querySelector('defs');
        if (!defs) {
            defs = document.createElementNS(ns, 'defs');
            svg.insertBefore(defs, svg.firstChild);
        }
        return defs;
    }

    function createGradient(defs, el, sc, tc) {
        var gradId = 'sankey-grad-' + gradCount++;
        var grad = document.createElementNS(ns, 'linearGradient');
        grad.setAttribute('id', gradId);
        grad.setAttribute('gradientUnits', 'userSpaceOnUse');
        var bbox = el.getBBox();
        grad.setAttribute('x1', bbox.x);
        grad.setAttribute('y1', bbox.y + bbox.height / 2);
        grad.setAttribute('x2', bbox.x + bbox.width);
        grad.setAttribute('y2', bbox.y + bbox.height / 2);
        var stop1 = document.createElementNS(ns, 'stop');
        stop1.setAttribute('offset', '0%');
        stop1.setAttribute('stop-color', sc);
        stop1.setAttribute('stop-opacity', linkOpacity);
        var stop2 = document.createElementNS(ns, 'stop');
        stop2.setAttribute('offset', '100%');
        stop2.setAttribute('stop-color', tc);
        stop2.setAttribute('stop-opacity', linkOpacity);
        grad.appendChild(stop1);
        grad.appendChild(stop2);
        defs.appendChild(grad);
        return gradId;
    }

    function applyGradients() {
        var svg = document.querySelector('.main-svg');
        if (!svg) return false;
        var defs = ensureDefs(svg);
        // Build a working copy of the map for first-pass assignment
        var available = {};
        for (var k in flatToGrad) available[k] = flatToGrad[k];

        // Find all link paths
        var paths = [];
        svg.querySelectorAll('.sankey-link').forEach(function(g) {
            g.querySelectorAll('path').forEach(function(p) { paths.push(p); });
        });
        if (!paths.length) {
            svg.querySelectorAll('.sankey path').forEach(function(p) { paths.push(p); });
        }

        paths.forEach(function(el) {
            // If already assigned, just ensure the fill is set
            if (assigned.has(el)) {
                var gid = assigned.get(el);
                if (el.style.fill !== 'url(#' + gid + ')') {
                    el.style.fill = 'url(#' + gid + ')';
                    el.style.stroke = linkStroke;
                    el.style.strokeWidth = '0.5px';
                }
                return;
            }
            // First time: match by flat color
            var fill = el.style.fill || el.getAttribute('fill') || '';
            var key = rgbKey(fill);
            if (!key || !available[key]) return;
            var colors = available[key];
            delete available[key]; // consume so duplicates get separate gradients
            var gradId = createGradient(defs, el, colors[0], colors[1]);
            assigned.set(el, gradId);
            el.style.fill = 'url(#' + gradId + ')';
            el.style.stroke = linkStroke;
            el.style.strokeWidth = '0.5px';
        });

        return paths.length > 0;
    }

    // Initial application with polling
    var attempts = 0;
    function init() {
        attempts++;
        if (applyGradients() || attempts > 50) {
            // Start observing for Plotly hover resets
            var svg = document.querySelector('.main-svg');
            if (svg) {
                new MutationObserver(function() { applyGradients(); })
                    .observe(svg, { attributes: true, subtree: true, attributeFilter: ['style'] });
            }
        } else {
            setTimeout(init, 200);
        }
    }
    setTimeout(init, 500);

    // Override Plotly's built-in camera (download) button to capture SVG gradients
    function overrideDownloadButton() {
        var plotDiv = document.querySelector('.plotly-graph-div');
        if (!plotDiv) return;
        var modebar = plotDiv.querySelector('.modebar-container .modebar-group');
        if (!modebar) return;
        // Find the existing toImage button and replace its click handler
        var buttons = modebar.querySelectorAll('.modebar-btn');
        buttons.forEach(function(btn) {
            var title = btn.getAttribute('data-title') || '';
            if (title.toLowerCase().indexOf('download') >= 0 || title.toLowerCase().indexOf('image') >= 0) {
                var clone = btn.cloneNode(true);
                clone.setAttribute('data-title', 'Download as PNG');
                clone.addEventListener('click', function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    downloadPNG();
                });
                btn.parentNode.replaceChild(clone, btn);
            }
        });
    }

    function downloadPNG() {
        applyGradients();
        // Collect all SVG layers that Plotly renders (main-svg, title, etc.)
        var plotDiv = document.querySelector('.plotly-graph-div');
        if (!plotDiv) return;
        var allSvgs = plotDiv.querySelectorAll('svg');
        // Filter out modebar SVGs (toolbar icons)
        var svgs = [];
        allSvgs.forEach(function(s) {
            if (!s.closest('.modebar-container')) svgs.push(s);
        });
        if (!svgs.length) return;
        var plotRect = plotDiv.getBoundingClientRect();
        var scale = 2;
        var canvas = document.createElement('canvas');
        canvas.width = plotRect.width * scale;
        canvas.height = plotRect.height * scale;
        var ctx = canvas.getContext('2d');
        ctx.scale(scale, scale);
        // Fill with page background
        ctx.fillStyle = bgColor;
        ctx.fillRect(0, 0, plotRect.width, plotRect.height);
        // Render each SVG layer onto the canvas in order
        var loaded = 0;
        var total = svgs.length;
        var images = [];
        svgs.forEach(function(svg, i) {
            var rect = svg.getBoundingClientRect();
            var svgData = new XMLSerializer().serializeToString(svg);
            var img = new Image();
            images[i] = { img: img, x: rect.left - plotRect.left, y: rect.top - plotRect.top,
                          w: rect.width, h: rect.height };
            img.onload = function() {
                loaded++;
                if (loaded === total) {
                    // Draw all layers in DOM order
                    for (var j = 0; j < total; j++) {
                        var m = images[j];
                        ctx.drawImage(m.img, m.x, m.y, m.w, m.h);
                    }
                    var a = document.createElement('a');
                    a.download = ((cfg && cfg.title) ? cfg.title.replace(/[^a-zA-Z0-9_-]/g, '_') : 'sankey_chart') + '.png';
                    a.href = canvas.toDataURL('image/png');
                    a.click();
                };
            };
            img.onerror = function() { loaded++; };
            img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svgData);
        });
    }
    setTimeout(overrideDownloadButton, 1000);
})();
</script>
"""


# ---------------------------------------------------------------------------
#  D3 Sankey template
# ---------------------------------------------------------------------------
# Placeholder tokens:
#   __BG_COLOR__         - hex background color
#   __TEXT_COLOR__        - hex text color
#   __TOOLTIP_BG__       - rgba tooltip background
#   __BUTTON_BG__        - rgba button background
#   __BUTTON_HOVER_BG__  - rgba button hover background
#   __BUTTON_BORDER__    - rgba button border
#   __D3_DATA_JSON__     - JSON data (nodes/links)
#   __D3_CONFIG_JSON__   - JSON config (width, height, colors, etc.)

D3_SANKEY_TEMPLATE = r"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Sankey Diagram</title>
<script src="https://unpkg.com/d3@7"></script>
<script src="https://unpkg.com/d3-sankey@0"></script>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: __BG_COLOR__; font-family: Roboto, Arial, sans-serif; }
  .plotly-graph-div { margin: 0 auto; }
  #sankey { display: block; margin: 0 auto; }
  #title {
    text-align: center; padding: 16px 0 4px 0;
    font-size: 16px; font-weight: 600; color: __TEXT_COLOR__;
  }
  #toolbar {
    position: absolute; top: 8px; right: 16px;
    display: flex; gap: 6px;
  }
  #toolbar button {
    background: __BUTTON_BG__; border: 1px solid __BUTTON_BORDER__;
    color: __TEXT_COLOR__; padding: 4px 12px; border-radius: 4px; cursor: pointer;
    font-size: 12px;
  }
  #toolbar button:hover { background: __BUTTON_HOVER_BG__; }
  .link:hover { stroke-opacity: 0.8 !important; }
  .node-label {
    fill: __TEXT_COLOR__; font-size: 11px;
    stroke: __BG_COLOR__; stroke-width: 3px; paint-order: stroke;
  }
  .tooltip {
    position: absolute; background: __TOOLTIP_BG__; color: __TEXT_COLOR__;
    padding: 6px 10px; border-radius: 4px; font-size: 12px;
    pointer-events: none; opacity: 0; transition: opacity 0.15s;
    white-space: nowrap;
  }
</style>
</head><body>
<div id="title"></div>
<div id="toolbar">
  <button id="btn-png">Download PNG</button>
</div>
<svg id="sankey"></svg>
<div class="tooltip" id="tooltip"></div>
<script>
(function() {
    var data = __D3_DATA_JSON__;
    var cfg = __D3_CONFIG_JSON__;

    document.getElementById('title').textContent = cfg.title || '';
    document.querySelector('body').style.background = cfg.bgColor || '__BG_COLOR__';
    // Also update CSS custom halo color
    document.querySelectorAll('.node-label').forEach(function(el) {
        el.style.stroke = cfg.bgColor || '__BG_COLOR__';
    });

    var margin = { top: 10, right: 20, bottom: 10, left: 20 };
    var w = cfg.width - margin.left - margin.right;
    var h = cfg.height - margin.top - margin.bottom - 40; // 40 for title

    var svg = d3.select('#sankey')
        .attr('width', cfg.width)
        .attr('height', cfg.height - 36)
        .append('g')
        .attr('transform', 'translate(' + margin.left + ',' + margin.top + ')');

    var sankey = d3.sankey()
        .nodeWidth(cfg.nodeWidth || 20)
        .nodePadding(cfg.nodePadding || 15)
        .nodeSort(null)
        .extent([[0, 0], [w, h]]);

    var graph = sankey({
        nodes: data.nodes.map(function(d) { return Object.assign({}, d); }),
        links: data.links.map(function(d) { return Object.assign({}, d); })
    });

    var tooltip = document.getElementById('tooltip');

    // --- Gradients ---
    var defs = svg.append('defs');
    graph.links.forEach(function(link, i) {
        var grad = defs.append('linearGradient')
            .attr('id', 'link-grad-' + i)
            .attr('gradientUnits', 'userSpaceOnUse')
            .attr('x1', link.source.x1)
            .attr('y1', 0)
            .attr('x2', link.target.x0)
            .attr('y2', 0);
        grad.append('stop')
            .attr('offset', '0%')
            .attr('stop-color', data.links[i].sourceColor)
            .attr('stop-opacity', cfg.opacity);
        grad.append('stop')
            .attr('offset', '100%')
            .attr('stop-color', data.links[i].targetColor)
            .attr('stop-opacity', cfg.opacity);
    });

    // --- Links ---
    svg.append('g')
        .attr('fill', 'none')
        .selectAll('path')
        .data(graph.links)
        .join('path')
        .attr('class', 'link')
        .attr('d', d3.sankeyLinkHorizontal())
        .attr('stroke', function(d, i) { return 'url(#link-grad-' + i + ')'; })
        .attr('stroke-width', function(d) { return Math.max(1, d.width); })
        .attr('stroke-opacity', cfg.opacity)
        .on('mouseover', function(event, d) {
            d3.select(this).attr('stroke-opacity', 0.9);
            var srcName = d.source.name || '';
            var tgtName = d.target.name || '';
            var val = d.value;
            tooltip.style.opacity = 1;
            tooltip.innerHTML = srcName + ' &rarr; ' + tgtName + ': ' + val.toLocaleString();
        })
        .on('mousemove', function(event) {
            tooltip.style.left = (event.pageX + 12) + 'px';
            tooltip.style.top = (event.pageY - 20) + 'px';
        })
        .on('mouseout', function() {
            d3.select(this).attr('stroke-opacity', cfg.opacity);
            tooltip.style.opacity = 0;
        });

    // --- Nodes ---
    var nodeG = svg.append('g')
        .selectAll('g')
        .data(graph.nodes)
        .join('g');

    nodeG.append('rect')
        .attr('x', function(d) { return d.x0; })
        .attr('y', function(d) { return d.y0; })
        .attr('height', function(d) { return Math.max(1, d.y1 - d.y0); })
        .attr('width', function(d) { return d.x1 - d.x0; })
        .attr('fill', function(d) { return d.color || cfg.textColor || '#888'; })
        .attr('opacity', cfg.opacity)
        .on('mouseover', function(event, d) {
            tooltip.style.opacity = 1;
            tooltip.innerHTML = d.name + ': ' + (d.value || 0).toLocaleString();
        })
        .on('mousemove', function(event) {
            tooltip.style.left = (event.pageX + 12) + 'px';
            tooltip.style.top = (event.pageY - 20) + 'px';
        })
        .on('mouseout', function() { tooltip.style.opacity = 0; });

    // --- Labels ---
    // Inline all styles as SVG attributes so they survive clone+serialize for PNG export
    nodeG.append('text')
        .attr('class', 'node-label')
        .attr('x', function(d) { return d.x0 < w / 2 ? d.x0 + 6 : d.x1 - 6; })
        .attr('y', function(d) { return (d.y0 + d.y1) / 2; })
        .attr('dy', '0.35em')
        .attr('text-anchor', function(d) { return d.x0 < w / 2 ? 'start' : 'end'; })
        .attr('fill', cfg.textColor || '__TEXT_COLOR__')
        .attr('font-size', '11px')
        .attr('font-family', 'Roboto, Arial, sans-serif')
        .attr('stroke', cfg.bgColor || '__BG_COLOR__')
        .attr('stroke-width', '3px')
        .attr('paint-order', 'stroke')
        .text(function(d) { return d.name; });

    // --- Download PNG ---
    document.getElementById('btn-png').addEventListener('click', function() {
        var titleEl = document.getElementById('title');
        var svgEl = document.querySelector('#sankey');
        // Build a combined SVG with title + chart
        var fullW = cfg.width;
        var fullH = cfg.height;
        var combinedSvg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        combinedSvg.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
        combinedSvg.setAttribute('width', fullW);
        combinedSvg.setAttribute('height', fullH);
        // Background rect
        var bgRect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        bgRect.setAttribute('width', fullW);
        bgRect.setAttribute('height', fullH);
        bgRect.setAttribute('fill', cfg.bgColor || '__BG_COLOR__');
        combinedSvg.appendChild(bgRect);
        // Title text
        if (cfg.title) {
            var titleText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            titleText.setAttribute('x', fullW / 2);
            titleText.setAttribute('y', 24);
            titleText.setAttribute('text-anchor', 'middle');
            titleText.setAttribute('fill', cfg.textColor || '__TEXT_COLOR__');
            titleText.setAttribute('font-family', 'Roboto, Arial, sans-serif');
            titleText.setAttribute('font-size', '16');
            titleText.setAttribute('font-weight', '600');
            titleText.textContent = cfg.title;
            combinedSvg.appendChild(titleText);
        }
        // Clone chart SVG content into a <g> offset for the title
        var chartGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        chartGroup.setAttribute('transform', 'translate(0, 36)');
        var svgContent = svgEl.cloneNode(true);
        // Copy all children from the cloned SVG
        while (svgContent.firstChild) {
            chartGroup.appendChild(svgContent.firstChild);
        }
        combinedSvg.appendChild(chartGroup);
        // Render to canvas
        var svgData = new XMLSerializer().serializeToString(combinedSvg);
        var scale = 2;
        var canvas = document.createElement('canvas');
        canvas.width = fullW * scale;
        canvas.height = fullH * scale;
        var ctx = canvas.getContext('2d');
        ctx.scale(scale, scale);
        var img = new Image();
        img.onload = function() {
            ctx.drawImage(img, 0, 0, fullW, fullH);
            var a = document.createElement('a');
            a.download = ((cfg && cfg.title) ? cfg.title.replace(/[^a-zA-Z0-9_-]/g, '_') : 'sankey_chart') + '.png';
            a.href = canvas.toDataURL('image/png');
            a.click();
        };
        img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svgData);
    });
})();
</script>
</body></html>
"""


def render_d3_sankey(theme):
    """Return the D3 Sankey template with theme colors substituted.

    Only fills in the CSS-level color placeholders.  The caller still needs
    to substitute ``__D3_DATA_JSON__`` and ``__D3_CONFIG_JSON__``.

    Args:
        theme: A :class:`~geeViz.outputLib.themes.Theme` instance.

    Returns:
        str: HTML template with color placeholders resolved.
    """
    return (
        D3_SANKEY_TEMPLATE
        .replace("__BG_COLOR__", theme.bg_hex)
        .replace("__TEXT_COLOR__", theme.text_hex)
        .replace("__TOOLTIP_BG__", theme.tooltip_bg_rgba)
        .replace("__BUTTON_BG__", theme.button_bg_rgba)
        .replace("__BUTTON_HOVER_BG__", theme.button_hover_rgba)
        .replace("__BUTTON_BORDER__", theme.button_border_rgba)
    )


def render_sankey_gradient_js(gradient_map_json, opacity, theme):
    """Return the Plotly Sankey gradient JS with all placeholders filled.

    Args:
        gradient_map_json (str): JSON string of the flat-to-gradient color map.
        opacity (float): Link opacity.
        theme: A :class:`~geeViz.outputLib.themes.Theme` instance.

    Returns:
        str: ``<script>`` block ready for injection.
    """
    return (
        SANKEY_GRADIENT_JS
        .replace("__FLAT_TO_GRADIENT_JSON__", gradient_map_json)
        .replace("__LINK_OPACITY__", str(opacity))
        .replace("__LINK_STROKE_COLOR__", theme.link_stroke_rgba)
        .replace("__PLOTLY_BG_COLOR__", theme.bg_hex)
    )


# ===================================================================
#  Report templates  (from reportLib)
# ===================================================================

def render_report_css(theme, layout="report"):
    """Generate complete CSS for a report from a Theme object.

    Args:
        theme: A :class:`~geeViz.outputLib.themes.Theme` instance.
        layout (str): ``"report"`` or ``"poster"``.

    Returns:
        str: Complete CSS string.
    """
    t = theme

    # Derive a lighter surface for alternating table rows in light themes
    from geeViz.outputLib._colors import blend, to_hex
    row_alt_bg = blend(t.surface, t.bg, 0.5) if not t.is_dark else t.surface

    base_css = textwrap.dedent(f"""\
        @import url('https://fonts.googleapis.com/css?family=Roboto+Condensed&display=swap');
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background: {t.bg_hex}; color: {to_hex(t.text)};
            font-family: 'Roboto Condensed', 'Segoe UI', Arial, sans-serif;
            line-height: 1.6; padding: 24px;
        }}
        .report-header {{
            display: flex; align-items: center; gap: 14px;
            padding: 12px 16px; margin-bottom: 12px;
            background: {t.surface_hex};
            border-bottom: 2px solid {t.accent_hex};
            border-radius: 6px 6px 0 0;
            overflow: visible;
        }}
        .report-header img {{ height: 40px; width: auto; max-width: 100px;
            border-radius: 4px; flex-shrink: 0; }}
        .report-header h1 {{ color: {t.accent_hex}; font-size: 24px; margin: 0;
            overflow-wrap: break-word; }}
        h2 {{ color: {t.accent_hex}; font-size: 20px; margin: 24px 0 10px 0;
             border-bottom: 1px solid {t.border_hex}; padding-bottom: 4px; }}
        .header-text {{ color: {t.muted_text_hex}; margin-bottom: 12px; font-size: 14px; }}
        .timestamp {{ color: {t.muted_text_hex}; font-size: 11px; margin-bottom: 20px; }}
        .summary, .narrative {{
            background: {t.surface_hex}; border-radius: 6px;
            padding: 14px 18px; margin: 10px 0; line-height: 1.65;
        }}
        .summary h3, .narrative h3 {{ color: {t.highlight_hex}; margin-bottom: 6px; font-size: 13px; }}
        .narrative p, .summary p {{ margin-bottom: 8px; color: {to_hex(t.text)}; font-size: 13px; }}
        .narrative ul, .summary ul {{ margin: 6px 0 6px 18px; color: {to_hex(t.text)}; font-size: 13px; }}
        .narrative strong, .summary strong {{ color: {t.highlight_hex}; }}
        .chart {{ margin: 12px 0; text-align: center; }}
        .chart img {{ max-width: 100%; border-radius: 6px; }}
        .chart .js-plotly-plot {{ margin: 0 auto; }}
        .thumb {{ margin: 10px 0; text-align: center; }}
        .thumb img {{ border-radius: 6px; max-width: 100%; }}
        .thumb figcaption {{ color: {t.muted_text_hex}; font-size: 11px; margin-top: 4px; }}
        .thumb-grid {{ display: grid; gap: 10px; margin: 12px 0; }}
        .gif-container {{ margin: 12px 0; text-align: center; }}
        .gif-container img {{ border-radius: 6px; max-width: 100%; }}
        .gif-container figcaption {{ color: {t.muted_text_hex}; font-size: 11px; margin-top: 4px; }}
        .filmstrip {{ margin: 12px 0; }}
        .filmstrip img {{ max-width: 100%; display: block; }}
        .filmstrip img:first-child {{ border-radius: 6px 6px 0 0; }}
        .filmstrip img:last-child {{ border-radius: 0 0 6px 6px; }}
        table {{ border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 11px; }}
        th, td {{ border: 1px solid {t.border_hex}; padding: 4px 8px; text-align: right; }}
        th {{ background: {t.surface_hex}; color: {t.accent_hex}; text-align: center; font-weight: 600; }}
        td {{ color: {to_hex(t.text)}; }}
        tr:nth-child(even) {{ background: {t.surface_rgba}; }}
        .section {{ margin-bottom: 32px; page-break-inside: avoid; }}
        .error {{ color: {t.highlight_hex}; background: {t.error_bg_rgba};
                 border-radius: 4px; padding: 10px; margin: 10px 0; font-size: 12px; }}
        .table-wrapper {{ overflow-x: auto; max-height: 600px; overflow-y: auto; margin: 10px 0; }}
        .table-wrapper::-webkit-scrollbar {{ width: 8px; height: 8px; }}
        .table-wrapper::-webkit-scrollbar-track {{ background: {t.bg_hex}; border-radius: 4px; }}
        .table-wrapper::-webkit-scrollbar-thumb {{ background: {t.border_hex}; border-radius: 4px; }}
        .table-wrapper::-webkit-scrollbar-thumb:hover {{ background: {t.muted_text_hex}; }}
        .table-units {{ color: {t.muted_text_hex}; font-size: 10px; margin: 2px 0 6px 0;
            font-style: italic; }}
        .matrix-title {{ color: {t.accent_hex}; font-size: 13px; margin: 12px 0 4px 0; }}
        .transition-matrix tr:nth-child(even) {{ background: transparent; }}
        .transition-matrix th {{ word-break: break-word; white-space: normal; max-width: 80px;
            font-size: 10px; padding: 3px 4px; }}
        .transition-matrix td {{ font-size: 10px; padding: 3px 4px; }}
        .transition-matrix .diag {{
            background: rgba({t.accent[0]}, {t.accent[1]}, {t.accent[2]}, 0.15);
            font-weight: 600;
        }}
        .transition-matrix .matrix-corner {{ font-size: 9px; font-style: italic;
            text-align: center; color: {t.muted_text_hex}; min-width: 60px; }}
        .report-footer {{
            margin-top: 36px; padding-top: 12px;
            border-top: 1px solid {t.border_hex};
            display: flex; align-items: center; gap: 10px;
            color: {t.muted_text_hex}; font-size: 10px;
        }}
        .report-footer img {{ height: 20px; width: 20px; border-radius: 4px; opacity: 0.7; }}
        .report-footer a {{ color: {t.accent_hex}; text-decoration: none; }}
        .report-footer a:hover {{ text-decoration: underline; }}
        .pdf-footer {{ display: none; }}
    """)

    layout_css = _LAYOUT_CSS.get(layout, _LAYOUT_CSS["report"])
    return base_css + layout_css


# Layout-specific CSS
_LAYOUT_CSS = {
    "report": textwrap.dedent("""\
        .report { max-width: 1100px; margin: 0 auto; }
        @media print {
            @page { size: portrait; margin: 0.5in; }
            .section { page-break-inside: avoid; }
        }
    """),

    "poster": textwrap.dedent("""\
        html, body { height: 100%; overflow: hidden; margin: 0; padding: 0; }
        body { padding: 0.4in; }
        .report {
            max-width: none; margin: 0;
            height: 100%;
            display: flex; flex-direction: column;
        }
        .report-header h1 { font-size: 32px; }
        .header-text { font-size: 13px; margin-bottom: 8px; }
        .timestamp { font-size: 10px; margin-bottom: 10px; }
        .summary { padding: 10px 14px; margin: 6px 0; }
        .summary h3 { font-size: 12px; margin-bottom: 4px; }
        .summary p { font-size: 11px; margin-bottom: 4px; }
        .poster-grid {
            flex: 1;
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 16px;
            align-items: start;
            align-content: start;
            overflow: hidden;
        }
        .poster-grid .section {
            margin-bottom: 0; break-inside: avoid;
            overflow: hidden;
        }
        .poster-grid h2 { margin-top: 0; font-size: 15px; margin-bottom: 6px; padding-bottom: 3px; }
        .poster-grid .narrative { padding: 8px 12px; margin: 6px 0; }
        .poster-grid .narrative p,
        .poster-grid .narrative ul { font-size: 10px; margin-bottom: 4px; line-height: 1.4; }
        .poster-grid .summary p,
        .poster-grid .summary ul { font-size: 10px; }
        .poster-grid .chart { margin: 6px 0; }
        .poster-grid .chart img { max-height: 280px; width: auto; }
        .poster-grid .thumb img { max-height: 250px; width: auto; }
        .poster-grid .gif-container img { max-height: 250px; width: auto; }
        .poster-grid table { font-size: 8px; }
        .poster-grid th, .poster-grid td { padding: 2px 4px; }
        .poster-grid .table-wrapper { max-height: 200px; overflow-y: auto; }
        .poster-grid .error { font-size: 10px; padding: 6px; }
        .report-footer { margin-top: 8px; padding-top: 6px; font-size: 9px; }
        .report-footer img { height: 16px; width: 16px; }
        @media print {
            @page { size: 48in 36in landscape; margin: 0.4in; }
            html, body { height: 100%; overflow: hidden; }
        }
        @media screen {
            html { height: 100vh; }
        }
    """),
}


# HTML page templates
HTML_TEMPLATE = textwrap.dedent("""\
    <!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title}</title>
    <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
    <style>{css}</style>
    </head>
    <body>
    <div class="report">
    {header_block}
    {header_text_html}
    <p class="timestamp">Generated {timestamp}</p>
    {summary_html}
    {sections_html}
    {footer_html}
    </div>
    </body>
    </html>
""")

# PDF template — no Plotly JS, charts are static images
PDF_HTML_TEMPLATE = textwrap.dedent("""\
    <!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="utf-8">
    <title>{title}</title>
    <style>{css}</style>
    </head>
    <body>
    <div class="report">
    {header_block}
    {header_text_html}
    <p class="timestamp">Generated {timestamp}</p>
    {summary_html}
    {sections_html}
    {footer_html}
    </div>
    {pdf_footer_html}
    </body>
    </html>
""")
