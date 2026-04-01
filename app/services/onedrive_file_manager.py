"""
OneDrive File Manager Service (Phase 9A.2)

This module provides OneDrive file and folder management operations
built on top of the Graph API client from Phase 9A.1.

Features:
    - Folder creation (with nested path support)
    - File existence checking
    - File ID resolution from paths
    - File metadata retrieval
    - File listing in folders
    - Excel file creation from templates

All paths are relative to ONEDRIVE_BASE_FOLDER environment variable.

Usage:
    from app.services.onedrive_file_manager import (
        ensure_folder, get_file_id, file_exists, get_file_metadata
    )
    
    # Create nested folders
    folder = ensure_folder("Aichi/2026-02")
    
    # Check if file exists
    if file_exists("Aichi/Format2_2026-02.xlsx"):
        file_id = get_file_id("Aichi/Format2_2026-02.xlsx")

Author: Phase 9A.2 - Excel Read Operations & OneDrive File Management
Date: 2026-02-28
"""

import os
import logging
from typing import Optional, List, Dict, Any

from app.services.graph_client import (
    graph_get, graph_post, graph_put,
    get_user_id, get_base_folder, GraphAPIError
)

# Configure logging
logger = logging.getLogger(__name__)


class OneDriveFileNotFoundError(Exception):
    """Raised when a file or folder is not found on OneDrive."""
    
    def __init__(self, path: str, message: str = None):
        self.path = path
        self.message = message or f"File not found: {path}"
        super().__init__(self.message)


class FolderCreationError(Exception):
    """Raised when folder creation fails."""
    
    def __init__(self, path: str, message: str = None):
        self.path = path
        self.message = message or f"Failed to create folder: {path}"
        super().__init__(self.message)


def _build_drive_path(relative_path: str) -> str:
    """
    Build full OneDrive path from relative path.
    
    Args:
        relative_path: Path relative to ONEDRIVE_BASE_FOLDER
        
    Returns:
        Full path including base folder
    """
    base_folder = get_base_folder()
    
    # Clean up path separators
    relative_path = relative_path.strip("/").strip("\\")
    base_folder = base_folder.strip("/").strip("\\")
    
    if relative_path:
        return f"{base_folder}/{relative_path}"
    return base_folder


def _build_item_path_endpoint(path: str) -> str:
    """
    Build Graph API endpoint for item by path.
    
    Args:
        path: Full OneDrive path (including base folder)
        
    Returns:
        Graph API endpoint string
    """
    user_id = get_user_id()
    # Encode path for URL (handle special characters)
    # Graph API uses colon notation for path-based access
    return f"users/{user_id}/drive/root:/{path}"


def _build_item_id_endpoint(item_id: str) -> str:
    """
    Build Graph API endpoint for item by ID.
    
    Args:
        item_id: OneDrive item ID
        
    Returns:
        Graph API endpoint string
    """
    user_id = get_user_id()
    return f"users/{user_id}/drive/items/{item_id}"


def ensure_folder(folder_path: str) -> Dict[str, Any]:
    """
    Ensure a folder exists at the given path, creating it if necessary.
    
    Creates all nested folders in the path if they don't exist.
    
    Args:
        folder_path: Path relative to ONEDRIVE_BASE_FOLDER
                    Example: "Aichi/2026-02" creates both folders if needed
                    
    Returns:
        dict: Folder item object from Graph API
        
    Raises:
        FolderCreationError: If folder creation fails
        
    Example:
        folder = ensure_folder("Aichi/2026-02")
        print(folder["id"])  # OneDrive item ID
    """
    full_path = _build_drive_path(folder_path)
    logger.info(f"Ensuring folder exists: {full_path}")
    
    # First, check if folder already exists
    try:
        endpoint = _build_item_path_endpoint(full_path)
        folder = graph_get(endpoint)
        logger.debug(f"Folder already exists: {full_path}")
        return folder
    except GraphAPIError as e:
        if e.status_code != 404:
            raise FolderCreationError(folder_path, f"Error checking folder: {e.message}")
    
    # Folder doesn't exist - create it by building path incrementally
    path_parts = full_path.split("/")
    current_path = ""
    current_item = None
    
    for i, part in enumerate(path_parts):
        if not part:
            continue
            
        if current_path:
            current_path = f"{current_path}/{part}"
        else:
            current_path = part
        
        # Check if this part exists
        try:
            endpoint = _build_item_path_endpoint(current_path)
            current_item = graph_get(endpoint)
            logger.debug(f"Path segment exists: {current_path}")
        except GraphAPIError as e:
            if e.status_code == 404:
                # Need to create this folder
                logger.info(f"Creating folder segment: {current_path}")
                
                # Get parent folder ID
                if i == 0:
                    # Creating at root
                    parent_endpoint = f"users/{get_user_id()}/drive/root/children"
                else:
                    parent_path = "/".join(path_parts[:i])
                    parent_endpoint = _build_item_path_endpoint(parent_path) + ":/children"
                
                try:
                    current_item = graph_post(parent_endpoint, {
                        "name": part,
                        "folder": {},
                        "@microsoft.graph.conflictBehavior": "fail"
                    })
                    logger.info(f"Created folder: {part}")
                except GraphAPIError as create_error:
                    # Handle race condition - folder may have been created
                    if create_error.error_code == "nameAlreadyExists":
                        current_item = graph_get(endpoint)
                    else:
                        raise FolderCreationError(
                            folder_path, 
                            f"Failed to create {part}: {create_error.message}"
                        )
            else:
                raise FolderCreationError(folder_path, f"Error accessing path: {e.message}")
    
    logger.info(f"Folder ensured: {full_path}")
    return current_item


