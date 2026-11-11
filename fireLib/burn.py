"""A fire's perimeter, and what it changed: the two-date burn comparison.

The everyday fire questions ("map the Monroe Canyon fire", "make a
before/after change map of it", "how severe was it") all start the same
way: find the official perimeter and the fire's dates, then compare a
composite from before the fire with one from after it. This module does
both in one call each, so the common path is three lines::

    fire = fl.burn_change("Monroe Canyon", year=2025)
    for name in ("pre", "post", "dnbr", "severity"):
        Map.addLayer(fire[name], fire["viz"][name], fire["names"][name])
    Map.addLayer(fire["perimeter"], fire["viz"]["perimeter"], fire["names"]["perimeter"])

**The perimeter** comes from the National Interagency Fire Center
(:mod:`georest.nifc.perimeters`): WFIGS for fires since 2016, with
discovery and containment dates, and the InterAgency history before
that. It is the official interagency perimeter, not a buffer or a
sketch.

**The comparison** is a median composite of Sentinel-2 (from 2017) and
Landsat over a window before discovery, and one over a window after the
fire ended, each as surface reflectance on a 0-10000 scale. The window
after a fire that ended in winter at a snowy latitude would compare
summer with snow, so it moves to the next year's same season as the
pre-fire window (one year on, the way MTBS's extended assessment does).

**dNBR and severity are derived here, not official.** dNBR is
``(NBR_pre - NBR_post) * 1000``; the classes use Key and Benson's
thresholds (100 / 270 / 440 / 660). MTBS publishes official severity
for large fires, a year or more after they burn. Say which one a map
shows.

Copyright 2026 Ian Housman and the geeViz contributors.
Licensed under the Apache License, Version 2.0.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any

import ee

#: Key and Benson (2006) dNBR thresholds, scaled by 1000.
SEVERITY_CLASSES = (
    (1, "Low", 100, 270, "ffff73"),
    (2, "Moderate-low", 270, 440, "ffaa00"),
    (3, "Moderate-high", 440, 660, "e60000"),
    (4, "High", 660, None, "730000"),
)
#: Sentinel-2 surface reflectance starts in March 2017.
_S2_FIRST = _dt.date(2017, 4, 1)
_BANDS = ["blue", "green", "red", "nir", "swir1", "swir2"]


def fire_perimeter(name: str, year: int | None = None, state: str | None = None,
                   min_acres: float = 0, max_offset_m: float | None = 10) -> dict:
    """A fire's official perimeter and facts, ready for Earth Engine.

    Args:
        name (str): The fire's name, such as ``"Cameron Peak"``.
        year (int, optional): The year it was discovered.
        state (str, optional): Where it started, ``"CO"`` or ``"Colorado"``.
            Names repeat ("Dixie" is a California and an Idaho fire in
            2021); give year and state when you know them.
        min_acres (float, optional): Ignore fires smaller than this.
        max_offset_m (float, optional): Generalize the outline by up to
            this many meters (default 10; None for exact).

    Returns:
        dict: ``perimeter`` (``ee.FeatureCollection`` of the one fire),
        ``info`` (name, year, state, acres, discovered, contained,
        fire_out, source, source_url...), ``candidates`` (other fires of
        that name, largest first) and ``geojson`` (the perimeter as
        GeoJSON).

    Raises:
        LookupError: NIFC has no fire of that name (and year / state).
    """
    from georest.nifc import perimeters

    fc = perimeters.fire_perimeter(name, year=year, state=state, min_acres=min_acres,
                                   max_offset_m=max_offset_m)
    feature = fc["features"][0]
    info = dict(feature["properties"])
    props = {k: v for k, v in info.items() if v is not None and k != "object_id"}
    perimeter = ee.FeatureCollection([ee.Feature(ee.Geometry(feature["geometry"]), props)])
    return {"perimeter": perimeter, "info": info, "candidates": fc["candidates"], "geojson": fc}


def _day(d) -> _dt.date:
    return d if isinstance(d, _dt.date) else _dt.date.fromisoformat(str(d)[:10])


def _center_lat(geojson: dict) -> float | None:
    """The middle latitude of a GeoJSON perimeter's bounds, computed locally."""
    lats: list[float] = []

    def walk(c):
        if isinstance(c, (list, tuple)) and c and isinstance(c[0], (int, float)):
            lats.append(float(c[1]))
        elif isinstance(c, (list, tuple)):
            for x in c:
                walk(x)
    for f in geojson.get("features") or []:
        walk((f.get("geometry") or {}).get("coordinates"))
    return (min(lats) + max(lats)) / 2 if lats else None


def _shift_year(d: _dt.date) -> _dt.date:
    try:
        return d.replace(year=d.year + 1)
    except ValueError:                      # Feb 29
        return d.replace(year=d.year + 1, day=28)


