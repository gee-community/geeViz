'''
This module contains functions to query and retrieve layers from ESRI FeatureServices,
and convert them to GeoJSON or Earth Engine geometries. It also contains general processing functions for interacting with EE/GCP cloud storage objects, and spatial manipulations and queries on local data using geopandas/shapely.

'''

import ee
import json
import requests
import geopandas as gpd
from shapely.geometry import Polygon, mapping, box
import pyproj
from pyproj import CRS, Transformer
import os
import rasterio
from rasterio.merge import merge
import math
import time
import string
import traceback

# Google Cloud imports
from google.cloud import storage
from googleapiclient import discovery
import google.auth
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError



import webcolors

def get_hex(color_name):
    # returns hex with hash, e.g., '#FFFF00'
    # geeviz might want it without hash, so we can strip it
    return webcolors.name_to_hex(color_name).upper().lstrip('#')

def color_to_hex(color):
    """Convert an text color name to a hex string."""
    import matplotlib.colors as mcolors
    try:
        hex_color = mcolors.to_hex(mcolors.CSS4_COLORS[color])
        return hex_color
    except KeyError:
        print(f"Color name '{color}' not recognized. Using default '#000000'.")
        return '#000000'

def esri_to_geojson(esri_geom):
                if esri_geom["geometryType"] == "esriGeometryEnvelope":
                    g = esri_geom["geometry"]
                    coords = [
                        [g["xmin"], g["ymin"]],
                        [g["xmin"], g["ymax"]],
                        [g["xmax"], g["ymax"]],
                        [g["xmax"], g["ymin"]],
                        [g["xmin"], g["ymin"]]
                    ]
                    return {"type": "Polygon", "coordinates": [coords]}
                elif esri_geom["geometryType"] == "esriGeometryPolygon":
                    return {"type": "Polygon", "coordinates": esri_geom["geometry"]["rings"]}
                elif esri_geom["geometryType"] == "esriGeometryPoint":
                    g = esri_geom["geometry"]
                    return {"type": "Point", "coordinates": [g["x"], g["y"]]}
                else:
                    raise ValueError("Unsupported ESRI geometryType for conversion.")



def featureServiceToGeoJSON(url, 
                           f = "geojson", 
                           where = "1=1", 
                           outFields = "*", 
                           returnGeometry = "true", 
                           outSR = None,
                           geometry = None,   
                           geometryType = None,
                           geometrySR = None,
                           spatialRel = "esriSpatialRelIntersects",  # esriSpatialRelIntersects, esriSpatialRelContains, etc.
                           quiet = False ):
    """
    Query a FeatureService and return the results as a GeoJSON FeatureCollection and the ESRI JSON geometry as ee.Geometry.

    Args:
        url: str, URL of the FeatureService layer.
        f: str, output format (default "geojson").
        where: str, SQL where clause to filter features.
        outFields: str, fields to return (default "*").
        returnGeometry: str, "true" or "false" to return geometry.
        outSR: int or None, output spatial reference (EPSG code).
        geometry: various types, geometry to filter features spatially.
        geometryType: str or None, type of geometry provided.
        spatialRel: str, spatial relationship for filtering.
        quiet: bool, if True suppresses print statements.
    """
    import requests
    import json
    import time

    url = checkEndingSlash(url)
    qprint(f"Using URL: {url}")

    # Check the SR of the service
    sr_dict, epsg = get_service_sr(url)
    qprint(f"spatialReference: {sr_dict}", quiet)
    qprint(f"EPSG/WKID: {epsg}", quiet)

    # Get service metadata to find maxRecordCount
    service_info_url = f"{url}?f=json"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    try:
        info_response = requests.get(service_info_url, headers=headers)
        info_response.raise_for_status()
        service_info = info_response.json()
        max_records = service_info.get('maxRecordCount', 500)
        qprint(f"Service maxRecordCount: {max_records}", quiet)
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Could not fetch service metadata from {service_info_url}: {e}")


    # Construct params
    base_params = {
        "f": f,
        "where": where,
        "outFields": outFields,
        "returnGeometry": returnGeometry,
        "outSR": outSR,
        "resultOffset": 0,
        "resultRecordCount": max_records
        
    }

    final_geom = None

    if geometry is not None:
        try:
            if geometrySR is None:
                geometrySR = epsg
            geo_obj = geom_to_esri_json(geometry, outSR=geometrySR)
            g_json = geo_obj["geometry"]
            print("ESRI geometry for filter:", g_json)
            base_params["geometry"] = json.dumps(g_json) if not isinstance(g_json, str) else g_json
            base_params["geometryType"] = geometryType or geo_obj.get("geometryType")
            base_params["spatialRel"] = spatialRel
            final_geom = geo_obj
        except Exception as e:
            raise ValueError(f"Failed to convert geometry to ESRI JSON: {e}")   

    # Params to determine how many features there are in the service
    count_params = {
        "f": "json",
        "where": where,
        "returnCountOnly": "true",
        "outFields": None,
        "returnGeometry": None
    }

    # count_response = requests.get(url+"query", params=count_params)
    # if count_response.status_code != 200:
    #     raise Exception(f"Error fetching feature count: {count_response.status_code}")
    # total_features = count_response.json().get("count", 0)
    # qprint(f"Total features in service: {total_features}")

    # if geometry is not None and total_features > 0:
    #     count_params["geometry"] = base_params.get("geometry")
    #     count_params["geometryType"] = base_params.get("geometryType")
    #     count_params["spatialRel"] = base_params.get("spatialRel")

    #     count_response = requests.get(url+"query", params=count_params)
    #     if count_response.status_code != 200:
    #         raise Exception(f"Error fetching feature count: {count_response.status_code}")
    #     total_features = count_response.json().get("count", 0)
    #     qprint(f"Total features in service that match geometry filter: {total_features}")
    #     if total_features == 0:
    #         # make an empty geojson feature collection
    #         features_out = {
    #             "type": "FeatureCollection",
    #             "features": []
    #         }
    #         print("No features found matching the query parameters; returning empty FeatureCollection.")
    #         return features_out

    # Fetch the data
    all_features = []
    total_features_retrieved = 0

    while True:
        try:
            response = requests.get(f"{url}query", params=base_params, headers=headers, timeout=60)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            error_msg = f"Error querying feature service at offset {base_params['resultOffset']}: {e}"
            if 'response' in locals() and response is not None:
                try:
                    error_msg += f"\nServer Response: {response.text}"
                except:
                    pass
            raise RuntimeError(error_msg)
        except json.JSONDecodeError:
            raise RuntimeError(f"Failed to decode JSON from response: {response.text}")

        features = data.get('features', [])
        if not features:
            break  # No more features to fetch

        all_features.extend(features)
        num_fetched = len(features)
        total_features_retrieved += num_fetched
        qprint(f"Retrieved {num_fetched} features... (Total: {total_features_retrieved})", quiet)

        if num_fetched < max_records:
            # This was the last page
            break
        else:
            # Prepare for the next page
            base_params["resultOffset"] += max_records
            time.sleep(0.1) # Small delay to be polite to the server

    qprint(f"Total features retrieved: {len(all_features)}", quiet)

    # Clean up properties that can cause issues in GEE
    for feature in all_features:
        props = feature.get('properties', {})
        if 'SHAPE.AREA' in props:
            del props['SHAPE.AREA']
        if 'SHAPE.LEN' in props:
            del props['SHAPE.LEN']

    features_out = {
        "type": "FeatureCollection",
        "features": all_features
    }
    return features_out
    

def qprint(msg, quiet=False):
    if not quiet:
        print(msg)

def checkEndingSlash(url):
    if not url.endswith('/'):
        url += '/'
    return url

def checkEndingQuery(url):
    if not url.endswith('?'):
        url += '?'
    return url

def checkEndingExport(url):
    if not url.endswith('/exportImage?'):
        if url.endswith('/exportImage'):
            url += '?'
        else:
            url = checkEndingSlash(url)
            url += 'exportImage?'
    return url

# write a function to reproject geometry to a different CRS
# make the function flexible to handle geopandas GeoDataFrame, GeoSeries, shapely geometry, ee.Geometry
def reproject_geometry(geometry, target_crs):
    """
    Reproject geometry to target_crs. Handles GeoDataFrame, GeoSeries, Shapely geometry, ee.Geometry, bounding box, and string formats.
    """
    try:
        import geopandas as gpd
        from shapely.geometry import shape, Polygon
        from shapely.ops import transform
        import pyproj
        import ee
    except ImportError as e:
        raise ImportError("Required libraries for reprojection are not installed: geopandas, shapely, pyproj, ee") from e

    # Helper to get EPSG code from CRS
    def get_epsg(crs):
        if hasattr(crs, 'to_epsg'):
            return crs.to_epsg()
        elif isinstance(crs, int):
            return crs
        elif isinstance(crs, str) and crs.lower().startswith('epsg:'):
            return int(crs.split(':')[1])
        return None

    # GeoDataFrame
    if gpd and isinstance(geometry, gpd.GeoDataFrame):
        if geometry.crs is None:
            raise ValueError("GeoDataFrame has no CRS.")
        return geometry.to_crs(target_crs)

    # GeoSeries
    elif gpd and isinstance(geometry, gpd.GeoSeries):
        if geometry.crs is None:
            raise ValueError("GeoSeries has no CRS.")
        return geometry.to_crs(target_crs)

    # Shapely Polygon or other geometry
    elif isinstance(geometry, Polygon) or hasattr(geometry, 'geom_type'):
        # Assume geometry has .crs attribute or user provides source_crs
        source_crs = getattr(geometry, 'crs', None)
        if source_crs is None:
            raise ValueError("Shapely geometry has no CRS. Please assign .crs attribute or use GeoDataFrame/GeoSeries.")
        project = pyproj.Transformer.from_crs(get_epsg(source_crs), get_epsg(target_crs), always_xy=True).transform
        return transform(project, geometry)

    # ee.Geometry
    elif isinstance(geometry, ee.Geometry):
        # Earth Engine geometries are usually EPSG:4326
        # Use .transform() to reproject
        # Note: Earth Engine does not support arbitrary reprojection in Python API, so just return as-is or convert to GeoJSON and reproject
        geojson = geometry.getInfo()
        # Only handle Point, Polygon, MultiPolygon
        if geojson['type'] == 'Point':
            coords = geojson['coordinates']
            point = shape({'type': 'Point', 'coordinates': coords})
            # Assume source is EPSG:4326
            project = pyproj.Transformer.from_crs(4326, get_epsg(target_crs), always_xy=True).transform
            return transform(project, point)
        elif geojson['type'] == 'Polygon':
            poly = shape(geojson)
            project = pyproj.Transformer.from_crs(4326, get_epsg(target_crs), always_xy=True).transform
            return transform(project, poly)
        elif geojson['type'] == 'MultiPolygon':
            multipoly = shape(geojson)
            project = pyproj.Transformer.from_crs(4326, get_epsg(target_crs), always_xy=True).transform
            return transform(project, multipoly)
        else:
            raise TypeError(f"Unsupported ee.Geometry type: {geojson['type']}")

    # Bounding box as list/tuple
    elif isinstance(geometry, (list, tuple)) and len(geometry) == 4:
        # Assume input bbox is in EPSG:4326
        minx, miny, maxx, maxy = geometry
        project = pyproj.Transformer.from_crs(4326, get_epsg(target_crs), always_xy=True).transform
        minx2, miny2 = project(minx, miny)
        maxx2, maxy2 = project(maxx, maxy)
        return (minx2, miny2, maxx2, maxy2)

    # String bbox
    elif isinstance(geometry, str):
        # Parse string to tuple
        try:
            bbox = tuple(map(float, geometry.split(',')))
            if len(bbox) == 4:
                minx, miny, maxx, maxy = bbox
                project = pyproj.Transformer.from_crs(4326, get_epsg(target_crs), always_xy=True).transform
                minx2, miny2 = project(minx, miny)
                maxx2, maxy2 = project(maxx, maxy)
                return (minx2, miny2, maxx2, maxy2)
        except Exception:
            raise TypeError("String geometry must be a comma-separated bbox: 'minx,miny,maxx,maxy'")

    # None
    elif geometry is None:
        return None

    else:
        raise TypeError("Unsupported geometry type for reprojection.")

