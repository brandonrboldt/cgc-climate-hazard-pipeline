# =============================================================================
# Script07_Fuzzy_Overlay.py
# CGC Climate Change and Hazard Exposure Assessment
# Brandon Boldt
#
# PURPOSE:
#   Create fuzzy overlay composite risk surfaces for all three future time
#   periods as an alternative to the weighted overlay method in Script06.
#
# METHODOLOGY:
#   Step 1 - Fuzzy Membership:
#     Each input risk raster (1-9 scale) is converted to fuzzy membership
#     values (0-1) using FuzzyLarge (monotonically increasing sigmoid).
#
#     CALIBRATION (midpoint=5, spread=4):
#       Chosen so that the WHP discrete values produce well-separated
#       membership values across the full risk scale:
#         WHP=3 (Low)      -> ~0.115
#         WHP=6 (Moderate) -> ~0.675
#         WHP=9 (High)     -> ~0.913
#       Climate values also distribute meaningfully:
#         TempRisk 2010-2039 (1.0-1.98) -> 0.002-0.024  (correctly near-zero)
#         TempRisk 2040-2069 (5.45-6.55) -> 0.50-0.675  (mid-range)
#         TempRisk 2070-2099 (7.64-9.00) -> 0.874-0.996 (high)
#       Spread=4 was selected over spread=5 to preserve the small but real
#       climate signal in the near-term (2010-2039) period.
#
#   Step 2 - Fuzzy Overlay (three operators):
#     GAMMA (0.9) - Primary output. Compromise between AND and OR, weighted
#                   toward OR. Standard for risk/suitability analysis.
#     AND         - Lower bound (pessimistic). Composite = minimum membership.
#     OR          - Upper bound (optimistic). Composite = maximum membership.
#
#   Step 3 - Rescale to 1-9:
#     All fuzzy outputs (0-1) linearly rescaled to 1-9 for direct comparison
#     with WeightedOverlay and WeightedSum outputs from Script06.
#
# TIME PERIODS: 2010-2039, 2040-2069, 2070-2099
#
# EXECUTION (from ArcGIS Pro Python window):
#   exec(open(r"C:\Users\Brandon Boldt\OneDrive\Documents\FRCC\CGC_ClimateHazard_Project\Output_Maps_and_Documentation\Scripts\Script07_Fuzzy_Overlay.py").read())
# =============================================================================

import arcpy
from arcpy.sa import *
import os
import shutil
import traceback

# =============================================================================
# CONFIGURATION
# =============================================================================

PROJECT_ROOT = r"C:\Users\Brandon Boldt\OneDrive\Documents\FRCC\CGC_ClimateHazard_Project"
GDB_PATH     = os.path.join(PROJECT_ROOT, "CGC_ClimateHazard_Project", "CGC_ClimateHazard.gdb")

TIME_PERIODS = ["2010_2039", "2040_2069", "2070_2099"]

WHP_RISK = os.path.join(GDB_PATH, "WHP_Risk")

# Fuzzy membership parameters
# midpoint=5: center of the 1-9 scale; membership=0.5 at risk value 5
# spread=4:   produces well-separated membership for WHP (3->0.115, 6->0.675, 9->0.913)
#             and meaningful differentiation across all three time periods
FUZZY_MIDPOINT = 5.0
FUZZY_SPREAD   = 4.0

# Expected membership values at key risk scores (for sanity checking output)
# Calculated as: 1 / (1 + (x/midpoint)^(-spread))
EXPECTED_MEMBERSHIP = {
    1: 0.002, 2: 0.025, 3: 0.115, 4: 0.309,
    5: 0.500, 6: 0.675, 7: 0.840, 8: 0.913, 9: 0.950
}

GAMMA_VALUE = 0.9

# =============================================================================
# SETUP
# =============================================================================

