# geeViz Release Notes

## 2026.7.4 — July 16, 2026

### geeViz.outputLib._basemaps

- **GIF title-strip auto-shrinks when the title is wider than the
  strip.** Previously, a long title (e.g. "Great Salt Lake summer
  surface reflectance, 1985 — 2024") was measured, centered, and
  drawn against a fixed font size — if it overflowed the strip
  width, the leading `G` and trailing `4` got clipped and the read
  looked broken. The bold-font path now proportionally shrinks the
  font size to fit inside `width − 2 × margin` (single verification
  pass to correct for glyph-metric slop, plus a one-step tighten
  loop for the rare case where a wide glyph dominated the estimate).
  Font size is floored at 8 px so we don't render illegibly small
  labels on very narrow strips. Affects every GIF and filmstrip
  built through `outputLib.thumbs` that carries a title.

### geeViz.getImagesLib

- **Export-filename cleanup actually runs now.** Six lines across
  `exportToAssetWrapper`, `exportToDriveWrapper`, and
  `exportToCloudStorageWrapper` had a copy-paste bug that used a
  literal JavaScript regex string as the argument to Python's
  `str.replace` — e.g. `outputName.replace("/\s+/g", "-")`. Python's
  `str.replace` does not take regex, so the calls silently did
  nothing and spaces / forward slashes passed through untouched
  into EE asset names and Drive / GCS output filenames. Rewritten
  to `re.sub(r"\s+", "-", outputName)` (whitespace → dash) and
  `outputName.replace("/", "-")` (slashes → dash); `import re` added
  to the module. Also fixes the Python 3.12+ SyntaxWarning about
  invalid `\s` / `\/` escape sequences that surfaced on every
  sphinx-autodoc pass.

### geeViz.migrateGEEAssets

- **No side effects at import time.** The module previously ran
  `ee.Initialize()` at line 3 and `batchChangePermissions(None,
  sourceRoot, ...)` at the bottom, so `import geeViz.migrateGEEAssets`
  from any tool (autodoc, an agent's tool listing, a REPL exploring
  the package) actually tried to change permissions on a hardcoded
  personal test asset — burning through the caller's EE creds and
  raising confusing 404s along the way. All script-mode logic
  (`ee.Initialize`, the `batchChangePermissions` seed call) is now
  behind an `if __name__ == "__main__":` guard. Run the migration
  the intended way with `python -m geeViz.migrateGEEAssets`.
- **`getTree` no longer trips on unreadable subtrees.** When
  `ee.data.listAssets({"parent": fromRoot})` raised (missing folder,
  permission denied), the bare `except` printed the error but left
  the local `assets` unbound; the very next `for asset in assets:`
  then raised `UnboundLocalError`, masking the original EE error.
  The except now returns the accumulated tree so far, letting the
  outer walk continue past the bad subtree instead of aborting.

### Documentation

- **`ee_auth.rst` (new page in geeViz docs)** — dedicated Earth
  Engine authentication guide. Covers the two-mode client init
  (proxy vs. direct-token), the tenant-routing story
  (`/ee-api/t/<tenant>/` URL path segment, prepended to per-session
  `runGeeViz.js` by `Map.view()`), a worked two-maps / two-tenants /
  two-billing-projects example with concrete traffic captures for
  `getMapId` / `value:compute` / `image:computePixels` / thumbnails,
  and non-Google runtime coverage (AWS Workload Identity Federation,
  Azure Managed Identity, on-prem OIDC). Ships an interactive
  drawio diagram + full-resolution PNG.
- **New per-package READMEs.** `outputLib/README.md` describes the
  charts / thumbs / reports / themes surface; `geeView/README.md`
  walks the served-frontend layout (`index.html`, per-session
  `runGeeViz.js`, `lcms-viewer.min.js`) and the JS boot order.
- **`eeAuth/README.md` expanded.** Tenant routing section rewritten
  to put the `/ee-api/t/<tenant>/` URL path prefix first (with the
  actual JS snippet `Map.view()` prepends to `runGeeViz.js` shown
  inline), adds the "How `Map.view()` pins each browser tab"
  walk-through, and the same two-tenants / two-billing-projects
  worked example that ships in the new `ee_auth.rst` doc page.
- **`mcp/README.md` — accurate alias list + related-package links.**
  The "Persistent REPL namespace" section now enumerates every
  alias `run_code` binds (`ee`, `Map`, `gv`, `gil`, `sal`, `edw`,
  `gm`, `palettes`, `cl`, `tl`, `rl`, `pd`/`pandas`, `np`/`numpy`,
  `save_file`) instead of stopping at five, so the docs match what
  `env_info(action="namespace")` actually returns.

### Docstrings — sphinx build now clean

Several module docstrings had formatting that tripped docutils on
sphinx-autodoc (invalid indentation, block quotes without trailing
blank lines, markdown code fences that RST doesn't understand,
markdown table separators being interpreted as RST substitution
references). All fixed with no behavior change:

- `eeAuth/registry.py` — blank line before the env-var convention
  bullet list.
- `eeAuth/client.py` — `tenant_context` example rewritten as a
  proper `.. code-block:: python` directive.
- `foliumView.py` — module-level `Example:` code block reformatted.
- `geePalettes.py` — replaced ` ```python ` fences with RST literal
  blocks (`Example — X::`).
- `esriLib.py` — markdown-style service-type table replaced with an
  RST grid table.
- `outputLib/charts.py` — blank line before the numbered list in
  `prepare_sankey_data`.
- `mcp/server.py` — `map_control` action-value list pulled out of
  the `Args:` block into a standalone bulleted list so napoleon
  doesn't have to parse nested bullets under an Args entry.

### Notebooks

- **`!python -m pip install geeViz` → `subprocess.check_call(...)`
  across 18 example notebooks.** The bang-syntax is a Jupyter shell
  magic, not valid Python, so pygments' Python lexer flagged every
  notebook with a highlighting warning. Rewritten to a pure-Python
  subprocess install (same semantics: install if missing, then
  import), with the surrounding `except:` tightened to
  `except ImportError:` so a stray SyntaxError elsewhere can't be
  silently swallowed by the install fallback.
- **First-cell heading promotion.** `Annual_NLCD_Viewer_Notebook`,
  `LCMAP_and_LCMS_Viewer_Notebook`, and
  `geeViewVSFoliumViewerExampleNotebook` opened with `## ` (H2)
  instead of `# ` (H1); MyST / nbsphinx flagged them as
  "Document headings start at H2, not H1." Promoted the first
  markdown heading to H1 in each.
- **`eeAuthExamples.ipynb` — Section 9 (`Map.view()` integration)
  expanded.** New markdown intro explaining that the browser tab
  is pinned to the current tenant via the `/ee-api/t/<tenant>/`
  URL path segment (not the query string), plus a new inspection
  code cell that prints `eeCreds.proxy_url`, `eeCreds.current()`,
  and the exact URL `Map.view()` would open — so readers can see
  the wiring without hunting through JS.

## 2026.7.3 — July 13, 2026

### geeViz.eeAuth

- **Colab defaults to `auto` proxy mode.** The 2026.7.1 detached-mode
  default breaks Colab: the detached proxy runs in a separate process
  and doesn't see the project id resolved by `robust_init`'s
  interactive prompt in the notebook kernel, so every `/ee-api`
  request gets signed without `x-goog-user-project` and EE returns 403
  (the viewer chrome loads but layers don't render). In Colab the
  default is now `auto` (in-process daemon-thread proxy) so
  `sync_oauth_project` after the prompt actually reaches the proxy's
  tenant registry. Desktop users still get `detached` by default;
  Colab users who want detached can opt in with
  `GEEVIZ_EEAUTH_MODE=detached` (typically after setting the project
  explicitly before importing geeViz).
- **`sync_oauth_project` now covers ADC entries.** In Colab and other
  ADC-based environments (Cloud Run, GCE, Cloud Build) the credential
  is registered as an ADC entry, not OAuth. The old sync helper only
  touched OAuth entries, so after `robust_init` prompted the user for
  a project the ADC entry's `project_id` stayed empty and downstream
  proxy calls signed without `x-goog-user-project`. ADC entries now
  get the same treatment; SA entries are still left alone (their
  `project_id` from the JSON key is authoritative). The cached
  `Credentials` object is also invalidated so the next mint re-applies
  `with_quota_project` against the new value.
- **Skip stub GCE-metadata ADC in Colab.** In fresh Colab kernels
  `google.auth.default()` hands back `compute_engine.Credentials`
  because google-auth's env probe thinks it's on GCE, but
  `metadata.google.internal` doesn't resolve. Every proxy request
  then tried to mint a token, hit 404, retried five times with
  exponential backoff, and emitted a wall of `TransportError`
  tracebacks before `ee.Authenticate(auth_mode='colab')` finished. A
  quick 0.5s ping to the metadata server now gates ADC registration
  — if the credentials are GCE-typed but the metadata server isn't
  reachable, the ADC entry isn't registered and the noisy retry loop
  disappears. Real GCE hosts (which respond in single-digit ms) are
  unaffected.
- **Success message on `robust_init`.** Every non-fast-path success
  now prints one unconditional line — e.g.
  `geeViz: Earth Engine ready (project='geeviz-geo-agent', source=interactive-auth-prompted-project)`
  — so the user gets clear confirmation the bootstrap worked,
  especially valuable after the Colab flow's mix of google-auth
  retries and the interactive project prompt. The already-initialized
  fast path stays silent so repeat imports don't spam the output.

### Notebooks

- **Github + Colab badge headers on every notebook.** Six examples
  (`eeAuthExamples`, `esri_integration`, `googleMapsLib_examples`,
  `report_generation_examples`, `thumbLib_examples`,
  `weather_forecast_examples`) were missing the standard "see
  sources / open in Colab" badge header at the top. All 24 example
  notebooks now carry the badges so anyone browsing the repo can
  jump straight into a runnable Colab session.

## 2026.7.2 — July 13, 2026

### geeViz.eeAuth

- **Project prompt retries on failure.** When the auto-resolution chain
  fails and `robust_init` has to prompt for a project id, a typo or an
  inaccessible project no longer instantly kills the import. The user
  now gets three attempts, only the working value is cached, and stale
  cached projects (deleted, access revoked, wrong Google account signed
  in) are invalidated on failure instead of poisoning future runs. Also
  addresses the common Colab pattern of authenticating with one Google
  account and typing a project owned by another.

### geeViz.geeView

- **Colab map render fix (detached-mode proxy port).** When Colab users
  explicitly opt into `GEEVIZ_EEAUTH_MODE=detached`, `Map.view()` now
  exposes the eeCreds proxy's actual port (parsed from `ee_proxy_url`,
  e.g. 8889) via `google.colab.kernel.proxyPort` instead of the default
  `self.port` (8001). Under the 2026.7.1 detached-mode default the
  in-process daemon server on 8001 wasn't started, so the old code was
  asking Colab to proxy a port where nothing was listening and the
  iframe rendered blank.

## 2026.7.1 — July 13, 2026

### MCP Server slimmed to 12 tools (21 → 12)

- **Consolidation, not deletion.** Report tools, examples, list_assets,
  and track/cancel_tasks were removed as dedicated tools; their
  functionality is now reached through the pre-loaded REPL aliases
  (`rl.build_report()`, `ee.data.listOperations()`, etc.) inside
  `run_code`. One execution primitive plus a rich namespace ended up
  more flexible than a proliferation of narrow wrappers.
- **Unified search.** `search_functions`, `get_reference_data`, and
  `examples` collapsed into a single `search_geeviz` tool that handles
  keyword lookup, signature retrieval, module listing, reference-dict
  values, and example script source. Backed by an AST-based module
  index — zero imports until a runtime value is actually requested.
- **Same feature coverage, fewer decisions for the agent.** Every
  workflow that worked before still works; there's just one obvious
  entry point per capability. The `run_code` REPL comes with `ee`,
  `Map`, `gv`, `gil`, `sal`, `cl`, `tl`, `rl`, `gm`, `edwLib`,
  and `save_file` pre-loaded.

### geeViz.eeAuth

- **Colab / hosted-notebook auth fix.** `robust_init` no longer hardcodes
  `auth_mode='localhost'` in the interactive fallback. In Colab (detected
  via `google.colab` in `sys.modules`) it uses `auth_mode='colab'` so
  the silent `google.colab.auth` flow runs; in Kaggle it uses
  `auth_mode='notebook'` for the URL/code-paste flow. Desktop dev keeps
  `auth_mode='localhost'`. Fixes `from geeViz.geeView import *`
  hanging in Colab when EE creds weren't already present (localhost from
  the Colab VM can't reach the user's browser).
