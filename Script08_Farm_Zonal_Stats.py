# =============================================================================
# Script08_Farm_Zonal_Stats.py
# CGC Climate Change and Hazard Exposure Assessment
# Brandon Boldt
#
# PURPOSE:
#   Extract composite risk scores for each CGC farm location across all
#   time periods and overlay methods. Creates 5km buffers around farms,
#   runs Zonal Statistics to extract mean risk per farm, compiles results
#   into a single output feature class, and classifies farms into risk tiers.
#
# METHODOLOGY:
#   1. Create 5km buffers around each farm (stored in Intermediate dataset)
#   2. Run Zonal Statistics as Table for each raster x farm buffer
#   3. Compile all results into output feature class
#   4. Classify farms into risk tiers based on average of WO and Gamma
#
# RISK TIERS (based on averaged WO + Gamma score, 1-9 scale):
#   Low:       1.0 - 3.0
#   Moderate:  3.0 - 5.0
#   High:      5.0 - 7.0
#   Very High: 7.0 - 9.0
#   (Breaks centered on midpoint 5 for equal class widths)
#
# RASTERS EXTRACTED (12 total, 4 per period):
#   WeightedOverlay_[period]     - Integer 1-9, official WO tool
#   WeightedSum_[period]         - Continuous 1-9, float precision
#   FuzzyOverlay_Gamma_[period]  - Primary fuzzy composite, 1-9
#   FuzzyOverlay_AND_[period]    - Lower bound fuzzy, 1-9
#
# OUTPUTS:
#   Intermediate/CGC_Farms_5km_Buffer  - Buffer polygons
#   Outputs/CGC_Farm_Risk_Scores       - Farm points with all risk attributes
#
# EXECUTION (from ArcGIS Pro Python window):
#   exec(open(r"C:\Users\Brandon Boldt\OneDrive\Documents\FRCC\CGC_ClimateHazard_Project\Output_Maps_and_Documentation\Scripts\Script08_Farm_Zonal_Stats.py").read())
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

FARMS_FC     = os.path.join(GDB_PATH, "Inputs", "CGC_Farms")
BUFFER_FC    = os.path.join(GDB_PATH, "Intermediate", "CGC_Farms_5km_Buffer")
OUTPUT_FC    = os.path.join(GDB_PATH, "Outputs", "CGC_Farm_Risk_Scores")

BUFFER_DIST  = "5000 Meters"
TIME_PERIODS = ["2010_2039", "2040_2069", "2070_2099"]

# Rasters to extract per period (field_prefix, raster_name_template)
RASTER_CONFIGS = [
    ("WO", "WeightedOverlay_{period}"),
    ("WS", "WeightedSum_{period}"),
    ("FG", "FuzzyOverlay_Gamma_{period}"),
    ("FA", "FuzzyOverlay_AND_{period}"),
]

# Risk tier breaks
TIER_BREAKS = [
    (1.0, 3.0, "Low"),
    (3.0, 5.0, "Moderate"),
    (5.0, 7.0, "High"),
    (7.0, 9.0, "Very High"),
]

ZONE_FIELD = "FarmID"

# Scratch GDB for temporary zonal stats tables.
# Using a dedicated scratch GDB (instead of memory/) prevents ArcGIS Pro
# from adding temp items to the Contents panel, which avoids red exclamation
# points after the script completes. All scratch tables are deleted at the end.
SCRATCH_GDB = os.path.join(PROJECT_ROOT, "CGC_ClimateHazard_Project", "scratch.gdb")

# =============================================================================
# SETUP
# =============================================================================

print("=" * 65)
print("Script08: Farm-Level Zonal Statistics")
print("=" * 65)
print(f"\n  Buffer distance:    {BUFFER_DIST}")
print(f"  Periods:            {', '.join(TIME_PERIODS)}")
print(f"  Rasters per period: {len(RASTER_CONFIGS)}")
print(f"  Total extractions:  {len(TIME_PERIODS) * len(RASTER_CONFIGS)}")

if arcpy.CheckExtension("Spatial") == "Available":
    arcpy.CheckOutExtension("Spatial")
    print("\n[OK] Spatial Analyst extension checked out")
else:
    raise RuntimeError("Spatial Analyst extension is not available.")

arcpy.env.workspace       = GDB_PATH
arcpy.env.overwriteOutput = True
arcpy.management.ClearWorkspaceCache()
arcpy.env.addOutputsToMap = False  # Prevents temp tables appearing in Contents panel

