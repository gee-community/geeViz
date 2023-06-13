"""
   Copyright 2023 Ian Housman

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

#--------------------------------------------------------------------------
#           Module to use GEE's online compute capabilities to take data from GEE into more universal environments such as Pandas
#--------------------------------------------------------------------------

import sys, ee, os, shutil, subprocess, datetime, calendar, json,glob,numpy,pandas
import time, logging, pdb
from simpledbf import Dbf5
try:
    z = ee.Number(1).getInfo()
except:
    print('Initializing GEE')
    ee.Initialize()
#########################################################################
# Function to convert a featureCollection to json
# If the output json file already exists, it will read it in
# Returns the json version of the featureCollection
# Currently maxNumberOfFeatures > 5000 will error out (need to handle slicing a feature list)
def featureCollection_to_json(featureCollection,output_json_name,overwrite=False,maxNumberOfFeatures=5000):
    if not os.path.exists(output_json_name) or overwrite:
        print('Converting featureCollection to json:',os.path.basename(output_json_name))
        t = featureCollection.limit(maxNumberOfFeatures).getInfo()
        o = open(output_json_name,'w')
        o.write(json.dumps(t))
        o.close()
    else:
        print('Already converted featureCollection to json:',os.path.basename(output_json_name))
        o = open(output_json_name,'r')
        t = json.load(o)
        o.close()
    return t
#########################################################################
# Convert featureCollection to csv
# Can accept geojson or GEE featureCollection as the featureCollection argument
# Will automatically create geojson version if given a gee FeatureCollection
def featureCollection_to_csv(featureCollection,output_csv_name,overwrite = False,maxNumberOfFeatures=5000):
    if not os.path.exists(output_csv_name) or overwrite:
        
        # First find out if it is a file pathname or GEE featureCollection
        # Read in if it's a json file pathname
        # If it is a GEE featureCollection, convert it to json
        if isinstance(featureCollection,str) and os.path.splitext(featureCollection)[1].lower().find('json') >-1:
            o = open(featureCollection,'r')
            table = json.load(o)
            o.close()
        elif isinstance(featureCollection,ee.featurecollection.FeatureCollection):
            output_json_name = os.path.splitext(output_csv_name)[0]+'.json'
            table = featureCollection_to_json(featureCollection,output_json_name,overwrite,maxNumberOfFeatures)
        
        # Set up the header
        # Pull in ID and Lng and Lat field names if it's a point
        if table['features'][0]['geometry']['type'] == 'Point':
            bands = ['ID','Lng','Lat'] 
        else:
            bands = ['ID']

        bands.extend(list(table['features'][0]['properties'].keys()))
        header = ','.join(bands)+'\n'
        out = header
        
        # Iterate across each feature and pull in the id, and properties
        for feature in table['features']:
            props = feature['properties']
            geo = feature['geometry']
            geoType = geo['type']
            ID = str(feature['id'])
            values = numpy.array(list(props.values()))
            
            if geoType == 'Point':
                ptCoords = geo['coordinates']
                values = numpy.concatenate([[ID],geo['coordinates'],values])
            values = ','.join([str(i) for i in values])+'\n'
            values = values.replace(',None',',')
            out+=values
        
        o = open(output_csv_name,'w')
        o.write(out)
        o.close()
#########################################################################
# Function to compute zonal stats in GEE and download results to a local csv
def geeToLocalZonalStats(zones,raster,output_csv,reducer=ee.Reducer.first(),scale=None,crs=None,transform=None,tileScale=4,overwrite=False,maxNumberOfFeatures=5000):
    table = raster.reduceRegions(\
      zones,\
      reducer, \
      scale, \
      crs,\
      transform, \
     tileScale)
    
    featureCollection_to_csv(table,output_csv,overwrite,maxNumberOfFeatures)
#########################################################################
# Function to convert a Pandas dataframe to geojson
# Assumes point location geometry
# Function taken from: https://notebook.community/captainsafia/nteract/applications/desktop/example-notebooks/pandas-to-geojson
def df_to_geojson(df, properties, lat='latitude', lon='longitude'):
    # create a new python dict to contain our geojson data, using geojson format
    geojson = {'type':'FeatureCollection', 'features':[]}

    # loop through each row in the dataframe and convert each row to geojson format
    for _, row in df.iterrows():
      if not pandas.isnull(row[lon]) and not pandas.isnull(row[lat]):
        # create a feature template to fill in
        feature = {'type':'Feature',
                    'properties':{},
                    'geometry':{'type':'Point',
                                'coordinates':[]}}

        # fill in the coordinates
        feature['geometry']['coordinates'] = [row[lon],row[lat]]

        # for each column, get the value and add it as a new feature property
        for prop in properties:
          p = row[prop]
          if pandas.isnull(p):p= 'NA'
          feature['properties'][prop] = p
        
        # add this feature (aka, converted dataframe row) to the list of features inside our dict
        
        geojson['features'].append(feature)
    
    return geojson
####################################################################################################
# Function to take the Excel HCB spreadsheet and convert it to a GEE featureCollection
# Supports Excel (mode='Excel'), CSV (mode='csv'), and Pickle (mode='pickle') input table formats
def tableToFeatureCollection(table_path,lat='Lat', lon='Lng',properties=[],dateCol=None,groupByColumns = None,mode=None):
    mode_dict = {'.csv':'csv','.xls':'excel','.xlsx':'excel','.pkl':'pickle','.pickle':'pickle'}
    if mode == None:
        try:
            mode = mode_dict[os.path.splitext(table_path)[1]]
        except:
            mode= ''
    # Read in the  table as a Pandas dataframe
    if mode.lower() == 'excel':
        df = pandas.read_excel(table_path)
    elif mode.lower() == 'csv':
        df = pandas.read_csv(table_path)
    elif mode.lower() == 'pickle':
        df = pandas.read_pickle(table_path)
    else: raise Exception('Table format not recognized. Support formats are: {}'.format(','.join(list(mode_dict.keys()))))

    # Convert the time to a user-friendly format of yyyy-mm-DD
    if dateCol == None:
        for c in df.columns[df.dtypes=='datetime64[ns]']:
            df[c]= df[c].dt.strftime('%Y-%m-%d')
    else:
        # hcb_df[dateCol]= hcb_df[dateCol].dt.strftime('%Y-%m-%d')
        df[dateCol] = pandas.to_datetime(df[dateCol]).astype(str)
    
    if groupByColumns != None:
        df = df.groupby(groupByColumns).sum(numeric_only=True).reset_index()

    # Convert the dataframe to geojson
    # Pull all non geo props if none are provided
    if properties == [] or properties == None:
        properties = [col for col in df.columns if col not in [lat,lon]]

    df_json = df_to_geojson(df, properties, lat, lon)
    
    # Read in the geojson as a GEE featureCollection
    df_fc = ee.FeatureCollection(df_json)
    return df_fc
#########################################################################
# Function to convert a dbf to json
def dfToJSON(dbf,outJsonFilename):
    dbf = Dbf5(dbf)
    df = dbf.to_dataframe()#.head()
    
    columns = df.columns
    rows = df.transpose().to_numpy()
    outJson = {}
    for i,c in enumerate(columns):
        outJson[c]=list(rows[i])

    o = open(outJsonFilename,'w')
    o.write(json.dumps(outJson))
    o.close()
    return outJson
####################################################################################################
# Scratch space for testing
if __name__ == '__main__':
    # tableToFeatureCollection(table_path,lat='Latitude', lon='Longitude',properties=[],dateCol=None,groupByColumns = None,mode='Excel')
    output_dir = r'C:\tmp\geeToPandasTest' 
    out_json = os.path.join(output_dir,'test_json.json')

    out_csv = os.path.join(output_dir,'test_json.csv')
    if not os.path.exists(output_dir):os.makedirs(output_dir)
    fc = ee.FeatureCollection('projects/lcms-292214/assets/CONUS-LCMS/Training-Tables/Training-Tables-AnnualizedFormat_v2022/LCMS-CONUS-2015').limit(5)
    composite = ee.ImageCollection('projects/lcms-tcc-shared/assets/Composites/Composite-Collection-yesL7-1984-2020')\
                    .filter(ee.Filter.calendarRange(2015,2015,'year')).mosaic()
    # fc = ee.FeatureCollection('projects/lcms-292214/assets/CONUS-Ancillary-Data/FS_District_Boundaries')
    # print(fc.size().getInfo())

    geeToLocalZonalStats(fc,composite,out_csv,reducer=ee.Reducer.first(),scale=30,crs='EPSG:5070',transform=None,tileScale=4,overwrite=False,maxNumberOfFeatures=500)

    fc_test = tableToFeatureCollection(out_csv,lat='Lat', lon='Lng',properties=[],dateCol=None,groupByColumns = None)
    print(fc_test.first().getInfo())
#     # featureCollection_to_json(fc,out_json,overwrite=True,maxNumberOfFeatures=20)
#     # featureCollection_to_csv(fc,out_csv,overwrite = True,maxNumberOfFeatures=500)