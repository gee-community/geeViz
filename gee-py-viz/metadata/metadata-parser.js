var gainLongDescription = 'Vegetative indices indicate a positive trend over time. Gain is categorized using one specific change process classification within the training data, described below.<br>\
						GROWTH/RECOVERY &#45 Land exhibiting an increase in vegetation cover due to growth and succession over one or more years. Applicable to any areas that may express spectral change associated with vegetation regrowth. In developed areas, growth can result from maturing vegetation and/or newly installed lawns and landscaping. In forests, growth includes vegetation growth from bare ground, as well as the over topping of intermediate and co-dominate trees and/or lower-lying grasses and shrubs. Growth/Recovery segments recorded following forest harvest will likely transition through different land cover classes as the forest regenerates. For these changes to be considered growth/recovery, spectral values should closely adhere to an increasing trend line (e.g. a positive slope that would, if extended to ~20 years, be on the order of .10 units of NDVI) which persists for several years.';
var lossLongDescription = 'Vegetative indices indicate a negative trend over time. Loss is not categorized explicitly. However, specific change process classifications are collected within the training data. The following describes the change processes collected within the training data. Any of them could be present and are collectively considered loss.<br>\
						FIRE &#45 Land altered by fire, regardless of the cause of the ignition (natural or anthropogenic), severity, or land use.<br>\
						HARVEST &#45 Forest land where trees, shrubs or other vegetation have been severed or removed by anthropogenic means. Examples include clearcutting, salvage logging after fire or insect outbreaks, thinning and other forest management prescriptions (e.g. shelterwood/seedtree harvest).<br>\
						MECHANICAL &#45 Non-forest land where trees, shrubs or other vegetation has been mechanically severed or removed by chaining, scraping, brush sawing, bulldozing, or any other methods of non-forest vegetation removal.<br>\
						STRUCTURAL DECLINE &#45 Land where trees or other woody vegetation is physically altered by unfavorable growing conditions brought on by non-anthropogenic or non-mechanical factors. This type of loss should generally create a trend in the spectral signal(s) (e.g. NDVI decreasing, Wetness decreasing; SWIR increasing; etc.) however the trend can be subtle. Structural decline occurs in woody vegetation environments, most likely from insects, disease, drought, acid rain, etc. Structural decline can include defoliation events that do not result in mortality such as in Gypsy moth and spruce budworm infestations which may recover within 1 or 2 years.<br>\
						SPECTRAL DECLINE &#45 A plot where the spectral signal shows a trend in one or more of the spectral bands or indices (e.g. NDVI decreasing, Wetness decreasing; SWIR increasing; etc.). Examples include cases where: a) non-forest/non-woody vegetation shows a trend suggestive of decline (e.g. NDVI decreasing, Wetness decreasing; SWIR increasing; etc.), or b) where woody vegetation shows a decline trend which is not related to the loss of woody vegetation, such as when mature tree canopies close resulting in increased shadowing, when species composition changes from conifer to hardwood, or when a dry period (as opposed to stronger, more acute drought) causes an apparent decline in vigor, but no loss of woody material or leaf area.<br>\
						WIND/ICE &#45 Land (regardless of use) where vegetation is altered by wind from hurricanes, tornados, storms and other severe weather events including freezing rain from ice storms.<br>\
						HYDROLOGY &#45 Land where flooding has significantly altered woody cover or other Land cover elements regardless of land use (e.g. new mixtures of gravel and vegetation in and around streambeds after a flood).<br>\
						DEBRIS &#45 Land (regardless of use) altered by natural material movement associated with landslides, avalanches, volcanos, debris flows, etc.<br>\
						OTHER &#45 Land (regardless of use) where the spectral trend or other supporting evidence suggests a disturbance or change event has occurred but the definitive cause cannot be determined or the type of change fails to meet any of the change process categories defined above.'
var lcLongDescription =  'BARREN &#45 Land comprised of bare soil exposed by disturbance (e.g., soil uncovered by mechanical clearing or forest harvest), as well as perennially barren areas such as deserts, playas, rock outcroppings (including minerals and other geologic materials exposed by surface mining activities), sand dunes, salt flats, and beaches. Roads made of dirt and gravel are also considered barren.<br>\
						GRASS/FORB/HERB &#45 Land covered by perennial grasses, forbs, or other forms of herbaceous vegetation.<br>\
						IMPERVIOUS &#45 Land covered with man-made materials that water cannot penetrate, such as paved roads, rooftops, and parking lots.<br>\
						SHRUB &#45 Land vegetated with shrubs.<br>\
						SNOW/ICE &#45 Land covered by snow and ice.<br>\
						TREE &#45 Land comprised of live or standing dead trees.<br>\
						WATER &#45 Land covered by water.';