# Create scratch GDB for temp tables - avoids orphaned Contents panel entries
if not arcpy.Exists(SCRATCH_GDB):
    arcpy.management.CreateFileGDB(
        os.path.dirname(SCRATCH_GDB),
        os.path.basename(SCRATCH_GDB)
    )
    print("[OK] Scratch GDB created for temporary tables")
else:
    print("[OK] Scratch GDB ready")

# Create scratch GDB if it doesn't exist
if not arcpy.Exists(SCRATCH_GDB):
    arcpy.management.CreateFileGDB(
        os.path.dirname(SCRATCH_GDB),
        os.path.basename(SCRATCH_GDB)
    )
    print("[OK] Scratch GDB created")
else:
    print("[OK] Scratch GDB exists")

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def safe_delete(path):
    if arcpy.Exists(path):
        arcpy.management.Delete(path)


def assign_tier(avg_score):
    """Return risk tier label based on averaged composite score."""
    if avg_score is None:
        return "Unknown"
    for low, high, label in TIER_BREAKS:
        if low <= avg_score <= high:
            return label
    return "Very High" if avg_score > 7.0 else "Low"


def short_period(period):
    """Convert 2010_2039 -> 10_39 for compact field names."""
    parts = period.split("_")
    return f"{parts[0][2:]}_{parts[1][2:]}"

# =============================================================================
# VALIDATE INPUTS
# =============================================================================


print("\n--- Validating Inputs ---")

if arcpy.Exists(FARMS_FC):
    farm_count = int(arcpy.management.GetCount(FARMS_FC).getOutput(0))
    print(f"  [OK] CGC_Farms: {farm_count} farms")
else:
    raise FileNotFoundError(f"CGC_Farms not found at: {FARMS_FC}")

print(f"\n  Checking rasters...")
missing_rasters = []
for period in TIME_PERIODS:
    for prefix, template in RASTER_CONFIGS:
        rname = template.format(period=period)
        rpath = os.path.join(GDB_PATH, rname)
        if arcpy.Exists(rpath):
            rmin = float(arcpy.management.GetRasterProperties(rpath, "MINIMUM").getOutput(0))
            rmax = float(arcpy.management.GetRasterProperties(rpath, "MAXIMUM").getOutput(0))
            print(f"    [OK] {rname:45s} {rmin:.1f}-{rmax:.1f}")
        else:
            print(f"    [MISSING] {rname}")
            missing_rasters.append(rname)

if missing_rasters:
    raise FileNotFoundError(
        f"{len(missing_rasters)} rasters missing. "
        "Ensure Scripts 06 and 07 completed successfully.")

# =============================================================================
# STEP 1: CREATE 5KM BUFFERS
# =============================================================================

print(f"\n--- Step 1: Creating 5km Farm Buffers ---")

try:
    safe_delete(BUFFER_FC)
    arcpy.analysis.Buffer(
        in_features              = FARMS_FC,
        out_feature_class        = BUFFER_FC,
        buffer_distance_or_field = BUFFER_DIST,
        line_side                = "FULL",
        line_end_type            = "ROUND",
        dissolve_option          = "NONE"
    )
    buf_count = int(arcpy.management.GetCount(BUFFER_FC).getOutput(0))
    print(f"  [Saved] CGC_Farms_5km_Buffer ({buf_count} buffers)")

except Exception as e:
    print(f"[ERROR] Buffer creation failed: {e}")
    traceback.print_exc()
    raise

# =============================================================================
# STEP 2: ZONAL STATISTICS
# =============================================================================

print(f"\n--- Step 2: Running Zonal Statistics ---")

# Verify zone field
field_info = {f.name: f.type for f in arcpy.ListFields(BUFFER_FC)}
field_names = list(field_info.keys())

if ZONE_FIELD in field_names and field_info[ZONE_FIELD] in ["Integer", "SmallInteger", "OID"]:
    zone_field = ZONE_FIELD
else:
    zone_field = "OBJECTID"
    print(f"  [INFO] FarmID not integer type, using OBJECTID as zone field")

print(f"  Zone field: {zone_field}")

# Initialize farm stats dictionary
farm_stats = {}
cursor_fields = [zone_field]
if "FarmName" in field_names:
    cursor_fields.append("FarmName")
if "County" in field_names:
    cursor_fields.append("County")

