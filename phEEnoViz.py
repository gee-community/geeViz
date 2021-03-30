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
#Script to help visualize variability of observations across space and time
#Intended to work within the geeViz package
######################################################################
from geeViz.getImagesLib import *
import os,json, pdb,glob,math,threading,time
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import date
###############################################################
def check_dir(dir):
  if not os.path.exists(dir):os.makedirs(dir)
###############################################################
def limitThreads(limit):
  while threading.activeCount() > limit:
    time.sleep(1)
    print(threading.activeCount(),'threads running')
###############################################################
#Function to extract a json table of zonal stats from an image 
def getTableWrapper(image,fc, outputName,reducer = ee.Reducer.first(),scale = 30,crs = 'EPSG:4326',transform = None,tryNumber = 1,maxTries = 15):
  #get zonal stats and export
  table = image.reduceRegions(\
      fc,\
      reducer, \
      scale, \
      crs,\
      transform, \
      4)
  try:
    print('Exporting table:',outputName)
    t = table.getInfo()
    o = open(outputName,'w')
    o.write(json.dumps(t))
    o.close()
    convert_to_csv(outputName)
  except Exception as e:
    print('Error encountered:',e)
    tryNumber += 1
    if tryNumber < maxTries:
      print('Trying to convert table again. Try number:',tryNumber)
      getTableWrapper(image,fc, outputName,reducer,scale,crs,transform,tryNumber,maxTries)
###############################################################
#Wrapper to get a sample of locations for a given area
def getTimeSeriesSample(startYear,endYear,startJulian,endJulian,compositePeriod,exportBands,studyArea,nSamples,output_table_name,showGEEViz,maskSnow = False):
  check_dir(os.path.dirname(output_table_name))
  #If available, bring in preComputed cloudScore offsets and TDOM stats
  #Set to null if computing on-the-fly is wanted
  #These have been pre-computed for all CONUS for Landsat and Setinel 2 (separately)
  #and are appropriate to use for any time period within the growing season
  #The cloudScore offset is generally some lower percentile of cloudScores on a pixel-wise basis
  preComputedCloudScoreOffset = getPrecomputedCloudScoreOffsets(10)
  preComputedLandsatCloudScoreOffset = preComputedCloudScoreOffset['landsat']
  preComputedSentinel2CloudScoreOffset = preComputedCloudScoreOffset['sentinel2']

  #The TDOM stats are the mean and standard deviations of the two bands used in TDOM
  #By default, TDOM uses the nir and swir1 bands
  preComputedTDOMStats = getPrecomputedTDOMStats()
  preComputedLandsatTDOMIRMean = preComputedTDOMStats['landsat']['mean']
  preComputedLandsatTDOMIRStdDev = preComputedTDOMStats['landsat']['stdDev']

  preComputedSentinel2TDOMIRMean = preComputedTDOMStats['sentinel2']['mean']
  preComputedSentinel2TDOMIRStdDev = preComputedTDOMStats['sentinel2']['stdDev']

  #####################################################################################
  #Function Calls
  #Get all images
  try:
    saBounds = studyArea.geometry().bounds()
  except:
    saBounds = studyArea.bounds()

  #Sample the study area
  randomSample = ee.FeatureCollection.randomPoints(studyArea, nSamples, 0, 50)
  Map.addLayer(randomSample,{},'Samples',True)

  dummyImage = ee.Image(getProcessedLandsatAndSentinel2Scenes(saBounds,\
            2019,\
            2020,\
            1,\
            365).first())
  for yr in range(startYear,endYear+1):
    output_table_nameT = '{}_{}_{}-{}_{}_{}{}'.format(os.path.splitext(output_table_name)[0], yr,startJulian,endJulian,compositePeriod,nSamples,os.path.splitext(output_table_name)[1])
    if not os.path.exists(output_table_nameT):
      images = getProcessedLandsatAndSentinel2Scenes(saBounds,\
            yr,\
            yr,\
            startJulian,\
            endJulian,\
            toaOrSR = 'TOA',
            includeSLCOffL7 = True,
            defringeL5 = False,
            applyQABand = False,
            applyCloudProbability = True,
            applyShadowShift = False,
            applyCloudScoreLandsat = False,
            applyCloudScoreSentinel2 = False,
            applyTDOMLandsat = True,
            applyTDOMSentinel2 = True,
            applyFmaskCloudMask = True,
            applyFmaskCloudShadowMask = True,
            applyFmaskSnowMask = False,
            cloudHeights = ee.List.sequence(500,10000,500),
            cloudScoreThresh = 20,
            performCloudScoreOffset = True,
            cloudScorePctl = 10,
            zScoreThresh = -1,
            shadowSumThresh = 0.35,
            contractPixels = 1.5,
            dilatePixels = 3.5,
            shadowSumBands = ['nir','swir1'],
            landsatResampleMethod = 'near',
            sentinel2ResampleMethod = 'aggregate',
            convertToDailyMosaics = True,
            runChastainHarmonization = True,
            # preComputedLandsatCloudScoreOffset = preComputedLandsatCloudScoreOffset,\
            # preComputedSentinel2CloudScoreOffset = preComputedSentinel2CloudScoreOffset,\
            # preComputedLandsatTDOMIRMean = preComputedLandsatTDOMIRMean,\
            # preComputedLandsatTDOMIRStdDev = preComputedLandsatTDOMIRStdDev,\
            # preComputedSentinel2TDOMIRMean = preComputedSentinel2TDOMIRMean,\
            # preComputedSentinel2TDOMIRStdDev = preComputedSentinel2TDOMIRStdDev
            )
      images = fillEmptyCollections(images,dummyImage)
      #Vizualize the median of the images
      # Map.addLayer(images.median(),vizParamsFalse,'Median Composite '+str(yr),False)


      #Mask snow
      if maskSnow:
        print('Masking snow')
        images = images.map(sentinel2SnowMask)


      #Add greenness ratio/indices
      images = images.map(HoCalcAlgorithm2)
      # Map.addLayer(images.select(exportBands),{},'Raw Time Series ' + str(yr),True)

      #Convert to n day composites
      composites = nDayComposites(images,yr,yr,startJulian,endJulian,compositePeriod)
      # Map.addLayer(composites.select(exportBands),{},str(compositePeriod) +' day composites '+str(yr))

      #Convert to a stack
      stack = composites.select(exportBands).toBands();

      #Fix band names to be yyyy_mm_dd
      bns = stack.bandNames()
      bns = bns.map(lambda bn: ee.String(bn).split('_').slice(1,None).join('_'))
      stack = stack.rename(bns);
      
      #Start export table thread
      tt = threading.Thread(target = getTableWrapper, args = (stack,randomSample,output_table_nameT))
      tt.start()
      time.sleep(0.1)
  
  if showGEEViz:
    #Vizualize outputs
    Map.addLayer(studyArea,{},'Study Area')
    Map.centerObject(studyArea)
    Map.view()
  limitThreads(1)


  