var luLongDescription = 'AGRICULTURE &#45 Land used for the production of food, fiber and fuels which is in either a vegetated or non-vegetated state. This includes but is not limited to cultivated and uncultivated croplands, hay lands, orchards, vineyards, confined livestock operations, and areas planted for production of fruits, nuts or berries. Roads used primarily for agricultural use (i.e. not used for public transport from town to town) are considered agriculture land use.<br>\
						DEVELOPED&#45 Land covered by man-made structures (e.g. high density residential, commercial, industrial, mining or transportation), or a mixture of both vegetation (including trees) and structures (e.g., low density residential, lawns, recreational facilities, cemeteries, transportation and utility corridors, etc.), including any land functionally altered by human activity.<br>\
						FOREST &#45 Land that is planted or naturally vegetated and which contains (or is likely to contain) 10% or greater tree cover at some time during a near-term successional sequence. This may include deciduous, evergreen and/or mixed categories of natural forest, forest plantations, and woody wetlands.<br>\
						NON-FOREST WETLAND &#45 Lands adjacent to or within a visible water table (either permanently or seasonally saturated) dominated by shrubs or persistent emergents. These wetlands may be situated shoreward of lakes, river channels, or estuaries; on river floodplains; in isolated catchments; or on slopes. They may also occur as prairie potholes, drainage ditches and stock ponds in agricultural landscapes and may also appear as islands in the middle of lakes or rivers. Other examples also include marshes, bogs, swamps, quagmires, muskegs, sloughs, fens, and bayous.<br>\
						OTHER &#45 Lands which are perennially covered with snow and ice, water, salt flats and other undeclared classes. Glaciers and ice sheets or places where snow and ice obscure any other land cover call are<br>\
						included (assumed is the presence of permanent snow and ice). Water includes rivers, streams, canals, ponds, lakes, reservoirs, bays, or oceans. This assumes permanent water (which can be in some state of flux due to ephemeral changes brought on by climate or anthropogenic).<br>\
						RANGELAND/PASTURE &#45 This class includes any area that is either a.) Rangeland, where vegetation is a mix of native grasses, shrubs, forbs and grass-like plants largely arising from natural factors and processes such as rainfall, temperature, elevation and fire, although limited management may include prescribed burning as well as grazing by domestic and wild herbivores; or b.) Pasture, where vegetation may range from mixed, largely natural grasses, forbs and herbs to more managed vegetation dominated by grass species that have been seeded and managed to maintain near monoculture.'

