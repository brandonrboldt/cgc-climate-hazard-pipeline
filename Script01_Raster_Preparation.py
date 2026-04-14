"""
CGC Climate Change and Hazard Exposure Assessment
Raster Preparation Script
=========================================================

Purpose: Batch process all climate and wildfire rasters to standardized specifications
    - Project to NAD 1983 UTM Zone 13N
    - Resample to 1000m cell size
    - Clip to Colorado boundary

Author: Brandon Boldt
Date: February 2026

Requirements:
    - ArcGIS Pro with Spatial Analyst extension
    - Input rasters in Original_Data folders
    - Colorado_Boundary in CGC_ClimateHazard.gdb/Inputs
"""

import arcpy
import os
from arcpy import env
from arcpy.sa import *

# ============================================================================
# USER PARAMETERS - EDIT THESE PATHS TO MATCH YOUR SYSTEM
# ============================================================================

# Base project directory - UPDATE THIS PATH if not Brandon Boldt!
project_dir = r"C:\Users\Brandon Boldt\OneDrive\Documents\FRCC\CGC_ClimateHazard_Project"

# Input data folders
temp_folder = os.path.join(project_dir, "Original_Data", "Temperature")
precip_folder = os.path.join(project_dir, "Original_Data", "Precipitation")
wildfire_folder = os.path.join(project_dir, "Original_Data", "Wildfire")

# Geodatabase paths
gdb_path = os.path.join(project_dir, "CGC_ClimateHazard_Project", "CGC_ClimateHazard.gdb")
colorado_boundary = os.path.join(gdb_path, "Inputs", "Colorado_Boundary")

# Output location (intermediate rasters go here)
output_gdb = gdb_path

# Processing parameters
target_crs = arcpy.SpatialReference(26913)  # NAD 1983 UTM Zone 13N
target_cell_size = 1000  # meters
resampling_method = "BILINEAR"  # Good for continuous data like temperature

# ============================================================================
# ENVIRONMENT SETUP
# ============================================================================

print("=" * 70)
print("CGC CLIMATE & HAZARD PROJECT - RASTER PREPARATION")
print("=" * 70)
print()

# Set workspace
env.workspace = output_gdb
env.overwriteOutput = True

# Check out Spatial Analyst extension
try:
    if arcpy.CheckExtension("Spatial") == "Available":
        arcpy.CheckOutExtension("Spatial")
        print("✓ Spatial Analyst extension checked out successfully")
    else:
        raise Exception("Spatial Analyst extension not available!")
except Exception as e:
    print(f"ERROR: {e}")
    print("Cannot proceed without Spatial Analyst extension.")
    exit()

# Verify Colorado boundary exists
if not arcpy.Exists(colorado_boundary):
    print(f"ERROR: Colorado boundary not found at {colorado_boundary}")
    print("Please verify the path and try again.")
    exit()
else:
    print(f"✓ Colorado boundary found: {colorado_boundary}")

print()
print("Processing Parameters:")
print(f"  Target CRS: NAD 1983 UTM Zone 13N (EPSG:26913)")
print(f"  Cell Size: {target_cell_size}m")
print(f"  Resampling: {resampling_method}")
print()

# ============================================================================
# DEFINE INPUT RASTERS
# ============================================================================

# Temperature rasters (4 files)
temp_rasters = [
    ("macav2metdata_tasmax_ANN_19712000_historical_20CMIP5ModelMean.tif", "Temp_Historical_1971_2000"),
    ("macav2metdata_tasmax_ANN_20102039_rcp45_20CMIP5ModelMean.tif", "Temp_Future_2010_2039"),
    ("macav2metdata_tasmax_ANN_20402069_rcp45_20CMIP5ModelMean.tif", "Temp_Future_2040_2069"),
    ("macav2metdata_tasmax_ANN_20702099_rcp45_20CMIP5ModelMean.tif", "Temp_Future_2070_2099")
]

# Precipitation rasters (4 files)
precip_rasters = [
    ("macav2metdata_pr_ANN_19712000_historical_20CMIP5ModelMean.tif", "Precip_Historical_1971_2000"),
    ("macav2metdata_pr_ANN_20102039_rcp45_20CMIP5ModelMean.tif", "Precip_Future_2010_2039"),
    ("macav2metdata_pr_ANN_20402069_rcp45_20CMIP5ModelMean.tif", "Precip_Future_2040_2069"),
    ("macav2metdata_pr_ANN_20702099_rcp45_20CMIP5ModelMean.tif", "Precip_Future_2070_2099")
]

# Wildfire raster (1 file)
wildfire_rasters = [
    ("WHP_CO.tif", "WHP_Colorado")
]