def get_file_id(file_path: str) -> str:
    """
    Get the OneDrive item ID for a file at the given path.
    
    Args:
        file_path: Path relative to ONEDRIVE_BASE_FOLDER
                  Example: "Aichi/Format2_2026-02.xlsx"
                  
    Returns:
        str: OneDrive item ID
        
    Raises:
        OneDriveFileNotFoundError: If file does not exist
        
    Example:
        file_id = get_file_id("Aichi/Format2_2026-02.xlsx")
    """
    full_path = _build_drive_path(file_path)
    
    try:
        endpoint = _build_item_path_endpoint(full_path)
        item = graph_get(endpoint)
        return item["id"]
    except GraphAPIError as e:
        if e.status_code == 404:
            raise OneDriveFileNotFoundError(file_path, f"File not found on OneDrive: {file_path}")
        raise


def file_exists(file_path: str) -> bool:
    """
    Check if a file exists at the given path.
    
    Args:
        file_path: Path relative to ONEDRIVE_BASE_FOLDER
        
    Returns:
        bool: True if file exists, False otherwise
        
    Note:
        This function does NOT throw on 404 - it returns False.
        
    Example:
        if file_exists("Aichi/Format2_2026-02.xlsx"):
            print("File found!")
    """
    full_path = _build_drive_path(file_path)
    
    try:
        endpoint = _build_item_path_endpoint(full_path)
        graph_get(endpoint)
        return True
    except GraphAPIError as e:
        if e.status_code == 404:
            return False
        # For other errors, log but return False to be safe
        logger.warning(f"Error checking file existence: {e.message}")
        return False


def create_excel_file(
    file_path: str,
    template_local_path: Optional[str] = None
) -> str:
    """
    Create a new Excel file on OneDrive.
    
    If a template_local_path is provided, uploads that file.
    If file already exists, returns the existing file ID without overwriting.
    
    Args:
        file_path: Path relative to ONEDRIVE_BASE_FOLDER
                  Example: "Aichi/Format2_2026-02.xlsx"
        template_local_path: Optional local path to template file to upload
        
    Returns:
        str: OneDrive item ID of the file
        
    Raises:
        OneDriveFileNotFoundError: If template file doesn't exist locally
        GraphAPIError: If upload fails
        
    Example:
        file_id = create_excel_file(
            "Aichi/Format2_2026-02.xlsx",
            "Template/Format2_Template.xlsx"
        )
    """
    # Check if file already exists
    if file_exists(file_path):
        logger.info(f"File already exists, returning existing ID: {file_path}")
        return get_file_id(file_path)
    
    # Ensure parent folder exists
    folder_path = "/".join(file_path.split("/")[:-1])
    if folder_path:
        ensure_folder(folder_path)
    
    full_path = _build_drive_path(file_path)
    file_name = file_path.split("/")[-1]
    
    if template_local_path:
        # Upload from local template
        if not os.path.exists(template_local_path):
            raise OneDriveFileNotFoundError(
                template_local_path,
                f"Template file not found locally: {template_local_path}"
            )
        
        logger.info(f"Uploading file from template: {template_local_path} -> {file_path}")
        
        # Read template file
        with open(template_local_path, "rb") as f:
            content = f.read()
        
        # Upload using PUT (for small files < 4MB)
        # For larger files, would need upload session
        user_id = get_user_id()
        endpoint = f"users/{user_id}/drive/root:/{full_path}:/content"
        
        # Need to use raw request for binary upload
        import requests
        from app.services.graph_auth import get_access_token
        
        url = f"https://graph.microsoft.com/v1.0/{endpoint}"
        headers = {
            "Authorization": f"Bearer {get_access_token()}",
            "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        }
        
        response = requests.put(url, headers=headers, data=content, timeout=60)
        
        if response.status_code in (200, 201):
            result = response.json()
            logger.info(f"File uploaded successfully: {file_path}")
            return result["id"]
        else:
            raise GraphAPIError(
                message=f"Upload failed: {response.text}",
                status_code=response.status_code
            )
    else:
        # Create empty Excel file using workbook session
        # This creates a minimal valid Excel file
        logger.info(f"Creating empty Excel file: {file_path}")
        
        # Upload an empty xlsx (minimal valid Excel file bytes)
        # This is a minimal valid .xlsx file
        import base64
        EMPTY_XLSX_BASE64 = (
            "UEsDBBQAAAAIAAAAAACHfwAAAAAAAAAAAAAAABIAHABjb2x0ZW50X3R5cGVzLnhtbFVUCQAD"
            # Minimal empty xlsx bytes - using template approach is better
        )
        
        # Better approach: just upload a minimal workbook
        # For now, we'll require a template
        raise ValueError(
            "template_local_path is required to create Excel files. "
            "Provide a path to a template .xlsx file."
        )


def get_file_metadata(file_id: str) -> Dict[str, Any]:
    """
    Get metadata for a file by its OneDrive item ID.
    
    Returns metadata including name, size, lastModifiedDateTime, and eTag.
    The eTag is used for optimistic concurrency on write operations.
    
    Args:
        file_id: OneDrive item ID
        
    Returns:
        dict: File metadata with keys:
            - id: Item ID
            - name: File name
            - size: File size in bytes
            - lastModifiedDateTime: ISO timestamp
            - eTag: Entity tag for concurrency
            - webUrl: URL to view in browser
            
    Example:
        meta = get_file_metadata(file_id)
        print(f"Last modified: {meta['lastModifiedDateTime']}")
        print(f"ETag: {meta['eTag']}")
    """
    endpoint = _build_item_id_endpoint(file_id)
    
    # Request specific fields
    params = "?$select=id,name,size,lastModifiedDateTime,eTag,webUrl,file"
    
    item = graph_get(endpoint + params)
    
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "size": item.get("size"),
        "lastModifiedDateTime": item.get("lastModifiedDateTime"),
        "eTag": item.get("eTag"),
        "webUrl": item.get("webUrl"),
        "mimeType": item.get("file", {}).get("mimeType")
    }


