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
import geeViz.geeView 
import sys, ee, os, shutil, subprocess, datetime, calendar, json,glob,numpy,pandas
import time, logging, pdb
from simpledbf import Dbf5



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
def featureCollection_to_csv(featureCollection,output_csv_name,overwrite = False):
    if not os.path.exists(output_csv_name) or overwrite:
        df = robust_featureCollection_to_df(featureCollection)
        print('Writing:',output_csv_name)
        df.to_csv(output_csv_name,index=False)
    else:
        print(output_csv_name,' already exists') 
        # # First find out if it is a file pathname or GEE featureCollection
        # # Read in if it's a json file pathname
        # # If it is a GEE featureCollection, convert it to json
        # if isinstance(featureCollection,str) and os.path.splitext(featureCollection)[1].lower().find('json') >-1:
        #     o = open(featureCollection,'r')
        #     table = json.load(o)
        #     o.close()
        # elif isinstance(featureCollection,ee.featurecollection.FeatureCollection):
        #     output_json_name = os.path.splitext(output_csv_name)[0]+'.json'
        #     table = featureCollection_to_json(featureCollection,output_json_name,overwrite,maxNumberOfFeatures)
        
        # # Set up the header
        # # Pull in ID and Lng and Lat field names if it's a point
        # if table['features'][0]['geometry']['type'] == 'Point':
        #     bands = ['ID','Lng','Lat'] 
        # else:
        #     bands = ['ID']

        # bands.extend(list(table['features'][0]['properties'].keys()))
        # header = ','.join(bands)+'\n'
        # out = header
        
        # # Iterate across each feature and pull in the id, and properties
        # for feature in table['features']:
        #     props = feature['properties']
        #     geo = feature['geometry']
        #     geoType = geo['type']
        #     ID = str(feature['id'])
        #     values = numpy.array(list(props.values()))
            
        #     if geoType == 'Point':
        #         ptCoords = geo['coordinates']
        #         values = numpy.concatenate([[ID],geo['coordinates'],values])
        #     values = ','.join([str(i) for i in values])+'\n'
        #     values = values.replace(',None',',')
        #     out+=values
        
        # o = open(output_csv_name,'w')
        # o.write(out)
        # o.close()
#########################################################################
# Function to convert GEE featureCollection to a Pandas Dataframe
# Handles the 5000 limit
# This will run into memory errors if any complex operations precede the tables creation
# In those instances, the featureCollections should first be exported to asset and then brought back in and run through
# this function
def robust_featureCollection_to_df(featureCollection,sep = '___'):
    maxFeatures = 5000
    nFeatures = featureCollection.size().getInfo()
    featureCollection = featureCollection.toList(1000000,0)
    out_df = []
    for start in range(0,nFeatures,maxFeatures):
        end = start+maxFeatures
        if end > nFeatures:end = nFeatures
        print(f'Converting features {start+1}-{end}')
        fcT = ee.FeatureCollection(featureCollection.slice(start,end))
        features = fcT.getInfo()["features"]
        df = pandas.json_normalize(features,sep = sep)
        out_df.append(df)
       
    out_df = pandas.concat(out_df)

    properties = out_df.columns
    properties_out = [prop.replace(f'properties{sep}','') for prop in properties]
    properties_out = [prop.replace(f'geometry{sep}','geometry.') for prop in properties_out]
    prop_dict = dict(zip(properties,properties_out))
    out_df = out_df.rename(columns=prop_dict)

    return out_df
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
    
    featureCollection_to_csv(table,output_csv,overwrite)
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
#########################################################################
# Show image array at a location
def setDFTitle(df,title):
    styles = [dict(selector="caption",
                       props=[("text-align", "left"),
                              ("font-size", "150%"),
                             ("font-weight", "bold")])]

    df = df.style.set_caption(title).set_table_styles(styles)
    return df
def imageArrayPixelToDataFrame(img,pt,scale=None,crs = None, transform = None,title = None,index = None,columns = None,bandName = None, reducer = ee.Reducer.first(),arrayImage = None):
    # Pull the values
    vals = img.reduceRegion(reducer,pt,scale=scale,crs = crs, crsTransform = transform).getInfo()
    
    # Determine if it is an array image
    # Only handle the first band or a single specified band if it is
    if arrayImage == None:
        if type(list(vals.values())[0])==list:
            arrayImage = True
        else:
            arrayImage = False

    if arrayImage:
        # If no band is specified, and its an array image, pull the first band
        if bandName == None:
            bandName = list(vals.keys())[0]
        
        # Get the values for the band
        vals = vals[bandName]

        # Convert to Pandas dataframe
        df = pandas.DataFrame(vals,columns = columns,index =index)

    else:
        df = pandas.DataFrame(list(vals.values()),columns = ['Values'],index =list(vals.keys()))
    # Set a title if provided
    if title != None:
        df = setDFTitle(df,title)
    return df

