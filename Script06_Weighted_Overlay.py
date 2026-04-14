# =============================================================================
# Script06_Weighted_Overlay.py
# CGC Climate Change and Hazard Exposure Assessment
# Brandon Boldt
#
# PURPOSE:
#   Combine TempRisk, PrecipRisk, and WHP_Risk into composite risk surfaces
#   for all three future time periods using two methods:
#     1. Weighted Overlay  - ArcGIS Pro Spatial Analyst standard tool
#                            (requires integer inputs; continuous rasters
#                             are rounded to integer 1-9 scale first)
#     2. Weighted Sum      - Works directly on continuous float rasters
#                            (more analytically precise; used for comparison)
#
# TIME PERIODS PROCESSED:
#   2010-2039  (near-term)
#   2040-2069  (mid-century)  <-- primary analysis period
#   2070-2099  (late-century)
#
# INPUT RASTERS (must exist in CGC_ClimateHazard.gdb):
#   TempRisk_[YYYY_YYYY]     - Continuous float, 1-9 scale
#   PrecipRisk_[YYYY_YYYY]   - Continuous float, 1-9 scale
#   WHP_Risk                 - Discrete integer: 3, 6, or 9
#                              (shared across all periods - current landscape)
#
# OUTPUT RASTERS (per period):
#   WeightedOverlay_[YYYY_YYYY]  - Integer 1-9 composite (official WO tool)
#   WeightedSum_[YYYY_YYYY]      - Continuous 1-9 composite (float precision)
#
# WEIGHTS (must sum to 1.0):
#   Temperature:   30%  (0.30)
#   Precipitation: 30%  (0.30)
#   Wildfire:      40%  (0.40)
#
# WEIGHT RATIONALE:
#   Wildfire weighted highest (40%) because it represents an acute, landscape-
#   level hazard with direct farm infrastructure and operational risk. Climate
#   metrics are equally weighted (30% each) reflecting symmetric uncertainty
#   in mid-century projections under RCP 4.5. Adjust weights here if needed
#   for sensitivity analysis.
#
# EXECUTION (from ArcGIS Pro Python window):
#   exec(open(r"C:\Users\Brandon Boldt\OneDrive\Documents\FRCC\CGC_ClimateHazard_Project\Output_Maps_and_Documentation\Scripts\Script06_Weighted_Overlay.py").read())
# =============================================================================

import arcpy
from arcpy.sa import *
import os
import traceback

# =============================================================================
# CONFIGURATION - Edit here if paths or weights need to change
# =============================================================================

PROJECT_ROOT = r"C:\Users\Brandon Boldt\OneDrive\Documents\FRCC\CGC_ClimateHazard_Project"
GDB_PATH     = os.path.join(PROJECT_ROOT, "CGC_ClimateHazard_Project", "CGC_ClimateHazard.gdb")

# Time periods to process
TIME_PERIODS = ["2010_2039", "2040_2069", "2070_2099"]

# WHP_Risk is shared across all periods (current landscape conditions)
WHP_RISK = os.path.join(GDB_PATH, "WHP_Risk")

# Weights (must sum to 1.0)
W_TEMP   = 0.30   # 30%
W_PRECIP = 0.30   # 30%
W_WHP    = 0.40   # 40%

# Sanity check weights
assert abs((W_TEMP + W_PRECIP + W_WHP) - 1.0) < 0.0001, \
    "ERROR: Weights must sum to 1.0. Check W_TEMP, W_PRECIP, W_WHP."

# =============================================================================
# SETUP
# =============================================================================

print("=" * 65)
print("Script06: Weighted Overlay Composite (All Time Periods)")
print("=" * 65)
print(f"\n  Periods to process: {', '.join(TIME_PERIODS)}")
print(f"  Weights - Temp: {int(W_TEMP*100)}%  |  "
      f"Precip: {int(W_PRECIP*100)}%  |  "
      f"Wildfire: {int(W_WHP*100)}%")

# Check out Spatial Analyst license
if arcpy.CheckExtension("Spatial") == "Available":
    arcpy.CheckOutExtension("Spatial")
    print("\n[OK] Spatial Analyst extension checked out")
else:
    raise RuntimeError("Spatial Analyst extension is not available.")

arcpy.env.workspace       = GDB_PATH
arcpy.env.overwriteOutput = True
arcpy.env.cellSize        = "MINOF"

# =============================================================================
# VALIDATE: WHP_Risk (shared input)
# =============================================================================

