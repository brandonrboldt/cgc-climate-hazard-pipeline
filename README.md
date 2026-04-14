# CGC Grower Climate & Wildfire Risk Assessment
### Python/arcpy Geospatial Pipeline
**Brandon Boldt**

---

## Overview

A fully automated nine-script Python/arcpy pipeline assessing composite climate and wildfire hazard exposure for 19 Colorado Grain Chain (CGC) member farms across three future time periods (2010–2039, 2040–2069, 2070–2099) under RCP 4.5. Results were published to ArcGIS Online as hosted feature layers, an ArcGIS StoryMap, and an Experience Builder application.

**Live project:** [storymaps.arcgis.com/stories/e662590c95904b7b80eeb2b31829f87d](https://storymaps.arcgis.com/stories/e662590c95904b7b80eeb2b31829f87d)

---

## Pipeline Architecture

```
Script01  Raster Preparation         Project → Resample → Clip to Colorado
Script02  Temperature Conversion     °F → °C (4 rasters)
Script03  Precipitation Conversion   inches → mm (4 rasters)
Script04  Climate Delta Calculation  Future − Historical (temp °C; precip % change)
Script05  Reclassify to Risk Scale   1–9 continuous scale (global breaks)
Script06  Weighted Overlay           Composite risk surface (WO + WeightedSum)
Script07  Fuzzy Overlay              Alternative composite (Gamma/AND/OR operators)
Script08  Farm Zonal Statistics      Per-farm risk extraction, tier classification
Script09  Component Risk Extraction  Decompose composite by temperature/precip/wildfire
```

---

## Key Design Decisions

### Global Reclassification Breaks (Script05)
Reclassification breaks for the 1–9 risk scale are computed **globally across all three time periods** before any reclassification occurs. The same breaks are then applied to each period identically. This ensures cross-temporal comparability. A risk score of 7 in 2010–2039 means the same thing as a risk score of 7 in 2070–2099, enabling meaningful temporal trend analysis in Experience Builder.

### Dual Composite Methods (Scripts 06 & 07)
Two independent composite methods are used and compared:
- **Weighted Overlay / Weighted Sum** (Script06): Standard GIS suitability method; wildfire weighted highest (40%) as an acute landscape-level hazard
- **Fuzzy Overlay** (Script07): GAMMA operator (γ=0.9) with AND/OR bounds; provides uncertainty envelope around the primary composite

**Weights:** Temperature 30% · Precipitation 30% · Wildfire Hazard Potential 40%

### Precipitation Risk as Absolute Deviation (Script05)
Precipitation risk is calculated as **absolute deviation from the historical baseline**, not directional change. Both wetting and drying represent risk to agricultural operations; departure from historical norms in either direction increases hazard exposure.

### 5km Farm Buffers (Scripts 08 & 09)
Zonal statistics are extracted within 5km buffers around each farm centroid rather than at the point location, accounting for the spatial footprint of actual farming operations and reducing sensitivity to point placement error.

---

## Data Sources

| Dataset | Source | Description |
|---------|--------|-------------|
| Temperature rasters | MACA v2 / MACAv2METDATA | Annual max temperature, RCP 4.5, 20-model CMIP5 mean |
| Precipitation rasters | MACA v2 / MACAv2METDATA | Annual precipitation, RCP 4.5, 20-model CMIP5 mean |
| Wildfire Hazard Potential | USFS / USDA | WHP index, national coverage |
| Colorado boundary | Colorado state GIS | Clip boundary |
| Farm locations | Colorado Grain Chain | 19 CGC member farm locations |

---

## Requirements

- ArcGIS Pro with **Spatial Analyst** extension
- Python 3.x (bundled with ArcGIS Pro)
- `arcpy` (ArcGIS Pro Python environment)

---

## Setup

1. Clone or download this repository
2. Open each script and update PROJECT_ROOT and gdb_path to match your local directory structure
3. Ensure all input rasters are placed in the expected `Original_Data` subfolders
4. Run scripts in order (01 → 09) from the ArcGIS Pro Python window:

```python
exec(open(r"path\to\Script01_Raster_Preparation.py").read())
```

---

## Script Reference

### Script01: Raster Preparation
Batch processes all climate and wildfire rasters to standardized specifications: projects to NAD 1983 UTM Zone 13N (EPSG:26913), resamples to 1000m cell size using bilinear interpolation for continuous data and nearest neighbor for categorical (wildfire), and clips to Colorado boundary using Extract by Mask.

### Script02: Temperature Unit Conversion
Converts temperature rasters from Fahrenheit to Celsius using raster algebra: `(°F − 32) × 5/9`. Overwrites input rasters in place using a safe temp/rename/delete pattern.

### Script03: Precipitation Unit Conversion
Converts precipitation rasters from inches to millimeters: `inches × 25.4`. Same safe overwrite pattern as Script02.

### Script04: Climate Delta Calculations
Calculates climate change signals relative to the 1971–2000 historical baseline:
- **Temperature delta:** `Future − Historical (°C)`
- **Precipitation % change:** `((Future − Historical) / Historical) × 100`

### Script05: Reclassify to Risk Scale
Converts climate deltas and wildfire hazard to a common 1–9 risk scale using **globally computed breaks** across all time periods. Temperature uses equal-interval rescaling; precipitation uses absolute deviation from zero; wildfire uses focal statistics smoothing (3×3 mean) and manual breaks (0–800=3, 800–2000=6, 2000+=9).

### Script06: Weighted Overlay
Combines TempRisk, PrecipRisk, and WHP_Risk into composite risk surfaces using two methods: ArcGIS Weighted Overlay tool (integer 1–9) and Weighted Sum (continuous float 1–9). Both methods run for all three time periods. Includes sanity-check comparison between methods.

### Script07: Fuzzy Overlay
Alternative composite using fuzzy set theory. FuzzyLarge membership function (midpoint=5, spread=4) converts 1–9 risk scores to 0–1 membership values. Three operators applied: GAMMA(0.9) as primary output, AND as lower bound, OR as upper bound. All outputs rescaled to 1–9 for direct comparison with Script06. Includes WO vs Gamma agreement assessment.

### Script08: Farm Zonal Statistics
Creates 5km buffers around farm locations, runs Zonal Statistics as Table (MEAN) for all 12 rasters (4 per period × 3 periods), compiles results into a single output feature class, and classifies farms into risk tiers (Low/Moderate/High/Very High) based on averaged WO+Gamma scores. Note: FuzzyOverlay outputs are rescaled from 0-1 to 1-9 in Script07 prior to averaging, ensuring both methods are on comparable scales before the ensemble composite is computed.

### Script09: Component Risk Extraction
Extracts per-farm mean values for each individual risk component (temperature, precipitation, wildfire) separately, enabling hazard decomposition analysis and identifying which driver dominates risk at each farm location.

---

## Output Risk Tiers

| Tier | Score Range | Description |
|------|------------|-------------|
| Low | 1.0 – 3.0 | Minimal projected exposure |
| Moderate | 3.0 – 5.0 | Moderate projected exposure |
| High | 5.0 – 7.0 | Elevated projected exposure |
| Very High | 7.0 – 9.0 | High projected exposure |

---

## Author

**Brandon Boldt**  
B.A.S. GIS Student, Front Range Community College  
M.S. Geosciences, Northern Arizona University  
[brandonboldt.com](https://brandonboldt.com) · [Brandon.R.Boldt@gmail.com](mailto:Brandon.R.Boldt@gmail.com)