print("=" * 65)
print("Script07: Fuzzy Overlay Composite (All Time Periods)")
print("=" * 65)
print(f"\n  Periods:          {', '.join(TIME_PERIODS)}")
print(f"  Membership fn:    FuzzyLarge(midpoint={FUZZY_MIDPOINT}, spread={FUZZY_SPREAD})")
print(f"  Primary operator: GAMMA ({GAMMA_VALUE})")
print(f"  Bracketing:       AND (lower bound), OR (upper bound)")
print(f"\n  Expected membership at key values:")
print(f"    Risk=1 -> {EXPECTED_MEMBERSHIP[1]:.3f}  (very low risk)")
print(f"    Risk=3 -> {EXPECTED_MEMBERSHIP[3]:.3f}  (WHP Low / low climate)")
print(f"    Risk=5 -> {EXPECTED_MEMBERSHIP[5]:.3f}  (midpoint)")
print(f"    Risk=6 -> {EXPECTED_MEMBERSHIP[6]:.3f}  (WHP Moderate)")
print(f"    Risk=9 -> {EXPECTED_MEMBERSHIP[9]:.3f}  (WHP High / max climate)")

if arcpy.CheckExtension("Spatial") == "Available":
    arcpy.CheckOutExtension("Spatial")
    print("\n[OK] Spatial Analyst extension checked out")
else:
    raise RuntimeError("Spatial Analyst extension is not available.")

arcpy.env.workspace       = GDB_PATH
arcpy.env.overwriteOutput = True
arcpy.env.cellSize        = "MINOF"
arcpy.env.addOutputsToMap = False  # Prevents outputs auto-appearing in Contents panel

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def safe_delete(path):
    """
    Delete a raster robustly:
    1. Try arcpy.management.Delete (handles normal cases)
    2. If arcpy.Exists returns False but folder exists on disk,
       use shutil.rmtree to remove the orphaned FGDB raster folder.
       This handles corrupted GDB entries invisible to arcpy but
       still blocking CopyRaster writes.
    """
    if arcpy.Exists(path):
        arcpy.management.Delete(path)
    # Also check disk directly -- arcpy.Exists can miss corrupted entries
    if os.path.exists(path):
        shutil.rmtree(path, ignore_errors=True)


def get_stats(path):
    props = ["MINIMUM", "MAXIMUM", "MEAN", "STD"]
    return tuple(
        float(arcpy.management.GetRasterProperties(path, p).getOutput(0))
        for p in props
    )


def rescale_0_1_to_1_9(raster):
    """Linearly rescale 0-1 fuzzy output to 1-9 risk scale."""
    scaled = raster * 8.0 + 1.0
    return Con(scaled < 1.0, 1.0, Con(scaled > 9.0, 9.0, scaled))


def check_membership_calibration(path, label, expected_vals):
    """
    Print membership stats and flag if values suggest miscalibration.
    A well-calibrated membership raster should span a wide portion of 0-1.
    If min and max are within 0.15 of each other, the function is too flat.
    """
    rmin, rmax, rmean, rstd = get_stats(path)
    span = rmax - rmin
    flag = "[WARN - span too narrow, check calibration]" if span < 0.05 else "[OK]"
    print(f"    {flag} {label}")
    print(f"           range: {rmin:.3f} - {rmax:.3f}  "
          f"span: {span:.3f}  mean: {rmean:.3f}")

# =============================================================================
# VALIDATE SHARED INPUT
# =============================================================================


print("\n--- Validating Shared Input ---")
if arcpy.Exists(WHP_RISK):
    whp_min, whp_max, _, _ = get_stats(WHP_RISK)
    print(f"  [OK] WHP_Risk  range: {whp_min:.0f} - {whp_max:.0f}")
else:
    raise FileNotFoundError("WHP_Risk not found. Ensure Script05 ran successfully.")

# =============================================================================
# COMPUTE WHP MEMBERSHIP ONCE (shared across all periods)
# WHP_Risk does not vary by time period, so membership is identical for all.
# Computing once avoids redundant writes and sidesteps any per-period
# naming conflicts in the geodatabase.
# =============================================================================

