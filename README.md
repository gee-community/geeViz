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

## 🌟 Key Features

- 🌎 Interactive Map Viewer (launches in your browser)
- 🔍 Layer toggling, opacity, visualization tools, querying, & area charting
- ⏳ Dynamic time-lapse creation from GEE `ImageCollections`
- 📈 Built-in charting & analysis tools (point/polygon, time series, area stats)
- 📝 Jupyter/Colab support and standalone scripting
- ⚡ Supports Landsat, Sentinel-2, MODIS, LCMS, LCMAP, and more
- 🏗️ Extensive examples and ready-to-run wrappers

---

## 🌍 Quick Links

- 📦 **PyPI:** [pypi.org/project/geeViz](https://pypi.org/project/geeViz/)
- 🔗 **Docs/Home:** [geeviz.org](https://geeviz.org/)
- 📝 **Notebooks & Scripts:** [`examples/`](examples)
- 👫 **Community Repo:** [github.com/gee-community/geeViz](https://github.com/gee-community/geeViz)
- 🏛️ **Forest Service GitHub:** [code.fs.usda.gov/forest-service/geeViz](https://code.fs.usda.gov/forest-service/geeViz)

<details>
  <summary><b>JavaScript Version & Related Links</b></summary>

- [GEE Playground Module](https://earthengine.googlesource.com/users/aaronkamoske/GTAC-Modules)  
- [JS Modules on GitHub](https://github.com/rcr-usfs/gtac-rcr-gee-js-modules.git)  
- [Forest Service JS Repo](https://code.fs.usda.gov/forest-service/gtac-gee-js-modules.git)
</details>

---

## 📚 Documentation & Help

- [geeViz Documentation and API Reference](https://geeviz.org/)
- See [`examples/`](examples) for Jupyter/Colab notebooks and scripts.
- Need help? Email us at [info@geeviz.org](mailto:info@geeviz.org).

---

## 🚀 Installation

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

## 🛠️ Getting Started

geeViz comes with ready-to-run examples and templates for fast onboarding.

<table>
<tr><td>

### ▶️ Example: Launch in Python

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

### 📒 Use with Jupyter & Colab

- Interactive notebooks are in the [`examples/`](examples) directory ([see docs ➔](https://geeviz.org/tutorials/getting-started/)).
- The geeViz map viewer also works directly inside Jupyter and [Google Colab](https://colab.research.google.com/).

---

### 🗺️ Features at a Glance

- **One line mapping:** Map any GEE image or collection instantly
- **Interactive:** Toggle layers, set opacity, area/point query, and chart
- **Dynamic Time-Lapses:** Animate temporal stacks and export GIFs
- **No JavaScript required:** Pure Python interface

---

## 🙌 Contributing

We love contributions and new users!

- Share a GEE script, notebook, or suggestion?  
  📩 [info@geeviz.org](mailto:info@geeviz.org)
- Pull requests & feature requests:  
  [github.com/gee-community/geeViz](https://github.com/gee-community/geeViz)

---

## 📄 License

geeViz is released under the [Apache 2.0 License](https://www.apache.org/licenses/LICENSE-2.0).  
See the [LICENSE](LICENSE) file for details.
