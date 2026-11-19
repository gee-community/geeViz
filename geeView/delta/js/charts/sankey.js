// Class-transition (Sankey) charts with d3-sankey. Port of
// geeViz/outputLib/_templates.py D3_SANKEY_TEMPLATE: links drawn with a
// gradient from the source class color to the target class color, node
// labels with a halo in the background color, tooltips on links and nodes,
// labels in SVG attributes so the PNG export keeps them. As in the approved
// mockup, only the outer columns are labeled, each column carries its
// period, and the diagram is drawn at the card's width. Names are text.
import { downloadUrl } from "./theme.js";

const LINK_OPACITY = 0.55;
const MIN_LABEL_HEIGHT = 10;

// The d3-sankey graph for a Sankey result: one node per period and class
// that carries flow, links re-indexed to them, colors from the classes.
export function sankeyGraph(r) {
  const d = r.data;
  const n = d.classNames.length || 1;
  const used = [...new Set(d.links.flatMap((l) => [l.source, l.target]))].sort((a, b) => a - b);
  const at = new Map(used.map((g, i) => [g, i]));
  const nodes = used.map((g) => {
    const col = Math.floor(g / n);
    const ci = g % n;
    return {
      name: d.classNames[ci] !== undefined ? String(d.classNames[ci]) : String(ci),
      period: d.periods[col],
      color: d.classPalette[ci] || "#888888",
      col,
    };
  });
  const links = d.links.map((l) => ({
    source: at.get(l.source),
    target: at.get(l.target),
    value: l.value,
    sourceColor: l.source_color,
    targetColor: l.target_color,
  }));
  return { nodes, links, columns: d.periods.slice() };
}

// Outer columns only, and only nodes tall enough to hold a line of text.
export function nodeLabelShown(node, columnCount) {
  return (node.col === 0 || node.col === columnCount - 1) && node.y1 - node.y0 > MIN_LABEL_HEIGHT;
}

const fmt = (v) => (typeof v === "number" ? v.toLocaleString("en-US", { maximumFractionDigits: 3 }) : String(v));

// Tooltip lines for a link: source and target with their periods, then the value.
export function linkTip(link, unit) {
  return [`${link.source.name} (${link.source.period}) → ${link.target.name} (${link.target.period})`, `${fmt(link.value)} ${unit}`];
}
export function nodeTip(node, unit) {
  return [`${node.name} (${node.period})`, `${fmt(node.value || 0)} ${unit}`];
}

let tipEl = null;
function tip() {
  if (!tipEl || !tipEl.isConnected) {
    tipEl = document.createElement("div");
    tipEl.className = "tip";
    tipEl.setAttribute("role", "tooltip");
    document.body.appendChild(tipEl);
  }
  return tipEl;
}
function showTip(event, lines) {
  const t = tip();
  // inside the expand modal the tip must live in the dialog's top layer
  const host = (event.target && event.target.closest && event.target.closest("dialog")) || document.body;
  if (t.parentNode !== host) host.appendChild(t);
  t.replaceChildren(
    ...lines.map((line, i) => {
      const e = document.createElement(i === lines.length - 1 ? "b" : "div");
      e.textContent = line;
      return e;
    })
  );
  moveTip(event);
  t.classList.add("on");
}
function moveTip(event) {
  const t = tip();
  t.style.left = event.clientX + 12 + "px";
  t.style.top = event.clientY - 28 + "px";
}
function hideTip() {
  if (tipEl) tipEl.classList.remove("on");
}

let uid = 0;