print("\n--- Validating Shared Input ---")
if arcpy.Exists(WHP_RISK):
    rmin = float(arcpy.management.GetRasterProperties(WHP_RISK, "MINIMUM").getOutput(0))
    rmax = float(arcpy.management.GetRasterProperties(WHP_RISK, "MAXIMUM").getOutput(0))
    print(f"  [OK] WHP_Risk  range: {rmin:.0f} - {rmax:.0f}")
else:
    raise FileNotFoundError(f"WHP_Risk not found at: {WHP_RISK}")

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def safe_delete(path):
    """Delete a raster if it exists. Required before CopyRaster calls."""
    if arcpy.Exists(path):
        arcpy.management.Delete(path)


def get_stats(path):
    """Return (min, max, mean, std) for a raster."""
    props = ["MINIMUM", "MAXIMUM", "MEAN", "STD"]
    return tuple(
        float(arcpy.management.GetRasterProperties(path, p).getOutput(0))
        for p in props
    )

# =============================================================================
# MAIN LOOP - Process each time period
# =============================================================================


results_summary = []  # Collect stats for final report

for period in TIME_PERIODS:

    print(f"\n{'=' * 65}")
    print(f"  Processing period: {period}")
    print(f"{'=' * 65}")

    # Build paths for this period
    temp_risk   = os.path.join(GDB_PATH, f"TempRisk_{period}")
    precip_risk = os.path.join(GDB_PATH, f"PrecipRisk_{period}")
    temp_int    = os.path.join(GDB_PATH, f"TempRisk_Int_{period}")
    precip_int  = os.path.join(GDB_PATH, f"PrecipRisk_Int_{period}")
    out_wo      = os.path.join(GDB_PATH, f"WeightedOverlay_{period}")
    out_ws      = os.path.join(GDB_PATH, f"WeightedSum_{period}")

    # ------------------------------------------------------------------
    # Validate inputs for this period
    # ------------------------------------------------------------------
    print(f"\n  Validating inputs for {period}...")
    missing = []
    for name, path in [(f"TempRisk_{period}", temp_risk),
                       (f"PrecipRisk_{period}", precip_risk)]:
        if arcpy.Exists(path):
            rmin = float(arcpy.management.GetRasterProperties(path, "MINIMUM").getOutput(0))
            rmax = float(arcpy.management.GetRasterProperties(path, "MAXIMUM").getOutput(0))
            print(f"    [OK] {name:35s} range: {rmin:.2f} - {rmax:.2f}")
        else:
            print(f"    [MISSING] {name} not found at: {path}")
            missing.append(name)

    if missing:
        print(f"  [SKIP] {period} - missing inputs, skipping this period.")
        results_summary.append((period, "SKIPPED - missing inputs", None, None))
        continue

    try:
        # --------------------------------------------------------------
        # Step 1: Convert continuous rasters to integer (for WeightedOverlay)
        # --------------------------------------------------------------
        print(f"\n  Step 1: Converting to integer rasters...")

        temp_rounded   = Int(Raster(temp_risk)   + 0.5)
        precip_rounded = Int(Raster(precip_risk) + 0.5)

        # Clamp to [1, 9]
        temp_int_ras   = Con(temp_rounded   < 1, 1, Con(temp_rounded   > 9, 9, temp_rounded))
        precip_int_ras = Con(precip_rounded < 1, 1, Con(precip_rounded > 9, 9, precip_rounded))

        safe_delete(temp_int)
        arcpy.management.CopyRaster(temp_int_ras,   temp_int,   pixel_type="8_BIT_UNSIGNED")

        safe_delete(precip_int)
        arcpy.management.CopyRaster(precip_int_ras, precip_int, pixel_type="8_BIT_UNSIGNED")

        print(f"    [Saved] TempRisk_Int_{period}")
        print(f"    [Saved] PrecipRisk_Int_{period}")

        # --------------------------------------------------------------
        # Step 2: Weighted Overlay
        # --------------------------------------------------------------
        print(f"\n  Step 2: Running Weighted Overlay...")

        temp_remap   = RemapValue([[1,1],[2,2],[3,3],[4,4],[5,5],[6,6],[7,7],[8,8],[9,9]])
        precip_remap = RemapValue([[1,1],[2,2],[3,3],[4,4],[5,5],[6,6],[7,7],[8,8],[9,9]])
        whp_remap    = RemapValue([[3,3],[6,6],[9,9]])

        wo_table = WOTable(
            [
                [temp_int,   int(W_TEMP   * 100), "VALUE", temp_remap],
                [precip_int, int(W_PRECIP * 100), "VALUE", precip_remap],
                [WHP_RISK,   int(W_WHP    * 100), "VALUE", whp_remap],
            ],
            [1, 9, 1]
        )

        wo_result = WeightedOverlay(wo_table)

        safe_delete(out_wo)
        arcpy.management.CopyRaster(wo_result, out_wo, pixel_type="8_BIT_UNSIGNED")

        wo_min, wo_max, wo_mean, wo_std = get_stats(out_wo)
        print(f"    [Saved] WeightedOverlay_{period}")
        print(f"    [Stats] Min: {int(wo_min)}  Max: {int(wo_max)}  "
              f"Mean: {wo_mean:.2f}  StdDev: {wo_std:.2f}")

        # --------------------------------------------------------------
        # Step 3: Weighted Sum
        # --------------------------------------------------------------
        print(f"\n  Step 3: Running Weighted Sum...")

        ws_table = WSTable(
            [
                [temp_risk,   "VALUE", W_TEMP],
                [precip_risk, "VALUE", W_PRECIP],
                [WHP_RISK,    "VALUE", W_WHP],
            ]
        )

        ws_result = WeightedSum(ws_table)

        safe_delete(out_ws)
        arcpy.management.CopyRaster(ws_result, out_ws, pixel_type="32_BIT_FLOAT")

        ws_min, ws_max, ws_mean, ws_std = get_stats(out_ws)
        print(f"    [Saved] WeightedSum_{period}")
        print(f"    [Stats] Min: {ws_min:.2f}  Max: {ws_max:.2f}  "
              f"Mean: {ws_mean:.2f}  StdDev: {ws_std:.2f}")

        # --------------------------------------------------------------
        # Step 4: Sanity check - compare WO vs WS
        # --------------------------------------------------------------
        diff      = Raster(out_ws) - Raster(out_wo)
        diff_mean = float(arcpy.management.GetRasterProperties(diff, "MEAN").getOutput(0))
        diff_min  = float(arcpy.management.GetRasterProperties(diff, "MINIMUM").getOutput(0))
        diff_max  = float(arcpy.management.GetRasterProperties(diff, "MAXIMUM").getOutput(0))

        status = "OK" if abs(diff_mean) < 0.5 else "WARN"
        print(f"\n  [{status}] WO vs WS difference: "
              f"range {diff_min:.2f} to {diff_max:.2f}, mean {diff_mean:.2f}")

        results_summary.append((period, "SUCCESS", wo_mean, ws_mean))

    except Exception as e:
        print(f"\n  [ERROR] Period {period} failed: {e}")
        traceback.print_exc()
        results_summary.append((period, f"ERROR: {e}", None, None))
        continue

