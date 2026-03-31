# geeViz MCP Server

MCP (Model Context Protocol) server for the **geeViz** Python package. Provides 32 execution and introspection tools that give AI agents structured, live access to Google Earth Engine and the geeViz API.

## Why MCP?

An AI coding agent already has powerful general-purpose tools -- it can search the web, read local files, grep source code, and write scripts. So why add an MCP server on top of that?

The core problem is that **Earth Engine is a live, authenticated cloud platform**. General-purpose tools can read _about_ GEE but cannot _interact_ with it. The MCP server bridges that gap by giving the agent 30 purpose-built tools that execute against your authenticated GEE session and the actual geeViz codebase. The table below compares what each approach can do for common GEE tasks:

| Task | Vanilla coding agent (web search, grep, file read) | geeViz MCP server |
|------|-----------------------------------------------------|-------------------|
| **Look up a geeViz function signature** | Grep source files or search the web -- may find outdated docs, wrong version, or miss internal helpers | `get_api_reference` runs Python `inspect` on the _installed_ code -- always returns the real signature and docstring |
| **Find which module has a function** | `grep -r` across all .py files, manually parse results | `search_functions` searches all 10 geeViz modules in one call, or lists functions in a specific module -- returns structured results |
| **Check what bands a dataset has** | Search the GEE data catalog website, parse HTML, hope the page is current | `inspect_asset` calls `ee.data.getInfo()` on the _live_ asset -- returns real bands, CRS, scale, date range, properties |
| **Get image count and date range for a filtered collection** | Write and run a script with multiple `getInfo()` calls | `inspect_asset` with optional start_date/end_date/region_var returns count, date range, band info in one structured call |
| **Search for GEE datasets by keyword** | Web search, browse the GEE catalog, read blog posts | `search_datasets` searches 700+ official and community datasets offline (24h-cached catalog), returns ranked results with asset IDs |
| **Get detailed dataset metadata (bands, classes, scale/offset)** | Find and parse the STAC JSON page for the dataset | `get_catalog_info` fetches the full STAC record and returns structured band info, class descriptions, viz params |
| **Test a code snippet** | Write to a file, run it in a terminal, read stdout/stderr | `run_code` executes in a persistent REPL namespace (like Jupyter) with `ee`, `Map`, `gv`, `gil` pre-loaded -- variables persist across calls, errors are returned inline |
| **Build up an analysis incrementally** | Each script run starts fresh; agent must manage state manually | `run_code` namespace persists -- build up variables, test each step, inspect intermediate results with `get_namespace` |
| **See what variables exist after several code steps** | Re-read the script, mentally track assignments | `get_namespace` returns all user-defined variables with type and repr -- no `getInfo()` calls |
| **Visualize results on a map** | Write code to call `Map.view()`, tell the user to open a browser | `view_map` opens the geeView map and returns the URL directly |
| **Get a visual preview of an image** | Write a `getThumbURL` script, fetch the image, save to disk | `get_thumbnail` returns a PNG/GIF that the LLM can _see_ and reason about visually |
| **Sample pixel values or chart zonal statistics** | Write `reduceRegion` scripts, detect thematic vs continuous data, choose reducers, build Plotly figures manually | `extract_and_chart` handles point sampling, time series, bar charts, and Sankey diagrams in one call — auto-detects data type, picks the right reducer, and returns a DataFrame + Plotly chart HTML |
| **Geocode a place name to a GEE geometry** | Call a geocoding API, manually construct `ee.Geometry` | `geocode` returns coordinates, bounding box, _and_ searches GEE boundary collections (WDPA, GAUL, TIGER) for matching polygons with ready-to-use EE code |
| **Export an image to an asset** | Write export code, look up `pyramidingPolicy` options, handle overwrite | `export_to_asset` wraps geeViz's exporter with validation, overwrite support, and pyramiding policy |
| **Export to Drive or Cloud Storage** | Write export boilerplate, remember required parameters | `export_to_drive` / `export_to_cloud_storage` handle all params with sensible defaults (COG enabled, etc.) |
| **Check task status or cancel tasks** | Write `ee.data.getTaskList()` code, filter manually | `track_tasks` / `cancel_tasks` return structured task info, support name filtering |
| **Manage assets (copy, move, delete, permissions)** | Write 5-10 lines of `ee.data.*` calls per operation | `copy_asset`, `move_asset`, `delete_asset`, `create_folder`, `update_acl` -- one call each with validation |
| **Read a geeViz example script** | `find` + `cat` the example file, hope you guess the filename | `list_examples` shows all 40+ examples with descriptions; `get_example` returns full source for .py or .ipynb |
| **Save the session as a reusable script** | Manually copy code blocks from the conversation | `save_session` exports the full `run_code` history as a .py or .ipynb file |

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