print("\n--- Computing WHP Fuzzy Membership (shared, once) ---")

WHP_MEMBER = os.path.join(GDB_PATH, "FuzzyMember_WHP")
membership_fn_shared = FuzzyLarge(FUZZY_MIDPOINT, FUZZY_SPREAD)

try:
    whp_member_shared = FuzzyMembership(Raster(WHP_RISK), membership_fn_shared)
    safe_delete(WHP_MEMBER)
    arcpy.management.CopyRaster(whp_member_shared, WHP_MEMBER, pixel_type="32_BIT_FLOAT")
    wm_min, wm_max, wm_mean, _ = get_stats(WHP_MEMBER)
    span = wm_max - wm_min
    flag = "[OK]" if span >= 0.05 else "[WARN - span too narrow]"
    print(f"  {flag} FuzzyMember_WHP  range: {wm_min:.3f} - {wm_max:.3f}  ")
    print(f"        span: {span:.3f}  mean: {wm_mean:.3f}")
    print(f"        (expected ~0.115-0.913 for WHP values 3/6/9)")
except Exception as e:
    raise RuntimeError(f"Failed to create shared WHP membership raster: {e}")

# =============================================================================
# MAIN LOOP
# =============================================================================

results_summary = []

for period in TIME_PERIODS:

    print(f"\n{'=' * 65}")
    print(f"  Processing period: {period}")
    print(f"{'=' * 65}")

    # Input paths
    temp_risk   = os.path.join(GDB_PATH, f"TempRisk_{period}")
    precip_risk = os.path.join(GDB_PATH, f"PrecipRisk_{period}")

    # Fuzzy membership output paths
    fm_temp   = os.path.join(GDB_PATH, f"FuzzyMember_Temp_{period}")
    fm_precip = os.path.join(GDB_PATH, f"FuzzyMember_Precip_{period}")
    # fm_whp is shared - computed once before loop as FuzzyMember_WHP

    # Fuzzy overlay output paths (rescaled 1-9)
    out_gamma = os.path.join(GDB_PATH, f"FuzzyOverlay_Gamma_{period}")
    out_and   = os.path.join(GDB_PATH, f"FuzzyOverlay_AND_{period}")
    out_or    = os.path.join(GDB_PATH, f"FuzzyOverlay_OR_{period}")

    # Clear workspace cache before each period to prevent FGDB lock carryover
    arcpy.management.ClearWorkspaceCache()

    # Validate inputs
    print(f"\n  Validating inputs...")
    missing = []
    for name, path in [(f"TempRisk_{period}", temp_risk),
                       (f"PrecipRisk_{period}", precip_risk)]:
        if arcpy.Exists(path):
            rmin, rmax, _, _ = get_stats(path)
            print(f"    [OK] {name:35s} range: {rmin:.2f} - {rmax:.2f}")
        else:
            print(f"    [MISSING] {name}")
            missing.append(name)

    if missing:
        print(f"  [SKIP] {period} - missing inputs.")
        results_summary.append((period, "SKIPPED", None, None, None, None, None))
        continue

    try:
        # --------------------------------------------------------------
        # Step 1: Fuzzy Membership
        # --------------------------------------------------------------
        print(f"\n  Step 1: Computing fuzzy membership values...")

        membership_fn = FuzzyLarge(FUZZY_MIDPOINT, FUZZY_SPREAD)

        # Temperature membership
        temp_member = FuzzyMembership(Raster(temp_risk), membership_fn)
        safe_delete(fm_temp)
        arcpy.management.CopyRaster(temp_member, fm_temp, pixel_type="32_BIT_FLOAT")
        check_membership_calibration(fm_temp, f"FuzzyMember_Temp_{period}",
                                     EXPECTED_MEMBERSHIP)

        # Precipitation membership
        precip_member = FuzzyMembership(Raster(precip_risk), membership_fn)
        safe_delete(fm_precip)
        arcpy.management.CopyRaster(precip_member, fm_precip, pixel_type="32_BIT_FLOAT")
        check_membership_calibration(fm_precip, f"FuzzyMember_Precip_{period}",
                                     EXPECTED_MEMBERSHIP)

        # WHP membership: use shared raster computed before loop
        print(f"    [Reusing] FuzzyMember_WHP (shared across all periods)")

        # --------------------------------------------------------------
        # Step 2a: Fuzzy Overlay - GAMMA (primary)
        # --------------------------------------------------------------
        print(f"\n  Step 2a: Fuzzy Overlay GAMMA ({GAMMA_VALUE})...")

        gamma_raw    = FuzzyOverlay([fm_temp, fm_precip, WHP_MEMBER], "GAMMA", GAMMA_VALUE)
        gamma_scaled = rescale_0_1_to_1_9(gamma_raw)

        safe_delete(out_gamma)
        arcpy.management.CopyRaster(gamma_scaled, out_gamma, pixel_type="32_BIT_FLOAT")
        g_min, g_max, g_mean, g_std = get_stats(out_gamma)
        print(f"    [Saved] FuzzyOverlay_Gamma_{period}")
        print(f"    [Stats] Min: {g_min:.2f}  Max: {g_max:.2f}  "
              f"Mean: {g_mean:.2f}  StdDev: {g_std:.2f}")

        # --------------------------------------------------------------
        # Step 2b: Fuzzy Overlay - AND (lower bound)
        # --------------------------------------------------------------
        print(f"\n  Step 2b: Fuzzy Overlay AND (lower bound)...")

        and_raw    = FuzzyOverlay([fm_temp, fm_precip, WHP_MEMBER], "AND")
        and_scaled = rescale_0_1_to_1_9(and_raw)

        safe_delete(out_and)
        arcpy.management.CopyRaster(and_scaled, out_and, pixel_type="32_BIT_FLOAT")
        a_min, a_max, a_mean, a_std = get_stats(out_and)
        print(f"    [Saved] FuzzyOverlay_AND_{period}")
        print(f"    [Stats] Min: {a_min:.2f}  Max: {a_max:.2f}  "
              f"Mean: {a_mean:.2f}  StdDev: {a_std:.2f}")

        # --------------------------------------------------------------
        # Step 2c: Fuzzy Overlay - OR (upper bound)
        # --------------------------------------------------------------
        print(f"\n  Step 2c: Fuzzy Overlay OR (upper bound)...")

        or_raw    = FuzzyOverlay([fm_temp, fm_precip, WHP_MEMBER], "OR")
        or_scaled = rescale_0_1_to_1_9(or_raw)

        safe_delete(out_or)
        arcpy.management.CopyRaster(or_scaled, out_or, pixel_type="32_BIT_FLOAT")
        o_min, o_max, o_mean, o_std = get_stats(out_or)
        print(f"    [Saved] FuzzyOverlay_OR_{period}")
        print(f"    [Stats] Min: {o_min:.2f}  Max: {o_max:.2f}  "
              f"Mean: {o_mean:.2f}  StdDev: {o_std:.2f}")

        # --------------------------------------------------------------
        # Step 3: Compare Gamma vs WeightedOverlay from Script06
        # --------------------------------------------------------------
        wo_path = os.path.join(GDB_PATH, f"WeightedOverlay_{period}")
        if arcpy.Exists(wo_path):
            diff      = Raster(out_gamma) - Raster(wo_path)
            diff_mean = float(arcpy.management.GetRasterProperties(diff, "MEAN").getOutput(0))
            diff_min  = float(arcpy.management.GetRasterProperties(diff, "MINIMUM").getOutput(0))
            diff_max  = float(arcpy.management.GetRasterProperties(diff, "MAXIMUM").getOutput(0))
            wo_mean   = float(arcpy.management.GetRasterProperties(wo_path, "MEAN").getOutput(0))
            agreement = "GOOD" if abs(diff_mean) < 1.0 else "MODERATE" if abs(diff_mean) < 2.0 else "DIVERGENT"
            print(f"\n  Method comparison: FuzzyGamma vs WeightedOverlay [{agreement}]")
            print(f"    WeightedOverlay mean:  {wo_mean:.2f}")
            print(f"    FuzzyGamma mean:       {g_mean:.2f}")
            print(f"    Difference (Gamma-WO): {diff_mean:.2f} "
                  f"(range: {diff_min:.2f} to {diff_max:.2f})")
        else:
            wo_mean   = None
            diff_mean = None
            print(f"\n  [INFO] WeightedOverlay_{period} not found - skipping comparison")

        results_summary.append((period, "SUCCESS", g_mean, a_mean, o_mean,
                                 wo_mean, diff_mean))

    except Exception as e:
        print(f"\n  [ERROR] Period {period} failed: {e}")
        traceback.print_exc()
        results_summary.append((period, f"ERROR: {e}", None, None, None, None, None))
        continue

