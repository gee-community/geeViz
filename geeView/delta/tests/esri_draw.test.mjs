// Esri map, tile and image services drawn as map tiles (js/esri/draw.js,
// js/plugins/esri.js), on recorded metadata.
import { test } from "node:test";
import assert from "node:assert/strict";
import { fakeFetch, fixture } from "./esrifake.mjs";
import { exportUrl, tileUrl, tile3857 } from "../js/esri/draw.js";
import { esriPlugin } from "../js/plugins/esri.js";
import { pluginFor, needsEE } from "../js/plugins/index.js";

const NFHL = fixture("nfhl_info").request.url;
const TOPO = fixture("topo_info").request.url;
const LCMS = fixture("lcms_info").request.url;
const B = { xmin: -11760000, ymin: 4940000, xmax: -11750000, ymax: 4950000 };

const params = (u) => Object.fromEntries(new URL(u).searchParams.entries());

test("a map service exports one transparent PNG per tile", () => {
  const u = exportUrl(NFHL, "esri.map", { layers: "show:28" }, B);
  assert.ok(u.startsWith(NFHL + "/export?"), u);
  const p = params(u);
  assert.equal(p.bbox, "-11760000,4940000,-11750000,4950000");
  assert.equal(p.bboxSR, "3857");
  assert.equal(p.imageSR, "3857");
  assert.equal(p.size, "256,256");
  assert.equal(p.transparent, "true");
  assert.equal(p.format, "png32");
  assert.equal(p.f, "image");
  assert.equal(p.layers, "show:28");
});

test("an image service exports with its rendering rule and time", () => {
  const info = fixture("lcms_info").response;
  const u = exportUrl(LCMS, "esri.image", { time: [1, 2], renderingRule: { rasterFunction: "None" }, bandIds: [0] }, B, 256, info);
  assert.ok(u.startsWith(LCMS + "/exportImage?"), u);
  const p = params(u);
  assert.equal(p.time, "1,2");
  assert.deepEqual(JSON.parse(p.renderingRule), { rasterFunction: "None" });
  assert.equal(p.bandIds, "0");
  assert.equal(p.format, "jpgpng");
  // an integer single band (a class map) is not smoothed
  assert.equal(p.interpolation, "RSP_NearestNeighbor");
  assert.equal(p.layers, undefined);
});

test("tile URLs and tile bounds", () => {
  assert.equal(tileUrl(TOPO)({ x: 6, y: 12 }, 5), TOPO + "/tile/5/12/6");
  const b = tile3857(0, 0, 0);
  assert.ok(Math.abs(b.xmin + 20037508.34) < 1 && Math.abs(b.ymax - 20037508.34) < 1);
  const q = tile3857(1, 1, 1);
  assert.ok(Math.abs(q.xmin) < 1e-6 && Math.abs(q.ymax) < 1e-6);
});

test("the Esri kinds are one plug-in, with no Earth Engine", () => {
  for (const k of ["esri.feature", "esri.map", "esri.tile", "esri.image", "esri.timelapse"]) {
    assert.equal(pluginFor(k), esriPlugin, k);
    assert.equal(needsEE({ kind: k }), false, k);
  }
  assert.equal(esriPlugin.ownsViz, true);
});

function fakeCtx(fetch) {
  const calls = { tiles: [], kinds: [], loading: [], fails: [] };
  return {
    calls,
    fetch,
    tileOverlay: (r, urlFor, extra) => {
      calls.tiles.push({ urlFor, extra });
      return { urlFor };
    },
    setKind: (r, kind) => {
      calls.kinds.push(kind);
      r.kind = kind;
      r.layerType = kind;
    },
    setLoading: (r, v) => calls.loading.push(v),
    sync: () => {},
    fail: (r, e) => calls.fails.push(String(e && e.message ? e.message : e)),
  };
}

test("draw: a dynamic map service is drawn by export, tile by tile", async () => {
  const ctx = fakeCtx(fakeFetch([[NFHL, "nfhl_info"]]));
  const r = { id: "l1", kind: "esri.map", layerType: "esri.map", viz: { esri: { layers: "show:28" } }, item: NFHL };
  await esriPlugin.draw(r, NFHL, ctx);
  assert.deepEqual(ctx.calls.fails, []);
  assert.equal(ctx.calls.tiles.length, 1);
  assert.equal(r.tileType, true);
  const u = ctx.calls.tiles[0].urlFor({ x: 0, y: 0 }, 0);
  assert.ok(u.startsWith(NFHL + "/export?") && u.includes("layers=show%3A28"), u);
});

test("draw: a cached map service added as a map service becomes tiles", async () => {
  const ctx = fakeCtx(fakeFetch([[TOPO, "topo_info"]]));
  const r = { id: "l2", kind: "esri.map", layerType: "esri.map", viz: {}, item: TOPO };
  await esriPlugin.draw(r, TOPO, ctx);
  assert.deepEqual(ctx.calls.kinds, ["esri.tile"]);
  assert.equal(ctx.calls.tiles[0].urlFor({ x: 6, y: 12 }, 5), TOPO + "/tile/5/12/6");
  assert.equal(ctx.calls.tiles[0].extra.maxZoom, 23);
});

test("draw: a service that fails says why on the layer", async () => {
  const ctx = fakeCtx(fakeFetch([[() => true, "error_body"]]));
  const url = "https://example.com/arcgis/rest/services/x/MapServer";
  await esriPlugin.draw({ id: "l3", kind: "esri.map", layerType: "esri.map", viz: {}, item: url }, url, ctx);
  assert.equal(ctx.calls.fails.length, 1);
  assert.match(ctx.calls.fails[0], /Invalid URL/);
});

test("exports go as 1024 px blocks of 4 by 4 map tiles (from zoom 2)", async () => {
  const { exportTileUrl } = await import("../js/esri/draw.js");
  const f = exportTileUrl(NFHL, "esri.map", {}, null);
  const t = f({ x: 6, y: 13 }, 5);
  assert.deepEqual(t.block, { size: 1024, x: 512, y: 256 });
  const p = params(t.url);
  assert.equal(p.size, "1024,1024");
  const b = tile3857(1, 3, 3);
  assert.equal(p.bbox, [b.xmin, b.ymin, b.xmax, b.ymax].join(","));
  // the 16 tiles of a block share its URL
  assert.equal(f({ x: 7, y: 15 }, 5).url, t.url);
  // the world at zoom 0 and 1: one image per tile
  assert.equal(typeof f({ x: 0, y: 0 }, 1), "string");
  // a service that limits image size to under 1024 px: tile by tile
  assert.equal(typeof exportTileUrl(NFHL, "esri.map", {}, { maxImageWidth: 800, maxImageHeight: 800 })({ x: 6, y: 13 }, 5), "string");
});
