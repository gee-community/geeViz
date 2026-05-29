# Esri Integration Design for geeViz

**Status:** Implemented  
**Module:** `geeViz/esriLib.py`  
**Date:** 2026-05-22

---

## Architecture Overview

`esriLib` is a standalone module mirroring the style of `geeViz/googleMapsLib.py`.
It bridges three Esri service types into the existing geeViz viewer via the two
layer mechanisms the viewer already supports:

| Esri service type | Bridge mechanism |
|---|---|
| Image Service | `Map.addTileLayer("<url>/tile/{z}/{y}/{x}")` |
| Map Service (cached) | `Map.addTileLayer(...)` — same tile path |
| Feature Service (≤ max_features) | Fetch `<url>/0/query?f=geojson` → `Map.addLayer(geojson_dict)` |
| Feature Service (> max_features) | `ValueError` with remediation message |

No JavaScript viewer changes required. The viewer already handles both
`tileMapService` and `geoJSONVector` layer types.

---

## Key Design Decisions

### 1. Feature Service overflow → ValueError (not silent truncation)

When a Feature Service count exceeds `max_features`, we raise `ValueError` with
a concrete remediation message:

```
ValueError: Feature service has 4,231 features (max_features=1000).
Increase max_features OR pass a `where` clause to filter,
e.g. where="STATE_FIPS='06'", OR set chunk_size= to paginate.
```

Rationale: silent truncation would produce partial-data analysis results with
no warning. Users who hit the limit can either raise the cap, filter server-side
with a `where` clause, or add a `chunk_size` paginator (future extension).

### 2. Portal search → generic ArcGIS Portal endpoint

`/sharing/rest/search` is a **standard ArcGIS Portal REST endpoint** present on:
- ArcGIS Online (`https://www.arcgis.com`)
- IIPP (`https://imagery.geoplatform.gov/iipp`)
- Any agency Portal (USFS, USGS, NOAA, custom Enterprise installs)

The `searchPortal` function is fully portal-agnostic. `portal=` accepts either
a full URL or a short name from the module-level `PORTALS` dict.

`PORTALS` curates the most commonly-used public portals for geospatial work:

```python
PORTALS = {
    "iipp":  "https://imagery.geoplatform.gov/iipp",
    "agol":  "https://www.arcgis.com",
    "usgs":  "https://www.sciencebase.gov/sciencebase",
    "noaa":  "https://coastalatlas.noaa.gov",
    "usfs":  "https://data.fs.usda.gov/geodata",
    "nasa":  "https://nasa.maps.arcgis.com",
}
```

Users can add custom portals at runtime:
```python
from geeViz.esriLib import PORTALS
PORTALS["myagency"] = "https://gis.myagency.gov/portal"
```

### 3. data_only filter bundling

The IIPP search UI applies a large exclusion list
(`-type:"Style" -type:"Layer" -type:"Map Document"...`) that filters non-data
items (templates, styles, packages). This is bundled into the `data_only=True`
default so users get data items by default. Power users can set
`data_only=False` and/or pass `raw_q=` to bypass it entirely.

### 4. Token support

Most public portals are token-free. Secured portals require a token obtained via:

```
POST <portal_url>/sharing/rest/generateToken
  username=...&password=...&client=requestip&expiration=60&f=json
```

Every helper accepts an optional `token=` kwarg forwarded as `?token=<>`.
Tokens are never required — omit for public services.

---

## Public API

```python
import geeViz.esriLib as el

# Portal discovery
results = el.searchPortal("naip 2023")                        # IIPP default
results = el.searchPortal("naip 2023", portal="agol")         # AGOL
results = el.searchPortal("naip 2023", portal="https://...")  # custom

# Service metadata
meta = el.getServiceMetadata("https://...FeatureServer/0")

# Add to map (auto-dispatches by service type)
el.addEsriService(result_or_url)

# Or explicitly:
el.addEsriImageService("https://.../ImageServer")
el.addEsriFeatureService("https://.../FeatureServer", max_features=2000,
                          where="STATE='UT'")
el.addEsriMapService("https://.../MapServer")
```

---

## Pitfalls

- **ArcGIS tile order is {z}/{y}/{x}**, not {z}/{x}/{y}. The tile URL builder
  emits the correct order automatically.
- **Feature count check**: always hits `returnCountOnly=true` before fetching
  geometry to avoid downloading thousands of features then failing.
- **SR/projection**: all Feature Service queries request `outSR=4326` so the
  returned GeoJSON is in WGS84 and Leaflet/the viewer can render it natively.
- **CORS**: public ArcGIS REST endpoints (AGOL, IIPP) send permissive CORS
  headers. Enterprise installs behind a firewall may require a backend proxy.
- **Token expiry**: ArcGIS tokens are short-lived (default 60 min). For
  long-running notebooks, generate fresh tokens before each session.
- **Pagination**: the current implementation enforces `max_features` hard cap.
  Paginated chunked fetch via `resultOffset`/`resultRecordCount` is a future
  extension (wire it up by setting `chunk_size=`).
