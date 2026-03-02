# geeViz Agent Instructions

This project is **geeViz**, a Python package for Google Earth Engine visualization and analysis. You have access to a geeViz MCP server with tools that let you look things up and execute code -- use them instead of guessing.

Copy this file (or its contents) into your editor's agent instructions file to get the best results from your AI assistant. See the section at the bottom for where each editor expects its instructions.

## Rules

1. **Always use the MCP tools before writing geeViz code.** Do not rely on your training data for function signatures, parameter names, or defaults. Look them up.
2. **Test your code with `run_code` before giving it to the user.** If it errors, fix it. The user should never be the first person to discover a bug.
3. **When you don't know which module a function is in**, use `search_functions` to find it across all modules.
4. **When the user asks about a dataset**, use `inspect_asset` to get its real bands, date range, and CRS -- don't guess.
5. **When writing a workflow similar to an existing example**, use `list_examples` and `get_example` to read the real source first.

## Typical workflow

For a request like "do change detection near Bozeman":

1. `list_examples(filter="LANDTRENDR")` -- find relevant examples
2. `get_example("LANDTRENDRWrapper")` -- read the real source
3. `get_api_reference("changeDetectionLib", "simpleLANDTRENDR")` -- check the actual signature
4. `run_code(...)` -- build the code incrementally, testing each step
5. `view_map()` -- open the map when layers are ready
6. Tell the user the `script_path` from the `run_code` response -- they get a saved .py file

## Key geeViz patterns

- Import: `import geeViz.geeView as gv` -- this initializes Earth Engine automatically
- The `run_code` namespace already has `ee`, `Map` (gv.Map), `gv`, and `gil` (getImagesLib)
- `Map.addLayer(image, vizParams, "name")` adds to the map; `Map.view()` opens it
- `Map.clearMap()` resets the map between experiments
- Study areas: `ee.Geometry.Point([lon, lat]).buffer(meters)` or `ee.Geometry.Polygon([...])`
- Visualization: `{"min": 0, "max": 1, "palette": "red,green,blue"}` or use built-in palettes

## Available MCP tools (33)

### Code Execution
- `run_code` -- execute Python in a persistent REPL (like Jupyter)
- `save_script` -- save all run_code history to a .py file
- `save_notebook` -- save run_code history as a Jupyter notebook

### Map Control
- `view_map` -- open the geeView map, returns URL
- `get_map_layers` -- see what's on the map
- `clear_map` -- reset the map

### API Introspection
- `get_api_reference` -- look up function signature + docstring
- `list_functions` -- list functions in a module
- `search_functions` -- search across all modules

### Asset & Task Management
- `inspect_asset` -- get GEE asset metadata (bands, CRS, dates, properties)
- `list_assets` -- list assets in a folder
- `track_tasks` -- check EE task status
- `cancel_tasks` -- cancel running/ready tasks (all or by name filter)

### Export
- `export_to_asset` -- export an ee.Image to a GEE asset (supports overwrite, pyramiding policy)
- `export_to_drive` -- export an ee.Image to Google Drive
- `export_to_cloud_storage` -- export an ee.Image to Google Cloud Storage

### Data Sampling & Time Series
- `sample_values` -- sample pixel values at a point or region (supports multiple reducers)
- `get_time_series` -- extract band values over time, returns chart PNG if matplotlib available

### Asset Operations
- `delete_asset` -- delete a single GEE asset
- `copy_asset` -- copy a GEE asset to a new location
- `move_asset` -- move a GEE asset (copy + delete source)
- `create_folder` -- create a GEE folder or ImageCollection (recursive)
- `update_acl` -- update permissions on a GEE asset

### Dataset Discovery
- `search_datasets` -- search the GEE dataset catalog by keyword
- `get_dataset_info` -- get detailed STAC metadata for a GEE dataset
- `get_collection_info` -- get summary info for an ImageCollection (count, dates, bands)
- `get_thumbnail` -- get a PNG thumbnail of an ee.Image or filmstrip

### Example Discovery
- `list_examples` -- list available geeViz example scripts (40+)
- `get_example` -- read the full source of an example

### Environment
- `get_version_info` -- check geeViz, EE, and Python versions
- `get_namespace` -- see what variables exist in the REPL
- `get_project_info` -- check which EE project is active
- `geocode` -- geocode a place name to coordinates / GEE boundary polygons

## Where to put this file

Each editor looks for agent instructions in a different place:

- **VS Code / GitHub Copilot**: `.github/copilot-instructions.md`
- **Cursor**: `.cursorrules` or Cursor Settings > Rules
- **Claude Code**: `CLAUDE.md` in the project root
- **Windsurf**: `.windsurfrules`

Copy the contents of this file into the appropriate location for your editor.