- **Per-thread `httplib2.Http` cache** for `TenantAwareHttp` on top of
  the 2026.6.1 thread-safety fix — cuts fan-out warm-up latency for
  repeat parallel `getMapId` calls (e.g., iterated `Map.testLayers()`).

### geeViz.outputLib.reports

- **`Report.generate()` now raises on section failures by default.**
  Prior behavior — errors were caught per-section, stored on
  `sec.error`, and embedded as red boxes inside the rendered HTML.
  Fine for a human reviewer who reads the final report; invisible
  to an agent calling `rl.build_report(...).generate()` inside
  `run_code`, which just saw a normal string return. Now
  `generate()` raises `rl.ReportGenerationError` when any section
  (or the executive summary) errored, carrying `.errors` (per-section
  detail), `.failed_sections` (titles), and `.html` (the partial
  report that would have been written). Successful section results
  are cached, so a debug-and-retry cycle only recomputes the fixed
  sections. Pass `generate(strict=False)` for the legacy
  silent-partial behavior.
- **New `Report.errors` property** exposes the same per-section
  error dict for callers who opted into `strict=False` — poll it
  after `generate()` returns.
- **Executive-summary errors** are now tracked separately (under
  key `"__summary__"` in `errors`) rather than swallowed into the
  fallback string.

### geeViz.geeView

- **`Map.view()` cache-buster** — appends a per-call `?v=<timestamp>`
  in detached-proxy mode. Fixes the notebook regression where a second
  `Map.view()` after `Map.clearMap()` kept showing the previous cell's
  layers because the browser tab's URL hadn't changed and Chrome
  silently focused the existing tab without reloading. Each call now
  navigates to a unique URL, forcing a full re-fetch of the embedded
  `run_js` so the displayed layers always match the current
  ``mapCommandList``.

### Packaging

- **Explicit eeAuth deps in `install_requires`** — ``fastapi``,
  ``uvicorn``, ``httpx``, ``httplib2``, ``google-auth``. Previously
  pulled transitively; declaring them keeps ``import geeViz.eeAuth``
  robust to a future transitive drop by ``earthengine-api`` or
  ``google-cloud-storage``.

## 2026.6.2 — June 23, 2026

- **`eeAuth` and `outputLib` package inclusion bug fix

## 2026.6.1 — June 10, 2026

### geeViz.eeAuth — detached default + same-port `/geeView`

- **`GEEVIZ_EEAUTH_MODE=detached` is the new default** (was `auto`). The
  proxy is spawned as a separate `python -m geeViz.eeAuth` background
  subprocess identified by a state file at
  `<tmp>/.geeViz_eeauth_proxy.json` (PID, port, tenant fingerprint,
  version). It survives the calling script's exit, so multi-`Map.view()`
  scripts no longer block, and re-running the same script reuses the
  existing proxy without re-spawning or re-authenticating. Override with
  `GEEVIZ_EEAUTH_MODE=auto` for the legacy in-process daemon-thread
  proxy (dies with the script).
- **Same-port architecture** — the detached proxy now mounts the
  geeView static tree at `/geeView/*` on the same port as `/ee-api/*`
  (8889 by default). The browser tab loads from
  `http://127.0.0.1:8889/geeView/` and makes EE calls back to
  `http://127.0.0.1:8889/ee-api/t/<tenant>/v1/...` on the same origin.
  No daemon-thread HTTP server, no CORS hop, no port juggling.
- **Path-prefix tenant routing** — the FastAPI proxy (`eeAuth.server`)
  now parses `/ee-api/t/<tenant>/<rest>`, strips the prefix, and routes
  the request as that tenant. The legacy daemon-thread server used to
  own this responsibility; moving it onto the FastAPI proxy is what
  unblocks the same-port architecture above. A bare `/ee-api/t/<tenant>`
  (no trailing segment) returns `204` as a tenant-ack ping.
- **Thread-safe `TenantAwareHttp`** — the EE SDK's shared HTTP transport
  now uses per-thread `httplib2.Http` instances (via `threading.local()`).
  Parallel `getMapId` fan-out — for example `Map.testLayers()` with its
  `ThreadPoolExecutor(max_workers=8)` — no longer hits the
  `'NoneType' object has no attribute 'close'` /
  `WinError 10038: not a socket` socket race that the previous
  single-instance transport produced.
- **Clean Windows spawn** — the detached subprocess now uses
  `CREATE_NO_WINDOW` (0x08000000) instead of `DETACHED_PROCESS`. The
  brief cmd-window flash that appeared on first `Map.view()` is gone.
- **Standalone runner mounts `/geeView`** — `python -m geeViz.eeAuth`
  now mounts both `/ee-api/*` and `/geeView/*` on its listening port,
  so a Cloud-Run-deployed proxy can serve a `Map.view()` export the same
  way the auto-spawned local proxy does. Default port aligned to `8889`
  (the agent UI uses `8888`, so they coexist).

### Map.view()

- **Detached by default** — `Map.view()` defaults to
  `GEEVIZ_EEAUTH_MODE=detached`, opens the browser to
  `<proxy_base>/geeView/`, and returns immediately (no `time.sleep(3)`
  to keep an in-process daemon alive). The browser tab is fully
  self-sufficient and survives script exit.
- **Skips the in-process daemon HTTP server** when running against a
  detached proxy. `_ensure_server(self.port)` is only called for Colab,
  Workbench/Cloud Run `/proxy/<port>/` deployments, and the legacy
  fallback path.
- **Skips `_set_ee_api_upstream`** in detached mode — the page is
  same-origin to `/ee-api/`, so no reverse-proxy hook is needed.
- **Multi-`Map.view()` scripts** — each call writes a per-session
  `runGeeViz.js` and opens a tab; the script can exit before the
  browser finishes loading and the detached proxy continues serving.

### Documentation

- **`examples/eeAuthExamples.ipynb` refreshed** — TL;DR, Section 1
  (zero-config), Section 9 (`Map.view()` integration with the new
  same-port architecture), Section 10 (added the `detached` mode and
  the full four-mode comparison table), Section 11 (in-process vs
  detached lifecycle, state-file inspection), Section 13 (standalone
  CLI on port 8889 with both header-based and path-prefix tenant
  examples), and the Quick Reference table all updated.
- **Sphinx docs** — `eeAuthExamples` notebook now appears under a new
  "Authentication & Multi-Tenant Proxy" section in `examples.rst`. The
  `modules.rst` eeAuth prose rewritten to reflect the detached default,
  same-port architecture, path-prefix routing, and thread-safe
  transport. New "Authentication & Multi-Tenant Proxy" section added
  to `overview.rst`.

## 2026.5.1 — May 29, 2026

### geeViz.eeAuth (new package)

- **Multi-tenant EE auth proxy** — a single Python process can now serve
  Earth Engine on behalf of many service accounts concurrently, bypassing
  the `ee.Initialize()` global-credential limitation. `Map.view()`
  auto-starts the proxy on first use; multi-credential workflows use
  `eeCreds.addCreds(...).use("<name>")` to switch tenants in-process.
- **`EECreds` class** — discover, register, switch, and introspect
  credential entries. Singleton `eeCreds` is the main entry point.
- **`eeCreds.discover()` env-var autodetection** — finds whatever
  credentials are present: `$GOOGLE_APPLICATION_CREDENTIALS`,
  `~/.config/earthengine/credentials`, gcloud ADC, `$GEE_SERVICE_ACCOUNT_B64`,
  per-tenant `$GEE_<NAME>_SERVICE_ACCOUNT`, and the new keyless paths
  below. Idempotent — safe to call repeatedly.
- **`eeCreds.robust_init()`** — the canonical EE bootstrap. Decision
  tree: try eeAuth proxy → EE refresh token → ADC fallback → interactive
  `ee.Authenticate`. Replaces the bespoke env-var dance previously
  scattered across consumers.

### Keyless authentication paths (security: no SA keys on disk)

- **`eeCreds.addADC()`** — register the runtime's Application Default
  Credentials as a tenant entry. On Cloud Run with an attached service
  account, on GKE with workload identity, or on AWS via Workload Identity
  Federation, this is the path that boots the proxy without any JSON key.
- **`eeCreds.addImpersonation(target_email, name)`** — mint tokens by
  impersonating a target service account at request time via
  `google.auth.impersonated_credentials`. No key material held; the
  runtime's ADC source must hold `roles/iam.serviceAccountTokenCreator`
  on the target.
- **WIF (Workload Identity Federation) support** — `external_account`
  credential JSON (from `gcloud iam workload-identity-pools create-cred-config`)
  is recognized by `_classify` and routes through the ADC path. Use for
  AWS-hosted agents that federate into GCP.
- **`GEE_<NAME>_SA_EMAIL=<email>` env-var pattern** — discover keyless
  per-tenant impersonation from env. Coexists with the legacy
  `GEE_<NAME>_SERVICE_ACCOUNT=<b64>` keyed pattern. Optional companion
  `GEE_<NAME>_PROJECT=<id>` overrides the quota project per tenant.
- **Bare SA-email auto-routing** — `eeCreds.addCreds("svc@p.iam.gserviceaccount.com", "name")`
  detects the email shape and routes to `addImpersonation` so the same
  one-liner registers both keyed and keyless tenants.

### MCP Server

- **`_init_ee_credentials` replaced** with `geeViz.eeAuth.robust_init()`.
  ~60 lines of bespoke SA-key/inline-JSON/ADC dispatching collapse to one
  call that handles every discovery source uniformly (B64, per-tenant SA
  env vars, WIF, impersonation, ADC). Standalone MCP usage (e.g. Claude
  Code via stdio) and chat-UI proxy mode both work without changes.
- **Project derivation from `GEE_SERVICE_ACCOUNT_B64`** in proxy mode —
  decodes the SA JSON's `project_id` directly when `$GEE_PROJECT` isn't
  set, eliminating a translation env var.

### geeViz.esriLib (new module)

