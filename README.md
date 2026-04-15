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
- **Inline zonal summary & charting** (`geeViz.outputLib.charts`, formerly `geeViz.chartingLib`) — run zonal stats and produce Plotly charts (time series, bar, grouped bar, donut, scatter, per-feature time series subplots, Sankey) directly in notebooks
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

### Optional: API Keys for Google Maps & Gemini

Some geeViz features (`googleMapsLib`, `outputLib.reports` LLM narratives) require API keys from Google Cloud. These are **optional** — core GEE functionality works without them.

**Gemini API Key** (for AI-generated report narratives and image interpretation):
1. Go to [Google AI Studio](https://aistudio.google.com/apikey)
2. Click **Create API Key** → select a project → copy the key

**Google Maps Platform API Key** (for geocoding, Street View, places, elevation, air quality, solar):
1. Go to [Google Cloud Console](https://console.cloud.google.com/) → select/create a project
2. Navigate to **APIs & Services** → **Credentials** → **Create Credentials** → **API Key**
3. (Recommended) Restrict the key to: Geocoding, Street View Static, Places (New), Elevation, Air Quality, Solar, Roads, Maps Static

**Store your keys** in a `.env` file in your geeViz package directory (alongside `geeView.py`):

```sh
# .env file in your geeViz package directory
GEMINI_API_KEY=your_gemini_api_key_here
GOOGLE_MAPS_PLATFORM_API_KEY=your_maps_platform_key_here
```

You can also set these as environment variables. The `.env` file is loaded automatically by `googleMapsLib` and `outputLib.reports` on import.

| Key | Used by | How to get |
|---|---|---|
| `GEMINI_API_KEY` | `googleMapsLib.interpret_image()`, `googleMapsLib.label_streetview()`, `outputLib.reports` LLM narratives | [Google AI Studio](https://aistudio.google.com/apikey) |
| `GOOGLE_MAPS_PLATFORM_API_KEY` | `googleMapsLib.geocode()`, `streetview_*()`, `search_places()`, `get_elevation()`, `get_air_quality()`, `get_solar_insights()`, etc. | [Google Cloud Console](https://console.cloud.google.com/apis/credentials) |

**Optional pip extras:**

```sh
pip install geeViz[gemini]         # Adds google-genai for AI features
pip install geeViz[segmentation]   # Adds torch + transformers for SegFormer
pip install geeViz[all]            # Everything
```

---

## AI-Assisted Development (MCP)

geeViz includes a built-in [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server with **21 tools** that give AI coding assistants live access to geeViz and Google Earth Engine. Instead of generating code from training data (which is often wrong or outdated), your AI assistant can look up real function signatures, read actual example scripts, execute and test code, inspect assets, export data, manage tasks, and more.

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

The 21 tools are organized into categories:

| Category | Tools |
|----------|-------|
| **Code Execution** | `run_code` — persistent REPL with `ee`, `Map`, `gv`, `gil`, `sal`, `tl`, `rl`, `cl` pre-loaded; `save_session` — export as `.py` or `.ipynb` |
| **API Introspection** | `get_api_reference` — function signatures & docstrings; `search_functions` — search across all modules; `examples` — list/read example scripts; `get_reference_data` — lookup reference dicts |
| **Dataset Discovery** | `search_datasets` — keyword search across official & community catalogs |
| **Asset Inspection** | `inspect_asset` — bands, CRS, scale, date range, properties; `list_assets` — browse GEE folders |
| **Map Control** | `map_control` — view, list layers, or clear the interactive map |
| **Exports** | `export_image` — export to asset, Drive, or Cloud Storage |
| **Task/Asset Management** | `track_tasks`, `cancel_tasks`, `manage_asset` (delete/copy/move/create/update ACL) |
| **Google Maps** | `get_streetview` — Street View imagery; `search_places` — places/geocoding |
| **Reports** | `create_report`, `add_report_section`, `generate_report`, `get_report_status`, `clear_report` |
| **Environment** | `env_info` — versions, namespace, project info |

Charting (`cl.summarize_and_chart()`), thumbnails (`tl.generate_thumbs()`), EDW queries (`edwLib`), and geocoding (`gm.geocode()`) are accessed via `run_code` for maximum flexibility.

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
