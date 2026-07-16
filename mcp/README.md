# geeViz MCP Server

MCP (Model Context Protocol) server for the **geeViz** Python package. Provides 12 execution and introspection tools that give AI agents structured, live access to Google Earth Engine and the geeViz API.

## Why MCP?

An AI coding agent already has powerful general-purpose tools -- it can search the web, read local files, grep source code, and write scripts. So why add an MCP server on top of that?

The core problem is that **Earth Engine is a live, authenticated cloud platform**. General-purpose tools can read _about_ GEE but cannot _interact_ with it. The MCP server bridges that gap by giving the agent 12 purpose-built tools that execute against your authenticated GEE session and the actual geeViz codebase. The table below compares what each approach can do for common GEE tasks:

| Task | Vanilla coding agent (web search, grep, file read) | geeViz MCP server |
|------|-----------------------------------------------------|-------------------|
| **Look up a geeViz function signature** | Grep source files or search the web -- may find outdated docs, wrong version, or miss internal helpers | `search_geeviz(name="func")` uses AST inspection on the _installed_ code -- always returns the real signature and docstring |
| **Find which module has a function** | `grep -r` across all .py files, manually parse results | `search_geeviz` searches every geeViz module in one call, or lists functions in a specific module -- structured results, no runtime imports |
| **Discover example scripts** | `find` + `cat` and guess the filename | `search_geeviz(module="examples")` lists example scripts; add `name="GFSTimeLapse"` to get the full source |
| **Look up reference data (band mappings, viz params, projections)** | Grep for the constants and hope you found the current version | `search_geeviz(module="getImagesLib", name="common_projections")` returns the live value; same tool serves signatures AND reference dicts |
| **Check what bands a dataset has** | Search the GEE data catalog website, parse HTML, hope the page is current | `inspect_asset` calls `ee.data.getInfo()` on the _live_ asset -- returns real bands, CRS, scale, date range, properties |
| **Get image count and date range for a filtered collection** | Write and run a script with multiple `getInfo()` calls | `inspect_asset` with optional start_date/end_date/region_var returns count, date range, band info in one structured call |
| **Search for GEE datasets by keyword** | Web search, browse the GEE catalog, read blog posts | `search_datasets` searches 700+ official and community datasets offline (24h-cached catalog), returns ranked results with asset IDs |
| **Get detailed dataset metadata (bands, classes, scale/offset)** | Find and parse the STAC JSON page for the dataset | `inspect_asset` fetches the full STAC record and returns structured band info, class descriptions, viz params |
| **Test a code snippet** | Write to a file, run it in a terminal, read stdout/stderr | `run_code` executes in a persistent REPL namespace (like Jupyter) with `ee`, `Map`, `gv`, `gil`, `sal`, `cl`, `tl`, `rl` pre-loaded -- variables persist across calls, errors are returned inline |
| **Build up an analysis incrementally** | Each script run starts fresh; agent must manage state manually | `run_code` namespace persists -- build up variables, test each step, inspect intermediate results with `env_info(action="namespace")` |
| **See what variables exist after several code steps** | Re-read the script, mentally track assignments | `env_info(action="namespace")` returns all user-defined variables with type and repr -- no `getInfo()` calls |
| **Visualize results on a map** | Write code to call `Map.view()`, tell the user to open a browser | `map_control(action="view")` opens the geeView map and returns the URL directly |
| **Get a visual preview of an image** | Write a `getThumbURL` script, fetch the image, save to disk | `tl.generate_thumbs()` in `run_code` produces publication-ready PNG thumbnails with basemap, legend, and scalebar |
| **Sample pixel values or chart zonal statistics** | Write `reduceRegion` scripts, detect thematic vs continuous data, choose reducers, build Plotly figures manually | `cl.summarize_and_chart()` in `run_code` handles point sampling, time series, bar charts, and Sankey diagrams in one call -- auto-detects data type, picks the right reducer, and returns a DataFrame + chart |
| **Geocode a place name to a GEE geometry** | Call a geocoding API, manually construct `ee.Geometry` | `geeviz_search_places` returns coordinates and place details; `sal` in `run_code` provides boundary polygons for counties, states, forests, protected areas, etc. |
| **See what a place looks like on the ground** | Call the Street View API manually, handle keys, decode responses | `get_streetview` returns a Street View image URL for any lat/lon -- useful for ground-truthing thematic classifications |
| **Export an image to an asset** | Write export code, look up `pyramidingPolicy` options, handle overwrite | `export_image(destination="asset")` wraps geeViz's exporter with validation, overwrite support, and pyramiding policy |
| **Export to Drive or Cloud Storage** | Write export boilerplate, remember required parameters | `export_image(destination="drive"\|"cloud")` handles all params with sensible defaults (COG enabled, etc.) |
| **Manage assets (copy, move, delete, permissions)** | Write 5-10 lines of `ee.data.*` calls per operation | `manage_asset(action="copy"\|"move"\|"delete"\|"create"\|"update_acl")` -- one call with validation |
| **Read the current map or a generated HTML/chart file** | Open the file, parse the HTML for the layers, guess what's rendered | `view_output` returns the current map URL AND the file contents on disk (chart HTML, thumbnails, etc.) |
| **Save the session as a reusable script** | Manually copy code blocks from the conversation | `save_session` exports the full `run_code` history as a `.py` or `.ipynb` file |

