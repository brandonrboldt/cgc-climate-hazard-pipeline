# =============================================================================
# Script09_Component_Risk_Extraction.py
# CGC Climate & Hazard Project – Component Risk Extraction
# Brandon Boldt
#
# Purpose:
#   Extract per-farm mean values for each individual risk component
#   (temperature, precipitation, wildfire) across all time periods using
#   5km farm buffers and Zonal Statistics. Results are joined back to the
#   CGC_Farms feature class as new fields, enabling hazard decomposition
#   analysis and identification of which component drives risk at each farm.
#
# Inputs required (must exist in CGC_ClimateHazard.gdb):
#   Rasters:
#     TempRisk_2010_2039, TempRisk_2040_2069, TempRisk_2070_2099
#     PrecipRisk_2010_2039, PrecipRisk_2040_2069, PrecipRisk_2070_2099
#     WHP_Risk
#   Feature classes:
#     Inputs/CGC_Farms
#     Intermediate/CGC_Farm_Buffers_5km  (created by Script08 - will be
#                                         created here if not present)
#
# Outputs:
#   New fields added to CGC_Farms:
#     TempRisk_Mean_10_39, TempRisk_Mean_40_69, TempRisk_Mean_70_99
#     PrecipRisk_Mean_10_39, PrecipRisk_Mean_40_69, PrecipRisk_Mean_70_99
#     WHP_Risk_Mean
#     (WHP_Risk_Mean is period-agnostic; replicated in decomposition calcs)
#
# Usage:
#   Run from ArcGIS Pro Python window:
#   exec(open(r"C:\Users\Brandon Boldt\OneDrive\Documents\FRCC\
#             CGC_ClimateHazard_Project\Output_Maps_and_Documentation\
#             Scripts\Script09_Component_Risk_Extraction.py").read())
#
# Author: Brandon Boldt | GIS2011 / GIS2040 / GIS1065 | FRCC Spring 2026
# =============================================================================

import arcpy
import os

# ── USER PARAMETERS ──────────────────────────────────────────────────────────

# Geodatabase path
gdb = r"C:\Users\Brandon Boldt\OneDrive\Documents\FRCC\CGC_ClimateHazard_Project\CGC_ClimateHazard.gdb"

# Scratch workspace for intermediate zonal statistics tables
scratch_gdb = arcpy.env.scratchGDB

# Buffer distance (must match Script08)
BUFFER_DIST = "5000 Meters"

# Join field – unique farm identifier used to link stats back to farms
JOIN_FIELD = "FarmID"

# =============================================================================


def check_extension():
    """Check out Spatial Analyst license."""
    if arcpy.CheckExtension("Spatial") == "Available":
        arcpy.CheckOutExtension("Spatial")
        print("  Spatial Analyst license checked out.")
    else:
        raise RuntimeError("Spatial Analyst extension is not available. "
                           "Cannot proceed.")


def validate_inputs(gdb, raster_names, farms_fc, buffer_fc_path):
    """Confirm all required rasters and the farm feature class exist."""
    print("\nValidating inputs...")
    missing = []

    if not arcpy.Exists(farms_fc):
        missing.append(f"Farm feature class: {farms_fc}")

    for rname in raster_names:
        rpath = os.path.join(gdb, rname)
        if not arcpy.Exists(rpath):
            missing.append(f"Raster: {rname}")

    if missing:
        print("  MISSING INPUTS:")
        for m in missing:
            print(f"    - {m}")
        raise FileNotFoundError(
            "One or more required inputs are missing. "
            "Ensure Scripts 01–05 have been run successfully."
        )
    print(f"  All {len(raster_names)} rasters found.")
    print("  Farm feature class found.")


