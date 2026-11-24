// Earth Engine is loaded and signed in only when a map needs it: once,
// however many layers ask, and a failure is reported to each of them.
import { test } from "node:test";
import assert from "node:assert/strict";
import { createEELoader, lazyEE, EE_SCRIPT_URL } from "../js/engine/ee.js";

function stubs({ fail } = {}) {
  const calls = { load: [], init: [] };
  return {
    calls,
    loadScript: (url) => {
      calls.load.push(url);
      return Promise.resolve();
    },
    init: (urlParams, proxyUrl) => {
      calls.init.push({ urlParams, proxyUrl });
      return fail ? Promise.reject(fail) : Promise.resolve();
    },
  };
}

test("ensure loads the script and signs in once, however many callers", async () => {
  const s = stubs();
  const loader = createEELoader({ urlParams: {}, proxyUrl: "/ee-api", loadScript: s.loadScript, init: s.init });
  await Promise.all([loader.ensure(), loader.ensure(), loader.ensure()]);
  assert.deepEqual(s.calls.load, [EE_SCRIPT_URL]);
  assert.equal(s.calls.init.length, 1);
  assert.equal(loader.isReady(), true);
  assert.equal(loader.error(), null);
});

test("a failed sign-in rejects every caller with the described failure", async () => {
  const s = stubs({ fail: new Error("invalid authentication credentials") });
  const loader = createEELoader({ urlParams: { accessToken: "x" }, proxyUrl: "", loadScript: s.loadScript, init: s.init });
  const results = await Promise.allSettled([loader.ensure(), loader.ensure()]);
  for (const r of results) {
    assert.equal(r.status, "rejected");
    assert.match(r.reason.message, /The access token looks invalid or expired/);
  }
  assert.match(loader.error(), /The access token looks invalid or expired/);
  assert.equal(loader.isReady(), false);
  assert.equal(s.calls.init.length, 1);
});

test("whenReady runs queued functions in order after sign-in, and never on failure", async () => {
  const ok = stubs();
  const loader = createEELoader({ urlParams: {}, loadScript: ok.loadScript, init: ok.init });
  const seen = [];
  loader.whenReady(() => seen.push(1));
  loader.whenReady(() => seen.push(2));
  assert.deepEqual(seen, []);
  await loader.ensure();
  assert.deepEqual(seen, [1, 2]);
  loader.whenReady(() => seen.push(3)); // already ready: runs now
  assert.deepEqual(seen, [1, 2, 3]);

  const bad = stubs({ fail: new Error("nope") });
  const failing = createEELoader({ urlParams: {}, loadScript: bad.loadScript, init: bad.init });
  const never = [];
  failing.whenReady(() => never.push(1));
  await failing.ensure().catch(() => {});
  assert.deepEqual(never, []);
});

test("an exported page signs in with its access token", async () => {
  const s = stubs();
  const urlParams = { accessToken: "tok", projectID: "p" };
  const loader = createEELoader({ urlParams, proxyUrl: "", loadScript: s.loadScript, init: s.init });
  await loader.ensure();
  assert.equal(s.calls.init[0].urlParams, urlParams);
});

test("lazyEE reads the global once loaded and says so before", () => {
  const saved = globalThis.ee;
  try {
    delete globalThis.ee;
    assert.throws(() => lazyEE.Image, /not loaded/);
    globalThis.ee = { Image: 1 };
    assert.equal(lazyEE.Image, 1);
  } finally {
    if (saved === undefined) delete globalThis.ee;
    else globalThis.ee = saved;
  }
});
