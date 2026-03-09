"""
Zonal Summary & Charting Library for GEE

geeViz.chartingLib provides a Python pipeline for running zonal statistics on
ee.Image / ee.ImageCollection objects and producing Plotly charts (time series,
bar, sankey). It mirrors the logic in the geeView JS frontend so that both human users and AI
agents have a clean, efficient API for this common workflow.
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

# --------------------------------------------------------------------------
#  Zonal summary + charting pipeline (ported from area-charting.js)
# --------------------------------------------------------------------------

import math
import ee
import pandas
import plotly.graph_objects as go
from geeViz.gee2Pandas import robust_featureCollection_to_df


###########################################################################
#                              Constants
###########################################################################

SPLIT_STR = "----"
SANKEY_TRANSITION_SEP = "0990"

DEFAULT_PLOT_BGCOLOR = "#d6d1ca"
DEFAULT_PLOT_FONT = "Roboto"
DEFAULT_CHART_WIDTH = 575
DEFAULT_CHART_HEIGHT = 350

AREA_FORMAT_DICT = {
    "Percentage": {"mult": None, "label": "% Area", "places": 2, "scale": 30},
    "Hectares": {"mult": 0.09, "label": "ha", "places": 0, "scale": 30},
    "Acres": {"mult": 0.222395, "label": "Acres", "places": 0, "scale": 30},
    "Pixels": {"mult": 1.0, "label": "Pixels", "places": 0, "scale": 30},
}


###########################################################################
#                          Private helpers
###########################################################################


def _ensure_hex_color(color):
    """Prepend '#' if missing from a hex color string."""
    if color is None:
        return None
    color = str(color)
    if not color.startswith("#"):
        color = "#" + color
    return color


def _interpolate_palette(palette, n):
    """Interpolate a color palette to *n* colors (continuous ramp).

    Given a list of hex color stops, linearly interpolate between them to
    produce exactly *n* evenly-spaced colors.  Matches the JS min/max/palette
    ramp behaviour for ordinal-thematic bar charts.
    """
    if not palette or n <= 0:
        return []
    palette = [_ensure_hex_color(c) for c in palette]
    if n == 1:
        return [palette[0]]
    if len(palette) >= n:
        # Down-sample evenly
        return [palette[round(i * (len(palette) - 1) / (n - 1))] for i in range(n)]

    out = []
    for i in range(n):
        t = i / (n - 1)  # 0 … 1
        pos = t * (len(palette) - 1)
        lo = int(math.floor(pos))
        hi = min(lo + 1, len(palette) - 1)
        frac = pos - lo
        c_lo = palette[lo].lstrip("#")
        c_hi = palette[hi].lstrip("#")
        # Expand 3-char hex to 6-char
        if len(c_lo) == 3:
            c_lo = "".join(ch * 2 for ch in c_lo)
        if len(c_hi) == 3:
            c_hi = "".join(ch * 2 for ch in c_hi)
        r = int(int(c_lo[0:2], 16) * (1 - frac) + int(c_hi[0:2], 16) * frac)
        g = int(int(c_lo[2:4], 16) * (1 - frac) + int(c_hi[2:4], 16) * frac)
        b = int(int(c_lo[4:6], 16) * (1 - frac) + int(c_hi[4:6], 16) * frac)
        out.append(f"#{r:02x}{g:02x}{b:02x}")
    return out


def _format_period(period):
    """Format a transition period list like [1985,1987] -> '1985-1987' or '1985' if equal."""
    if isinstance(period, (list, tuple)) and len(period) == 2:
        if period[0] == period[1]:
            return str(period[0])
        return f"{period[0]}-{period[1]}"
    return str(period)


def _expand_thematic_reduce_regions(df, band_names, class_info, area_format, scale, split_str):
    """Expand histogram dict columns from reduceRegions into class-name columns."""
    scale_mult = (scale / AREA_FORMAT_DICT["Hectares"]["scale"]) ** 2

    out_rows = []
    for _, row in df.iterrows():
        out_row = {}
        # preserve any non-histogram columns (e.g. label/id)
        for col in df.columns:
            if col not in band_names:
                out_row[col] = row[col]

        for bn in band_names:
            histogram = row.get(bn)
            if histogram is None or not isinstance(histogram, dict):
                continue

            # For stacked band names like "2020----Land_Cover", look up class_info
            # by the original band name (the part after the SPLIT_STR prefix).
            original_bn = bn.split(split_str, 1)[-1] if split_str in bn else bn
            info = class_info.get(original_bn, {})
            class_values = info.get("class_values", [])
            class_names = info.get("class_names", [])
            value_to_name = dict(zip([str(v) for v in class_values], class_names))

            pixel_total = sum(histogram.values()) or 1

            for str_val, count in histogram.items():
                name = value_to_name.get(str_val, str_val)
                col_name = f"{bn}{split_str}{name}" if len(band_names) > 1 else name
                if area_format == "Percentage":
                    out_row[col_name] = round((count / pixel_total) * 100, 2)
                elif area_format == "Pixels":
                    out_row[col_name] = count
                else:
                    mult = AREA_FORMAT_DICT[area_format]["mult"] * scale_mult
                    out_row[col_name] = round(count * mult, AREA_FORMAT_DICT[area_format]["places"])

        out_rows.append(out_row)

    return pandas.DataFrame(out_rows)


###########################################################################
#                       Data pipeline functions
###########################################################################


def get_obj_info(ee_obj, band_names=None):
    """
    Detect the type of a GEE object and read its thematic class metadata.

    Args:
        ee_obj (ee.Image or ee.ImageCollection): The GEE object to inspect.
        band_names (list, optional): Override the band names to use.

    Returns:
        dict: Keys ``obj_type``, ``band_names``, ``is_thematic``, ``class_info``, ``size``.
              ``class_info`` is ``{band_name: {class_values, class_names, class_palette}}``
    """
    obj_type = type(ee_obj).__name__

    if obj_type == "ImageCollection":
        first_img = ee.Image(ee_obj.first())
        size = ee_obj.size().getInfo()
    else:
        first_img = ee.Image(ee_obj)
        size = 1

    if band_names is None:
        band_names = first_img.bandNames().getInfo()

    # Read class metadata from image properties
    props = first_img.toDictionary().getInfo()
    class_info = {}
    is_thematic = False

    for bn in band_names:
        values_key = f"{bn}_class_values"
        names_key = f"{bn}_class_names"
        palette_key = f"{bn}_class_palette"

        if values_key in props and names_key in props:
            is_thematic = True
            class_info[bn] = {
                "class_values": props[values_key],
                "class_names": props[names_key],
                "class_palette": props.get(palette_key, []),
            }

    return {
        "obj_type": obj_type,
        "band_names": band_names,
        "is_thematic": is_thematic,
        "class_info": class_info,
        "size": size,
    }


def detect_geometry_type(geometry):
    """
    Determine whether the input geometry represents a single region or multiple.

    Args:
        geometry: An ``ee.Geometry``, ``ee.Feature``, or ``ee.FeatureCollection``.

    Returns:
        tuple: ``(geo_type, geometry)`` where geo_type is ``'single'`` or ``'multi'``,
               and geometry is an ``ee.Geometry`` (single) or ``ee.FeatureCollection`` (multi).
    """
    type_name = type(geometry).__name__

    if type_name == "Geometry":
        return ("single", geometry)

    if type_name == "Feature":
        return ("single", geometry.geometry())

    if type_name == "FeatureCollection":
        size = geometry.size().getInfo()
        if size <= 1:
            return ("single", geometry.geometry())
        return ("multi", geometry)

    # Fallback: try treating as geometry
    return ("single", ee.Geometry(geometry))


def prepare_for_reduction(ee_obj, obj_info, x_axis_property="system:time_start", date_format="YYYY"):
    """
    Prepare a GEE object for reduction by stacking an ImageCollection into a
    single multi-band image.

    Args:
        ee_obj: ``ee.Image`` or ``ee.ImageCollection``.
        obj_info (dict): Output of :func:`get_obj_info`.
        x_axis_property (str): Property name to use for x-axis labels.
        date_format (str): Earth Engine date format string (e.g. ``'YYYY'``).

    Returns:
        tuple: ``(stacked_image, stack_band_names, x_axis_labels)``
    """
    band_names = obj_info["band_names"]

    if obj_info["obj_type"] == "ImageCollection":
        ic = ee_obj

        # Tag images with x_axis_property if it's a date-derived field
        if x_axis_property in ("year", "date", "system:time_start"):
            ic = ic.map(lambda img: img.set("year", img.date().format(date_format)))
            if x_axis_property in ("date", "system:time_start"):
                x_axis_property = "year"

        # Get the x-axis labels
        x_axis_labels = ic.aggregate_histogram(x_axis_property).keys().getInfo()

        # Select only the bands we care about
        ic = ic.select(band_names)

        # Group by x_axis_property - if multiple images per label, mosaic them
        label_counts = ic.aggregate_histogram(x_axis_property).getInfo()
        needs_mosaic = any(v > 1 for v in label_counts.values())

        if needs_mosaic:
            print("Auto-mosaicking ImageCollection for x-axis labels...")
            def _mosaic_for_label(label):
                label = ee.String(label)
                filtered = ic.filter(ee.Filter.eq(x_axis_property, label))
                return filtered.mosaic().copyProperties(filtered.first()).set(x_axis_property, label)

            ic = ee.ImageCollection(ee.List(x_axis_labels).map(_mosaic_for_label))
        
        # Stack into single image with band names like "2020----forest"
        def _rename_bands(img):
            label = ee.String(img.get(x_axis_property))
            new_names = ee.List(band_names).map(
                lambda bn: label.cat(SPLIT_STR).cat(ee.String(bn))
            )
            return img.select(band_names).rename(new_names)

        # Pre-compute expected band names: "label----band" for each label × band
        expected_names = []
        for x_label in x_axis_labels:
            for bn in band_names:
                expected_names.append(f"{x_label}{SPLIT_STR}{bn}")

        ic = ic.map(_rename_bands)
        stacked = ic.toBands()

        # toBands() prefixes each band with the image's system:index + "_".
        # For programmatically-built collections (e.g. from the mosaic branch)
        # this is "0_", "1_", etc.  But for collections with original system:index
        # values (e.g. "LC09_038029_20230613") the prefix is unpredictable.
        # Instead of trying to strip the prefix, rename to the expected names
        # we already know.
        stacked = stacked.rename(expected_names)
        return (stacked, expected_names, x_axis_labels)

    else:
        # Single image - pass through
        return (ee.Image(ee_obj).select(band_names), band_names, [])


def reduce_region(image, geometry, reducer, scale=30, crs=None, transform=None, tile_scale=4):
    """
    Run ``image.reduceRegion`` with sensible defaults.

    If both ``scale`` and ``transform`` are provided, ``scale`` is set to None
    (transform takes precedence in GEE).

    Args:
        image (ee.Image): The image to reduce.
        geometry: An ``ee.Geometry`` or ``ee.Feature``.
        reducer (ee.Reducer): The reducer to apply.
        scale (int, optional): Pixel scale in meters. Defaults to 30.
        crs (str, optional): CRS string. Defaults to None.
        transform (list, optional): Affine transform. Defaults to None.
        tile_scale (int, optional): Tile scale for parallelism. Defaults to 4.

    Returns:
        dict: The reduction result dictionary.
    """
    if transform is not None and scale is not None:
        scale = None

    return image.reduceRegion(
        reducer=reducer,
        geometry=geometry,
        scale=scale,
        crs=crs,
        crsTransform=transform,
        bestEffort=True,
        maxPixels=1e13,
        tileScale=tile_scale,
    ).getInfo()


def reduce_regions(image, features, reducer, scale=30, crs=None, transform=None, tile_scale=4):
    """
    Run ``image.reduceRegions`` and return the result as a DataFrame.

    Args:
        image (ee.Image): The image to reduce.
        features (ee.FeatureCollection): The zones.
        reducer (ee.Reducer): The reducer to apply.
        scale (int, optional): Pixel scale in meters. Defaults to 30.
        crs (str, optional): CRS string. Defaults to None.
        transform (list, optional): Affine transform. Defaults to None.
        tile_scale (int, optional): Tile scale for parallelism. Defaults to 4.

    Returns:
        pandas.DataFrame: The reduction results.
    """
    if transform is not None and scale is not None:
        scale = None

    result = image.reduceRegions(
        collection=features,
        reducer=reducer,
        scale=scale,
        crs=crs,
        crsTransform=transform,
        tileScale=tile_scale,
    )
    return robust_featureCollection_to_df(result)


def parse_thematic_results(raw_dict, obj_info, x_axis_labels, area_format="Percentage", scale=30, split_str=SPLIT_STR):
    """
    Parse frequency histogram reduction results into a DataFrame with class names as columns.

    Args:
        raw_dict (dict): Output of :func:`reduce_region` using ``frequencyHistogram``.
        obj_info (dict): Output of :func:`get_obj_info`.
        x_axis_labels (list): Labels for the x-axis (e.g. years).
        area_format (str): One of ``'Percentage'``, ``'Hectares'``, ``'Acres'``, ``'Pixels'``.
        scale (int): Pixel scale used in reduction.
        split_str (str): Band name separator.

    Returns:
        pandas.DataFrame: Rows are x-axis labels (or a single row for Image),
                          columns are class names.
    """
    class_info = obj_info["class_info"]
    band_names = obj_info["band_names"]
    scale_mult = (scale / AREA_FORMAT_DICT["Hectares"]["scale"]) ** 2

    if x_axis_labels:
        # ImageCollection path - histogram keys are like "2020----Land_Cover"
        rows = []
        for x_label in x_axis_labels:
            row = {"x": x_label}
            for bn in band_names:
                key = f"{x_label}{split_str}{bn}"
                histogram = raw_dict.get(key, {})
                if histogram is None:
                    histogram = {}

                info = class_info.get(bn, {})
                class_values = info.get("class_values", [])
                class_names = info.get("class_names", [])
                value_to_name = dict(zip([str(v) for v in class_values], class_names))

                pixel_total = sum(histogram.values()) or 1

                for str_val, count in histogram.items():
                    name = value_to_name.get(str_val, str_val)
                    col_name = f"{bn}{split_str}{name}" if len(band_names) > 1 else name
                    if area_format == "Percentage":
                        row[col_name] = round((count / pixel_total) * 100, 2)
                    elif area_format == "Pixels":
                        row[col_name] = count
                    else:
                        mult = AREA_FORMAT_DICT[area_format]["mult"] * scale_mult
                        row[col_name] = round(count * mult, AREA_FORMAT_DICT[area_format]["places"])

            rows.append(row)

        df = pandas.DataFrame(rows).set_index("x")
        df.index.name = None
        df = df.fillna(0)
        return df

    else:
        # Single Image path - histogram keys are band names directly
        row = {}
        for bn in band_names:
            histogram = raw_dict.get(bn, {})
            if histogram is None:
                histogram = {}

            info = class_info.get(bn, {})
            class_values = info.get("class_values", [])
            class_names = info.get("class_names", [])
            value_to_name = dict(zip([str(v) for v in class_values], class_names))

            pixel_total = sum(histogram.values()) or 1

            for str_val, count in histogram.items():
                name = value_to_name.get(str_val, str_val)
                col_name = f"{bn}{split_str}{name}" if len(band_names) > 1 else name
                if area_format == "Percentage":
                    row[col_name] = round((count / pixel_total) * 100, 2)
                elif area_format == "Pixels":
                    row[col_name] = count
                else:
                    mult = AREA_FORMAT_DICT[area_format]["mult"] * scale_mult
                    row[col_name] = round(count * mult, AREA_FORMAT_DICT[area_format]["places"])

        df = pandas.DataFrame([row])
        df = df.fillna(0)
        return df


def parse_continuous_results(raw_dict, obj_info, x_axis_labels, split_str=SPLIT_STR):
    """
    Parse continuous (mean/median/etc.) reduction results into a DataFrame.

    Args:
        raw_dict (dict): Output of :func:`reduce_region`.
        obj_info (dict): Output of :func:`get_obj_info`.
        x_axis_labels (list): Labels for the x-axis.
        split_str (str): Band name separator.

    Returns:
        pandas.DataFrame: Rows are x-axis labels (or single row), columns are band names.
    """
    band_names = obj_info["band_names"]

    if x_axis_labels:
        rows = []
        for x_label in x_axis_labels:
            row = {"x": x_label}
            for bn in band_names:
                key = f"{x_label}{split_str}{bn}"
                row[bn] = raw_dict.get(key)
            rows.append(row)

        df = pandas.DataFrame(rows).set_index("x")
        df.index.name = None
        return df

    else:
        row = {bn: raw_dict.get(bn) for bn in band_names}
        return pandas.DataFrame([row])


def zonal_stats(
    ee_obj,
    geometry,
    band_names=None,
    reducer=None,
    scale=30,
    crs=None,
    transform=None,
    tile_scale=4,
    area_format="Percentage",
    x_axis_property="system:time_start",
    date_format="YYYY",
):
    """
    Compute zonal statistics for a GEE Image or ImageCollection over a geometry.

    This is the main entry point for the data pipeline. It auto-detects the
    object type, whether data is thematic or continuous, the appropriate reducer,
    and the geometry type.

    Args:
        ee_obj: ``ee.Image`` or ``ee.ImageCollection``.
        geometry: ``ee.Geometry``, ``ee.Feature``, or ``ee.FeatureCollection``.
        band_names (list, optional): Bands to include. Auto-detected if None.
        reducer (ee.Reducer, optional): Override the auto-selected reducer.
        scale (int): Pixel scale in meters. Defaults to 30.
        crs (str, optional): CRS string.
        transform (list, optional): Affine transform.
        tile_scale (int): Tile scale for parallelism. Defaults to 4.
        area_format (str): Area unit for thematic data. One of
            ``'Percentage'``, ``'Hectares'``, ``'Acres'``, ``'Pixels'``.
        x_axis_property (str): Property for x-axis labels (ImageCollection).
        date_format (str): Date format string for x-axis labels.

    Returns:
        pandas.DataFrame: The zonal statistics table.
    """
    ee_obj = ee_obj.filterBounds(geometry)

    obj_info = get_obj_info(ee_obj, band_names)
    geo_type, geo = detect_geometry_type(geometry)

    # Choose reducer
    if reducer is None:
        if obj_info["is_thematic"]:
            reducer = ee.Reducer.frequencyHistogram()
        else:
            reducer = ee.Reducer.mean()

    # Determine if using frequency histogram
    is_histogram = False
    try:
        reducer_type = reducer.getInfo()["type"]
        is_histogram = "frequencyHistogram" in reducer_type
    except Exception:
        pass

    # Prepare image
    stacked, stack_bands, x_axis_labels = prepare_for_reduction(
        ee_obj, obj_info, x_axis_property, date_format
    )

    if geo_type == "single":
        raw = reduce_region(stacked, geo, reducer, scale, crs, transform, tile_scale)

        if is_histogram:
            return parse_thematic_results(raw, obj_info, x_axis_labels, area_format, scale)
        else:
            return parse_continuous_results(raw, obj_info, x_axis_labels)

    else:
        # Multi-region: reduceRegions
        df = reduce_regions(stacked, geo, reducer, scale, crs, transform, tile_scale)

        if is_histogram:
            return _expand_thematic_reduce_regions(
                df, stack_bands, obj_info["class_info"], area_format, scale, SPLIT_STR
            )
        else:
            return df


def prepare_sankey_data(
    ee_collection,
    band_name,
    transition_periods,
    class_info,
    geometry,
    scale=30,
    crs=None,
    transform=None,
    tile_scale=4,
    area_format="Percentage",
    min_percentage=0.2,
):
    """
    Build a Sankey diagram dataset from class transitions across time periods.

    For each consecutive pair of periods, this function:
    1. Filters the collection to each period
    2. Computes the mode for each period
    3. Creates a transition image encoding ``{from}0990{to}``
    4. Runs ``frequencyHistogram`` to count transitions
    5. Parses results into both a source/target/value DataFrame and a
       transition matrix DataFrame

    Args:
        ee_collection (ee.ImageCollection): The input collection.
        band_name (str): The thematic band to analyze.
        transition_periods (list): List of ``[start_year, end_year]`` pairs.
        class_info (dict): Class info dict for the band (from :func:`get_obj_info`).
        geometry: ``ee.Geometry`` or ``ee.Feature``.
        scale (int): Pixel scale in meters.
        crs (str, optional): CRS string.
        transform (list, optional): Affine transform.
        tile_scale (int): Tile scale for parallelism.
        area_format (str): Area unit.
        min_percentage (float): Minimum percentage threshold for including a
            flow in the source-target table. The transition matrix always
            includes all observed transitions regardless of this threshold.

    Returns:
        tuple: ``(sankey_df, matrix_df)``

        - **sankey_df** (``pandas.DataFrame``): Source-target-value table with
          columns ``source``, ``target``, ``value``, ``source_name``,
          ``target_name``, ``source_color``, ``target_color``, ``period``.
          Flows below ``min_percentage`` are excluded.
        - **matrix_df** (``pandas.DataFrame``): Transition matrix where rows are
          "from" classes (labelled ``"{period} {class_name}"``), columns are
          "to" classes, and values are the converted counts. One block of rows
          per consecutive period pair, matching the JS CSV export format.
    """
    _, geo = detect_geometry_type(geometry)

    info = class_info.get(band_name, class_info.get(list(class_info.keys())[0], {}))
    class_values = info.get("class_values", [])
    class_names = info.get("class_names", [])
    class_palette = info.get("class_palette", [])

    value_to_idx = {v: i for i, v in enumerate(class_values)}
    idx_to_name = {i: n for i, n in enumerate(class_names)}
    idx_to_color = {i: _ensure_hex_color(c) for i, c in enumerate(class_palette)}
    num_classes = len(class_values)

    scale_mult = (scale / AREA_FORMAT_DICT["Hectares"]["scale"]) ** 2

    all_rows = []
    transition_band_names = []

    # Build transition images for each consecutive period pair
    transition_images = []
    period_labels = []

    for i in range(len(transition_periods) - 1):
        p1 = transition_periods[i]
        p2 = transition_periods[i + 1]

        p1_start, p1_end = (p1, p1) if not isinstance(p1, (list, tuple)) else (p1[0], p1[-1])
        p2_start, p2_end = (p2, p2) if not isinstance(p2, (list, tuple)) else (p2[0], p2[-1])

        # Filter and compute mode for each period
        filtered1 = ee_collection.filter(
            ee.Filter.calendarRange(int(p1_start), int(p1_end), "year")
        ).select([band_name])
        filtered2 = ee_collection.filter(
            ee.Filter.calendarRange(int(p2_start), int(p2_end), "year")
        ).select([band_name])

        mode1 = filtered1.mode().rename(["from"])
        mode2 = filtered2.mode().rename(["to"])

        # Encode transition: from_class * 10000 + 9900 + to_class
        combined = mode1.addBands(mode2)
        transition = (
            combined.select("from").multiply(10000)
            .add(9900)
            .add(combined.select("to"))
            .rename([f"{_format_period(p1)}---{_format_period(p2)}"])
        )

        transition_images.append(transition)
        transition_band_names.append(f"{_format_period(p1)}---{_format_period(p2)}")
        period_labels.append((_format_period(p1), _format_period(p2)))

    # Stack all transition images
    if len(transition_images) == 1:
        stacked = transition_images[0]
    else:
        stacked = transition_images[0]
        for t_img in transition_images[1:]:
            stacked = stacked.addBands(t_img)

    # Run frequency histogram
    raw = reduce_region(
        stacked.toInt(), geo, ee.Reducer.frequencyHistogram(), scale, crs, transform, tile_scale
    )

    # Parse results — build both the source-target table and the transition matrix
    matrix_rows = []

    for ti, t_bn in enumerate(transition_band_names):
        histogram = raw.get(t_bn, {})
        if histogram is None:
            histogram = {}

        pixel_total = sum(histogram.values()) or 1
        p1_label, p2_label = period_labels[ti]
        offset1 = ti * num_classes
        offset2 = (ti + 1) * num_classes

        # Build count_lookup: (from_idx, to_idx) -> display_val for ALL transitions
        count_lookup = {}
        for encoded_str, count in histogram.items():
            encoded = int(float(encoded_str))
            from_class = encoded // 10000
            to_class = encoded % 10000 - 9900

            from_idx = value_to_idx.get(from_class)
            to_idx = value_to_idx.get(to_class)
            if from_idx is None or to_idx is None:
                continue

            # Compute display value
            pct = (count / pixel_total) * 100
            if area_format == "Percentage":
                display_val = round(pct, 2)
            elif area_format == "Pixels":
                display_val = count
            else:
                mult = AREA_FORMAT_DICT[area_format]["mult"] * scale_mult
                display_val = round(count * mult, AREA_FORMAT_DICT[area_format]["places"])

            count_lookup[(from_idx, to_idx)] = display_val

            # Source-target table: only include flows above min_percentage
            if pct >= min_percentage:
                all_rows.append(
                    {
                        "source": from_idx + offset1,
                        "target": to_idx + offset2,
                        "value": display_val,
                        "source_name": f"{p1_label} {idx_to_name.get(from_idx, str(from_class))}",
                        "target_name": f"{p2_label} {idx_to_name.get(to_idx, str(to_class))}",
                        "source_color": idx_to_color.get(from_idx, "#888888"),
                        "target_color": idx_to_color.get(to_idx, "#888888"),
                        "period": f"{p1_label} -> {p2_label}",
                    }
                )

        # Build transition matrix rows for this period pair
        # Columns are "to" class labels, rows are "from" class labels
        for fi in range(num_classes):
            row_label = f"{idx_to_name.get(fi, str(fi))} {p1_label}"
            row_data = {"": row_label}
            for ti2 in range(num_classes):
                col_label = f"{idx_to_name.get(ti2, str(ti2))} {p2_label}"
                row_data[col_label] = count_lookup.get((fi, ti2), 0)
            matrix_rows.append(row_data)

    # Build sankey_df
    empty_cols = ["source", "target", "value", "source_name", "target_name", "source_color", "target_color", "period"]
    if not all_rows:
        sankey_df = pandas.DataFrame(columns=empty_cols)
    else:
        sankey_df = pandas.DataFrame(all_rows)

    # Build matrix_df
    if matrix_rows:
        matrix_df = pandas.DataFrame(matrix_rows).set_index("")
        matrix_df.index.name = None
    else:
        matrix_df = pandas.DataFrame()

    return (sankey_df, matrix_df)


###########################################################################
#                          Chart functions
###########################################################################


def chart_time_series(
    df,
    colors=None,
    chart_type="lines+markers",
    title="Time Series",
    x_label="Year",
    y_label=None,
    stacked=False,
    width=DEFAULT_CHART_WIDTH,
    height=DEFAULT_CHART_HEIGHT,
    label_max_length=30,
):
    """
    Create a Plotly time series chart from a zonal stats DataFrame.

    Args:
        df (pandas.DataFrame): Output of :func:`zonal_stats` for an ImageCollection.
            Index = x-axis labels, columns = data series.
        colors (list, optional): Hex color strings for each column.
        chart_type (str): ``'lines'``, ``'bar'``, or ``'lines+markers'``.
        title (str): Chart title.
        x_label (str): X-axis label.
        y_label (str, optional): Y-axis label.
        stacked (bool): Whether to stack the series.
        width (int): Chart width in pixels.
        height (int): Chart height in pixels.
        label_max_length (int): Max characters for legend labels.

    Returns:
        plotly.graph_objects.Figure
    """
    fig = go.Figure()

    x_values = list(df.index)
    # Convert pure-integer labels (e.g. years) to int so Plotly uses a
    # linear axis with automatic tick spacing instead of a categorical axis
    # that crams every label together.  Mirrors the JS parseInt() logic.
    try:
        x_values = [int(v) for v in x_values]
    except (ValueError, TypeError):
        pass
    columns = list(df.columns)

    for i, col in enumerate(columns):
        color = None
        if colors and i < len(colors):
            color = _ensure_hex_color(colors[i])

        label = col[:label_max_length]

        if chart_type == "bar":
            fig.add_trace(
                go.Bar(
                    x=x_values,
                    y=df[col].values,
                    name=label,
                    marker_color=color,
                )
            )
        else:
            mode = chart_type if chart_type in ("lines", "lines+markers") else "lines+markers"
            fig.add_trace(
                go.Scatter(
                    x=x_values,
                    y=df[col].values,
                    mode=mode,
                    name=label,
                    line=dict(color=color, width=1),
                    marker=dict(color=color, size=3),
                    stackgroup="one" if stacked else None,
                )
            )

    bar_mode = "stack" if stacked and chart_type == "bar" else ("group" if chart_type == "bar" else None)

    fig.update_layout(
        title=dict(text=title, x=0.5, xanchor="center"),
        xaxis=dict(
            title=x_label,
            tickangle=45,
            # If x-values are integers (years), use integer tick format and
            # let Plotly auto-space the ticks instead of showing every value.
            tickformat="d" if all(isinstance(v, int) for v in x_values) else None,
        ),
        yaxis=dict(
            title=y_label,
            automargin=True,
        ),
        plot_bgcolor=DEFAULT_PLOT_BGCOLOR,
        paper_bgcolor=DEFAULT_PLOT_BGCOLOR,
        font=dict(family=DEFAULT_PLOT_FONT),
        width=width,
        height=height,
        margin=dict(l=35, r=25, b=50, t=50, pad=5),
        barmode=bar_mode,
        hovermode="x unified",
    )

    return fig


def chart_bar(
    df,
    colors=None,
    title="Class Distribution",
    y_label=None,
    max_classes=30,
    width=DEFAULT_CHART_WIDTH,
    height=DEFAULT_CHART_HEIGHT,
):
    """
    Create a Plotly bar chart from a single-Image zonal stats DataFrame.

    Automatically chooses horizontal or vertical orientation based on label length.

    Args:
        df (pandas.DataFrame): Output of :func:`zonal_stats` for a single Image.
            Single row, columns = class names.
        colors (list, optional): Hex color strings for each bar.
        title (str): Chart title.
        y_label (str, optional): Value axis label.
        max_classes (int): Maximum number of classes to display.
        width (int): Chart width in pixels.
        height (int): Chart height in pixels.

    Returns:
        plotly.graph_objects.Figure
    """
    # Flatten to series
    if len(df) == 1:
        values = df.iloc[0]
    else:
        values = df.sum()

    labels = list(values.index)
    vals = list(values.values)

    # Cap at max_classes (keep top N by value)
    if len(labels) > max_classes:
        sorted_pairs = sorted(zip(vals, labels, range(len(labels))), reverse=True)
        sorted_pairs = sorted_pairs[:max_classes]
        sorted_pairs.sort(key=lambda x: x[2])  # restore original order
        vals = [p[0] for p in sorted_pairs]
        labels = [p[1] for p in sorted_pairs]
        # Also filter colors
        if colors:
            idxs = [p[2] for p in sorted_pairs]
            colors = [_ensure_hex_color(colors[i]) for i in idxs if i < len(colors)]

    if colors:
        if len(colors) < len(labels):
            # Interpolate palette as a continuous ramp (matches JS min/max/palette)
            colors = _interpolate_palette(colors, len(labels))
        else:
            colors = [_ensure_hex_color(c) for c in colors[:len(labels)]]

    # Determine orientation
    max_label_len = max((len(str(l)) for l in labels), default=0)
    orientation = "h" if max_label_len > max(len(labels), 6) else "v"

    fig = go.Figure()

    if orientation == "h":
        fig.add_trace(
            go.Bar(
                y=labels,
                x=vals,
                orientation="h",
                marker_color=colors,
            )
        )
        fig.update_layout(
            xaxis=dict(title=y_label, automargin=True),
            yaxis=dict(automargin=True),
            margin=dict(l=80, r=25, b=30, t=50, pad=5),
        )
    else:
        fig.add_trace(
            go.Bar(
                x=labels,
                y=vals,
                orientation="v",
                marker_color=colors,
            )
        )
        fig.update_layout(
            xaxis=dict(tickangle=45, automargin=True),
            yaxis=dict(title=y_label, automargin=True),
            margin=dict(l=35, r=25, b=80, t=50, pad=5),
        )

    fig.update_layout(
        title=dict(text=title, x=0.5, xanchor="center"),
        plot_bgcolor=DEFAULT_PLOT_BGCOLOR,
        paper_bgcolor=DEFAULT_PLOT_BGCOLOR,
        font=dict(family=DEFAULT_PLOT_FONT),
        width=width,
        height=height,
        hovermode="closest",
    )

    return fig


def chart_grouped_bar(
    df,
    colors=None,
    title="Zonal Summary by Feature",
    y_label=None,
    stacked=False,
    width=DEFAULT_CHART_WIDTH,
    height=DEFAULT_CHART_HEIGHT,
):
    """
    Create a grouped (or stacked) bar chart for multi-feature zonal stats.

    Each group on the x-axis is a feature (row) and each bar/segment within the
    group is a class (column). This is the natural chart type when
    ``reduceRegions`` returns one row per zone.

    Args:
        df (pandas.DataFrame): Rows = features (index used as labels),
            columns = class names, values = numeric area/percentage.
        colors (list, optional): Hex color strings, one per column (class).
        title (str): Chart title.
        y_label (str, optional): Y-axis label.
        stacked (bool): Stack bars instead of grouping. Defaults to False.
        width (int): Chart width in pixels.
        height (int): Chart height in pixels.

    Returns:
        plotly.graph_objects.Figure
    """
    fig = go.Figure()
    feature_labels = [str(v) for v in df.index]

    for i, col in enumerate(df.columns):
        color = None
        if colors and i < len(colors) and colors[i] is not None:
            color = _ensure_hex_color(colors[i])

        fig.add_trace(
            go.Bar(
                name=str(col),
                x=feature_labels,
                y=df[col].values,
                marker_color=color,
            )
        )

    fig.update_layout(
        barmode="stack" if stacked else "group",
        title=dict(text=title, x=0.5, xanchor="center"),
        xaxis=dict(title="Feature", tickangle=45, automargin=True),
        yaxis=dict(title=y_label or "", automargin=True),
        plot_bgcolor=DEFAULT_PLOT_BGCOLOR,
        paper_bgcolor=DEFAULT_PLOT_BGCOLOR,
        font=dict(family=DEFAULT_PLOT_FONT),
        width=width,
        height=height,
        margin=dict(l=35, r=25, b=80, t=50, pad=5),
        hovermode="x unified",
    )

    return fig


def chart_sankey(
    sankey_df,
    class_names,
    class_palette,
    transition_periods,
    title="Class Transitions",
    width=DEFAULT_CHART_WIDTH,
    height=DEFAULT_CHART_HEIGHT,
    node_thickness=35,
    node_pad=15,
):
    """
    Create a Plotly Sankey diagram from transition data.

    Args:
        sankey_df (pandas.DataFrame): Output of :func:`prepare_sankey_data`.
        class_names (list): List of class names.
        class_palette (list): List of hex color strings.
        transition_periods (list): The transition period list used to generate the data.
        title (str): Chart title.
        width (int): Chart width in pixels.
        height (int): Chart height in pixels.
        node_thickness (int): Sankey node bar thickness.
        node_pad (int): Padding between Sankey nodes.

    Returns:
        plotly.graph_objects.Figure
    """
    if sankey_df.empty:
        fig = go.Figure()
        fig.update_layout(title=title, annotations=[dict(text="No transitions found", showarrow=False)])
        return fig

    # Build node labels and colors for all period slots
    num_periods = len(transition_periods)
    num_classes = len(class_names)
    labels = []
    node_colors = []

    for p in transition_periods:
        p_label = _format_period(p)
        for i, name in enumerate(class_names):
            labels.append(f"{p_label} {name}")
            color = _ensure_hex_color(class_palette[i]) if i < len(class_palette) else "#888888"
            node_colors.append(color)

    # Build link colors (average of source and target)
    link_colors = []
    for _, row in sankey_df.iterrows():
        sc = row.get("source_color", "#888888")
        link_colors.append(sc.replace("#", "rgba(") if False else sc)  # use source color with alpha
        # Simple approach: use source color at reduced opacity
        hex_c = row.get("source_color", "#888888").lstrip("#")
        if len(hex_c) == 6:
            r, g, b = int(hex_c[:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
            link_colors[-1] = f"rgba({r},{g},{b},0.4)"

    fig = go.Figure(
        data=[
            go.Sankey(
                textfont=dict(size=10),
                orientation="h",
                node=dict(
                    pad=node_pad,
                    thickness=node_thickness,
                    line=dict(color="black", width=0.5),
                    label=labels,
                    color=node_colors,
                ),
                link=dict(
                    source=list(sankey_df["source"]),
                    target=list(sankey_df["target"]),
                    value=list(sankey_df["value"]),
                    color=link_colors,
                ),
            )
        ]
    )

    fig.update_layout(
        title=dict(text=title, x=0.5, xanchor="center"),
        font=dict(family=DEFAULT_PLOT_FONT, size=12),
        plot_bgcolor=DEFAULT_PLOT_BGCOLOR,
        paper_bgcolor=DEFAULT_PLOT_BGCOLOR,
        width=width,
        height=height,
        margin=dict(l=25, r=25, b=25, t=50, pad=0),
    )

    return fig


###########################################################################
#                        Convenience function
###########################################################################


def summarize_and_chart(
    ee_obj,
    geometry,
    band_names=None,
    reducer=None,
    scale=30,
    crs=None,
    transform=None,
    tile_scale=4,
    area_format="Percentage",
    x_axis_property="system:time_start",
    date_format="YYYY",
    title=None,
    chart_type="lines+markers",
    stacked=False,
    sankey=False,
    transition_periods=None,
    sankey_band_name=None,
    min_percentage=0.2,
    palette=None,
    feature_label=None,
    width=DEFAULT_CHART_WIDTH,
    height=DEFAULT_CHART_HEIGHT,
):
    """
    Run zonal statistics and produce a chart in one call.

    Orchestrates :func:`zonal_stats` (or :func:`prepare_sankey_data`) and the
    appropriate chart function. Auto-picks chart type: bar for a single Image,
    time series for an ImageCollection, Sankey if ``sankey=True``.

    When ``feature_label`` is provided and the geometry is an ``ee.FeatureCollection``
    with multiple features, the function uses ``reduceRegions`` to compute
    per-feature statistics and produces a grouped bar chart via
    :func:`chart_grouped_bar`. Each feature is labeled by the given property name.

    Args:
        ee_obj: ``ee.Image`` or ``ee.ImageCollection``.
        geometry: ``ee.Geometry``, ``ee.Feature``, or ``ee.FeatureCollection``.
        band_names (list, optional): Bands to include.
        reducer (ee.Reducer, optional): Override the auto-selected reducer.
        scale (int): Pixel scale in meters.
        crs (str, optional): CRS string.
        transform (list, optional): Affine transform.
        tile_scale (int): Tile scale for parallelism.
        area_format (str): Area unit for thematic data.
        x_axis_property (str): Property for x-axis labels.
        date_format (str): Date format string.
        title (str, optional): Chart title. Auto-generated if None.
        chart_type (str): ``'lines'``, ``'lines+markers'``, or ``'bar'``.
        stacked (bool): Whether to stack series. Defaults to False.
        sankey (bool): Whether to produce a Sankey diagram.
        transition_periods (list, optional): Period list for Sankey.
        sankey_band_name (str, optional): Band for Sankey analysis.
        min_percentage (float): Minimum percentage for Sankey flows.
        palette (list, optional): Hex color strings for each series/band.
            Overrides auto-detected class palette when provided.
        feature_label (str, optional): Property name to use as row labels when
            the geometry is a multi-feature ``ee.FeatureCollection``. Triggers
            the ``reduceRegions`` path and produces a grouped bar chart.
        width (int): Chart width in pixels.
        height (int): Chart height in pixels.

    Returns:
        tuple: For non-Sankey charts: ``(DataFrame, Figure)``.
               For Sankey charts: ``(sankey_df, Figure, matrix_df)`` where
               ``sankey_df`` is the source-target-value table and ``matrix_df``
               is the from-class x to-class transition matrix.
    """
    ee_obj = ee_obj.filterBounds(geometry)
    obj_info = get_obj_info(ee_obj, band_names)
    class_info = obj_info["class_info"]
    y_label = AREA_FORMAT_DICT.get(area_format, {}).get("label", area_format) if obj_info["is_thematic"] else None

    # Sankey path
    if sankey and obj_info["obj_type"] == "ImageCollection" and class_info:
        bn = sankey_band_name or obj_info["band_names"][0]
        if transition_periods is None:
            raise ValueError("transition_periods is required for Sankey charts")

        if title is None:
            title = f"{bn} Class Transitions"

        sankey_df, matrix_df = prepare_sankey_data(
            ee_obj,
            bn,
            transition_periods,
            class_info,
            geometry,
            scale=scale,
            crs=crs,
            transform=transform,
            tile_scale=tile_scale,
            area_format=area_format,
            min_percentage=min_percentage,
        )

        info = class_info.get(bn, {})
        fig = chart_sankey(
            sankey_df,
            class_names=info.get("class_names", []),
            class_palette=info.get("class_palette", []),
            transition_periods=transition_periods,
            title=title,
            width=width,
            height=height,
        )
        return (sankey_df, fig, matrix_df)

    # Multi-feature path: reduceRegions + grouped bar chart
    geo_type, _ = detect_geometry_type(geometry)
    if geo_type == "multi" and feature_label:
        df = zonal_stats(
            ee_obj,
            geometry,
            band_names=band_names,
            reducer=reducer,
            scale=scale,
            crs=crs,
            transform=transform,
            tile_scale=tile_scale,
            area_format=area_format,
            x_axis_property=x_axis_property,
            date_format=date_format,
        )

        # Set index to feature label column
        if feature_label in df.columns:
            df = df.set_index(feature_label)

        # Identify class columns from class_info
        class_cols = []
        if class_info:
            for bn in obj_info["band_names"]:
                info = class_info.get(bn, {})
                for name in info.get("class_names", []):
                    col_name = f"{bn}{SPLIT_STR}{name}" if len(obj_info["band_names"]) > 1 else name
                    if col_name in df.columns:
                        class_cols.append(col_name)

        # Fallback: keep numeric columns that aren't geometry/system properties
        if not class_cols:
            class_cols = [
                c for c in df.columns
                if pandas.api.types.is_numeric_dtype(df[c])
                and not c.startswith("geometry")
                and c not in ("system:index",)
            ]

        chart_df = df[class_cols].fillna(0)

        # Build colors
        colors = palette
        if colors is None and class_info:
            color_lookup = {}
            for bn in obj_info["band_names"]:
                info = class_info.get(bn, {})
                cn = info.get("class_names", [])
                cp = info.get("class_palette", [])
                for i, name in enumerate(cn):
                    col_name = f"{bn}{SPLIT_STR}{name}" if len(obj_info["band_names"]) > 1 else name
                    if i < len(cp):
                        color_lookup[col_name] = cp[i]
            if color_lookup:
                colors = [color_lookup.get(col) for col in chart_df.columns]

        if title is None:
            title = "Zonal Summary by Feature"

        fig = chart_grouped_bar(
            chart_df,
            colors=colors,
            title=title,
            y_label=y_label,
            stacked=stacked,
            width=width,
            height=height,
        )
        return (chart_df, fig)

    # Standard single-region zonal stats path
    df = zonal_stats(
        ee_obj,
        geometry,
        band_names=band_names,
        reducer=reducer,
        scale=scale,
        crs=crs,
        transform=transform,
        tile_scale=tile_scale,
        area_format=area_format,
        x_axis_property=x_axis_property,
        date_format=date_format,
    )

    # Extract colors from class info (unless caller provided palette).
    # Build the color list to match actual DataFrame column order so that
    # multi-band thematic charts (e.g. Change + Land_Cover + Land_Use)
    # assign the correct color to each class.
    colors = palette
    if colors is None and class_info:
        # Build a lookup: column_name -> hex color
        color_lookup = {}
        for bn in obj_info["band_names"]:
            info = class_info.get(bn, {})
            class_names = info.get("class_names", [])
            class_palette = info.get("class_palette", [])
            for i, name in enumerate(class_names):
                col_name = f"{bn}{SPLIT_STR}{name}" if len(obj_info["band_names"]) > 1 else name
                if i < len(class_palette):
                    color_lookup[col_name] = class_palette[i]
        # Map each DataFrame column to its color (fall back to None)
        if color_lookup:
            colors = [color_lookup.get(col) for col in df.columns]

    # Pick chart type
    if obj_info["obj_type"] == "ImageCollection":
        if title is None:
            title = "Zonal Summary"
        fig = chart_time_series(
            df,
            colors=colors,
            chart_type=chart_type,
            title=title,
            x_label=x_axis_property.replace("_", " ").title() if x_axis_property != "year" else "Year",
            y_label=y_label,
            stacked=stacked,
            width=width,
            height=height,
        )
    else:
        if title is None:
            title = "Class Distribution"
        fig = chart_bar(
            df,
            colors=colors,
            title=title,
            y_label=y_label,
            width=width,
            height=height,
        )

    return (df, fig)
