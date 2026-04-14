"""
CGC Climate Change and Hazard Exposure Assessment
Climate Delta Calculations
==========================================================

Purpose: Calculate climate change signals from baseline to future periods
    - Temperature Delta: Future - Historical (in °C)
    - Precipitation % Change: ((Future - Historical) / Historical) × 100

Author: Brandon Boldt
Date: February 2026

Requirements:
    - ArcGIS Pro with Spatial Analyst extension
    - Temperature and precipitation rasters (in correct units)
"""

import arcpy
from arcpy.sa import *
import os

# ============================================================================
# USER PARAMETERS
# ============================================================================

# Geodatabase path
gdb_path = r"C:\Users\Brandon Boldt\OneDrive\Documents\FRCC\CGC_ClimateHazard_Project\CGC_ClimateHazard_Project\CGC_ClimateHazard.gdb"

# Historical baseline rasters
temp_historical = "Temp_Historical_1971_2000"
precip_historical = "Precip_Historical_1971_2000"

# Future period rasters (3 time periods)
future_periods = [
    ("2010_2039", "Temp_Future_2010_2039", "Precip_Future_2010_2039"),
    ("2040_2069", "Temp_Future_2040_2069", "Precip_Future_2040_2069"),
    ("2070_2099", "Temp_Future_2070_2099", "Precip_Future_2070_2099")
]

# ============================================================================
# SETUP
# ============================================================================

print("=" * 70)
print("CGC CLIMATE CHANGE SIGNAL CALCULATIONS")
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
print("Baseline Period: 1971-2000")
print("Future Scenarios: RCP 4.5 (lower emissions)")
print()
print("Calculations:")
print("  Temperature Delta = Future - Historical (°C)")
print("  Precipitation % Change = ((Future - Historical) / Historical) × 100")
print()

# Verify baseline rasters exist
if not arcpy.Exists(temp_historical):
    print(f"ERROR: Temperature baseline not found: {temp_historical}")
    exit()
if not arcpy.Exists(precip_historical):
    print(f"ERROR: Precipitation baseline not found: {precip_historical}")
    exit()

print(f"✓ Baseline rasters found")
print()

# ============================================================================
# CALCULATION FUNCTIONS
# ============================================================================


def calculate_temp_delta(future_temp, historical_temp, period_name):
    """
    Calculate temperature delta (change) from baseline to future

    Args:
        future_temp: Name of future temperature raster
        historical_temp: Name of historical temperature raster
        period_name: Time period label (e.g., "2040_2069")

    Returns:
        Output raster name if successful, None otherwise
    """
    try:
        print(f"  Calculating temperature delta for {period_name}...")

        # Load rasters
        future_ras = Raster(future_temp)
        hist_ras = Raster(historical_temp)

        # Calculate delta: Future - Historical
        delta_ras = future_ras - hist_ras

        # Output name
        output_name = f"Temp_Delta_{period_name}"
        output_path = os.path.join(gdb_path, output_name)

        # Save
        delta_ras.save(output_path)

        print(f"    ✓ SUCCESS: {output_name}")
        print(f"       (Positive values = warming; Negative = cooling)")

        return output_name

    except Exception as e:
        print(f"    ✗ ERROR: {str(e)}")
        print(f"       ArcPy messages: {arcpy.GetMessages()}")
        return None


def calculate_precip_pct_change(future_precip, historical_precip, period_name):
    """
    Calculate precipitation percent change from baseline to future

    Args:
        future_precip: Name of future precipitation raster
        historical_precip: Name of historical precipitation raster
        period_name: Time period label (e.g., "2040_2069")

    Returns:
        Output raster name if successful, None otherwise
    """
    try:
        print(f"  Calculating precipitation % change for {period_name}...")

        # Load rasters
        future_ras = Raster(future_precip)
        hist_ras = Raster(historical_precip)

        # Calculate % change: ((Future - Historical) / Historical) * 100
        pct_change_ras = ((future_ras - hist_ras) / hist_ras) * 100.0

        # Output name
        output_name = f"Precip_PctChange_{period_name}"
        output_path = os.path.join(gdb_path, output_name)

        # Save
        pct_change_ras.save(output_path)

        print(f"    ✓ SUCCESS: {output_name}")
        print(f"       (Positive values = wetter; Negative = drier)")

        return output_name

    except Exception as e:
        print(f"    ✗ ERROR: {str(e)}")
        print(f"       ArcPy messages: {arcpy.GetMessages()}")
        return None

# ============================================================================
# MAIN CALCULATION LOOP
# ============================================================================


print("=" * 70)
print("STARTING DELTA CALCULATIONS")
print("=" * 70)
print()

success_count = 0
fail_count = 0
total_calculations = len(future_periods) * 2  # 2 metrics per period

output_rasters = []

for period_name, temp_future, precip_future in future_periods:
    print(f"--- PERIOD: {period_name} ---")
    print()

    # Verify future rasters exist
    if not arcpy.Exists(temp_future):
        print(f"  ✗ MISSING: {temp_future}")
        fail_count += 2
        print()
        continue
    if not arcpy.Exists(precip_future):
        print(f"  ✗ MISSING: {precip_future}")
        fail_count += 2
        print()
        continue

    # Calculate temperature delta
    temp_output = calculate_temp_delta(temp_future, temp_historical, period_name)
    if temp_output:
        success_count += 1
        output_rasters.append(temp_output)
    else:
        fail_count += 1

    print()

    # Calculate precipitation % change
    precip_output = calculate_precip_pct_change(precip_future, precip_historical, period_name)
    if precip_output:
        success_count += 1
        output_rasters.append(precip_output)
    else:
        fail_count += 1

    print()

# ============================================================================
# SUMMARY REPORT
# ============================================================================

print("=" * 70)
print("CALCULATION COMPLETE")
print("=" * 70)
print(f"Total calculations: {total_calculations}")
print(f"  ✓ Successful: {success_count}")
print(f"  ✗ Failed: {fail_count}")
print()

if success_count == total_calculations:
    print("🎉 ALL CLIMATE CHANGE SIGNALS CALCULATED!")
    print()
    print("Rasters created:")
    for raster in output_rasters:
        print(f"  • {raster}")
    print()
    print("Next steps:")
    print("  1. Examine delta rasters in ArcGIS Pro")
    print("  2. Check value ranges (temp: ±5°C; precip: ±50%)")
    print("  3. Generate histograms and statistics")
    print("  4. Begin reclassification to 1-9 risk scale")
else:
    print("⚠ Some calculations failed. Review errors above.")

print()
print("Output location:", gdb_path)
print("=" * 70)

# Check in extension
arcpy.CheckInExtension("Spatial")
print("✓ Spatial Analyst extension checked in")
print("\nScript complete.")
