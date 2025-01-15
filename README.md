# GTAC GEE Visualization Python Modules

> A repository of GEE Python code modules for general data processing, analysis, and visualization

> > geeViz is a powerful tool for exploring and analyzing Earth observation data like Landsat images within Google Earth Engine. It simplifies complex Earth Engine code into user-friendly Python functions.

> [Can be accessed from the GEE Community Repository](https://github.com/gee-community/geeViz) > [Or within the internal Forest Service GitHub instance](https://code.fs.usda.gov/forest-service/geeViz)
>
> [A javaScript equivalent can be accessed in the GEE Playground](https://earthengine.googlesource.com/users/aaronkamoske/GTAC-Modules) > [on GitHub](https://github.com/rcr-usfs/gtac-rcr-gee-js-modules.git) > [Or within the Forest Service GitHub instance](https://code.fs.usda.gov/forest-service/gtac-gee-js-modules.git)

## Primary POCs

Ian Housman- ian.housman@usda.gov

Josh Heyer- joshua.heyer@usda.gov

Bonnie Ruefenacht- bonnie.ruefenacht@usda.gov

## [Documentation (in progress)](https://geeviz.org/)

## Installing

1. Become a trusted Google Earth Engine (GEE) tester (<https://signup.earthengine.google.com/#!/>)
2. Install package using pip (`pip install geeViz`)
   folder
3. Authenticate using the GEE cli in a cmd prompt (`earthengine authenticate`)

4. You can also install with git. If installing this way, first install the Python GEE package (`pip install earthengine-api`)
5. Then clone this repository (`git clone https://github.com/gee-community/geeViz`) into your Python's site-packages
6. To stay up to date, upgrade via PIP (`pip install geeViz --upgrade`) or pull the latest commit (`git pull origin master`)
7. This repository is also available within the FS gitHub instance (<https://code.fs.usda.gov/forest-service/geeViz>)

## Using

- Several examples are available within the examples module to help you get started. To test, enter the following command within the Python build you installed geeViz in:

  - `from geeViz.examples import geeViewExample`

- Other examples are:

  - `from geeViz.examples import timeLapseExample`
  - `from geeViz.examples import getLandsatWrapper`
  - `from geeViz.examples import getSentinel2Wrapper`
  - `from geeViz.examples import getCombinedLandsatSentinel2Wrapper`
  - `from geeViz.examples import harmonicRegressionWrapper`
  - `from geeViz.examples import LANDTRENDRWrapper`
  - `from geeViz.examples import LANDTRENDRViz`
  - `from geeViz.examples import CCDCViz`
  - `from geeViz.examples import lcmsViewerExample`
  - `from geeViz.examples import LCMAP_and_LCMS_Viewer`
  - `from geeViz.examples import phEEnoVizWrapper`
  - `from geeViz.examples import LANDTRENDRViz`
  - `from geeViz.examples import GFSTimeLapse`

- These examples are a great way of getting started. In order to use them for your work, go to you Python site-packages folder `PythonNN\Lib\site-packages\geeViz`
- There are several notebook eamples also available. These are very similar to their script counterparts, but are better for learning how to use the tool.
- When these examples are run, a viewer should open in your default browser. It will show any data that was added to the map.
- Layers can be toggled on/off and opacity changed. They can also be measured and queried under the TOOLS pane.

## Contributing

1. If you have a great piece of GEE code to share, please contact a POC listed above.

## License

This project is licensed under the Apache 2 License - see the LICENSE file for details
