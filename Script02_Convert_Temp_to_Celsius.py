"""
CGC Climate Change and Hazard Exposure Assessment
Temperature Unit Conversion Script
==================================================================

Purpose: Convert temperature rasters from Fahrenheit to Celsius
    Formula: (°F - 32) × 5/9 = °C

Author: Brandon Boldt
Date: February 2026

Requirements:
    - ArcGIS Pro with Spatial Analyst extension
    - Temperature rasters already processed (in geodatabase)
"""

import arcpy
from arcpy.sa import *

# ============================================================================
# USER PARAMETERS
# ============================================================================

# Geodatabase path
gdb_path = r"C:\Users\Brandon Boldt\OneDrive\Documents\FRCC\CGC_ClimateHazard_Project\CGC_ClimateHazard_Project\CGC_ClimateHazard.gdb"

# Temperature rasters to convert (in Fahrenheit)
temp_rasters_f = [
    "Temp_Historical_1971_2000",
    "Temp_Future_2010_2039",
    "Temp_Future_2040_2069",
    "Temp_Future_2070_2099"
]

# ============================================================================
# SETUP
# ============================================================================

print("=" * 70)
print("TEMPERATURE UNIT CONVERSION: °F → °C")
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
print("Formula: (°F - 32) × 5/9 = °C")
print()

# ============================================================================
# CONVERSION FUNCTION
# ============================================================================


def convert_f_to_c(raster_name):
    """
    Convert a temperature raster from Fahrenheit to Celsius

    Args:
        raster_name: Name of raster in geodatabase (currently in °F)

    Returns:
        True if successful, False otherwise
    """
    try:
        print(f"Converting: {raster_name}")

        # Input raster (Fahrenheit)
        input_raster = Raster(raster_name)

        # Formula: (F - 32) * 5/9 = C
        output_raster = (input_raster - 32) * 5.0 / 9.0

        # Create temporary name
        temp_name = f"{raster_name}_TEMP"
        temp_path = arcpy.os.path.join(gdb_path, temp_name)

        # Save the Celsius version with temp name
        output_raster.save(temp_path)
        print(f"  → Created Celsius version")

        # Delete the old Fahrenheit version
        arcpy.management.Delete(raster_name)
        print(f"  → Deleted old °F version")

        # Rename temp version to original name (now that old one is gone)
        arcpy.management.Rename(temp_name, raster_name)
        print(f"  → Renamed to: {raster_name}")

        print(f"  ✓ SUCCESS: {raster_name} now in °C")
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

for raster_name in temp_rasters_f:
    # Check if raster exists
    if arcpy.Exists(raster_name):
        if convert_f_to_c(raster_name):
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
print(f"Total rasters: {len(temp_rasters_f)}")
print(f"  ✓ Converted: {success_count}")
print(f"  ✗ Failed: {fail_count}")
print()

if success_count == len(temp_rasters_f):
    print("🎉 ALL TEMPERATURE RASTERS NOW IN CELSIUS!")
    print()
    print("Next steps:")
    print("  1. Verify temperature values are reasonable (-5°C to +25°C)")
    print("  2. Begin delta calculations (Future - Historical)")
else:
    print("⚠ Some conversions failed. Review errors above.")

print()
print("=" * 70)

# Check in extension
arcpy.CheckInExtension("Spatial")
print("✓ Spatial Analyst extension checked in")
print("\nScript complete.")