###############################################################
#Function to convert json gee table into csvs
#Assumes id format is bandName_yyyy-dd-mm
def convert_to_csv(output_table_name):
  with open(output_table_name) as jf:
    table = json.load(jf)
  
  #First find the bands and dates in the table
  bands = []
  dates = []
  print('Finding dates and bands in json:',output_table_name)
  for feature in table['features'][:1]:
    props = feature['properties']
    for prop in list(props.keys()):
      value = props[prop]
      band = prop.split('_')[-1]
      if band not in bands:bands.append(band)

      date = prop.split('_')[0]
      if date not in dates:dates.append(date)
      
  #For each of the bands, create a csv
  for band in bands:
    output_csv = os.path.splitext(output_table_name)[0] + '_{}.csv'.format(band)
    out_table = '{}\n'.format(','.join(dates))
    if not os.path.exists(output_csv):
      print('Parsing:',band)

      #Iterate across each feature and pull all properties and values that have that band
      for feature in table['features']:
        id = feature['id']
        values = []
        props = feature['properties']
        prop_keys = list(props.keys())
        prop_keys = [i for i in prop_keys if i.split('_')[-1] == band]
        
        for prop in prop_keys:
          value = str(props[prop])
          if value == 'None':value = ''
          values.append(value)
        out_line = '{}\n'.format(','.join(values))
        out_table += out_line

      #Write out table
      o = open(output_csv,'w')
      o.write(out_table)
      o.close()