def burn_windows(discovered, ended=None, composite_days: int = 60, lat: float | None = None,
                 today: _dt.date | None = None) -> dict:
    """The pre- and post-fire windows for a fire's dates.

    Pre: the ``composite_days`` before discovery. Post: the
    ``composite_days`` after the fire ended (containment, else fire-out,
    else 30 days after discovery). When most of that post window falls
    from November to March poleward of 37 degrees it would be compared
    with snow (the 2021 Dixie Fire, contained in late October), so the
    post window becomes the pre window one year on instead.

    Returns:
        dict: ``startDatePre``, ``endDatePre``, ``startDatePost``,
        ``endDatePost`` (ISO dates) and ``post_rule`` (why the post window
        is where it is).

    Raises:
        ValueError: The post window has not begun yet.
    """
    today = today or _dt.date.today()
    disc = _day(discovered)
    end = _day(ended) if ended else disc + _dt.timedelta(days=30)
    end_pre = disc - _dt.timedelta(days=1)
    start_pre = end_pre - _dt.timedelta(days=composite_days)
    start_post = end + _dt.timedelta(days=1)
    end_post = start_post + _dt.timedelta(days=composite_days)
    span = [start_post + _dt.timedelta(days=i) for i in range((end_post - start_post).days + 1)]
    wintry = sum(d.month in (11, 12, 1, 2, 3) for d in span) > len(span) / 2
    if wintry and lat is not None and abs(lat) >= 37:
        start_post = _shift_year(start_pre)
        end_post = _shift_year(end_pre)
        rule = ("most of the weeks after the fire fall in winter, so the post window is the pre "
                "window one year on (same season, no snow)")
    else:
        rule = f"the {composite_days} days after the fire ended" + ("" if ended else
               " (no containment date, so 30 days after discovery)")
    if start_post > today:
        raise ValueError(f"no post-fire imagery yet: the post window starts {start_post.isoformat()}")
    end_post = min(end_post, today)
    return {"startDatePre": start_pre.isoformat(), "endDatePre": end_pre.isoformat(),
            "startDatePost": start_post.isoformat(), "endDatePost": end_post.isoformat(),
            "post_rule": rule}


def _composite(area, start: str, end: str, include_landsat: bool):
    """Median of Sentinel-2 (from 2017) and Landsat scenes, 0-10000 SR."""
    from geeViz import getImagesLib as gil

    s, e = _day(start), _day(end)
    cols = []
    if e >= _S2_FIRST:
        cols.append(gil.superSimpleGetS2(area, max(s, _S2_FIRST).isoformat(), end, toaOrSR="SR")
                    .select(_BANDS).map(lambda i: ee.Image(i.toFloat().copyProperties(i, ["system:time_start"]))))
    if include_landsat or not cols:
        # It prints a line per processing step. Do NOT silence it with
        # contextlib.redirect_stdout: that swaps the process-wide
        # sys.stdout, and two runs doing it at once in one server left
        # stdout pointing at a dead buffer, so every later run_code in that
        # server returned no output at all.
        ls = gil.getProcessedLandsatScenes(area, s.year, e.year, 1, 365, toaOrSR="SR")
        cols.append(ls.filterDate(start, (e + _dt.timedelta(days=1)).isoformat()).select(_BANDS).map(
            lambda i: ee.Image(i.multiply(10000).toFloat().copyProperties(i, ["system:time_start"]))))
    col = cols[0]
    for c in cols[1:]:
        col = col.merge(c)
    img = col.median()
    return img.addBands(img.normalizedDifference(["nir", "swir2"]).rename("NBR"))


def severity_classes(dnbr: ee.Image) -> ee.Image:
    """dNBR (x1000) as Key and Benson classes 1-4, unburned masked, with
    class properties so ``autoViz`` colors and labels it."""
    sev = ee.Image(0)
    for value, _name, lo, hi, _color in SEVERITY_CLASSES:
        cond = dnbr.gte(lo) if hi is None else dnbr.gte(lo).And(dnbr.lt(hi))
        sev = sev.where(cond, value)
    sev = sev.selfMask().toByte().rename("Severity")
    return sev.set({
        "Severity_class_values": [c[0] for c in SEVERITY_CLASSES],
        "Severity_class_names": [c[1] for c in SEVERITY_CLASSES],
        "Severity_class_palette": [c[4] for c in SEVERITY_CLASSES],
    })