# =============================================================================
# FINAL SUMMARY REPORT
# =============================================================================

print(f"\n{'=' * 65}")
print("Script06 Complete - Summary of All Periods")
print(f"{'=' * 65}")
print(f"\n  {'Period':<15} {'Status':<12} {'WO Mean':>8} {'WS Mean':>8}")
print(f"  {'-'*14} {'-'*11} {'-'*8} {'-'*8}")

for period, status, wo_mean, ws_mean in results_summary:
    wo_str = f"{wo_mean:.2f}" if wo_mean is not None else "  --  "
    ws_str = f"{ws_mean:.2f}" if ws_mean is not None else "  --  "
    print(f"  {period:<15} {status:<12} {wo_str:>8} {ws_str:>8}")

print(f"""
  All outputs saved to:
  {GDB_PATH}

  Output rasters created:
    WeightedOverlay_2010_2039  /  WeightedSum_2010_2039
    WeightedOverlay_2040_2069  /  WeightedSum_2040_2069
    WeightedOverlay_2070_2099  /  WeightedSum_2070_2099

  Intermediate integer rasters:
    TempRisk_Int_[period] and PrecipRisk_Int_[period] for each period

  NEXT STEPS:
  -----------
  1. Verify all three WeightedOverlay outputs in ArcGIS Pro map.
     Mean risk values should increase from 2010-2039 to 2070-2099,
     reflecting the growing climate change signal in later periods.

  2. Run Script07_Fuzzy_Overlay.py for the second composite method
     (also loops over all three time periods).

  3. Run Script08_Farm_Zonal_Stats.py to extract per-farm risk scores.
""")

arcpy.env.addOutputsToMap = True   # Restore default behavior
arcpy.CheckInExtension("Spatial")
print("  [OK] Spatial Analyst license returned")