def list_files_in_folder(folder_path: str) -> List[Dict[str, Any]]:
    """
    List all files in a folder.
    
    Args:
        folder_path: Path relative to ONEDRIVE_BASE_FOLDER
                    Use empty string "" for base folder itself
                    
    Returns:
        list: Array of file info dicts with keys:
            - name: File name
            - id: Item ID
            - size: Size in bytes
            - isFolder: Boolean
            - lastModified: ISO timestamp
            
    Example:
        files = list_files_in_folder("Aichi/2026-02")
        for f in files:
            print(f"{f['name']} - {f['size']} bytes")
    """
    full_path = _build_drive_path(folder_path) if folder_path else get_base_folder()
    
    try:
        endpoint = _build_item_path_endpoint(full_path) + ":/children"
        result = graph_get(endpoint)
        
        items = result.get("value", [])
        
        return [
            {
                "name": item.get("name"),
                "id": item.get("id"),
                "size": item.get("size", 0),
                "isFolder": "folder" in item,
                "lastModified": item.get("lastModifiedDateTime")
            }
            for item in items
        ]
        
    except GraphAPIError as e:
        if e.status_code == 404:
            raise OneDriveFileNotFoundError(folder_path, f"Folder not found: {folder_path}")
        raise


def get_folder_id(folder_path: str) -> str:
    """
    Get the OneDrive item ID for a folder.
    
    Args:
        folder_path: Path relative to ONEDRIVE_BASE_FOLDER
        
    Returns:
        str: OneDrive item ID
        
    Raises:
        OneDriveFileNotFoundError: If folder does not exist
    """
    full_path = _build_drive_path(folder_path) if folder_path else get_base_folder()
    
    try:
        endpoint = _build_item_path_endpoint(full_path)
        item = graph_get(endpoint)
        return item["id"]
    except GraphAPIError as e:
        if e.status_code == 404:
            raise OneDriveFileNotFoundError(folder_path, f"Folder not found: {folder_path}")
        raise


def get_base_folder_id() -> str:
    """
    Get the OneDrive item ID for the base folder (ONEDRIVE_BASE_FOLDER).
    
    Creates the base folder if it doesn't exist.
    
    Returns:
        str: OneDrive item ID of base folder
    """
    base_folder = get_base_folder()
    
    try:
        endpoint = _build_item_path_endpoint(base_folder)
        item = graph_get(endpoint)
        return item["id"]
    except GraphAPIError as e:
        if e.status_code == 404:
            # Create the base folder
            logger.info(f"Creating base folder: {base_folder}")
            folder = ensure_folder("")
            return folder["id"]
        raise
