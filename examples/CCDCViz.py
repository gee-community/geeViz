#Example of how to visualize CCDC outputs using the Python visualization tools
#Adds change products and fitted harmonics from CCDC output to the viewer
#The general workflow for CCDC is to run the CCDCWrapper.py script, and then either utilize the harmonic model for a given date
#or to use the breaks for change detection. All of this is demonstrated in this example
####################################################################################################
import os,sys
sys.path.append(os.getcwd())

#Module imports
from  geeViz.getImagesLib import *
from geeViz.changeDetectionLib import *
Map.clearMap()
####################################################################################################
#Bring in ccdc image asset
#This is assumed to be an image of arrays that is returned from the ee.Algorithms.TemporalSegmentation.Ccdc method
ccdcImg = ee.Image('users/iwhousman/test/ChangeCollection/CCDC-Test3')

#Specify which harmonics to use when predicting the CCDC model
#CCDC exports the first 3 harmonics (1 cycle/yr, 2 cycles/yr, and 3 cycles/yr)
#If you only want to see yearly patterns, specify [1]
#If you would like a tighter fit in the predicted value, include the second or third harmonic as well [1,2,3]
whichHarmonics = [1,2,3]

#Whether to fill gaps between segments' end year and the subsequent start year to the break date
fillGaps = True

#Specify which band to use for loss and gain. 
#This is most important for the loss and gain magnitude since the year of change will be the same for all years
changeDetectionBandName = 'NDVI'
####################################################################################################
#Pull out some info about the ccdc image
startJulian = ccdcImg.get('startJulian').getInfo()
endJulian = ccdcImg.get('endJulian').getInfo()
startYear = ccdcImg.get('startYear').getInfo()
endYear = ccdcImg.get('endYear').getInfo()

#Extract the change years and magnitude
changeObj = ccdcChangeDetection(ccdcImg,changeDetectionBandName);
Map.addLayer(changeObj['highestMag']['loss']['year'],{'min':startYear,'max':endYear,'palette':lossYearPalette},'Loss Year')
Map.addLayer(changeObj['highestMag']['loss']['mag'],{'min':-0.5,'max':-0.1,'palette':lossMagPalette},'Loss Mag',False);
Map.addLayer(changeObj['highestMag']['gain']['year'],{'min':startYear,'max':endYear,'palette':gainYearPalette},'Gain Year');
Map.addLayer(changeObj['highestMag']['gain']['mag'],{'min':0.05,'max':0.2,'palette':gainMagPalette},'Gain Mag',False);

#Apply the CCDC harmonic model across a time series
#First get a time series of time images 
yearImages = getTimeImageCollection(startYear,endYear,startJulian,endJulian,0.1);

#Then predict the CCDC models
fitted = predictCCDC(ccdcImg,yearImages,fillGaps,whichHarmonics)
Map.addLayer(fitted.select(['.*_predicted']),{'opacity':0},'Fitted CCDC',True);



####################################################################################################
#Load the study region
studyArea = ccdcImg.geometry()
Map.addLayer(studyArea, {'strokeColor': '0000FF'}, "Study Area", False)
Map.centerObject(studyArea)
####################################################################################################
Map.view()