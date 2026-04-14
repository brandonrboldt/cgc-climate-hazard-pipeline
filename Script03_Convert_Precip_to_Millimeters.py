"""
CGC Climate Change and Hazard Exposure Assessment
Precipitation Unit Conversion Script
====================================================================

Purpose: Convert precipitation rasters from inches to millimeters
    Formula: inches × 25.4 = mm

Author: Brandon Boldt
Date: February 2026

Requirements:
    - ArcGIS Pro with Spatial Analyst extension
    - Precipitation rasters already processed (in geodatabase)
"""

import arcpy
from arcpy.sa import *

# ============================================================================
# USER PARAMETERS
# ============================================================================

# Geodatabase path
gdb_path = r"C:\Users\Brandon Boldt\OneDrive\Documents\FRCC\CGC_ClimateHazard_Project\CGC_ClimateHazard_Project\CGC_ClimateHazard.gdb"

# Precipitation rasters to convert (in inches)
precip_rasters_in = [
    "Precip_Historical_1971_2000",
    "Precip_Future_2010_2039",
    "Precip_Future_2040_2069",
    "Precip_Future_2070_2099"
]

# ============================================================================
# SETUP
# ============================================================================

print("=" * 70)
print("PRECIPITATION UNIT CONVERSION: inches → mm")
print("=" * 70)
print()

# Set workspace
arcpy.env.workspace = gdb_path
arcpy.env.overwriteOutput = True

# Check out Spatial Analyst
try:
    if arcpy.CheckExtension("Spatial") == "Available":
        arcpy.CheckOutExtension("Spatial")
        print("✓ Spatial Analyst extension checked out")
    else:
        raise Exception("Spatial Analyst not available!")
except Exception as e:
    print(f"ERROR: {e}")
    exit()

print(f"✓ Workspace: {gdb_path}")
print()
print("Formula: inches × 25.4 = mm")
print()

# ============================================================================
# CONVERSION FUNCTION
# ============================================================================


def convert_in_to_mm(raster_name):
    """
    Convert a precipitation raster from inches to millimeters

    Args:
        raster_name: Name of raster in geodatabase (currently in inches)

    Returns:
        True if successful, False otherwise
    """
    try:
        print(f"Converting: {raster_name}")

        # Input raster (inches)
        input_raster = Raster(raster_name)

        # Formula: inches * 25.4 = mm
        output_raster = input_raster * 25.4

        # Create temporary name
        temp_name = f"{raster_name}_TEMP"
        temp_path = arcpy.os.path.join(gdb_path, temp_name)

        # Save the mm version with temp name
        output_raster.save(temp_path)
        print(f"  → Created millimeters version")

        # Delete the old inches version
        arcpy.management.Delete(raster_name)
        print(f"  → Deleted old inches version")

        # Rename temp version to original name (now that old one is gone)
        arcpy.management.Rename(temp_name, raster_name)
        print(f"  → Renamed to: {raster_name}")

        print(f"  ✓ SUCCESS: {raster_name} now in mm")
        return True

    except Exception as e:
        print(f"  ✗ ERROR: {str(e)}")
        print(f"    ArcPy messages: {arcpy.GetMessages()}")
        return False

# ============================================================================
# MAIN CONVERSION LOOP
# ============================================================================


print("=" * 70)
print("STARTING CONVERSIONS")
print("=" * 70)
print()

success_count = 0
fail_count = 0

for raster_name in precip_rasters_in:
    # Check if raster exists
    if arcpy.Exists(raster_name):
        if convert_in_to_mm(raster_name):
            success_count += 1
        else:
            fail_count += 1
        print()  # Blank line between rasters
    else:
        print(f"✗ RASTER NOT FOUND: {raster_name}")
        print(f"  Skipping...")
        print()
        fail_count += 1

# ============================================================================
# SUMMARY
# ============================================================================

print("=" * 70)
print("CONVERSION COMPLETE")
print("=" * 70)
print(f"Total rasters: {len(precip_rasters_in)}")
print(f"  ✓ Converted: {success_count}")
print(f"  ✗ Failed: {fail_count}")
print()

if success_count == len(precip_rasters_in):
    print("🎉 ALL PRECIPITATION RASTERS NOW IN MILLIMETERS!")
    print()
    print("Next steps:")
    print("  1. Verify precipitation values are reasonable (200-1000+ mm)")
    print("  2. Begin delta calculations (percent change)")
else:
    print("⚠ Some conversions failed. Review errors above.")

print()
print("=" * 70)

# Check in extension
arcpy.CheckInExtension("Spatial")
print("✓ Spatial Analyst extension checked in")
print("\nScript complete.")
