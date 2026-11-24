"""
USFS Enterprise Data Warehouse (EDW) REST API client: now :mod:`georest.usfs.edw`.

Search, metadata and spatial feature queries against the ArcGIS REST
services at https://apps.fs.usda.gov/arcx/rest/services/EDW. The client
itself moved to georest, RedCastle's library of geospatial REST clients;
this module keeps the geeViz names and adds the one thing georest does
not do: accept Earth Engine objects (``ee.Geometry``, ``ee.Feature``,
``ee.FeatureCollection``) as the spatial filter.

Quick start::

    import geeViz.edwLib as edw

    # Search for fire-related services
    services = edw.search_services("fire")

    # Get layer info
    info = edw.get_service_info("EDW_MTBS_01")

    # Query features as GeoJSON
    geojson = edw.query_features("EDW_MTBS_01", 15,
        where="FIRE_NAME LIKE '%CAMERON PEAK%'",
        out_fields="FIRE_NAME,ACRES,YEAR")

    # Features intersecting an Earth Engine geometry
    utah = ee.FeatureCollection("TIGER/2018/States").filter(ee.Filter.eq("NAME", "Utah"))
    forests = edw.query_features("EDW_ForestSystemBoundaries_01", 1, geometry=utah)

    # NOTE: ``where`` and ``out_fields`` are case-insensitive SQL, but the
    # CASE of the keys in the returned properties is the service's choice
    # and can change without notice -- EDW_MTBS_01 returns 'fire_name'
    # today where it returned 'FIRE_NAME' before. Match field names
    # case-insensitively rather than indexing one spelling.

    # Load into Earth Engine
    import ee
    fc = ee.FeatureCollection(geojson)

Features come back ready for Earth Engine: property names with dots
(``SHAPE.LEN``) are dropped, and every feature has a string ``id``, its
object id where the service gives one.
"""
from __future__ import annotations

from typing import Any

from georest.usfs import edw as _edw

EDW_BASE_URL = _edw.EDW_BASE_URL


def search_services(query: str = "", theme: str = "") -> list[dict[str, str]]:
    """Search EDW services by keyword and/or theme.

    Matches service names and their curated descriptions, and expands
    common terms ("riparian", "wildfire", "ownership") to the themes and
    services they imply. See :func:`georest.usfs.edw.search_edw_services`.

    Args:
        query: Keyword(s), e.g. ``"fire"`` or ``"roads"``. Empty lists all.
        theme: Restrict to one theme, e.g. ``"boundaries"``,
            ``"environment"``, ``"inland_waters"``, ``"transportation"``.

    Returns:
        List of dicts with ``name``, ``url``, ``theme`` and ``description``.
    """
    return _edw.search_edw_services(query, theme)


def get_service_info(service_name: str) -> dict[str, Any]:
    """A service's description and layers, e.g. ``"EDW_MTBS_01"``.

    See :func:`georest.usfs.edw.get_service_info`.
    """
    return _edw.get_service_info(service_name)


def get_layer_info(service_name: str, layer_id: int) -> dict[str, Any]:
    """A layer's fields, extent and record limit.

    See :func:`georest.usfs.edw.get_layer_info`.
    """
    return _edw.get_layer_info(service_name, layer_id)


def query_features(
    service_name: str,
    layer_id: int,
    geometry: Any = None,
    geometry_type: str = "esriGeometryEnvelope",
    spatial_rel: str = "esriSpatialRelIntersects",
    where: str = "1=1",
    out_fields: str = "*",
    max_features: int = 1000,
    out_sr: int = 4326,
    return_count_only: bool = False,
    in_sr: int | None = None,
    max_allowable_offset: float | None = None,
) -> dict:
    """Query features from an EDW layer, optionally filtered by spatial intersection.

    Args:
        service_name: Short service name, e.g. "EDW_MTBS_01".
        layer_id: Layer ID within the service.
        geometry: Geometry for spatial filter. Can be:
            - An ``ee.Geometry``, ``ee.Feature`` or ``ee.FeatureCollection``
            - A GeoJSON geometry dict (Point, Polygon, MultiPolygon, ...)
            - An Esri JSON geometry string/dict
            - A bbox string "xmin,ymin,xmax,ymax"
            - None for no spatial filter
        geometry_type: Esri geometry type. Left at the default, it follows
            the geometry given (a GeoJSON polygon is sent as a polygon).
        spatial_rel: Spatial relationship. Default: esriSpatialRelIntersects.
        where: SQL WHERE clause. Default: "1=1" (all features).
        out_fields: Comma-separated field names or "*" for all.
        max_features: Maximum features to return (capped at server max).
        out_sr: Output spatial reference WKID. Default: 4326 (WGS84).
        return_count_only: If True, return only the count of matching features.
        in_sr: Spatial reference of ``geometry``. Default 4326, which is
            what GeoJSON and Earth Engine objects are in.
        max_allowable_offset: Simplify returned shapes to this tolerance,
            in ``out_sr`` units.

    Returns:
        GeoJSON FeatureCollection dict, or {"count": N} if return_count_only.

    Raises:
        RuntimeError: The service refused the query; the message says why.
    """
    return _edw.query_features(
        service_name, layer_id, geometry=_ee_to_geojson(geometry),
        geometry_type=geometry_type, spatial_rel=spatial_rel, where=where,
        out_fields=out_fields, max_features=max_features, out_sr=out_sr,
        return_count_only=return_count_only, in_sr=in_sr,
        max_allowable_offset=max_allowable_offset,
    )


def query_features_with_pagination(
    service_name: str,
    layer_id: int,
    geometry: Any = None,
    geometry_type: str = "esriGeometryEnvelope",
    spatial_rel: str = "esriSpatialRelIntersects",
    where: str = "1=1",
    out_fields: str = "*",
    max_features: int = 5000,
    out_sr: int = 4326,
    in_sr: int | None = None,
) -> dict:
    """Query features with automatic pagination to get more than one page of results.

    Same args as :func:`query_features`, but ``max_features`` can exceed
    the server's per-request limit. Returns a combined GeoJSON
    FeatureCollection.
    """
    return _edw.query_features_with_pagination(
        service_name, layer_id, geometry=_ee_to_geojson(geometry),
        geometry_type=geometry_type, spatial_rel=spatial_rel, where=where,
        out_fields=out_fields, max_features=max_features, out_sr=out_sr,
        in_sr=in_sr,
    )


def _ee_to_geojson(geometry):
    """An ee.Geometry / ee.Feature / ee.FeatureCollection as GeoJSON.

    query_features used to hand these straight to json.dumps, which fails
    with "Object of type Geometry is not JSON serializable" -- and an ee
    object is what an Earth Engine workflow has in hand ("forests
    intersecting this state"). Duck-typed so this module never imports ee.
    """
    if geometry is None or isinstance(geometry, (dict, str)) or not hasattr(geometry, "getInfo"):
        return geometry
    if hasattr(geometry, "geometry"):          # Feature / FeatureCollection
        geometry = geometry.geometry()
    return geometry.getInfo()