| Tool | Description |
|------|-------------|
| **`run_code`** | Execute Python/GEE code in a persistent REPL namespace. Variables persist across calls. Pre-populated with `ee`, `Map`, `gv`, `gil`, `sal`. Supports timeout and namespace reset. |
| **`inspect_asset`** | Get detailed metadata for any GEE asset -- bands, CRS, scale, date range, size, columns, properties. For ImageCollections, supports optional date/region filters and returns image count, date range, per-band details. |
| **`get_api_reference`** | Look up function signatures and docstrings from any geeViz module via Python `inspect`. Always reflects current code. |
| **`search_functions`** | Search/list functions across geeViz modules. Pass `query` to search all modules, `module` to list one module's functions, or both to search within a module. |
| **`get_example`** | Read the full source code of a geeViz example script (.py or .ipynb). |
| **`list_examples`** | List available example scripts (40+) with descriptions. Supports substring filter. |
| **`list_assets`** | List assets in a GEE folder (id, type, size). |
| **`track_tasks`** | Get status of recent Earth Engine tasks (state, type, start time, errors). |
| **`get_version_info`** | Return geeViz, Earth Engine, and Python version info. |
| **`get_namespace`** | Inspect user-defined variables in the persistent REPL namespace (name, type, repr). No `getInfo()` calls. |
| **`get_project_info`** | Return the current EE project ID and a sample of root assets. |
| **`save_session`** | Save accumulated `run_code` history as a `.py` script (format="py") or Jupyter notebook (format="ipynb"). |
| **`export_to_asset`** | Export an `ee.Image` to a GEE asset using geeViz's `exportToAssetWrapper`. Supports overwrite and pyramiding policy. |
| **`geocode`** | Geocode a place name to coordinates (Nominatim) and optionally search GEE boundary collections (WDPA, GAUL, TIGER) for matching polygons. |
| **`search_datasets`** | Search the GEE dataset catalog by keyword. Searches official (~500+) and community (~200+) catalogs with relevance-ranked results. Cached locally with 24h TTL. |
| **`get_catalog_info`** | Get the full STAC JSON record for a GEE dataset -- bands (with classes, wavelengths, scale/offset), description, extent, keywords, license, visualization parameters, and more. |
| **`get_thumbnail`** | Get a PNG thumbnail of an `ee.Image` or animated GIF of an `ee.ImageCollection`. Returns the image directly so the LLM can see it for visual context. |
| **`export_to_drive`** | Export an `ee.Image` to Google Drive using geeViz's `exportToDriveWrapper`. Region is required. |
| **`export_to_cloud_storage`** | Export an `ee.Image` to Google Cloud Storage using geeViz's `exportToCloudStorageWrapper`. Defaults to Cloud Optimized GeoTIFF. |
| **`cancel_tasks`** | Cancel running/ready EE tasks. Cancel all tasks or filter by name substring using geeViz's `taskManagerLib`. |
| **`extract_and_chart`** | Extract values from an `ee.Image` or `ee.ImageCollection` over a point/region. Handles point sampling (buffer_meters=0), bar charts, time series, Sankey diagrams, donut charts, scatter plots, grouped bar charts, and per-feature time series subplots. Auto-detects thematic data. Wraps `geeViz.outputLib.charts.summarize_and_chart`. |
| **`delete_asset`** | Delete a single GEE asset. Checks existence before deleting. Single-asset only (not recursive). |
| **`copy_asset`** | Copy a GEE asset to a new location. Supports overwrite. |
| **`move_asset`** | Move a GEE asset (copy then delete source). Only deletes source after successful copy. |
| **`create_folder`** | Create a GEE folder or ImageCollection. Creates intermediate folders recursively. |
| **`update_acl`** | Update permissions (ACL) on a GEE asset -- set public read, add readers/writers by email. |

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

