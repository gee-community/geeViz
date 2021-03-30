# GTAC GEE Visualization Python Modules
> A repository of GEE Python code modules for general data processing, analysis, and visualization

> [Can be accessed in GitHub](https://github.com/rcr-usfs/geeViz)
> [Or within the internal Forest Service GitHub instance](https://code.fs.usda.gov/forest-service/geeViz)
> [Or within the GEE Community Repository](https://github.com/gee-community/geeViz)

> [A javaScript equivalent can be accessed in the GEE Playground](https://earthengine.googlesource.com/users/USFS_GTAC/modules)
> [on GitHub](https://github.com/rcr-usfs/gtac-rcr-gee-js-modules.git)
> [Or withing the Forest Service GitHub instance](https://code.fs.usda.gov/forest-service/gtac-gee-js-modules.git)

## Primary POCs

Ian Housman- ian.housman@usda.gov

Leah Campbell- leah.campbell@usda.gov

Bonnie Ruefenacht- bonnie.ruefenacht@usda.gov

## Installing
1. Become a trusted Google Earth Engine (GEE) tester (<https://signup.earthengine.google.com/#!/>)
2. Install package using pip (`pip install geeViz`) 
folder
3. Authenticate using the GEE cli in a cmd prompt (`earthengine authenticate`)

4. You can also install with git. If installing this way, first install the Python GEE package (`pip install earthengine-api`)
5. Then clone this repository (`git clone https://github.com/rcr-usfs/geeViz`) into your Python's site-packages 
6. To stay up to date, pull the latest commit (`git pull origin master`)
7. This repository is also available within the FS gitHub instance (<https://code.fs.usda.gov/forest-service/geeViz>)
   * To add this instance to your local git instance execute `remote add https://code.fs.usda.gov/forest-service/geeViz` in a git bash
   * Now you can pull the latest from your origin (`git pull origin master`) or github (`git pull github master`)

## Using
* Several examples are available within the examples module to help you get started. To test, enter the following command within the Python build you installed geeViz in: 
	* `from geeViz.examples import geeViewExample`

* Other examples are:
	* `from geeViz.examples import getLandsatWrapper`
	* `from geeViz.examples import getSentinel2Wrapper`
	* `from geeViz.examples import harmonicRegressionWrapper`
	* `from geeViz.examples import LANDTRENDRWrapper`
	* `from geeViz.examples import CCDCViz`
	* `from geeViz.examples import lcmsViewerExample`
	* `from geeViz.examples import phEEnoVizWrapper`

* When these examples are run, a viewer should open in your default browser.  It will show any data that was added to the map.
* Layers can be toggled on/off and opacity changed.  They can also be measured and queried under the TOOLS pane.



## Contributing
1. If contributing, contact a POC

