// Time-enabled ArcGIS services as timelapses (js/esri/timelapse.js): one
// frame per time step, each drawn with the service's time= parameter.
import { test } from "node:test";
import assert from "node:assert/strict";
import { fakeFetch, fixture, response } from "./esrifake.mjs";
import { esriFrameLoader } from "../js/esri/timelapse.js";
import { isTimelapse, isTimelapseKind } from "../js/util.js";
import { pluginFor } from "../js/plugins/index.js";

const LCMS = fixture("lcms_info").request.url;
const engineWith = (fetch) => ({ fetch });
const layer = (url, viz = {}) => ({ id: "t1", name: "Change", kind: "esri.timelapse", item: url, viz: { timelapse: true, ...viz } });

test("an image service's catalog years are the frames", async () => {
  const fetch = fakeFetch([[LCMS, "lcms_info"], [LCMS + "/query", "lcms_catalog_years"], [LCMS + "/legend", "lcms_legend"]]);
  const ld = esriFrameLoader(engineWith(fetch), layer(LCMS));
  const p = await ld.prepare();
  assert.equal(p.legend.type, "images");
  assert.equal(p.legend.items.length, 16);
  const years = await ld.years();
  const want = response("lcms_catalog_years").features.map((f) => String(f.attributes.year)).sort();
  assert.deepEqual(years, want);
  assert.equal(years[0], "1985");
});

test("each frame draws its own time step", async () => {
  const fetch = fakeFetch([[LCMS, "lcms_info"], [LCMS + "/query", "lcms_catalog_years"], [LCMS + "/legend", "lcms_legend"]]);
  const ld = esriFrameLoader(engineWith(fetch), layer(LCMS, { esri: { renderingRule: { rasterFunction: "None" } } }));
  await ld.years();
  const urlFor = await ld.frame(0);
  assert.equal(typeof urlFor, "function");
  const u = new URL(urlFor({ x: 6, y: 12 }, 5));
  assert.ok(u.pathname.endsWith("/ImageServer/exportImage"), u.pathname);
  assert.equal(u.searchParams.get("time"), `${Date.UTC(1985, 0, 1)},${Date.UTC(1986, 0, 1) - 1}`);
  assert.deepEqual(JSON.parse(u.searchParams.get("renderingRule")), { rasterFunction: "None" });
  const last = await ld.frame((await ld.years()).length - 1);
  assert.ok(new URL(last({ x: 0, y: 0 }, 1)).searchParams.get("time").startsWith(String(Date.UTC(Number((await ld.years()).slice(-1)[0]), 0, 1))));
});

test("the Query tool asks the service for its values over time", async () => {
  const fetch = fakeFetch([[LCMS, "lcms_info"]]);
  const ld = esriFrameLoader(engineWith(fetch), layer(LCMS));
  const t = await ld.queryTarget();
  assert.deepEqual([t.type, t.item], ["esri.image", LCMS]);
  assert.equal(typeof pluginFor("esri.timelapse").query, "function");
});

test("a service that is not time-enabled says so", async () => {
  const url = "https://example.com/arcgis/rest/services/x/ImageServer";
  const fetch = fakeFetch([[url, { name: "x", pixelType: "U8" }]]);
  const ld = esriFrameLoader(engineWith(fetch), { ...layer(url), name: "Plain" });
  await assert.rejects(ld.years(), /Plain is not time-enabled, so it cannot play as a timelapse\./);
});

test("both timelapse kinds are timelapses", () => {
  assert.ok(isTimelapseKind("timelapse") && isTimelapseKind("esri.timelapse"));
  assert.ok(!isTimelapseKind("esri.image"));
  assert.ok(isTimelapse({ kind: "esri.timelapse" }) && !isTimelapse(null));
});

test("the plug-in starts an Esri timelapse with the Esri frame loader", () => {
  const calls = [];
  const started = pluginFor("esri.timelapse").start({ kind: "esri.timelapse" }, { addTimelapse: (l, loader) => calls.push(loader) });
  assert.equal(started, true);
  assert.equal(calls[0], esriFrameLoader);
  assert.equal(pluginFor("esri.image").start({ kind: "esri.image" }, { addTimelapse: () => calls.push("no") }), false);
});
