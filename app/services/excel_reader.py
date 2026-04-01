"""
Excel Worksheet Reader Service (Phase 9A.2)

This module provides read-only operations for Excel files stored on OneDrive
using the Microsoft Graph API Excel workbook endpoints.

Features:
    - List worksheet names
    - Read entire worksheets
    - Read worksheets as objects (with header mapping)
    - Read specific rows and cells
    - Get last used row index

All operations are read-only. Write operations are in Phase 9A.3.

Usage:
    from app.services.excel_reader import (
        get_worksheet_names, read_worksheet, read_worksheet_as_objects
    )
    
    # Get worksheets
    sheets = get_worksheet_names(file_id)
    
    # Read data
    rows = read_worksheet(file_id, "Sheet1")
    objects = read_worksheet_as_objects(file_id, "Sheet1")

Author: Phase 9A.2 - Excel Read Operations & OneDrive File Management
Date: 2026-02-28
"""

import logging
from typing import List, Dict, Any, Optional, Union

from app.services.graph_client import (
    graph_get, get_user_id, GraphAPIError
)

# Configure logging
logger = logging.getLogger(__name__)


class WorksheetNotFoundError(Exception):
    """Raised when a worksheet is not found in the Excel file."""
    
    def __init__(self, worksheet_name: str, file_id: str):
        self.worksheet_name = worksheet_name
        self.file_id = file_id
        self.message = f"Worksheet '{worksheet_name}' not found in file {file_id}"
        super().__init__(self.message)


class ExcelReadError(Exception):
    """Raised when an Excel read operation fails."""
    
    def __init__(self, operation: str, message: str):
        self.operation = operation
        self.message = f"Excel read error ({operation}): {message}"
        super().__init__(self.message)


def _build_workbook_endpoint(file_id: str) -> str:
    """
    Build base workbook endpoint for a file.
    
    Args:
        file_id: OneDrive item ID
        
    Returns:
        Graph API endpoint for workbook operations
    """
    user_id = get_user_id()
    return f"users/{user_id}/drive/items/{file_id}/workbook"


def _encode_worksheet_name(name: str) -> str:
    """
    Encode worksheet name for use in URL.
    
    Handles special characters that need URL encoding.
    
    Args:
        name: Worksheet name
        
    Returns:
        URL-encoded worksheet name
    """
    # Graph API accepts worksheet names with single quotes escaped
    # and wrapped in single quotes for names with special chars
    import urllib.parse
    return urllib.parse.quote(name, safe='')


def get_worksheet_names(file_id: str) -> List[str]:
    """
    Get all worksheet names in an Excel file.
    
    Args:
        file_id: OneDrive item ID of the Excel file
        
    Returns:
        list: Array of worksheet names
        
    Raises:
        ExcelReadError: If operation fails
        
    Example:
        sheets = get_worksheet_names(file_id)
        # ['Sheet1', 'Summary', 'Data']
    """
    endpoint = f"{_build_workbook_endpoint(file_id)}/worksheets"
    
    try:
        result = graph_get(endpoint)
        worksheets = result.get("value", [])
        
        names = [ws.get("name") for ws in worksheets if ws.get("name")]
        logger.debug(f"Found {len(names)} worksheets in file {file_id[:8]}...")
        
        return names
        
    except GraphAPIError as e:
        raise ExcelReadError(
            "get_worksheet_names",
            f"Failed to get worksheets: {e.message}"
        )


def read_worksheet(
    file_id: str,
    worksheet_name: str,
    include_empty_rows: bool = False
) -> List[List[Any]]:
    """
    Read all used rows from a worksheet.
    
    Returns raw cell values as a 2D array (list of rows, each row is list of cells).
    
    Args:
        file_id: OneDrive item ID of the Excel file
        worksheet_name: Name of the worksheet to read
        include_empty_rows: If False, filters out completely empty rows
        
    Returns:
        list: Array of row arrays with cell values
        
    Raises:
        WorksheetNotFoundError: If worksheet doesn't exist
        ExcelReadError: If read operation fails
        
    Example:
        rows = read_worksheet(file_id, "Sheet1")
        # [['Date', 'Vendor', 'Amount'], ['2026-01-05', 'Store A', 1500], ...]
    """
    encoded_name = _encode_worksheet_name(worksheet_name)
    endpoint = f"{_build_workbook_endpoint(file_id)}/worksheets('{encoded_name}')/usedRange"
    
    try:
        result = graph_get(endpoint)
        
        values = result.get("values", [])
        
        if not include_empty_rows:
            # Filter out rows where all cells are None or empty string
            values = [
                row for row in values
                if any(cell is not None and cell != "" for cell in row)
            ]
        
        logger.debug(f"Read {len(values)} rows from worksheet '{worksheet_name}'")
        return values
        
    except GraphAPIError as e:
        if e.status_code == 404 or e.error_code == "ItemNotFound":
            raise WorksheetNotFoundError(worksheet_name, file_id)
        raise ExcelReadError(
            "read_worksheet",
            f"Failed to read worksheet '{worksheet_name}': {e.message}"
        )