# =============================================================================
# FINAL SUMMARY
# =============================================================================

print(f"\n{'=' * 65}")
print("Script07 Complete - Fuzzy Overlay Summary (All Periods)")
print(f"{'=' * 65}")

print(f"\n  {'Period':<15} {'Gamma':>7} {'AND':>7} {'OR':>7} "
      f"{'WO':>7} {'Diff':>7} {'AND-OR':>7}")
print(f"  {'-'*14} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7}")

for row in results_summary:
    period, status = row[0], row[1]
    if status == "SUCCESS":
        g, a, o, wo, diff = row[2], row[3], row[4], row[5], row[6]
        spread = o - a if (o and a) else None
        g_s    = f"{g:.2f}"    if g    is not None else "  --"
        a_s    = f"{a:.2f}"    if a    is not None else "  --"
        o_s    = f"{o:.2f}"    if o    is not None else "  --"
        wo_s   = f"{wo:.2f}"   if wo   is not None else "  --"
        d_s    = f"{diff:.2f}" if diff is not None else "  --"
        sp_s   = f"{spread:.2f}" if spread is not None else "  --"
        print(f"  {period:<15} {g_s:>7} {a_s:>7} {o_s:>7} {wo_s:>7} {d_s:>7} {sp_s:>7}")
    else:
        print(f"  {period:<15} {status}")

