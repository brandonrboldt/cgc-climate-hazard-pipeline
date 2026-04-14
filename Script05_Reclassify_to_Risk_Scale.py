# =============================================================================
# Script05_Reclassify_to_Risk_Scale.py
# CGC Climate Change and Hazard Exposure Assessment
# Brandon Boldt
#
# PURPOSE:
#   Reclassify climate delta rasters and wildfire hazard to a common 1-9 risk
#   scale for all three future time periods.
#
# KEY DESIGN DECISION - GLOBAL BREAKS:
#   Reclassification breaks are computed GLOBALLY across all three time periods
#   before any reclassification occurs. The same breaks are then applied to
#   each period identically. This ensures the 1-9 scale is cross-temporally
#   comparable -- a risk score of 7 in 2010-2039 means the same thing as a
#   risk score of 7 in 2070-2099. This is essential for temporal trend
#   analysis and multi-period display in Experience Builder.
#
# TIME PERIODS PROCESSED:
#   2010-2039  (near-term)
#   2040-2069  (mid-century)  <-- primary analysis period
#   2070-2099  (late-century)
#
# INPUT RASTERS (must exist in CGC_ClimateHazard.gdb):
#   Temp_Delta_[YYYY_YYYY]        - Temperature change from baseline (deg C)
#   Precip_PctChange_[YYYY_YYYY]  - Precipitation % change from baseline
#   WHP_Colorado                  - Wildfire Hazard Potential (raw, 0-20840)
#
# OUTPUT RASTERS (per period):
#   TempRisk_[YYYY_YYYY]          - Continuous 1-9 scale (equal interval)
#   PrecipRisk_[YYYY_YYYY]        - Continuous 1-9 scale (absolute deviation)
#
# OUTPUT RASTERS (shared, created once):
#   WHP_Risk                      - Discrete 3/6/9 (focal smooth + manual breaks)
#
# RECLASSIFICATION METHODS:
#   Temperature:   Equal interval over GLOBAL range across all periods
#                  Higher warming = Higher risk
#   Precipitation: Absolute deviation from zero over GLOBAL max abs deviation
#                  Larger departure (wet OR dry) = Higher risk
#   Wildfire:      3x3 Focal Statistics (MEAN) + manual meaningful breaks
#                  0-800 = 3 (Low), 800-2000 = 6 (Moderate), 2000+ = 9 (High)
#                  (unchanged from original - not time-period dependent)
#
# EXECUTION (from ArcGIS Pro Python window):
#   exec(open(r"C:\Users\Brandon Boldt\OneDrive\Documents\FRCC\CGC_ClimateHazard_Project\Output_Maps_and_Documentation\Scripts\Script05_Reclassify_to_Risk_Scale.py").read())
# =============================================================================

import arcpy
from arcpy.sa import *
import os
import traceback

# =============================================================================
# CONFIGURATION
# =============================================================================

PROJECT_ROOT = r"C:\Users\Brandon Boldt\OneDrive\Documents\FRCC\CGC_ClimateHazard_Project"
GDB_PATH     = os.path.join(PROJECT_ROOT, "CGC_ClimateHazard_Project", "CGC_ClimateHazard.gdb")

TIME_PERIODS = ["2010_2039", "2040_2069", "2070_2099"]

# Wildfire input (raw, pre-smoothing)
WHP_INPUT  = os.path.join(GDB_PATH, "WHP_Colorado")
WHP_OUTPUT = os.path.join(GDB_PATH, "WHP_Risk")

# Wildfire manual break thresholds (based on WHP index interpretation)
WHP_LOW_BREAK  = 800    # 0-800    -> 3 (Low:    eastern plains)
WHP_HIGH_BREAK = 2000   # 800-2000 -> 6 (Moderate: foothills/transition)
                        # 2000+    -> 9 (High:   mountains/Front Range)

# =============================================================================
# SETUP
# =============================================================================