- **Esri Feature Service integration** — query, download, and convert
  ArcGIS Online / Portal feature services into `ee.FeatureCollection`
  objects. Bridges the ArcGIS data layer with geeViz / Earth Engine
  analysis workflows.
- **`docs/esri-integration-design.md`** — architecture and conversion
  patterns between Esri JSON, GeoJSON, and EE.
- **`examples/esri_integration.ipynb`** — worked examples.

### outputLib.themes (new module)

- Centralized chart theming primitives shared across
  `outputLib.charts` and `outputLib.reports`.

### Testing

- **`geeViz/eeAuth/tests/`** — new package: `test_eeCreds.py`,
  `test_discovery_and_modes.py`, `test_library.py`. Covers WIF,
  impersonation, ADC fallback, env-var discovery, and the new keyless
  shapes end-to-end.
- New `geeViz/tests/`: `test_add_tile_layer.py`,
  `test_apply_theme.py`, `test_esriLib.py`, `test_export_layer_json.py`,
  `test_no_adk_template_collisions.py`, `test_search_geeviz_repl.py`,
  `test_auto_date_format.py`, `test_continuous_histogram.py`,
  `test_empty_chart_detector.py`, `test_multi_output_reducer.py`.

### Examples

- **`examples/eeAuthExamples.ipynb`** — walks through single-credential
  usage, multi-credential workflows, the proxy lifecycle, and the
  keyless paths above.

### geeView, getImagesLib, getSummaryAreasLib, outputLib

- Misc improvements, bug fixes, and chart/report polish across modules
  (see commit log for details).

## 2026.4.2 — April 21, 2026

### geeView

- **`Map.view()` display logic reworked**: Notebooks now default to IFrame only (no extra browser tab). Scripts default to browser only. If one is explicitly set, only that one opens. Both can be enabled by setting both to `True`.
- **`Map.testLayers()` autoViz validation**: When `autoViz: True`, validates that image bands have matching `<bandName>_class_values/names/palette` properties. Returns error (not just warning) when no band has class properties — the map will break without them. Also detects orphaned properties set for wrong band names.

### outputLib.charts

- **`save_chart_html()` simplified**: Removed `deepcopy` and theme re-application that was corrupting Plotly binary data (`bdata`). Now uses `fig.write_html()` directly. Removed `theme`, `sankey`, `bg_color`, `font_color` params (charts are already themed by `summarize_and_chart`).
- **`_safe_write_file` encoding fix**: Now uses `encoding="utf-8"` for text writes, fixing `UnicodeEncodeError` on Windows (cp1252) for characters like `→`.

### outputLib.thumbs

- **GIF date labels larger**: `date_font_size` now defaults to 1.4× `label_font_size` (was equal), making year labels more prominent than scalebar ticks.
- **Pydoc fixes**: Corrected `crs` default (EPSG:3857, not None), `inset_on_map` default in `generate_filmstrip` (False, not True), and documented missing params (`burn_in_geometry`, `geometry_outline_color`, `clip_to_geometry`, etc.).

### MCP Server

- **`run_code` `stream_stdout` param**: New `stream_stdout=True` option streams print output to a file that the agent frontend can poll in real-time. Default `False` (backward compatible).
- **Agent instructions updated**: `search_datasets` and other MCP tools are now documented as tools (not Python functions) in COMMON MISTAKES to prevent `NameError` in `run_code`.

## 2026.4.1 — April 15, 2026

### MCP Server — Map Test Action and Tool Fixes

- **`map_control(action="test")`** — new action that captures a PNG of the geeView map via headless Chrome DevTools Protocol (CDP). Returns `tile_errors` (HTTP 4xx/5xx on EE tile URLs) and `console_messages` (JS errors/warnings) for programmatic error detection. Used as an internal quality gate: agents call `test` before `view`, fix any tile errors silently, then show the clean map to the user. Requires `websocket-client` (`pip install websocket-client`); falls back to simple `--screenshot` if not installed. Screenshot PNGs are saved to `generated_outputs/` with timestamps.
- **Restored `@app.tool` decorators** for `cancel_tasks` and `get_streetview` — both were defined but not exposed as MCP tools since the 27→21 consolidation
- **Updated all MCP documentation** — tool counts, stale tool name references (`get_api_reference`, `view_map`, `get_thumbnail`, `extract_and_chart`, `geocode`, etc.) updated to current names across `mcp/README.md`, `mcp/agent-instructions.md`, `mcp.rst`, `geeViz.mcp.server.rst`, and `server.py` help text


### Map Viewer — file:// Support (No HTTP Server Required for Scripts)

- **`Map.view()` now opens `geeView/index.html` directly via `file://` URL** in plain Python scripts — no HTTP server, no subprocess, no port management. The access token and project id are passed via the same `?accessToken=…&projectID=…` URL query string the viewer has always used.
- **In notebooks (VS Code, Jupyter)**, `Map.view()` spins up a lightweight in-process threaded `http.server` (daemon thread) for iframe display, since VS Code's webview blocks `file://` in iframes. The server auto-picks a free port if the preferred one is held by another process.
- **`run_local_server()` rewritten** — replaced `subprocess.Popen(['python', '-m', 'http.server'])` with an in-process `ThreadingTCPServer`. No more subprocess management, orphan PIDs, or chdir side effects.
- **`buildgeeViz.py` patches for `file://` compatibility** — the build script now applies three targeted edits to the viewer assets: (1) replaces the XHR-based `$.getScript()` runtime loader in `lcms-viewer.min.js` with a `document.createElement('script')` DOM loader that works under `file://`; (2) strips the dead `require(...)` Node fallback from `changeDetectionLib.js`; (3) fixes the protocol-relative jQuery-UI CSS URL (`//code.jquery.com/...` → `https://code.jquery.com/...`).
- **New method: `Map.refresh()`** — re-runs the last `view()` call with a freshly minted access token.
- **Backward compatible.** Existing example scripts and notebooks that call `Map.view()` work unchanged. `Map.port`, `Map.proxy_url`, `IS_COLAB`, `IS_WORKBENCH`, `run_local_server()`, `isPortActive()` all still exist.

### Sankey Charts — Direct D3 Rendering (no Plotly)

- **`chart_type='sankey'`** is now the preferred way to request Sankey diagrams (replaces `sankey=True`)
- **New function: `chart_sankey_d3()`** — builds D3 Sankey HTML directly from `prepare_sankey_data()` output, skipping Plotly entirely
- `summarize_and_chart()` now returns a **dict** (`{"df": ..., "chart": ...}`) instead of a tuple. Sankey returns `{"df": ..., "chart": sankey_html, "matrix": ...}`. All thumbnail/GIF/filmstrip functions now return `{"bytes": ..., "format": "png"|"gif", "html": ...}` instead of `{"thumb_bytes": ...}` or `{"gif_bytes": ...}`
- `summarize_and_chart(chart_type='sankey')` returns `sankey_html` as a self-contained D3 HTML string with native SVG `linearGradient` links
- **New function: `sankey_iframe()`** — wraps sankey HTML in a `data:text/html;base64` iframe for Jupyter notebook display
- `transition_periods` now uses flat year lists `[1990, 2000, 2024]` instead of nested ranges `[[1990,1995], [2000,2005]]`
- Removed old `chart_sankey()` (Plotly builder) and `_sankey_to_html_plotly()` — all sankey rendering is now pure D3
- Download filename for sankey PNG reflects the chart title

### Chart Improvements

- **`band_names` accepts strings** — `summarize_and_chart`, `zonal_stats`, `get_obj_info`, and `auto_viz` now accept `band_names='Land_Use'` or `'NDVI,NBR'` (comma-separated) in addition to lists. Strings are automatically split into lists.
- **`max_x_tick_labels`** (default 10) and **`max_y_tick_labels`** params on `chart_time_series`, `chart_multi_feature_timeseries`, and `summarize_and_chart` — auto-thins tick labels using nice strides (1, 2, 5, 10, 20, 50...)
- **`%` suffix** on y-axis tick labels when `y_label` contains `%` (e.g. "% Area")
- **X-axis dead space fix** — `range` constrained to `[min - 0.5, max + 0.5]` for integer axes
- **`class_visible`** now works for multi-feature time series subplots and grouped bar/donut charts (was only applied to single-geometry charts)
- **Download filename** for Plotly charts reflects the chart title (patched `fig.show()` and `fig.to_html()` with `toImageButtonOptions`)

### Thumbnail Improvements

- **Expanded EE region** for basemap compositing — EE thumbnail request now covers the same geographic extent as the basemap (including padding margin), eliminating the gap where only basemap showed
- **CRS-aware north arrow** — `crs` parameter now propagated through `_assemble_with_cartography` so grid convergence angle is computed and the arrow rotates for projected CRS
- **CRS-aware inset map** — extent indicator drawn as a projected polygon (not axis-aligned rectangle) when using projected CRS like EPSG:5070
- **Multi-feature grid inset fix** — inset now uses union of all feature bounds; grid expands vertically when legend fills the column to make room for inset below
- **Uniform cell sizing** — grid cells use max width/height across all frames, centered with padding (different-shaped features no longer cut off)
- **`clip_to_geometry`** now works for multi-feature grids (was always clipping)
- **`ee.Feature` / `ee.Element` support** — `fc.first()` (returns `ee.Element`) now works in `generate_thumbs()`, `summarize_and_chart()`, and all thumbnail functions
- **`auto_viz` fix** — `red/green/blue` band names no longer hardcode `min:0, max:255`; properly delegates to `auto_viz_continuous` for data-driven stretch

### Roads Data Expansion (`getSummaryAreasLib`)

- **`getRoads(area, source='tiger', year=2024)`** — expanded from TIGER 2016 only:
  - `source='tiger'` (default): TIGER roads, years 2012-2025 via community catalog
  - `source='grip'`: GRIP4 (Global Roads Inventory Project), 7 regional shards with road type classification (`GP_RTP`: 1=Highway through 5=Local)

### MCP Server Optimization (27 → 21 tools)

- **Removed 5 tools** that were thin wrappers around `run_code`: `get_thumbnail`, `extract_and_chart`, `edw_query`, `geocode`, `get_catalog_info` — saves ~3,200 tokens of schema overhead per conversation. `inspect_asset` now includes catalog metadata (title, provider, keywords, viz params)
- Use `run_code` with `tl.generate_thumbs()`, `cl.summarize_and_chart()`, `edwLib.query_features()`, `gm.geocode()` instead
- **Agent instructions rewritten** — 414 lines → 59 lines (86% reduction) as compact rules + pitfalls format; no examples (model uses `get_api_reference` and `examples` tools on demand)
- **`inspect_asset` rewrite** — catalog metadata (`date_range`, `title`, `provider`) extracted from `ee.data.getInfo` instantly (no compute); live queries (count, bands, dates) run in daemon threads with 10-second timeout; never hangs on large collections like S2
- **`run_code` idle timeout** — timeout now tracks inactivity (no new stdout/stderr output for 120s) instead of total elapsed time; long-running code that keeps printing can run indefinitely

### New Example Files

