"""
   Copyright 2021 Ian Housman

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
"""

#Example of how to visualize CCDC outputs using the Python visualization tools
#Adds change products and fitted harmonics from CCDC output to the viewer
#The general workflow for CCDC is to run the CCDCWrapper.py script, and then either utilize the harmonic model for a given date
#or to use the breaks for change detection. All of this is demonstrated in this example
####################################################################################################
import os,sys
sys.path.append(os.getcwd())

#Module imports
import geeViz.getImagesLib as getImagesLib
import geeViz.changeDetectionLib as changeDetectionLib
ee = getImagesLib.ee
Map = getImagesLib.Map
Map.clearMap()
####################################################################################################
#Bring in ccdc image asset
#This is assumed to be an image of arrays that is returned from the ee.Algorithms.TemporalSegmentation.Ccdc method
ccdcImg = ee.ImageCollection("projects/CCDC/USA_V2")\
          .filter(ee.Filter.eq('spectral', 'SR')).mosaic()
# ccdcImg = ee.ImageCollection('projects/lcms-292214/assets/R8/PR_USVI/Base-Learners/CCDC-Landsat_1984_2020').mosaic()
#Specify which harmonics to use when predicting the CCDC model
#CCDC exports the first 3 harmonics (1 cycle/yr, 2 cycles/yr, and 3 cycles/yr)
#If you only want to see yearly patterns, specify [1]
#If you would like a tighter fit in the predicted value, include the second or third harmonic as well [1,2,3]
whichHarmonics = [1,2,3]

#Whether to fill gaps between segments' end year and the subsequent start year to the break date
fillGaps = False

#Specify which band to use for loss and gain. 
#This is most important for the loss and gain magnitude since the year of change will be the same for all years
changeDetectionBandName = 'NDVI'
####################################################################################################
#Pull out some info about the ccdc image
startJulian = 1
endJulian = 365
startYear = 1984
endYear = 2020

#Add the raw array image
Map.addLayer(ccdcImg,{},'Raw CCDC Output',False)

#Extract the change years and magnitude
changeObj = changeDetectionLib.ccdcChangeDetection(ccdcImg,changeDetectionBandName);
Map.addLayer(changeObj['highestMag']['loss']['year'],{'min':startYear,'max':endYear,'palette':changeDetectionLib.lossYearPalette},'Loss Year')
Map.addLayer(changeObj['highestMag']['loss']['mag'],{'min':-0.5,'max':-0.1,'palette':changeDetectionLib.lossMagPalette},'Loss Mag',False);
Map.addLayer(changeObj['highestMag']['gain']['year'],{'min':startYear,'max':endYear,'palette':changeDetectionLib.gainYearPalette},'Gain Year');
Map.addLayer(changeObj['highestMag']['gain']['mag'],{'min':0.05,'max':0.2,'palette':changeDetectionLib.gainMagPalette},'Gain Mag',False);

#Apply the CCDC harmonic model across a time series
#First get a time series of time images 
yearImages = changeDetectionLib.getTimeImageCollection(startYear,endYear,startJulian,endJulian,0.1);

#Then predict the CCDC models
fitted = changeDetectionLib.predictCCDC(ccdcImg,yearImages,fillGaps,whichHarmonics)
Map.addLayer(fitted.select(['.*_predicted']),{'opacity':0},'Fitted CCDC',True);

####################################################################################################
#Load the study region
studyArea = ccdcImg.geometry()
Map.addLayer(studyArea, {'strokeColor': '0000FF'}, "Study Area", False)
# Map.centerObject(studyArea)
####################################################################################################
Map.view()