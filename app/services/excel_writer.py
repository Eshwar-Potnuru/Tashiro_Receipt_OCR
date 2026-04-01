"""
Excel Writer Service with ETag Concurrency (Phase 9A.3)

This module provides write operations for Excel files stored on OneDrive
using Microsoft Graph API with ETag-based optimistic locking.

Concurrency Model:
    - Every write operation requires a current ETag obtained from getFileMetadata()
    - The ETag is sent via If-Match header to ensure no concurrent modifications
    - If 412 Precondition Failed is returned, an ETagConflictError is raised
    - The conflict_resolver module provides automatic retry with ETag refresh

All operations return the new ETag after successful write for chained operations.

Usage:
    from app.services.excel_writer import append_row, update_cell, ETagConflictError
    from app.services.onedrive_file_manager import get_file_metadata
    
    # Get current ETag before writing
    meta = get_file_metadata(file_id)
    etag = meta['eTag']
    
    # Write with ETag
    try:
        new_etag = append_row(file_id, "Sheet1", ["value1", "value2"], etag)
    except ETagConflictError:
        # Handle conflict - refetch ETag and retry

Author: Phase 9A.3 - Excel Write Operations with ETag Concurrency
Date: 2026-02-28
"""

import logging
from typing import List, Any, Dict, Optional, Tuple
import urllib.parse

from app.services.graph_client import (
    graph_request_with_etag, graph_get, get_user_id, GraphAPIError
)
from app.services.excel_reader import get_last_used_row, get_used_range_address

# Configure logging
logger = logging.getLogger(__name__)


class ETagConflictError(Exception):
    """
    Raised when a write operation fails due to ETag mismatch (412 Precondition Failed).
    
    This indicates the file was modified by another process since the ETag was obtained.
    The caller should re-fetch the current ETag and retry the operation.
    
    Attributes:
        file_id: OneDrive item ID
        worksheet_name: Name of the worksheet being written
        operation: Type of write operation (append, update, delete)
        message: Human-readable error message
    """
    
    def __init__(
        self,
        file_id: str,
        worksheet_name: str,
        operation: str,
        message: str = None
    ):
        self.file_id = file_id
        self.worksheet_name = worksheet_name
        self.operation = operation
        self.message = message or (
            f"ETag conflict on '{worksheet_name}' in {file_id[:20]}... "
            f"during {operation}. Re-fetch and retry."
        )
        super().__init__(self.message)


class ExcelWriteError(Exception):
    """Raised when an Excel write operation fails for non-conflict reasons."""
    
    def __init__(self, operation: str, message: str):
        self.operation = operation
        self.message = f"Excel write error ({operation}): {message}"
        super().__init__(self.message)


def _build_workbook_endpoint(file_id: str) -> str:
    """Build base workbook endpoint for a file."""
    user_id = get_user_id()
    return f"users/{user_id}/drive/items/{file_id}/workbook"


def _encode_worksheet_name(name: str) -> str:
    """URL-encode worksheet name for use in API endpoints."""
    return urllib.parse.quote(name, safe='')


def _handle_etag_error(
    error: GraphAPIError,
    file_id: str,
    worksheet_name: str,
    operation: str
) -> None:
    """
    Check if a GraphAPIError is an ETag conflict and raise appropriate exception.
    
    Raises:
        ETagConflictError: If error is 412 Precondition Failed
        GraphAPIError: Re-raises original error for other cases
    """
    if error.status_code == 412:
        logger.warning(
            f"ETag conflict detected: {operation} on '{worksheet_name}' "
            f"in file {file_id[:20]}..."
        )
        raise ETagConflictError(
            file_id=file_id,
            worksheet_name=worksheet_name,
            operation=operation
        )
    raise error