def geometry_to_bbox(geometry, sr = None, quiet=False):

    try:
            import geopandas as gpd
            from shapely.geometry import Polygon
            import ee
    except ImportError:
        gpd = None
        Polygon = None
        ee = None
    
    bounds = None

    # GeoDataFrame
    if gpd and isinstance(geometry, gpd.GeoDataFrame):
        if geometry.empty:
            raise ValueError("Provided GeoDataFrame is empty.")
        bounds = geometry.total_bounds
        qprint(f"Extracted bounds from GeoDataFrame: {bounds}", quiet)
        if sr is None and geometry.crs is not None:
            bboxSR = int(geometry.crs.to_epsg())
            qprint(f"Using sr from GeoDataFrame CRS: {sr}", quiet)
        elif sr is None:
            raise ValueError("No CRS found in GeoDataFrame and no 'sr' parameter was provided.")
    
    # Shapely Polygon
    elif Polygon and isinstance(geometry, Polygon):
        bounds = geometry.bounds
        qprint(f"Extracted bounds from Shapely Polygon: {bounds}", quiet)
        if sr is None and hasattr(geometry, 'crs') and geometry.crs is not None:
            sr = int(geometry.crs.to_epsg())
            qprint(f"Using bboxSR from Polygon CRS: {sr}", quiet)
        elif sr is None:
            raise ValueError("No CRS present Polygon and no 'sr' parameter was provided.")
    # GeoSeries
    elif gpd and isinstance(geometry, gpd.GeoSeries):
        bounds = geometry.total_bounds
        qprint(f"Extracted bounds from GeoSeries: {bounds}", quiet)
        if sr is None and geometry.crs is not None:
            sr = int(geometry.crs.to_epsg())
            qprint(f"Using bboxSR from GeoSeries CRS: {sr}", quiet)
        elif sr is None:
            raise ValueError("No CRS found in GeoSeries and no 'sr' parameter was provided.")
    
    # ee.Geometry
    elif isinstance(geometry, ee.Geometry):
        bounds_info = geometry.bounds().getInfo()
        coords = bounds_info['coordinates'][0]
        minx, miny = coords[0]
        maxx, maxy = coords[2]
        bounds = (minx, miny, maxx, maxy)
        qprint(f"Extracted bounds from ee.Geometry: {bounds}", quiet)
        if sr is None:
            sr = 4326  # Earth Engine geometries are usually EPSG:4326
            qprint(f"Using default bboxSR for ee.Geometry: {sr}", quiet)

    # List or tuple
    elif isinstance(geometry, (list, tuple)) and len(geometry) == 4:
        bounds = geometry
        qprint(f"Using provided bounds list/tuple: {bounds}", quiet)
        if sr is None:
            raise ValueError("No 'sr' parameter was provided for bounding box list/tuple.")
    # String
    elif isinstance(geometry, str):
        bounds = geometry
        qprint(f"Using provided bounds string: {bounds}", quiet)
        if sr is None:
            raise ValueError("No 'sr' parameter was provided for bounding box string.")
    # None
    elif geometry is None:
        raise ValueError("No geometry provided to extract bounding box.")

    else:
        raise TypeError("Unsupported geometry type for 'geometry' parameter.")
    
    return bounds, sr

def geom_to_esri_json(obj, outSR = 4326):
    """Convert various geometry types to ESRI geometry dict and reproject to outSR.

    The function accepts:
      - bbox tuple/list (minx,miny,maxx,maxy)
      - comma-separated bbox string
      - GeoJSON-like dict
      - shapely geometry
      - geopandas GeoDataFrame / GeoSeries
      - ee.Geometry

    It reprojects geometries to `outSR` (EPSG code int) where possible using pyproj + shapely.
    If the input contains a CRS (GeoDataFrame, GeoSeries), that CRS is used as the source CRS.
    For ee.Geometry and plain GeoJSON/shapely inputs without a CRS, EPSG:4326 is assumed.
    """

    import json
    import ee

    try:
        import geopandas as gpd
        from shapely.geometry import mapping, shape
        from shapely.ops import transform as shapely_transform
        import pyproj
    except Exception:
        gpd = None
        mapping = None
        shape = None
        shapely_transform = None
        pyproj = None

    def _to_shapely_and_src_epsg(o):
        """Return (shapely_geom, src_epsg) or (None, None) if not convertible."""
        # GeoDataFrame / GeoSeries
        if gpd and isinstance(o, gpd.GeoDataFrame):
            if o.crs is None:
                src = 4326
            else:
                src = int(o.crs.to_epsg())
            geom = o.unary_union
            return geom, src
        if gpd and isinstance(o, gpd.GeoSeries):
            if o.crs is None:
                src = 4326
            else:
                src = int(o.crs.to_epsg())
            geom = o.unary_union
            return geom, src

        # shapely geometry
        if shape and hasattr(o, '__geo_interface__'):
            # try to read .crs if user attached one (non-standard)
            src = getattr(o, 'crs', None) or 4326
            return o, int(src)

        # GeoJSON-like dict
        if isinstance(o, dict) and 'type' in o and 'coordinates' in o:
            geom = shape(o)
            # no CRS encoded in simple GeoJSON -> assume 4326
            return geom, 4326

        # ee.Geometry
        if 'ee' in globals() and hasattr(ee, 'Geometry') and isinstance(o, ee.Geometry):
            geojson = o.getInfo()
            geom = shape(geojson)
            return geom, 4326

        return None, None

    def _reproject_shapely(geom, src_epsg, dst_epsg):
        if src_epsg is None:
            src_epsg = 4326
        if dst_epsg is None:
            dst_epsg = 4326
        if src_epsg == dst_epsg:
            return geom
        if pyproj is None or shapely_transform is None:
            raise RuntimeError('pyproj and shapely are required for reprojection')
        transformer = pyproj.Transformer.from_crs(int(src_epsg), int(dst_epsg), always_xy=True)
        return shapely_transform(transformer.transform, geom)

    # bbox tuple/list -> envelope (assume coords already in outSR)
    if isinstance(obj, (list, tuple)) and len(obj) == 4:
        minx, miny, maxx, maxy = obj
        return {"geometry": {"xmin": minx, "ymin": miny, "xmax": maxx, "ymax": maxy, "spatialReference": {"wkid": int(outSR)}},
                "geometryType": "esriGeometryEnvelope"}

    # JSON string -> dict or bbox string
    if isinstance(obj, str):
        try:
            parsed = json.loads(obj)
            return geom_to_esri_json(parsed, outSR=outSR)
        except Exception:
            parts = obj.split(',')
            if len(parts) == 4:
                try:
                    nums = list(map(float, parts))
                    return geom_to_esri_json(nums, outSR=outSR)
                except Exception:
                    pass

    # If it's already an ESRI JSON dict with spatialReference matching outSR, return as-is (or reproject coords below)
    if isinstance(obj, dict) and is_esri_geometry_json(obj):
        # If geometry is envelope, point, or rings, try to convert to shapely and reproject to outSR
        try:
            # Build a GeoJSON-like dict from ESRI JSON to reuse code
            esri = obj
            if 'rings' in esri:
                geojson = {'type': 'Polygon', 'coordinates': esri['rings']}
            elif 'x' in esri and 'y' in esri:
                geojson = {'type': 'Point', 'coordinates': [esri['x'], esri['y']]}
            elif all(k in esri for k in ['xmin', 'ymin', 'xmax', 'ymax']):
                # envelope -> polygon
                xmin = esri['xmin']; ymin = esri['ymin']; xmax = esri['xmax']; ymax = esri['ymax']
                coords = [[ [xmin, ymin], [xmin, ymax], [xmax, ymax], [xmax, ymin], [xmin, ymin] ]]
                geojson = {'type': 'Polygon', 'coordinates': coords}
            else:
                geojson = None
            if geojson:
                geom_shp, src_epsg = _to_shapely_and_src_epsg(geojson)
                if geom_shp is None:
                    geom_shp = shape(geojson)
                    src_epsg = esri.get('spatialReference', {}).get('wkid', outSR) or outSR
                geom_reproj = _reproject_shapely(geom_shp, src_epsg, outSR)
                geo_map = mapping(geom_reproj)
                # construct ESRI JSON polygon rings
                if geo_map['type'] == 'Point':
                    x, y = geo_map['coordinates']
                    return {"geometry": {"x": x, "y": y, "spatialReference": {"wkid": int(outSR)}}, "geometryType": "esriGeometryPoint"}
                if geo_map['type'] in ('Polygon', 'MultiPolygon'):
                    # ensure rings are in ESRI format (list of linear rings)
                    if geo_map['type'] == 'Polygon':
                        rings = geo_map['coordinates']
                    else:
                        rings = [ring for poly in geo_map['coordinates'] for ring in poly]
                    return {"geometry": {"rings": rings, "spatialReference": {"wkid": int(outSR)}}, "geometryType": "esriGeometryPolygon"}
        except Exception:
            # fallback to returning the input object with requested spatialReference
            obj['spatialReference'] = {'wkid': int(outSR)}
            return {"geometry": obj, "geometryType": None}

    # Try to convert GeoDataFrame/GeoSeries/shapely/ee/geojson to shapely + source epsg
    geom_shp, src_epsg = _to_shapely_and_src_epsg(obj)
    if geom_shp is not None:
        geom_reproj = _reproject_shapely(geom_shp, src_epsg, outSR)
        geo_map = mapping(geom_reproj)
        gtype = geo_map['type']
        coords = geo_map['coordinates']
        if gtype == 'Point':
            return {"geometry": {"x": coords[0], "y": coords[1], "spatialReference": {"wkid": int(outSR)}},
                    "geometryType": "esriGeometryPoint"}
        if gtype == 'Polygon':
            return {"geometry": {"rings": coords, "spatialReference": {"wkid": int(outSR)}},
                    "geometryType": "esriGeometryPolygon"}
        if gtype == 'MultiPolygon':
            rings = [ring for poly in coords for ring in poly]
            return {"geometry": {"rings": rings, "spatialReference": {"wkid": int(outSR)}},
                    "geometryType": "esriGeometryPolygon"}

    # GeoJSON-like dict last attempt
    if isinstance(obj, dict) and 'type' in obj and 'coordinates' in obj:
        geom_shp = shape(obj)
        geom_reproj = _reproject_shapely(geom_shp, 4326, outSR)
        geo_map = mapping(geom_reproj)
        if geo_map['type'] == 'Point':
            x, y = geo_map['coordinates']
            return {"geometry": {"x": x, "y": y, "spatialReference": {"wkid": int(outSR)}}, "geometryType": "esriGeometryPoint"}
        if geo_map['type'] in ('Polygon', 'MultiPolygon'):
            if geo_map['type'] == 'Polygon':
                rings = geo_map['coordinates']
            else:
                rings = [ring for poly in geo_map['coordinates'] for ring in poly]
            return {"geometry": {"rings": rings, "spatialReference": {"wkid": int(outSR)}}, "geometryType": "esriGeometryPolygon"}

    raise TypeError("Unsupported geometry type for geometry filter or failed to convert/reproject the input geometry.")