def get_or_create_buffers(farms_fc, buffer_fc_path, buffer_dist, join_field):
    """
    Return path to 5km farm buffers. Creates them if Script08 hasn't
    already done so.
    """
    if arcpy.Exists(buffer_fc_path):
        count = int(arcpy.GetCount_management(buffer_fc_path)[0])
        print(f"\n  Farm buffers already exist ({count} features). Reusing.")
        return buffer_fc_path

    print(f"\n  Farm buffers not found. Creating {buffer_dist} buffers...")
    arcpy.analysis.Buffer(
        in_features=farms_fc,
        out_feature_class=buffer_fc_path,
        buffer_distance_or_field=buffer_dist,
        line_side="FULL",
        line_end_type="ROUND",
        dissolve_option="NONE"
    )
    print(arcpy.GetMessages())
    count = int(arcpy.GetCount_management(buffer_fc_path)[0])
    print(f"  Buffers created: {count} features.")
    return buffer_fc_path


def run_zonal_stats(raster_path, buffer_fc, join_field, stats_table_path):
    """
    Run Zonal Statistics as Table (MEAN) for one raster × buffer combination.
    Deletes existing output table first to avoid conflicts.
    """
    # Clear any pre-existing table
    if arcpy.Exists(stats_table_path):
        arcpy.management.Delete(stats_table_path)

    arcpy.sa.ZonalStatisticsAsTable(
        in_zone_data=buffer_fc,
        zone_field=join_field,
        in_value_raster=raster_path,
        out_table=stats_table_path,
        ignore_nodata="DATA",
        statistics_type="MEAN"
    )
    print(arcpy.GetMessages(0))  # info-level messages only


def add_field_if_missing(fc, field_name, field_type="DOUBLE"):
    """Add a field to a feature class only if it doesn't already exist."""
    existing = [f.name for f in arcpy.ListFields(fc)]
    if field_name not in existing:
        arcpy.management.AddField(fc, field_name, field_type)


def join_mean_to_farms(farms_fc, stats_table, target_field, join_field):
    """
    Transfer the MEAN column from a zonal statistics table into a new
    field on the farm feature class using a dictionary join (fast, no
    temporary joins left behind).
    """
    # Build lookup: FarmID → MEAN value
    mean_lookup = {}
    with arcpy.da.SearchCursor(stats_table, [join_field, "MEAN"]) as cursor:
        for row in cursor:
            mean_lookup[row[0]] = row[1]

    if not mean_lookup:
        print(f"    WARNING: No values returned from stats table for {target_field}.")
        return 0

    # Ensure target field exists
    add_field_if_missing(farms_fc, target_field)

    # Write values
    updated = 0
    with arcpy.da.UpdateCursor(farms_fc, [join_field, target_field]) as cursor:
        for row in cursor:
            farm_id = row[0]
            if farm_id in mean_lookup:
                row[1] = round(mean_lookup[farm_id], 4)
                cursor.updateRow(row)
                updated += 1

    return updated


# =============================================================================
# MAIN WORKFLOW
# =============================================================================

print("=" * 65)
print("Script09 – Component Risk Extraction")
print("CGC Climate & Hazard Project | FRCC GIS Spring 2026")
print("=" * 65)

# ── Environment setup ─────────────────────────────────────────────────────────
arcpy.env.workspace = gdb
arcpy.env.overwriteOutput = True

# ── License ───────────────────────────────────────────────────────────────────
check_extension()

# ── Define rasters to extract ─────────────────────────────────────────────────
# Each entry: (raster_name_in_gdb, output_field_on_farms)
# WHP_Risk is extracted once; it applies to all periods in decomposition math.
RASTER_FIELD_MAP = [
    ("TempRisk_2010_2039",   "TempRisk_Mean_10_39"),
    ("TempRisk_2040_2069",   "TempRisk_Mean_40_69"),
    ("TempRisk_2070_2099",   "TempRisk_Mean_70_99"),
    ("PrecipRisk_2010_2039", "PrecipRisk_Mean_10_39"),
    ("PrecipRisk_2040_2069", "PrecipRisk_Mean_40_69"),
    ("PrecipRisk_2070_2099", "PrecipRisk_Mean_70_99"),
    ("WHP_Risk",             "WHP_Risk_Mean"),
]

