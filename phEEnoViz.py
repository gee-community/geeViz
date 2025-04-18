"""
Visualize the spectral seasonality of an area to facilitate composting methods development

geeViz.phEEnoViz facilitates the creation of plots to show the seasonality of an area. This is a good tool for deciding what date ranges to use for compositing.
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
# Script to help visualize variability of observations across space and time
# Intended to work within the geeViz package
######################################################################
import geeViz.getImagesLib as getImagesLib
import os, json, pdb, glob, math, threading, time, datetime
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from datetime import date

ee = getImagesLib.ee
Map = getImagesLib.Map
Map.clearMap()


###############################################################
def check_dir(dir):
    """
    Ensures that a directory exists, creating it if necessary.

    Args:
        dir (str): The directory path.

    Example:
        >>> check_dir('/tmp/mydir')
    """
    # Create the directory if it does not exist
    if not os.path.exists(dir):
        os.makedirs(dir)


###############################################################
def limitThreads(limit):
    """
    Limits the number of active threads to a specified limit.

    Args:
        limit (int): The maximum number of threads allowed.

    Example:
        >>> limitThreads(2)
    """
    # Wait until the number of active threads is below the limit
    while threading.activeCount() > limit:
        time.sleep(1)
        print(threading.activeCount(), "threads running")


###############################################################
# Function to extract a json table of zonal stats from an image
def getTableWrapper(
    image,
    fc,
    outputName,
    reducer=ee.Reducer.first(),
    scale=30,
    crs="EPSG:4326",
    transform=None,
    tryNumber=1,
    maxTries=15,
):
    """
    Extracts a JSON table of zonal statistics from an image and exports it.

    Args:
        image (ee.Image): The image to reduce.
        fc (ee.FeatureCollection): The feature collection for zonal stats.
        outputName (str): Output filename for the JSON table.
        reducer (ee.Reducer, optional): Reducer to use. Defaults to ee.Reducer.first().
        scale (int, optional): Scale in meters. Defaults to 30.
        crs (str, optional): Coordinate reference system. Defaults to "EPSG:4326".
        transform (optional): Transform parameter. Defaults to None.
        tryNumber (int, optional): Current try number. Defaults to 1.
        maxTries (int, optional): Maximum number of tries. Defaults to 15.

    Example:
        >>> getTableWrapper(image, fc, 'output.json')
    """
    # Run reduceRegions to get zonal statistics for each feature in the collection
    table = image.reduceRegions(fc, reducer, scale, crs, transform, 4)
    try:
        print("Exporting table:", outputName)
        t = table.getInfo()
        # Write the result to a JSON file
        o = open(outputName, "w")
        o.write(json.dumps(t))
        o.close()
        # Convert the JSON to CSV(s) for easier analysis
        convert_to_csv(outputName)
    except Exception as e:
        print("Error encountered:", e)
        # Retry if not at maxTries and not a fatal error
        tryNumber += 1
        if tryNumber < maxTries and e.args[0].find(" Parameter 'image' is required") == -1:
            print("Trying to convert table again. Try number:", tryNumber)
            getTableWrapper(
                image,
                fc,
                outputName,
                reducer,
                scale,
                crs,
                transform,
                tryNumber,
                maxTries,
            )


###############################################################
# Wrapper to get a sample of locations for a given area
def getTimeSeriesSample(
    startYear,
    endYear,
    startJulian,
    endJulian,
    compositePeriod,
    exportBands,
    studyArea,
    nSamples,
    output_table_name,
    showGEEViz,
    maskSnow=False,
    programs=["Landsat", "Sentinel2"],
):
    """
    Samples locations for a given area and exports time series data.

    Args:
        startYear (int): Start year.
        endYear (int): End year.
        startJulian (int): Start Julian day.
        endJulian (int): End Julian day.
        compositePeriod (int): Composite period in days.
        exportBands (list): List of bands to export.
        studyArea (ee.Geometry or ee.FeatureCollection): Study area.
        nSamples (int): Number of samples.
        output_table_name (str): Output table name.
        showGEEViz (bool): Whether to show GEEViz visualization.
        maskSnow (bool, optional): Whether to mask snow. Defaults to False.
        programs (list, optional): List of programs. Defaults to ["Landsat", "Sentinel2"].

    Example:
        >>> getTimeSeriesSample(2019, 2020, 1, 365, 16, ['NDVI'], studyArea, 100, 'output.json', True)
    """
    check_dir(os.path.dirname(output_table_name))
    # Load precomputed cloud and shadow statistics for masking
    preComputedCloudScoreOffset = getImagesLib.getPrecomputedCloudScoreOffsets(10)
    preComputedLandsatCloudScoreOffset = preComputedCloudScoreOffset["landsat"]
    preComputedSentinel2CloudScoreOffset = preComputedCloudScoreOffset["sentinel2"]

    preComputedTDOMStats = getImagesLib.getPrecomputedTDOMStats()
    preComputedLandsatTDOMIRMean = preComputedTDOMStats["landsat"]["mean"]
    preComputedLandsatTDOMIRStdDev = preComputedTDOMStats["landsat"]["stdDev"]
    preComputedSentinel2TDOMIRMean = preComputedTDOMStats["sentinel2"]["mean"]
    preComputedSentinel2TDOMIRStdDev = preComputedTDOMStats["sentinel2"]["stdDev"]

    #####################################################################################
    # Get the bounding box of the study area
    try:
        saBounds = studyArea.geometry().bounds()
    except:
        saBounds = studyArea.bounds()

    # Generate random sample points within the study area
    randomSample = ee.FeatureCollection.randomPoints(studyArea, nSamples, 0, 50)
    Map.addLayer(randomSample, {"layerType": "geeVector"}, "Samples", True)

    dummyImage = None

    # Loop over each year and export time series for each sample
    for yr in range(startYear, endYear + 1):
        output_table_nameT = "{}_{}_{}_{}-{}_{}_{}{}".format(
            os.path.splitext(output_table_name)[0],
            "-".join(programs),
            yr,
            startJulian,
            endJulian,
            compositePeriod,
            nSamples,
            os.path.splitext(output_table_name)[1],
        )
        if not os.path.exists(output_table_nameT):
            # Select imagery source(s) and get processed images
            if "Landsat" in programs and "Sentinel2" in programs:
                if dummyImage == None:
                    dummyImage = ee.Image(getImagesLib.getProcessedLandsatAndSentinel2Scenes(saBounds, 2019, 2020, 1, 365).first())

                images = getImagesLib.getProcessedLandsatAndSentinel2Scenes(
                    saBounds,
                    yr,
                    yr,
                    startJulian,
                    endJulian,
                    toaOrSR="TOA",
                    includeSLCOffL7=True,
                )
            elif "Sentinel2" in programs:
                if dummyImage == None:
                    dummyImage = ee.Image(getImagesLib.getProcessedSentinel2Scenes(saBounds, 2019, 2020, 1, 365).first())
                images = getImagesLib.getProcessedSentinel2Scenes(saBounds, yr, yr, startJulian, endJulian)
            elif "Landsat" in programs:
                if dummyImage == None:
                    dummyImage = ee.Image(getImagesLib.getProcessedLandsatScenes(saBounds, 2019, 2020, 1, 365).first())
                images = getImagesLib.getProcessedLandsatScenes(
                    saBounds,
                    yr,
                    yr,
                    startJulian,
                    endJulian,
                    toaOrSR="TOA",
                    includeSLCOffL7=True,
                )
            # Fill empty collections with a dummy image to avoid errors
            images = getImagesLib.fillEmptyCollections(images, dummyImage)

            # Optionally mask snow pixels
            if maskSnow:
                print("Masking snow")
                images = images.map(getImagesLib.sentinel2SnowMask)

            # Add vegetation indices or other band calculations
            images = images.map(getImagesLib.HoCalcAlgorithm2)

            # Convert to n-day composites for temporal smoothing
            composites = getImagesLib.nDayComposites(images, yr, yr, 1, 365, compositePeriod)

            # Stack composites into a single multi-band image
            stack = composites.select(exportBands).toBands()

            # Rename bands to use yyyy_mm_dd format
            bns = stack.bandNames()
            bns = bns.map(lambda bn: ee.String(bn).split("_").slice(1, None).join("_"))
            stack = stack.rename(bns)

            # Start export in a new thread to allow parallel processing
            tt = threading.Thread(target=getTableWrapper, args=(stack, randomSample, output_table_nameT))
            tt.start()
            time.sleep(0.1)

    # Set thread limit depending on whether visualization is shown
    threadLimit = 1
    if showGEEViz:
        # Visualize the study area and samples in geeViz
        Map.addLayer(studyArea, {"strokeColor": "00F"}, "Study Area")
        Map.centerObject(studyArea)
        Map.view()
        threadLimit = 2
    limitThreads(threadLimit)


###############################################################
# Function to convert json gee table into csvs
# Assumes id format is bandName_yyyy-dd-mm
def convert_to_csv(output_table_name):
    """
    Converts a JSON GEE table into CSV files, one per band.

    Args:
        output_table_name (str): Path to the JSON table.

    Example:
        >>> convert_to_csv('output.json')
    """
    with open(output_table_name) as jf:
        table = json.load(jf)

    # Parse the JSON to extract all bands and dates present in the table
    bands = []
    dates = []
    print("Finding dates and bands in json:", output_table_name)
    for feature in table["features"][:1]:
        props = feature["properties"]
        for prop in list(props.keys()):
            value = props[prop]
            band = prop.split("_")[-1]
            if band not in bands:
                bands.append(band)

            date = prop.split("_")[0]
            if date not in dates:
                dates.append(date)

    # For each band, create a CSV with dates as columns and samples as rows
    for band in bands:
        output_csv = os.path.splitext(output_table_name)[0] + "_{}.csv".format(band)
        out_table = "{}\n".format(",".join(dates))
        if not os.path.exists(output_csv):
            print("Parsing:", band)

            # For each feature (sample), extract values for this band across all dates
            for feature in table["features"]:
                id = feature["id"]
                values = []
                props = feature["properties"]
                prop_keys = list(props.keys())
                prop_keys = [i for i in prop_keys if i.split("_")[-1] == band]

                for prop in prop_keys:
                    value = str(props[prop])
                    if value == "None":
                        value = ""
                    values.append(value)
                out_line = "{}\n".format(",".join(values))
                out_table += out_line

            # Write the CSV file
            o = open(output_csv, "w")
            o.write(out_table)
            o.close()


###############################################################
# Function to take a set of csv tables with yyyy-mm-dd dates on the header row and values of a band/index from an
# area for each row (some sort of zonal stat or point location value). Null values are expected to be blank entries in the csv.
# It produces a time series chart of the histogram for each date in the given table
def chartTimeSeriesDistributions(
    tables,
    output_dir,
    output_base_name,
    n_bins=40,
    min_pctl=0.05,
    max_pctl=99.95,
    background_color="#D6D1CA",
    font_color="#1B1716",
    overwrite=False,
    howManyHarmonics=3,
    showChart=False,
    annotate_harmonic_peaks=True,
):
    """
    Plots time series histograms for each date in the given tables.

    Args:
        tables (list): List of CSV file paths.
        output_dir (str): Output directory for charts.
        output_base_name (str): Base name for output charts.
        n_bins (int, optional): Number of histogram bins. Defaults to 40.
        min_pctl (float, optional): Minimum percentile for value clipping. Defaults to 0.05.
        max_pctl (float, optional): Maximum percentile for value clipping. Defaults to 99.95.
        background_color (str, optional): Background color for plots. Defaults to "#D6D1CA".
        font_color (str, optional): Font color for plots. Defaults to "#1B1716".
        overwrite (bool, optional): Overwrite existing charts. Defaults to False.
        howManyHarmonics (int, optional): Number of harmonics for regression. Defaults to 3.
        showChart (bool, optional): Show chart interactively. Defaults to False.
        annotate_harmonic_peaks (bool, optional): Annotate harmonic peaks. Defaults to True.

    Example:
        >>> chartTimeSeriesDistributions(['table_NDVI.csv'], './charts', 'study_NDVI')
    """
    # Ensure output directory exists
    check_dir(output_dir)

    # Identify all bands present in the input tables
    bands = []
    for table in tables:
        band = os.path.splitext(os.path.basename(table))[0].split("_")[-1]
        if band not in bands:
            bands.append(band)
    for band in bands:
        output_chart_name = os.path.join(output_dir, output_base_name + "_" + band + ".png")
        if not os.path.exists(output_chart_name) or overwrite:
            title = " ".join(output_base_name.split("_")) + " " + band + " Distrubution Time Series"
            tablesT = [table for table in tables if os.path.basename(table).find(band) > -1]
            # Find the name of the band/index
            index_name = band

            print("Creating time series distribution chart for:", band)
            values = []
            # Concatenate all CSVs for this band
            data = pd.concat([pd.read_csv(t) for t in tablesT], axis=1)
            columns = data.columns
            values = data.to_numpy()

            # Flatten all values to compute percentiles for clipping
            flat = values.flatten()
            flat = flat[~(np.isnan(flat))]
            min = np.percentile(flat, min_pctl)  # Lower bound for histogram
            max = np.percentile(flat, max_pctl)  # Upper bound for histogram
            min_2 = np.percentile(flat, 10)      # For annotation
            max_2 = np.percentile(flat, 90)
            values = values.clip(min, max)
            # Extract dates from column names (assumed format: yyyy-mm-dd_band)
            dates = [i.split("_")[0] for i in columns]
            years = np.unique([i.split("-")[0] for i in dates])
            print("years", years)

            # Set up bins for histogram
            bin_step = (max - min) / n_bins
            bins = np.arange(min, max + bin_step, bin_step)

            # Compute histograms for each date (column)
            hist = np.array([np.histogram(data[column], bins=bins, density=True)[0] for column in columns]).transpose()
            hist = np.nan_to_num(hist, nan=0)
            hist = hist.clip(np.percentile(hist, 10), np.percentile(hist, 99))

            # Harmonic regression fitting to model seasonality
            table_xs = np.array([])
            table_ys = np.array([])
            table_all_xs = np.array([])
            d0 = date(1969, 12, 31)
            percentiles = []
            # For each date, compute decimal year and percentiles
            for i, column in enumerate(columns):
                d = dates[i]
                d1 = date(int(d.split("-")[0]), int(d.split("-")[1]), int(d.split("-")[2]))
                delta = d1 - d0
                delta_fraction = math.modf(delta.days / 365.25)[0]
                decimal_date = int(d.split("-")[0]) + delta_fraction

                ys = values[:, i]
                ys = ys[~(np.isnan(ys))]
                if len(ys) > 3:
                    percentiles.append(np.percentile(ys, [0, 5, 25, 50, 75, 95, 100]))
                else:
                    percentiles.append([np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan])
                xs = np.repeat(decimal_date, len(ys))
                table_ys = np.append(table_ys, ys)
                table_xs = np.append(table_xs, xs)
                table_all_xs = np.append(table_all_xs, decimal_date)
            percentiles = np.array(percentiles)

            table_all_xs = np.array(table_all_xs).flatten()
            table_xs = np.array(table_xs).flatten()
            table_ys = np.array(table_ys).flatten()

            # Fit harmonic regression models (1, 2, or 3 harmonics)
            peak_year_i = 2
            if peak_year_i > len(years) - 1:
                peak_year_i = 0
            xs = np.array([table_xs]).T
            sin1Term = np.sin(xs * 2 * math.pi)
            cos1Term = np.cos(xs * 2 * math.pi)
            sin2Term = np.sin(xs * 4 * math.pi)
            cos2Term = np.cos(xs * 4 * math.pi)
            sin3Term = np.sin(xs * 6 * math.pi)
            cos3Term = np.cos(xs * 6 * math.pi)
            intTerm = np.ones(xs.shape[0])
            harm_1 = np.c_[sin1Term, cos1Term, xs, intTerm]
            harm_1_2 = np.c_[sin1Term, cos1Term, sin2Term, cos2Term, xs, intTerm]
            harm_1_2_3 = np.c_[sin1Term, cos1Term, sin2Term, cos2Term, sin3Term, cos3Term, xs, intTerm]

            harm_1_model = np.linalg.lstsq(harm_1, table_ys, rcond=None)
            harm_1_2_model = np.linalg.lstsq(harm_1_2, table_ys, rcond=None)
            harm_1_2_3_model = np.linalg.lstsq(harm_1_2_3, table_ys, rcond=None)

            # Find the phase (peak) of the first harmonic
            peak_1_fraction = math.atan(harm_1_model[0][0] / harm_1_model[0][1]) / (2 * math.pi)
            peak_2_fraction = peak_1_fraction + 0.5
            if peak_1_fraction < 0:
                peak_1_fraction = 1 + peak_1_fraction
            if peak_2_fraction > 1:
                peak_2_fraction = peak_2_fraction - 1

            peak_1_yr = int(years[peak_year_i]) + peak_1_fraction
            peak_2_yr = int(years[peak_year_i]) + peak_2_fraction
            peak_1_pred = np.dot(
                [
                    np.sin(peak_1_yr * 2 * math.pi),
                    np.cos(peak_1_yr * 2 * math.pi),
                    peak_1_yr,
                    1,
                ],
                harm_1_model[0],
            )
            peak_2_pred = np.dot(
                [
                    np.sin(peak_2_yr * 2 * math.pi),
                    np.cos(peak_2_yr * 2 * math.pi),
                    peak_2_yr,
                    1,
                ],
                harm_1_model[0],
            )
            peak_1_y = min_2
            peak_2_y = max_2
            if peak_1_pred > peak_2_pred:
                peak_1_y = max_2
                peak_2_y = min_2

            # Convert peak fractions to day-of-year and then to month-day
            peak_date = int(peak_1_fraction * 365) + 1
            peak_date2 = int(peak_2_fraction * 365) + 1

            print(
                peak_date,
                peak_date2,
                peak_1_pred,
                peak_2_pred,
                years[peak_year_i][2:] + f"{peak_date:03}",
                years[peak_year_i][2:] + f"{peak_date2:03}",
            )
            peak_date = datetime.datetime.strptime(years[peak_year_i][2:] + f"{peak_date:03}", "%y%j").strftime("%m-%d")
            peak_date2 = datetime.datetime.strptime(years[peak_year_i][2:] + f"{peak_date2:03}", "%y%j").strftime("%m-%d")

            # Apply harmonic model to all dates for plotting
            xs = np.array([table_all_xs]).T
            sin1Term = np.sin(xs * 2 * math.pi)
            cos1Term = np.cos(xs * 2 * math.pi)
            sin2Term = np.sin(xs * 4 * math.pi)
            cos2Term = np.cos(xs * 4 * math.pi)
            sin3Term = np.sin(xs * 6 * math.pi)
            cos3Term = np.cos(xs * 6 * math.pi)
            intTerm = np.ones(xs.shape[0])
            harm_1 = np.c_[sin1Term, cos1Term, xs, intTerm]
            harm_1_2 = np.c_[sin1Term, cos1Term, sin2Term, cos2Term, xs, intTerm]
            harm_1_2_3 = np.c_[sin1Term, cos1Term, sin2Term, cos2Term, sin3Term, cos3Term, xs, intTerm]
            pred_1 = np.dot(harm_1, harm_1_model[0])
            pred_1_2 = np.dot(harm_1_2, harm_1_2_model[0])
            pred_1_2_3 = np.dot(harm_1_2_3, harm_1_2_3_model[0])

            pred_dict = {"1": pred_1, "2": pred_1_2, "3": pred_1_2_3}
            pred = pred_dict[str(howManyHarmonics)]

            # Plotting
            xTickFreq = 8  # Frequency of x-axis ticks
            yTickFreq = (max - min) / 10  # Frequency of y-axis ticks
            width = (len(columns) / 25) + 2
            if width < 8:
                width = 12
                xTickFreq = 3
            fig, ax = plt.subplots(figsize=(width, 7), frameon=True, facecolor="w")
            fig.patch.set_facecolor(background_color)

            params = {
                "ytick.color": font_color,
                "xtick.color": font_color,
                "axes.labelcolor": font_color,
                "axes.edgecolor": font_color,
                "legend.fontsize": 7,
                "legend.handlelength": 1.2,
            }
            plt.rcParams.update(params)

            ax.set_title(title)

            cmap = plt.get_cmap("viridis")
            hist = hist[:, :-1]

            # Plot the histogram as a color mesh
            cf = plt.pcolormesh(dates, bins, hist, cmap=cmap)
            degrees = 45
            plt.xticks(rotation=degrees, fontsize=7, ha="right")

            # Overlay the harmonic regression fit
            harm_line = plt.plot(
                dates,
                pred,
                linestyle="-",
                color=background_color,
                linewidth=2,
                label="Harmonic Fit ({})".format(howManyHarmonics),
            )

            ax.set_ylim([min, max])
            ax.set_ylabel("{} Value".format(index_name), fontsize=10)
            ax.set_xlabel("Date", fontsize=10)

            # Set up the x and y axis tick frequencies
            ax.xaxis.set_major_locator(plt.MultipleLocator(xTickFreq))
            ax.xaxis.set_minor_locator(plt.MultipleLocator(1))
            ax.yaxis.set_major_locator(plt.MultipleLocator(yTickFreq))
            ax.yaxis.set_minor_locator(plt.MultipleLocator(1))

            ax.grid(True, which="major", axis="y", linestyle="--", color=font_color)
            ax.grid(True, which="major", axis="x", linestyle="--", color=font_color)

            cbax = fig.add_axes([0.93, 0.11, 0.01, 0.71])
            legend = plt.legend(handles=harm_line, bbox_to_anchor=(-2.5, 1.08), loc="upper left")

            cb = plt.colorbar(cf, cax=cbax, orientation="vertical")
            cb.ax.tick_params(labelsize=10)
            cb.set_label(
                "Percent of Samples (%)",
                rotation=270,
                labelpad=15,
                fontsize=10,
                color=font_color,
            )

            # Clip predicted peaks to plotting range
            if peak_1_pred > max:
                peak_1_pred = max
            elif peak_1_pred < min:
                peak_1_pred = min
            if peak_2_pred > max:
                peak_2_pred = max
            elif peak_2_pred < min:
                peak_2_pred = min
            if annotate_harmonic_peaks:
                print("Annotating peak dates of harmonics")
                try:
                    # Annotate the first and second harmonic peaks on the plot
                    yr_dates = [i for i in dates if i.split("-")[0] == years[peak_year_i]]
                    m_dates = [i for i in yr_dates if i.split("-")[1] == peak_date.split("-")[0]]
                    if len(m_dates) == 0:
                        m_dates = [i for i in yr_dates if int(i.split("-")[1]) == int(peak_date.split("-")[0]) - 1]
                        print(m_dates)
                    m_dates = m_dates[0]
                    ax.annotate(
                        "{} ({})".format(peak_date, round(peak_1_pred, 3)),
                        xy=(m_dates, peak_1_pred),
                        xycoords="data",
                        color=background_color,
                        fontsize="10",
                        path_effects=[pe.withStroke(linewidth=2.5, foreground=font_color)],
                    )
                    yr_dates = [i for i in dates if i.split("-")[0] == years[peak_year_i]]
                    m_dates = [i for i in yr_dates if i.split("-")[1] == peak_date2.split("-")[0]][0]
                    ax.annotate(
                        "{} ({})".format(peak_date2, round(peak_2_pred, 3)),
                        xy=(m_dates, peak_2_pred),
                        xycoords="data",
                        color=background_color,
                        fontsize="10",
                        path_effects=[pe.withStroke(linewidth=2.5, foreground=font_color)],
                    )
                except Exception as e:
                    print(e)
            fig.savefig(output_chart_name)
            if showChart:
                plt.show()
            plt.close()
        else:
            print("Already produced:", output_chart_name)