- **`WeatherNextTimeLapse.py`** — deterministic (Graph) and 64-member ensemble (WeatherNext 2) forecast time lapses with temperature, wind, precipitation, MSLP, 500 hPa height, SST, and ensemble spread
- **`weather_forecast_examples.ipynb`** — comprehensive notebook covering GFS, ECMWF IFS, WeatherNext Graph, and WeatherNext 2 with model comparison difference maps
- Consolidated `getSummaryAreasExampleNotebook.ipynb` into `getSummaryAreas_thumb_and_chartingLib_examples.ipynb` — every section now includes thumbnail generation with varied basemaps, CRS projections, inset maps, geometry burn-in, and Sankey charts alongside time series

### Documentation

- **`modules.rst`**: Added `outputLib.themes` module; updated outputLib as parent section
- **`overview.rst`**: Added `edwLib`, `googleMapsLib`, `outputLib.themes`; updated autosummary list
- **`examples.rst`**: Added sections for charting/thumbnails, reports, Google Maps, weather forecasts, pandas integration
- **`installation.rst`**: Expanded API key setup with step-by-step instructions for both Gemini and Google Maps Platform keys
- **`mcp.rst`**: Updated tool count to 22; added 40+ example questions across 9 categories
- **`README.md`**: Updated MCP tools table, API key instructions, tool count
- **`superSimpleGetS2`** docstring: marked as preferred S2 function
- **`getSentinel2Wrapper`** docstring: marked as deprecated in favor of `superSimpleGetS2`
- Removed stale `mcp/edw.py` (duplicate of `edwLib.py`)

## 2026.3.3 —  March 26, 2026

### New: Google Maps Platform Integration (`geeViz.googleMapsLib`)

- **New module: `geeViz.googleMapsLib`** — 24 functions for ground-truthing remote sensing analysis using Google Maps Platform APIs:
  - **Geocoding**: `geocode()`, `reverse_geocode()`, `validate_address()`
  - **Places**: `search_places()`, `search_nearby()`, `get_place_photo()`
  - **Street View**: `streetview_metadata()`, `streetview_image()`, `streetview_panorama()` (auto-stitches 360° from multiple frames), `streetview_html()`
  - **AI Analysis**: `interpret_image()` (Gemini vision for object inventory), `label_streetview()` (bounding box detection), `segment_image()` / `segment_streetview()` (SegFormer pixel-level semantic segmentation)
  - **Elevation**: `get_elevation()`, `get_elevations()`, `get_elevation_along_path()`
  - **Environment**: `get_air_quality()`, `get_solar_insights()`, `get_timezone()`
  - **Maps & Roads**: `get_static_map()`, `snap_to_roads()`, `nearest_roads()`
- Requires `MAPS_PLATFORM_API_KEY` in `.env` with desired APIs enabled
- Available as `gm` in the MCP REPL namespace

### New: USFS EDW Library (`geeViz.edwLib`)

- **New module: `geeViz.edwLib`** — USFS Enterprise Data Warehouse REST API client, moved from `mcp/edw.py` to root package for direct use in scripts/notebooks
  - `search_services()`, `get_service_info()`, `get_layer_info()`, `query_features()`
  - Keyword aliases (e.g. "riparian" finds stream/watershed services)
  - Available as `edw` in the MCP REPL namespace

### MCP Server Consolidation (38 → 27 tools)

- **Consolidated tool groups** to reduce tool count and simplify the API:
  - `view_map` + `get_map_layers` + `clear_map` → **`map_control(action=...)`**
  - `export_to_asset` + `export_to_drive` + `export_to_cloud_storage` → **`export_image(destination=...)`**
  - `delete_asset` + `copy_asset` + `move_asset` + `create_folder` + `update_acl` → **`manage_asset(action=...)`**
  - `get_example` + `list_examples` → **`examples(action=...)`**
  - `get_version_info` + `get_namespace` + `get_project_info` → **`env_info(action=...)`**
  - `search_edw` + `get_edw_service_info` + `query_edw_features` → **`edw_query(action=...)`**
- **New MCP tools**: `get_streetview`, `search_places`, `geocode` (now uses Google Geocoding API with Nominatim fallback)
- **Tool annotations**: All 27 tools have `ToolAnnotations` (readOnlyHint, destructiveHint, openWorldHint) for client auto-approval
- `geocode` tool now uses Google Geocoding API for accurate street address resolution, with OSM Nominatim as fallback

### Report Improvements

- **`chart_types` parameter** on `add_section()` — accepts a list of chart types per section (e.g. `["sankey", "line+markers"]`). Replaces the old `sankey=True` + `sankey_only` pattern
- **Snake-case API**: `addSection` → `add_section`, `generateTable` → `generate_table`, `generateChart` → `generate_chart`
- `line_width` and `marker_size` parameters on `chart_time_series()` and `summarize_and_chart()`

### Thumbnail & Chart Fixes

- **Inset map colors** match geometry outline/fill colors (no longer hardcoded red)
- **Legend swatch** correctly renders fill color opacity (RRGGBBAA hex alpha)
- **Scalebar/north arrow** show without basemap in `generate_thumbs()`
- **Donut chart margins** tightened
- **Projected geometry basemap fix** — `_get_bounds_4326` transforms to EPSG:4326 before fetching tiles
- `simple_buffer()` added to `getSummaryAreasLib` — lightweight metric square buffer in EPSG:3857

### Documentation

- **5 new RST docs**: `geeViz.edwLib`, `geeViz.googleMapsLib`, `geeViz.outputLib.charts`, `geeViz.outputLib.thumbs`, `geeViz.outputLib.reports`
- Updated `modules.rst` with all new modules
- Updated MCP server RST with current 27 tools
- **New example notebooks**: `report_generation_examples.ipynb` (6 report scenarios), `mcp_with_gemini_tutorial.ipynb` (MCP + Gemini agent loop)

## March 23, 2026

### New: Output Library Reorganization & New Features (`geeViz.outputLib`)

- **Moved `geeViz.chartingLib` to `geeViz.outputLib.charts`.** The old `geeViz.chartingLib` import path continues to work for backward compatibility, but new code should use `from geeViz.outputLib import charts as cl`.
- **New module: `geeViz.outputLib.thumbs`** — thumbnail, GIF, filmstrip, and map+chart generation with basemaps, legends, scalebars, and inset maps. Available as `tl` in the MCP REPL namespace.
- **New module: `geeViz.outputLib.reports`** — automated report generation with parallel EE data fetching, charts, tables, thumbnails, GIFs, and LLM narratives. Available as `rl` in the MCP REPL namespace.
- **New chart types in `summarize_and_chart`:** `"donut"` (thematic pie/donut chart) and `"scatter"` (scatter plot with optional thematic colouring via `thematic_band_name`).
- **New function: `generate_map_chart()`** in `geeViz.outputLib.thumbs` — produces a combined map thumbnail + chart (bar/donut/scatter for `ee.Image`, delegates to GIF for `ee.ImageCollection`).
- **Gamma support in `auto_viz` continuous stretch** — new `gamma` parameter (default 1.6) for gamma correction when auto-detecting continuous visualization parameters.

## March 12, 2026

### New Features

### New: Summary Areas Library (`geeViz.getSummaryAreasLib`)

- **New module: `geeViz.getSummaryAreasLib`**
  15 functions returning filtered `ee.FeatureCollection` objects for common study and summary areas. Every function accepts an `area` parameter (`ee.Geometry`, `ee.Feature`, or `ee.FeatureCollection`) and returns spatially filtered results.
    - **Admin boundaries:** `getAdminBoundaries(area, level=0|1|2|3|4)` — unified function supporting countries (0), states (1), counties (2), sub-districts (3), localities (4). Sources: geoBoundaries v6 (default, official), FAO GAUL 2015, FAO GAUL 2024, FieldMaps humanitarian. Companion `getAdminNameProperty(level, source)` returns the correct name column for any source.
    - **US-specific:** `getUSStates()`, `getUSCounties()` (with `state_fips`/`state_abbr` filters), `getUSUrbanAreas()`, `getUSCensusBlocks()`, `getUSBlockGroups()`, `getUSCensusTracts()`
    - **USFS units:** `getUSFSForests()`, `getUSFSDistricts()` (with `forest_name`/`region` filters), `getUSFSRegions()`
    - **Infrastructure:** `getRoads()`, `getBuildings()` (VIDA Combined, Microsoft, or Google Open Buildings sources)
    - **Protected areas:** `getProtectedAreas()` (with `iucn_cat`/`desig_type` filters)
    - **MCP integration:** Available as `sal` in the MCP REPL namespace; discoverable via `get_api_reference` and `search_functions`
    - **Example notebook:** `getSummaryAreasExampleNotebook.ipynb` demonstrates all 15 functions with map visualization, area charting, and inline chartingLib charts

### New: Multi-Feature Time Series Charting (`chartingLib`)

- **Per-feature time series subplots:** `summarize_and_chart()` now supports passing `feature_label` with an `ee.ImageCollection` and a multi-feature `ee.FeatureCollection`. Produces one time series subplot per feature using a single `reduceRegions` call on the stacked image (efficient — one EE call regardless of feature count).
    - Returns `(dict, Figure)` where `dict` is `{feature_name: DataFrame}` with per-feature time series data
    - Works for both thematic data (frequencyHistogram) and continuous data (mean/median)
    - New functions: `chart_multi_feature_timeseries()`, `_pivot_multi_feature_timeseries()`
    - For `ee.Image` + `feature_label`, the existing grouped bar chart behavior is unchanged

### Bug Fixes

#### `chartingLib` Fixes

- **`frequencyHistogram` + `reduceRegions` on multi-band images:** Fixed `Reducer.setOutputs: Need 1 output names` error when using `frequencyHistogram` with stacked (multi-band) images. `setOutputs()` is now only called for single-band images; for multi-band images, EE auto-names outputs by band name.
- **Feature property leakage in grouped bar charts:** Fixed a bug where numeric feature properties (e.g. `ALAND`, `AWATER` from census tracts) were included as chart columns alongside image band values. The fallback column detection now prefers columns matching image band names before falling back to all numeric columns.

---

# geeViz 2026.3.2 Release Notes

## March 5, 2026

### New Features
### New: Inline Zonal Summary & Charting Library (`geeViz.chartingLib`)

- **New module: `geeViz.chartingLib`**
  A Python pipeline for running zonal statistics on `ee.Image` / `ee.ImageCollection` objects and producing Plotly charts directly in notebooks. Mirrors the logic from the geeView JS frontend area-charting module.
    - **Auto-detection:** Automatically detects thematic vs. continuous data from `class_values`, `class_names`, `class_palette` image properties.
    - **Chart types:** Time series (line/stacked), bar, and Sankey transition diagrams.
    - **Area formats:** Percentage, Hectares, Acres, or raw Pixels.
    - **Sankey charts** return both a source-target-value table and a transition matrix (from-class × to-class).
    - **Convenience function:** `summarize_and_chart()` orchestrates zonal stats and charting in one call.
    - **Lower-level API:** `get_obj_info()`, `zonal_stats()`, `chart_time_series()`, `chart_bar()`, `chart_sankey()`, `prepare_sankey_data()` for full control.
    - **Color ramp interpolation:** Palette colors are interpolated across all bars when fewer colors than classes are provided.
    - **`palette` parameter:** Matches the map-based `palette` convention for specifying custom colors.

### Bug Fixes

#### `chartingLib` Fixes

