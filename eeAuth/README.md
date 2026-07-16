# geeViz.eeAuth — Earth Engine multi-tenant auth proxy

A token-injecting HTTP proxy + Python client helpers that let one Python
process talk to Earth Engine on behalf of many service accounts
concurrently. Bypasses the `ee.Initialize()` global-credential
limitation that normally forces a process-per-tenant design.

## Why

The Earth Engine Python SDK stores credentials in module-global state
via `ee.Initialize()`. Two tenants can't run concurrently in one
process without racing each other's auth. By routing every REST call
through a local proxy that injects the right SA per request, you keep
one Python process, one `ee.Initialize` call, and get full multi-tenant
concurrency — for browser JS clients **and** server-side Python.

## Package layout

| File | Purpose |
|---|---|
| `registry.py` | SA discovery + per-tenant token cache |
| `tags.py` | EE workload-tag construction for billing attribution |
| `client.py` | `initialize_via_proxy()` + `TenantAwareHttp` (server-side Python) |
| `server.py` | FastAPI proxy app (mountable or standalone) |
| `__main__.py` | `python -m geeViz.eeAuth` CLI runner |

## Configuring tenants

The proxy reads service-account credentials from environment variables:

| Env var | Meaning |
|---|---|
| `GEE_SERVICE_ACCOUNT_B64` | Default tenant (legacy name kept for back-compat) |
| `GEE_<NAME>_SERVICE_ACCOUNT` | Named tenant (e.g. `GEE_TRAINING_SERVICE_ACCOUNT` → `training`) |

Each value is **base64-encoded service-account JSON**.

```bash
# One-line encoder
GEE_SERVICE_ACCOUNT_B64=$(base64 -w0 sa-default.json)
GEE_TRAINING_SERVICE_ACCOUNT=$(base64 -w0 sa-training.json)
```

Each SA must be **registered with Earth Engine** independently — the
proxy just signs requests; it can't grant EE access.

## Running the proxy

### Standalone

```bash
python -m geeViz.eeAuth --port 8888
```

Hit `http://localhost:8888/` to see the loaded tenants. All EE REST
endpoints are exposed at `/ee-api/v1/...`.

### Mounted in an existing FastAPI app

```python
from fastapi import FastAPI
from geeViz.eeAuth.server import build_proxy_router

app = FastAPI()
app.include_router(build_proxy_router(), prefix="/ee-api")
```

This is what the AskTerra agent does — the proxy is one of many routes
in the same FastAPI app, sharing IAP and Cloud Logging integration.

## Tenant routing

The proxy picks which SA to use per-request, in this precedence order:

1. **`/ee-api/t/<tenant>/` URL path prefix** — the primary mechanism.
   Used by every browser tab `Map.view()` opens. The tenant is
   **not in the query string** — it's baked into the URL PATH of every
   REST call the tab issues. See "How `Map.view()` pins each browser
   tab" below.
2. **`X-geeViz-Creds` header** — set by the server-side Python EE SDK
   via the `TenantAwareHttp` transport. Reads from a `ContextVar`, so
   `async` and threaded code carry their own tenant per-request.
3. **`?tenant=` query string** — accepted as a fallback / manual override
   (useful for one-off curl testing). Rarely used by real callers.
4. **Default tenant** (`GEE_SERVICE_ACCOUNT_B64`, or the first registered
   credential in `eeCreds`) — when none of the above resolve.

### How `Map.view()` pins each browser tab

The URL `Map.view()` opens in the browser has **no** tenant in it — just
a cache-buster (`?v=<timestamp>`). Tenant routing works because
`Map.view()` prepends a tiny JavaScript snippet to the per-session
`runGeeViz.js` that gets fetched by the tab:

```javascript
// This runs BEFORE ee.initialize() fires, and reassigns the top-level
// `authProxyAPIURL` variable that lcms-viewer.min.js set to the default
// "/ee-api". Once reassigned, every REST call the EE JS SDK issues
// carries the /t/<tenant>/ path prefix.
try {
  authProxyAPIURL = window.location.origin + '/ee-api/t/<tenant>';
} catch (e) {}
```