def append_row(
    file_id: str,
    worksheet_name: str,
    row_data: List[Any],
    etag: str
) -> str:
    """
    Append a single row to the end of used data in a worksheet.
    
    Uses range-based approach: finds last used row and writes to next row.
    
    Args:
        file_id: OneDrive item ID of the Excel file
        worksheet_name: Name of the worksheet
        row_data: Array of cell values in column order
        etag: Current ETag from get_file_metadata() - REQUIRED
        
    Returns:
        str: New ETag after successful write
        
    Raises:
        ETagConflictError: If file was modified (412 Precondition Failed)
        ExcelWriteError: If write operation fails
        
    Example:
        etag = get_file_metadata(file_id)['eTag']
        new_etag = append_row(file_id, "Sheet1", ["2026-01-05", "Vendor", 1500], etag)
    """
    if not etag:
        raise ValueError("etag is required for write operations")
    
    encoded_name = _encode_worksheet_name(worksheet_name)
    
    # Get last used row to determine where to append
    last_row = get_last_used_row(file_id, worksheet_name)
    next_row = last_row + 2  # +1 for 1-indexed, +1 for next row
    
    # If worksheet is empty (last_row = -1), start at row 1
    if last_row < 0:
        next_row = 1
    
    # Calculate range address (e.g., "A5:E5" for 5 columns)
    num_cols = len(row_data)
    end_col = _column_index_to_letter(num_cols - 1)
    range_address = f"A{next_row}:{end_col}{next_row}"
    
    logger.info(f"Appending row to '{worksheet_name}' at {range_address}")
    
    endpoint = (
        f"{_build_workbook_endpoint(file_id)}/worksheets('{encoded_name}')"
        f"/range(address='{range_address}')"
    )
    
    body = {
        "values": [row_data]  # Graph API expects 2D array
    }
    
    try:
        result = graph_request_with_etag("PATCH", endpoint, body=body, etag=etag)
        new_etag = result.get("etag")
        
        logger.info(f"Row appended successfully at row {next_row}")
        return new_etag
        
    except GraphAPIError as e:
        _handle_etag_error(e, file_id, worksheet_name, "append_row")


def update_cell(
    file_id: str,
    worksheet_name: str,
    cell_address: str,
    value: Any,
    etag: str
) -> str:
    """
    Update a single cell value.
    
    Args:
        file_id: OneDrive item ID of the Excel file
        worksheet_name: Name of the worksheet
        cell_address: Cell address in A1 notation (e.g., 'B5')
        value: New cell value (string, number, boolean, or None)
        etag: Current ETag - REQUIRED
        
    Returns:
        str: New ETag after successful write
        
    Raises:
        ETagConflictError: If file was modified since ETag was obtained
        ExcelWriteError: If write operation fails
        
    Example:
        new_etag = update_cell(file_id, "Sheet1", "B5", 1500, etag)
    """
    if not etag:
        raise ValueError("etag is required for write operations")
    
    encoded_name = _encode_worksheet_name(worksheet_name)
    
    logger.info(f"Updating cell {cell_address} in '{worksheet_name}'")
    
    endpoint = (
        f"{_build_workbook_endpoint(file_id)}/worksheets('{encoded_name}')"
        f"/range(address='{cell_address}')"
    )
    
    body = {
        "values": [[value]]  # Single cell as 2D array
    }
    
    try:
        result = graph_request_with_etag("PATCH", endpoint, body=body, etag=etag)
        new_etag = result.get("etag")
        
        logger.info(f"Cell {cell_address} updated successfully")
        return new_etag
        
    except GraphAPIError as e:
        _handle_etag_error(e, file_id, worksheet_name, "update_cell")


def update_row(
    file_id: str,
    worksheet_name: str,
    row_index: int,
    row_data: List[Any],
    etag: str
) -> str:
    """
    Update an entire row by 0-based index.
    
    Args:
        file_id: OneDrive item ID of the Excel file
        worksheet_name: Name of the worksheet
        row_index: 0-based row number (0 = first row)
        row_data: Array of cell values
        etag: Current ETag - REQUIRED
        
    Returns:
        str: New ETag after successful write
        
    Raises:
        ETagConflictError: If file was modified since ETag was obtained
        ExcelWriteError: If write operation fails
        
    Example:
        new_etag = update_row(file_id, "Sheet1", 5, ["A", "B", "C", 100], etag)
    """
    if not etag:
        raise ValueError("etag is required for write operations")
    
    encoded_name = _encode_worksheet_name(worksheet_name)
    excel_row = row_index + 1  # Convert to 1-indexed
    
    # Calculate range
    num_cols = len(row_data)
    end_col = _column_index_to_letter(num_cols - 1)
    range_address = f"A{excel_row}:{end_col}{excel_row}"
    
    logger.info(f"Updating row {row_index} in '{worksheet_name}' (range: {range_address})")
    
    endpoint = (
        f"{_build_workbook_endpoint(file_id)}/worksheets('{encoded_name}')"
        f"/range(address='{range_address}')"
    )
    
    body = {
        "values": [row_data]
    }
    
    try:
        result = graph_request_with_etag("PATCH", endpoint, body=body, etag=etag)
        new_etag = result.get("etag")
        
        logger.info(f"Row {row_index} updated successfully")
        return new_etag
        
    except GraphAPIError as e:
        _handle_etag_error(e, file_id, worksheet_name, "update_row")