def read_worksheet_as_objects(
    file_id: str,
    worksheet_name: str,
    header_row: int = 0,
    skip_empty_rows: bool = True
) -> List[Dict[str, Any]]:
    """
    Read worksheet and map rows to objects using header row as keys.
    
    This is useful for reading structured data where the first row contains
    column headers.
    
    Args:
        file_id: OneDrive item ID of the Excel file
        worksheet_name: Name of the worksheet to read
        header_row: 0-indexed row number containing headers (default 0 = first row)
        skip_empty_rows: If True, skips rows where all values are empty
        
    Returns:
        list: Array of dicts, each dict represents a row with header keys
        
    Raises:
        WorksheetNotFoundError: If worksheet doesn't exist
        ExcelReadError: If read operation fails
        
    Example:
        data = read_worksheet_as_objects(file_id, "Sheet1")
        # [
        #     {'Date': '2026-01-05', 'Vendor': 'Store A', 'Amount': 1500},
        #     {'Date': '2026-01-06', 'Vendor': 'Store B', 'Amount': 2300},
        # ]
    """
    rows = read_worksheet(file_id, worksheet_name, include_empty_rows=True)
    
    if not rows:
        return []
    
    if header_row >= len(rows):
        raise ExcelReadError(
            "read_worksheet_as_objects",
            f"Header row {header_row} exceeds available rows ({len(rows)})"
        )
    
    # Extract headers
    headers = rows[header_row]
    
    # Convert headers to strings and clean them
    headers = [
        str(h).strip() if h is not None else f"Column_{i}"
        for i, h in enumerate(headers)
    ]
    
    objects = []
    
    # Process data rows (skip header row)
    for row_idx, row in enumerate(rows):
        if row_idx <= header_row:
            continue
        
        # Check if row is empty
        if skip_empty_rows:
            if all(cell is None or cell == "" for cell in row):
                continue
        
        # Build object from row
        obj = {}
        for col_idx, header in enumerate(headers):
            if col_idx < len(row):
                obj[header] = row[col_idx]
            else:
                obj[header] = None
        
        objects.append(obj)
    
    logger.debug(
        f"Converted {len(objects)} rows to objects from worksheet '{worksheet_name}'"
    )
    return objects


def read_row(
    file_id: str,
    worksheet_name: str,
    row_index: int
) -> List[Any]:
    """
    Read a single row by 0-indexed row number.
    
    Args:
        file_id: OneDrive item ID of the Excel file
        worksheet_name: Name of the worksheet
        row_index: 0-indexed row number (0 = first row)
        
    Returns:
        list: Array of cell values for the row
        
    Raises:
        ExcelReadError: If row index is out of range or operation fails
        
    Example:
        header = read_row(file_id, "Sheet1", 0)  # First row
        data_row = read_row(file_id, "Sheet1", 5)  # Sixth row
    """
    # Excel rows are 1-indexed
    excel_row = row_index + 1
    
    encoded_name = _encode_worksheet_name(worksheet_name)
    # Read entire row using range notation
    endpoint = (
        f"{_build_workbook_endpoint(file_id)}/worksheets('{encoded_name}')"
        f"/range(address='{excel_row}:{excel_row}')"
    )
    
    try:
        result = graph_get(endpoint)
        values = result.get("values", [[]])
        
        if values and len(values) > 0:
            return values[0]
        return []
        
    except GraphAPIError as e:
        raise ExcelReadError(
            "read_row",
            f"Failed to read row {row_index} from '{worksheet_name}': {e.message}"
        )


def read_cell(
    file_id: str,
    worksheet_name: str,
    cell_address: str
) -> Any:
    """
    Read a single cell value.
    
    Args:
        file_id: OneDrive item ID of the Excel file
        worksheet_name: Name of the worksheet
        cell_address: Cell address in A1 notation (e.g., 'A1', 'B5', 'AA100')
        
    Returns:
        The cell value (string, number, boolean, or None)
        
    Raises:
        ExcelReadError: If operation fails
        
    Example:
        title = read_cell(file_id, "Sheet1", "A1")
        total = read_cell(file_id, "Sheet1", "E10")
    """
    encoded_name = _encode_worksheet_name(worksheet_name)
    endpoint = (
        f"{_build_workbook_endpoint(file_id)}/worksheets('{encoded_name}')"
        f"/range(address='{cell_address}')"
    )
    
    try:
        result = graph_get(endpoint)
        values = result.get("values", [[None]])
        
        if values and len(values) > 0 and len(values[0]) > 0:
            return values[0][0]
        return None
        
    except GraphAPIError as e:
        raise ExcelReadError(
            "read_cell",
            f"Failed to read cell {cell_address} from '{worksheet_name}': {e.message}"
        )


