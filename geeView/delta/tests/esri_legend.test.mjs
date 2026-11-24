// Service legends (js/esri/legend.js) from recorded /legend answers, and how
// the layer list writes them (js/ui/legend.js).
import { test } from "node:test";
import assert from "node:assert/strict";
import { fakeFetch, fixture, response } from "./esrifake.mjs";
import { serviceLegend, layerChoice } from "../js/esri/legend.js";
import { legendMarkup, swatchColors } from "../js/ui/legend.js";

const NFHL = fixture("nfhl_info").request.url;
const LCMS = fixture("lcms_info").request.url;

test("a map service legend: one section per sublayer drawn by default", async () => {
  const fetch = fakeFetch([[NFHL + "/legend", "nfhl_legend"]]);
  const lg = await serviceLegend(NFHL, response("nfhl_info"), {}, { fetch, title: "Flood" });
  assert.equal(lg.type, "sections");
  assert.equal(lg.title, "Flood");
  const shown = response("nfhl_info").layers.filter((l) => l.defaultVisibility).map((l) => l.name);
  assert.deepEqual(lg.sections.map((s) => s.title).sort(), shown.slice().sort());
  const zones = lg.sections.find((s) => s.title === "Flood Hazard Zones");
  assert.equal(zones.items.length, 8);
  zones.items.forEach((it) => assert.ok(it.src.startsWith("data:image/png;base64,"), it.src.slice(0, 30)));
});

test("a layers choice keeps only those sublayers; one left is a flat legend", async () => {
  const fetch = fakeFetch([[NFHL + "/legend", "nfhl_legend"]]);
  const lg = await serviceLegend(NFHL, response("nfhl_info"), { layers: "show:28" }, { fetch, title: "Zones" });
  assert.equal(lg.type, "images");
  assert.equal(lg.items.length, 8);
  const two = await serviceLegend(NFHL, response("nfhl_info"), { layers: "show:27,28" }, { fetch, title: "Z" });
  assert.deepEqual(two.sections.map((s) => s.title).sort(), ["Flood Hazard Boundaries", "Flood Hazard Zones"]);
  // hide: removes from the default set
  const hide = await serviceLegend(NFHL, response("nfhl_info"), { layers: "hide:0,3,14,27" }, { fetch, title: "Z" });
  assert.equal(hide.type, "images");
});

test("layerChoice reads ArcGIS layers strings", () => {
  const all = [{ id: 1, defaultVisibility: true }, { id: 2, defaultVisibility: false }, { id: 3, defaultVisibility: true }];
  assert.deepEqual([...layerChoice(all, "")].sort(), [1, 3]);
  assert.deepEqual([...layerChoice(all, "show:2")], [2]);
  assert.deepEqual([...layerChoice(all, "hide:1")], [3]);
  assert.deepEqual([...layerChoice(all, "include:2")].sort(), [1, 2, 3]);
  assert.deepEqual([...layerChoice(all, "exclude:3")], [1]);
});

test("an image service class legend gets the class values", async () => {
  const fetch = fakeFetch([[LCMS + "/legend", "lcms_legend"]]);
  const lg = await serviceLegend(LCMS, response("lcms_info"), {}, { fetch, title: "LCMS" });
  assert.equal(lg.type, "images");
  assert.equal(lg.items.length, 16);
  assert.deepEqual(lg.items.map((i) => i.value), Array.from({ length: 16 }, (_, i) => i + 1));
  assert.equal(lg.items[0].label, "Wind");
  assert.equal(lg.items[15].label, "Non-Processing Area Mask");
  // the rendering rule goes with the legend request
  await serviceLegend(LCMS, response("lcms_info"), { renderingRule: { rasterFunction: "None" } }, { fetch, title: "x" });
  assert.deepEqual(JSON.parse(fetch.calls[1].params.renderingRule), { rasterFunction: "None" });
});

test("legend markup: images and sections, escaped, data images only", () => {
  const lg = {
    type: "images",
    items: [
      { label: "<b>Zone A</b>", src: "data:image/png;base64,AAAA" },
      { label: "bad", src: "javascript:alert(1)" },
    ],
  };
  const html = legendMarkup(lg);
  assert.ok(html.includes('<img class="lgimg" src="data:image/png;base64,AAAA"'), html);
  assert.ok(html.includes("&lt;b&gt;Zone A&lt;/b&gt;"));
  assert.ok(!html.includes("javascript:"));
  assert.ok(!html.includes(">bad<"));
  const sec = legendMarkup({ type: "sections", sections: [{ title: "Zones & more", items: [lg.items[0]] }] });
  assert.ok(sec.includes('class="lgsec"') && sec.includes("Zones &amp; more"), sec);
  const sw = swatchColors({ type: "sections", sections: [{ title: "a", items: [lg.items[0], lg.items[0]] }, { title: "b", items: [lg.items[0]] }] });
  assert.equal(sw.kind, "images");
  assert.equal(sw.srcs.length, 3);
  assert.deepEqual(sw.colors, sw.srcs);
  assert.equal(swatchColors({ type: "images", items: [lg.items[1]] }), null);
});
