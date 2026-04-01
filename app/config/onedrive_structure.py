"""
OneDrive Folder Structure Configuration (Phase 9.R.1)

This module defines the OneDrive folder path patterns for the
receipt OCR system's Excel file storage.

The structure parallels the local file system:
    Local:    app/Data/accumulation/staff/{STAFF_NAME}_{LOCATION}.xlsx
    OneDrive: {BASE_FOLDER}/staff/{STAFF_NAME}_{LOCATION}.xlsx

All paths are relative to ONEDRIVE_BASE_FOLDER environment variable.

Usage:
    from app.config.onedrive_structure import (
        get_staff_folder_path,
        get_staff_file_path,
        get_location_folder_path,
        get_location_file_path,
        FORMAT1_TEMPLATE_NAME,
        FORMAT2_TEMPLATE_NAME,
    )
    
    # Get staff file path
    path = get_staff_file_path("田中太郎", "Aichi")
    # Returns: "staff/田中太郎_Aichi.xlsx"
    
    # Get location file path
    path = get_location_file_path("Aichi")
    # Returns: "locations/Aichi_Accumulated.xlsx"

Author: Phase 9.R.1 - Format① Writer Migration
Date: 2026-02-28
"""

import re
from typing import Optional


# =============================================================================
# FOLDER STRUCTURE CONSTANTS
# =============================================================================

# Staff ledger folder (Format 01 - Individual Staff Ledgers)
STAFF_FOLDER = "staff"

# Location ledger folder (Format 02 - Branch/Location Ledgers)  
LOCATION_FOLDER = "locations"

# HQ Master Ledger folder (Phase 13 - HQ consolidated ledger)
HQ_FOLDER = "hq"
HQ_MASTER_LEDGER_NAME = "HQ_Master_Ledger.xlsx"
HQ_TEMPLATE_NAME = "HQ_Master_Template.xlsx"

# Template file names (base templates stored in OneDrive)
FORMAT1_TEMPLATE_NAME = "各個人集計用　_2024.xlsx"
FORMAT2_TEMPLATE_NAME = "事業所集計テーブル.xlsx"

# Artifact folder for copies
ARTIFACT_FOLDER = "artifacts"


# =============================================================================
# FILENAME UTILITIES
# =============================================================================

def _safe_filename(name: str) -> str:
    """
    Convert a string to a safe filename component.
    
    Removes or replaces characters that are invalid in OneDrive filenames:
    - / \\ : * ? " < > |
    - Leading/trailing spaces and dots
    
    Args:
        name: Raw string to convert
        
    Returns:
        Safe filename string
    """
    if not name:
        return "unknown"
    
    # Replace invalid characters with underscores
    safe = re.sub(r'[/\\:*?"<>|]', '_', name)
    
    # Remove leading/trailing whitespace and dots
    safe = safe.strip().strip('.')
    
    # Collapse multiple underscores
    safe = re.sub(r'_+', '_', safe)
    
    # Ensure non-empty
    return safe if safe else "unknown"


# =============================================================================
# STAFF LEDGER PATHS (FORMAT 01)
# =============================================================================

def get_staff_folder_path() -> str:
    """
    Get the relative path to the staff ledger folder.
    
    Returns:
        Relative path: "staff"
    """
    return STAFF_FOLDER


def get_staff_file_path(staff_name: str, location_id: str) -> str:
    """
    Get the relative path for a staff ledger file.
    
    Matches the local naming convention: {STAFF_NAME}_{LOCATION}.xlsx
    
    Args:
        staff_name: Staff member's display name
        location_id: Business location identifier
        
    Returns:
        Relative path, e.g., "staff/田中太郎_Aichi.xlsx"
    """
    safe_staff = _safe_filename(staff_name)
    safe_location = _safe_filename(location_id)
    return f"{STAFF_FOLDER}/{safe_staff}_{safe_location}.xlsx"


def get_staff_file_name(staff_name: str, location_id: str) -> str:
    """
    Get just the filename for a staff ledger file (no folder).
    
    Args:
        staff_name: Staff member's display name
        location_id: Business location identifier
        
    Returns:
        Filename, e.g., "田中太郎_Aichi.xlsx"
    """
    safe_staff = _safe_filename(staff_name)
    safe_location = _safe_filename(location_id)
    return f"{safe_staff}_{safe_location}.xlsx"


