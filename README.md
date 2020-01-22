# GEE Visualization Python Modules
> A repository of GEE Python code modules for general data processing, analysis, and visualization

> [Can be accessed in Bitbucket](https://bitbucket.org/ihousman/geeviz)

> [Or within the FS GitHub instance](https://code.fs.usda.gov/forest-service/geeViz)

## Primary POCs

Ian Housman- ian.housman@usda.gov

Leah Campbell- leah.campbell@usda.gov

Bonnie Ruefenacht- bonnie.ruefenacht@usda.gov

## Using
1. Become a trusted Google Earth Engine (GEE) tester (<https://signup.earthengine.google.com/#!/>)
2. Install the Python GEE package (`pip install earthengine-api`)
3. Authenticate using the GEE cli in a cmd prompt (`earthengine authenticate`)
4. Install package using pip (`pip install geeViz`) or clone this repository (`git clone https://bitbucket.org/ihousman/geeviz`) into your Python's site-packages folder
5. To stay up to date, pull the latest commit (`git pull origin master`)
6. This repository is also available within the FS gitHub instance (<https://code.fs.usda.gov/forest-service/geeViz>)
   * To add this instance to your local git instance execute `remote add https://code.fs.usda.gov/forest-service/geeViz` in a git bash
   * Now you can pull the latest from your origin (`git pull origin master`) or github (`git pull github master`)
7. Several examples are available within the examples module to help you get started. To test, enter the following command within the Python build you installed geeViz in: `from geeViz.examples import geeViewExample`
8. Other examples are:
	*  `from geeViz.examples import getLandsatWrapper`
	*  `from geeViz.examples import getSentinel2Wrapper`
	*  `from geeViz.examples import harmonicRegressionWrapper`
	*  `from geeViz.examples import LANDTRENDRWrapper`
9. When these examples are run, a viewer should open in your default browser.  It will show any data that was added to the map.
![image info](./geeView/images/geeViewExampleThumb.png)


## Contributing
1. If contributing, contact a POC
2. Install git locally (<https://git-scm.com/download/win>)
3. Make sure you have the latest commit (`git pull origin master`)
4. Create and checkout a new branch (`git checkout -b branchName')
5. Make your changes
6. Add your changes (`git add .`)
7. Commit your changes (`git commit -m 'Add some fooBar'`)
8. Push to the branch (`git push origin branchName`)