def is_esri_geometry_json(obj):
    if not isinstance(obj, dict):
        return False
    # Polygon
    if "rings" in obj and "spatialReference" in obj:
        return True
    # Point
    if "x" in obj and "y" in obj and "spatialReference" in obj:
        return True
    # Envelope
    if all(k in obj for k in ["xmin", "ymin", "xmax", "ymax"]) and "spatialReference" in obj:
        return True
    return False

def gdf_to_ee(gdf):
    '''
    Convert a GeoDataFrame to an Earth Engine FeatureCollection. Default behavior reprojects to EPSG:4326 if the GeoDataFrame has a different CRS, since Earth Engine expects lat/lon coordinates. 
    Also converts any datetime fields to integer timestamps in milliseconds since epoch, which is a format that Earth Engine can handle. The function first converts the GeoDataFrame to a GeoJSON string, then parses it to a dictionary, and finally creates an ee.FeatureCollection from that dictionary.


    @Args: 
    gdf: GeoDataFrame to convert to ee.FeatureCollection

    @Returns:
    ee.FeatureCollection in EPSG:4326 CRS with datetime fields converted to timestamps.
    Returns an empty ee.FeatureCollection if gdf is None or empty.


    NOTE: add to GeeViz
    
    '''

    import ee
    import json
    import pandas as pd
    import geopandas as gpd

    # Handle None or empty GeoDataFrame
    if gdf is None:
        return ee.FeatureCollection([])
    
    if isinstance(gdf, gpd.GeoDataFrame) and len(gdf) == 0:
        return ee.FeatureCollection([])

    # get CRS of GeoDataFrame
    gdf_crs = gdf.crs if gpd and hasattr(gdf, 'crs') else None

    # reproject to EPSG:4326 if not already
    if gdf_crs and gdf_crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)
    else:
        gdf = gdf.copy()

    # identify if there are any date fields. if so, convert them to a format that ee can handle
    for col in gdf.columns:
        if pd.api.types.is_datetime64_any_dtype(gdf[col]):
            gdf[col] = gdf[col].astype('int64') // 10**6

    # Convert GeoDataFrame to GeoJSON string
    geojson_str = gdf.to_json()
    # Parse GeoJSON string to dictionary
    geojson_dict = json.loads(geojson_str)
    # Convert GeoJSON dictionary to ee.FeatureCollection
    ee_fc = ee.FeatureCollection(geojson_dict)
    return ee_fc

def ee_to_gdf(ee_fc, out_crs = None):
    '''

    Convert an Earth Engine FeatureCollection to a GeoDataFrame.
    
    @ Args:
    ee_fc: ee.FeatureCollection to convert to GeoDataFrame
    out_crs: optional, if provided, reproject the geometries to this CRS (e.g., 'EPSG:3857'). If not provided, geometries will be in the original CRS (usually EPSG:4326).

    @ Returns:
    GeoDataFrame with geometries and properties from the ee.FeatureCollection. Geometries will be in EPSG:4326 by default, or reprojected to out_crs if specified.

    '''

    import ee
    import geopandas as gpd
    import json
    from shapely.geometry import shape

    # Get GeoJSON dictionary from ee.FeatureCollection
    geojson_dict = ee_fc.getInfo()
    features = geojson_dict['features']

    # Convert features to list of geometries and properties
    geometries = []
    properties = []
    for feature in features:
        geom = shape(feature['geometry'])
        prop = feature['properties']
        geometries.append(geom)
        properties.append(prop)

    # Create GeoDataFrame
    gdf = gpd.GeoDataFrame(properties, geometry=geometries, crs="EPSG:4326")

    # Reproject if out_crs is specified
    if out_crs:
        gdf = gdf.to_crs(out_crs)

    return gdf

import requests
import pandas as pd
import time

# write a function that converts an ee feature collection to a normal geojson feature collection (list of dicts) and then to a geopandas geodataframe. This is useful for users who want to work with the data in Python instead of GEE.
def ee_to_geojson(ee_fc):

    '''
    Simple function to convert an ee.FeatureCollection to a GeoJSON-like dictionary. 

    @Args:
    ee_fc: ee.FeatureCollection to convert to GeoJSON dictionary
    @Returns:
    GeoJSON-like dictionary with 'type': 'FeatureCollection' and 'features': list of features.

    '''

    import ee
    import json

    # Get GeoJSON dictionary from ee.FeatureCollection
    geojson_dict = ee_fc.getInfo()
    return geojson_dict


def featureServiceToDataFrame(url, where="1=1", outFields="*", quiet=False):
    """
    Queries a table from an ArcGIS Feature Service and returns the data as a pandas DataFrame.
    This function is designed for non-spatial tables and handles pagination.

    Args:
        url (str): The URL of the Feature Service layer (e.g., .../FeatureServer/0).
        where (str): The SQL WHERE clause to filter records. Defaults to "1=1".
        outFields (str): Comma-separated list of fields to return. Defaults to "*".
        quiet (bool): If True, suppresses print statements.

    Returns:
        pandas.DataFrame: A DataFrame containing the queried records, or an empty
                          DataFrame if no records are found or an error occurs.
    """
    if not url.endswith('/'):
        url += '/'

    # Get service metadata to find maxRecordCount
    service_info_url = f"{url}?f=json"
    try:
        info_response = requests.get(service_info_url)
        info_response.raise_for_status()
        service_info = info_response.json()
        # Use a safe default if maxRecordCount is not present
        max_records = service_info.get('maxRecordCount', 1000)
        qprint(f"Service maxRecordCount: {max_records}", quiet)
    except requests.exceptions.RequestException as e:
        print(f"Error: Could not fetch service metadata from {service_info_url}: {e}")
        return pd.DataFrame() # Return empty DataFrame on error

    params = {
        "f": "json",
        "where": where,
        "outFields": outFields,
        "returnGeometry": "false", # Explicitly false for tables
        "resultOffset": 0,
        "resultRecordCount": max_records
    }

    all_records = []
    total_records_retrieved = 0

    while True:
        try:
            response = requests.get(f"{url}query", params=params)
            print("Request URL:", response.url)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error querying feature service at offset {params['resultOffset']}: {e}")
            break # Exit loop on error
        except ValueError: # Catches JSONDecodeError
            print(f"Error: Failed to decode JSON from response: {response.text}")
            break

        # Handle potential errors returned in the JSON response
        if 'error' in data:
            print(f"API Error: {data['error'].get('message', 'Unknown error')}")
            print(f"Details: {data['error'].get('details', [])}")
            break

        features = data.get('features', [])
        if not features:
            break  # No more features to fetch

        # Extract attributes from each feature
        for feature in features:
            all_records.append(feature.get('attributes', {}))

        num_fetched = len(features)
        total_records_retrieved += num_fetched
        if not quiet:
            print(f"Retrieved {num_fetched} records... (Total: {total_records_retrieved})")

        # Check if this was the last page.
        # The 'exceededTransferLimit' property is a reliable way to check for more pages.
        if data.get('exceededTransferLimit', False):
             params["resultOffset"] += num_fetched
             time.sleep(0.1) # Be polite to the server
        else:
            break


    if not quiet:
        print(f"Total records retrieved: {len(all_records)}")

    if not all_records:
        return pd.DataFrame()

    return pd.DataFrame(all_records)

def featureServiceToFeatureCollection(url, 
                               f = "geojson", 
                               where = "1=1", 
                               outFields = "*", 
                               returnGeometry = "true", 
                               resultOffset = 0, 
                               resultRecordCount = 500, 
                               outSR = None,
                               geometry = None,   
                               geometryType = None,
                               spatialRel = "esriSpatialRelIntersects",  # esriSpatialRelIntersects, esriSpatialRelContains, esriSpatialRelCrosses, esriSpatialRelEnvelopeIntersects, esriSpatialRelIndexIntersects, esriSpatialRelOverlaps, esriSpatialRelTouches, esriSpatialRelWithin
                               quiet = False,
                               return_geom = False,
                               id_field = "OBJECTID",
                               simplify_geometries=False,
                               simplify_max_error=10
                               ): 
    
    # TO ADD: 
    # - handle pagination if more than 1000 features (resultRecordCount max)

    import requests
    import json
    import ee

    url = checkEndingSlash(url)
    print(f"URL for feature service query: {url}")

    # Check the SR of the service
    #----------------------------------------------------------------------------#
    sr_dict, epsg = get_service_sr(url)
    #print("spatialReference:", sr_dict)
    qprint(f"EPSG/WKID OF feature service: {epsg}", quiet)

    # Count features in the service
    #----------------------------------------------------------------------------#
    # Params to determine how many features there are in the service
    count_params = {
        "f": "json",
        "where": "1=1",  # Select all features for initial count
        "returnCountOnly": "true",
        "outFields": None,
        "returnGeometry": None
    }

    # Get total feature count
    count_response = requests.get(url+"query", params=count_params)
    if count_response.status_code != 200:
        raise Exception(f"Error fetching feature count: {count_response.status_code}")
    total_features = count_response.json().get("count", 0)
    qprint(f"Total features in service: {total_features}", quiet)


    # Construct query
    #---------------------------------------------------------------------------------#
    # Query parameters
    base_params = {
        "f": f,  # Output format
        "where": where, # apply query
        "outFields": outFields,  # Include all fields
        "returnGeometry": returnGeometry,  # Include geometry
        "resultOffset": resultOffset,  # starting record
        "resultRecordCount": resultRecordCount, # record count per request
        "outSR": outSR  # Output spatial reference 
    }

    # Track the final ESRI JSON geometry used (None if not applicable)
    final_geom = None

    if geometry is not None:
        # convert geometry to appropriate format and reproject to service SR
        geo_obj = geom_to_esri_json(geometry, outSR=epsg)
        g_json = geo_obj["geometry"]
        print("ESRI geometry for filter:", g_json)
        base_params["geometry"] = json.dumps(g_json) if not isinstance(g_json, str) else g_json
        base_params["geometryType"] = geometryType or geo_obj.get("geometryType")
        base_params["spatialRel"] = spatialRel
        final_geom = geo_obj  # Store the full ESRI JSON geometry object (with geometryType)
    
        if total_features > 0:
            # params for geometry filter
            count_params["geometry"] = base_params.get("geometry")
            count_params["geometryType"] = base_params.get("geometryType")
            count_params["spatialRel"] = base_params.get("spatialRel")

            # Get total feature count with geometry filter
            #---------------------------------------------------------------------------------#
            count_response = requests.get(url+"query", params=count_params)
            if count_response.status_code != 200:
                raise Exception(f"Error fetching feature count: {count_response.status_code}")
            total_features = count_response.json().get("count", 0)
            qprint(f"Total features in service that match geometry filter: {total_features}", quiet)
            if total_features == 0:
                # Return empty FeatureCollection 
                return ee.FeatureCollection([])

    # Fetch the data
    #---------------------------------------------------------------------------------#
    response = requests.get(url+"query", params=base_params)
    qprint(f"Request URL: {response.url}")

    # Check if the request was successful
    if response.status_code != 200:
        raise Exception(f"Error fetching data: {response.status_code}")

    # Parse the JSON response
    data = response.json()
    features = data.get('features', [])
    qprint(f"Total number of features fetched: {len(features)}")
    if len(features) == 0:
        print("No features found matching the query parameters.")
        # Return empty FeatureCollection
        return ee.FeatureCollection([])

    # # Optionally print debug info for first feature
    # qprint("DEBUG: first feature details:", quiet)
    # qprint(features[0].keys(), quiet)
    # qprint("DEBUG: first feature attributes: ", quiet)
    # qprint(features[0]['properties'].keys(), quiet)

    # The 'data' variable is a GeoJSON FeatureCollection dictionary.
    # We need to manually add a string-based 'system:index' to each feature's
    # properties, as GEE requires it. We'll use the OBJECTID for this.
    # We also need to remove the top-level 'id' field from each feature to avoid conflicts.
    for feature in data.get('features', []):
        # Remove the top-level 'id' field if it exists.
        if 'id' in feature:
            del feature['id']

        properties = feature['properties']
        
        # Ensure system:index is a string, using OBJECTID.
        if id_field in properties:
            properties['system:index'] = str(properties[id_field])

        # Remove fields that are not compatible with ee.Feature
        if 'SHAPE.AREA' in properties:
            del properties['SHAPE.AREA']
        if 'SHAPE.LEN' in properties:
            del properties['SHAPE.LEN']

    # Construct the FeatureCollection directly from the modified GeoJSON dictionary
    fc = ee.FeatureCollection(data)

    # Simplify geometries if requested
    if simplify_geometries:
        def simplify_feature(feature):
            # Simplify the geometry of the feature.
            simplified_geometry = feature.geometry().simplify(maxError=simplify_max_error)
            return feature.setGeometry(simplified_geometry)
        
        # Map the simplification function over the FeatureCollection.
        fc = fc.map(simplify_feature)
    
    # Prep the geometry used for the query as an ee geom for optional export
    if final_geom is not None:
        from shapely.geometry import shape, mapping
        def esri_to_geojson(esri_geom):
            if esri_geom["geometryType"] == "esriGeometryEnvelope":
                g = esri_geom["geometry"]
                coords = [
                    [g["xmin"], g["ymin"]],
                    [g["xmin"], g["ymax"]],
                    [g["xmax"], g["ymax"]],
                    [g["xmax"], g["ymin"]],
                    [g["xmin"], g["ymin"]]
                ]
                return {"type": "Polygon", "coordinates": [coords]}
            elif esri_geom["geometryType"] == "esriGeometryPolygon":
                return {"type": "Polygon", "coordinates": esri_geom["geometry"]["rings"]}
            elif esri_geom["geometryType"] == "esriGeometryPoint":
                g = esri_geom["geometry"]
                return {"type": "Point", "coordinates": [g["x"], g["y"]]}
            else:
                raise ValueError("Unsupported ESRI geometryType for conversion.")
        geojson = esri_to_geojson(final_geom)
        ee_geom = ee.Geometry(geojson)
    
    if return_geom:
        return fc, ee_geom
    else:
        return fc 

