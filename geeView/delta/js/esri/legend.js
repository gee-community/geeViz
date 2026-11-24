// A map or image service's legend, from its /legend endpoint, as the ArcGIS
// JS API's Legend widget shows it: the swatch images the server draws, one
// section per sublayer drawn.
import { esriRequest } from "./rest.js";

// The sublayer ids an ArcGIS `layers` string draws: show, hide, include or
// exclude, against the sublayers drawn by default.
export function layerChoice(layers, spec) {
  const all = layers || [];
  const byDefault = new Set(all.filter((l) => l.defaultVisibility !== false).map((l) => l.id));
  const m = /^\s*(show|hide|include|exclude)\s*:\s*([\d,\s]*)$/i.exec(String(spec || ""));
  if (!m) return byDefault;
  const ids = m[2].split(",").map((s) => s.trim()).filter(Boolean).map(Number);
  const how = m[1].toLowerCase();
  if (how === "show") return new Set(ids);
  if (how === "include") return new Set([...byDefault, ...ids]);
  return new Set([...byDefault].filter((id) => ids.indexOf(id) === -1));
}

const isNumber = (v) => v !== null && v !== "" && Number.isFinite(Number(v));

function itemsOf(entry) {
  return (entry.legend || []).map((it) => ({
    label: it.label || entry.layerName || "",
    src: `data:${it.contentType || "image/png"};base64,${it.imageData || ""}`,
    values: it.values || null,
  }));
}

// Class values for an image service legend: its own numeric values or
// labels, else, when there is one item per value between the service's
// minimum and maximum, those values in order (a class map whose legend names
// its classes but not their numbers).
function withValues(items, info) {
  const own = items.map((it) => (it.values && it.values.length === 1 && isNumber(it.values[0]) ? Number(it.values[0]) : isNumber(it.label) ? Number(it.label) : null));
  if (own.every((v) => v !== null)) return items.map((it, i) => ({ ...it, value: own[i] }));
  const min = info && info.minValues && Number(info.minValues[0]);
  const max = info && info.maxValues && Number(info.maxValues[0]);
  if (Number.isInteger(min) && Number.isInteger(max) && max - min + 1 === items.length) {
    return items.map((it, i) => ({ ...it, value: min + i }));
  }
  return items;
}

const clean = (items) => items.map(({ label, src, value }) => (value === undefined ? { label, src } : { label, src, value }));

// serviceLegend(url, info, esriOpts, {fetch, title}) -> legend or null.
export async function serviceLegend(url, info, esriOpts = {}, opts = {}) {
  const o = esriOpts || {};
  const params = {};
  if (o.renderingRule) params.renderingRule = o.renderingRule;
  const out = await esriRequest(url + "/legend", params, opts);
  const isImage = /\/ImageServer$/i.test(url);
  let entries = out.layers || [];
  if (!isImage && info && Array.isArray(info.layers) && info.layers.length) {
    const keep = layerChoice(info.layers, o.layers);
    entries = entries.filter((e) => keep.has(e.layerId));
  }
  const title = opts.title || (info && (info.mapName || info.name)) || "";
  const sections = entries
    .map((e) => ({ title: e.layerName || "", items: clean(isImage ? withValues(itemsOf(e), info) : itemsOf(e)) }))
    .filter((s) => s.items.length);
  if (!sections.length) return null;
  if (sections.length === 1) return { type: "images", title, items: sections[0].items };
  return { type: "sections", title, sections };
}