with arcpy.da.SearchCursor(BUFFER_FC, cursor_fields) as cursor:
    for row in cursor:
        fid = row[0]
        farm_stats[fid] = {}
        if "FarmName" in cursor_fields:
            farm_stats[fid]["FarmName"] = row[cursor_fields.index("FarmName")]
        if "County" in cursor_fields:
            farm_stats[fid]["County"] = row[cursor_fields.index("County")]

print(f"  Initialized {len(farm_stats)} farm records\n")

# Run extractions
for period in TIME_PERIODS:
    sp = short_period(period)
    print(f"  Period: {period}")
    arcpy.management.ClearWorkspaceCache()

    for prefix, template in RASTER_CONFIGS:
        rname      = template.format(period=period)
        rpath      = os.path.join(GDB_PATH, rname)
        field_name = f"{prefix}_{sp}"
        temp_table = os.path.join(SCRATCH_GDB, f"zs_{prefix}_{sp}")

        try:
            safe_delete(temp_table)
            ZonalStatisticsAsTable(
                in_zone_data    = BUFFER_FC,
                zone_field      = zone_field,
                in_value_raster = rpath,
                out_table       = temp_table,
                ignore_nodata   = "DATA",
                statistics_type = "MEAN"
            )

            extracted = 0
            with arcpy.da.SearchCursor(temp_table, [zone_field, "MEAN"]) as cursor:
                for row in cursor:
                    fid, mean_val = row[0], row[1]
                    if fid in farm_stats:
                        farm_stats[fid][field_name] = round(mean_val, 3)
                        extracted += 1

            arcpy.management.Delete(temp_table)
            print(f"    [OK] {field_name:<12} {extracted} farms extracted")

        except Exception as e:
            print(f"    [ERROR] {field_name}: {e}")
            for fid in farm_stats:
                farm_stats[fid][field_name] = None

# =============================================================================
# STEP 3: CALCULATE AVERAGES AND RISK TIERS
# =============================================================================

print(f"\n--- Step 3: Calculating Averages and Risk Tiers ---")

for fid in farm_stats:
    farm = farm_stats[fid]
    for period in TIME_PERIODS:
        sp     = short_period(period)
        wo_val = farm.get(f"WO_{sp}")
        fg_val = farm.get(f"FG_{sp}")

        if wo_val is not None and fg_val is not None:
            avg = round((wo_val + fg_val) / 2.0, 3)
        elif wo_val is not None:
            avg = wo_val
        elif fg_val is not None:
            avg = fg_val
        else:
            avg = None

        farm[f"Avg_{sp}"]  = avg
        farm[f"Tier_{sp}"] = assign_tier(avg)

print(f"  [OK] Averages and tiers calculated for all farms")

# =============================================================================
# STEP 4: BUILD OUTPUT FEATURE CLASS
# =============================================================================

print(f"\n--- Step 4: Building Output Feature Class ---")

try:
    safe_delete(OUTPUT_FC)
    arcpy.management.CopyFeatures(FARMS_FC, OUTPUT_FC)
    print(f"  [Copied] CGC_Farms -> CGC_Farm_Risk_Scores")

    # Define fields to add
    numeric_fields = []
    text_fields    = []

    for period in TIME_PERIODS:
        sp = short_period(period)
        for prefix, _ in RASTER_CONFIGS:
            numeric_fields.append((f"{prefix}_{sp}", "DOUBLE", f"{prefix} mean {period}"))
        numeric_fields.append((f"Avg_{sp}", "DOUBLE", f"Avg WO+Gamma {period}"))
        text_fields.append((f"Tier_{sp}", "TEXT", f"Risk tier {period}"))

    # Add numeric fields
    for fname, ftype, falias in numeric_fields:
        arcpy.management.AddField(OUTPUT_FC, fname, ftype, field_alias=falias)

    # Add text fields
    for fname, ftype, falias in text_fields:
        arcpy.management.AddField(OUTPUT_FC, fname, ftype,
                                   field_length=20, field_alias=falias)

    total_fields = len(numeric_fields) + len(text_fields)
    print(f"  [OK] Added {total_fields} fields to output")

    # Populate via UpdateCursor
    all_field_names = (
        [zone_field] +
        [f[0] for f in numeric_fields] +
        [f[0] for f in text_fields]
    )

    updated = 0
    with arcpy.da.UpdateCursor(OUTPUT_FC, all_field_names) as cursor:
        for row in cursor:
            fid  = row[0]
            if fid not in farm_stats:
                continue
            farm = farm_stats[fid]
            new_row = [fid]
            for fname, _, _ in numeric_fields:
                new_row.append(farm.get(fname))
            for fname, _, _ in text_fields:
                new_row.append(farm.get(fname))
            cursor.updateRow(new_row)
            updated += 1

    print(f"  [OK] Populated {updated} farm records")

