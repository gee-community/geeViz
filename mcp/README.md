# geeViz MCP Server

MCP (Model Context Protocol) server for the **geeViz** Python package. Provides 21 execution and introspection tools that give AI agents structured, live access to Google Earth Engine and the geeViz API.

## Why MCP?

An AI coding agent already has powerful general-purpose tools -- it can search the web, read local files, grep source code, and write scripts. So why add an MCP server on top of that?

The core problem is that **Earth Engine is a live, authenticated cloud platform**. General-purpose tools can read _about_ GEE but cannot _interact_ with it. The MCP server bridges that gap by giving the agent 21 purpose-built tools that execute against your authenticated GEE session and the actual geeViz codebase. The table below compares what each approach can do for common GEE tasks:

| Task | Vanilla coding agent (web search, grep, file read) | geeViz MCP server |
|------|-----------------------------------------------------|-------------------|
| **Look up a geeViz function signature** | Grep source files or search the web -- may find outdated docs, wrong version, or miss internal helpers | `search_functions(function_name="func")` runs Python `inspect` on the _installed_ code -- always returns the real signature and docstring |
| **Find which module has a function** | `grep -r` across all .py files, manually parse results | `search_functions` searches all 10 geeViz modules in one call, or lists functions in a specific module -- returns structured results |
| **Check what bands a dataset has** | Search the GEE data catalog website, parse HTML, hope the page is current | `inspect_asset` calls `ee.data.getInfo()` on the _live_ asset -- returns real bands, CRS, scale, date range, properties |
| **Get image count and date range for a filtered collection** | Write and run a script with multiple `getInfo()` calls | `inspect_asset` with optional start_date/end_date/region_var returns count, date range, band info in one structured call |
| **Search for GEE datasets by keyword** | Web search, browse the GEE catalog, read blog posts | `search_datasets` searches 700+ official and community datasets offline (24h-cached catalog), returns ranked results with asset IDs |
| **Get detailed dataset metadata (bands, classes, scale/offset)** | Find and parse the STAC JSON page for the dataset | `inspect_asset` fetches the full STAC record and returns structured band info, class descriptions, viz params |
| **Test a code snippet** | Write to a file, run it in a terminal, read stdout/stderr | `run_code` executes in a persistent REPL namespace (like Jupyter) with `ee`, `Map`, `gv`, `gil` pre-loaded -- variables persist across calls, errors are returned inline |
| **Build up an analysis incrementally** | Each script run starts fresh; agent must manage state manually | `run_code` namespace persists -- build up variables, test each step, inspect intermediate results with `env_info(action="namespace")` |
| **See what variables exist after several code steps** | Re-read the script, mentally track assignments | `env_info(action="namespace")` returns all user-defined variables with type and repr -- no `getInfo()` calls |
| **Visualize results on a map** | Write code to call `Map.view()`, tell the user to open a browser | `map_control(action="view")` opens the geeView map and returns the URL directly |
| **Get a visual preview of an image** | Write a `getThumbURL` script, fetch the image, save to disk | `tl.generate_thumbs()` in `run_code` produces publication-ready PNG thumbnails with basemap, legend, and scalebar |
| **Sample pixel values or chart zonal statistics** | Write `reduceRegion` scripts, detect thematic vs continuous data, choose reducers, build Plotly figures manually | `cl.summarize_and_chart()` in `run_code` handles point sampling, time series, bar charts, and Sankey diagrams in one call -- auto-detects data type, picks the right reducer, and returns a DataFrame + chart |
| **Geocode a place name to a GEE geometry** | Call a geocoding API, manually construct `ee.Geometry` | `search_places` returns coordinates and place details; `sal` in `run_code` provides boundary polygons for counties, states, forests, protected areas, etc. |
| **Export an image to an asset** | Write export code, look up `pyramidingPolicy` options, handle overwrite | `export_image(destination="asset")` wraps geeViz's exporter with validation, overwrite support, and pyramiding policy |
| **Export to Drive or Cloud Storage** | Write export boilerplate, remember required parameters | `export_image(destination="drive"\|"cloud")` handles all params with sensible defaults (COG enabled, etc.) |
| **Check task status or cancel tasks** | Write `ee.data.getTaskList()` code, filter manually | `track_tasks` / `cancel_tasks` return structured task info, support name filtering |
| **Manage assets (copy, move, delete, permissions)** | Write 5-10 lines of `ee.data.*` calls per operation | `manage_asset(action="copy"\|"move"\|"delete"\|"create"\|"update_acl")` -- one call with validation |
| **Read a geeViz example script** | `find` + `cat` the example file, hope you guess the filename | `examples(action="list")` shows all 40+ examples with descriptions; `examples(action="get")` returns full source for .py or .ipynb |
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
| **`run_code`** | Execute Python/GEE code in a persistent REPL. Variables persist across calls. Pre-populated with `ee`, `Map`, `gv`, `gil`, `sal`, `tl`, `rl`, `cl`, `save_file`. Timeout tracks inactivity (not total time). |
| **`inspect_asset`** | Get metadata for any GEE asset — bands, CRS, scale, date range, catalog info (title, provider, keywords, viz params), properties. Uses 10s timeout per query; never hangs on large collections. |
| **`search_functions`** | Search, list, or get full docs for geeViz functions. Use `function_name="func"` for exact lookup with full docstring. |
| **`examples`** | List or read example scripts (action="list"\|"get"). 40+ examples with descriptions. |
| **`search_datasets`** | Search GEE dataset catalogs by keyword. Crawls official STAC + community catalogs (cached 1 week). |
| **`get_reference_data`** | Look up reference dicts (band mappings, viz params, collection IDs, projections, test areas). |
| **`env_info`** | Get versions, REPL namespace, or project info (action="version"\|"namespace"\|"project"). |
| **`list_assets`** | List assets in a GEE folder (id, type, size). |
| **`track_tasks`** | Get status of recent Earth Engine tasks. |
| **`cancel_tasks`** | Cancel running/ready EE tasks (all or by name filter). |
| **`export_image`** | Export an `ee.Image` to asset, Drive, or Cloud Storage (destination="asset"\|"drive"\|"cloud"). |
| **`manage_asset`** | Delete, copy, move, create folder, or update ACL (action="delete"\|"copy"\|"move"\|"create"\|"update_acl"). |
| **`map_control`** | View, list layers, clear, or test the interactive map (action="view"\|"layers"\|"layer_names"\|"clear"\|"test"). `view` renders a self-contained HTML file and opens it in the browser. `test` captures a PNG via headless Chrome CDP and returns `tile_errors` + `console_messages` for debugging — use as a quality gate before `view`. |
| **`save_session`** | Save run_code history as `.py` or `.ipynb`. |
| **`get_streetview`** | Get Google Street View imagery at a location for ground-truthing. |
| **`search_places`** | Search Google Places API for nearby landmarks, businesses, POIs. Also useful for geocoding. |
| **`create_report`** | Create a new report (title, theme, layout, tone). |
| **`add_report_section`** | Add a section to the active report (ee.Image/IC + geometry). |
| **`generate_report`** | Generate the report (HTML, Markdown, or PDF). |
| **`get_report_status`** | Check active report status and section list. |
| **`clear_report`** | Discard the active report. |