- **`.toBands()` prefix handling:** Fixed a bug in `prepare_for_reduction()` where non-mosaic ImageCollections (collections with fewer images than x-axis labels) failed to rename bands correctly. `.toBands()` prefixes each band with `system:index_`, which for real collections produces non-numeric prefixes like `LC09_038029_20230613_`. The cleanup code assumed numeric prefixes (`0_`, `1_`). Now pre-computes expected band names (`label----band`) and renames directly.
- **`copyProperties` in mosaic branch:** Added `.copyProperties(filtered.first())` to the mosaic path so that image properties (e.g. `class_values`, `class_names`, `class_palette`) are preserved through the mosaic operation. Mirrors the JavaScript area-charting implementation.
- **Sankey chart transition periods:** Fixed `p2 = transition_periods[i]` → `transition_periods[i + 1]` in the Sankey data preparation. The copy-paste error caused each period to be compared to itself rather than the next period, producing empty/incorrect transition diagrams.

#### Local Server Port Collision

- **`geeViz.geeView`**: Fixed a bug where the local HTTP server could be running on the correct port but serving files from a different directory (e.g. a previous project or working directory). The old code only checked `isPortActive(port)` and assumed the existing server was correct. Now `_ensure_server(port)` tracks the server's PID and root directory in a temp-file state (`~/.geeViz_server_{port}.json`), detects mismatched directories, and automatically kills and restarts the server when needed.
- **`geeViz.foliumView`**: Updated to use the same `_ensure_server()` helper for consistent server management.

### MCP Server Enhancements

- **Tool consolidation (33 → 30 tools):** Merged and renamed tools to reduce agent confusion:
    - `save_script` + `save_notebook` → **`save_session`** — single tool with `format="py"` or `format="ipynb"` parameter.
    - `list_functions` merged into **`search_functions`** — accepts optional `query` and/or `module` params. `module` only = list all functions in that module (old `list_functions`), `query` only = search all modules, both = search within a specific module.
    - `get_collection_info` merged into **`inspect_asset`** — new optional `start_date`, `end_date`, and `region_var` params. For ImageCollections, returns `image_count`, `first_date`, `last_date`, and per-band details.
    - `get_dataset_info` renamed to **`get_catalog_info`** — clarifies distinction from `inspect_asset` (live EE metadata vs. STAC catalog documentation).
- **New MCP tool: `extract_and_chart`** (replaces `zonal_summary`)
  Wraps `chartingLib.summarize_and_chart` for AI agents — returns both a structured `summary` (JSON records) and `chart_html` (interactive Plotly HTML). Auto-detects thematic vs. continuous data, supports bar, time series, Sankey, and grouped bar charts.
- **`run_code` improvements:**
    - Now `async` with progress heartbeats every ~10 seconds to keep MCP client connections alive during long-running computations.
    - Static analysis warnings: detects `.getInfo()` inside loops and `.getInfo()` on collections without `.limit()` before execution.
    - Improved timeout messages with actionable hints.
    - Properly restores `sys.stdout`/`sys.stderr` after timeout to prevent stream capture leaks.
- **`chartingLib` added to introspectable modules:** `get_api_reference` and `search_functions` now support the `chartingLib` module.
- **`run_code` subprocess:** Server process is now launched with a list argument (`subprocess.Popen(list)`) instead of `shell=True` for improved safety and reliability.

### Documentation Updates

- **`geeViz.chartingLib`** added to Sphinx API reference (`modules.rst`), module overview (`overview.rst`), and homepage feature list (`index.rst`).
- **MCP server docs (`mcp_server.rst`):** Replaced verbose inline tool reference with a link to the auto-generated API docs at `geeViz.mcp.server`. Added "Why MCP?" comparison table showing 22 common GEE tasks and how the MCP tools compare to a vanilla coding agent.
- **MCP tool count updated** to 30 across all docs, agent instructions, README, and module docstrings.
- **Agent instructions (`agent-instructions.md`, `copilot-instructions.md`):** Added Rule 7 (never write manual `reduceRegion` — use `extract_and_chart` or `chartingLib.summarize_and_chart`). Fixed chartingLib example pattern to return structured JSON + HTML instead of `fig.show()`/`print(df)` which are useless to agents. Updated tool list and descriptions for consolidated tools.
- **`README.md`:** Added `chartingLib` to Key Features and MCP tools table. Updated tool count and descriptions.
- **`release-notes.md`:** Added this release entry.

### Example Notebook Updates

- **`examples/areaChart_examples.ipynb`:** Now demonstrates both map-based (`canAreaChart`) and inline (`chartingLib`) approaches side-by-side for every example, including NLCD mode, MTBS Burn Severity, LCMS multi-band, composites time series, and version comparison with Sankey.

### Build & Packaging

- **`setup.py`:** Added `plotly` and `mcp` to `install_requires`. Added `mcp/*.py` and `mcp/*.md` to `package_data`. Centralized version string management across all `__init__.py` files. Added `mcp` and `stac` keywords.
- **`LICENSE`:** Updated copyright year to 2026.

---

# geeViz 2026.3.1 Release Notes

## March 1, 2026

### Major Update: MCP Server Integration

- **New: MCP (Model Context Protocol) server package**  
  Introduced `geeViz.mcp`, a robust, modular backend server for advanced Earth Engine workflows. The MCP server exposes 33 execution and introspection tools via an HTTP/REPL interface, enabling:
    - Interactive code execution in a persistent Python REPL.
    - Introspection and browsing of live GEE assets (images, collections, tables, folders).
    - Dynamic querying of Earth Engine API signatures and assets.
    - Bulk asset management: copy, move, delete, export, upload, and inspect.
    - Visualization endpoints: generate satellite thumbnails (PNG/GIF), region previews, time series charts, and more for faster AI-assisted exploration.
    - Enhanced error handling and unified tool endpoints.
    - Easy integration with Python, LLMs, or browser-based/UIs for rapid interactive development.

  The MCP server enables powerful, scriptable workflows and is usable both as a standalone server and a module. See `geeViz/mcp/README.md` for setup and tool documentation.


---
# geeViz 2025.10.2 Release Notes

## October 14, 2025


### Bug fixes

- `geeViz.cloudStorageManager` project_id in `geeViz.geeView` missing. Updated to use the `ee.data._get_state()` method.

---
# geeViz 2025.10.1 Release Notes

## October 14, 2025


### Bug fixes

- `geeViz.geeView.rubustInitializer` auto auth bug fix. Integrated new `ee.data._get_state()` state management method for getting the current project.

---
# geeViz 2025.4.3 Release Notes

## April 18, 2025

### New Features

- **Additional Pydocs** - Added/updated pydocs throughout the package.

---

# geeViz 2025.4.3 Release Notes

## April 17, 2025

### Bug fixes

- `geeViz.geeView.simpleSetProject` bug fix.It would not create the credential directory if it did not already exist. Not it creates it.

---

# geeViz 2025.4.2 Release Notes

## April 17, 2025

### New Features

- **`assetManagerLib.ingestFromGCSImagesAsBands()`** - New function for ingesting multiple images as bands of a single Earth Engine image asset. Takes a list of dictionaries, with each dictionary containing a key/value for the 'gcsURI' of the input image, and optional keys/values for 'pyramidingPolicy', 'noDataValue', and 'bandName'.
- **`assetManagerLib.uploadToGEEAssetImagesAsBands()`** - New wrapper function for uploading multiple images to gcloud and manifesting them as bands of a single Earth Engine image asset. Takes a dictionary in which keys are file paths to each image, and values are dictionaries with keys/values for 'pyramidingPolicy', 'noDataValue', and 'bandName'.
- **`assetManagerLib.uploadTifToGCS()`** - New function for uploading individual tifs to gcloud. Uses `gcloud storage` command instead of `gsutil`.
- **`assetManagerLib.create_image_collection()`** - This function now takes an optional dictionary as a parameter that defines properties to set for the image collection.

- **`examples.LCMS_Levels_Viewer_Notebook` updates** - In preparation for the v2024.10 release of LCMS, the new levels that will be published are now supported and better-documented in the notebook.

---

# geeViz 2025.4.1 Release Notes

## April 16, 2025

### New Features

- **geeView area charting chartType setting** - Can now set the `chartType` (`vizParams["areaChartParams"]["chartType"]`) to "line", "bar", "stacked-line", and "stacked-bar". This is only used for `ee.ImageCollection` objects. For `ee.Image` objects, the chartType is always "bar". See pydoc for `Map.addLayer`, `Map.addTimeLapse`, and `Map.addAreaChartLayer` for details.

### Bug fixes

- `geeViz.geeView.robustInitializer()` bug fix. Method was broken by some updates to the GEE API returning a number for a project ID. This is now fixed. The new `robustIntializer()` is far simpler than the prior versions, so it will not handle as many scenarios as before. The overall stability should be improved though.

---

# geeViz 2025.3.6 Release Notes

## March 31, 2025

### Bug fixes

- `geeViz.geeView` `Map.view()` bug fix for Google Colab. Updated to handle the new Google Colab proxy syntax. The old syntax should work still should they switch back in the future.

---

# geeViz 2025.3.5 Release Notes

## March 31, 2025

### New Features

- **New `examples.LANDTRENDRVizNotebook.ipynb`** - Adapted the `examples.LANDTRENDRViz.py` script to a notebook format. Use this to learn how to take exported LandTrendr outputs and visualize them and use them for change detection.

- **New `examples.Aboveground_Biomass_Viewer_Notebook.ipynb`** - Shows how the visualize and summarize the ESA CCI Global Forest Above Ground Biomass dataset using `geeViz`.

---

# geeViz 2025.3.4 Release Notes

## March 21, 2025

### Bug fixes

- `geeViz.geeView` auto-authentication/initialization create directory bug fix. In the past, this module would always try to create a `.config` directory. Not it only does this if it is using the standard refresh token auth method.

- `examples.LANDTRENDRWrapperNotebook` study area bug fix. The `studyArea` was called on before it was declared in the first example. This was removed.

---

# geeViz 2025.3.3 Release Notes

## March 17, 2025

### New Features

- `getImagesLib.simpeWaterMask` `elevationImagePath` `ee.Image | ee.ImageCollection` support - You can now provide an `ee.Image` or `ee.ImageCollection` type input for the `elevationImagePath` parameter. Previously, this had to be a string. Since some elevation assets are `ee.ImageCollections` supporting additional types was needed.

---

# geeViz 2025.3.2 Release Notes

## March 5, 2025

### New Features

- **`getImagesLib.superSimpleGetS2` `studyArea` Optional** - You no longer have to provide a studyArea for the `getImagesLib.superSimpleGetS2` method. This allows for global, map extent focused applications to use this method. When using this method, only the `.filterDate` method will render an output, so `startJulian` and `endJulian` are ignored. Ideally the `startDate` and `endDate` will suffice.

- **`examples.LANDTRENDRWrapperNotebook.ipynb` Improved Markdown** - Improved the markdown for the `examples.LANDTRENDRWrapperNotebook.ipynb` for easier understanding of what is going on.

- **`examples.timeLapseExample.py` Updates** - Updated the assets and visualization methods in `examples.timeLapseExample.py`

---

# geeViz 2025.3.1 Release Notes

## March 3, 2025

### Bug fixes

- `geeViz layer indexing` simplification. Layer IDs are always the name with an index only appended if a layer with the same name was already added.

---

# geeViz 2025.1.6 Release Notes

## January 23, 2025

### Bug fixes