except Exception as e:
    print(f"[ERROR] Output creation failed: {e}")
    traceback.print_exc()
    raise

# =============================================================================
# STEP 5: SUMMARY REPORT
# =============================================================================

print(f"\n{'=' * 65}")
print("Farm Risk Score Summary")
print(f"{'=' * 65}")

print(f"\n  {'ID':>4} {'Farm Name':<25} {'County':<14} "
      f"{'2010':>9} {'2040':>9} {'2070':>9} "
      f"{'Avg10':>6} {'Avg40':>6} {'Avg70':>6}")
print(f"  {'-'*4} {'-'*25} {'-'*14} "
      f"{'-'*9} {'-'*9} {'-'*9} "
      f"{'-'*6} {'-'*6} {'-'*6}")

for fid in sorted(farm_stats.keys()):
    farm   = farm_stats[fid]
    name   = str(farm.get("FarmName", f"Farm_{fid}"))[:24]
    county = str(farm.get("County", ""))[:13]
    t10    = farm.get("Tier_10_39", "??")[:9]
    t40    = farm.get("Tier_40_69", "??")[:9]
    t70    = farm.get("Tier_70_99", "??")[:9]
    a10    = farm.get("Avg_10_39")
    a40    = farm.get("Avg_40_69")
    a70    = farm.get("Avg_70_99")
    a10s   = f"{a10:.2f}" if a10 is not None else "  --"
    a40s   = f"{a40:.2f}" if a40 is not None else "  --"
    a70s   = f"{a70:.2f}" if a70 is not None else "  --"
    print(f"  {fid:>4} {name:<25} {county:<14} "
          f"{t10:>9} {t40:>9} {t70:>9} "
          f"{a10s:>6} {a40s:>6} {a70s:>6}")

# Tier distribution
print(f"\n  Tier Distribution by Period:")
for period in TIME_PERIODS:
    sp = short_period(period)
    counts = {}
    for farm in farm_stats.values():
        tier = farm.get(f"Tier_{sp}", "Unknown")
        counts[tier] = counts.get(tier, 0) + 1
    tiers_present = [t for t in ["Low","Moderate","High","Very High","Unknown"]
                     if counts.get(t, 0) > 0]
    tier_str = "  |  ".join([f"{t}: {counts[t]}" for t in tiers_present])
    print(f"    {period}: {tier_str}")

# =============================================================================
# CLEANUP: Remove all temporary zonal stats tables from scratch GDB
# =============================================================================

print(f"\n--- Cleanup: Removing temporary tables ---")
try:
    arcpy.env.workspace = SCRATCH_GDB
    temp_tables = arcpy.ListTables()
    if temp_tables:
        for t in temp_tables:
            arcpy.management.Delete(os.path.join(SCRATCH_GDB, t))
        print(f"  [OK] Removed {len(temp_tables)} temporary tables from scratch GDB")
    else:
        print(f"  [OK] No temporary tables found - already clean")
    arcpy.env.workspace = GDB_PATH
except Exception as e:
    print(f"  [WARN] Cleanup encountered an issue: {e}")
    arcpy.env.workspace = GDB_PATH

print(f"""
{'=' * 65}
Script08 Complete
{'=' * 65}

  Output: {OUTPUT_FC}

  Fields per period (sp = 10_39 / 40_69 / 70_99):
    WO_[sp]   WeightedOverlay mean score
    WS_[sp]   WeightedSum mean score
    FG_[sp]   FuzzyGamma mean score
    FA_[sp]   FuzzyAND mean score
    Avg_[sp]  Average of WO + FuzzyGamma (tier basis)
    Tier_[sp] Low / Moderate / High / Very High

  NEXT STEPS:
  -----------
  1. Open CGC_Farm_Risk_Scores in ArcGIS Pro map.
     Symbolize by Tier_40_69 using unique values:
       Low       = Green
       Moderate  = Yellow
       High      = Orange
       Very High = Red

  2. Verify that farms near mountains/Front Range score higher
     than farms on the eastern plains.

  3. Publish CGC_Farm_Risk_Scores to ArcGIS Online for
     Experience Builder app development.
""")

arcpy.env.addOutputsToMap = True   # Restore default behavior
arcpy.CheckInExtension("Spatial")
print("  [OK] Spatial Analyst license returned")
