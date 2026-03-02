# geeViz MCP Server

MCP (Model Context Protocol) server for the **geeViz** Python package. Provides 33 execution and introspection tools that let LLMs run code, inspect live GEE assets, search the GEE dataset catalog, geocode places, export data, manage assets and tasks, sample values, chart time series, and query API signatures -- things static docs cannot do.

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
| **`run_code`** | Execute Python/GEE code in a persistent REPL namespace. Variables persist across calls. Pre-populated with `ee`, `Map`, `gv`, `gil`. Supports timeout and namespace reset. |
| **`inspect_asset`** | Get detailed metadata for any GEE asset -- bands, CRS, scale, date range, size, columns, properties. |
| **`get_api_reference`** | Look up function signatures and docstrings from any geeViz module via Python `inspect`. Always reflects current code. |
| **`list_functions`** | List all public functions/classes in a geeViz module with one-line descriptions. Supports substring filter. |
| **`get_example`** | Read the full source code of a geeViz example script (.py or .ipynb). |
| **`list_examples`** | List available example scripts (40+) with descriptions. Supports substring filter. |
| **`list_assets`** | List assets in a GEE folder (id, type, size). |
| **`track_tasks`** | Get status of recent Earth Engine tasks (state, type, start time, errors). |
| **`get_version_info`** | Return geeViz, Earth Engine, and Python version info. |
| **`get_namespace`** | Inspect user-defined variables in the persistent REPL namespace (name, type, repr). No `getInfo()` calls. |
| **`get_project_info`** | Return the current EE project ID and a sample of root assets. |
| **`save_notebook`** | Save accumulated `run_code` history as a Jupyter notebook (`.ipynb`). One code cell per call. |
| **`export_to_asset`** | Export an `ee.Image` to a GEE asset using geeViz's `exportToAssetWrapper`. Supports overwrite and pyramiding policy. |
| **`geocode`** | Geocode a place name to coordinates (Nominatim) and optionally search GEE boundary collections (WDPA, GAUL, TIGER) for matching polygons. |
| **`search_datasets`** | Search the GEE dataset catalog by keyword. Searches official (~500+) and community (~200+) catalogs with relevance-ranked results. Cached locally with 24h TTL. |
| **`get_dataset_info`** | Get the full STAC JSON record for a GEE dataset -- bands (with classes, wavelengths, scale/offset), description, extent, keywords, license, visualization parameters, and more. |
| **`get_thumbnail`** | Get a PNG thumbnail of an `ee.Image` or animated GIF of an `ee.ImageCollection`. Returns the image directly so the LLM can see it for visual context. |
| **`export_to_drive`** | Export an `ee.Image` to Google Drive using geeViz's `exportToDriveWrapper`. Region is required. |
| **`export_to_cloud_storage`** | Export an `ee.Image` to Google Cloud Storage using geeViz's `exportToCloudStorageWrapper`. Defaults to Cloud Optimized GeoTIFF. |
| **`cancel_tasks`** | Cancel running/ready EE tasks. Cancel all tasks or filter by name substring using geeViz's `taskManagerLib`. |
| **`sample_values`** | Sample pixel values from an `ee.Image` at a point (lon/lat) or region. Supports multiple reducers (mean, median, min, max, etc.). |
| **`get_time_series`** | Extract time series of band values from an `ee.ImageCollection`. Returns date-value pairs and a chart PNG (if matplotlib is available). |
| **`delete_asset`** | Delete a single GEE asset. Checks existence before deleting. Single-asset only (not recursive). |
| **`copy_asset`** | Copy a GEE asset to a new location. Supports overwrite. |
| **`move_asset`** | Move a GEE asset (copy then delete source). Only deletes source after successful copy. |
| **`create_folder`** | Create a GEE folder or ImageCollection. Creates intermediate folders recursively. |
| **`update_acl`** | Update permissions (ACL) on a GEE asset -- set public read, add readers/writers by email. |
| **`get_collection_info`** | Get summary info for an ImageCollection by asset ID -- image count, date range, band names/types, scale. |

## Architecture

### Lazy initialization

Every geeViz module import triggers `robustInitializer()` at module level, which initializes Earth Engine. The MCP server defers all geeViz imports until the first tool call that needs them. A thread-safe `_ensure_initialized()` function handles this.

### Persistent REPL namespace

`run_code` uses a module-level `dict` as a shared namespace (like a Jupyter kernel). It is pre-populated after init with:

- `ee` -- the Earth Engine API
- `Map` -- `gv.Map` (geeView map object)
- `gv` -- `geeViz.geeView`
- `gil` -- `geeViz.getImagesLib`

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

# Find functions
list_functions("geeView", filter="add")

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
save_notebook("my_analysis")

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
get_dataset_info("LANDSAT/LC09/C02/T1_L2")

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

# Sample pixel values at a point
sample_values("my_image", lon=-111.04, lat=45.68)

# Sample with a region and reducer
sample_values("my_image", geometry_var="roi", reducer="mean")

# Get time series (returns chart if matplotlib is available)
get_time_series("my_collection", "roi", band="NDVI")

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

# Get collection info
get_collection_info("LANDSAT/LC09/C02/T1_L2", start_date="2023-01-01", end_date="2023-12-31")
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