So the full request lifecycle for a tab is:

1. Python opens `http://127.0.0.1:8889/geeView/?v=<ts>` in the browser.
2. Browser loads the page, then fetches the per-session `runGeeViz.js`.
3. `runGeeViz.js` executes the snippet above, reassigning
   `authProxyAPIURL` to include `/t/<tenant>`.
4. `ee.initialize(authProxyAPIURL, ...)` is called, and every downstream
   `getMapId` / `value:compute` / `computePixels` POST goes to
   `http://127.0.0.1:8889/ee-api/t/<tenant>/v1/…`.
5. The proxy reads `<tenant>` out of the URL path (see
   `server.py` `_proxy_ee_api`, ~line 515) and mints the token for
   that credential.

Because the snippet is baked into each per-session `runGeeViz.js`, **each
open browser tab is permanently pinned** to whichever tenant was current
when `Map.view()` was called. A later `eeCreds.use("other")` in Python
changes the process-wide default (so a *new* `Map.view()` call uses
"other"), but existing tabs keep talking to their original tenant — no
credential drift on open windows.

### Worked example: two maps, two tenants, two billing projects

Two service accounts, each registered with EE on a different GCP project.
One Python process opens two `Map.view()` tabs — one per SA — and every
EE call from each tab is billed to the matching project.

**Setup (once at startup):**

```python
from geeViz.eeAuth import eeCreds

eeCreds.addCreds("sa-a.json", name="tenant-a", project="project-a")
eeCreds.addCreds("sa-b.json", name="tenant-b", project="project-b")
eeCreds.start()      # spins up local proxy on 127.0.0.1:8889
```

After this the proxy's registry is just a Python dict:

```python
registry._sa_json = {
    "tenant-a": { ...sa-a.json..., "project_id": "project-a" },
    "tenant-b": { ...sa-b.json..., "project_id": "project-b" },
}
```

**Open Map A (bills project-a):**

```python
from geeViz.geeView import Map
import ee

eeCreds.use("tenant-a")
Map.clearMap()
Map.addLayer(ee.Image("USGS/SRTMGL1_003"),
             {"min": 0, "max": 4000, "palette": "green,yellow,white"},
             "SRTM")
Map.view()
```

The tab's per-session `runGeeViz.js` prepends:

```javascript
authProxyAPIURL = window.location.origin + "/ee-api/t/tenant-a";
```

**Open Map B in a second tab (bills project-b), same process:**

```python
eeCreds.use("tenant-b")
Map.clearMap()
Map.addLayer(ee.Image("USDA/NAIP/DOQQ/m_..."),
             {"bands": ["R", "G", "B"], "min": 0, "max": 255},
             "NAIP")
Map.view()
```

Tab #2's `runGeeViz.js` prepends:

```javascript
authProxyAPIURL = window.location.origin + "/ee-api/t/tenant-b";
```

**Traffic on the wire — what each tab actually sends.** No
Authorization header ever leaves the tab; the tenant sits in the URL
path segment:

```
# Map A — every getMapId, value:compute, image:computePixels
POST http://127.0.0.1:8889/ee-api/t/tenant-a/v1/projects/project-a/maps:getMap
POST http://127.0.0.1:8889/ee-api/t/tenant-a/v1/projects/project-a/value:compute
POST http://127.0.0.1:8889/ee-api/t/tenant-a/v1/projects/project-a/image:computePixels

# Map B — same shape, different tenant + different EE project
POST http://127.0.0.1:8889/ee-api/t/tenant-b/v1/projects/project-b/maps:getMap
POST http://127.0.0.1:8889/ee-api/t/tenant-b/v1/projects/project-b/value:compute
POST http://127.0.0.1:8889/ee-api/t/tenant-b/v1/projects/project-b/image:computePixels
```

**What the proxy forwards to Google.** For each request it parses
`t/<name>/` out of the path, looks up `registry._sa_json[name]`,
mints (or returns cached) an OAuth token, and stamps two headers:

