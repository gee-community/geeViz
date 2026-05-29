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

The proxy picks which SA to use, in this order:

1. **`X-geeViz-Creds` header** — set by server-side EE SDK via the
   `TenantAwareHttp` transport.
2. **`?tenant=` query string** — set by browser map iframes via the JS
   `ee.initialize(authProxyAPIURL, ...)` URL.
3. **Default tenant** (`GEE_SERVICE_ACCOUNT_B64`) — when neither signal
   is present.

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