def imageServiceToTiff(
    url, 
    geometry=None,
    localdir=r'C:\tmp',
    localfile='outtest.tif',
    f="image", 
    format="tiff",
    geometrySR=None,
    imageSR=None,
    pixelType=None,
    pixelSize=None,
    size=None, # Add size parameter
    noData = None, 
    noDataInterpretation="esriNoDataMatchAny",
    interpolation="RSP_BilinearInterpolation",
    quiet=False,
    timeout=300
):
    import requests
    import ee
    import os

    # check url format
    url = checkEndingExport(url)
    qprint(f"Using URL: {url}", quiet)


    # Initial Parameter Construct
    #----------------------------------------------------------#

    # Get info about image service to use to construct parameters
    info_url = url.replace('/exportImage?', '?f=json')
    response = requests.get(info_url)
    info = response.json()

    # Construct params
    params = {
        "f": f,
        "bbox": None,  # will be set below
        "bboxSR": None,  # will be set below
        "imageSR": imageSR,
        "format": format,
        "pixelType": pixelType,
        "pixelSize": pixelSize,
        "noData": noData,
        "noDataInterpretation": noDataInterpretation,
        "interpolation": interpolation
    }

    # Confirm params with information from image service
    pixel_size_service = info.get('pixelSizeX', None) or info.get('rasterInfo', {}).get('pixelSize', {}).get('x', None)
    if pixelSize is not None: 
        params['pixelSize'] = pixelSize
    if pixelSize is None and pixel_size_service is not None:
        params['pixelSize'] = pixel_size_service
    if pixelSize is None and pixel_size_service is None:
        qprint("No pixel size provided, and native pixel size not found in service info. Using default of 30.", quiet)
        params['pixelSize'] = 30

    nodata_service = info.get('noDataValue', None) or info.get('rasterInfo', {}).get('noDataValue', None)
    if noData is not None:
        params['noData'] = noData
    if noData is None and nodata_service is not None:
        params['noData'] = nodata_service
    if noData is None and nodata_service is None:
        qprint("No nodata value provided, and nodata value not found in service info. Using default of None.", quiet)
        params['noData'] = None

    image_sr_service = info.get('spatialReference', {}).get('latestWkid', None) or info.get('spatialReference', {}).get('wkid', None)
    if imageSR is not None:
        params['imageSR'] = imageSR
    if imageSR is None and image_sr_service is not None:
        params['imageSR'] = image_sr_service
    if imageSR is None and image_sr_service is None:
        qprint("No imageSR provided, and spatial reference not found in service info. Using default of 4326.", quiet)
        params['imageSR'] = 4326

    pixel_type_service = info.get('pixelType', None) or info.get('rasterInfo', {}).get('pixelType', None)
    if pixelType is not None:
        params['pixelType'] = pixelType
    if pixelType is None and pixel_type_service is not None:
        params['pixelType'] = pixel_type_service
    if pixelType is None and pixel_type_service is None:
        qprint("No pixelType provided, and pixel type not found in service info. Using default of S16.", quiet)
        params['pixelType'] = "S16"

    # Set geometry / bounding box and projection
    #----------------------------------------------------------#

    default_bbox = '-111,39,-110,40'
    default_bboxSR = 4326

    if geometry is None:
        qprint("No geometry provided. Using default bounding box and bboxSR: " + default_bbox + ", " + str(default_bboxSR), quiet)

    else:
        qprint(f"Using provided geometry", quiet)

        # check if geometrySR matches ImageSR
        if geometrySR is not None and params['imageSR'] is not None and geometrySR != params['imageSR']:
            qprint(f"Warning: geometrySR ({geometrySR}) does not match imageSR ({params['imageSR']}). The server will reproject the output image.", quiet)

        # convert geometry to bounding box        
        bounds, bboxSR = geometry_to_bbox(geometry, sr=geometrySR, quiet=quiet)

        #qprint(f"Using bounding box: {bounds} with bboxSR: {bboxSR}", quiet)

        

    # Set bbox and bboxSR params
    params["bbox"] = f"{bounds[0]},{bounds[1]},{bounds[2]},{bounds[3]}"
    params["bboxSR"] = bboxSR

    # Add size to params if provided
    if size:
        params["size"] = size



    # Format request
    #----------------------------------------------------------#
    try:
        response = requests.get(url+"query", params=params, timeout=timeout)
        qprint(f"Request URL: {response.url}", quiet)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)

    except requests.exceptions.Timeout:
        qprint(f"Request timed out after {timeout} seconds.", quiet)
        return None
    except requests.exceptions.RequestException as e:
        qprint(f"An error occurred: {e}", quiet)
        return None

    if response.status_code != 200:
        qprint(f"Failed to download image. HTTP Status Code: {response.status_code}", quiet)
        exit()
    else:
        file_path = f"{localdir}\\{localfile}"
        os.makedirs(localdir, exist_ok=True)
        with open(file_path, mode='wb') as localfile:
            localfile.write(response.content)
        qprint("Image saved to " + file_path, quiet)


def zonalStatsForPolygon(
    raster_path,
    polygon,
    polygon_id=None
):
    """
    Calculates zonal stats for a single polygon from a local raster file.
    Ignores NAs or no data values in the raster.
    Ensures the CRS of the polygon matches the raster; reprojects if needed.
    """
    import rasterio
    import rasterio.mask
    import numpy as np
    from shapely.geometry import mapping
    from rasterstats import zonal_stats
    
    try:
        with rasterio.open(raster_path) as src:
            raster_crs = src.crs

            # Reproject polygon to raster CRS if needed
            try:
                import geopandas as gpd
                if hasattr(polygon, 'crs') and polygon.crs is not None and polygon.crs != raster_crs:
                    polygon = gpd.GeoSeries([polygon], crs=polygon.crs).to_crs(raster_crs).iloc[0]
                    print(f"Reprojected polygon to match raster CRS: {raster_crs}")
            except ImportError:
                pass  # If geopandas is not available, assume polygon is already in correct CRS

            shapes = [mapping(polygon)]
            out_image, out_transform = rasterio.mask.mask(src, shapes, crop=True)
            out_image = out_image[0]

            nodata = src.nodata if src.nodata is not None else np.nan # Use NaN if no nodata is set

            # Mask out nodata and NaN values
            mask = (out_image != nodata) & (~np.isnan(out_image))
            if not np.any(mask):
                # All values are nodata or NaN
                results = {
                    'min': None, 'max': None, 'mean': None, 'median': None,
                    'std': None, 'count': 0, 'majority': None, 'polygon_id': polygon_id
                }
                return results

            # Only use valid data for stats
            valid_data = out_image[mask]

            # Compute stats manually to ensure nodata/NaN are ignored
            results = {
                'min': float(np.min(valid_data)) if valid_data.size > 0 else None,
                'max': float(np.max(valid_data)) if valid_data.size > 0 else None,
                'mean': float(np.mean(valid_data)) if valid_data.size > 0 else None,
                'median': float(np.median(valid_data)) if valid_data.size > 0 else None,
                'std': float(np.std(valid_data)) if valid_data.size > 0 else None,
                'count': int(valid_data.size),
                'majority': float(np.bincount(valid_data.astype(int)).argmax()) if valid_data.size > 0 else None,
                'polygon_id': polygon_id
            }

            return results

    except Exception as e:
        print(f"Error processing polygon: {e}")
        return {
            'min': None, 'max': None, 'mean': None, 'median': None,
            'std': None, 'count': 0, 'majority': None, 'polygon_id': polygon_id
        }

