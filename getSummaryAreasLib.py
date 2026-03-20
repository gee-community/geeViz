"""
Functions for retrieving common summary and study area FeatureCollections.

geeViz.getSummaryAreasLib provides helpers that return filtered
``ee.FeatureCollection`` objects for political boundaries, USFS
administrative units, census geographies, buildings, roads, protected
areas, and more.  Every public function accepts an ``area`` parameter
(an ``ee.FeatureCollection``, ``ee.Feature``, or ``ee.Geometry``) that
is used to spatially filter the result.
"""

"""
   Copyright 2026 Ian Housman

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

import ee

# ---------------------------------------------------------------------------
#  Asset IDs
# ---------------------------------------------------------------------------
# Custom RCR assets (public)
_USFS_FORESTS = "projects/rcr-geeviz/assets/public/summaryAreas/S_USA-AdministrativeForest_3-26-25"
_USFS_DISTRICTS = "projects/rcr-geeviz/assets/public/summaryAreas/S_USA-RangerDistrict_3-26-25"
_USFS_REGIONS = "projects/rcr-geeviz/assets/public/summaryAreas/FS_Region_Boundaries"
_TIGER_URBAN_AREAS = "projects/rcr-geeviz/assets/public/summaryAreas/TIGER_Urban_Areas_2024"
_TIGER_COUNTIES = "projects/rcr-geeviz/assets/public/summaryAreas/tl_2024_us_county_wNames"

# Official GEE datasets
_TIGER_STATES = "TIGER/2018/States"
_TIGER_ROADS = "TIGER/2016/Roads"
_TIGER_BLOCKS_2020 = "TIGER/2020/TABBLOCK20"
_TIGER_BLOCK_GROUPS_2020 = "TIGER/2020/BG"
_TIGER_TRACTS_2020 = "TIGER/2020/TRACT"

# Admin boundary sources — keyed by (source, level)
# geoBoundaries v6 (official GEE catalog, levels 0-2)
_GEOB_V6 = {
    0: "WM/geoLab/geoBoundaries/600/ADM0",
    1: "WM/geoLab/geoBoundaries/600/ADM1",
    2: "WM/geoLab/geoBoundaries/600/ADM2",
}

# FAO GAUL 2015 (official GEE catalog, levels 0-2)
_GAUL_2015 = {
    0: "FAO/GAUL/2015/level0",
    1: "FAO/GAUL/2015/level1",
    2: "FAO/GAUL/2015/level2",
}

# FAO GAUL 2024 (community catalog, levels 0-2)
_GAUL_2024 = {
    0: "projects/sat-io/open-datasets/FAO/GAUL/GAUL_2024_L0",
    1: "projects/sat-io/open-datasets/FAO/GAUL/GAUL_2024_L1",
    2: "projects/sat-io/open-datasets/FAO/GAUL/GAUL_2024_L2",
}

# FieldMaps humanitarian edge-matched (community catalog, levels 1-4)
_FIELDMAPS = {
    1: "projects/sat-io/open-datasets/field-maps/edge-matched-humanitarian/adm1_polygons",
    2: "projects/sat-io/open-datasets/field-maps/edge-matched-humanitarian/adm2_polygons",
    3: "projects/sat-io/open-datasets/field-maps/edge-matched-humanitarian/adm3_polygons",
    4: "projects/sat-io/open-datasets/field-maps/edge-matched-humanitarian/adm4_polygons",
}

_ADMIN_SOURCES = {
    "geob": _GEOB_V6,
    "gaul": _GAUL_2015,
    "gaul2024": _GAUL_2024,
    "fieldmaps": _FIELDMAPS,
}

# Name properties for each source (the column containing the admin unit name)
_ADMIN_NAME_PROPS = {
    "geob": "shapeName",
    "gaul": lambda level: f"ADM{level}_NAME",
    "gaul2024": lambda level: f"gaul{level}_name",
    "fieldmaps": lambda level: f"adm{level}_name",
}

# Buildings
_VIDA_COMBINED_ROOT = "projects/sat-io/open-datasets/VIDA_COMBINED"
_MS_BUILDINGS_ROOT = "projects/sat-io/open-datasets/MSBuildings"
_GOOGLE_OPEN_BUILDINGS = "GOOGLE/Research/open-buildings/v3/polygons"

# Protected areas
_WDPA = "WCMC/WDPA/current/polygons"


# ---------------------------------------------------------------------------
#  Internal helpers
# ---------------------------------------------------------------------------
def _to_geometry(area):
    """Convert an ee.FeatureCollection, ee.Feature, or ee.Geometry to ee.Geometry."""
    if isinstance(area, ee.FeatureCollection):
        return area.geometry()
    elif isinstance(area, ee.Feature):
        return area.geometry()
    elif isinstance(area, ee.Geometry):
        return area
    raise TypeError(f"Expected ee.FeatureCollection, ee.Feature, or ee.Geometry, got {type(area)}")


def _filter_bounds(asset_id, area):
    """Load a FeatureCollection and filter by area bounds."""
    return ee.FeatureCollection(asset_id).filterBounds(_to_geometry(area))


def _get_intersecting_country_names(area, source="geob"):
    """Return a server-side ee.List of country names that intersect ``area``."""
    geom = _to_geometry(area)
    asset = _ADMIN_SOURCES.get(source, _GEOB_V6).get(0, _GEOB_V6[0])
    name_prop = getAdminNameProperty(level=0, source=source) if source in _ADMIN_NAME_PROPS else "shapeName"
    return ee.FeatureCollection(asset).filterBounds(geom).aggregate_array(name_prop)


def _get_intersecting_country_iso3(area):
    """Return ee.List of ISO-3 codes that intersect ``area`` (via geoBoundaries v6)."""
    geom = _to_geometry(area)
    countries = ee.FeatureCollection(_GEOB_V6[0]).filterBounds(geom)
    return countries.aggregate_array("shapeGroup")


# ---------------------------------------------------------------------------
#  Political / administrative boundaries
# ---------------------------------------------------------------------------
def getAdminBoundaries(area, level=0, source="geob"):
    """Return administrative boundaries at a given level that intersect ``area``.

    Levels follow the standard admin hierarchy:

    - **0** — Countries
    - **1** — States / provinces
    - **2** — Districts / counties / municipalities
    - **3** — Sub-districts / wards (FieldMaps only)
    - **4** — Neighborhoods / localities (FieldMaps only)

    Available sources and their level coverage:

    - ``"geob"`` — geoBoundaries v6.0 (official GEE catalog, levels 0–2).
      Name property: ``shapeName``.
    - ``"gaul"`` — FAO GAUL 2015 (official GEE catalog, levels 0–2).
      Name property: ``ADM{level}_NAME`` (e.g. ``ADM0_NAME``).
    - ``"gaul2024"`` — FAO GAUL 2024 (community catalog, levels 0–2).
      Name property: ``gaul{level}_name``.
    - ``"fieldmaps"`` — FieldMaps humanitarian edge-matched boundaries
      (community catalog, levels 1–4). Name property:
      ``adm{level}_name``. Includes parent admin names and ISO codes.

    For levels 3–4, if the requested source doesn't support them the
    function automatically falls back to FieldMaps.

    Args:
        area: ee.FeatureCollection, ee.Feature, or ee.Geometry to filter by.
        level (int): Administrative level (0–4). Default ``0``.
        source (str): Boundary source. Default ``"geob"``.

    Returns:
        ee.FeatureCollection of admin boundary polygons.

    Example:
        >>> countries = getAdminBoundaries(my_area, level=0)
        >>> states = getAdminBoundaries(my_area, level=1)
        >>> districts = getAdminBoundaries(my_area, level=2, source="gaul")
        >>> wards = getAdminBoundaries(my_area, level=3)  # auto-uses FieldMaps
    """
    source_assets = _ADMIN_SOURCES.get(source)
    if source_assets is None:
        raise ValueError(
            f"Unknown source: {source!r}. "
            f"Use one of: {', '.join(repr(s) for s in _ADMIN_SOURCES)}."
        )
    asset = source_assets.get(level)

    # Auto-fallback to FieldMaps for levels not in the requested source
    if asset is None and source != "fieldmaps":
        asset = _FIELDMAPS.get(level)

    if asset is None:
        available = sorted(source_assets.keys())
        raise ValueError(
            f"Admin level {level} is not available for source {source!r}. "
            f"Available levels: {available}. "
            f"Levels 3–4 are available via source='fieldmaps'."
        )

    return _filter_bounds(asset, area)


def getAdminNameProperty(level=0, source="geob"):
    """Return the feature property name that contains the admin unit name.

    Useful for setting ``feature_label`` in ``summarize_and_chart`` or
    ``selectLayerNameProperty`` in ``Map.addSelectLayer``.

    Args:
        level (int): Administrative level (0–4).
        source (str): Boundary source (same options as :func:`getAdminBoundaries`).

    Returns:
        str: The property name (e.g. ``"shapeName"``, ``"ADM1_NAME"``).

    Example:
        >>> prop = getAdminNameProperty(level=1, source="gaul")  # "ADM1_NAME"
    """
    name_prop = _ADMIN_NAME_PROPS.get(source)
    if name_prop is None:
        raise ValueError(f"Unknown source: {source!r}.")
    if callable(name_prop):
        return name_prop(level)
    return name_prop




# ---------------------------------------------------------------------------
#  US-specific political/census boundaries
# ---------------------------------------------------------------------------
def getUSStates(area):
    """Return US state boundaries (TIGER 2018) that intersect ``area``.

    Properties include ``NAME``, ``STUSPS`` (abbreviation), ``STATEFP``
    (FIPS code), ``REGION``, ``DIVISION``.

    Args:
        area: ee.FeatureCollection, ee.Feature, or ee.Geometry.

    Returns:
        ee.FeatureCollection.
    """
    return _filter_bounds(_TIGER_STATES, area)


def getUSCounties(area, state_fips=None, state_abbr=None):
    """Return US county boundaries that intersect ``area``.

    Optionally filter to a single state by FIPS code or postal abbreviation.

    Properties include ``NAME``, ``FULL_NAME``, ``STATEFP``, ``STUSPS``,
    ``COUNTYFP``, ``GEOID``.

    Args:
        area: ee.FeatureCollection, ee.Feature, or ee.Geometry.
        state_fips (str, optional): Two-digit state FIPS (e.g. ``"49"`` for Utah).
        state_abbr (str, optional): Two-letter postal abbreviation (e.g. ``"UT"``).

    Returns:
        ee.FeatureCollection.
    """
    fc = _filter_bounds(_TIGER_COUNTIES, area)
    if state_fips is not None:
        fc = fc.filter(ee.Filter.eq("STATEFP", state_fips))
    if state_abbr is not None:
        fc = fc.filter(ee.Filter.eq("STUSPS", state_abbr.upper()))
    return fc


def getUSUrbanAreas(area):
    """Return TIGER 2024 urban area boundaries that intersect ``area``.

    Properties include ``NAME20``, ``NAMELSAD20``, ``ALAND20``, ``AWATER20``.

    Args:
        area: ee.FeatureCollection, ee.Feature, or ee.Geometry.

    Returns:
        ee.FeatureCollection.
    """
    return _filter_bounds(_TIGER_URBAN_AREAS, area)


def getUSCensusBlocks(area):
    """Return TIGER 2020 census blocks that intersect ``area``.

    .. warning::
        Census blocks are extremely numerous.  Use a small study area
        or the query may be slow / exceed memory limits.

    Args:
        area: ee.FeatureCollection, ee.Feature, or ee.Geometry.

    Returns:
        ee.FeatureCollection.
    """
    return _filter_bounds(_TIGER_BLOCKS_2020, area)


def getUSBlockGroups(area):
    """Return TIGER 2020 census block groups that intersect ``area``.

    Args:
        area: ee.FeatureCollection, ee.Feature, or ee.Geometry.

    Returns:
        ee.FeatureCollection.
    """
    return _filter_bounds(_TIGER_BLOCK_GROUPS_2020, area)


def getUSCensusTracts(area):
    """Return TIGER 2020 census tracts that intersect ``area``.

    Args:
        area: ee.FeatureCollection, ee.Feature, or ee.Geometry.

    Returns:
        ee.FeatureCollection.
    """
    return _filter_bounds(_TIGER_TRACTS_2020, area)


# ---------------------------------------------------------------------------
#  USFS Administrative boundaries
# ---------------------------------------------------------------------------
def getUSFSForests(area, region=None):
    """Return USFS National Forest boundaries that intersect ``area``.

    Properties include ``FORESTNAME``, ``FORESTNUMB``, ``REGION``,
    ``FORESTORGC``, ``GIS_ACRES``.

    Args:
        area: ee.FeatureCollection, ee.Feature, or ee.Geometry.
        region (str, optional): Two-digit USFS region number to filter by
            (e.g. ``"01"`` for Northern Region).

    Returns:
        ee.FeatureCollection.
    """
    fc = _filter_bounds(_USFS_FORESTS, area)
    if region is not None:
        fc = fc.filter(ee.Filter.eq("REGION", str(region).zfill(2)))
    return fc


def getUSFSDistricts(area, forest_name=None, region=None):
    """Return USFS Ranger District boundaries that intersect ``area``.

    Properties include ``DISTRICTNA``, ``FORESTNAME``, ``FORESTNUMB``,
    ``REGION``, ``GIS_ACRES``.

    Args:
        area: ee.FeatureCollection, ee.Feature, or ee.Geometry.
        forest_name (str, optional): Filter to districts within a specific
            National Forest (exact match on ``FORESTNAME``).
        region (str, optional): Two-digit USFS region number.

    Returns:
        ee.FeatureCollection.
    """
    fc = _filter_bounds(_USFS_DISTRICTS, area)
    if forest_name is not None:
        fc = fc.filter(ee.Filter.eq("FORESTNAME", forest_name))
    if region is not None:
        fc = fc.filter(ee.Filter.eq("REGION", str(region).zfill(2)))
    return fc


def getUSFSRegions(area):
    """Return USFS region boundaries that intersect ``area``.

    Properties include ``REGION``, ``REGIONNAME``, ``REGIONHEAD``
    (headquarters city), ``FS_ADMINAC`` (admin acres).

    Args:
        area: ee.FeatureCollection, ee.Feature, or ee.Geometry.

    Returns:
        ee.FeatureCollection with one feature per USFS region.
    """
    return _filter_bounds(_USFS_REGIONS, area)


# ---------------------------------------------------------------------------
#  Roads
# ---------------------------------------------------------------------------
def getRoads(area):
    """Return TIGER 2016 road features that intersect ``area``.

    Properties include ``fullname``, ``mtfcc`` (MAF/TIGER Feature Class
    Code), ``rttyp`` (route type), ``linearid``.

    Common MTFCC codes:

    - ``S1100`` — Primary road (interstate)
    - ``S1200`` — Secondary road (US/state highway)
    - ``S1400`` — Local road
    - ``S1500`` — Vehicular trail (4WD)
    - ``S1630`` — Ramp
    - ``S1640`` — Service drive
    - ``S1730`` — Alley
    - ``S1780`` — Parking lot road
    - ``S1820`` — Bike path / trail

    Args:
        area: ee.FeatureCollection, ee.Feature, or ee.Geometry.

    Returns:
        ee.FeatureCollection.

    Example:
        >>> interstates = getRoads(my_area).filter(ee.Filter.eq('mtfcc', 'S1100'))
    """
    return _filter_bounds(_TIGER_ROADS, area)


# ---------------------------------------------------------------------------
#  Buildings
# ---------------------------------------------------------------------------
def getBuildings(area, source="vida"):
    """Return building footprints that intersect ``area``.

    This function determines which countries intersect the given area,
    then loads and merges per-country building footprint collections.

    Args:
        area: ee.FeatureCollection, ee.Feature, or ee.Geometry.
        source (str): Building footprint source.

            - ``"vida"`` — VIDA Combined Building Footprints (179 countries,
              ISO-3 keyed).  Properties: ``area_in_meters``, ``confidence``,
              ``bf_source``.
            - ``"ms"`` — Microsoft Building Footprints (202 countries,
              country-name keyed).  Properties vary by country.
            - ``"google"`` — Google Open Buildings v3 (Africa, South/Southeast
              Asia).  Properties: ``area_in_meters``, ``confidence``,
              ``full_plus_code``.

    Returns:
        ee.FeatureCollection of building footprint polygons.

    Note:
        Building collections are very large.  Use a small study area
        or the query may be slow / exceed memory limits.

    Example:
        >>> buildings = getBuildings(ee.Geometry.Point([-111, 40.7]).buffer(1000))
    """
    geom = _to_geometry(area)

    if source == "google":
        return ee.FeatureCollection(_GOOGLE_OPEN_BUILDINGS).filterBounds(geom)

    if source == "vida":
        return _get_multi_country_fc(
            geom,
            root=_VIDA_COMBINED_ROOT,
            key_type="iso3",
        )

    if source == "ms":
        return _get_multi_country_fc(
            geom,
            root=_MS_BUILDINGS_ROOT,
            key_type="country_name",
        )

    raise ValueError(f"Unknown building source: {source!r}. Use 'vida', 'ms', or 'google'.")


# Country-name mapping for MS Buildings (ISO-3 → folder name)
_MS_ISO3_TO_NAME = {
    "USA": "US", "GBR": "United_Kingdom", "DEU": "Germany", "FRA": "France",
    "ITA": "Italy", "ESP": "Spain", "CAN": "Canada", "AUS": "Australia",
    "BRA": "Brazil", "MEX": "Mexico", "ARG": "Argentina", "COL": "Colombia",
    "PER": "Peru", "CHL": "Chile", "JPN": "Japan", "CHN": "China",
    "IND": "India", "RUS": "Russia", "ZAF": "South_Africa", "NGA": "Nigeria",
    "KEN": "Kenya", "EGY": "Egypt", "MAR": "Morocco", "DZA": "Algeria",
    "TUN": "Tunisia", "LBY": "Libya", "SDN": "Sudan", "ETH": "Ethiopia",
    "TZA": "Tanzania", "UGA": "Uganda", "GHA": "Ghana", "CMR": "Cameroon",
    "CIV": "Ivory_Coast", "SEN": "Senegal", "MLI": "Mali", "BFA": "Burkina_Faso",
    "NER": "Niger", "TCD": "Chad", "COD": "Congo_DRC", "COG": "Republic_of_the_Congo",
    "AGO": "Angola", "MOZ": "Mozambique", "MDG": "Madagascar", "MWI": "Malawi",
    "ZMB": "Zambia", "ZWE": "Zimbabwe", "BWA": "Botswana", "NAM": "Namibia",
    "SWZ": "Swaziland", "LSO": "Lesotho", "MUS": "Mauritius", "SYC": "Seychelles",
    "RWA": "Rwanda", "BDI": "Burundi", "SSD": "South_Sudan", "SOM": "Somalia",
    "DJI": "Djibouti", "ERI": "Eritrea", "CAF": "Central_African_Republic",
    "GNQ": "Equatorial_Guinea", "GAB": "Gabon", "STP": "Sao_Tome_and_Principe",
    "CPV": "Cape_Verde", "GMB": "The_Gambia", "GNB": "Guinea-Bissau",
    "GIN": "Guinea", "SLE": "Sierra_Leone", "LBR": "Liberia", "TGO": "Togo",
    "BEN": "Benin", "MRT": "Mauritania", "PAK": "Pakistan", "BGD": "Bangladesh",
    "LKA": "Sri_Lanka", "NPL": "Nepal", "BTN": "Bhutan", "MMR": "Myanmar",
    "THA": "Thailand", "VNM": "Vietnam", "LAO": "Laos", "KHM": "Cambodia",
    "MYS": "Malaysia", "IDN": "Indonesia", "PHL": "Philippines", "MNG": "Mongolia",
    "KAZ": "Kazakhstan", "UZB": "Uzbekistan", "TKM": "Turkmenistan",
    "TJK": "Tajikistan", "KGZ": "Kyrgyzstan", "AFG": "Afghanistan",
    "IRN": "Iran", "IRQ": "Iraq", "SYR": "Syria", "JOR": "Jordan",
    "LBN": "Lebanon", "ISR": "Israel", "SAU": "Kingdom_of_Saudi_Arabia",
    "YEM": "Republic_of_Yemen", "OMN": "Sultanate_of_Oman", "ARE": "United_Arab_Emirates",
    "QAT": "State_of_Qatar", "BHR": "Bahrain", "KWT": "Kuwait",
    "TUR": "Turkey", "GEO": "Georgia", "ARM": "Armenia", "AZE": "Azerbaijan",
    "UKR": "Ukraine", "BLR": "Belarus", "MDA": "Moldova", "ROU": "Romania",
    "BGR": "Bulgaria", "SRB": "Serbia", "MNE": "Montenegro", "BIH": "Bosnia_and_Herzegovina",
    "HRV": "Croatia", "SVN": "Slovenia", "MKD": "FYRO_Makedonija",
    "ALB": "Albania", "GRC": "Greece", "CYP": "Cyprus", "MLT": "Malta",
    "POL": "Poland", "CZE": "Czech_Republic", "SVK": "Slovakia", "HUN": "Hungary",
    "AUT": "Austria", "CHE": "Switzerland", "NLD": "Netherlands", "BEL": "Belgium",
    "LUX": "Luxembourg", "DNK": "Denmark", "SWE": "Sweden", "NOR": "Norway",
    "FIN": "Finland", "ISL": "Iceland", "IRL": "Ireland", "PRT": "Portugal",
    "EST": "Estonia", "LVA": "Latvia", "LTU": "Lithuania", "AND": "Andorra",
    "MCO": "Monaco", "SMR": "San_Marino", "VAT": "Vatican_City",
    "ECU": "Ecuador", "VEN": "Venezuela", "BOL": "Bolivia", "PRY": "Paraguay",
    "URY": "Uruguay", "GUY": "Guyana", "SUR": "Suriname", "GTM": "Guatemala",
    "HND": "Honduras", "SLV": "El_Salvador", "NIC": "Nicaragua", "CRI": "Costa_Rica",
    "PAN": "Panama", "CUB": "Cuba", "HTI": "Haiti", "DOM": "Dominican_Republic",
    "JAM": "Jamaica", "TTO": "Trinidad_and_Tobago", "BRB": "Barbados",
    "BHS": "The_Bahamas", "BLZ": "Belize", "GRD": "Grenada", "LCA": "Saint_Lucia",
    "DMA": "Dominica", "KNA": "St_Kitts_and_Nevis", "VCT": "St_Vincent_and_the_Grenadines",
    "ATG": "Antigua_and_Barbuda", "MDV": "Maldives", "BRN": "Brunei",
    "PNG": "Papua_New_Guinea", "KSV": "Kosovo",
}


def _get_multi_country_fc(geom, root, key_type="iso3"):
    """Load and merge per-country FeatureCollections that intersect ``geom``.

    Uses a client-side approach: first determines which countries intersect
    the area (via ``getInfo()``), then builds constant asset IDs and merges
    the results server-side.  This is necessary because ``ee.FeatureCollection``
    requires a constant string for the asset ID.

    Args:
        geom: ee.Geometry to filter by.
        root: Root asset folder (e.g. VIDA_COMBINED or MSBuildings).
        key_type: ``"iso3"`` for VIDA (subfolder is ISO-3 code) or
                  ``"country_name"`` for MS Buildings (subfolder is country name).

    Returns:
        ee.FeatureCollection — merged and spatially filtered.
    """
    # Client-side: determine which countries intersect
    iso3_codes = _get_intersecting_country_iso3(geom).getInfo()

    if not iso3_codes:
        return ee.FeatureCollection([])

    collections = []
    for iso3 in iso3_codes:
        if key_type == "iso3":
            asset_ids = [f"{root}/{iso3}"]
        else:
            country_name = _MS_ISO3_TO_NAME.get(iso3)
            if country_name is None:
                continue
            # Some MS Buildings entries (e.g. US) are IndexedFolders
            # with per-state sub-collections.  Try loading them and
            # fall back to listing sub-assets.
            asset_ids = [f"{root}/{country_name}"]

        for asset_id in asset_ids:
            try:
                # Verify asset is a TABLE, not an IndexedFolder
                info = ee.data.getAsset(asset_id)
                asset_type = info.get("type", "")
                if asset_type in ("TABLE", "FEATURE_COLLECTION"):
                    fc = ee.FeatureCollection(asset_id).filterBounds(geom)
                    collections.append(fc)
                elif asset_type == "FOLDER":
                    # IndexedFolder — load sub-assets
                    sub_result = ee.data.listAssets({"parent": asset_id})
                    for sub in sub_result.get("assets", []):
                        if sub.get("type") in ("TABLE", "FEATURE_COLLECTION"):
                            sub_fc = ee.FeatureCollection(sub["name"]).filterBounds(geom)
                            collections.append(sub_fc)
            except Exception:
                pass

    if not collections:
        return ee.FeatureCollection([])

    merged = collections[0]
    for fc in collections[1:]:
        merged = merged.merge(fc)
    return merged


# ---------------------------------------------------------------------------
#  Protected areas
# ---------------------------------------------------------------------------
def getProtectedAreas(area, iucn_cat=None, desig_type=None):
    """Return WDPA protected area polygons that intersect ``area``.

    Properties include ``NAME``, ``DESIG_ENG``, ``IUCN_CAT``, ``STATUS``,
    ``STATUS_YR``, ``GOV_TYPE``, ``DESIG_TYPE``, ``REP_AREA``, ``GIS_AREA``,
    ``ISO3``.

    Args:
        area: ee.FeatureCollection, ee.Feature, or ee.Geometry.
        iucn_cat (str, optional): Filter by IUCN category (e.g.
            ``"II"`` for National Parks, ``"Ia"`` for Strict Nature Reserve).
        desig_type (str, optional): Filter by designation type
            (``"National"``, ``"Regional"``, ``"International"``,
            ``"Not Applicable"``).

    Returns:
        ee.FeatureCollection.
    """
    fc = _filter_bounds(_WDPA, area)
    if iucn_cat is not None:
        fc = fc.filter(ee.Filter.eq("IUCN_CAT", iucn_cat))
    if desig_type is not None:
        fc = fc.filter(ee.Filter.eq("DESIG_TYPE", desig_type))
    return fc


# ---------------------------------------------------------------------------
#  Convenience: all available summary area types
# ---------------------------------------------------------------------------
AVAILABLE_SUMMARY_AREAS = {
    "admin_boundaries": {
        "function": "getAdminBoundaries",
        "description": "Admin boundaries: level 0 (countries), 1 (states), 2 (counties), 3 (sub-districts), 4 (localities). Sources: geob, gaul, gaul2024, fieldmaps.",
    },
    "us_states": {
        "function": "getUSStates",
        "description": "US state boundaries (TIGER 2018)",
    },
    "us_counties": {
        "function": "getUSCounties",
        "description": "US county boundaries with names (TIGER 2024)",
    },
    "us_urban_areas": {
        "function": "getUSUrbanAreas",
        "description": "US urban area boundaries (TIGER 2024)",
    },
    "us_census_blocks": {
        "function": "getUSCensusBlocks",
        "description": "US census blocks (TIGER 2020)",
    },
    "us_block_groups": {
        "function": "getUSBlockGroups",
        "description": "US census block groups (TIGER 2020)",
    },
    "us_census_tracts": {
        "function": "getUSCensusTracts",
        "description": "US census tracts (TIGER 2020)",
    },
    "usfs_forests": {
        "function": "getUSFSForests",
        "description": "USFS National Forest boundaries",
    },
    "usfs_districts": {
        "function": "getUSFSDistricts",
        "description": "USFS Ranger District boundaries",
    },
    "usfs_regions": {
        "function": "getUSFSRegions",
        "description": "USFS region boundaries (dissolved from forests)",
    },
    "roads": {
        "function": "getRoads",
        "description": "TIGER 2016 road features",
    },
    "buildings": {
        "function": "getBuildings",
        "description": "Building footprints (VIDA, MS, or Google)",
    },
    "protected_areas": {
        "function": "getProtectedAreas",
        "description": "WDPA protected area polygons",
    },
}