###############################################################
#Function to take a set of csv tables with yyyy-mm-dd dates on the header row and values of a band/index from an
#area for each row (some sort of zonal stat or point location value)
#It produces a time series chart of the histogram for each date in the given table
def chartTimeSeriesDistributions(tables,output_dir,output_base_name,n_bins = 40,min_pctl = 1,max_pctl = 99,background_color = '#D6D1CA',font_color = '#1B1716',overwrite = False, howManyHarmonics = 3):
  # print(tables)
  check_dir(output_dir)

  bands = []
  for table in tables:
    band = os.path.splitext(os.path.basename(table))[0].split('_')[-1]
    if band not in bands:bands.append(band)
  for band in bands[3:4]:
    output_chart_name = os.path.join(output_dir,output_base_name + '_'+band+'.png')
    if not os.path.exists(output_chart_name) or overwrite:
      title = ' '.join(output_base_name.split('_')) + ' '+band + ' Distrubution Time Series'
      tablesT = [table for table in tables if os.path.basename(table).find(band) > -1]
      #Find the name of the band/index
      index_name = band


      print('Creating hovmuller for:',band)
      values = []
      data = pd.concat([pd.read_csv(t) for t in tablesT],axis = 1)
      columns = data.columns
      values = data.to_numpy()
     
      #Get min and max
      flat = values.flatten()
      flat = flat[~(np.isnan(flat))]
      min = np.percentile(flat,min_pctl)#flat.min()
      max = np.percentile(flat,max_pctl)#flat.max()
      values = values.clip(min,max)
      #Get dates (yyyy-mm-dd)
      dates = [i.split('_')[0] for i in columns]

      #Set up bins for histogram
      bin_step = (max-min)/n_bins
      bins = np.arange(min,max+bin_step,bin_step)

      #Get histograms for each date and clip out outlier frequency values
      hist = np.array([np.histogram(data[column], bins=bins,density = True)[0] for column in columns]).transpose()
      hist = np.nan_to_num(hist, nan=0)
      hist = hist.clip(np.percentile(hist,10),np.percentile(hist,99))
      


      #Harmonic regression fitting
      #Get table of all xs and ys
      table_xs = np.array([])
      table_ys = np.array([])
      table_all_xs = np.array([])
      d0 = date(1969, 12, 31)
      percentiles = []
      #Set up tables for harmonic regression
      for i,column in enumerate(columns):
        d = dates[i]
        d1 = date(int(d.split('-')[0]),int(d.split('-')[1]),int(d.split('-')[2]))
        delta = d1 - d0
        delta_fraction = math.modf(delta.days/365.25)[0]
        decimal_date = int(d.split('-')[0])+delta_fraction

        ys = values[:,i]
        ys = ys[~(np.isnan(ys))]
        if(len(ys) > 3):
          percentiles.append(np.percentile(ys,[0,5,25,50,75,95,100]))
        else:
          percentiles.append([np.nan,np.nan,np.nan,np.nan,np.nan,np.nan,np.nan])
        xs = np.repeat(decimal_date,len(ys))
        table_ys = np.append(table_ys,ys)
        table_xs = np.append(table_xs,xs)
        table_all_xs = np.append(table_all_xs,decimal_date)
      percentiles = np.array(percentiles)
      
      table_all_xs = np.array(table_all_xs).flatten()
      table_xs = np.array(table_xs).flatten()
      table_ys = np.array(table_ys).flatten()
 
      #Harmonic regression fit model
      xs = np.array([table_xs]).T
      sin1Term = np.sin(xs*2*math.pi)
      cos1Term = np.cos(xs*2*math.pi)
      sin2Term = np.sin(xs*4*math.pi)
      cos2Term = np.cos(xs*4*math.pi)
      sin3Term = np.sin(xs*6*math.pi)
      cos3Term = np.cos(xs*6*math.pi)
      intTerm = np.ones(xs.shape[0])
      harm_1 = np.c_[sin1Term,cos1Term,xs, intTerm] 
      harm_1_2 = np.c_[sin1Term,cos1Term,sin2Term,cos2Term,xs, intTerm]
      harm_1_2_3 = np.c_[sin1Term,cos1Term,sin2Term,cos2Term,sin3Term,cos3Term,xs, intTerm]

      harm_1_model = np.linalg.lstsq(harm_1, table_ys, rcond=None)
      harm_1_2_model = np.linalg.lstsq(harm_1_2, table_ys, rcond=None)
      harm_1_2_3_model = np.linalg.lstsq(harm_1_2_3, table_ys, rcond=None)
      
      #Apply harm model
      xs = np.array([table_all_xs]).T
      sin1Term = np.sin(xs*2*math.pi)
      cos1Term = np.cos(xs*2*math.pi)
      sin2Term = np.sin(xs*4*math.pi)
      cos2Term = np.cos(xs*4*math.pi)
      sin3Term = np.sin(xs*6*math.pi)
      cos3Term = np.cos(xs*6*math.pi)
      intTerm = np.ones(xs.shape[0])
      harm_1 = np.c_[sin1Term,cos1Term,xs, intTerm] 
      harm_1_2 = np.c_[sin1Term,cos1Term,sin2Term,cos2Term,xs, intTerm]
      harm_1_2_3 = np.c_[sin1Term,cos1Term,sin2Term,cos2Term,sin3Term,cos3Term,xs, intTerm]
      # print('beta hat:',beta_hat[0],xs)
      pred_1 = np.dot(harm_1,harm_1_model[0])
      pred_1_2 = np.dot(harm_1_2,harm_1_2_model[0])
      pred_1_2_3 = np.dot(harm_1_2_3,harm_1_2_3_model[0])
      
      pred_dict  = {'1':pred_1,
                    '2':pred_1_2,
                    '3':pred_1_2_3}

      pred = pred_dict[str(howManyHarmonics)]


      #Plot
      xTickFreq = 8#int(len(columns)/20)
      yTickFreq = 0.1
      width = (len(columns)/25)+2
      if width < 8:
        width = 12
        xTickFreq = 3
      fig = plt.figure(figsize=(width,6),frameon=True,facecolor='w')

      fig.patch.set_facecolor(background_color)
      
      params = {"ytick.color" : font_color,
              "xtick.color" : font_color,
              "axes.labelcolor" : font_color,
              "axes.edgecolor" : font_color,
              'legend.fontsize': 7,
              'legend.handlelength': 1.2}
      plt.rcParams.update(params)
   
      ax = fig.add_axes([0.06, 0.15, 0.84, 0.80])
      ax.set_title(title)
      cmap = plt.get_cmap('viridis')
      cf = plt.pcolormesh(dates, bins, hist, cmap = cmap)#, vmin = 500)
      degrees = 45
      plt.xticks(rotation=degrees, fontsize = 7)

      # print(list(zip(dates,pred,table_all_xs)))
      harm_line =plt.plot(dates, pred, linestyle = '-', color = background_color, linewidth = 2, label='Harmonic Fit ({})'.format(howManyHarmonics))
      # plt.plot(dates, percentiles[:,3], linestyle = '--', color = '#880', linewidth = 1.5,label = 'Median')
  
      ax.set_ylim([min, max])
      ax.set_ylabel('{} Value'.format(index_name), fontsize = 10)
      ax.set_xlabel('Date', fontsize = 10)

      #Set up the x and y axis tick frequencies
      ax.xaxis.set_major_locator(plt.MultipleLocator(xTickFreq))
      ax.xaxis.set_minor_locator(plt.MultipleLocator(1))
      ax.yaxis.set_major_locator(plt.MultipleLocator(yTickFreq))
      ax.yaxis.set_minor_locator(plt.MultipleLocator(1))
      
      ax.grid(True, which='major', axis='y', linestyle='--', color=font_color)
      ax.grid(True, which='major', axis='x', linestyle='--', color=font_color)

      cbax = fig.add_axes([0.93, 0.15, 0.01, 0.75])
      plt.legend(handles = harm_line, bbox_to_anchor=(-2.5, 1.08), loc='upper left')
 
      cb = plt.colorbar(cf, cax = cbax, orientation = 'vertical')
      cb.ax.tick_params(labelsize=10)
      cb.set_label('Percent of Samples (%)', rotation = 270, labelpad = 15, fontsize = 10) 


      fig.savefig(output_chart_name)
      plt.show()
      plt.close()
    else:
      print('Already produced:',output_chart_name)