print("=" * 65)
print("Script05: Reclassify to Risk Scale (All Time Periods)")
print("=" * 65)
print(f"\n  Periods: {', '.join(TIME_PERIODS)}")
print(f"  Method:  Global breaks for cross-temporal comparability")

if arcpy.CheckExtension("Spatial") == "Available":
    arcpy.CheckOutExtension("Spatial")
    print("\n[OK] Spatial Analyst extension checked out")
else:
    raise RuntimeError("Spatial Analyst extension is not available.")

arcpy.env.workspace       = GDB_PATH
arcpy.env.overwriteOutput = True

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def safe_delete(path):
    if arcpy.Exists(path):
        arcpy.management.Delete(path)


def get_min_max(path):
    """Return (min, max) for a raster."""
    rmin = float(arcpy.management.GetRasterProperties(path, "MINIMUM").getOutput(0))
    rmax = float(arcpy.management.GetRasterProperties(path, "MAXIMUM").getOutput(0))
    return rmin, rmax


def rescale_to_risk(raster, global_min, global_max):
    """
    Linearly rescale raster values to 1-9 based on global min/max.
    Formula: ((value - global_min) / (global_max - global_min)) * 8 + 1
    Clamp output to [1, 9] to handle any floating point edge cases.
    """
    span = global_max - global_min
    if span == 0:
        raise ValueError("Global min and max are identical — cannot rescale.")
    scaled = ((raster - global_min) / span) * 8.0 + 1.0
    # Clamp to [1, 9]
    clamped = Con(scaled < 1.0, 1.0, Con(scaled > 9.0, 9.0, scaled))
    return clamped

# =============================================================================
# PASS 1: VALIDATE ALL INPUTS AND GATHER GLOBAL STATISTICS
# =============================================================================


print("\n" + "=" * 65)
print("Pass 1: Validating inputs and computing global statistics")
print("=" * 65)

# Track global bounds across all periods
temp_global_min =  999.0
temp_global_max = -999.0
precip_global_max_abs = 0.0  # Max absolute deviation from zero

all_inputs_valid = True

for period in TIME_PERIODS:
    temp_delta_path   = os.path.join(GDB_PATH, f"Temp_Delta_{period}")
    precip_delta_path = os.path.join(GDB_PATH, f"Precip_PctChange_{period}")

    print(f"\n  Period: {period}")

    # Validate and get temp stats
    if arcpy.Exists(temp_delta_path):
        tmin, tmax = get_min_max(temp_delta_path)
        temp_global_min = min(temp_global_min, tmin)
        temp_global_max = max(temp_global_max, tmax)
        print(f"    [OK] Temp_Delta_{period}: {tmin:.3f} to {tmax:.3f} deg C")
    else:
        print(f"    [MISSING] Temp_Delta_{period}")
        all_inputs_valid = False

    # Validate and get precip stats
    # For precipitation we use absolute deviation, so we need max(abs(min), abs(max))
    if arcpy.Exists(precip_delta_path):
        pmin, pmax = get_min_max(precip_delta_path)
        period_max_abs = max(abs(pmin), abs(pmax))
        precip_global_max_abs = max(precip_global_max_abs, period_max_abs)
        print(f"    [OK] Precip_PctChange_{period}: {pmin:.3f} to {pmax:.3f} %")
        print(f"         Max absolute deviation this period: {period_max_abs:.3f} %")
    else:
        print(f"    [MISSING] Precip_PctChange_{period}")
        all_inputs_valid = False

# Validate WHP input
if arcpy.Exists(WHP_INPUT):
    whp_min, whp_max = get_min_max(WHP_INPUT)
    print(f"\n  [OK] WHP_Colorado: {whp_min:.0f} to {whp_max:.0f}")
else:
    print(f"\n  [MISSING] WHP_Colorado")
    all_inputs_valid = False

if not all_inputs_valid:
    raise FileNotFoundError(
        "One or more input rasters are missing. "
        "Ensure Scripts 01-04 completed successfully before running Script05.")