metadata_parser_dict ={'STUDYAREA': [ 'BTNF', 'FNF' ],
'STUDYAREA_LONGNAME': {'BTNF':'Bridger-Teton National Forest','FNF': 'Flathead National Forest'},

'STUDYAREA_URL' :  'https://lcms-data-explorer-beta.appspot.com/',
'VERSION' : 'v2019.1',
'SUMMARYMETHOD' :{'year':'Most recent observation above specified threshold', 'prob':'Highest probability observation'},
'GAINORLOSS' :['Gain' , 'Loss'],
'LCORLU' : ['Cover' , 'Use'],


//(OOB_ACCURACY and OOB_KAPPA in html file)
'Gain_ACC':{'OOB_ACCURACY': 0.993, 'OOB_KAPPA':0.931,'THRESHOLD':0.35},
'Loss_ACC':{'OOB_ACCURACY': 0.985, 'OOB_KAPPA':0.752,'THRESHOLD':0.35},
'Landcover_ACC':{'OOB_ACCURACY': 0.984, 'OOB_KAPPA':0.978,'THRESHOLD':'NA'},
'Landuse_ACC':{'OOB_ACCURACY': 0.991, 'OOB_KAPPA':0.978,'THRESHOLD':'NA'},

'Gain Year_Description':['SUMMARY_METHOD (Threshold = LOWER_THRESHOLD). Each year has a modelled probability of gain using TimeSync model calibration data in a Random Forest model.<br>\
						The modelled probability is then thresholded.  SUMMARY_METHOD is then selected for the final map output.<br>\
						Classes:<br>0:No Data<br>All other values represent 4-digit year',gainLongDescription],
'Loss Year_Description':['SUMMARY_METHOD (Threshold = LOWER_THRESHOLD). Each year has a modelled probability of loss using TimeSync model calibration data in a Random Forest model.<br>\
						The modelled probability is then thresholded.  SUMMARY_METHOD is then selected for the final map output.<br>\
						Classes:<br>0:No Data<br>All other values represent 4-digit year',lossLongDescription],

'Gain Duration_Description':['SUMMARY_METHOD (Threshold = LOWER_THRESHOLD). Each year has a modelled probability of gain using TimeSync model calibration data in a Random Forest model.<br>\
						The modelled probability is then thresholded, and any observation above the specified threshold is counted toward duration.<br>\
						Classes:<br>0:No Data<br>All other values represent a count in years',gainLongDescription],
'Loss Duration_Description':['SUMMARY_METHOD (Threshold = LOWER_THRESHOLD). Each year has a modelled probability of loss using TimeSync model calibration data in a Random Forest model.<br>\
						The modelled probability is then thresholded, and any observation above the specified threshold is counted toward duration.<br>\
						Classes:<br>0:No Data<br>All other values represent a count in years',lossLongDescription],

'Gain Probability_Description':['SUMMARY_METHOD (Threshold = LOWER_THRESHOLD). Each year has a modelled probability of gain using TimeSync model calibration data in a Random Forest model.<br>\
						The modelled probability is then thresholded.  SUMMARY_METHOD is then selected for the final map output.<br>\
						Classes:<br>0:No Data<br>1 &#45 100: probability * 100 = raster value',gainLongDescription],
'Loss Probability_Description':['SUMMARY_METHOD (Threshold = LOWER_THRESHOLD). Each year has a modelled probability of gain using TimeSync model calibration data in a Random Forest model.<br>\
						The modelled probability is then thresholded.  SUMMARY_METHOD is then selected for the final map output.<br>\
						Classes:<br>0:No Data<br>1 &#45 100: probability * 100 = raster value',lossLongDescription],

'Landcover MODE_Description':['Each year has a modelled landcover class using TimeSync model calibration data in a Random Forest model.<br>\
						The MODE of the landcover classes across the years is then selected for the final map output.<br>\
						Classes:<br>0 &#45 No data<br>1 &#45 Barren<br>2 &#45 Grass/forb/herb<br>3 &#45 Impervious<br>4 &#45 Shrubs<br>5 &#45 Snow/ice<br>6 &#45 Trees<br>7 &#45 Water',lcLongDescription],
'Landuse MODE_Description':['Each year has a modelled landuse class using TimeSync model calibration data in a Random Forest model.<br>\
						The MODE of the landuse classes across the years is then selected for the final map output.<br>\
						Classes:<br>0 &#45 No data<br>1 &#45 Agriculture<br>2 &#45 Developed<br>3 &#45 Forest<br>4 &#45 Non-forest wetland<br>5 &#45 Other<br>6 &#45 Rangeland',luLongDescription],



//-Definitions and Descriptions
//(LCORLU_ONELINE_DEFINITION in html file)
'LANDCOVER_ONELINE_DEFINITION' : 'The vegetation, water, rock, or man-made constructions occurring on the earth’s surface. ',
'LANDUSE_ONELINE_DEFINITION' : 'The way in which land cover resources are used. ',

// //(CONFUSIONMATRIX in html file)
'Gain_CONFUSIONMATRIX':  '<table width = "300"><tr><th></th> <th>Reference</th>  </tr> <tr>  <td><b>Prediction</b></td> <td>  No Gain </td> <td>   Gain   </td> </tr>  <tr> <td>  No Gain   </td> <td>  71565   </td>  <td>    270   </td> </tr> <tr> <td>   Gain </td> <td>    296   </td>  <td>   4054   </td> </tr> </table>',
 

'Loss_CONFUSIONMATRIX' :'<table width = "300"><tr><th></th><th>Reference</th> </tr><tr> <td><b>Prediction</b></td> <td>   Loss   </td> <td>  No Loss </td> </tr><tr> <td>   Loss   </td><td>   1780   </td> <td>    500   </td></tr><tr><td>  No Loss </td><td>    628   </td> <td>   73277  </td></tr></table>',

'Landcover_CONFUSIONMATRIX':
'<table width = "500"><tr><th></th><th>Reference</th></tr><tr><td><b>Prediction</b></td><td>Barren</td><td>Grass/Forb/Herb</td><td>Impervious</td><td>Shrubs</td><td>Trees</td><td>Water</td></tr><tr><td>Barren</td><td>7282</td><td>66</td><td>0</td><td>12</td><td>22</td><td>10</td></tr><tr><td>Grass/Forb/Herb</td><td>144</td><td>19311</td><td>2</td>\
    <td>123</td><td>90</td><td>11</td></tr><tr><td>Impervious</td><td>0</td><td>0</td><td>178</td><td>0</td><td>0</td><td>0</td></tr><tr><td>Shrubs</td><td>29</td><td>154</td><td>0</td> <td>22771</td><td>76</td><td>7</td></tr><tr><td>Trees</td><td>102</td><td>194</td><td>0</td><td>180</td><td>24577</td><td>8</td></tr><tr><td>Water</td><td>0</td><td>1</td><td>0</td><td>1</td><td>3</td><td>831</td> </tr></table>',


'Landuse_CONFUSIONMATRIX':
'<table width = "500"><tr><th></th><th>Reference</th></tr><tr><td><b>Prediction</b></td><td>Agriculture</td><td>Developed</td><td>Forest</td>\
    <td>Non_forest_Wetland</td><td>Other</td><td>Rangeland</td></tr><tr><td>Agriculture</td><td>812</td><td>0</td><td>0</td><td>3</td><td>0</td><td>1</td></tr><tr>\
    <td>Developed</td><td>0</td><td>506</td><td>0</td><td>0</td><td>0</td><td>1</td></tr><tr><td>Forest</td><td>19</td><td>5</td><td>37698</td><td>82</td>\
    <td>26</td><td>215</td></tr><tr><td>Non_forest_Wetland</td><td>2</td><td>1</td><td>5</td><td>2276</td><td>2</td><td>1</td></tr><tr><td>Other</td><td>0</td><td>0</td> \
    <td>5</td><td>1</td><td>6579</td><td>8</td></tr><tr><td>Rangeland</td><td>48</td><td>14</td><td>118</td><td>71</td><td>25</td><td>27661</td></tr></table>'

}