def zonalStatsFromImageService(
    image_service_url,
    polygons_gdf,
    polygon_id_field=None,
    geometry=None,
    tmp_dir='.',        
    geometrySR=None,
    imageSR=None,
    pixelSize=30,
    format='tiff',
    pixelType="S16",
    noData = None,
    noDataInterpretation="esriNoDataMatchAny",
    interpolation="RSP_BilinearInterpolation",
    quiet=False,
    cleanup =True
):
    """
    For each polygon in polygons_gdf, calculates a zonal histogram from an ArcGIS ImageServer.
    If geometry is provided, downloads a single raster for the bbox of the geometry and crops to each polygon. Only suggested for smaller areas to avoid resampling errors based on resampling.
    If bbox is not provided, downloads a raster for each polygon's bounding box.

    polygons_gdf: GeoDataFrame with polygons to calculate zonal stats for.
    cleanup: if True, deletes downloaded rasters after processing to save space.
    """
    import os
    import rasterio
    import rasterio.mask
    import numpy as np
    from shapely.geometry import mapping

    os.makedirs(tmp_dir, exist_ok=True)
    results = {}

    # check that polygons_gdf is a gdf and not empty
    try:
        import geopandas as gpd
        if not isinstance(polygons_gdf, gpd.GeoDataFrame):
            raise TypeError("polygons_gdf must be a GeoDataFrame.")
        if polygons_gdf.empty:
            raise ValueError("polygons_gdf is empty.")

    except Exception as e:
        print(f"Error checking polygons_gdf: {e}")
        return {}

    # Define default keys for stats
    default_keys = ['min', 'max', 'mean', 'median', 'std', 'count', 'majority', 'polygon_id']

    def default_result(polygon_id):
        return {k: None for k in default_keys[:-1]} | {'polygon_id': polygon_id}

    if geometry is not None:
        print(f"Using provided geometry for initial raster download")

        # Convert geometry to bounding box
        bbox, bboxSR = geometry_to_bbox(geometry, sr=geometrySR, quiet=quiet)

        # Download single raster for the bounding box
        raster_path = os.path.join(tmp_dir, "bbox_img.tif")
        imageServiceToTiff(
            url=image_service_url,
            geometry=bbox,
            localdir=tmp_dir,
            localfile="bbox_img.tif",
            f="image",
            format=format,
            geometrySR=geometrySR,
            imageSR=imageSR,
            pixelType=pixelType,
            pixelSize=pixelSize,
            noData=noData,
            noDataInterpretation=noDataInterpretation,
            interpolation=interpolation,
            quiet=True
        )

        # # Resample raster to desired pixel size if needed
        # with rasterio.open(raster_path) as src:
        #     native_pixel_size_x = src.transform.a
        #     native_pixel_size_y = -src.transform.e
        #     if pixelSize is not None and (abs(native_pixel_size_x - pixelSize) > 1e-6 or abs(native_pixel_size_y - pixelSize) > 1e-6):
        #         print(f"Resampling raster from native pixel size ({native_pixel_size_x}, {native_pixel_size_y}) to desired pixel size ({pixelSize}, {pixelSize})")
        #         from rasterio.warp import calculate_default_transform, reproject, Resampling

        #         dst_transform, width, height = calculate_default_transform(
        #             src.crs, src.crs, src.width, src.height, *src.bounds, resolution=pixelSize
        #         )
        #         dst_kwargs = src.meta.copy()
        #         dst_kwargs.update({
        #             'crs': src.crs,
        #             'transform': dst_transform,
        #             'width': width,
        #             'height': height
        #         })

        #         resampled_raster_path = os.path.join(tmp_dir, "bbox_resampled.tif")
        #         with rasterio.open(resampled_raster_path, 'w', **dst_kwargs) as dst:
        #             for i in range(1, src.count + 1):
        #                 reproject(
        #                     source=rasterio.band(src, i),
        #                     destination=rasterio.band(dst, i),
        #                     src_transform=src.transform,
        #                     src_crs=src.crs,
        #                     dst_transform=dst_transform,
        #                     dst_crs=src.crs,
        #                     resampling=Resampling.bilinear
        #                 )
        #         raster_path = resampled_raster_path
        #     else:
        #         print("No resampling needed; using downloaded raster as-is.")

        # Crop the raster to each polygon and calculate zonal stats
        total_polygons = len(polygons_gdf)
        for idx, row in polygons_gdf.iterrows():
            # Print progress: if > 200 polys, print every nth, otherwise print every time.
            print_index = 100
            if total_polygons > 200:
                if (idx + 1) % print_index == 0 or (idx + 1) == 1:
                    print(f"Processing polygon {idx + 1}/{total_polygons}")
            else:
                print(f"Processing polygon {idx + 1}/{total_polygons}")
            
            polygon = row.geometry
            # Always use the polygon_id from the input row
            polygon_id = row[polygon_id_field] if polygon_id_field in row else idx
            try:
                results_poly = zonalStatsForPolygon(raster_path, polygon, polygon_id=polygon_id)
                if results_poly is None:
                    results[idx] = default_result(polygon_id)
                else:
                    results[idx] = results_poly
            except Exception as e:
                print(f"Error processing polygon {idx}: {e}")
                results[idx] = default_result(polygon_id)

        if cleanup:
            # delete the raster to save space
            os.remove(raster_path)

    else:
        print("No bounding box provided. Downloading raster for each polygon.")

        # get sr of polygons if not provided
        if hasattr(polygons_gdf, 'crs') and polygons_gdf.crs is not None:
            polySR = polygons_gdf.crs.to_epsg()

        # Process each polygon individually
        for idx, row in polygons_gdf.iterrows():
            print(f"Processing polygon {idx+1}/{len(polygons_gdf)}")
            polygon = row.geometry

            # convert polygon to bounding box
            bbox, bboxSR = geometry_to_bbox(polygon, sr = polySR, quiet=quiet)

            raster_path = os.path.join(tmp_dir, f"subset_{idx}.tif")

            try:
                imageServiceToTiff(
                    url=image_service_url,
                    geometry=bbox,
                    localdir=tmp_dir,
                    localfile=f"subset_{idx}.tif",
                    f="image",
                    format=format,
                    geometrySR=bboxSR,
                    imageSR=imageSR,
                    pixelType=pixelType,
                    pixelSize=pixelSize,
                    noData=noData,
                    noDataInterpretation=noDataInterpretation,
                    interpolation=interpolation,
                    quiet=quiet
                )
                results_poly = zonalStatsForPolygon(raster_path, polygon, polygon_id=idx)
                if results_poly is None:
                    results[idx] = default_result(idx)
                else:
                    results[idx] = results_poly
                if cleanup:
                    # delete the raster to save space
                    os.remove(raster_path)
            except Exception as e:
                qprint(f"Error processing polygon {idx}: {e}", quiet)
                results[idx] = default_result(idx)

    return results
# ...existing code...

def imageServiceToMosaic(
    url,
    geometry,
    localdir=r'C:\tmp',
    localfile='mosaic.tif',
    max_tile_size=None,  # will be set from service if not provided
    pixelSize=30,
    geometrySR=None,
    imageSR=None,
    format="tiff",
    pixelType="S16",
    noData=None,
    noDataInterpretation="esriNoDataMatchAny",
    interpolation="RSP_BilinearInterpolation",
    quiet=False
):
    """
    Downloads an ArcGIS ImageServer raster for a large AOI by splitting into tiles and mosaicking.

    CHECK THIS FUNCTION, IT MAY HAVE BUGS. 
    The output mosaic seems misaligned with the input image. This might be due to incorrect handling of coordinate transformations or pixel size calculations.

    geometry: shapely Polygon, GeoSeries, or bounds tuple/list.
    max_tile_size: maximum number of pixels per tile side (from service if not provided).
    pixelSize: pixel size in meters.
    geometrySR: spatial reference for geometry (EPSG code).
    interpolation: resampling method. Options include: RSP_NearestNeighbor, RSP_BilinearInterpolation, RSP_CubicConvolution, RSP_Majority, RSP_Minimum, RSP_Maximum, RSP_Median, RSP_Mode, RSP_Lanczos
    localdir: directory to save files.
    localfile: name of output mosaic file.

    
    """
    import os
    import requests

    # Ensure output directory exists
    os.makedirs(localdir, exist_ok=True)

    # Get max image size from image service if not provided
    if max_tile_size is None:
        info_url = checkEndingExport(url).replace('/exportImage?', '?f=json')
        response = requests.get(info_url)
        info = response.json()
        max_image_height = info.get('maxImageHeight', None)
        max_image_width = info.get('maxImageWidth', None)
        # Use the smaller of the two for square tiles
        if max_image_height and max_image_width:
            max_tile_size = min(max_image_height, max_image_width)
            qprint(f"Using max_tile_size from service: {max_tile_size}", quiet)
        else:
            max_tile_size = 10000  # fallback default
            qprint("maxImageHeight/maxImageWidth not found in service info, using default 10000.", quiet)

    bounds, bboxSR = geometry_to_bbox(geometry, sr=geometrySR, quiet=quiet)

    # project bounds and bbox to epsg:4326 if needed
    # epsg:4326 is used for tile calculations; assumes pixelSize is in meters
    if bboxSR != 4326:
        from pyproj import Transformer
        transformer = Transformer.from_crs(bboxSR, 4326, always_xy=True)
        minx, miny = transformer.transform(bounds[0], bounds[1])
        maxx, maxy = transformer.transform(bounds[2], bounds[3])
        bounds = (minx, miny, maxx, maxy)
        bboxSR = 4326
        qprint(f"Reprojected bounds to EPSG:4326: {bounds}", quiet)
    
    # get bounds as separate variables
    minx, miny, maxx, maxy = bounds

    # convert pixelSize to degrees
    import math

    # --- For X dimension (Longitude) ---
    center_lat = (miny + maxy) / 2
    meters_per_degree_lon = 111320 * math.cos(math.radians(center_lat))
    pixelSize_degrees_x = pixelSize / meters_per_degree_lon

    # --- For Y dimension (Latitude) ---
    meters_per_degree_lat = 111132 # A degree of latitude is roughly constant
    pixelSize_degrees_y = pixelSize / meters_per_degree_lat

    # --- Calculate AOI size in pixels using the correct dimension for each ---
    width_degrees = maxx - minx
    height_degrees = maxy - miny
    width_pixels = int(width_degrees / pixelSize_degrees_x)
    height_pixels = int(height_degrees / pixelSize_degrees_y)

    # Calculate tile size in degrees
    tile_width_degrees = max_tile_size * pixelSize_degrees_x
    tile_height_degrees = max_tile_size * pixelSize_degrees_y

    x_tiles = math.ceil(width_degrees / tile_width_degrees)
    y_tiles = math.ceil(height_degrees / tile_height_degrees)

    qprint(f"Tile width (degrees): {tile_width_degrees}, Tile height (degrees): {tile_height_degrees}", quiet)
    qprint(f"AOI will be split into {x_tiles} x {y_tiles} tiles.", quiet)
    qprint(f"Each tile will be approximately {width_pixels // x_tiles} x {height_pixels // y_tiles} pixels.", quiet)

    image_size = f'{width_pixels//x_tiles},{height_pixels//y_tiles}'

    # Get Tiles
    tile_files = []

    for i in range(1, x_tiles + 1):
        for j in range(1, y_tiles + 1):
            qprint(f"Downloading tile {i},{j} of {x_tiles},{y_tiles}", quiet)

            # Create tile geom
            tile_minx = minx + (i - 1) * tile_width_degrees
            tile_maxx = min(tile_minx + tile_width_degrees, maxx)
            tile_miny = miny + (j - 1) * tile_height_degrees
            tile_maxy = min(tile_miny + tile_height_degrees, maxy)
            tile_geom = box(tile_minx, tile_miny, tile_maxx, tile_maxy)

            qprint(f"Tile bounds: {tile_minx}, {tile_miny}, {tile_maxx}, {tile_maxy}", quiet)

            # reproject tile_geom to imageSR if needed
            if imageSR is not None and imageSR != bboxSR:
                from pyproj import Transformer
                transformer = Transformer.from_crs(bboxSR, imageSR, always_xy=True)
                t_minx, t_miny = transformer.transform(tile_minx, tile_miny)
                t_maxx, t_maxy = transformer.transform(tile_maxx, tile_maxy)
                tile_geom = box(t_minx, t_miny, t_maxx, t_maxy)

            tile_file = os.path.join(localdir, f"tile_{i}_{j}.tif")
            imageServiceToTiff(
                    url=url,
                    geometry=tile_geom,
                    localdir=localdir,
                    localfile=f"tile_{i}_{j}.tif",
                    f="image",
                    format=format,
                    geometrySR=imageSR,
                    imageSR=imageSR,
                    pixelType=pixelType,
                    pixelSize=pixelSize,
                    size = image_size,
                    noDataInterpretation=noDataInterpretation,
                    interpolation=interpolation,
                    quiet=False
                )
            tile_files.append(tile_file)

    # Mosaic tiles
    src_files_to_mosaic = [rasterio.open(fp) for fp in tile_files]
    mosaic, out_trans = merge(src_files_to_mosaic)

    # Use metadata from first tile
    out_meta = src_files_to_mosaic[0].meta.copy()
    out_meta.update({
        "driver": "GTiff",
        "height": mosaic.shape[1],
        "width": mosaic.shape[2],
        "transform": out_trans
    })

    # Write mosaic to disk
    mosaic_path = os.path.join(localdir, localfile)
    with rasterio.open(mosaic_path, "w", **out_meta) as dest:
        dest.write(mosaic)

    # Clean up tile files
    for src in src_files_to_mosaic:
        src.close()
    for fp in tile_files:
        os.remove(fp)

    if not quiet:
        print(f"Mosaic saved to {mosaic_path}")

    #return mosaic_path

