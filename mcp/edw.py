"""
USFS Enterprise Data Warehouse (EDW) REST API client.

Provides search, metadata inspection, and spatial feature queries against
the ArcGIS REST services at https://apps.fs.usda.gov/arcx/rest/services/EDW.

Used by server.py to expose EDW tools via MCP.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EDW_BASE_URL = "https://apps.fs.usda.gov/arcx/rest/services/EDW"
_TIMEOUT = 30  # seconds for HTTP requests
_MAX_RECORD_COUNT = 2000  # ArcGIS server default max

# ---------------------------------------------------------------------------
# Theme catalog — maps EDW service names to thematic categories + descriptions.
# Sourced from https://data.fs.usda.gov/geodata/edw/datasets.php
# This enables search by theme keyword (e.g. "riparian" → inland waters services)
# ---------------------------------------------------------------------------

_SERVICE_THEMES: dict[str, dict[str, str]] = {
    # --- Biota ---
    "EDW_CicadaBroods_01": {"theme": "biota", "desc": "Active Periodical Cicada Broods of the United States"},
    "EDW_InvasiveSpecies_01": {"theme": "biota", "desc": "Current Invasive Plants"},
    "EDW_ExistingVegetation_01": {"theme": "biota", "desc": "Existing Vegetation (Region 5 CALVEG)"},
    "EDW_AquaticOrganismPassage_01": {"theme": "biota", "desc": "Aquatic Organism Passage: activities, habitat miles, surveys"},
    # --- Boundaries ---
    "EDW_ForestSystemBoundaries_01": {"theme": "boundaries", "desc": "Administrative Forest Boundaries"},
    "EDW_BipartisanInfrastructureLaw_01": {"theme": "boundaries", "desc": "Bipartisan Infrastructure Law Landscape Investments"},
    "EDW_ExperimentalForestandRange_01": {"theme": "boundaries", "desc": "Experimental Forest and Range Areas and Locations"},
    "EDW_ForestCommonNames_01": {"theme": "boundaries", "desc": "Forest Common Names"},
    "EDW_LandAndWaterConservationFundParcels_01": {"theme": "boundaries", "desc": "Forest Service LWCF Parcels"},
    "EDW_RegionalBoundaries_01": {"theme": "boundaries", "desc": "Forest Service Regional Boundaries"},
    "EDW_BasicOwnership_01": {"theme": "boundaries", "desc": "Surface Ownership Parcels (basic)"},
    "EDW_SurfaceOwnership_01": {"theme": "boundaries", "desc": "Surface Ownership Parcels (detailed)"},
    "EDW_NationalForestLands_01": {"theme": "boundaries", "desc": "National Forest System Land Units"},
    "EDW_NationalGrasslandUnits_01": {"theme": "boundaries", "desc": "National Grassland Units"},
    "EDW_Wilderness_01": {"theme": "boundaries", "desc": "National Wilderness Areas"},
    "EDW_WildernessFSOnly_01": {"theme": "boundaries", "desc": "Wilderness Areas: Legal Status (FS only)"},
    "EDW_WildScenicRiver_01": {"theme": "boundaries", "desc": "National Wild and Scenic Rivers: lines, segments, legal status"},
    "EDW_ProclaimedForestBoundaries_01": {"theme": "boundaries", "desc": "Original Proclaimed National Forest Boundaries"},
    "EDW_ProclaimedForestsAndGrasslands_01": {"theme": "boundaries", "desc": "Proclaimed National Forests and National Grasslands"},
    "EDW_RangerDistricts_01": {"theme": "boundaries", "desc": "Ranger District Boundaries"},
    "EDW_ResearchStations_01": {"theme": "boundaries", "desc": "Research Station Boundaries"},
    "EDW_RightofWay_01": {"theme": "boundaries", "desc": "Right of Way"},
    "EDW_SpecialInterestMgmtAreas_01": {"theme": "boundaries", "desc": "Special Interest Management Areas"},
    "EDW_SpecialStatusAreas_01": {"theme": "boundaries", "desc": "Special Status Areas"},
    "EDW_TribalLands_01": {"theme": "boundaries", "desc": "Tribal Ceded Lands"},
    "EDW_PADUS_01": {"theme": "boundaries", "desc": "PADUS FS Managed Surface Ownership, Designated Areas, Easements"},
    "EDW_ALPStatusAndEncumbrance_01": {"theme": "boundaries", "desc": "Land status, encumbrance, mineral rights, survey boundaries"},
    # --- Environment ---
    "EDW_ActivityRangeVegetationImprovement_01": {"theme": "environment", "desc": "Range Vegetation Improvement Activities"},
    "EDW_ActivityTimberHarvests_01": {"theme": "environment", "desc": "Timber Harvests"},
    "EDW_ActivityHazFuelTrt_01": {"theme": "environment", "desc": "Hazardous Fuel Treatment Reduction"},
    "EDW_ActivitySilvicultureTimberStandImprovement_01": {"theme": "environment", "desc": "Silviculture Timber Stand Improvement"},
    "EDW_SilvicultureReforestation_01": {"theme": "environment", "desc": "Silviculture Reforestation"},
    "EDW_SilvicultureReforestationNeeds_01": {"theme": "environment", "desc": "Silviculture Reforestation Needs"},
    "EDW_CFLRP_01": {"theme": "environment", "desc": "Collaborative Forest Landscape Restoration Program"},
    "EDW_StewardshipContracting_01": {"theme": "environment", "desc": "Stewardship Contracting"},
    "EDW_WesternBarkBeetleStrategy_01": {"theme": "environment", "desc": "Western Bark Beetle Strategy"},
    "EDW_HealthyForestRestorationAct_01": {"theme": "environment", "desc": "Healthy Forest Restoration Act Activities"},
    "EDW_RecreationSites_01": {"theme": "environment", "desc": "Recreation Sites Public Information"},
    "EDW_AerialFireRetardantAvoidanceAreas_Terrestrial_01": {"theme": "environment", "desc": "Aerial Fire Retardant Avoidance Areas: Terrestrial"},
    "EDW_ClimateShield_01": {"theme": "environment", "desc": "Climate Shield: Bull Trout and Cutthroat Trout habitat (1980/2040/2080)"},
    "EDW_TEUInventoryStatus_01": {"theme": "environment", "desc": "Ecosystem Terrestrial Ecological Unit Inventory Status"},
    "EDW_ActivityFactsCommonAttributes_01": {"theme": "environment", "desc": "FACTS Common Attributes (all regions)"},
    "EDW_FireOccurrence6thEdition_01": {"theme": "environment", "desc": "FIRESTAT Fire Occurrence (yearly update)"},
    "EDW_FireOccurrenceAndPerimeter_01": {"theme": "environment", "desc": "National USFS Fire Occurrence and Perimeter"},
    "EDW_CommWildfireDefenseGrant_01": {"theme": "environment", "desc": "Community Wildfire Defense Grant"},
    "EDW_Fireshed_01": {"theme": "environment", "desc": "Fireshed Registry: Fireshed and Project Areas"},
    "EDW_HazardousSites_01": {"theme": "environment", "desc": "Hazardous Sites"},
    "EDW_NorWeST_StreamTemperatures_01": {"theme": "environment", "desc": "NorWeST Stream Temperatures: observed points and predicted lines"},
    "EDW_RAVG_01": {"theme": "environment", "desc": "RAVG Postfire Vegetation Change Perimeters"},
    "EDW_MTBS_01": {"theme": "environment", "desc": "Monitoring Trends in Burn Severity: fire occurrence and burned area boundaries 1984-present"},
    "EDW_BurnedAreaEmergencyResponse_01": {"theme": "environment", "desc": "Burned Area Emergency Response (BAER)"},
    "EDW_HistoricalWoodlandDensity_01": {"theme": "environment", "desc": "Historical Woodland Density of the Conterminous U.S., 1873"},
    "EDW_BaileysEcoregions_01": {"theme": "environment", "desc": "Bailey's Ecoregions: provinces, sections, subsections"},
    "EDW_Ecomap2025_01": {"theme": "environment", "desc": "Ecomap 2025: domains, divisions, provinces, sections, subsections"},
    # --- Geoscientific Information ---
    "EDW_EcologicalProvinces_01": {"theme": "geoscientific", "desc": "Ecological Provinces"},
    "EDW_EcologicalSections_01": {"theme": "geoscientific", "desc": "Ecological Sections"},
    "EDW_EcologicalSubsections_01": {"theme": "geoscientific", "desc": "Ecological Subsections"},
    "EDW_TongassLandslide_01": {"theme": "geoscientific", "desc": "Tongass Landslide Areas and Initiation"},
    # --- Inland Waters ---
    "EDW_AerialFireRetardantAvoidanceAreas_Aquatic_01": {"theme": "inland_waters", "desc": "Aerial Fire Retardant Avoidance Areas: Aquatic"},
    "EDW_HydroPercentStreamFlowNFSAnnual_01": {"theme": "inland_waters", "desc": "Fraction of Runoff from Forest Service Lands (Annual)"},
    "EDW_HydroPercentStreamFlowNFSSummer_01": {"theme": "inland_waters", "desc": "Fraction of Runoff from Forest Service Lands (Summer)"},
    "EDW_GreatBasinMountainRangesWatersheds_01": {"theme": "inland_waters", "desc": "Great Basin Montane Watersheds: streams, valley bottoms, pour points"},
    "EDW_HydroFlowMetricsHistorical_01": {"theme": "inland_waters", "desc": "Hydro Flow Metrics: Historical"},
    "EDW_HydroFlowMetrics2040_01": {"theme": "inland_waters", "desc": "Hydro Flow Metrics: Mid-Century (2040)"},
    "EDW_HydroFlowMetrics2080_01": {"theme": "inland_waters", "desc": "Hydro Flow Metrics: End-of-Century (2080)"},
    "EDW_HydroFlowMetricsAbsChange2040_01": {"theme": "inland_waters", "desc": "Hydro Flow Metrics: Absolute Change by Mid-Century"},
    "EDW_HydroFlowMetricsAbsChange2080_01": {"theme": "inland_waters", "desc": "Hydro Flow Metrics: Absolute Change by End-of-Century"},
    "EDW_HydroFlowMetricsPercentChange2040_01": {"theme": "inland_waters", "desc": "Hydro Flow Metrics: Percent Change by Mid-Century"},
    "EDW_HydroFlowMetricsPercentChange2080_01": {"theme": "inland_waters", "desc": "Hydro Flow Metrics: Percent Change by End-of-Century"},
    "EDW_Watersheds_01": {"theme": "inland_waters", "desc": "Watershed Condition Classification"},
    "EDW_PriorityWatersheds_01": {"theme": "inland_waters", "desc": "Priority Watersheds"},
    # --- Planning Cadastre ---
    "EDW_LandUtilization_01": {"theme": "planning_cadastre", "desc": "Land Utilization"},
    "EDW_PLSS_01": {"theme": "planning_cadastre", "desc": "Public Land Survey System: corners, monuments, sections, townships"},
    # --- Structure ---
    "EDW_CommunicationsSites_01": {"theme": "structure", "desc": "Communications Sites Special Use Authorizations"},
    "EDW_DevelopedSites_01": {"theme": "structure", "desc": "Forest Service developed sites subject to regulation"},
    "EDW_ResearchStationFacilities_01": {"theme": "structure", "desc": "Research Station Facilities"},
    # --- Transportation ---
    "EDW_MVUM_Roads_01": {"theme": "transportation", "desc": "Motor Vehicle Use Map: Roads"},
    "EDW_MVUM_Trails_01": {"theme": "transportation", "desc": "Motor Vehicle Use Map: Trails"},
    "EDW_Roads_01": {"theme": "transportation", "desc": "National Forest System Roads"},
    "EDW_Trails_01": {"theme": "transportation", "desc": "National Forest System Trails"},
}

# Keyword aliases: map common search terms to themes or service name fragments.
# This allows searches like "riparian" to find relevant services even when the
# exact word doesn't appear in the service name.
_KEYWORD_ALIASES: dict[str, list[str]] = {
    # Water-related
    "riparian": ["inland_waters", "stream", "hydro", "watershed", "aquatic", "norwest"],
    "wetland": ["inland_waters", "hydro", "watershed"],
    "river": ["wild scenic river", "inland_waters", "hydro"],
    "creek": ["stream", "inland_waters", "hydro"],
    "lake": ["inland_waters", "hydro", "watershed"],
    "fish": ["aquatic organism", "climate shield", "norwest", "biota"],
    "aquatic": ["aquatic", "inland_waters", "stream", "climate shield"],
    # Fire-related
    "fire": ["fire", "mtbs", "burn", "ravg", "fireshed", "retardant"],
    "burn": ["mtbs", "burn", "baer", "ravg", "fire"],
    "wildfire": ["fire", "mtbs", "burn", "ravg", "fireshed"],
    # Vegetation / ecology
    "vegetation": ["vegetation", "existing vegetation", "biota", "calveg"],
    "timber": ["timber", "silviculture", "harvest"],
    "ecology": ["ecological", "ecoregion", "ecomap", "bailey", "geoscientific"],
    "habitat": ["climate shield", "aquatic organism", "biota"],
    "invasive": ["invasive", "biota"],
    # Land management
    "ownership": ["ownership", "basic ownership", "surface ownership", "padus"],
    "wilderness": ["wilderness", "roadless"],
    "recreation": ["recreation", "trail", "mvum"],
    "grazing": ["range vegetation", "grassland"],
    "mining": ["mineral", "hazardous"],
    "trail": ["trail", "mvum", "transportation"],
    "road": ["road", "mvum", "transportation"],
    # Administrative
    "ranger": ["ranger district", "boundaries"],
    "boundary": ["boundaries", "forest system", "proclaimed", "regional"],
    "tribal": ["tribal", "ceded"],
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fetch_json(url: str, params: dict[str, str] | None = None) -> dict:
    """GET a URL with optional query params, return parsed JSON."""
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "geeViz-MCP/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"EDW request failed ({exc.code}): {url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"EDW request error: {exc.reason}") from exc


def _post_json(url: str, params: dict[str, str]) -> dict:
    """POST form-encoded params, return parsed JSON. Used for large queries."""
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "User-Agent": "geeViz-MCP/1.0",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"EDW request failed ({exc.code}): {url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"EDW request error: {exc.reason}") from exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def search_services(query: str = "", theme: str = "") -> list[dict[str, str]]:
    """Search EDW services by keyword and/or theme.

    Uses three matching strategies (results are deduplicated):
    1. Substring match on service name (e.g. "mtbs" → EDW_MTBS_01)
    2. Keyword alias expansion (e.g. "riparian" → inland_waters theme + stream services)
    3. Theme filter (e.g. theme="inland_waters")

    Args:
        query: Search keyword (case-insensitive). Matches against service names,
               theme descriptions, and keyword aliases.
        theme: Filter by theme category. Valid themes: biota, boundaries,
               environment, geoscientific, inland_waters, planning_cadastre,
               structure, transportation. Pass "" to skip theme filtering.

    Returns a list of dicts with keys: name, type, url, theme, description.
    If both query and theme are empty, returns all services.
    """
    data = _fetch_json(EDW_BASE_URL, {"f": "pjson"})
    services = data.get("services", [])

    query_lower = query.lower().strip()
    theme_lower = theme.lower().strip()

    # Build expanded search terms from keyword aliases
    alias_terms: list[str] = []
    alias_themes: list[str] = []
    if query_lower and query_lower in _KEYWORD_ALIASES:
        for term in _KEYWORD_ALIASES[query_lower]:
            if term in (
                "biota", "boundaries", "environment", "geoscientific",
                "inland_waters", "planning_cadastre", "structure", "transportation",
            ):
                alias_themes.append(term)
            else:
                alias_terms.append(term.lower())

    seen = set()
    results = []

    for svc in services:
        full_name = svc.get("name", "")  # e.g. "EDW/EDW_MTBS_01"
        svc_type = svc.get("type", "MapServer")
        short_name = full_name.split("/", 1)[-1] if "/" in full_name else full_name

        if short_name in seen:
            continue

        # Look up theme metadata
        meta = _SERVICE_THEMES.get(short_name, {})
        svc_theme = meta.get("theme", "")
        svc_desc = meta.get("desc", "")

        # Apply theme filter
        if theme_lower and svc_theme != theme_lower:
            continue

        matched = False

        if not query_lower:
            matched = True
        else:
            # Strategy 1: substring match on service name
            if query_lower in short_name.lower():
                matched = True
            # Strategy 2: substring match on theme description
            elif query_lower in svc_desc.lower():
                matched = True
            # Strategy 3: keyword alias — match expanded terms against name + desc
            elif alias_terms:
                name_and_desc = (short_name + " " + svc_desc).lower()
                if any(t in name_and_desc for t in alias_terms):
                    matched = True
            # Strategy 4: keyword alias — match expanded themes
            if not matched and alias_themes and svc_theme in alias_themes:
                matched = True

        if matched:
            seen.add(short_name)
            results.append(
                {
                    "name": short_name,
                    "type": svc_type,
                    "url": f"{EDW_BASE_URL}/{short_name}/{svc_type}",
                    "theme": svc_theme or "uncategorized",
                    "description": svc_desc,
                }
            )

    return results


def get_service_info(service_name: str) -> dict[str, Any]:
    """Get metadata for an EDW MapServer service: description, layers, spatial ref.

    Args:
        service_name: Short service name, e.g. "EDW_MTBS_01".

    Returns:
        Dict with keys: name, description, spatialReference, layers (id, name,
        geometryType, defaultVisibility, minScale, maxScale).
    """
    url = f"{EDW_BASE_URL}/{service_name}/MapServer"
    data = _fetch_json(url, {"f": "pjson"})

    if "error" in data:
        raise RuntimeError(f"EDW service error: {data['error'].get('message', data['error'])}")

    layers = []
    for lyr in data.get("layers", []):
        layers.append(
            {
                "id": lyr.get("id"),
                "name": lyr.get("name", ""),
                "defaultVisibility": lyr.get("defaultVisibility", False),
                "minScale": lyr.get("minScale", 0),
                "maxScale": lyr.get("maxScale", 0),
            }
        )

    return {
        "name": data.get("mapName", service_name),
        "description": data.get("description", "").strip() or data.get("serviceDescription", "").strip(),
        "spatialReference": data.get("spatialReference", {}),
        "fullExtent": data.get("fullExtent", {}),
        "layers": layers,
    }


def get_layer_info(service_name: str, layer_id: int) -> dict[str, Any]:
    """Get detailed metadata for a specific layer: fields, geometry type, capabilities.

    Args:
        service_name: Short service name, e.g. "EDW_MTBS_01".
        layer_id: Layer ID within the service.

    Returns:
        Dict with keys: name, geometryType, description, fields, extent,
        maxRecordCount, supportedQueryFormats.
    """
    url = f"{EDW_BASE_URL}/{service_name}/MapServer/{layer_id}"
    data = _fetch_json(url, {"f": "pjson"})

    if "error" in data:
        raise RuntimeError(f"EDW layer error: {data['error'].get('message', data['error'])}")

    fields = []
    for f in data.get("fields", []):
        fields.append(
            {
                "name": f.get("name"),
                "type": f.get("type", "").replace("esriFieldType", ""),
                "alias": f.get("alias", ""),
            }
        )

    return {
        "name": data.get("name", ""),
        "geometryType": data.get("geometryType", ""),
        "description": data.get("description", ""),
        "fields": fields,
        "extent": data.get("extent", {}),
        "maxRecordCount": data.get("maxRecordCount", _MAX_RECORD_COUNT),
        "supportedQueryFormats": data.get("supportedQueryFormats", ""),
    }


def query_features(
    service_name: str,
    layer_id: int,
    geometry: dict | str | None = None,
    geometry_type: str = "esriGeometryEnvelope",
    spatial_rel: str = "esriSpatialRelIntersects",
    where: str = "1=1",
    out_fields: str = "*",
    max_features: int = 1000,
    out_sr: int = 4326,
    return_count_only: bool = False,
) -> dict:
    """Query features from an EDW layer, optionally filtered by spatial intersection.

    Args:
        service_name: Short service name, e.g. "EDW_MTBS_01".
        layer_id: Layer ID within the service.
        geometry: Geometry for spatial filter. Can be:
            - A GeoJSON geometry dict (Point, Polygon, Envelope-style bbox)
            - An Esri JSON geometry string/dict
            - A bbox string "xmin,ymin,xmax,ymax"
            - None for no spatial filter
        geometry_type: Esri geometry type. Common values:
            esriGeometryPoint, esriGeometryEnvelope, esriGeometryPolygon
        spatial_rel: Spatial relationship. Default: esriSpatialRelIntersects.
        where: SQL WHERE clause. Default: "1=1" (all features).
        out_fields: Comma-separated field names or "*" for all.
        max_features: Maximum features to return (capped at server max).
        out_sr: Output spatial reference WKID. Default: 4326 (WGS84).
        return_count_only: If True, return only the count of matching features.

    Returns:
        GeoJSON FeatureCollection dict, or {"count": N} if return_count_only.
    """
    url = f"{EDW_BASE_URL}/{service_name}/MapServer/{layer_id}/query"

    params: dict[str, str] = {
        "where": where,
        "outFields": out_fields,
        "outSR": str(out_sr),
        "f": "geojson",
        "resultRecordCount": str(min(max_features, _MAX_RECORD_COUNT)),
    }

    if return_count_only:
        params["returnCountOnly"] = "true"
        params["f"] = "json"

    if geometry is not None:
        geom_str = _convert_geometry(geometry, geometry_type)
        params["geometry"] = geom_str
        params["geometryType"] = geometry_type
        params["spatialRel"] = spatial_rel
        params["inSR"] = str(out_sr)

    # Use POST for large payloads (polygon geometries can be big)
    data = _post_json(url, params)

    if "error" in data:
        raise RuntimeError(f"EDW query error: {data['error'].get('message', data['error'])}")

    if return_count_only:
        return {"count": data.get("count", 0)}

    return _sanitize_for_ee(data)


def _convert_geometry(geometry: dict | str, geometry_type: str) -> str:
    """Convert geometry input to Esri-compatible JSON string for query params.

    Handles:
    - Bbox string "xmin,ymin,xmax,ymax" → Esri envelope JSON
    - GeoJSON geometry dict → Esri JSON
    - Already-Esri JSON dict → pass through
    - String → pass through
    """
    # Simple bbox string
    if isinstance(geometry, str):
        # Check if it's a simple bbox: "xmin,ymin,xmax,ymax"
        parts = geometry.split(",")
        if len(parts) == 4:
            try:
                xmin, ymin, xmax, ymax = [float(p.strip()) for p in parts]
                return json.dumps(
                    {"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax}
                )
            except ValueError:
                pass
        return geometry  # pass through as-is

    if isinstance(geometry, dict):
        # Already Esri-style envelope
        if "xmin" in geometry:
            return json.dumps(geometry)

        # Already Esri-style rings/points
        if "rings" in geometry or "x" in geometry or "points" in geometry:
            return json.dumps(geometry)

        # GeoJSON → Esri JSON conversion
        geom_type = geometry.get("type", "")
        coords = geometry.get("coordinates")

        if geom_type == "Point" and coords:
            return json.dumps({"x": coords[0], "y": coords[1]})

        if geom_type == "Polygon" and coords:
            # GeoJSON polygon rings → Esri rings
            return json.dumps({"rings": coords})

        if geom_type == "MultiPolygon" and coords:
            # Flatten all rings
            rings = []
            for polygon in coords:
                rings.extend(polygon)
            return json.dumps({"rings": rings})

        # Fallback: serialize as-is
        return json.dumps(geometry)

    return json.dumps(geometry)


def _sanitize_for_ee(geojson: dict) -> dict:
    """Sanitize a GeoJSON FeatureCollection for Earth Engine compatibility.

    - Removes properties with dots in the name (e.g. 'SHAPE.LEN') — EE rejects them
    - Ensures each feature has a string 'id' — EE requires system:index to be a string
    """
    for i, feat in enumerate(geojson.get("features", [])):
        props = feat.get("properties", {})
        bad_keys = [k for k in props if "." in k]
        for k in bad_keys:
            del props[k]
        feat["id"] = str(i)
    return geojson


def query_features_with_pagination(
    service_name: str,
    layer_id: int,
    geometry: dict | str | None = None,
    geometry_type: str = "esriGeometryEnvelope",
    spatial_rel: str = "esriSpatialRelIntersects",
    where: str = "1=1",
    out_fields: str = "*",
    max_features: int = 5000,
    out_sr: int = 4326,
) -> dict:
    """Query features with automatic pagination to get more than 2000 results.

    Same args as query_features, but max_features can exceed the server limit.
    Returns a combined GeoJSON FeatureCollection.
    """
    all_features = []
    offset = 0
    page_size = min(max_features, _MAX_RECORD_COUNT)

    while len(all_features) < max_features:
        url = f"{EDW_BASE_URL}/{service_name}/MapServer/{layer_id}/query"
        params: dict[str, str] = {
            "where": where,
            "outFields": out_fields,
            "outSR": str(out_sr),
            "f": "geojson",
            "resultRecordCount": str(page_size),
            "resultOffset": str(offset),
        }

        if geometry is not None:
            geom_str = _convert_geometry(geometry, geometry_type)
            params["geometry"] = geom_str
            params["geometryType"] = geometry_type
            params["spatialRel"] = spatial_rel
            params["inSR"] = str(out_sr)

        data = _post_json(url, params)

        if "error" in data:
            raise RuntimeError(f"EDW query error: {data['error'].get('message', data['error'])}")

        features = data.get("features", [])
        if not features:
            break

        all_features.extend(features)
        offset += len(features)

        # If we got fewer than page_size, we've hit the end
        if len(features) < page_size:
            break

    # Trim to max_features
    all_features = all_features[:max_features]

    return _sanitize_for_ee({
        "type": "FeatureCollection",
        "features": all_features,
    })