# ============================================================================
# BATCH PROCESSING FUNCTION
# ============================================================================


def process_raster(input_path, output_name, data_type="climate"):
    """
    Process a single raster: project, resample, clip

    Args:
        input_path: Full path to input raster
        output_name: Name for output raster in geodatabase
        data_type: "climate" or "wildfire" (affects resampling method)

    Returns:
        True if successful, False otherwise
    """
    try:
        print(f"\nProcessing: {os.path.basename(input_path)}")
        print(f"  → Output: {output_name}")

        # Step 1: Project to UTM 13N
        print("  [1/3] Projecting to NAD 1983 UTM Zone 13N...")
        projected = os.path.join(env.workspace, f"{output_name}_proj")
        arcpy.management.ProjectRaster(
            in_raster=input_path,
            out_raster=projected,
            out_coor_system=target_crs,
            resampling_type=resampling_method
        )

        # Step 2: Resample to 1000m
        print("  [2/3] Resampling to 1000m cell size...")
        resampled = os.path.join(env.workspace, f"{output_name}_resamp")

        # For wildfire (categorical), use NEAREST; for climate (continuous), use BILINEAR
        resample_method = "NEAREST" if data_type == "wildfire" else "BILINEAR"

        arcpy.management.Resample(
            in_raster=projected,
            out_raster=resampled,
            cell_size=f"{target_cell_size} {target_cell_size}",
            resampling_type=resample_method
        )

        # Step 3: Extract by mask (clip to Colorado)
        print("  [3/3] Clipping to Colorado boundary...")
        output_final = os.path.join(env.workspace, output_name)

        # Use Extract by Mask (requires Spatial Analyst)
        out_extract = ExtractByMask(resampled, colorado_boundary)
        out_extract.save(output_final)

        # Clean up intermediate files
        arcpy.management.Delete(projected)
        arcpy.management.Delete(resampled)

        print(f"  ✓ SUCCESS: {output_name}")
        return True

    except Exception as e:
        print(f"  ✗ ERROR processing {output_name}: {str(e)}")
        print(f"    ArcPy messages: {arcpy.GetMessages()}")
        return False

# ============================================================================
# MAIN PROCESSING LOOP
# ============================================================================


print("\n" + "=" * 70)
print("STARTING BATCH PROCESSING")
print("=" * 70)

success_count = 0
fail_count = 0
total_count = len(temp_rasters) + len(precip_rasters) + len(wildfire_rasters)

# Process temperature rasters
print("\n--- TEMPERATURE RASTERS (4 files) ---")
for filename, output_name in temp_rasters:
    input_path = os.path.join(temp_folder, filename)
    if os.path.exists(input_path):
        if process_raster(input_path, output_name, data_type="climate"):
            success_count += 1
        else:
            fail_count += 1
    else:
        print(f"\n✗ FILE NOT FOUND: {input_path}")
        fail_count += 1

# Process precipitation rasters
print("\n--- PRECIPITATION RASTERS (4 files) ---")
for filename, output_name in precip_rasters:
    input_path = os.path.join(precip_folder, filename)
    if os.path.exists(input_path):
        if process_raster(input_path, output_name, data_type="climate"):
            success_count += 1
        else:
            fail_count += 1
    else:
        print(f"\n✗ FILE NOT FOUND: {input_path}")
        fail_count += 1

# Process wildfire raster
print("\n--- WILDFIRE HAZARD RASTER (1 file) ---")
for filename, output_name in wildfire_rasters:
    input_path = os.path.join(wildfire_folder, filename)
    if os.path.exists(input_path):
        if process_raster(input_path, output_name, data_type="wildfire"):
            success_count += 1
        else:
            fail_count += 1
    else:
        print(f"\n✗ FILE NOT FOUND: {input_path}")
        fail_count += 1

# ============================================================================
# SUMMARY REPORT
# ============================================================================

print("\n" + "=" * 70)
print("PROCESSING COMPLETE")
print("=" * 70)
print(f"Total rasters processed: {total_count}")
print(f"  ✓ Successful: {success_count}")
print(f"  ✗ Failed: {fail_count}")
print()

if success_count == total_count:
    print("🎉 ALL RASTERS PROCESSED SUCCESSFULLY!")
    print()
    print("Next steps:")
    print("  1. Verify rasters in ArcGIS Pro")
    print("  2. Check cell sizes and extents match")
    print("  3. Begin raster math (delta calculations)")
else:
    print("⚠ Some rasters failed to process. Review errors above.")

print()
print("Output location:", output_gdb)
print("=" * 70)

# Check in Spatial Analyst extension
arcpy.CheckInExtension("Spatial")
print("\n✓ Spatial Analyst extension checked in")
print("\nScript complete.")