- `test_mcp.ipynb` — Jupyter notebook testing all 27 tools via Gemini
- `test_mcp_comparison.py` — Three-way comparison: bare Gemini vs Google Search vs MCP server

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
        tools = await session.list_tools()       # discover all 27 tools
        result = await session.call_tool(         # call any tool
            name="get_version_info", arguments={}
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

`run_code` uses a module-level `dict` as a shared namespace (like a Jupyter kernel). It is pre-populated after init with:

- `ee` -- the Earth Engine API
- `Map` -- `gv.Map` (geeView map object)
- `gv` -- `geeViz.geeView`
- `gil` -- `geeViz.getImagesLib`
- `sal` -- `geeViz.getSummaryAreasLib`

Variables set in one `run_code` call are available in subsequent calls. Use `reset=True` to clear and re-initialize.

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

# Look up a function
get_api_reference("getImagesLib", "getLandsat")

# Find functions in a module
search_functions(module="geeView", query="add")

# Read an example
get_example("getLandsatWrapper")

# List examples
list_examples(filter="CCDC")

# List assets in a folder
list_assets("projects/my-project/assets")

# Check task status
track_tasks()

# Check versions
get_version_info()

# See what variables exist after run_code calls
get_namespace()

# Check which EE project is active
get_project_info()

# Save session as a Jupyter notebook
save_session("my_analysis", format="ipynb")

# Export an image (after creating it with run_code)
export_to_asset("my_image", "projects/my-project/assets/export_name")

# Geocode a place name
geocode("Yellowstone National Park")

# Geocode with GEE boundary search
geocode("Montana", use_boundaries=True)

# Search for datasets
search_datasets("landsat surface reflectance")

# Search only community datasets
search_datasets("fire", source="community")

# Get detailed info on a specific dataset
get_catalog_info("LANDSAT/LC09/C02/T1_L2")

# Get a thumbnail (after creating an image with run_code)
get_thumbnail("my_image", '{"bands": ["B4","B3","B2"], "min": 0, "max": 3000}')

# Export to Google Drive
export_to_drive("my_image", "output_name", "my_drive_folder", "roi")

# Export to Google Cloud Storage
export_to_cloud_storage("my_image", "output_name", "my-bucket", "roi")

# Cancel all running tasks
cancel_tasks()

# Cancel tasks matching a name
cancel_tasks("my_export")

# Point sample -- raw pixel values (no chart)
extract_and_chart(image_var="my_image", lon=-111.04, lat=45.68, buffer_meters=0)

# Time series chart over a buffered point
extract_and_chart(collection_var="my_collection", lon=-111.04, lat=45.68, buffer_meters=10000, band_names="NDVI")

# Time series chart over a region variable
extract_and_chart(collection_var="my_collection", geometry_var="roi", band_names="NDVI")

# Delete an asset
delete_asset("projects/my-project/assets/old_image")

# Copy an asset
copy_asset("projects/my-project/assets/src", "projects/my-project/assets/dest")

# Move an asset
move_asset("projects/my-project/assets/src", "projects/my-project/assets/dest")

# Create a folder
create_folder("projects/my-project/assets/new_folder")

# Create an ImageCollection
create_folder("projects/my-project/assets/new_collection", folder_type="ImageCollection")

# Make an asset publicly readable
update_acl("projects/my-project/assets/my_image", all_users_can_read=True)

# Get collection info (inspect_asset with optional filters)
inspect_asset("LANDSAT/LC09/C02/T1_L2", start_date="2023-01-01", end_date="2023-12-31")

# Zonal summary -- thematic ImageCollection (auto-detects frequencyHistogram)
extract_and_chart(collection_var="lcms", lon=-105.5, lat=40.0, buffer_meters=50000)

# Sankey transition diagram
extract_and_chart(collection_var="lcms", geometry_var="roi", sankey=True, transition_periods="[[1985,1990],[2005,2010],[2018,2023]]", sankey_band_name="Land_Cover")

# Continuous data with mean reducer
extract_and_chart(collection_var="composites", geometry_var="roi", band_names="NDVI", reducer="mean")

# Single Image bar chart
extract_and_chart(image_var="lc_mode", geometry_var="roi", area_format="Hectares")
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

## License

Apache 2.0. See the main geeViz package and `__init__.py` in this directory.