- `phEEnoViz` module bug fix with colormap causing method to fail. See `examples.phEEnoVizWrapper.py` for a working example of how to use this powerful tool.

- `Map.turnOnAutoAreaCharting` bug fix. Occasionally the tool would not activate when this method was called. This method has now been moved to a setTimeout callback, so it should activate more consistently.

---

# geeViz 2025.1.5 Release Notes

## January 23, 2025

### New Features

- **geeviz.org logo integration** - Updated geeViz branding logo

---

# geeViz 2025.1.4 Release Notes

## January 15, 2025

### New Features

- **geeviz.org migration** - Migrated documentation from https://gee-community.github.io/geeViz/build/html/index.html to the geeviz.org domain

---

# geeViz 2025.1.3 Release Notes

## January 9, 2025

### Bug fixes

- `examples.LCMS_Levels_Viewer_Notebook` import of the `lcmsLevelLookup` script path didn't work in Colab. Not it's imported as part of the geeViz module.

---

# geeViz 2025.1.2 Release Notes

## January 9, 2025

### New Features

- **getImagesLib.getClimateWrapper Exporting** - You can now specify whether you'd like to export to Google Cloud Storage or an Earth Engine asset with the `getImagesLib.getClimateWrapper` function.

---

# geeViz 2025.1.1 Release Notes

## January 9, 2025

### New Features

- **LCMS Classification Levels Notebook** - A new example notebook showing how to crosswalk (remap) LCMS classes to various levels of thematic detail is now provided in `examples.LCMS_Levels_Viewer_Notebook`. This is intended to serve as a companion to a forthcoming LCMS manuscript.

---

# geeViz 2024.11.4 Release Notes

## November 26, 2024

### Bug fixes

- Follow-on bug fix - Area Charting Tools UI is not only visible if an area charting layer has been added to the map. Previously, the UI would show an older area charting UI if no area charting layers had been added the map.

---

# geeViz 2024.11.3 Release Notes

## November 25, 2024

### New Features

- **geeViz.geeView Enanced Image Area Charting** - geeViz.geeView aera charting for thematic images now tries to optimize the orientation of the bar chart based on the length of the class labels. Any chart with long class label lengths will be a horizontal bar chart. Short class labels will remain a vertical bar chart as it has always been. Also, the Plotly `autoMargin` functionality is now used for these charts.

### Bug fixes

- Area Charting Tools UI is not only visible if an area charting layer has been added to the map. Previously, the UI would show an older area charting UI if no area charting layers had been added the map.

---

# geeViz 2024.11.2 Release Notes

## November 11, 2024

### New Features

- **geeViz.geeView Enanced Error Handling** - geeViz.geeView no longer falls back on default credentials if loading fails. The error messaging has been improved to help users navigate likely causes of loading failures so they can continue to use the same credentials on the Python and javaScript side (using a temporary access token) of geeViz.geeView.

### Bug fixes

- `examples.CCDCVizNotebook` endYear bug fix. The endYear was set to 2024, but needed set to 2022 for the first few code blocks.

---

# geeViz 2024.11.1 Release Notes

## November 8, 2024

### New Features

- **CCDC Feathering Documentation** - The ability to combine two CCDC raw array `ee.Image` outputs for prediction and change detection has been streamlined and included in examples `examples.CCDCVizNotebook` and `examples.CCDCViz`, along with improved Pydocs.

- **Annual NLCD Example Notebook** - New notebook for Annual NLCD has been included in `examples.Annual_NLCD_Viewer_Notebook`. This notebook walks through how to visualize, summarize, and explore Annua NLCD products.

---

# geeViz 2024.10.1 Release Notes

## October 25, 2024

### New Features

- **geeView UI Layout Enhancements** - UI has had minor enhancements to improve use of space and alignment.

- **upload_to_gcs overwrite setting** - `assetManagerLib.upload_to_gcs` `overwite` parameter. By default, it is now set to `False`. This can be a breaking change since before it was unset, leaving it to essentially be `overwrite = True`.

- **cloudStorageManager new functions** - `cloudStorageManager.list_files`, `cloudStorageManager.bucket_exists`, and `cloudStorageManager.create_bucket` functions to facilitate various cloud storage tasks.

- **geeView query yLabel setting** - Can now set the `yLabel` (`vizParams["queryParams"]["yLabel"]`) to label the y axis of a query chart. See pydoc for `Map.addLayer` and `Map.addTimeLapse` for details.

- **geeView minZoomSpecifiedScale** - Can now set min zoom level to start changing zonal stats reduction scale changes (`vizParams["areaChartParams"]["minZoomSpecifiedScale"]`). This is useful to avoid memory errors, but ideally, can be set to a lower zoom level if possible. See pydoc for `Map.addLayer` and `Map.addTimeLapse` for details.

---

# geeViz 2024.9.3 Release Notes

## September 20, 2024

### New Features

- **Doc updates** - Continued work improving Documentation website. Numerous function-wise examples added to the code.

- **GEE Palettes Integration** - Converted Gena's EE Palettes json to a Python script/module. Use the module as `import geeViz.geePalettes as palettes`

### Bug fixes

- `Map.addLayer` and `Map.addTimeLapse` functions now create a copy of the `viz` param dictionary. If you passed a dictionary, and then reused that in another layer call, the `layerType` key was then populated and wouldn't be updated, this resulting in an object type error. By creating a copy, the dictionary isn't changed outside the function.

---

# geeViz 2024.9.2 Release Notes

## September 18, 2024

### New Features

- **Doc updates** - Continued work improving Documentation website.

- **Simple Sentinel-2** - `getImagesLib.superSimpleGetS2` is a super lightweight function to get analysis-ready Sentinel-2 data integrating the cloudScore+ algorithm. This may be a better option than existing functions that support out-dated legacy methods that are no longer needed since cloudScore+ works so well.

---

# geeViz 2024.9.1 Release Notes

## September 6, 2024

### New Features

- **Doc updates** - Continued work improving Documentation website.

- **MapBiomas Example Rework** - The MapBiomas example script and notebook now integrate a full mosaic of all study areas and the ability to collapse to lower levels of the classification hiearchy.

---

# geeViz 2024.8.3 Release Notes

## August 28, 2024

### New Features

- **Doc updates** - Continued work improving Documentation website - logo bug fix..

---

# geeViz 2024.8.2 Release Notes

## August 28, 2024

### New Features

- **Doc updates** - Continued work improving Documentation website.

- **New and Updated Example Notebooks** - Global Landcover notebook added and updates to MapBiomas example notebook and script.

---

# geeViz 2024.8.1 Release Notes

## August 23, 2024

### New Features

- **Doc updates** - Continued work improving Documentation website. Notably integrating notebook examples into doc website.

### Bug fixes

- Function parameter reordering bug fix for `getImagesLib.getS2`

---

# geeViz 2024.7.1 Release Notes

## July 1, 2024

### New Features

- **CloudScore+ cs_cdf band support** - You can now utilize the `"cs_cdf"` band from the cloudScore+ algorithm in any of the Sentinel-2 image prep functions in the `getImagesLib` (`getS2`, `getProcessedSentinel2Scenes`, `getProcessedLandsatAndSentinel2Scenes`, `getSentinel2Wrapper`, `getLandsatAndSentinel2HybridWrapper`) by specifying `cloudScorePlusScore = "cs_cdf"`.

- **LayerType optimizing** - The specification of the `layerType` insize the visualization pareters in a `Map.addLayer` function is now largely unnecessary since an efficient object type method has been added.

### Bug fixes

- Area charting add layer bug fix for adding area chart layers without delcared object type.

---

# geeViz 2024.5.3 Release Notes

## May 15, 2024

### New Features

- **Larger Area Charts for Downloading** - Area charts no automatically scale by 2x for downloading

- **Sankey Charts Filtering** - Any class less than a specified percentage (`sankeyMinPercentage` - default : `0.5%`) won't be shown in the sankey chart. This helps clean up largely meaningless transitions from being shown.

- **Composite uploading support** - `assetManagerLib.uploadToGEEImageAsset` now supports composite uploading using the `"GSUtil:parallel_composite_upload_threshold` setting.

### Bug fixes

- Sentinel-2 QA bands being set to null instead of 0 since ~Feb 2024 bug fixed. QA bands are no longer required to have values for a pixel to be valid.

---

# geeViz 2024.5.2 Release Notes

## May 1, 2024

### Bug fixes

- Google Colab bug fix - earthengine-api changed `ee.oauth._in_colab_shell()` to `ee.oauth.in_colab_shell()`. Backward compatability supported for older function name.

---

# geeViz 2024.5.1 Release Notes

## May 1, 2024

### Bug fixes

- Area charting bug fixes and time lapse uneven dates slider bug fix.

---

# geeViz 2024.4.1 Release Notes

## April 4, 2024

### New Features

- **Area Charting Example Notebook** - There is now an area chart example notebook that walks through many examples of the available methods for charting zonal stats of ee images and imageCollections.

### Bug fixes

- Area charting bug fixes for various data types including thematic images.

---

# geeViz 2024.3.1 Release Notes

## March 22, 2024

### Bug fixes

- You can now use `Map.addLayer` or `Map.addTimeLapse` with an image collection where `"canAreaChart" : True` and `"reducer : ee.Reducer.frequencyHistogram()` but no `bandName_class_values`, `bandName_class_names`, `bandName_class_palette` are provided. Previously, this would not work.

- Fixed bug where `areaChartParams` `reducer` was not being handled properly for `Map.addTimeLapse` calls.

---

# geeViz 2024.3.1 Release Notes

## March 21, 2024

### New Features

- **Documentation for geeViz** - We are working on including docstrings and corresponding documentation. The site is located here: <https://gee-community.github.io/geeViz/build/html/index.html>

- **Map Layer area charting option** - Can now include any map layer for area summarizing using the `"canAreaChart" : True` inside the `viz` parameters dictionary. The `lcmsViewerExample.py` and new `mapBiomasViewerExample.py` include the area charting functionality.

- **Map Biomas Example** - There is an example of how to visualize and explore the Map Biomas land use / land cover datasets provided in `mapBiomasViewerExample.py`.

- **Linearly Interpolated Color Ramp** - A function to linearly interpolate a set of hex colors given a starting set of colors, and min and max values (`geeview.get_poly_gradient_ct`). This is useful for charting values.

### Bug fixes

- When querying layers, if `"autoViz" :True` or a `queryDict` is provided, but there is a queried value that is returned not found in that dictionary, the value will be shown instead. Previously, this would result in an error.

---

# geeViz 2024.2.3 Release Notes

## February 8, 2024

### New Features

- **Map Layer Drag Reordering Deactivation Option** - Can now deactivate layer reordering using `Map.setCanReorderLayers(False)`.

### Bug fixes

- Layer reordering with > 10 layers bug fixed. Sorting > 10 would sort 1,10,11,2,3,....etc. `geeVector` layerType is now frozen and cannot be reordered. This is because Google Maps API doesn't treat vector layers the same as raster overlays.Support for reordering vectors on the map is not supported.

---

# geeViz 2024.2.2 Release Notes

## February 7, 2024

### New Features

- **Map Layer Drag Reordering** - Can now reorder non-timelapse map layers by clicking and dragging the layer up or down. This feature still can be buggy depending on the underlying layer type.