def get_last_used_row(
    file_id: str,
    worksheet_name: str
) -> int:
    """
    Get the 0-indexed row number of the last row with data.
    
    This is useful before appending data to know where to write next.
    
    Args:
        file_id: OneDrive item ID of the Excel file
        worksheet_name: Name of the worksheet
        
    Returns:
        int: 0-indexed row number of last used row, or -1 if worksheet is empty
        
    Raises:
        WorksheetNotFoundError: If worksheet doesn't exist
        ExcelReadError: If operation fails
        
    Example:
        last_row = get_last_used_row(file_id, "Sheet1")
        next_row = last_row + 1  # Where to append next
    """
    encoded_name = _encode_worksheet_name(worksheet_name)
    endpoint = f"{_build_workbook_endpoint(file_id)}/worksheets('{encoded_name}')/usedRange"
    
    try:
        result = graph_get(endpoint)
        
        # Get the address which tells us the used range
        # Format: "Sheet1!A1:E25" or just "A1:E25"
        address = result.get("address", "")
        
        if not address or address == "":
            return -1
        
        # Parse the range to get the last row
        # Remove sheet name if present
        if "!" in address:
            address = address.split("!")[-1]
        
        # Parse range (could be single cell "A1" or range "A1:E25")
        if ":" in address:
            end_cell = address.split(":")[1]
        else:
            end_cell = address
        
        # Extract row number from cell address (e.g., "E25" -> 25)
        row_str = ""
        for char in end_cell:
            if char.isdigit():
                row_str += char
        
        if row_str:
            # Convert to 0-indexed
            return int(row_str) - 1
        
        return -1
        
    except GraphAPIError as e:
        if e.status_code == 404 or e.error_code == "ItemNotFound":
            raise WorksheetNotFoundError(worksheet_name, file_id)
        raise ExcelReadError(
            "get_last_used_row",
            f"Failed to get last row from '{worksheet_name}': {e.message}"
        )


def get_used_range_address(
    file_id: str,
    worksheet_name: str
) -> Optional[str]:
    """
    Get the address of the used range in A1 notation.
    
    Args:
        file_id: OneDrive item ID of the Excel file
        worksheet_name: Name of the worksheet
        
    Returns:
        str: Range address like "A1:E25" or None if worksheet is empty
        
    Example:
        range_addr = get_used_range_address(file_id, "Sheet1")
        # "A1:F100"
    """
    encoded_name = _encode_worksheet_name(worksheet_name)
    endpoint = f"{_build_workbook_endpoint(file_id)}/worksheets('{encoded_name}')/usedRange"
    
    try:
        result = graph_get(endpoint)
        address = result.get("address", "")
        
        # Remove sheet name if present
        if "!" in address:
            address = address.split("!")[-1]
        
        return address if address else None
        
    except GraphAPIError as e:
        if e.status_code == 404:
            return None
        raise


def read_range(
    file_id: str,
    worksheet_name: str,
    range_address: str
) -> List[List[Any]]:
    """
    Read a specific range of cells.
    
    Args:
        file_id: OneDrive item ID of the Excel file
        worksheet_name: Name of the worksheet
        range_address: Range in A1 notation (e.g., "A1:E10", "B2:D5")
        
    Returns:
        list: 2D array of cell values
        
    Example:
        data = read_range(file_id, "Sheet1", "A1:E10")
        # Returns 10 rows, 5 columns
    """
    encoded_name = _encode_worksheet_name(worksheet_name)
    endpoint = (
        f"{_build_workbook_endpoint(file_id)}/worksheets('{encoded_name}')"
        f"/range(address='{range_address}')"
    )
    
    try:
        result = graph_get(endpoint)
        return result.get("values", [])
        
    except GraphAPIError as e:
        raise ExcelReadError(
            "read_range",
            f"Failed to read range {range_address} from '{worksheet_name}': {e.message}"
        )


def get_worksheet_info(
    file_id: str,
    worksheet_name: str
) -> Dict[str, Any]:
    """
    Get metadata about a worksheet.
    
    Args:
        file_id: OneDrive item ID of the Excel file
        worksheet_name: Name of the worksheet
        
    Returns:
        dict: Worksheet info including:
            - id: Worksheet ID
            - name: Worksheet name
            - position: Position in workbook (0-indexed)
            - visibility: 'Visible', 'Hidden', or 'VeryHidden'
            
    Example:
        info = get_worksheet_info(file_id, "Sheet1")
        print(f"Position: {info['position']}")
    """
    encoded_name = _encode_worksheet_name(worksheet_name)
    endpoint = f"{_build_workbook_endpoint(file_id)}/worksheets('{encoded_name}')"
    
    try:
        result = graph_get(endpoint)
        
        return {
            "id": result.get("id"),
            "name": result.get("name"),
            "position": result.get("position"),
            "visibility": result.get("visibility", "Visible")
        }
        
    except GraphAPIError as e:
        if e.status_code == 404:
            raise WorksheetNotFoundError(worksheet_name, file_id)
        raise ExcelReadError(
            "get_worksheet_info",
            f"Failed to get worksheet info for '{worksheet_name}': {e.message}"
        )