# Functions to extract any EE image object type to a dataframe
# Handles multi-band images (with array images as well) and image collections
# While intended for point locations using the ee.Reducer.first() reducer, it can handle polygons and multi-polygons with an appropriate reducer (e.g. ee.Reducer.mean() or ee.Reducer.median())
def extractPointImageValues(ee_image,pt,scale=None,crs = None, transform = None,reducer = ee.Reducer.first(),includeNonSystemProperties = False,includeSystemProperties=True):
    # Pull the values
    ee_image = ee.Image(ee_image)
    system_props = ee_image.toDictionary(['system:index','system:time_start','system:time_end'])
    props = ee_image.toDictionary()
    vals = ee.Image(ee_image).reduceRegion(reducer,pt,scale=scale,crs = crs, crsTransform = transform)
    if includeNonSystemProperties and includeSystemProperties:
        props = system_props.combine(props)
        return props.combine(vals)
    elif includeNonSystemProperties and not includeSystemProperties:
        return props.combine(vals)
    elif not includeNonSystemProperties and includeSystemProperties:
        return system_props.combine(vals)
    else:
        return vals
def extractPointValuesToDataFrame(ee_object,pt,scale=None,crs = None, transform = None,title = None,index = None,columns = None,bandName = None, reducer = ee.Reducer.first(),includeNonSystemProperties = False,includeSystemProperties=True):
    if isinstance(ee_object, ee.imagecollection.ImageCollection):
        vals = ee_object.toList(10000,0).map(lambda ee_image:extractPointImageValues(ee_image,pt,scale=scale,crs = crs, transform = transform,reducer = reducer,includeNonSystemProperties=includeNonSystemProperties,includeSystemProperties=includeSystemProperties)).getInfo()
        
    elif isinstance(ee_object, ee.image.Image):
        vals = extractPointImageValues(ee_object,pt,scale=scale,crs = crs, transform = transform,reducer = reducer,includeNonSystemProperties=includeNonSystemProperties,includeSystemProperties=includeSystemProperties).getInfo()
       
    return pandas.json_normalize(vals)
    
####################################################################################################
# Scratch space for testing
if __name__ == '__main__':
    output_dir = r'C:\tmp\geeToPandasTest' 
    if not os.path.exists(output_dir):os.makedirs(output_dir)
#     out_json = os.path.join(output_dir,'test_json.json')

    # out_csv = os.path.join(output_dir,'test_json.csv')
#     if not os.path.exists(output_dir):os.makedirs(output_dir)
#     fc = ee.FeatureCollection('projects/lcms-292214/assets/CONUS-LCMS/Training-Tables/Training-Tables-AnnualizedFormat_v2022/LCMS-CONUS-2015').limit(5)
#     composite = ee.ImageCollection('projects/lcms-tcc-shared/assets/Composites/Composite-Collection-yesL7-1984-2020')\
#                     .filter(ee.Filter.calendarRange(2015,2015,'year')).mosaic()
#     # fc = ee.FeatureCollection('projects/lcms-292214/assets/CONUS-Ancillary-Data/FS_District_Boundaries')
#     # print(fc.size().getInfo())

#     geeToLocalZonalStats(fc,composite,out_csv,reducer=ee.Reducer.first(),scale=30,crs='EPSG:5070',transform=None,tileScale=4,overwrite=False,maxNumberOfFeatures=500)

#     fc_test = tableToFeatureCollection(out_csv,lat='Lat', lon='Lng',properties=[],dateCol=None,groupByColumns = None)
#     print(fc_test.first().getInfo())
# #     # featureCollection_to_json(fc,out_json,overwrite=True,maxNumberOfFeatures=20)
# #     # featureCollection_to_csv(fc,out_csv,overwrite = True,maxNumberOfFeatures=500)

    # assets = ee.data.listAssets({'parent': 'projects/rcr-gee/assets/lcms-training/lcms-training_module-4_timeSync'})['assets']

    # training_data = ee.FeatureCollection([ee.FeatureCollection(asset['name']) for asset in assets]).flatten()
   
    # robust_featureCollection_to_df(training_data.limit(10))
    # featureCollection_to_csv(training_data,out_csv,overwrite = True)

    pt = ee.Geometry.Point([-65.8491, 18.2233])
    comps = ee.ImageCollection('projects/rcr-gee/assets/lcms-training/lcms-training_module-2_composites')
    lt = ee.ImageCollection('projects/rcr-gee/assets/lcms-training/lcms-training_module-3_landTrendr')\
    # .filter(ee.Filter.eq('band','NBR')).first()\
    # .select(['LandTrendr'])

    # eeObjToDataFrame(ee.Image([1,2,3]),pt,crs = 'EPSG:5070', scale=30,transform = None,title = None,index = None,
    #             columns = None,bandName = None, reducer = ee.Reducer.first())
    # extractPointValues(ee.Image.cat([ee.Image([1,2,3]).toArray(),ee.Image(1)]),pt,crs = 'EPSG:5070', scale=30,transform = None,title = None,index = None,columns = None,bandName = None, reducer = ee.Reducer.first())

    extracted = extractPointValuesToDataFrame(comps,pt,crs = 'EPSG:5070', scale=30,transform = None,title = None,index = None,columns = None,bandName = None, reducer = ee.Reducer.first(),includeNonSystemProperties = False,includeSystemProperties=True)
    print(extracted)
    # df = imagePixelToDataFrame(lt,pt,crs = 'EPSG:5070', scale=30,transform = None,index = ['year','vertex fit'],columns = None,bandName = None, reducer = ee.Reducer.first())
    # print(df)
    # df = imagePixelToDataFrame(ee.Image([1,2,3]).byte(),pt,crs = 'EPSG:5070', scale=30,transform = None)


    # print(df)