- **CCDC output smart join method** - The `batchFeatherCCDCImgs` will take two time series of CCDC coefficients (typically created using `predictCCDC`), and linearly weight which coefficients are being used across a user-specified transition period (`featherStartYr`,`featherEndYr`). This allows for a smooth way of splicing together two sets of CCDC outputs with a generous overlapping time period. An example script of how to use this will be provided in a future release once this function solidifies a bit.

---

# geeViz 2024.2.1 Release Notes

## February 7, 2024

### Bug fixes

- The reducer in `batchSimpleLTFit` was hard-coded to `.max` for reducing any multi-image inputs for a given band/index. This resulted in nulls or errors in overlapping areas if LandTrendr arrays were being mosaicked. There is now a parameter `mosaicReducer` that can be set to handle overlapping values as you see fit. For array formatted outputs, it has to be `ee.Reducer.firstNonNull()` or `ee.Reducer.lastNonNull()` (default) since GEE doesn't handle array reductions well for imageCollection reductions.

---

# geeViz 2024.1.1 Release Notes

## January 19, 2024

### New Features

- **Improved cloudStorage Support** - Can now manage cloudStorage assets with the `cloudStorageManagerLib.py` module.

- **Improved `exportToCloudStorageWrapper`** - The `exportToCloudStorageWrapper` now can overwrite running tasks or existing cloudStorage blobs if `overwrite = True` is specified. Additionally, support for TFrecords is not handled.

- **geemap integration** - We are starting to use the `geemap` package when possible. There is a new example script `geeViz_and_geemap.py` that we will be building on to illustrate using geemap with geeViz. The first example illustrates how you would take a shapefile, use `geemap` to convert it to an ee object, and the use that in a `geeViz` workflow.

### Bug fixes

- If `ee.Initialize(project='someProjectID')` is called on prior to importing geeViz, that project will automatically be used

---

# geeViz 2023.12.6 Release Notes

## December 21, 2023

### New Features

- **Easier Colab Availability** - Colab links are now provided in each notebook in the examples folder.

### Bug fixes

- 'addLayer' Viz params `reducer` bug fix. When a reducer within a `viz` dictionary is passed to the map with a `addLayer` call more than once, geeViz would try to serialize it again resulting in an error. It now accepts it and assumes it's already been serialized.

---

# geeViz 2023.12.5 Release Notes

## December 21, 2023

### Bug fixes

- Fixed bug when `ee.oauth.get_credentials_path()` folder didn't exist already and geeViz tried to store the selected project within it. The folder is now created if it does not exist. This is needed when `ee.Authenticate` does not automatically make the folder.

---

# geeViz 2023.12.4 Release Notes

## December 21, 2023

### Bug fixes

- Fixed bug where project was not read in if ee was initialized outside of geeViz. `setProject` is run when geeView is imported which sets the `project_id` to the project provided in `ee.Initialize` if it was provided.

---

# geeViz 2023.12.3 Release Notes

## December 21, 2023

### New Features

- **Enhanced project support** - More robust handling of projects for authentication, as well as geeViz viewer authentication. The same project you are using in Python is now used in `geeView`.

### Bug fixes

- `geeView` query of collections with over 5000 image\*bands values would not query. Reverted to older getRegion-based query method.

---

# geeViz 2023.12.2 Release Notes

## December 8, 2023

### New Features

- **Color name support** - Colors for `vizParams` `palette` and `classLegendDict` can now be provided as standard w3 color name strings.

- **simpleLTFit batchSimpleLTFit multBy support** - Better support for ingesting landTrendr array vertex outputs that are multiplied by 10000 using the `multBy` parameter in the `simpleLTFit` `batchSimpleLTFit` functions. E.g. if the fitted vertex values were multiplied by 10000, set `multBy = 0.0001`.

---

# geeViz 2023.12.1 Release Notes

## December 4, 2023

### New Features

- **Simplified simpleLANDTRENDR** - the `simpleLANDTRENDR` function has been reworked to be more streamlined, but still provide the same functionality. Steps it uses are now available as stand-alone functions. These include the following new functions: `runLANDTRENDR, multLT, LTLossGainExportPrep, and addLossGainToMap` and the following previously existing functions: `simpleLTFit and convertToLossGain`. The `LANDTRENDRViz.py`, `LANDTRENDRWrapper.py`, and `LANDTRENDRWrapperNotebook.ipynb` examples have all been updated to utilize these reworked functions.

- **setQueryPrecision for Charting** - The precision of query outputs is now handled better. It can be changed by using the `Map.setQueryPrecision` function. Any floating point number will be constrained by the maximum of `chartPrecision` or `chartDecimalProportion*len(someFloatingPointNumber)`. The default is `3` and `0.25` respectively. E.g. if the number is `0.12345`, `max[3,ceiling(len(0.12345)*0.25)] = 3`, so the final number would be `0.123`.

- **setQueryDateFormat for Charting** - The date format can be changed by using the `Map.setQueryDateFormat` function or `queryDateFormat` property within the viz params for a `Map.addLayer` or `Map.addTimeLapse` call. E.g. if you want to only show the year in a chart, you'd put `Map.setQueryDateFormat('YYYY')` or if you need hours and minutes, `Map.setQueryDateFormat('YYYY-MM-dd HH:mm')`

### Bug fixes

- ImageCollection query bug when some pixels were null, but there was a `queryDict` provided is now fixed

---

# geeViz 2023.10.1 Release Notes

## October 31, 2023

### New Features

- **cloudScore+ For Sentinel-2** - cloudScore+ is now available for cloud and cloud shadow masking for Sentinel-2. It is available for all Sentinel-2 functions/wrappers/examples.

- **mosiac time lapses** - if an input imageCollection for an `addTimeLapse` call has multiple images per date, you can now have them mosaicked on-the-fly by using `{'mosaic':True}` in the viz parameters.

- **Reducers for imageCollections in addLayer** - When adding an imageCollection with `Map.addLayer`, you can now specify the reducer that is used to reduce the imageCollection to a single image to show on the map. Use `{'reducer':ee.SomeReducer()}` in the viz params.

### Bug fixes

- Improved Y axis label overcrowding image query charting robustness

---

# geeViz 2023.9.1 Release Notes

## September 20, 2023

### New Features

- **queryDict Chart Y Tick Labels** - Charting any imageCollection from a `Map.addLayer` or `Map.addTimeLapse` call will automatically use the `queryDict` `viz` parameter (e.g. `Map.addLayer(someLayer,{"queryDict":{1:"Trees",2:"Grass",3:"Water"}},"SomeLayerName")`) to label the Y axis ticks with class names. If class names are too long, they will be shortened. The max character length and the max characters per line in a Y axis tick label can be changed using `Map.setYLabelMaxLength` and `Map.setYLabelBreakLength` respectively.

### Bug fixes

- Improved array and mixed array and traditional image query charting robustness

---

# geeViz 2023.8.7 Release Notes

## August 24, 2023

### New Features

- **extractPointValuesToDataFrame** - `gee2Pandas.extractPointValuesToDataFrame` function extract values as a Pandas data frame. Will handle images or imageCollections automatically.

### Bug fixes

- Minor bug fixes

---

# geeViz 2023.8.6 Release Notes

## August 23, 2023

### New Features

- **imageArrayPixelToDataFrame** - `gee2Pandas.imageArrayPixelToDataFrame` function to easily visualize image array values as a Pandas data frame.
- **new_interp_date** - `changeDetectionLib.new_interp_date` experimental function to interpolate dates. This method is likely no faster than the previous method (`changeDetectionLib.linearInterp`), but does extrapolate in a more expected manner.

### Bug fixes

- Minor bug fixes

---

# geeViz 2023.8.5 Release Notes

## August 17, 2023

### New Features

- **setZoom** - `setZoom` function to set the zoom level of the map within `geeView.Mapper` . This functionality is also avail
  able in the `centerObject` function where the zoom level can optionally be set.

- **Date Interpolation now optional for annualizing CCDC** - `annualizeCCDC` and `getTimeImageCollectionFromComposites` functions now can have the linear interpolation turned off. Turning interpolation off will speed up creating outputs, but will result in null values where any date image data are missing.

### Bug fixes

- Minor bug fixes

---

# geeViz 2023.8.4 Release Notes

## August 10, 2023

### Bug fixes

- Minor bug fixes

---

# geeViz 2023.8.3 Release Notes

## August 9, 2023

### Bug fixes

- Minor bug fixes

---

# geeViz 2023.8.2 Release Notes

## August 7, 2023

### New Features

- **robust_featureCollection_to_df** - `robust_featureCollection_to_df` in the `gee2Pandas` module will handle large featureCollection conversion to a Pandas dataframe.

### Bug fixes

- `create_asset` will now handle nested folder creation with `recursive = True`.

---

# geeViz 2023.8.1 Release Notes

## August 3, 2023

### New Features

- **verbose parameter** - `getImagesLib` Landsat and Sentinel 2 functions now can be less verbose when run. This helps clean up the console. By defult, `verbose = False`.

### Bug fixes

- `assetManagerLib` has improved error handling when various operations cannot be performed - likely due to permissions errors.

---

# geeViz 2023.7.5 Release Notes

## July 28, 2023

### New Features

- **geeView Vertex AI Workbench lab Support** - `geeView` can now be used in Vertex AI notebooks. This support may present authentication bugs depending on how you are authenticating to GEE. You must provide the URL from which the lab is being run as the variable `proxy_url`. This can be set as `MapObject.proxy_url = https://code-dot-region.notebooks.googleusercontent.com/`. If it is not provided before a `.view()` call is made, the user will be prompted to enter it. This attribute will stick with the Map object for the duration of its existence.

---

# geeViz 2023.7.4 Release Notes

## July 24, 2023

### New Features

- **exportToAssetWrapper overwrite support in wrappers** - `getLandsatWrapper`, `getSentinel2Wrapper`, and `getLandsatAndSentinel2HybridWrapper` can now be run with `overwrite` set to `True` or `False`. It will check to see if the asset either exists or is currently being exported. If set to `True` it will stop the export or delete the existing asset and restart it. If set to `False`, it will not start the export.

---

# geeViz 2023.7.3 Release Notes

## July 24, 2023

### New Features

- **exportToAssetWrapper overwrite support** - `exportToAssetWrapper` can now be run with `overwrite` set to `True` or `False`. It will check to see if the asset either exists or is currently being exported. If set to `True` it will stop the export or delete the existing asset and restart it. If set to `False`, it will not start the export.

---

# geeViz 2023.7.2 Release Notes

## July 19, 2023

### New Features

- **geeView Colab Support** - `geeView` can now be used in Google Colab notebooks. This support may present authentication bugs depending on how you are authenticating to GEE.

---

# geeViz 2023.7.1 Release Notes

## July 14, 2023

### New Features

- **More robust authentication and initialization** - There are many inconsistencies being introduced for authenticating and initializing to GEE. A new function (`geeViz.geeView.robustInitializer`) attempts to handle some of these scenarios. It is not solid though and if you know your particular environment setup, it is best to authenticate and initialize before importing geeViz. There is also difficulty with authenticating on the javaScript client for geeView for some GEE accounts. If the javaScript instance fails to initialize, it will fall back on an existing auth proxy. Since this uses an account different from your own, it may result in errors in accessing assets for viewing in geeView. This can be solved by sharing assets publically.

