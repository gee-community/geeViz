<p align="center">
  <a href="https://geeviz.org/">
    <img src="https://geeviz.org/_static/images/geeviz-logo-light.png" alt="geeViz logo" height="120">
  </a>
</p>

<h1 align="center">geeViz</h1>
<p align="center"><b>The Earth Engine Visualization Toolkit for Python</b></p>

<p align="center">
  <a href="https://pypi.org/project/geeViz/"><img src="https://img.shields.io/pypi/v/geeViz?color=blue" alt="PyPI version"></a>
  <a href="https://github.com/gee-community/geeViz"><img src="https://img.shields.io/github/stars/gee-community/geeViz?logo=github" alt="GitHub stars"></a>
  <a href="https://geeviz.org/">Docs</a>
  <a href="https://earthengine.google.com/">Google Earth Engine</a>
</p>

---

**geeViz** makes exploring, visualizing, and analyzing Earth Engine data and geospatial imagery easy in Python. Whether you’re an analyst, scientist, or just getting started, geeViz offers interactive mapping, time series, and advanced charting—without the JavaScript overhead.

Developed by [RedCastle Resources](https://www.redcastleresources.com/), geeViz features a powerful, customizable map viewer and Pythonic interfaces for working with [Google Earth Engine (GEE)](https://earthengine.google.com/).

---

## Key Features

- Interactive Map Viewer (launches in your browser)
- Layer toggling, opacity, visualization tools, querying, & area charting
- Dynamic time-lapse creation from GEE `ImageCollections`
- Built-in charting & analysis tools (point/polygon, time series, area stats)
- **Inline zonal summary & charting** (`geeViz.chartingLib`) — run zonal stats and produce Plotly charts (time series, bar, grouped bar, per-feature time series subplots, Sankey) directly in notebooks
- **Summary area retrieval** (`geeViz.getSummaryAreasLib`) — 15 functions returning filtered `ee.FeatureCollection` objects for political boundaries, USFS units, census geographies, buildings, roads, and protected areas
- Jupyter/Colab support and standalone scripting
- Supports Landsat, Sentinel-2, MODIS, LCMS, LCMAP, and more
- Extensive examples and ready-to-run wrappers
- Built-in [MCP server](https://modelcontextprotocol.io/) for AI coding assistants (Cursor, Claude Code, VS Code Github Copilot, Windsurf, AntiGravity, etc...)

---

## Quick Links

- **PyPI:** [pypi.org/project/geeViz](https://pypi.org/project/geeViz/)
- **Docs/Home:** [geeviz.org](https://geeviz.org/)
- **Notebooks & Scripts:** [`examples/`](examples)
- **Community Repo:** [github.com/gee-community/geeViz](https://github.com/gee-community/geeViz)
- **Forest Service GitHub:** [code.fs.usda.gov/forest-service/geeViz](https://code.fs.usda.gov/forest-service/geeViz)

<details>
  <summary><b>JavaScript Version & Related Links</b></summary>

- [GEE Playground Module](https://earthengine.googlesource.com/users/aaronkamoske/GTAC-Modules)  
- [JS Modules on GitHub](https://github.com/rcr-usfs/gtac-rcr-gee-js-modules.git)  
- [Forest Service JS Repo](https://code.fs.usda.gov/forest-service/gtac-gee-js-modules.git)
</details>

---

## Documentation & Help

- [geeViz Documentation and API Reference](https://geeviz.org/)
- See [`examples/`](examples) for Jupyter/Colab notebooks and scripts.
- Need help? Email us at [info@geeviz.org](mailto:info@geeviz.org).

---

## Installation

The fastest way to get started:

1. **Sign up for [Google Earth Engine](https://signup.earthengine.google.com/#!/)**
2. **Install geeViz via pip:**
    ```sh
    pip install geeViz
    ```
3. **Authenticate your Google account with Earth Engine:**
    ```sh
    earthengine authenticate
    ```

---

<details>
  <summary><b>Manual / Advanced Installation</b></summary>

1. Install the Earth Engine Python API if not present:
    ```sh
    pip install earthengine-api
    ```

2. Clone this repository:
    ```sh
    git clone https://github.com/gee-community/geeViz
    ```

3. Optionally, add or symlink the `geeViz` folder to your Python site-packages.

4. To update to the latest version:
    ```sh
    pip install geeViz --upgrade
    ```
    or, if installed via Git:
    ```sh
    git pull origin master
    ```

_geeViz is also mirrored at [code.fs.usda.gov/forest-service/geeViz](https://code.fs.usda.gov/forest-service/geeViz)._
</details>

---

## AI-Assisted Development (MCP)

geeViz includes a built-in [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server with **32 tools** that give AI coding assistants live access to geeViz and Google Earth Engine. Instead of generating code from training data (which is often wrong or outdated), your AI assistant can look up real function signatures, read actual example scripts, execute and test code, inspect assets, export data, manage tasks, and more.

Works with **Cursor**, **Claude Code**, **VS Code with GitHub Copilot**, **Windsurf**, and any MCP-compatible client. The `mcp` SDK is included as a dependency — no extra install needed.

### Quick setup

1. Add a config file for your editor (see [MCP Server docs](https://geeviz.org/mcp_server.html)):
    ```json
    {
      "mcpServers": {
        "geeviz": {
          "command": "python",
          "args": ["-m", "geeViz.mcp.server"]
        }
      }
    }
    ```
2. Copy the agent instructions from `geeViz/mcp/agent-instructions.md` into your editor's instructions file (`.github/copilot-instructions.md`, `.cursorrules`, `CLAUDE.md`, or `.windsurfrules`).

### What the MCP server can do

The 32 tools are organized into nine categories:

| Category | Tools |
|----------|-------|
| **Code Execution** | `run_code` — persistent REPL with `ee`, `Map`, `gv`, `gil`, `sal` pre-loaded; `get_namespace` — inspect live variables; `save_notebook` — export session as `.ipynb` |
| **API Introspection** | `get_api_reference` — function signatures & docstrings; `list_functions` — browse module contents; `get_example` / `list_examples` — read example scripts |
| **Dataset Discovery** | `search_datasets` — keyword search across official & community catalogs; `get_dataset_info` — full STAC metadata for any dataset |
| **Asset Inspection** | `inspect_asset` — bands, CRS, scale, date range, properties; `list_assets` — browse GEE folders; `get_collection_info` — image count, date range, bands |
| **Visualization** | `get_thumbnail` — PNG for images, animated GIF for collections; `geocode` — place name to coordinates with optional boundary search |
| **Exports** | `export_to_asset`, `export_to_drive`, `export_to_cloud_storage` — using geeViz wrappers with sensible defaults |
| **Task Management** | `track_tasks` — check task status; `cancel_tasks` — cancel by name or all |
| **Zonal Summary & Charting** | `extract_and_chart` — extract values and chart `ee.Image` or `ee.ImageCollection` over a point/region; supports point sampling, bar charts, time series, Sankey diagrams, and grouped bar charts via `geeViz.chartingLib` |
| **Asset Management** | `create_folder`, `delete_asset`, `copy_asset`, `move_asset`, `update_acl` — manage GEE assets and permissions |
| **Environment** | `get_version_info`, `get_project_info` |

For the complete tool reference, architecture details, and usage examples, see the **[MCP Server README](mcp/README.md)** and the [online MCP Server guide](https://geeviz.org/mcp_server.html).

---

## Getting Started

geeViz comes with ready-to-run examples and templates for fast onboarding.

<table>
<tr><td>

### Example: Launch in Python

Authenticate and then try:
```python
from geeViz.examples import geeViewExample
```

Explore other examples:
```python
from geeViz.examples import timeLapseExample
from geeViz.examples import getLandsatWrapper
from geeViz.examples import getSentinel2Wrapper
from geeViz.examples import getCombinedLandsatSentinel2Wrapper
from geeViz.examples import harmonicRegressionWrapper
from geeViz.examples import LANDTRENDRWrapper
from geeViz.examples import LANDTRENDRViz
from geeViz.examples import CCDCViz
from geeViz.examples import lcmsViewerExample
from geeViz.examples import LCMAP_and_LCMS_Viewer
from geeViz.examples import phEEnoVizWrapper
from geeViz.examples import GFSTimeLapse
```
</td></tr>
</table>

---

### Use with Jupyter & Colab

- Interactive notebooks are in the [`examples/`](examples) directory ([see docs ➔](https://geeviz.org/tutorials/getting-started/)).
- The geeViz map viewer also works directly inside Jupyter and [Google Colab](https://colab.research.google.com/).

---

### Features at a Glance

- **One line mapping:** Map any GEE image or collection instantly
- **Interactive:** Toggle layers, set opacity, area/point query, and chart
- **Dynamic Time-Lapses:** Animate temporal stacks and export GIFs
- **No JavaScript required:** Pure Python interface

---

## Contributing

We love contributions and new users!

- Share a GEE script, notebook, or suggestion?  
  [info@geeviz.org](mailto:info@geeviz.org)
- Pull requests & feature requests:  
  [github.com/gee-community/geeViz](https://github.com/gee-community/geeViz)

---

## License

geeViz is released under the [Apache 2.0 License](https://www.apache.org/licenses/LICENSE-2.0).  
See the [LICENSE](LICENSE) file for details.