Charting (`cl.summarize_and_chart()`), thumbnails (`tl.generate_thumbs()`), EDW queries (`edwLib`), and geocoding (`gm.geocode()`) are accessed via `run_code`.

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
        tools = await session.list_tools()       # discover all 21 tools
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

# Look up a function (exact match with full docstring)
search_functions(function_name="superSimpleGetS2")

# Search functions by keyword
search_functions(query="add", module="geeView")

# List all examples
examples(action="list", filter="CCDC")

# Read an example
examples(action="get", name="getLandsatWrapper")

# List assets in a folder
list_assets("projects/my-project/assets")

# Check task status
track_tasks()

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

# Cancel all running tasks
cancel_tasks()

# Cancel tasks matching a name
cancel_tasks("my_export")

# Manage assets (delete, copy, move, create folder, update ACL)
manage_asset(action="delete", asset_id="projects/my-project/assets/old_image")
manage_asset(action="copy", asset_id="projects/src", dest_id="projects/dest")
manage_asset(action="create", asset_id="projects/my-project/assets/new_folder")
manage_asset(action="update_acl", asset_id="projects/my-project/assets/img", all_users_can_read=True)

# View the map (after adding layers with run_code)
map_control(action="view")

# Test map rendering (before showing to user)
map_control(action="test")

# Search for places / geocode
search_places("Yellowstone National Park")

# Get Street View imagery
get_streetview(lon=-111.88, lat=40.76)

# Charting, thumbnails, and analysis via run_code
run_code("df, fig = cl.summarize_and_chart(my_ic, geometry=area)")
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

## License

Apache 2.0. See the main geeViz package and `__init__.py` in this directory.