# =============================================================================
# LOCATION LEDGER PATHS (FORMAT 02)
# =============================================================================

def get_location_folder_path() -> str:
    """
    Get the relative path to the location ledger folder.
    
    Returns:
        Relative path: "locations"
    """
    return LOCATION_FOLDER


def get_location_file_path(location_id: str) -> str:
    """
    Get the relative path for a location ledger file.
    
    Matches the local naming convention: {LOCATION}_Accumulated.xlsx
    
    Args:
        location_id: Business location identifier
        
    Returns:
        Relative path, e.g., "locations/Aichi_Accumulated.xlsx"
    """
    safe_location = _safe_filename(location_id)
    return f"{LOCATION_FOLDER}/{safe_location}_Accumulated.xlsx"


def get_location_file_name(location_id: str) -> str:
    """
    Get just the filename for a location ledger file (no folder).
    
    Args:
        location_id: Business location identifier
        
    Returns:
        Filename, e.g., "Aichi_Accumulated.xlsx"
    """
    safe_location = _safe_filename(location_id)
    return f"{safe_location}_Accumulated.xlsx"


# =============================================================================
# TEMPLATE PATHS
# =============================================================================

def get_template_folder_path() -> str:
    """
    Get the relative path to the templates folder.
    
    Returns:
        Relative path: "templates"
    """
    return "templates"


def get_format1_template_path() -> str:
    """
    Get the relative path to the Format 01 (staff) template.
    
    Returns:
        Relative path, e.g., "templates/各個人集計用　_2024.xlsx"
    """
    return f"templates/{FORMAT1_TEMPLATE_NAME}"


def get_format2_template_path() -> str:
    """
    Get the relative path to the Format 02 (location) template.
    
    Returns:
        Relative path, e.g., "templates/事業所集計テーブル.xlsx"
    """
    return f"templates/{FORMAT2_TEMPLATE_NAME}"


# =============================================================================
# WORKSHEET NAMING
# =============================================================================

def get_month_sheet_name(year: int, month: int) -> str:
    """
    Get the worksheet name for a specific year/month (Format①).
    
    Matches the existing convention: "YYYYMM"
    
    Args:
        year: 4-digit year (e.g., 2026)
        month: Month number (1-12)
        
    Returns:
        Sheet name, e.g., "202602"
    """
    return f"{year}{month:02d}"


def get_format2_month_sheet_name(year: int, month: int) -> str:
    """
    Get the worksheet name for a specific year/month (Format②).
    
    Matches the Format② convention: "YYYY年M月"
    
    Args:
        year: 4-digit year (e.g., 2026)
        month: Month number (1-12)
        
    Returns:
        Sheet name, e.g., "2026年3月"
    """
    return f"{year}年{month}月"


def get_template_sheet_name() -> str:
    """
    Get the name of the template/source sheet.
    
    The staff template uses "原本" as the source sheet for copying.
    
    Returns:
        Template sheet name: "原本"
    """
    return "原本"


# =============================================================================
# HQ MASTER LEDGER PATHS (PHASE 13)
# =============================================================================

def get_hq_folder_path() -> str:
    """
    Get the relative path to the HQ master ledger folder.
    
    Returns:
        Relative path: "hq"
    """
    return HQ_FOLDER


def get_hq_master_ledger_path() -> str:
    """
    Get the relative path for the HQ Master Ledger file.
    
    Returns:
        Relative path, e.g., "hq/HQ_Master_Ledger.xlsx"
    """
    return f"{HQ_FOLDER}/{HQ_MASTER_LEDGER_NAME}"


def get_hq_template_path() -> str:
    """
    Get the relative path to the HQ Master Ledger template.
    
    Returns:
        Relative path, e.g., "templates/HQ_Master_Template.xlsx"
    """
    return f"templates/{HQ_TEMPLATE_NAME}"


def get_hq_month_sheet_name(year: int, month: int) -> str:
    """
    Get the worksheet name for a specific year/month in HQ Master Ledger.
    
    Uses same convention as Format②: "YYYY年M月"
    
    Args:
        year: 4-digit year (e.g., 2026)
        month: Month number (1-12)
        
    Returns:
        Sheet name, e.g., "2026年3月"
    """
    return f"{year}年{month}月"