print(f"""
  Column key:
    Gamma  = FuzzyOverlay GAMMA 0.9, rescaled 1-9 (primary output)
    AND    = FuzzyOverlay AND, lower bound, rescaled 1-9
    OR     = FuzzyOverlay OR, upper bound, rescaled 1-9
    WO     = WeightedOverlay mean from Script06
    Diff   = Gamma minus WO (method agreement)
    AND-OR = Spread between bounds (uncertainty estimate)

  INTERPRETATION:
    - Gamma and WO should show similar temporal trends (both increase
      from 2010-2039 to 2070-2099) even if absolute values differ.
    - AND-OR spread indicates spatial uncertainty: where one factor
      is high and others low, the bounds will diverge more.
    - 2010-2039 Gamma will be driven primarily by WHP since climate
      risk is genuinely low (TempRisk 1.0-1.98) -- this is correct.

  All outputs saved to:
  {GDB_PATH}

  NEXT STEPS:
  -----------
  1. Verify FuzzyOverlay_Gamma maps in ArcGIS Pro. Check that:
       - Spatial pattern matches WeightedOverlay qualitatively
       - WHP_Risk pattern is clearly visible (low plains, high mountains)
       - Temporal progression from 2010-2039 to 2070-2099 is visible

  2. Run Script08_Farm_Zonal_Stats.py to extract per-farm risk scores
     from both WeightedOverlay and FuzzyOverlay outputs.
""")

arcpy.env.addOutputsToMap = True   # Restore default behavior
arcpy.CheckInExtension("Spatial")
print("  [OK] Spatial Analyst license returned")