def get_service_sr(url):
    import requests
    """Return the service spatialReference dict and a best-effort EPSG int or None.
    
    Example Usage: 
    sr_dict, epsg = get_service_sr("https://services.arcgis.com/.../FeatureServer")
    print("spatialReference:", sr_dict)
    print("EPSG/WKID:", epsg)

    
    """
    url = url.rstrip('/') + '?f=json'
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    info = r.json()
    # Feature services often include top-level spatialReference
    sr = info.get('spatialReference') or info.get('extent', {}).get('spatialReference')
    if not sr:
        # Some services return layers array with per-layer SRs
        layers = info.get('layers') or info.get('featureLayers')
        if layers and len(layers) > 0:
            sr = layers[0].get('spatialReference') or layers[0].get('extent', {}).get('spatialReference')
    if not sr:
        return None, None
    epsg = sr.get('latestWkid') or sr.get('wkid')
    return sr, int(epsg) if epsg else None

def get_asset_list(parent, pattern=None):
    """
    REDUNDANT WITH AN EXISTING FUNCTION IN GEEVIZ.
    Recursively list all assets under a parent. If pattern is provided, only return assets whose names match the pattern (supports Unix shell-style wildcards).
    """
    import fnmatch
    parent_asset = ee.data.getAsset(parent)
    parent_id = parent_asset['name']
    parent_type = parent_asset['type']
    asset_list = []
    child_assets = ee.data.listAssets({'parent': parent_id})['assets']
    # If a pattern is provided, wrap it with wildcards for substring matching
    match_pattern = None
    if pattern is not None:
        # Only add wildcards if not already present
        if not pattern.startswith("*"):
            pattern = "*" + pattern
        if not pattern.endswith("*"):
            pattern = pattern + "*"
        match_pattern = pattern
    for child_asset in child_assets:
        child_id = child_asset['name']
        child_type = child_asset['type']
        if child_type in ['FOLDER','IMAGE_COLLECTION']:
            # Recursively call the function to get child assets
            asset_list.extend(get_asset_list(child_id, pattern=pattern))
        else:
            if match_pattern is None or fnmatch.fnmatch(child_id, match_pattern):
                asset_list.append(child_id)
    return asset_list

def download_blob(bucket_name, source_blob_name, destination_file_name):
    """Downloads a blob from the bucket.
    Args:
        bucket_name (str): The name of the GCS bucket.
        source_blob_name (str): The name of the blob in the GCS bucket.
        destination_file_name (str): The local path to save the downloaded file.
    Example:
        download_blob('my-bucket', 'path/to/blob', 'local/path/to/file')
    """
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(source_blob_name)
    filename = blob.name.replace('/', '_') 
    blob.download_to_filename(destination_file_name)
    print(f"Downloaded {source_blob_name} to {destination_file_name}.")

def exportToCloudStorageWrapper(
    imageForExport: ee.Image,
    outputName: str,
    bucketName: str,
    roi: ee.Geometry,
    scale: float | None = None,
    crs: str | None = None,
    transform: list | None = None,
    outputNoData: int = -32768,
    fileFormat: str = "GeoTIFF",
    formatOptions: dict = {"cloudOptimized": True},
    overwrite: bool = False,
):
    """Exports an image to Google Cloud Storage.

    This function exports an Earth Engine Image to a specified Google Cloud Storage bucket.

    Args:
        imageForExport: The Earth Engine Image to export.
        outputName: The desired name for the exported file.
        bucketName: The name of the Google Cloud Storage bucket.
        roi: The Earth Engine Geometry defining the region of interest.
        scale: The desired export scale in meters.
        crs: The desired coordinate reference system for the export.
        transform: The desired transform for the export.
        outputNoData: The no data value to use for the export.
        fileFormat: The desired output file format (e.g., "GeoTIFF", "TFRecord").
        formatOptions: Additional format options for the export.
        overwrite: A boolean indicating whether to overwrite an existing file.

    Returns:
        None. The function starts the export task.
    """
    import geeViz.cloudStorageManagerLib as cml
    import geeViz.taskManagerLib as tml


    outputName = outputName.replace("/\s+/g", "-")  # Get rid of any spaces
    outputNameDescription = outputName.replace("/", "_")  # Get rid of any slashes for description; compatibility for exporting to folders

    extension_dict = {"GeoTIFF": [".tif"], "TFRecord": [".tfrecord", ".json"]}
    extensions = extension_dict[fileFormat]

    extension_dict = {"GeoTIFF": [".tif"], "TFRecord": [".tfrecord", ".json"]}
    extensions = extension_dict[fileFormat]
    # Pull geometry if feature or featureCollection
    try:
        roi = roi.geometry()
    except Exception as e:
        x = e

    # Make sure image is clipped to roi in case it's a multi-part polygon
    imageForExport = imageForExport.clip(roi).unmask(outputNoData, False)

    if transform != None and (str(type(transform)) == "<type 'list'>" or str(type(transform)) == "<class 'list'>"):
        transform = str(transform)

    # Ensure bounds are in export projection
    outRegion = roi.bounds(100, crs)

    # Handle different instances of an blob either already existing or currently being exported and whether it should be overwritten
    currently_exporting = outputName in tml.getTasks()["running"] or outputName in tml.getTasks()["ready"]
    currently_exists = cml.gcs_exists(bucketName, outputName + extensions[0])

    if overwrite and currently_exists:
        for extension in extensions:
            cml.delete_blob(bucketName, outputName + extension)
    if overwrite and currently_exporting:
        tml.cancelByName(outputName)
    if overwrite or (not currently_exists and not currently_exporting):
        t = ee.batch.Export.image.toCloudStorage(
            imageForExport,
            outputNameDescription,
            bucketName,
            outputName,
            None,
            outRegion,
            scale,
            crs,
            transform,
            1e13,
            fileFormat=fileFormat,
            formatOptions=formatOptions,
        )
        print("Exporting:", outputName)
        print(t)
        t.start()


################################################################################
################################################################################

# Geopandas functions

import geopandas as gpd
import pandas as pd


# write function to identify intersecting polygons and add names to data_poly
def add_intersecting_poly_names(data_poly, places, places_name_field='NAME', output_field='intersecting_place_names'):
    """
    For each polygon in data_poly, identify intersecting polygons in places
    and add a new column 'intersecting_place_names' with the names of intersecting places.

    Args:
        data_poly: GeoDataFrame with polygons to check for intersections.
        places: GeoDataFrame with place polygons.

    Returns:
        Updated data_poly GeoDataFrame with new column for intersecting place names.
    """
    # Ensure both GeoDataFrames use the same CRS
    if data_poly.crs != places.crs:
        places = places.to_crs(data_poly.crs)


    # join polygons based on intersection
    intersecting_polygons = gpd.sjoin(data_poly, places, predicate='intersects', how='left')

    # group by original data_poly index and aggregate place names into a list
    intersecting_places = intersecting_polygons.groupby(intersecting_polygons.index)[places_name_field].apply(lambda x: list(x.dropna().unique())).reset_index()

    # merge back to original data_poly
    intersecting_places.rename(columns={places_name_field: output_field}, inplace=True) 
    data_poly = data_poly.merge(intersecting_places, left_index=True, right_on='index', how='left')

    # Drop the original index column
    data_poly.drop(columns=['index'], inplace=True)

    # Drop 'index_right' if it exists to prevent downstream errors
    if 'index_right' in data_poly.columns:
        data_poly = data_poly.drop(columns=['index_right'])

    # Drop 'index_left' if it exists to prevent downstream errors
    if 'index_left' in data_poly.columns:
        data_poly = data_poly.drop(columns=['index_left'])

    # Simplify the output field to a single name if only one intersecting place, List if two intersecting places, else None if no intersections. 
    data_poly[output_field] = data_poly[output_field].apply(
    lambda x: x[0] if isinstance(x, list) and len(x) == 1 else (x if isinstance(x, list) and len(x) > 0 else None)
    )

    return data_poly

# write a function to identify nearest point feature (e.g., sawmill) to a polygon centroid
# and add distance and name of point feature as new columns to data_poly
def add_nearest_point_info(data_poly, points, point_name_field='Name', output_distance_field='nearest_point_distance_m', output_name_field='nearest_point_name'):
    """
    For each polygon in data_poly, identify the nearest point in points
    and add new columns for distance and point name.

    Args:
        data_poly: GeoDataFrame with polygons.
        points: GeoDataFrame with point features.
        points_name_field: str, name of the field in points containing the point names.
        output_distance_field: str, name of the new field for distance to nearest point.
        output_name_field: str, name of the new field for nearest point name.
    Returns:
        Updated data_poly GeoDataFrame with new columns for nearest point distance and name.
    Usage:
    data_poly = sl.add_nearest_point_info(data_poly, gdf_sawmills,
        points_name_field='Name', output_name_field='sawmill_name', output_distance_field='sawmill_distance_m')
    """
    # Ensure both GeoDataFrames use the same CRS
    if data_poly.crs != points.crs:
        points = points.to_crs(data_poly.crs)

    # Prepare for distance calculation
    # If CRS is geographic, project to a suitable projected CRS (EPSG:5070 - NAD83 / Conus Albers)
    # to ensure accurate distance calculation in meters.
    calc_poly = data_poly.copy()
    calc_points = points.copy()
    
    if calc_poly.crs and calc_poly.crs.is_geographic:
        target_crs = "EPSG:5070"
        calc_poly = calc_poly.to_crs(target_crs)
        calc_points = calc_points.to_crs(target_crs)

    # Get centroids of polygons (using the potentially projected data)
    calc_poly_centroids = calc_poly.copy()
    calc_poly_centroids['geometry'] = calc_poly_centroids.geometry.centroid

    # Function to find nearest point and distance for a single polygon
    def find_nearest_point(polygon):
        # Calculate distances to all points
        distances = calc_points.geometry.distance(polygon.geometry)
        # Find index of nearest point
        min_idx = distances.idxmin()
        # Get nearest point name (from original points to ensure metadata is correct)
        nearest_point_name = points.loc[min_idx, point_name_field]
        nearest_point_distance = distances[min_idx]
        return pd.Series({output_name_field: nearest_point_name, output_distance_field: nearest_point_distance})

    # Apply the function to each polygon centroid
    nearest_info = calc_poly_centroids.apply(find_nearest_point, axis=1)

    # Merge the new information back into data_poly
    data_poly = pd.concat([data_poly, nearest_info], axis=1)

    return data_poly