def burn_change(fire: str | None = None, year: int | None = None, state: str | None = None,
                area: Any = None, startDatePre: str | None = None, endDatePre: str | None = None,
                startDatePost: str | None = None, endDatePost: str | None = None,
                composite_days: int = 60, buffer_m: float = 2000, include_landsat: bool = True,
                clip: bool = True) -> dict:
    """A fire's two-date change: pre and post composites, dNBR and severity.

    **Use for any before/after, change or burn severity map of a fire.**
    Give the fire's name (and year) and everything else is found: the
    official NIFC perimeter, its discovery and containment dates, and the
    windows on either side (see :func:`burn_windows`). Or give ``area``
    and the four dates for a fire NIFC does not have.

    Args:
        fire (str, optional): The fire's name, such as ``"Monroe Canyon"``.
        year (int, optional): The year it was discovered.
        state (str, optional): Where it started, ``"UT"``.
        area (ee.Geometry | ee.Feature | ee.FeatureCollection, optional):
            Instead of ``fire``: the area to compare. Needs all four dates.
        startDatePre, endDatePre, startDatePost, endDatePost (str, optional):
            Override the windows (``YYYY-MM-DD``).
        composite_days (int, optional): Window length. Default 60.
        buffer_m (float, optional): Composite this far around the
            perimeter, so the map shows unburned ground for contrast.
            Default 2000.
        include_landsat (bool, optional): Merge Landsat with Sentinel-2 to
            fill cloud gaps. Before 2017 Landsat is used alone. Default True.
        clip (bool, optional): Clip ``dnbr`` and ``severity`` to the
            perimeter. Default True.

    Returns:
        dict:
            ``pre``, ``post``: composites (0-10000 SR, with an ``NBR`` band).
            ``dnbr``: (NBR_pre - NBR_post) * 1000. ``severity``: classes 1-4.
            ``perimeter``: the fire (``ee.FeatureCollection``), or None.
            ``area``: what was composited.
            ``info``: the fire's facts (name, year, state, acres,
            discovered, contained, source...), or None.
            ``candidates``: other fires of that name.
            ``dates``: the four window dates and ``post_rule``.
            ``viz`` and ``names``: map settings and layer names for each
            of pre, post, dnbr, severity and perimeter.
            ``notes``: one sentence on sources and what is derived.

    Example:
        >>> fire = fl.burn_change("Monroe Canyon", year=2025)
        >>> for k in ("pre", "post", "dnbr", "severity", "perimeter"):
        ...     Map.addLayer(fire[k], fire["viz"][k], fire["names"][k])
        >>> Map.centerObject(fire["perimeter"])
    """
    info, candidates, perimeter = None, [], None
    given = (startDatePre, endDatePre, startDatePost, endDatePost)
    if fire:
        p = fire_perimeter(fire, year=year, state=state)
        info, candidates, perimeter = p["info"], p["candidates"], p["perimeter"]
        if not info.get("discovered") and not all(given):
            raise ValueError(
                f"NIFC's record of {info['name']} ({info['source']}) has no dates; "
                "pass startDatePre, endDatePre, startDatePost and endDatePost")
        dates = (burn_windows(info["discovered"], info.get("contained") or info.get("fire_out"),
                              composite_days, _center_lat(p["geojson"]))
                 if info.get("discovered") else {})
        geom = perimeter.geometry()
        area = geom.bounds(1).buffer(buffer_m, 1).bounds(1)
    elif area is not None:
        if not all(given):
            raise ValueError("with area, give startDatePre, endDatePre, startDatePost and endDatePost")
        dates, geom = {}, None
        area = ee.FeatureCollection(area).geometry() if isinstance(area, ee.FeatureCollection) else ee.Geometry(
            area.geometry() if isinstance(area, ee.Feature) else area)
    else:
        raise ValueError("give a fire name, or an area and the four dates")
    for k, v in zip(("startDatePre", "endDatePre", "startDatePost", "endDatePost"), given):
        if v:
            dates[k] = v
    if given != (None, None, None, None):
        dates["post_rule"] = "dates given"

    pre = _composite(area, dates["startDatePre"], dates["endDatePre"], include_landsat)
    post = _composite(area, dates["startDatePost"], dates["endDatePost"], include_landsat)
    dnbr = pre.select("NBR").subtract(post.select("NBR")).multiply(1000).rename("dNBR")
    severity = severity_classes(dnbr)
    if clip and geom is not None:
        dnbr, severity = dnbr.clip(geom), severity.clip(geom)

    label = f"{info['name']} {info['year']}" if info else "Area"
    pre_d = f"{dates['startDatePre']} to {dates['endDatePre']}"
    post_d = f"{dates['startDatePost']} to {dates['endDatePost']}"
    from geeViz import getImagesLib as gil
    viz = {
        "pre": dict(gil.vizParamsFalse10k), "post": dict(gil.vizParamsFalse10k),
        "dnbr": {"min": -100, "max": 800, "palette": ["1a9641", "a6d96a", "ffffbf", "fdae61", "d7191c", "7a0000"]},
        "severity": {"autoViz": True, "canAreaChart": True},
        "perimeter": {"strokeColor": "000000", "fillColor": "00000000", "strokeWeight": 2,
                      "layerType": "geeVector"},
    }
    names = {"pre": f"{label} pre-fire ({pre_d})", "post": f"{label} post-fire ({post_d})",
             "dnbr": f"{label} dNBR (derived)", "severity": f"{label} burn severity (derived from dNBR)",
             "perimeter": f"{label} perimeter ({info['source']})" if info else "Perimeter"}
    notes = ((f"Perimeter and dates from {info['source']}. " if info else "")
             + "Composites are Sentinel-2" + (" and Landsat" if include_landsat else "")
             + " surface reflectance medians; dNBR and the severity classes (Key and Benson "
             "thresholds) are derived here, not MTBS's official severity.")
    return {"pre": pre, "post": post, "dnbr": dnbr, "severity": severity, "perimeter": perimeter,
            "area": area, "info": info, "candidates": candidates, "dates": dates, "viz": viz,
            "names": names, "notes": notes}