```
# Map A's request as it leaves the proxy toward Google
POST https://earthengine.googleapis.com/v1/projects/project-a/maps:getMap
Authorization:       Bearer ya29.a0AS3H6NxTOKEN-A…
x-goog-user-project: project-a           ← billing target

# Map B's request
POST https://earthengine.googleapis.com/v1/projects/project-b/maps:getMap
Authorization:       Bearer ya29.a0AS3H6NxTOKEN-B…
x-goog-user-project: project-b           ← billing target
```

**Tile bytes bypass the proxy.** The `getMapId` JSON that comes back
contains a pre-signed tile URL that the browser hits directly:

```
GET https://earthengine.googleapis.com/v1/projects/project-a/maps/xxxxx/tiles/10/163/395
  (no proxy hop, no Authorization header — URL carries its own signature)
```

**Net result:** every `getMapId` / `value:compute` / `image:computePixels`
from tab A bills project-a; the same calls from tab B bill project-b.
The two tabs are permanently pinned — a later `eeCreds.use("some-other")`
in Python won't change what either tab does; it only changes what a
*new* `Map.view()` call would use.

**The only thing the client ever sends is a tenant NAME** — an opaque
identifier like `"tenant-a"`. The credential material (SA JSON, minted
OAuth token) never leaves the Python process. A network trace between
the browser and the proxy shows no SA keys and no bearer tokens — just
tenant names in URL paths.

## Initializing the Python EE SDK to use the proxy

```python
from geeViz.eeAuth import initialize_via_proxy, tenant_context
import ee

initialize_via_proxy("http://localhost:8888/ee-api")

# Default tenant
print(ee.Image(1).getInfo())

# Switch tenant for a block
with tenant_context("training"):
    print(ee.Image(2).getInfo())   # uses the training SA
    # any nested .getInfo / .getMapId / Export.* etc. routes through the
    # training SA — no global state changes
```

This works because:

- `ee.Initialize(url=...)` plus `http_transport=TenantAwareHttp()`
  tells the SDK to send all REST calls through the proxy.
- `AnonymousCredentials` is used so the SDK doesn't try to attach its
  own bearer — the proxy substitutes its own.
- The `CURRENT_TENANT` `ContextVar` propagates through `await`
  boundaries, so concurrent tenant work is safe.

## Initializing the JS EE SDK to use the proxy

```js
ee.initialize(
  "http://localhost:8888/ee-api",     // authProxyAPIURL — calls go here
  "https://earthengine.googleapis.com", // tile URL — direct to EE
  () => { /* on success */ },
  (err) => { /* on failure */ },
  null,
  "ee-proxy-placeholder",
);
```

Pass `?tenant=<name>` on the iframe URL to switch tenants in the
browser path.

## Customizing

```python
build_proxy_router(
    upstream="https://earthengine.googleapis.com",  # or content-earthengine
    tenant_header="X-MyOrg-Tenant",                 # rename the header
    tenant_query_param="org",                       # rename the query param
    tenant_resolver=my_resolver,                    # custom (request) -> tenant
    workload_tag_builder=my_tag,                    # custom (request, tenant) -> tag
)
```

A custom `tenant_resolver` lets you resolve tenancy from IAP identity,
JWT claims, or wherever else your auth lives. The default reads the
header then the query param.

A custom `workload_tag_builder` lets you build richer attribution tags
(user + session + tool etc.). Default builds `ee-proxy__<tenant>`.

## Workload tags

Every POST request gets a `workloadTag` query parameter added. EE
surfaces these in GCP Billing under the
`goog-earth-engine-workload-tag` label, so spend slices cleanly by
tenant. See `tags.py` for the tag-construction rules.

## Testing

The proxy can be exercised against any EE endpoint:

```bash
curl http://localhost:8888/ee-api/v1/projects/earthengine-legacy/algorithms

# Switch tenant
curl -H "X-geeViz-Creds: training" \
  http://localhost:8888/ee-api/v1/projects/earthengine-legacy/algorithms
```

The response is whatever EE itself returned; the proxy is transparent
once auth is substituted.