raster_names = [r for r, _ in RASTER_FIELD_MAP]

# ── Feature class paths ───────────────────────────────────────────────────────
farms_fc      = os.path.join(gdb, "Inputs", "CGC_Farms")
buffer_fc     = os.path.join(gdb, "Intermediate", "CGC_Farm_Buffers_5km")

# ── Validate ──────────────────────────────────────────────────────────────────
validate_inputs(gdb, raster_names, farms_fc, buffer_fc)

# ── Buffers ───────────────────────────────────────────────────────────────────
buffer_fc = get_or_create_buffers(farms_fc, buffer_fc, BUFFER_DIST, JOIN_FIELD)

# ── Main extraction loop ──────────────────────────────────────────────────────
print(f"\nExtracting component risk values for {len(RASTER_FIELD_MAP)} rasters...")
print("-" * 65)

total_updated = 0
errors = []

for i, (raster_name, target_field) in enumerate(RASTER_FIELD_MAP, start=1):
    print(f"\n[{i}/{len(RASTER_FIELD_MAP)}]  {raster_name}  →  {target_field}")

    raster_path = os.path.join(gdb, raster_name)
    stats_table = os.path.join(scratch_gdb, f"ZonalStats_{raster_name}")

    try:
        # Step 1: Zonal statistics
        print("  Running Zonal Statistics as Table (MEAN)...")
        run_zonal_stats(raster_path, buffer_fc, JOIN_FIELD, stats_table)

        # Step 2: Verify row count
        result_count = int(arcpy.GetCount_management(stats_table)[0])
        print(f"  Zonal stats table: {result_count} records")

        # Step 3: Join mean back to farms
        n = join_mean_to_farms(farms_fc, stats_table, target_field, JOIN_FIELD)
        print(f"  Joined to farms: {n} records updated")
        total_updated += n

        # Step 4: Clean up scratch table
        arcpy.management.Delete(stats_table)

    except Exception as e:
        err_msg = f"  ERROR on {raster_name}: {e}"
        print(err_msg)
        errors.append(err_msg)

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n" + "=" * 65)
print("SCRIPT09 COMPLETE – SUMMARY")
print("=" * 65)
print(f"  Rasters processed : {len(RASTER_FIELD_MAP) - len(errors)}/{len(RASTER_FIELD_MAP)}")
print(f"  Total field updates: {total_updated}")

new_fields = [f for _, f in RASTER_FIELD_MAP]
print(f"\n  New fields added to CGC_Farms:")
for f in new_fields:
    print(f"    • {f}")

if errors:
    print(f"\n  ERRORS ({len(errors)}):")
    for e in errors:
        print(f"    {e}")
else:
    print("\n  No errors encountered.")

print("""
NEXT STEPS
----------
The following analyses are now supported by the new fields:

1. HAZARD DECOMPOSITION
   For each farm and time period, calculate each component's share
   of the weighted composite score:
     TempShare    = (TempRisk_Mean   * 0.30) / CompositeScore
     PrecipShare  = (PrecipRisk_Mean * 0.30) / CompositeScore
     WHPShare     = (WHP_Risk_Mean   * 0.40) / CompositeScore
   Group by region (Front Range, Plains, Western Slope) to reveal
   whether wildfire, temperature, or precipitation dominates.

2. TEMPORAL TRAJECTORY
   Compare TempRisk_Mean and PrecipRisk_Mean across 10_39 → 40_69
   → 70_99 per farm. Farms whose total risk increases rapidly are
   driven by one or both climate components (WHP is static).

3. PRECIPITATION BANDING VALIDATION
   Farms ordered along a SW-NE axis should show more similar
   PrecipRisk_Mean values than farms on a NW-SE transect — a
   simple attribute-level check before full raster transect work.
""")

arcpy.CheckInExtension("Spatial")
print("  Spatial Analyst license returned.")
print("=" * 65)
