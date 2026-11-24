// A shapefile picked as its parts (.shp, .shx, .dbf, .prj, ...) is zipped in
// the browser and sent like a .zip upload.
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { crc32, zipStore } from "../js/engine/zip.js";
import { shapefileSets } from "../js/engine/areasources.js";

const bytes = (s) => new TextEncoder().encode(s);

test("crc32 matches the standard check value", () => {
  assert.equal(crc32(bytes("123456789")), 0xcbf43926);
  assert.equal(crc32(new Uint8Array(0)), 0);
});

test("zipStore writes an archive other tools read back exactly", () => {
  const files = [
    { name: "parts unit.shp", bytes: bytes("shape bytes") },
    { name: "parts unit.dbf", bytes: new Uint8Array([0, 1, 2, 255]) },
  ];
  const zip = zipStore(files);
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "dzzip-"));
  const p = path.join(dir, "t.zip");
  fs.writeFileSync(p, zip);
  // Python's zipfile, the reader the server uses, checks every CRC
  // the workspace's venv when it is there (a bare "python" may be a store stub)
  const venv = new URL("../../../../venv/Scripts/python.exe", import.meta.url);
  const py = process.env.DELTA_PYTHON || (fs.existsSync(venv) ? fileURLToPath(venv) : "python");
  const out = execFileSync(py, ["-c", "import zipfile,sys,json;z=zipfile.ZipFile(sys.argv[1]);assert z.testzip() is None;print(json.dumps({n:list(z.read(n)) for n in z.namelist()}))", p]).toString();
  assert.deepEqual(JSON.parse(out), { "parts unit.shp": [...bytes("shape bytes")], "parts unit.dbf": [0, 1, 2, 255] });
});

test("shapefileSets: one zip name per shapefile, and the missing part named", () => {
  assert.deepEqual(shapefileSets(["a.shp", "a.shx", "a.dbf", "a.prj"]), { sets: ["a"], error: null });
  assert.deepEqual(shapefileSets(["A.SHP", "a.shx", "a.DBF"]).error, null); // any case
  assert.match(shapefileSets(["a.shp", "a.shx"]).error, /a\.dbf/);
  assert.match(shapefileSets(["a.shp", "a.dbf", "a.prj"]).error, /a\.shx/);
  assert.deepEqual(shapefileSets(["a.shp", "a.shx", "a.dbf", "b.shp", "b.shx", "b.dbf"]).sets, ["a", "b"]);
  // parts with no .shp, or a part for a shapefile not picked
  assert.match(shapefileSets(["a.dbf", "a.shx"]).error, /\.shp/);
  assert.match(shapefileSets(["a.shp", "a.shx", "a.dbf", "b.dbf"]).error, /b\.dbf/);
  // a non-shapefile file among the parts: one upload at a time
  assert.match(shapefileSets(["a.shp", "a.shx", "a.dbf", "x.kml"]).error, /x\.kml/);
});