# Report global bounds
print(f"\n{'=' * 65}")
print("  GLOBAL RECLASSIFICATION BOUNDS (document these for write-up)")
print(f"{'=' * 65}")
print(f"\n  Temperature Delta:")
print(f"    Global min: {temp_global_min:.4f} deg C  (lowest warming, any period)")
print(f"    Global max: {temp_global_max:.4f} deg C  (highest warming, any period)")
print(f"    Scale:      {temp_global_min:.4f} deg C -> 1 (lowest risk)")
print(f"                {temp_global_max:.4f} deg C -> 9 (highest risk)")

print(f"\n  Precipitation % Change (absolute deviation):")
print(f"    Global max absolute deviation: {precip_global_max_abs:.4f} %")
print(f"    Scale:      0 % deviation      -> 1 (lowest risk)")
print(f"                {precip_global_max_abs:.4f} % deviation -> 9 (highest risk)")

print(f"\n  Wildfire Hazard Potential:")
print(f"    Method: 3x3 Focal Statistics (MEAN) + manual breaks")
print(f"    0 - {WHP_LOW_BREAK}   -> 3 (Low risk)")
print(f"    {WHP_LOW_BREAK} - {WHP_HIGH_BREAK} -> 6 (Moderate risk)")
print(f"    {WHP_HIGH_BREAK}+      -> 9 (High risk)")

# =============================================================================
# PASS 2: CREATE WHP_RISK (once, shared across all periods)
# =============================================================================

print(f"\n{'=' * 65}")
print("Pass 2: Creating WHP_Risk (shared across all periods)")
print(f"{'=' * 65}")

try:
    # Check if WHP_Risk already exists and is valid
    if arcpy.Exists(WHP_OUTPUT):
        whp_r_min, whp_r_max = get_min_max(WHP_OUTPUT)
        print(f"\n  WHP_Risk already exists (range: {whp_r_min:.0f} - {whp_r_max:.0f})")
        print(f"  Rebuilding to ensure consistency...")
        safe_delete(WHP_OUTPUT)

    print(f"\n  Applying 3x3 Focal Statistics (MEAN) for smoothing...")
    whp_raw     = Raster(WHP_INPUT)
    whp_smooth  = FocalStatistics(whp_raw, NbrRectangle(3, 3, "CELL"), "MEAN", "DATA")

    print(f"  Applying manual risk breaks...")
    # 0-800 -> 3, 800-2000 -> 6, 2000+ -> 9
    whp_risk = Con(whp_smooth <= WHP_LOW_BREAK, 3,
                   Con(whp_smooth <= WHP_HIGH_BREAK, 6, 9))

    safe_delete(WHP_OUTPUT)
    arcpy.management.CopyRaster(whp_risk, WHP_OUTPUT, pixel_type="8_BIT_UNSIGNED")

    whp_r_min, whp_r_max = get_min_max(WHP_OUTPUT)
    print(f"  [Saved] WHP_Risk  range: {whp_r_min:.0f} - {whp_r_max:.0f} (expected: 3-9)")

except Exception as e:
    print(f"[ERROR] WHP_Risk creation failed: {e}")
    traceback.print_exc()
    raise

# =============================================================================
# PASS 3: RECLASSIFY CLIMATE RASTERS FOR EACH PERIOD
# =============================================================================

print(f"\n{'=' * 65}")
print("Pass 3: Reclassifying climate rasters (global breaks)")
print(f"{'=' * 65}")

results_summary = []