def update_range(
    file_id: str,
    worksheet_name: str,
    range_address: str,
    values: List[List[Any]],
    etag: str
) -> str:
    """
    Update a range of cells.
    
    Args:
        file_id: OneDrive item ID of the Excel file
        worksheet_name: Name of the worksheet
        range_address: Range in A1 notation (e.g., "A1:C5")
        values: 2D array of values matching range dimensions
        etag: Current ETag - REQUIRED
        
    Returns:
        str: New ETag after successful write
        
    Raises:
        ETagConflictError: If file was modified since ETag was obtained
        ExcelWriteError: If write operation fails
        
    Example:
        values = [["A", "B"], ["C", "D"]]
        new_etag = update_range(file_id, "Sheet1", "A1:B2", values, etag)
    """
    if not etag:
        raise ValueError("etag is required for write operations")
    
    encoded_name = _encode_worksheet_name(worksheet_name)
    
    logger.info(f"Updating range {range_address} in '{worksheet_name}'")
    
    endpoint = (
        f"{_build_workbook_endpoint(file_id)}/worksheets('{encoded_name}')"
        f"/range(address='{range_address}')"
    )
    
    body = {
        "values": values
    }
    
    try:
        result = graph_request_with_etag("PATCH", endpoint, body=body, etag=etag)
        new_etag = result.get("etag")
        
        logger.info(f"Range {range_address} updated successfully")
        return new_etag
        
    except GraphAPIError as e:
        _handle_etag_error(e, file_id, worksheet_name, "update_range")


def delete_row(
    file_id: str,
    worksheet_name: str,
    row_index: int,
    etag: str
) -> str:
    """
    Delete a row by 0-based index.
    
    Note: This uses the Graph API range delete operation which shifts
    cells up to fill the deleted row.
    
    Args:
        file_id: OneDrive item ID of the Excel file
        worksheet_name: Name of the worksheet
        row_index: 0-based row number to delete
        etag: Current ETag - REQUIRED
        
    Returns:
        str: New ETag after successful delete
        
    Raises:
        ETagConflictError: If file was modified since ETag was obtained
        ExcelWriteError: If delete operation fails
        
    Example:
        new_etag = delete_row(file_id, "Sheet1", 5, etag)
    """
    if not etag:
        raise ValueError("etag is required for write operations")
    
    encoded_name = _encode_worksheet_name(worksheet_name)
    excel_row = row_index + 1  # Convert to 1-indexed
    
    logger.info(f"Deleting row {row_index} from '{worksheet_name}'")
    
    # Get the used range to determine row width
    range_addr = get_used_range_address(file_id, worksheet_name)
    if range_addr and ":" in range_addr:
        end_col = range_addr.split(":")[1].rstrip("0123456789")
    else:
        end_col = "Z"  # Default to wide range
    
    row_range = f"A{excel_row}:{end_col}{excel_row}"
    
    endpoint = (
        f"{_build_workbook_endpoint(file_id)}/worksheets('{encoded_name}')"
        f"/range(address='{row_range}')/delete"
    )
    
    body = {
        "shift": "Up"  # Shift cells up to fill deleted row
    }
    
    try:
        result = graph_request_with_etag("POST", endpoint, body=body, etag=etag)
        new_etag = result.get("etag")
        
        logger.info(f"Row {row_index} deleted successfully")
        return new_etag
        
    except GraphAPIError as e:
        _handle_etag_error(e, file_id, worksheet_name, "delete_row")