# write a function to identify nearest linear feature (e.g., road) to a polygon edge
# and add distance and name of linear feature as new columns to data_poly
def add_nearest_line_info(
    data_poly,
    lines,
    line_name_field='FULLNAME',
    output_distance_field='nearest_line_distance_m',
    output_name_field='nearest_line_name'
):
    """
    For each polygon in data_poly, identify the nearest line in lines
    and add new columns for distance and line name.

    Args:
        data_poly: GeoDataFrame with polygons.
        lines: GeoDataFrame with line features.
        lines_name_field: str, name of the field in lines containing the line names.
        output_distance_field: str, name of the new field for distance to nearest line.
        output_name_field: str, name of the new field for nearest line name.
    Returns:
        Updated data_poly GeoDataFrame with new columns for nearest line distance and name.

    Usage:
    data_poly = sl.add_nearest_line_info(data_poly, roads, line_name_field='FULLNAME', output_name_field='NEAREST_ROAD_NAME', output_distance_field='NEAREST_ROAD_DIST')

    """

    # Ensure both GeoDataFrames use the same CRS
    if data_poly.crs != lines.crs:
        lines = lines.to_crs(data_poly.crs)

    # Function to find nearest line and distance for a single polygon
    def find_nearest_line(polygon):
        poly_geom = polygon.geometry
        centroid = poly_geom.centroid

        # Find lines that intersect the polygon
        intersecting = lines[lines.geometry.intersects(poly_geom)]

        if not intersecting.empty:
            # Compute distance from centroid to each intersecting line
            distances = intersecting.geometry.distance(centroid)
            min_idx = distances.idxmin()
            nearest_line_name = intersecting.loc[min_idx, line_name_field]
            nearest_line_distance = distances[min_idx]

        else:
            # No intersecting lines, fall back to nearest line (to polygon edge)
            distances = lines.geometry.distance(poly_geom)
            min_idx = distances.idxmin()
            nearest_line_name = lines.loc[min_idx, line_name_field]
            nearest_line_distance = distances[min_idx]

        return pd.Series({output_name_field: nearest_line_name, output_distance_field: nearest_line_distance})

    # Apply the function to each polygon
    nearest_info = data_poly.apply(find_nearest_line, axis=1)

    # Merge the new information back into data_poly
    data_poly = pd.concat([data_poly, nearest_info], axis=1)

    return data_poly

def add_nearest_polygon_info(data_poly, polygons, 
                             polygon_name_field='NAME', output_distance_field='nearest_poly_distance_m', output_name_field='nearest_poly_name'):
    """
    For each polygon in data_poly, identify the nearest polygon in the 'polygons' GeoDataFrame
    and add new columns for distance and polygon name.
    
    Args:
        data_poly: GeoDataFrame (Source) - The polygons you want to annotate.
        polygons: GeoDataFrame (Target) - The reference polygons (e.g., Harvest sites).
        polygon_name_field: Field in 'polygons' to use as the name.
    """
    # Ensure both GeoDataFrames use the same CRS
    if data_poly.crs != polygons.crs:
        polygons = polygons.to_crs(data_poly.crs)

    # Function to find nearest polygon and distance for a single polygon
    def find_nearest_polygon(polygon):
        poly_geom = polygon.geometry

        # Calculate distances from polygon edge to all target polygons
        # Note: If datasets are large, this is slow. Consider using sindex.nearest() for optimization.
        distances = polygons.geometry.distance(poly_geom)
        
        # Find minimum distance
        min_dist = distances.min()
        
        # Identify all polygons that share the minimum distance (within a small tolerance for floats)
        candidates = distances[distances <= min_dist + 1e-9]
        
        if len(candidates) > 1:
            # Break tie using distance from source centroid to target geometry
            centroid = poly_geom.centroid
            centroid_distances = polygons.loc[candidates.index].geometry.distance(centroid)
            min_idx = centroid_distances.idxmin()
        else:
            min_idx = candidates.idxmin()
        
        # Get nearest polygon name and distance
        nearest_poly_name = polygons.loc[min_idx, polygon_name_field]
        nearest_poly_distance = distances[min_idx]
        
        return pd.Series({output_name_field: nearest_poly_name, output_distance_field: nearest_poly_distance})

    # Apply the function to each polygon in data_poly
    nearest_info = data_poly.apply(find_nearest_polygon, axis=1)

    # Merge the new information back into data_poly
    data_poly = pd.concat([data_poly, nearest_info], axis=1)

    return data_poly

##############################################################

############################################################### 

# load in example data
def load_example_data(data_type='feature_service', source='us_states', clip_to_country=True, quiet=False):
    """
    Load example data for testing and demonstration purposes.

    Args:
        data_type (str): The type of data to load. Options are 'feature_service' or 'asset'.
        source (str): The source of the data. Depends on the data_type.
        clip_to_country (bool): Whether to clip the data to the boundaries of the United States.
        quiet (bool): If True, suppress print statements.

    Returns:
        GeoDataFrame or FeatureCollection: The loaded data.
    """
    import geopandas as gpd
    from shapely.geometry import mapping
    import ee

    if data_type == 'feature_service':
        # Feature service URLs
        urls = {
            'us_states': 'https://services.arcgis.com/ArcGIS/rest/services/USA_States_Generalized/FeatureServer/0',
            'us_counties': 'https://services.arcgis.com/ArcGIS/rest/services/USA_Counties_Generalized/FeatureServer/0',
            'world_countries': 'https://services.arcgis.com/ArcGIS/rest/services/World_Countries/FeatureServer/0'
        }

        if source not in urls:
            raise ValueError(f"Unknown source '{source}' for data_type 'feature_service'. Available sources: {list(urls.keys())}")

        url = urls[source]

        # Load as GeoDataFrame
        gdf = gpd.read_file(f"ESRI__GeoJSON:{url}")

        if clip_to_country:
            # Get US boundaries from Natural Earth
            us_boundaries = gpd.read_file(gpd.datasets.get_path('naturalearth_lowres'))
            us_boundaries = us_boundaries[us_boundaries.name == "United States"]

            # Clip to US boundaries
            gdf = gdf.clip(us_boundaries.geometry.unary_union)

        return gdf

    elif data_type == 'asset':
        # Earth Engine asset URLs
        ee_assets = {

            'us_states': 'users/gena/USA_States',
            'us_counties': 'users/gena/USA_Counties',
            'world_countries': 'users/gena/World_Countries'
        }

        if source not in ee_assets:
            raise ValueError(f"Unknown source '{source}' for data_type 'asset'. Available sources: {list(ee_assets.keys())}")

        asset = ee_assets[source]

        # Load as FeatureCollection
        fc = ee.FeatureCollection(asset)

        # Convert to GeoDataFrame
        gdf = gpd.GeoDataFrame.from_features(fc.getInfo()['features'])

        if clip_to_country:
            # Get US boundaries from Natural Earth
            us_boundaries = gpd.read_file(gpd.datasets.get_path('naturalearth_lowres'))
            us_boundaries = us_boundaries[us_boundaries.name == "United States"]

            # Clip to US boundaries
            gdf = gdf.clip(us_boundaries.geometry.unary_union)

        return gdf

    else:
        raise ValueError("Invalid data_type. Available options: 'feature_service', 'asset'.")


def test_gdf(gdf, max_points=10):
    """
    Test function to display and print basic info about a GeoDataFrame.

    Args:
        gdf (GeoDataFrame): The GeoDataFrame to test.
        max_points (int): Maximum number of points to display for geometry columns.

    Returns:
        None
    """
    if gdf is None or gdf.empty:
        print("GeoDataFrame is empty.")
        return

    print(f"GeoDataFrame with {len(gdf)} features.")

    # Print the first few rows of the GeoDataFrame
    print(gdf.head())

    # Print the geometry column info
    geom_col = gdf.geometry.name
    print(f"\nGeometry column: {geom_col}")
    print(gdf.geometry.head(max_points))

    # Print the CRS
    print(f"\nCRS: {gdf.crs}")

    # If it's a FeatureCollection, print the properties of the first feature
    if 'properties' in gdf.columns:
        print("\nSample properties:")
        print(gdf['properties'].head(max_points))
    
    # If there are any multi-part geometries, warn the user
    if gdf.geometry.apply(lambda geom: geom.type.startswith('Multi')).any():
        print("\nWarning: There are multi-part geometries in this GeoDataFrame. This may affect some spatial operations.")

    print("\nSummary statistics:")
    print(gdf.describe())

    # If there are any categorical fields, print the unique values
    for col in gdf.select_dtypes(include=['category', 'object']).columns:
        print(f"\nUnique values in '{col}':")
        print(gdf[col].unique())

    print("\nGeoDataFrame test complete.")

# def to test loading example data
def test_load_example_data():
    import time

    # Load US States example data
    print("Loading example data: US States")
    us_states = load_example_data(data_type='feature_service', source='us_states', clip_to_country=True, quiet=False)
    test_gdf(us_states)

    # Load World Countries example data
    print("\nLoading example data: World Countries")
    world_countries = load_example_data(data_type='feature_service', source='world_countries', clip_to_country=False, quiet=False)
    test_gdf(world_countries)

    print("\nExample data loading test complete.")

