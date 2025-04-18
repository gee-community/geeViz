"""
Take data from GEE to Pandas and back

geeViz.gee2Pandas facilitates converting GEE objects to tabular formats that work well in more common packages such as Pandas.  

"""

"""
   Copyright 2025 Ian Housman

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

# --------------------------------------------------------------------------
#           Module to use GEE's online compute capabilities to take data from GEE into more universal environments such as Pandas
# --------------------------------------------------------------------------
import geeViz.geeView
import sys, ee, os, shutil, subprocess, datetime, calendar, json, glob, numpy, pandas
import time, logging, pdb
from simpledbf import Dbf5


#########################################################################
def featureCollection_to_json(featureCollection, output_json_name, overwrite=False, maxNumberOfFeatures=5000):
    """
    Converts a Google Earth Engine (GEE) FeatureCollection to a JSON file.

    If the output JSON file already exists and `overwrite` is False, the function reads the existing file.
    Otherwise, it converts the FeatureCollection to JSON and writes it to the specified file.

    Args:
        featureCollection (ee.FeatureCollection): The GEE FeatureCollection to convert.
        output_json_name (str): The path to the output JSON file.
        overwrite (bool, optional): Whether to overwrite the existing file. Defaults to False.
        maxNumberOfFeatures (int, optional): Maximum number of features to include. Defaults to 5000.

    Returns:
        dict: The JSON representation of the FeatureCollection.

    Example:
        >>> from geeViz.gee2Pandas import featureCollection_to_json
        >>> fc = ee.FeatureCollection("TIGER/2018/States").limit(10)
        >>> output_json = "states.json"
        >>> json_data = featureCollection_to_json(fc, output_json, overwrite=True)
        >>> print(json_data)
    """
    if not os.path.exists(output_json_name) or overwrite:
        print("Converting featureCollection to json:", os.path.basename(output_json_name))
        t = featureCollection.limit(maxNumberOfFeatures).getInfo()
        o = open(output_json_name, "w")
        o.write(json.dumps(t))
        o.close()
    else:
        print(
            "Already converted featureCollection to json:",
            os.path.basename(output_json_name),
        )
        o = open(output_json_name, "r")
        t = json.load(o)
        o.close()
    return t


#########################################################################
def featureCollection_to_csv(featureCollection, output_csv_name, overwrite=False):
    """
    Converts a GEE FeatureCollection to a CSV file.

    If the output CSV file already exists and `overwrite` is False, the function skips the conversion.
    Otherwise, it converts the FeatureCollection to a Pandas DataFrame and writes it to a CSV file.

    Args:
        featureCollection (ee.FeatureCollection): The GEE FeatureCollection to convert.
        output_csv_name (str): The path to the output CSV file.
        overwrite (bool, optional): Whether to overwrite the existing file. Defaults to False.

    Example:
        >>> from geeViz.gee2Pandas import featureCollection_to_csv
        >>> fc = ee.FeatureCollection("TIGER/2018/States").limit(10)
        >>> output_csv = "states.csv"
        >>> featureCollection_to_csv(fc, output_csv, overwrite=True)
    """
    if not os.path.exists(output_csv_name) or overwrite:
        df = robust_featureCollection_to_df(featureCollection)
        print("Writing:", output_csv_name)
        df.to_csv(output_csv_name, index=False)
    else:
        print(output_csv_name, " already exists")


#########################################################################
def robust_featureCollection_to_df(featureCollection, sep="___"):
    """
    Converts a GEE FeatureCollection to a Pandas DataFrame.

    Handles the 5000-feature limit by slicing the FeatureCollection into manageable chunks.
    This function is memory-intensive and may fail for complex operations.

    Args:
        featureCollection (ee.FeatureCollection): The GEE FeatureCollection to convert.
        sep (str, optional): Separator for nested property names. Defaults to "___".

    Returns:
        pandas.DataFrame: The resulting DataFrame.

    Example:
        >>> from geeViz.gee2Pandas import robust_featureCollection_to_df
        >>> fc = ee.FeatureCollection("TIGER/2018/States").limit(10)
        >>> df = robust_featureCollection_to_df(fc)
        >>> print(df.head())
    """
    maxFeatures = 5000
    nFeatures = featureCollection.size().getInfo()
    featureCollection = featureCollection.toList(1000000, 0)
    out_df = []
    for start in range(0, nFeatures, maxFeatures):
        end = start + maxFeatures
        if end > nFeatures:
            end = nFeatures
        print(f"Converting features {start+1}-{end}")
        fcT = ee.FeatureCollection(featureCollection.slice(start, end))
        features = fcT.getInfo()["features"]
        df = pandas.json_normalize(features, sep=sep)
        out_df.append(df)

    out_df = pandas.concat(out_df)

    properties = out_df.columns
    properties_out = [prop.replace(f"properties{sep}", "") for prop in properties]
    properties_out = [prop.replace(f"geometry{sep}", "geometry.") for prop in properties_out]
    prop_dict = dict(zip(properties, properties_out))
    out_df = out_df.rename(columns=prop_dict)

    return out_df


#########################################################################
def geeToLocalZonalStats(
    zones,
    raster,
    output_csv,
    reducer=ee.Reducer.first(),
    scale=None,
    crs=None,
    transform=None,
    tileScale=4,
    overwrite=False,
    maxNumberOfFeatures=5000,
):
    """
    Computes zonal statistics in GEE and saves the results to a local CSV file.

    Args:
        zones (ee.FeatureCollection): The zones over which to compute statistics.
        raster (ee.Image): The raster image to analyze.
        output_csv (str): The path to the output CSV file.
        reducer (ee.Reducer, optional): The reducer to apply. Defaults to ee.Reducer.first().
        scale (float, optional): The scale in meters for the analysis. Defaults to None.
        crs (str, optional): The coordinate reference system. Defaults to None.
        transform (list, optional): The affine transform. Defaults to None.
        tileScale (int, optional): Tile scale for computation. Defaults to 4.
        overwrite (bool, optional): Whether to overwrite the existing file. Defaults to False.
        maxNumberOfFeatures (int, optional): Maximum number of features to include. Defaults to 5000.

    Example:
        >>> from geeViz.gee2Pandas import geeToLocalZonalStats
        >>> zones = ee.FeatureCollection("TIGER/2018/States").limit(5)
        >>> raster = ee.Image("USGS/NLCD/NLCD2016").select("landcover")
        >>> output_csv = "zonal_stats.csv"
        >>> geeToLocalZonalStats(zones, raster, output_csv, scale=30, overwrite=True)
    """
    table = raster.reduceRegions(zones, reducer, scale, crs, transform, tileScale)
    featureCollection_to_csv(table, output_csv, overwrite)


#########################################################################
def df_to_geojson(
    df,
    properties=None,
    geometry_type_fieldname="geometry.type",
    geometry_coordinates_fieldname="geometry.coordinates",
):
    """
    Converts a Pandas DataFrame to a GeoJSON object.

    Assumes point location geometry. Adapted from: https://notebook.community/captainsafia/nteract/applications/desktop/example-notebooks/pandas-to-geojson

    Args:
        df (pandas.DataFrame): The DataFrame to convert.
        properties (list, optional): List of property column names to include. Defaults to None.
        geometry_type_fieldname (str, optional): Column name for geometry type. Defaults to "geometry.type".
        geometry_coordinates_fieldname (str, optional): Column name for geometry coordinates. Defaults to "geometry.coordinates".

    Returns:
        dict: The GeoJSON object.

    Example:
        >>> import pandas as pd
        >>> from geeViz.gee2Pandas import df_to_geojson
        >>> data = {
        ...     "geometry.type": ["Point", "Point"],
        ...     "geometry.coordinates": ['[-65.8491, 18.2233]', '[-66.1057, 18.4655]'],
        ...     "name": ["Location1", "Location2"],
        ... }
        >>> df = pd.DataFrame(data)
        >>> geojson = df_to_geojson(df)
        >>> print(geojson)
    """
    geojson = {"type": "FeatureCollection", "features": []}

    if properties == [] or properties == None:
        properties = [col for col in df.columns if col not in [geometry_type_fieldname, geometry_coordinates_fieldname]]

    for _, row in df.iterrows():
        if not pandas.isnull(row[geometry_type_fieldname]) and not pandas.isnull(row[geometry_coordinates_fieldname]):
            feature = {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": row[geometry_type_fieldname],
                    "coordinates": json.loads(row[geometry_coordinates_fieldname]),
                },
            }

            for prop in properties:
                p = row[prop]
                if pandas.isnull(p):
                    p = "NA"
                feature["properties"][prop] = p

            geojson["features"].append(feature)

    return geojson


####################################################################################################
def tableToFeatureCollection(
    table_path,
    properties=None,
    dateCol=None,
    groupByColumns=None,
    mode=None,
    geometry_type_fieldname="geometry.type",
    geometry_coordinates_fieldname="geometry.coordinates",
):
    """
    Converts a table to a GEE FeatureCollection.

    Supports Excel, CSV, and Pickle input table formats.

    Args:
        table_path (str): Path to the input table.
        properties (list, optional): List of property column names to include. Defaults to None.
        dateCol (str, optional): Column name for date. Defaults to None.
        groupByColumns (list, optional): Columns to group by. Defaults to None.
        mode (str, optional): Input table format. Defaults to None.
        geometry_type_fieldname (str, optional): Column name for geometry type. Defaults to "geometry.type".
        geometry_coordinates_fieldname (str, optional): Column name for geometry coordinates. Defaults to "geometry.coordinates".

    Returns:
        ee.FeatureCollection: The resulting FeatureCollection.

    Example:
        >>> from geeViz.gee2Pandas import tableToFeatureCollection
        >>> table_path = "locations.csv"
        >>> fc = tableToFeatureCollection(table_path, mode="csv")
        >>> print(fc.getInfo())
    """
    mode_dict = {
        ".csv": "csv",
        ".xls": "excel",
        ".xlsx": "excel",
        ".pkl": "pickle",
        ".pickle": "pickle",
    }
    if mode == None:
        try:
            mode = mode_dict[os.path.splitext(table_path)[1]]
        except:
            mode = ""
    if mode.lower() == "excel":
        df = pandas.read_excel(table_path)
    elif mode.lower() == "csv":
        df = pandas.read_csv(table_path)
    elif mode.lower() == "pickle":
        df = pandas.read_pickle(table_path)
    else:
        raise Exception("Table format not recognized. Support formats are: {}".format(",".join(list(mode_dict.keys()))))

    if dateCol == None:
        for c in df.columns[df.dtypes == "datetime64[ns]"]:
            df[c] = df[c].dt.strftime("%Y-%m-%d")
    else:
        df[dateCol] = pandas.to_datetime(df[dateCol]).astype(str)

    if groupByColumns != None:
        df = df.groupby(groupByColumns).sum(numeric_only=True).reset_index()

    df_json = df_to_geojson(
        df,
        properties,
        geometry_type_fieldname=geometry_type_fieldname,
        geometry_coordinates_fieldname=geometry_coordinates_fieldname,
    )

    df_fc = ee.FeatureCollection(df_json)
    return df_fc


#########################################################################
def dfToJSON(dbf, outJsonFilename):
    """
    Converts a DBF file to a JSON file.

    Args:
        dbf (str): Path to the DBF file.
        outJsonFilename (str): Path to the output JSON file.

    Returns:
        dict: The JSON representation of the DBF file.

    Example:
        >>> from geeViz.gee2Pandas import dfToJSON
        >>> dbf_path = "data.dbf"
        >>> json_path = "data.json"
        >>> json_data = dfToJSON(dbf_path, json_path)
        >>> print(json_data)
    """
    dbf = Dbf5(dbf)
    df = dbf.to_dataframe()

    columns = df.columns
    rows = df.transpose().to_numpy()
    outJson = {}
    for i, c in enumerate(columns):
        outJson[c] = list(rows[i])

    o = open(outJsonFilename, "w")
    o.write(json.dumps(outJson))
    o.close()
    return outJson


#########################################################################
def setDFTitle(df, title):
    """
    Sets a title for a Pandas DataFrame.

    Args:
        df (pandas.DataFrame): The DataFrame to modify.
        title (str): The title to set.

    Returns:
        pandas.io.formats.style.Styler: The styled DataFrame.

    Example:
        >>> import pandas as pd
        >>> from geeViz.gee2Pandas import setDFTitle
        >>> data = {"A": [1, 2], "B": [3, 4]}
        >>> df = pd.DataFrame(data)
        >>> styled_df = setDFTitle(df, "Sample DataFrame")
        >>> print(styled_df)
    """
    styles = [
        dict(
            selector="caption",
            props=[
                ("text-align", "left"),
                ("font-size", "150%"),
                ("font-weight", "bold"),
            ],
        )
    ]

    df = df.style.set_caption(title).set_table_styles(styles)
    return df


def imageArrayPixelToDataFrame(
    img,
    pt,
    scale=None,
    crs=None,
    transform=None,
    title=None,
    index=None,
    columns=None,
    bandName=None,
    reducer=ee.Reducer.first(),
    arrayImage=None,
):
    """
    Converts pixel values from an image array to a Pandas DataFrame.

    Args:
        img (ee.Image): The image to extract values from.
        pt (ee.Geometry.Point): The point location.
        scale (float, optional): The scale in meters for the analysis. Defaults to None.
        crs (str, optional): The coordinate reference system. Defaults to None.
        transform (list, optional): The affine transform. Defaults to None.
        title (str, optional): Title for the DataFrame. Defaults to None.
        index (list, optional): Index for the DataFrame. Defaults to None.
        columns (list, optional): Columns for the DataFrame. Defaults to None.
        bandName (str, optional): Band name for array images. Defaults to None.
        reducer (ee.Reducer, optional): Reducer to apply. Defaults to ee.Reducer.first().
        arrayImage (bool, optional): Whether the image is an array image. Defaults to None.

    Returns:
        pandas.DataFrame: The resulting DataFrame.

    Example:
        >>> from geeViz.gee2Pandas import imageArrayPixelToDataFrame
        >>> img = ee.Image([1, 2, 3])
        >>> pt = ee.Geometry.Point([-65.8491, 18.2233])
        >>> df = imageArrayPixelToDataFrame(img, pt, scale=30)
        >>> print(df)
    """
    vals = img.reduceRegion(reducer, pt, scale=scale, crs=crs, crsTransform=transform).getInfo()

    if arrayImage == None:
        if type(list(vals.values())[0]) == list:
            arrayImage = True
        else:
            arrayImage = False

    if arrayImage:
        if bandName == None:
            bandName = list(vals.keys())[0]

        vals = vals[bandName]
        df = pandas.DataFrame(vals, columns=columns, index=index)
    else:
        df = pandas.DataFrame(list(vals.values()), columns=["Values"], index=list(vals.keys()))

    if title != None:
        df = setDFTitle(df, title)
    return df


def extractPointImageValues(
    ee_image,
    pt,
    scale=None,
    crs=None,
    transform=None,
    reducer=ee.Reducer.first(),
    includeNonSystemProperties=False,
    includeSystemProperties=True,
):
    """
    Extracts values from a GEE image at a specific point.

    Args:
        ee_image (ee.Image): The image to extract values from.
        pt (ee.Geometry.Point): The point location.
        scale (float, optional): The scale in meters for the analysis. Defaults to None.
        crs (str, optional): The coordinate reference system. Defaults to None.
        transform (list, optional): The affine transform. Defaults to None.
        reducer (ee.Reducer, optional): Reducer to apply. Defaults to ee.Reducer.first().
        includeNonSystemProperties (bool, optional): Whether to include non-system properties. Defaults to False.
        includeSystemProperties (bool, optional): Whether to include system properties. Defaults to True.

    Returns:
        ee.Dictionary: The extracted values.

    Example:
        >>> from geeViz.gee2Pandas import extractPointImageValues
        >>> img = ee.Image([1, 2, 3])
        >>> pt = ee.Geometry.Point([-65.8491, 18.2233])
        >>> values = extractPointImageValues(img, pt, scale=30)
        >>> print(values.getInfo())
    """
    ee_image = ee.Image(ee_image)
    system_props = ee_image.toDictionary(["system:index", "system:time_start", "system:time_end"])
    props = ee_image.toDictionary()
    vals = ee.Image(ee_image).reduceRegion(reducer, pt, scale=scale, crs=crs, crsTransform=transform)
    if includeNonSystemProperties and includeSystemProperties:
        props = system_props.combine(props)
        return props.combine(vals)
    elif includeNonSystemProperties and not includeSystemProperties:
        return props.combine(vals)
    elif not includeNonSystemProperties and includeSystemProperties:
        return system_props.combine(vals)
    else:
        return vals


def extractPointValuesToDataFrame(
    ee_object,
    pt,
    scale=None,
    crs=None,
    transform=None,
    title=None,
    index=None,
    columns=None,
    bandName=None,
    reducer=ee.Reducer.first(),
    includeNonSystemProperties=False,
    includeSystemProperties=True,
):
    """
    Extracts values from a GEE object at a specific point and converts them to a Pandas DataFrame.

    Args:
        ee_object (ee.Image or ee.ImageCollection): The GEE object to extract values from.
        pt (ee.Geometry.Point): The point location.
        scale (float, optional): The scale in meters for the analysis. Defaults to None.
        crs (str, optional): The coordinate reference system. Defaults to None.
        transform (list, optional): The affine transform. Defaults to None.
        title (str, optional): Title for the DataFrame. Defaults to None.
        index (list, optional): Index for the DataFrame. Defaults to None.
        columns (list, optional): Columns for the DataFrame. Defaults to None.
        bandName (str, optional): Band name for array images. Defaults to None.
        reducer (ee.Reducer, optional): Reducer to apply. Defaults to ee.Reducer.first().
        includeNonSystemProperties (bool, optional): Whether to include non-system properties. Defaults to False.
        includeSystemProperties (bool, optional): Whether to include system properties. Defaults to True.

    Returns:
        pandas.DataFrame: The resulting DataFrame.

    Example:
        >>> from geeViz.gee2Pandas import extractPointValuesToDataFrame
        >>> img = ee.Image([1, 2, 3])
        >>> pt = ee.Geometry.Point([-65.8491, 18.2233])
        >>> df = extractPointValuesToDataFrame(img, pt, scale=30)
        >>> print(df)
    """
    if isinstance(ee_object, ee.imagecollection.ImageCollection):
        vals = (
            ee_object.toList(10000, 0)
            .map(
                lambda ee_image: extractPointImageValues(
                    ee_image,
                    pt,
                    scale=scale,
                    crs=crs,
                    transform=transform,
                    reducer=reducer,
                    includeNonSystemProperties=includeNonSystemProperties,
                    includeSystemProperties=includeSystemProperties,
                )
            )
            .getInfo()
        )

    elif isinstance(ee_object, ee.image.Image):
        vals = extractPointImageValues(
            ee_object,
            pt,
            scale=scale,
            crs=crs,
            transform=transform,
            reducer=reducer,
            includeNonSystemProperties=includeNonSystemProperties,
            includeSystemProperties=includeSystemProperties,
        ).getInfo()

    return pandas.json_normalize(vals)


####################################################################################################
if __name__ == "__main__":
    output_dir = r"C:\tmp\geeToPandasTest"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    pt = ee.Geometry.Point([-65.8491, 18.2233])
    comps = ee.ImageCollection("projects/rcr-gee/assets/lcms-training/lcms-training_module-2_composites")
    lt = ee.ImageCollection("projects/rcr-gee/assets/lcms-training/lcms-training_module-3_landTrendr")