def batch_append_rows(
    file_id: str,
    worksheet_name: str,
    rows_data: List[List[Any]],
    etag: str
) -> Tuple[int, str]:
    """
    Append multiple rows in a single or batched API call.
    
    For efficiency, this writes all rows in a single range update when possible.
    
    Args:
        file_id: OneDrive item ID of the Excel file
        worksheet_name: Name of the worksheet
        rows_data: List of row arrays to append
        etag: Current ETag - REQUIRED
        
    Returns:
        Tuple[int, str]: (count of rows written, new ETag)
        
    Raises:
        ETagConflictError: If file was modified since ETag was obtained
        ExcelWriteError: If write operation fails
        
    Example:
        rows = [
            ["2026-01-05", "Vendor A", 1000],
            ["2026-01-06", "Vendor B", 2000],
        ]
        count, new_etag = batch_append_rows(file_id, "Sheet1", rows, etag)
    """
    if not etag:
        raise ValueError("etag is required for write operations")
    
    if not rows_data:
        return (0, etag)
    
    encoded_name = _encode_worksheet_name(worksheet_name)
    
    # Get last used row
    last_row = get_last_used_row(file_id, worksheet_name)
    next_row = last_row + 2 if last_row >= 0 else 1
    
    # Calculate range for all rows
    num_rows = len(rows_data)
    num_cols = max(len(row) for row in rows_data)
    end_row = next_row + num_rows - 1
    end_col = _column_index_to_letter(num_cols - 1)
    range_address = f"A{next_row}:{end_col}{end_row}"
    
    logger.info(
        f"Batch appending {num_rows} rows to '{worksheet_name}' at {range_address}"
    )
    
    # Normalize row lengths (pad shorter rows with None)
    normalized_rows = []
    for row in rows_data:
        normalized_row = list(row)
        while len(normalized_row) < num_cols:
            normalized_row.append(None)
        normalized_rows.append(normalized_row)
    
    endpoint = (
        f"{_build_workbook_endpoint(file_id)}/worksheets('{encoded_name}')"
        f"/range(address='{range_address}')"
    )
    
    body = {
        "values": normalized_rows
    }
    
    try:
        result = graph_request_with_etag("PATCH", endpoint, body=body, etag=etag)
        new_etag = result.get("etag")
        
        logger.info(f"Batch append completed: {num_rows} rows written")
        return (num_rows, new_etag)
        
    except GraphAPIError as e:
        _handle_etag_error(e, file_id, worksheet_name, "batch_append_rows")


def clear_range(
    file_id: str,
    worksheet_name: str,
    range_address: str,
    etag: str
) -> str:
    """
    Clear values in a range (keeps formatting).
    
    Args:
        file_id: OneDrive item ID of the Excel file
        worksheet_name: Name of the worksheet
        range_address: Range to clear in A1 notation
        etag: Current ETag - REQUIRED
        
    Returns:
        str: New ETag after successful clear
        
    Example:
        new_etag = clear_range(file_id, "Sheet1", "A2:E100", etag)
    """
    if not etag:
        raise ValueError("etag is required for write operations")
    
    encoded_name = _encode_worksheet_name(worksheet_name)
    
    logger.info(f"Clearing range {range_address} in '{worksheet_name}'")
    
    endpoint = (
        f"{_build_workbook_endpoint(file_id)}/worksheets('{encoded_name}')"
        f"/range(address='{range_address}')/clear"
    )
    
    body = {
        "applyTo": "Contents"  # Clear values only, keep formatting
    }
    
    try:
        result = graph_request_with_etag("POST", endpoint, body=body, etag=etag)
        new_etag = result.get("etag")
        
        logger.info(f"Range {range_address} cleared successfully")
        return new_etag
        
    except GraphAPIError as e:
        _handle_etag_error(e, file_id, worksheet_name, "clear_range")


def _column_index_to_letter(index: int) -> str:
    """
    Convert 0-based column index to Excel column letter.
    
    Args:
        index: 0-based column index (0 = A, 25 = Z, 26 = AA)
        
    Returns:
        Excel column letter(s)
        
    Examples:
        0 -> 'A', 25 -> 'Z', 26 -> 'AA', 27 -> 'AB'
    """
    result = ""
    index += 1  # Convert to 1-based
    
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    
    return result


def _letter_to_column_index(letter: str) -> int:
    """
    Convert Excel column letter to 0-based index.
    
    Args:
        letter: Excel column letter(s) (e.g., 'A', 'AA')
        
    Returns:
        0-based column index
    """
    result = 0
    for char in letter.upper():
        result = result * 26 + (ord(char) - ord('A') + 1)
    return result - 1