for period in TIME_PERIODS:

    print(f"\n  --- Period: {period} ---")

    temp_delta_path   = os.path.join(GDB_PATH, f"Temp_Delta_{period}")
    precip_delta_path = os.path.join(GDB_PATH, f"Precip_PctChange_{period}")
    temp_risk_out     = os.path.join(GDB_PATH, f"TempRisk_{period}")
    precip_risk_out   = os.path.join(GDB_PATH, f"PrecipRisk_{period}")

    try:
        # ------------------------------------------------------------------
        # Temperature Risk: linear rescale using global min/max
        # Higher warming = higher risk (direct relationship)
        # ------------------------------------------------------------------
        print(f"  Temperature reclassification (equal interval, global bounds)...")

        temp_ras  = Raster(temp_delta_path)
        temp_risk = rescale_to_risk(temp_ras, temp_global_min, temp_global_max)

        safe_delete(temp_risk_out)
        arcpy.management.CopyRaster(temp_risk, temp_risk_out, pixel_type="32_BIT_FLOAT")

        tr_min, tr_max = get_min_max(temp_risk_out)
        print(f"    [Saved] TempRisk_{period}  range: {tr_min:.2f} - {tr_max:.2f}")

        # ------------------------------------------------------------------
        # Precipitation Risk: absolute deviation rescaled to 1-9
        # Both wetting and drying are risks; deviation from zero = risk
        # Global max absolute deviation anchors the top of the scale (9)
        # ------------------------------------------------------------------
        print(f"  Precipitation reclassification (absolute deviation, global bounds)...")

        precip_ras     = Raster(precip_delta_path)
        precip_abs_dev = Abs(precip_ras)   # Convert to absolute deviation

        # Rescale: 0 deviation -> 1, global_max_abs_dev -> 9
        precip_risk = rescale_to_risk(precip_abs_dev, 0.0, precip_global_max_abs)

        safe_delete(precip_risk_out)
        arcpy.management.CopyRaster(precip_risk, precip_risk_out, pixel_type="32_BIT_FLOAT")

        pr_min, pr_max = get_min_max(precip_risk_out)
        print(f"    [Saved] PrecipRisk_{period}  range: {pr_min:.2f} - {pr_max:.2f}")

        results_summary.append((period, "SUCCESS", tr_min, tr_max, pr_min, pr_max))

    except Exception as e:
        print(f"  [ERROR] Period {period} failed: {e}")
        traceback.print_exc()
        results_summary.append((period, f"ERROR: {e}", None, None, None, None))
        continue

# =============================================================================
# FINAL SUMMARY
# =============================================================================

print(f"\n{'=' * 65}")
print("Script05 Complete - Summary")
print(f"{'=' * 65}")

print(f"\n  Global bounds applied:")
print(f"    Temp range:    {temp_global_min:.4f} to {temp_global_max:.4f} deg C")
print(f"    Precip max abs dev: {precip_global_max_abs:.4f} %")

print(f"\n  {'Period':<15} {'Status':<10} {'TempRisk':>12} {'PrecipRisk':>12}")
print(f"  {'-'*14} {'-'*9} {'-'*12} {'-'*12}")

for row in results_summary:
    period, status = row[0], row[1]
    if status == "SUCCESS":
        tr_range = f"{row[2]:.2f}-{row[3]:.2f}"
        pr_range = f"{row[4]:.2f}-{row[5]:.2f}"
        print(f"  {period:<15} {status:<10} {tr_range:>12} {pr_range:>12}")
    else:
        print(f"  {period:<15} {status}")

print(f"""
  All risk rasters saved to:
  {GDB_PATH}

  Outputs created:
    TempRisk_2010_2039,  TempRisk_2040_2069,  TempRisk_2070_2099
    PrecipRisk_2010_2039, PrecipRisk_2040_2069, PrecipRisk_2070_2099
    WHP_Risk (shared)

  NOTE: All TempRisk and PrecipRisk rasters use identical global breaks.
  Risk scores are directly comparable across time periods.

  NEXT STEPS:
  -----------
  1. Run Script06_Weighted_Overlay.py - will now succeed for all 3 periods.
  2. Verify that TempRisk and PrecipRisk mean values increase from
     2010-2039 through 2070-2099, confirming the temporal trend is captured.
""")

arcpy.CheckInExtension("Spatial")
print("  [OK] Spatial Analyst license returned")
