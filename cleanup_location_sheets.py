#!/usr/bin/env python3
"""
Cleanup script to reset all location accumulation workbooks to fresh state.

This script:
1. Backs up existing location workbooks
2. Deletes all current location workbooks
3. Recreates them from the clean template

Use this to start fresh with the corrected insertion logic.
"""

import sys
from pathlib import Path
from datetime import datetime
import shutil

# Add project to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.excel.excel_template_loader import ExcelTemplateLoader
from app.services.config_service import ConfigService


def main():
    print("=" * 70)
    print("LOCATION SHEETS CLEANUP UTILITY")
    print("=" * 70)
    print("\nThis will:")
    print("  1. Backup all existing location workbooks")
    print("  2. Delete all location workbooks")
    print("  3. Recreate fresh workbooks from templates")
    print("\n⚠️  WARNING: All current data in location sheets will be archived!")
    print("=" * 70)
    
    response = input("\nProceed with cleanup? (yes/no): ").strip().lower()
    if response != "yes":
        print("Cleanup cancelled.")
        return
    
    # Initialize services
    template_loader = ExcelTemplateLoader()
    config_service = ConfigService()
    
    # Get all locations
    locations = config_service.get_locations()
    
    if not locations:
        print("\n✗ No locations found in configuration!")
        return
    
    print(f"\nFound {len(locations)} locations")
    
    # Create backup directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = template_loader.location_dir.parent / f"backup_locations_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\nBackup directory: {backup_dir}")
    
    # Process each location
    backed_up = 0
    deleted = 0
    created = 0
    
    for loc_id in locations:
        print(f"\nProcessing: {loc_id}")
        
        workbook_path = template_loader.location_dir / f"{loc_id}_Accumulated.xlsx"
        
        # Backup if exists
        if workbook_path.exists():
            backup_path = backup_dir / workbook_path.name
            shutil.copy2(workbook_path, backup_path)
            print(f"  ✓ Backed up to: {backup_path.name}")
            backed_up += 1
            
            # Delete original
            try:
                workbook_path.unlink()
                print(f"  ✓ Deleted: {workbook_path.name}")
                deleted += 1
            except PermissionError:
                print(f"  ✗ Cannot delete - file may be open in Excel!")
                print(f"    Please close {workbook_path.name} and run cleanup again")
                continue
        else:
            print(f"  - No existing workbook")
        
        # Recreate from template
        try:
            new_path = template_loader.ensure_location_workbook(loc_id)
            print(f"  ✓ Created fresh: {new_path.name}")
            created += 1
        except Exception as e:
            print(f"  ✗ Failed to create: {e}")
    
    print("\n" + "=" * 70)
    print("CLEANUP SUMMARY")
    print("=" * 70)
    print(f"  Backed up: {backed_up} workbooks")
    print(f"  Deleted:   {deleted} workbooks")
    print(f"  Created:   {created} fresh workbooks")
    print(f"\nBackup location: {backup_dir}")
    print("\n✓ Cleanup complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