// Draw a Sankey result into el at el's width. Returns the svg element.
export function renderSankey(el, r, theme) {
  const d3 = window.d3;
  el.replaceChildren();
  if (!d3 || !d3.sankey) return null;
  const g = sankeyGraph(r);
  if (!g.links.length) {
    const p = document.createElement("div");
    p.className = "val-code";
    p.textContent = `No class transitions of at least ${r.data.minPercentage}% of the area.`;
    el.appendChild(p);
    return null;
  }
  const unit = r.data.unitText;
  const W = Math.max(240, Math.round(el.clientWidth || 300));
  const H = Math.round(W * 0.72);
  const top = 18;
  const id = "dzsk" + ++uid;
  const svg = d3
    .select(el)
    .append("svg")
    .attr("xmlns", "http://www.w3.org/2000/svg")
    .attr("viewBox", `0 0 ${W} ${H}`)
    .attr("width", W)
    .attr("height", H);
  const sankey = d3
    .sankey()
    .nodeWidth(9)
    .nodePadding(7)
    .nodeSort(null)
    .extent([
      [1, top],
      [W - 1, H - 4],
    ]);
  const graph = sankey({ nodes: g.nodes.map((x) => ({ ...x })), links: g.links.map((x) => ({ ...x })) });

  // --- Gradients ---
  const defs = svg.append("defs");
  graph.links.forEach((link, i) => {
    const grad = defs
      .append("linearGradient")
      .attr("id", `${id}-g${i}`)
      .attr("gradientUnits", "userSpaceOnUse")
      .attr("x1", link.source.x1)
      .attr("y1", 0)
      .attr("x2", link.target.x0)
      .attr("y2", 0);
    grad.append("stop").attr("offset", "0%").attr("stop-color", link.sourceColor);
    grad.append("stop").attr("offset", "100%").attr("stop-color", link.targetColor);
  });

  // --- Links ---
  svg
    .append("g")
    .attr("fill", "none")
    .selectAll("path")
    .data(graph.links)
    .join("path")
    .attr("class", "link")
    .attr("d", d3.sankeyLinkHorizontal())
    .attr("stroke", (dd, i) => `url(#${id}-g${i})`)
    .attr("stroke-width", (dd) => Math.max(1, dd.width))
    .attr("stroke-opacity", LINK_OPACITY)
    .on("mouseover", function (event, dd) {
      d3.select(this).attr("stroke-opacity", 0.9);
      showTip(event, linkTip(dd, unit));
    })
    .on("mousemove", moveTip)
    .on("mouseout", function () {
      d3.select(this).attr("stroke-opacity", LINK_OPACITY);
      hideTip();
    });

  // --- Nodes ---
  const nodeG = svg.append("g").selectAll("g").data(graph.nodes).join("g");
  nodeG
    .append("rect")
    .attr("x", (dd) => dd.x0)
    .attr("y", (dd) => dd.y0)
    .attr("width", (dd) => dd.x1 - dd.x0)
    .attr("height", (dd) => Math.max(1, dd.y1 - dd.y0))
    .attr("rx", 2)
    .attr("fill", (dd) => dd.color)
    .on("mouseover", (event, dd) => showTip(event, nodeTip(dd, unit)))
    .on("mousemove", moveTip)
    .on("mouseout", hideTip);

  // --- Labels: outer columns, halo in the background color ---
  const last = g.columns.length - 1;
  nodeG
    .filter((dd) => nodeLabelShown(dd, g.columns.length))
    .append("text")
    .attr("class", "node-label")
    .attr("x", (dd) => (dd.col === last ? dd.x0 - 4 : dd.x1 + 4))
    .attr("y", (dd) => (dd.y0 + dd.y1) / 2)
    .attr("dy", "0.35em")
    .attr("text-anchor", (dd) => (dd.col === last ? "end" : "start"))
    .attr("fill", theme.ink)
    .attr("stroke", theme.solid)
    .attr("stroke-width", 3)
    .attr("paint-order", "stroke")
    .attr("font-size", 10)
    .attr("font-weight", 600)
    .attr("font-family", theme.font)
    .text((dd) => dd.name);

  // --- Column (period) labels ---
  g.columns.forEach((p, ci) => {
    const node = graph.nodes.find((dd) => dd.col === ci);
    const x = ci === 0 ? 0 : ci === last ? W : node ? (node.x0 + node.x1) / 2 : (W * ci) / last;
    svg
      .append("text")
      .attr("class", "col-label")
      .attr("x", x)
      .attr("y", 11)
      .attr("text-anchor", ci === 0 ? "start" : ci === last ? "end" : "middle")
      .attr("fill", theme.faint)
      .attr("font-size", 10)
      .attr("font-family", theme.mono)
      .text(p);
  });
  return svg.node();
}

// port of D3_SANKEY_TEMPLATE's PNG download: serialize the SVG over a
// background rect, draw it on a 2x canvas, save the PNG.
export function sankeyPng(el, filename, theme) {
  const svgEl = el && el.querySelector("svg");
  if (!svgEl) return Promise.resolve(null);
  const W = Number(svgEl.getAttribute("width"));
  const H = Number(svgEl.getAttribute("height"));
  const clone = svgEl.cloneNode(true);
  const bg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  bg.setAttribute("width", W);
  bg.setAttribute("height", H);
  bg.setAttribute("fill", theme.solid);
  clone.insertBefore(bg, clone.firstChild);
  const data = new XMLSerializer().serializeToString(clone);
  const scale = 2;
  const canvas = document.createElement("canvas");
  canvas.width = W * scale;
  canvas.height = H * scale;
  const ctx = canvas.getContext("2d");
  ctx.scale(scale, scale);
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      ctx.drawImage(img, 0, 0, W, H);
      const url = canvas.toDataURL("image/png");
      downloadUrl(url, filename + ".png");
      resolve(url);
    };
    img.onerror = () => reject(new Error("The Sankey chart could not be drawn as an image"));
    img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(data);
  });
}