In short: a vanilla agent can _read about_ GEE; the MCP lets it _use_ GEE. Every tool returns structured data rather than text to parse, handles authentication and error cases, and exposes domain-specific parameters (reducers, CRS, pyramiding policies, STAC metadata) that a general-purpose search would never surface reliably.

## Requirements

- Python 3.x
- geeViz (`pip install geeViz`) -- the [mcp](https://pypi.org/project/mcp/) SDK is included as a dependency automatically
- Authenticated Earth Engine session (run `ee.Authenticate()` + `ee.Initialize(project=...)` beforehand, or let geeViz handle it on first tool call)

```bash
pip install geeViz
```

You can run `python -m geeViz.mcp.server --help` or `python -m geeViz.mcp --help` to verify the server is available.

## Running the server

From the directory that contains the `geeViz` package (e.g. `geeVizBuilder`):

```bash
# Default: stdio transport (for Cursor/IDE)
python -m geeViz.mcp.server

# Show usage and options
python -m geeViz.mcp.server --help
```

Or run the `mcp` subpackage (same as above):

```bash
python -m geeViz.mcp --help
python -m geeViz.mcp
```

### HTTP transport (optional)

```bash
set MCP_TRANSPORT=streamable-http
set MCP_PORT=8000
set MCP_HOST=127.0.0.1
python -m geeViz.mcp.server
```

## Cursor / Claude Code configuration

Add to your MCP settings (e.g. Cursor Settings -> MCP, or `.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "geeviz": {
      "command": "python",
      "args": ["-m", "geeViz.mcp.server"],
      "cwd": "C:\\path\\to\\geeVizBuilder"
    }
  }
}
```

Ensure `cwd` is the folder that contains the `geeViz` package so `python -m geeViz.mcp.server` runs correctly.

## Tools

The MCP surface is **12 tools** organized by role. Charting, thumbnails, reports, and geocoding are accessed via `run_code` using pre-loaded aliases (`cl`, `tl`, `rl`, `gm`) rather than dedicated tools — one execution primitive plus a rich REPL namespace beats a proliferation of narrow wrappers.

### Discover & inspect
| Tool | Description |
|------|-------------|
| **`search_geeviz`** | Unified search across every geeViz module. Signature lookup, module listing, source dumps, reference-dict values, and example scripts all in one tool. Use `search_geeviz(query="landsat")` for broad search, `search_geeviz(name="simpleMask")` for exact lookup with full docstring, `search_geeviz(module="getImagesLib")` to list a module's contents, `search_geeviz(module="examples", name="GFSTimeLapse")` for a runnable example. AST-based — no imports until a runtime value is actually requested. |
| **`inspect_asset`** | Get metadata for any GEE asset — bands, CRS, scale, date range, catalog info (title, provider, keywords, viz params), properties. Uses 10s timeout per query; never hangs on large collections. |
| **`search_datasets`** | Search GEE dataset catalogs by keyword. Crawls official STAC + community catalogs (cached 24h). Returns ranked results with asset IDs. |
| **`env_info`** | Get versions, REPL namespace, or project info (action="version"\|"namespace"\|"project"). Use `action="namespace"` to see all variables defined by prior `run_code` calls. |

### Execute
| Tool | Description |
|------|-------------|
| **`run_code`** | Execute Python/GEE code in a persistent REPL (like Jupyter). Variables persist across calls. Pre-populated with `ee`, `Map`, `gv` (geeView), `gil` (getImagesLib), `sal` (getSummaryAreasLib), `edw` (edwLib), `gm` (googleMapsLib), `palettes` (geePalettes), `cl` (outputLib.charts), `tl` (outputLib.thumbs), `rl` (outputLib.reports), `pd`/`pandas`, `np`/`numpy`, and `save_file`. See "Persistent REPL namespace" below for the full list. Timeout tracks inactivity (not total time). Errors are returned inline with traceback. |
| **`save_session`** | Save the current REPL history as a `.py` or `.ipynb` file. |

### Visualize & preview
| Tool | Description |
|------|-------------|
| **`map_control`** | View, list layers, clear, or test the interactive map viewer. Actions: `view` (renders a self-contained HTML file and opens it in the browser), `layers` (structured list of active layers), `layer_names` (just the names), `clear` (drop all layers), `test_layers` (validates every layer with parallel `getMapId()` calls — ~1-2s quality gate before `view`), `test_view` (captures a PNG via headless Chrome CDP for visual/JS console checks). |
| **`view_output`** | Return the current map viewer URL and read back the contents of files the REPL has produced (thumbnails, chart HTML, reports). Useful when the agent needs to inspect the final artifact after `run_code`. |
| **`get_streetview`** | Get Google Street View imagery at a lat/lon for ground-truthing thematic classifications. |
| **`geeviz_search_places`** | Search Google Places API for nearby landmarks, businesses, POIs. Also useful for geocoding a place name to coordinates before turning them into an `ee.Geometry`. |

### Export & manage
| Tool | Description |
|------|-------------|
| **`export_image`** | Export an `ee.Image` to asset, Drive, or Cloud Storage (`destination="asset"\|"drive"\|"cloud"`). Wraps geeViz's exporter with validation, overwrite support, COG output, and pyramiding policy. |
| **`manage_asset`** | One tool for asset lifecycle: `action="delete"\|"copy"\|"move"\|"create"\|"update_acl"`. Handles both single assets and folders. |

**Accessed via `run_code`, not dedicated tools:**

- **Zonal summaries + charts** — `cl.summarize_and_chart()` returns a DataFrame plus a Plotly figure. Auto-detects thematic vs continuous data, picks the right reducer, supports time series / bar / grouped bar / donut / scatter / Sankey.
- **Thumbnails** — `tl.generate_thumbs()` produces publication-ready PNGs with basemap, legend, and scalebar.
- **Reports** — `rl.build_report()` writes multi-section HTML reports.
- **Geocoding** — `gm.geocode("Salt Lake City, UT")` returns coordinates without needing the Places API.
- **Task management** — `ee.data.listOperations()` or `ee.data.getTaskList()` inside `run_code` gives the agent full task control when needed.

## Using Without an IDE

If you can't use the MCP server through a coding IDE, there are several other options.

### Desktop AI Apps

**Claude Desktop** — Add to your config (`%APPDATA%\Claude\claude_desktop_config.json` on Windows, `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "geeViz": {
      "command": "python",
      "args": ["-m", "geeViz.mcp.server"]
    }
  }
}
```

**ChatGPT Desktop** — Also supports MCP servers. Add the same server command in ChatGPT's MCP configuration.

### Terminal

**Gemini CLI** — Google's [Gemini CLI](https://github.com/google-gemini/gemini-cli) supports MCP servers:

```bash
gemini --mcp-server "python -m geeViz.mcp.server"
```

Or add to `.gemini/settings.json`:

```json
{
  "mcpServers": {
    "geeViz": {
      "command": "python",
      "args": ["-m", "geeViz.mcp.server"]
    }
  }
}
```

**Claude Code (CLI)** — Terminal-based AI agent with MCP support:

```bash
claude mcp add geeViz python -- -m geeViz.mcp.server
```

### Python Script or Jupyter Notebook

Connect programmatically using the `mcp` Python client library and pipe tool calls through any LLM API (Gemini, Claude, OpenAI). See the included examples:

- `mcp_with_gemini_tutorial.ipynb` — Jupyter notebook tutorial for using the MCP server with Gemini

Both use `python-dotenv` to load a `GOOGLE_API_KEY` from a `.env` file. Core pattern:

```python
import subprocess
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

server_params = StdioServerParameters(
    command="python",
    args=["-m", "geeViz.mcp.server"],
)

# errlog=subprocess.DEVNULL needed in Jupyter on Windows
async with stdio_client(server_params, errlog=subprocess.DEVNULL) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()
        tools = await session.list_tools()       # discover all 12 tools
        result = await session.call_tool(         # call any tool
            name="env_info", arguments={"action": "version"}
        )
```

### Choosing the Right Option

| Option | Setup effort | Best for | Notes |
|--------|-------------|----------|-------|
| **IDE** (Cursor, VS Code, etc.) | Low | Daily development | Tightest integration — tools appear inline while coding |
| **Claude Desktop / ChatGPT** | Low | Chat-style exploration | No coding required, conversational interface |
| **Gemini CLI / Claude Code** | Low | Terminal users | Full agent capabilities from the command line |
| **Python script / notebook** | Medium | Batch testing, custom workflows | Full control over prompts and output handling |
| **HTTP server** | Medium | Remote/shared access | Any HTTP MCP client can connect |

## Architecture

### Lazy initialization

Every geeViz module import triggers `robustInitializer()` at module level, which initializes Earth Engine. The MCP server defers all geeViz imports until the first tool call that needs them. A thread-safe `_ensure_initialized()` function handles this.

### Persistent REPL namespace

`run_code` uses a per-session `dict` as a shared namespace (like a Jupyter kernel). It is pre-populated after init with:

- `ee` -- the Earth Engine API
- `Map` -- `gv.Map` (geeView map object, per-session)
- `gv` -- `geeViz.geeView`
- `gil` -- `geeViz.getImagesLib`
- `sal` -- `geeViz.getSummaryAreasLib`
- `edw` -- `geeViz.edwLib` (USFS Enterprise Data Warehouse REST client)
- `gm` -- `geeViz.googleMapsLib` (geocoding, Street View, elevation, etc.)
- `palettes` -- `geeViz.geePalettes` (Gennadiy Donchyts' `ee-palettes` collection)
- `cl` -- `geeViz.outputLib.charts` (`summarize_and_chart`, Sankey diagrams)
- `tl` -- `geeViz.outputLib.thumbs` (PNG thumbnails, animated GIFs, filmstrips)
- `rl` -- `geeViz.outputLib.reports` (multi-section HTML/MD/PDF reports)
- `pd` / `pandas` -- both aliases point at the pandas module
- `np` / `numpy` -- both aliases point at numpy
- `save_file` -- helper for writing per-session output files
- `search_datasets`, `search_geeviz`, `inspect_asset`, `map_control`, `env_info`,
  `view_output`, `geeviz_search_places`, `search_places`, `lookup_weather`,
  `compute_routes` -- clear-error stubs for MCP tool names, so if the agent
  accidentally calls one from inside `run_code` it gets an actionable message
  instead of a confusing NameError.

Variables set in one `run_code` call are available in subsequent calls within the same session. Use `reset=True` to clear and re-initialize.

### Timeout (Windows)

Uses `threading.Thread(daemon=True)` + `.join(timeout)`. Known limitation: a hung `getInfo()` call cannot be force-killed on Windows -- the thread continues in background.

### FastMCP loading

Because `geeViz.mcp` shadows the `mcp` SDK package name, the server resolves `FastMCP` by scanning site-packages directly (`_load_fastmcp()`).

## Example usage

Once the server is running in an MCP client:

```
# Run code in the persistent REPL
run_code("x = ee.Number(42).getInfo()")
run_code("print(x)")  # prints 42

# Inspect an asset
inspect_asset("COPERNICUS/S2_SR_HARMONIZED")

# Look up a function (exact match with full docstring)
search_geeviz(name="superSimpleGetS2")

# Search by keyword across a module
search_geeviz(query="add", module="geeView")

# List example scripts, then read one
search_geeviz(module="examples")
search_geeviz(module="examples", name="GFSTimeLapse")

# Look up a reference dict (band mappings, viz params, projections, test areas)
search_geeviz(module="getImagesLib", name="common_projections")

# Check versions / namespace / project
env_info(action="version")
env_info(action="namespace")
env_info(action="project")

# Save session as a Jupyter notebook
save_session("my_analysis", format="ipynb")

# Export an image (after creating it with run_code)
export_image("my_image", "projects/my-project/assets/export_name", destination="asset")

# Export to Google Drive
export_image("my_image", "output_name", destination="drive", folder="my_drive_folder")

# Search for datasets
search_datasets("landsat surface reflectance")

# Search only community datasets
search_datasets("fire", source="community")

# Get detailed info on a specific dataset (with optional filters)
inspect_asset("LANDSAT/LC09/C02/T1_L2", start_date="2023-01-01", end_date="2023-12-31")

# Manage assets (delete, copy, move, create folder, update ACL)
manage_asset(action="delete", asset_id="projects/my-project/assets/old_image")
manage_asset(action="copy", asset_id="projects/src", dest_id="projects/dest")
manage_asset(action="create", asset_id="projects/my-project/assets/new_folder")
manage_asset(action="update_acl", asset_id="projects/my-project/assets/img", all_users_can_read=True)

# View the map (after adding layers with run_code)
map_control(action="view")

# Fast layer validation (before showing to user)
map_control(action="test_layers")

# Full browser screenshot (slow, for visual checks)
map_control(action="test_view")

# Read the current map URL and/or a generated file's contents
view_output()

# Search for places / geocode
geeviz_search_places("Yellowstone National Park")

# Get Street View imagery
get_streetview(lon=-111.88, lat=40.76)

# Task management (no dedicated tools — use run_code + ee.data)
run_code("import ee; ops = ee.data.listOperations(); print([o['metadata']['description'] for o in ops[:10]])")

# Charting, thumbnails, and analysis via run_code
run_code("result = cl.summarize_and_chart(my_ic, geometry=area)")
run_code("result = tl.generate_thumbs(my_image, area)")
```

## Agent instructions

The MCP server automatically serves agent instructions to every connected client via the MCP `instructions` protocol field. When your AI assistant connects, it receives the full set of rules, workflow patterns, and tool descriptions — no manual setup required.

These instructions are loaded from [`agent-instructions.md`](agent-instructions.md) in this directory, which also ships with the package for reference. If your editor supports additional instructions files, you can copy the contents there for extra reinforcement:

| Editor | Instructions file |
|--------|-------------------|
| **VS Code / GitHub Copilot** | `.github/copilot-instructions.md` |
| **Cursor** | `.cursorrules` or Cursor Settings > Rules |
| **Claude Code** | `CLAUDE.md` in the project root |
| **Windsurf** | `.windsurfrules` |

You can find the file at:

```bash
# If installed via pip
python -c "import geeViz.mcp; import os; print(os.path.join(os.path.dirname(geeViz.mcp.__file__), 'agent-instructions.md'))"

# Or in the source tree
cat geeViz/mcp/agent-instructions.md
```

**Use both the MCP server and the instructions file.** The MCP server gives the AI tools; the instructions file tells it when to use them. Without instructions, the AI has tools but may not think to reach for them. Without MCP, the instructions are just more text for the AI to hallucinate from.

## Package usage

```python
from geeViz.mcp import app

# app is the FastMCP instance; use with mcp.run() or your MCP host.
```

## Related packages

- **`geeViz.geeView`** — the interactive map viewer that `map_control(action="view")` opens. See [`../geeView/README.md`](../geeView/README.md).
- **`geeViz.outputLib`** — the charting / thumbnail / report pipeline reached via `cl`, `tl`, `rl` in `run_code`. See [`../outputLib/README.md`](../outputLib/README.md).
- **`geeViz.eeAuth`** — the multi-tenant EE auth proxy `map_control` relies on for per-request tenant routing. See [`../eeAuth/README.md`](../eeAuth/README.md).

## License

Apache 2.0. See the main geeViz package and `__init__.py` in this directory.
