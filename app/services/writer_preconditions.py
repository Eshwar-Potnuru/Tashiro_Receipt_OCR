"""
Graph Writer Precondition Validators (Phase 11A-1)

This module provides shared precondition checks for Format①/② Graph writers.
Centralizes input validation to ensure consistent behavior and clear error messages.

Usage:
    from app.services.writer_preconditions import (
        validate_year_month,
        validate_required_fields,
        PreconditionError,
    )

Author: Phase 11A-1 - Graph Writer Operational Completion
Date: 2026
"""

from __future__ import annotations

import os
import logging
from typing import Any, Dict, List, Optional


# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

# STRICT_SHEET_MODE controls whether writers fail or fallback when month sheet missing
# Default: False (legacy fallback behavior preserved for backward compatibility)
# Set to "true" in environment to require month sheet to exist before writing
STRICT_SHEET_MODE = os.environ.get("GRAPH_WRITER_STRICT_SHEET_MODE", "false").lower() == "true"


# =============================================================================
# EXCEPTIONS
# =============================================================================

class PreconditionError(Exception):
    """
    Base exception for precondition validation failures.
    
    Attributes:
        error_code: Machine-readable error code for programmatic handling
        field: Field that failed validation (if applicable)
        message: Human-readable error message
    """
    
    def __init__(self, error_code: str, message: str, field: Optional[str] = None):
        self.error_code = error_code
        self.field = field
        self.message = message
        super().__init__(f"[{error_code}] {message}")


class InvalidYearMonthError(PreconditionError):
    """Raised when year or month values are invalid."""
    
    def __init__(self, year: Any, month: Any, reason: str):
        super().__init__(
            error_code="INVALID_YEAR_MONTH",
            message=f"Invalid year/month: year={year}, month={month} - {reason}",
            field="year_month"
        )
        self.year = year
        self.month = month


class MissingRequiredFieldError(PreconditionError):
    """Raised when a required field is missing or empty."""
    
    def __init__(self, field_name: str, format_type: str = ""):
        format_prefix = f"Format{format_type} " if format_type else ""
        super().__init__(
            error_code="MISSING_REQUIRED_FIELD",
            message=f"{format_prefix}requires field '{field_name}'",
            field=field_name
        )


class SheetNotFoundStrictError(PreconditionError):
    """Raised in STRICT_SHEET_MODE when target month sheet doesn't exist."""
    
    def __init__(self, target_sheet: str, available_sheets: List[str], format_type: str = ""):
        format_prefix = f"Format{format_type}" if format_type else "Writer"
        super().__init__(
            error_code="STRICT_SHEET_NOT_FOUND",
            message=(
                f"{format_prefix}: Target month sheet '{target_sheet}' not found. "
                f"Available: {available_sheets}. "
                f"Create the sheet in OneDrive before retrying, or set "
                f"GRAPH_WRITER_STRICT_SHEET_MODE=false to allow fallback."
            ),
            field="worksheet"
        )
        self.target_sheet = target_sheet
        self.available_sheets = available_sheets


# =============================================================================
# VALIDATORS
# =============================================================================

def validate_year_month(year: Any, month: Any) -> tuple:
    """
    Validate and normalize year/month values.
    
    Args:
        year: Year value (should be int between 2020-2100)
        month: Month value (should be int between 1-12)
        
    Returns:
        tuple: (validated_year, validated_month) as integers
        
    Raises:
        InvalidYearMonthError: If values are invalid
    """
    # Check types
    if year is None:
        raise InvalidYearMonthError(year, month, "year cannot be None")
    if month is None:
        raise InvalidYearMonthError(year, month, "month cannot be None")
    
    # Convert to int if possible
    try:
        year_int = int(year)
    except (TypeError, ValueError):
        raise InvalidYearMonthError(year, month, f"year must be numeric, got {type(year).__name__}")
    
    try:
        month_int = int(month)
    except (TypeError, ValueError):
        raise InvalidYearMonthError(year, month, f"month must be numeric, got {type(month).__name__}")
    
    # Range checks
    if year_int < 2020 or year_int > 2100:
        raise InvalidYearMonthError(year, month, f"year must be between 2020-2100, got {year_int}")
    
    if month_int < 1 or month_int > 12:
        raise InvalidYearMonthError(year, month, f"month must be between 1-12, got {month_int}")
    
    return (year_int, month_int)


def validate_required_fields(
    receipt_data: Dict[str, Any],
    required_fields: List[str],
    format_type: str = ""
) -> Dict[str, Any]:
    """
    Validate that required fields are present and non-empty in receipt data.
    
    Args:
        receipt_data: Receipt data dictionary
        required_fields: List of required field names
        format_type: Format identifier for error messages ("①" or "②")
        
    Returns:
        Dict containing extracted/validated values
        
    Raises:
        MissingRequiredFieldError: If any required field is missing/empty
    """
    result = {}
    
    for field in required_fields:
        value = receipt_data.get(field)
        
        # Check for None or empty string
        if value is None or (isinstance(value, str) and value.strip() == ""):
            raise MissingRequiredFieldError(field, format_type)
        
        result[field] = value
    
    return result


def should_fail_on_missing_sheet() -> bool:
    """
    Check if writer should fail when month sheet is missing.
    
    Returns:
        bool: True if STRICT_SHEET_MODE is enabled
    """
    return STRICT_SHEET_MODE


def check_sheet_exists_or_fail(
    target_sheet: str,
    available_sheets: List[str],
    format_type: str = ""
) -> None:
    """
    Check if target sheet exists, raising error if in STRICT mode.
    
    This should be called before falling back to template sheet.
    
    Args:
        target_sheet: Expected sheet name
        available_sheets: List of sheets in workbook
        format_type: Format identifier for error messages
        
    Raises:
        SheetNotFoundStrictError: If STRICT mode enabled and sheet not found
    """
    if STRICT_SHEET_MODE:
        raise SheetNotFoundStrictError(target_sheet, available_sheets, format_type)
    
    # In non-strict mode, just log a warning (caller handles fallback)
    logger.warning(
        f"SHEET FALLBACK (STRICT_MODE=off): Target sheet '{target_sheet}' not found. "
        f"Available: {available_sheets}. Writer will fall back to template sheet."
    )


def build_skip_result(
    error_code: str,
    reason: str,
    receipt_data: Dict[str, Any],
    identifier_field: str = "receipt_id"
) -> Dict[str, Any]:
    """
    Build a standardized skip result dictionary.
    
    Args:
        error_code: Machine-readable status code (e.g., "skipped_missing_staff_id")
        reason: Human-readable reason
        receipt_data: Original receipt data
        identifier_field: Field to include as identifier
        
    Returns:
        dict: Standardized skip result
    """
    return {
        "status": error_code,
        "reason": reason,
        identifier_field: str(receipt_data.get(identifier_field, "")),
    }


def build_error_result(
    error: Exception,
    identifier_value: Any,
    identifier_key: str = "staff"
) -> Dict[str, Any]:
    """
    Build a standardized error result dictionary.
    
    Args:
        error: Exception that occurred
        identifier_value: Primary identifier (staff_id or location_id)
        identifier_key: Key name for identifier
        
    Returns:
        dict: Standardized error result
    """
    error_code = getattr(error, "error_code", "UNKNOWN_ERROR")
    
    return {
        "status": "error",
        "error_code": error_code,
        "error": str(error),
        identifier_key: identifier_value,
    }
