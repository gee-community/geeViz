---
name: fire
description: A named wildfire - its official perimeter, a before/after (two-date) change map, dNBR or burn severity. Load for any fire perimeter, burn scar, burn severity or post-fire change request.
---
# Fire: perimeter, two-date change, burn severity

`fl` (geeViz.fireLib) is already loaded in `run_code`. These calls find the
official NIFC perimeter and the fire's own dates for you. Do not search
EDW, ArcGIS Online or MTBS for a perimeter, and do not look these
functions up: their signatures are here.

## A change map, dNBR or severity map: one `run_code`, then `map_control`

```python
fire = fl.burn_change("Monroe Canyon", year=2025)   # add state="UT" when the name is common
for k in ("pre", "post", "dnbr", "severity", "perimeter"):
    Map.addLayer(fire[k], fire["viz"][k], fire["names"][k])
Map.centerObject(fire["perimeter"])
print(fire["info"]); print(fire["dates"]); print(fire["notes"])
print([(c["name"], c["state"], round(c["acres"] or 0)) for c in fire["candidates"]])
```

Then `map_control(action="export")`. That is the whole job.

- `fl.burn_change(fire=None, year=None, state=None, area=None, startDatePre=None, endDatePre=None, startDatePost=None, endDatePost=None, composite_days=60, buffer_m=2000, include_landsat=True, clip=True)`
- Returns `pre`, `post` (Sentinel-2 + Landsat SR medians, 0-10000, with an `NBR` band), `dnbr` ((NBR pre - NBR post) x 1000), `severity` (classes 1-4, Key and Benson thresholds, colored by autoViz), `perimeter`, `info` (name, year, state, acres, discovered, contained, source), `candidates`, `dates` (the four window dates and `post_rule`), `viz`, `names`, `notes`.
- Windows: the 60 days before discovery against the 60 days after containment. When those weeks are mostly winter at a snowy latitude, the post window is the same season one year later; `dates["post_rule"]` says which.
- Only one fire of the year shown for a common name: if `candidates` is not empty, say which fire you mapped (state, acres) and that others share the name.
- For a fire NIFC does not have, pass `area=` (a geometry) and all four dates.

Do not, unless the person asked:
- compute statistics (percentiles, acres per class, means): `map_control` already checks every layer renders;
- call `tl.auto_viz` on `dnbr` or the composites: `fire["viz"]` has the stretches;
- add more layers than the five above.

## Just the perimeter

```python
p = fl.fire_perimeter("Cameron Peak", year=2020)    # perimeter, info, candidates
Map.addLayer(p["perimeter"], {"strokeColor": "000000", "fillColor": "00000000", "layerType": "geeVector"}, "Cameron Peak perimeter")
```

## Acres, only when asked

One `run_code`, one grouped sum, inside the perimeter:

```python
acres = ee.Image.pixelArea().divide(4046.86).addBands(fire["severity"]).reduceRegion(
    ee.Reducer.sum().group(1, "class"), fire["perimeter"].geometry(), 30, maxPixels=1e10, tileScale=4).getInfo()
```

## Official severity (MTBS)

When the person asks for official severity: `USFS/GTAC/MTBS/annual_burn_severity_mosaics/v1`,
`.filter(ee.Filter.calendarRange(year, year, "year")).filterBounds(fire["perimeter"]).mosaic().select([0], ["Severity"])`
with `{"autoViz": True}`. MTBS lags a year or more, so a recent fire may not be in it: say so, and offer the derived severity.

## When NIFC has no such fire

`LookupError`: try without `year`, or with a shorter name. For large fires before 2016, MTBS boundaries
(`USFS/GTAC/MTBS/burned_area_boundaries/v1`, `Incid_Name` in capitals, `Ig_Date`) are the other official source.
Never draw a perimeter from memory or a buffer around a point; if nothing is found, say so.

## What to tell the person

The perimeter's source and the fire's dates (`fire["info"]`), the two windows compared (`fire["dates"]`),
and that dNBR and the severity classes are derived here, not MTBS's official severity (`fire["notes"]`).