def spatial_join_ee(left_fc, right_fc, join_type='left', max_dist=1, right_fields_to_join=None, right_fields_prefix=''):
    """
    Performs a spatial join between two Earth Engine FeatureCollections, ensuring all
    features from the primary collection are retained in a left or right join.

    Args:
        left_fc (ee.FeatureCollection): The "left" feature collection.
        right_fc (ee.FeatureCollection): The "right" feature collection.
        join_type (str, optional): 'left', 'right', or 'inner'. Defaults to 'left'.
        max_dist (int, optional): Max distance in meters for intersection. Defaults to 1.
        right_fields_to_join (list, optional): A list of property names from the 
            right_fc to join. If None, all properties are joined. Defaults to None.
        right_fields_prefix (str, optional): A prefix to add to the joined fields 
            from the right_fc. Defaults to ''.

    Returns:
        ee.FeatureCollection: The result of the join.
    """
    # Define the spatial filter
    spatial_filter = ee.Filter.withinDistance(
        distance=max_dist,
        rightField='.geo',
        leftField='.geo',
        maxError=1
    )

    if join_type.lower() == 'inner':
        # Standard inner join
        inner_join = ee.Join.inner('primary', 'secondary')
        joined_fc = inner_join.apply(left_fc, right_fc, spatial_filter)

        def merge_features(feature):
            primary = ee.Feature(feature.get('primary'))
            secondary = ee.Feature(feature.get('secondary'))
            
            # If a prefix is provided, rename secondary properties
            if right_fields_prefix:
                prefix = ee.String(right_fields_prefix)
                props_to_rename = secondary.propertyNames()
                if right_fields_to_join:
                    props_to_rename = ee.List(right_fields_to_join)
                
                new_names = props_to_rename.map(lambda n: prefix.cat(n))
                secondary = secondary.select(props_to_rename, new_names)

            return primary.copyProperties(secondary, exclude=['system:index'])
        
        return joined_fc.map(merge_features)

    elif join_type.lower() in ['left', 'right']:
        # Use saveAll for left/right joins to keep all primary features
        save_all_join = ee.Join.saveAll(matchesKey='matches', ordering='distance')
        
        # Determine which collection is primary
        primary_fc = left_fc if join_type.lower() == 'left' else right_fc
        secondary_fc = right_fc if join_type.lower() == 'left' else left_fc
        
        joined_fc = save_all_join.apply(primary_fc, secondary_fc, spatial_filter)

        def merge_join_results(feature):
            # Preserve the original feature
            original_feature = ee.Feature(feature)
            
            # Get the list of matching features
            matches = ee.List(feature.get('matches'))
            
            # Define how to handle a feature that has matches
            def with_matches(match_list):
                # Get the first match
                first_match = ee.Feature(match_list.get(0))
                
                # Select and optionally rename properties from the matched feature
                props_to_join = first_match.propertyNames()
                if right_fields_to_join:
                    props_to_join = ee.List(right_fields_to_join)
                
                # If a prefix is provided, create new field names
                if right_fields_prefix:
                    prefix = ee.String(right_fields_prefix)
                    new_names = props_to_join.map(lambda n: prefix.cat(n))
                    joined_props = first_match.select(props_to_join, new_names)
                else:
                    joined_props = first_match.select(props_to_join)
                
                # Copy the selected and renamed properties to the original feature
                return original_feature.copyProperties(joined_props, exclude=['system:index'])

            # If there are no matches, return the original feature unmodified
            # Otherwise, process the matches
            merged_feature = ee.Feature(ee.Algorithms.If(
                matches.size().gt(0),
                with_matches(matches),
                original_feature
            ))
            
            # Remove the intermediate 'matches' property
            return merged_feature.set('matches', None)

        return joined_fc.map(merge_join_results)

    else:
        raise ValueError("Unsupported join_type. Use 'left', 'right', or 'inner'.")

def ingest_table_from_gcs(gcs_uri, asset_id, description="", overwrite =False):
    """
    Starts an Earth Engine ingestion task to create a table asset from a file in GCS.

    This function checks if the asset already exists before starting the ingestion.
    It returns the task ID so it can be monitored.

    The file in GCS must be in .shp format, or be a zip containing the shapefile components,

    Args:
        gcs_uri (str): The Google Cloud Storage URI of the source file 
                       (e.g., 'gs://bucket/folder/file.geojson').
                       Supported formats include GeoJSON, CSV, and SHP (in a .zip).
        asset_id (str): The destination asset ID for the new table 
                        (e.g., 'projects/your-project/assets/folder/your-asset').
        description (str, optional): A description for the ingestion task. Defaults to "".


    Returns:
        str: The task ID of the started ingestion task, or None if the asset
             already exists or an error occurs.

  
        
    """
    print(f"Starting ingestion for asset: {asset_id} from GCS: {gcs_uri}")
    
    # 1. Check if the asset already exists to avoid errors.
    try:
        ee.data.getAsset(asset_id)
        print(f"Asset '{asset_id}' already exists. Skipping ingestion.")
        return None
    except ee.ee_exception.EEException as e:
        # This exception is expected if the asset does not exist.
        if f"Asset '{asset_id}' does not exist" in str(e):
            print("Asset does not exist, proceeding with ingestion.")
        else:
            # Re-raise other unexpected GEE exceptions.
            print(f"An unexpected GEE error occurred: {e}")
            raise e

    # 2. Define the ingestion request.
    request_id = ee.data.newTaskId()[0]
    params = {
        'id': asset_id,
        'sources': [{
            'uris': [gcs_uri]
        }]
    }

    # 3. Start the ingestion task.
    try:
        
        task_id = ee.data.startTableIngestion(request_id, params, allow_overwrite=overwrite)
        print(f"Successfully started ingestion task with ID: {task_id['id']}")
        return task_id['id']
    except Exception as e:
        print(f"Failed to start ingestion task: {e}")
        return None
    
    

def monitor_task(task_id):
    """
    Monitors a single Earth Engine task until it completes or fails.

    Args:
        task_id (str): The ID of the task to monitor.
    """
    if not task_id:
        print("No task ID provided to monitor.")
        return

    print(f"Monitoring task: {task_id}...")
    while True:
        try:
            status = ee.data.getTaskStatus(task_id)[0]
            state = status['state']
            
            if state == 'COMPLETED':
                print(f"Task '{task_id}' finished successfully.")
                break
            elif state in ['FAILED', 'CANCELLED']:
                error_message = status.get('error_message', 'No error message found.')
                print(f"Task '{task_id}' finished with state: {state}. Error: {error_message}")
                break
            else:
                print(f"Task '{task_id}' is currently {state}...")
                time.sleep(30)  # Wait 30 seconds before the next check.
        except Exception as e:
            print(f"An error occurred while monitoring task '{task_id}': {e}")
            break

def get_ee_asset_safe(asset_path, max_retries=4, retry_wait=20):
    """
    Attempts to load an Earth Engine asset (FeatureCollection), retrying if it fails.
    Useful when waiting for an asset export task to complete and become available.
    """
    for attempt in range(max_retries + 1):
        try:
            collection = ee.FeatureCollection(asset_path)
            # Force a check to see if it exists/is accessible by getting size
            count = collection.size().getInfo()
            print(f"Successfully loaded asset from: {asset_path}")
            print(f"Number of features: {count}")
            return collection
        except Exception as e:
            if attempt < max_retries:
                print(f"Asset not found or not ready. Retrying in {retry_wait} seconds... (Attempt {attempt + 1}/{max_retries})")
                time.sleep(retry_wait)
            else:
                print(f"Error: Could not load asset: {asset_path}")
                raise e

def get_gcs_object_safe(bucket_name, object_name, max_retries=4, retry_wait=20):
    """
    Attempts to access a GCS object, retrying if it fails. Useful when waiting for an export task to complete and the file to become available.
    """
    from google.cloud import storage

    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)

    for attempt in range(max_retries + 1):
        try:
            blob = bucket.blob(object_name)
            if blob.exists():
                print(f"Successfully accessed GCS object: gs://{bucket_name}/{object_name}")
                return blob
            else:
                raise FileNotFoundError(f"GCS object not found: gs://{bucket_name}/{object_name}")
        except Exception as e:
            if attempt < max_retries:
                print(f"GCS object not found or not ready. Retrying in {retry_wait} seconds... (Attempt {attempt + 1}/{max_retries})")
                time.sleep(retry_wait)
            else:
                print(f"Error: Could not access GCS object: gs://{bucket_name}/{object_name}")
                raise e

def prepare_bbox_for_query(aoi_input, target_crs):
    """
    Prepares a bounding box polygon from various inputs (GDF, GeoSeries, Polygon)
    projected to the target CRS.

    Inputs:
        aoi_input: GeoDataFrame, GeoSeries, or shapely Polygon representing the area of interest.
        target_crs: (String) The target CRS to reproject the geometry to (e.g., "EPSG:5070").
    """
    # 1. Extract Geometry
    if isinstance(aoi_input, (gpd.GeoDataFrame, gpd.GeoSeries)):
        if aoi_input.empty:
             return None
        geo_series = aoi_input.geometry
    elif isinstance(aoi_input, Polygon):
        # Assume 4326 if not specified? Or require CRS?
        # The current script assumes 4326 for raw polygons.
        geo_series = gpd.GeoSeries([aoi_input], crs="EPSG:4326")
    else:
        print("Error: Invalid AOI input.")
        return None

    # 2. Reproject
    try:
        if geo_series.crs is None:
             print("Warning: Input geometry has no CRS. Assuming EPSG:4326.")
             geo_series = geo_series.set_crs("EPSG:4326")
        
        geo_series_reproj = geo_series.to_crs(target_crs)
    except Exception as e:
        print(f"Error reprojecting to {target_crs}: {e}")
        return None

    # 3. Calculate Bounds
    # Check for infinite values which can happen with projection issues
    bounds = geo_series_reproj.total_bounds
    if not all(math.isfinite(x) for x in bounds):
        print(f"Error: Reprojected bounds contain infinite values: {bounds}")
        print(f"Input CRS: {geo_series.crs}, Target CRS: {target_crs}")
        return None

    minx, miny, maxx, maxy = bounds
    bbox_polygon = Polygon([
        (minx, miny), (minx, maxy), (maxx, maxy), (maxx, miny), (minx, miny)
    ])
    
    # Return as GeoSeries with CRS to ensure downstream functions know the projection
    return gpd.GeoSeries([bbox_polygon], crs=target_crs)

def upload_to_drive(local_path, remote_filename, folder_ids=None, overwrite=False):
    """
    Uploads a local file to Google Drive.

    Args:
        local_path (str): The file path to the local file to upload.
        remote_filename (str): The name the file should have on Google Drive. 
                               Note: This function does not handle directory structure creation; 
                               it uploads to the specified folder IDs.
        folder_ids (list, optional): A list of Google Drive folder IDs to upload the file to. 
                                     If None, looks for 'GDRIVE_FOLDER_IDS' env var.
        overwrite (bool, optional): If True, deletes any existing files with the same name 
                                    in the target folders before uploading. Defaults to False.

    Returns:
        dict: The response object from the Drive API (containing file ID, etc.).
    
    Raises:
        ValueError: If folder_ids is None 
        FileNotFoundError: If local_path does not exist.
    """
    if not os.path.exists(local_path):
        raise FileNotFoundError(f"Local file not found: {local_path}")

    # Resolve folder IDs
    if folder_ids is None:
        raise ValueError("No folder IDs provided.")
    
    # Authenticate and build service
    # Note: explicit scopes are often required for Drive API
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/drive"])
    service = discovery.build('drive', 'v3', credentials=credentials)
    
    target_name = remote_filename.split("/")[-1] # Ensure we only get the filename

    # Handle overwrite
    if overwrite:
        print(f"Overwrite enabled: Checking for existing files named '{target_name}'...")
        for folder_id in folder_ids:
            query = f"name = '{target_name}' and '{folder_id}' in parents and trashed = false"
            try:
                results = service.files().list(q=query, fields="files(id, name)").execute()
                files = results.get('files', [])
                for file in files:
                    print(f"Overwriting: Deleting existing file '{file['name']}' (ID: {file['id']})")
                    service.files().delete(fileId=file['id']).execute()
            except Exception as e:
                print(f"Warning: Failed to check/delete existing file in folder {folder_id}: {e}")

    media = MediaFileUpload(local_path)
    
    file_metadata = {
        "name": target_name, 
        "parents": folder_ids
    }
    
    print(f"Starting upload to Drive: {target_name}")
    try:
        response = service.files().create(
            media_body=media, 
            body=file_metadata
        ).execute()
        print(f"Upload complete. File ID: {response.get('id')}")
        return response
    except HttpError as e:
        if e.resp.status == 403 and "insufficient authentication scopes" in str(e):
            print("\n" + "="*60)
            print("ERROR: Google Drive upload failed due to insufficient permissions.")
            print("The current credentials do not have 'https://www.googleapis.com/auth/drive' scope.")
            print("Please run the following command in your terminal to re-authenticate:")
            print('gcloud auth application-default login --scopes="https://www.googleapis.com/auth/drive,https://www.googleapis.com/auth/cloud-platform"')
            print("="*60 + "\n")
        raise
    except Exception as e:
        print(f"Error uploading to Drive: {e}")
        raise

