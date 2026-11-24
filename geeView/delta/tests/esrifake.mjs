// Recorded ArcGIS responses (tests/fixtures/esri, written by record.py) and
// a fake fetch that answers from them, for the Esri plug-in tests.
import fs from "node:fs";

const DIR = new URL("./fixtures/esri/", import.meta.url);

export function fixture(name) {
  return JSON.parse(fs.readFileSync(new URL(name + ".json", DIR), "utf8"));
}
export const response = (name) => fixture(name).response;

// A request's URL and its params, whether sent as GET or a POST form.
export function parseRequest(url, init = {}) {
  const u = new URL(url);
  const params = Object.fromEntries(u.searchParams.entries());
  if (init.body) {
    const body = typeof init.body === "string" ? init.body : init.body.toString();
    Object.assign(params, Object.fromEntries(new URLSearchParams(body).entries()));
  }
  return { base: u.origin + u.pathname, params, method: (init.method || "GET").toUpperCase() };
}

// fakeFetch(routes): routes is [[match(req) -> bool | base url string, answer]],
// answer a fixture name, an object (the JSON), or a function(req) -> either.
// Every request is kept in fetch.calls. An unmatched request rejects.
export function fakeFetch(routes) {
  const calls = [];
  const fn = async (url, init) => {
    const req = parseRequest(url, init);
    req.url = url;
    req.init = init || {};
    calls.push(req);
    for (const [match, answer] of routes) {
      const hit = typeof match === "string" ? req.base === match : match(req);
      if (!hit) continue;
      let body = typeof answer === "function" ? answer(req) : answer;
      if (body instanceof Error) throw body;
      if (typeof body === "string") body = response(body);
      if (body && body.__status) return { ok: false, status: body.__status, json: async () => ({}), text: async () => "" };
      return { ok: true, status: 200, json: async () => body, text: async () => JSON.stringify(body) };
    }
    throw new Error("no route for " + url);
  };
  fn.calls = calls;
  return fn;
}