### Bug fixes

- `changeDetectionLib.getTimeImageCollectionFromComposites` has been updated to fill in a blank image for any missing years and allow a year range to be specified to allow for interpolation and extrapolation. The unused parameters of `startJulian` and `endJulian` are no longer used.

---

# geeViz 2023.6.1 Release Notes

## June 13, 2023

### New Features

- **Folium based simple GEE object viewer** - A Folium-based GEE object viewer is now available (`foliumView.py`). The syntax is very similar to geeView. It tends to load faster, but be quite buggy with layer ordering, and lacks the ability to query values of layers. Examples are provided to help use it (`examples\foliumViewer.ipynb`,`examples\geeViewVSFoliumViewerExampleNotebook.ipynb`)

- **GEE2Pandas data science helper module** - A new module geared toward going between traditional data formats (csv, Excel, dbf, json, etc) and GEE (`gee2Pandas.py`). Functions are provided to go from a Pandas dataframe to GEE featureCollection and back. An example is provided (`examples\gee2PandasExample.ipynb`)

### Bug fixes

- geeView layer names with odd characters are now accepted (`e.g. / \ `)

---

# geeViz 2023.4.1 Release Notes

## April 11, 2023

### New Features

- **Default Query Output Location Change** - Query outputs are not placed in the side pane where the legend is located.

  - To back to using the default on-map infoWindow use: `Map.setQueryToInfoWindow()`

- **Improved Upload To Asset Capabilities** - Can now upload tifs to gee assets more easily and handle setting a number of paramters (`assetManagerLib.uploadToGEEImageAsset`) and (`assetManagerLib.ingestImageFromGCS`)

### Bug fixes

- All MODIS collections have been updated to newer 061 collections
- Query box size now reflects the chosen scale

---

# geeViz 2023.3.1 Release Notes

## March 22, 2023

### New Features

- **Query (inspector) parameters setting** - Can now set the click query projection (crs, scale and/or transform), and query box color parameters.
  - To set the query box color: `Map.setQueryBoxColor(hexColor)`
  - To set the query crs: `Map.setQueryCRS(crs)`
  - To set the query transform: `Map.setQueryTransform(transform)` (note: this will set the scale to null)
  - To set the query scale: `Map.setQueryScale(scale)` (note: this will set the transform to null)
- **LandTrendr Array Image Support** - Can now export the raw LandTrendr array image output for vertex values only as well as RMSE (`changeDetectionLib.rawLTToVertices`). Functions to annualize vertex-only array images are now available too (`changeDetectionLib.simpleLTFit` with `arrayMode = True`. See the LANDTRENDRWrapper example script for a detailed example.
- **Improved `Map.addLayer` error handling** - Any ee object added using a `Map.addLayer` call that fails to load will show an error and not load onto the map rather than stopping the entire map from loading.

### Bug fixes

- Landsat and Sentinel 2 resampling was set for all bands, including the qa bits. This resulted in speckling around the edges of cloud, cloud shadow, and snow masks. Now, the resampling method remains nearest neighbor for any qa bit band for both Landsat and Sentinel 2. This bug does not exist for MODIS since all masking is performed on continuous bands or the underlying mask of the thermal data.

---

# geeViz 2023.1.3 Release Notes

## January 26, 2023

### New Features

- **Join Collections Using Different Field Names** - The `joinFeatureCollections` and `joinCollections` functions now optionally support different field names between the two collections. e.g. `joinFeatureCollections(primaryFC,secondaryFC,'primaryFieldName','secondaryFieldName')`

---

# geeViz 2023.1.2 Release Notes

## January 18, 2023

### New Features

- **Sentinel 1 Basic Processing** - Integration of Guido Lemoine's shared GEE adaptation of the Refined Lee speckle filter from [this script](https://code.earthengine.google.com/2ef38463ebaf5ae133a478f173fd0ab5) as coded in the SNAP 3.0 S1 Toolbox. This can be found in the `getS1` function in the `getImagesLib`.

---

# geeViz 2023.1.1 Release Notes

## January 17, 2023

### Bug fixes

- When loading very large/complicated outputs into geeView, it would often not load the first time. This bug has been fixed to the page properly loads even with very large/complicated EE objects. It can take a while to load the page however.

---

# geeViz 2022.7.2 Release Notes

## July 8, 2022

### New Features

- **geeView Service Account Options** - geeView can now utilize a service account key for authentication to GEE. For general guidance for setting up a service account, [see this](https://developers.google.com/earth-engine/guides/service_account). This service account must be white-listed using [this tool](https://signup.earthengine.google.com/#!/service_accounts). Be sure to download the json key to a local, unshared location. To have geeView use a service account key, specify the path to the json key file as the `serviceKeyPath` attribute of the Map object (e.g. `Map.serviceKeyPath = r"c:\someFolder\keyFile.json"`). This will cause geeView to use that file to gain access to GEE instead of using the default persistent refresh token. If it fails, geeView will then try to use the persistent credential method.

---

# geeViz 2022.7.1 Release Notes

## July 6, 2022

### New Features

- **geeView Token Options** - geeView now tries to utilize the default location GEE refresh token instead of a proxy. It cannot use private keys from service accounts. You can however specify a different location of the refresh token from the default (e.g. `Map.accessToken = r'C:\someOtherFolder\someOtherPersistentCredentials`).
  If geeView fails to find a refresh token, it will fall back to utilizing the default proxy location. If that fails, a message will appear. It is best to simply ensure there is a working refresh token available (most easily created using `earthengine authenticate` or `ee.Authenticate()`).

---

# geeViz 2022.6.1 Release Notes

## June 17, 2022

### New Features

- **Landsat 9 Integration** - Landsat 9 is now included for all Collection 2 Landsat functions.
- **Specify geeView port** - You can now specify which port to run geeView through by specifying it (e.g. `Map.port = 8000`).

---

# geeViz 2022.4.2 Release Notes

## April 15, 2022

### New Features

- **GFS Time Lapse Example** - A new example script illustrating how to visualize the GFS forecast model outputs.

### Bug fixes

- When running geeViz from inside certain IDEs (such as IDLE), the use of sys.executable to identify how to run the local web server would hit on the pythonw instead of python executable. If it finds a pythonw under the sys.executable variable, it now forces it to use the python (without a w).

---

# geeViz 2022.4.1 Release Notes

## April 1, 2022

### New Features

- **Improved LandTrendr decompression method.** - A new function called batchSimpleLTFit has been added to the changeDetectionLib to help provide a faster method for decompressing the LandTrendr stacked output format into a usable time series image collection with all relevant metrics from LandTrendr.

- **LANDTRENDRViz example script.** - A new example script that demonstrates how to visualize and post-process LandTrendr outputs.

- **Common projection info dictionary** - In order to help organize common projections, a common_projections dictionary is now provided in the getImagesLib module.

### Bug fixes

- Landsat Collection 2 Level 2 data often have null values in the thermal band. Past versions of geeViz forced all bands to have data (some earlier scenes would have missing data in some but not all bands). This would result in null values in all bands over any area the new Collection 2 surface temperature algorithm could not compute an output. In order to handle this, for Landsat data, all optical bands found in TM, ETM+, and OLI sensors (blue, green, red, nir, swir1, swir2) must have data now, thus allowing a null thermal value to carry through.
- Related to the bug fix above - The medoidMosaicMSD function would still result in a null output if any band had null values. In order to fix this, the min reducer was swapped with the qualityMosaic function and the sum of the squared differences is multiplied by -1 so the qualityMosaic function can function properly. This results in almost the identical result. As the sum of the squared differences approaches 0 for more than a single observation for a given pixel, this method can result in a slightly different pixel choice, but should not make any substantive differences in the final composite.
- Removed the layerType key from the vizParams found within the getImagesLib. If imageCollections were added to the map using addLayer or addTimeLapse, they would not render if using any of the vizParams (vizParamsFalse and vizParamsTrue) since the layer type was explicitly specified as geeImage. You can add the relevant property back into those dictionaries in order to speed up map rendering. Example scripts that make use of these vizParams dictionaries have been updated. e.g. getImagesLib.vizParamsFalse['layerType']= 'geeImage' or getImagesLib.vizParamsFalse['layerType']= 'geeImageCollection'

---

# geeViz 2022.2.1 Release Notes

## February 14, 2022

### New Features

- **LCMAP_and_LCMS_Viewer Script and Notebook.** - A new example viewer that displays two US-wide change mapping products - Land Change Monitoring, Assessment, and Projection (LCMAP) produced by USGS and the Landscape Change Monitoring System (LCMS) produced by USFS. Land cover, land use, and change outputs from each product suite are displayed for easy comparison. The notebook facilitates the comparison by bringing in each set of data from the data suites into separate viewers.

- **Task Tracking in Example Scripts** - While the taskManagerLib is not new, the task tracking functionality available within that module was added to the example scripts that export data.

### Bug fixes

- Fixed bug in pulling CCDC most recent loss and gain year out. It now behaves in a similar manner as the most recent loss and gain outputs.

---

# geeViz 2021.12.1 Release Notes

## December 27, 2021

### New Features

- **Time Lapse Charting** - Any time lapse that is visible will be charted if double-clicked using "Query Visible Map Layers" tool.
- **Landsat Collection 2 Support** - Landsat Collection 2 is now used by default for all getLandsat methods. Collection 1 is still available by specifying landsatCollectionVersion = 'C1'. Specify 'C2' (which is the default) if you would like to use Collection 2.

---

# geeViz 2021.11.1 Release Notes

## November 19, 2021

### New Features

- None

### Bug fixes

- Fixed endDate for all filterDate calls. Previously, it had been assumed this was inclusive of the day of the endDate, when the GEE filterDate method is exclusive of the day of the endDate. Since the assumption is that all dates specified are inclusive, the current fix involves advancing all endDates provided to any filterDate function by 1 day.

---

# geeViz 2021.10.1 Release Notes

## October 15, 2021

### New Features

- **LANDTRENDRWrapper Notebook** - A new example of how to use LandTrendr in a Jupyter Notebook format. This is very similar to the script, but provides a little more detail of the resources available to run LandTrendr.

### Bug fixes

- geeView would not work in ArcPro Miniconda Python builds (and perhaps others). The new fix addresses this issue and allows it to run from Miniconda Python builds based from ArcPro

---

# geeViz 2021.8.1 Release Notes

## August 26, 2021

### New Features

- **Smarter GEE initialization** - All modules that call upon ee.Initialize will now check to ensure GEE hasn't already been initialized. If it hasn't, it will initialize.

### Bug fixes

- GEE occasionally wouldn't recognize an imageCollection as such when adding a TimeLapse. An explicit cast to imageCollection was now made.

---

# geeViz 2021.7.2 Release Notes

## July 28, 2021

### New Features

- **Back and foward view buttons** - Users can go backward and forward views within the geeView viewer.

### Bug fixes

- Fixed export wrappers exporting empty areas with GEE update to export methods

---

# geeViz 2021.7.1 and prior Release Notes

### New Features

- **Notebook examples** - Several examples are now available in an interactive notebook format under the examples module.
- **CCDC updates** - Updates to CCDC annualizing functionality.
- **MODIS Processing** - Similar pre-processing (cloud and cloud shadow masking) functionality that has been available for Landsat and Sentinel 2 now available for MODIS data.
