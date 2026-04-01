"""
Graph API Authentication Service (Phase 9A.1)

This module handles OAuth2 client credentials flow authentication with Microsoft Graph API
using MSAL (Microsoft Authentication Library). It caches access tokens and automatically
refreshes them before expiry.

Usage:
    from app.services.graph_auth import get_access_token
    
    token = get_access_token()
    # Use token in Authorization: Bearer {token} header

Environment Variables Required:
    - MICROSOFT_TENANT_ID: Azure AD tenant ID
    - MICROSOFT_CLIENT_ID: App registration client ID  
    - MICROSOFT_CLIENT_SECRET: App registration client secret

Author: Phase 9A.1 - Graph API Foundation
Date: 2026-02-27
"""

import os
import logging
import time
from typing import Optional
from msal import ConfidentialClientApplication

# Configure logging
logger = logging.getLogger(__name__)

# Microsoft Graph API scope for client credentials flow
GRAPH_SCOPE = ["https://graph.microsoft.com/.default"]

# Token cache - stores the access token and expiry time
_token_cache = {
    "access_token": None,
    "expires_at": 0  # Unix timestamp when token expires
}

# Buffer time in seconds - refresh token this many seconds before actual expiry
TOKEN_EXPIRY_BUFFER = 300  # 5 minutes

# MSAL app instance (lazy initialized)
_msal_app: Optional[ConfidentialClientApplication] = None


def _get_msal_app() -> ConfidentialClientApplication:
    """
    Get or create the MSAL ConfidentialClientApplication instance.
    Lazy initialization to allow environment variables to be loaded first.
    
    Returns:
        ConfidentialClientApplication: Configured MSAL app instance
        
    Raises:
        ValueError: If required environment variables are not set
    """
    global _msal_app
    
    if _msal_app is not None:
        return _msal_app
    
    # Read credentials from environment variables
    tenant_id = os.environ.get("MICROSOFT_TENANT_ID")
    client_id = os.environ.get("MICROSOFT_CLIENT_ID")
    client_secret = os.environ.get("MICROSOFT_CLIENT_SECRET")
    
    # Validate required variables
    missing_vars = []
    if not tenant_id or tenant_id == "your-tenant-id-here":
        missing_vars.append("MICROSOFT_TENANT_ID")
    if not client_id or client_id == "your-client-id-here":
        missing_vars.append("MICROSOFT_CLIENT_ID")
    if not client_secret or client_secret == "your-client-secret-here":
        missing_vars.append("MICROSOFT_CLIENT_SECRET")
    
    if missing_vars:
        error_msg = f"Missing or invalid Microsoft Graph API credentials: {', '.join(missing_vars)}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    # Build authority URL
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    
    # Create MSAL confidential client application
    _msal_app = ConfidentialClientApplication(
        client_id=client_id,
        client_credential=client_secret,
        authority=authority
    )
    
    logger.info(f"MSAL app initialized for tenant: {tenant_id[:8]}...")
    return _msal_app


def _is_token_valid() -> bool:
    """
    Check if the cached token is still valid (not expired).
    
    Returns:
        bool: True if token exists and hasn't expired (with buffer), False otherwise
    """
    if _token_cache["access_token"] is None:
        return False
    
    current_time = time.time()
    # Check if token will expire within buffer time
    return current_time < (_token_cache["expires_at"] - TOKEN_EXPIRY_BUFFER)


def _acquire_new_token() -> str:
    """
    Acquire a new access token using client credentials flow.
    
    Returns:
        str: The access token
        
    Raises:
        Exception: If token acquisition fails
    """
    msal_app = _get_msal_app()
    
    logger.info("Acquiring new Microsoft Graph API access token...")
    
    # Try to get token from MSAL's internal cache first
    result = msal_app.acquire_token_silent(
        scopes=GRAPH_SCOPE,
        account=None
    )
    
    if not result:
        # No cached token, acquire new one
        result = msal_app.acquire_token_for_client(scopes=GRAPH_SCOPE)
    
    if "access_token" in result:
        # Calculate expiry time (tokens typically last 1 hour = 3600 seconds)
        expires_in = result.get("expires_in", 3600)
        expires_at = time.time() + expires_in
        
        # Update cache
        _token_cache["access_token"] = result["access_token"]
        _token_cache["expires_at"] = expires_at
        
        logger.info(f"Access token acquired successfully (expires in {expires_in}s)")
        return result["access_token"]
    
    # Token acquisition failed
    error = result.get("error", "unknown_error")
    error_description = result.get("error_description", "No description available")
    
    error_msg = f"Failed to acquire token: {error} - {error_description}"
    logger.error(error_msg)
    raise Exception(error_msg)


def get_access_token() -> str:
    """
    Get a valid Microsoft Graph API access token.
    
    Returns a cached token if valid, otherwise acquires a new one.
    This is the main entry point for authentication.
    
    Returns:
        str: Valid access token for Microsoft Graph API
        
    Raises:
        ValueError: If environment variables are not configured
        Exception: If token acquisition fails
        
    Example:
        token = get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
    """
    if _is_token_valid():
        logger.debug("Using cached access token")
        return _token_cache["access_token"]
    
    return _acquire_new_token()


def clear_token_cache() -> None:
    """
    Clear the cached access token.
    
    Useful for testing or when credentials change.
    """
    global _msal_app
    
    _token_cache["access_token"] = None
    _token_cache["expires_at"] = 0
    _msal_app = None
    
    logger.info("Token cache cleared")


def get_token_info() -> dict:
    """
    Get information about the current cached token (for debugging).
    
    Returns:
        dict: Token information including expiry status
        
    Note:
        Does NOT return the actual token value for security reasons.
    """
    if _token_cache["access_token"] is None:
        return {
            "has_token": False,
            "expires_at": None,
            "is_valid": False,
            "seconds_until_expiry": None
        }
    
    current_time = time.time()
    seconds_until_expiry = _token_cache["expires_at"] - current_time
    
    return {
        "has_token": True,
        "expires_at": _token_cache["expires_at"],
        "is_valid": _is_token_valid(),
        "seconds_until_expiry": int(seconds_until_expiry) if seconds_until_expiry > 0 else 0
    }


# =============================================================================
# PHASE 9 STEP 2: SAFE TEST OPERATIONS
# =============================================================================

def test_graph_auth() -> dict:
    """
    Test Graph API authentication without making any other API calls.
    
    This is a SAFE operation that:
    1. Checks configuration is present
    2. Attempts to acquire a token
    3. Reports success/failure with details
    
    Use this for Phase 10 PoC initial validation.
    
    Returns:
        dict: Test result with status and details
        
    Example:
        result = test_graph_auth()
        if result["success"]:
            print("Auth works!")
        else:
            print(f"Auth failed: {result['error']}")
    """
    result = {
        "test": "graph_auth",
        "success": False,
        "error": None,
        "details": {}
    }
    
    # Step 1: Check configuration
    if not is_graph_api_configured():
        result["error"] = "Graph API not configured"
        result["details"]["config_status"] = get_graph_config_status()
        return result
    
    result["details"]["config_check"] = "passed"
    
    # Step 2: Attempt token acquisition
    try:
        # Clear any cached token to force fresh acquisition
        clear_token_cache()
        
        # Try to get a fresh token
        token = get_access_token()
        
        if token:
            result["success"] = True
            result["details"]["token_acquired"] = True
            result["details"]["token_info"] = get_token_info()
            result["details"]["message"] = "Successfully authenticated with Microsoft Graph API"
        else:
            result["error"] = "Token acquisition returned empty"
            result["details"]["token_acquired"] = False
            
    except ValueError as e:
        result["error"] = f"Configuration error: {str(e)}"
        result["details"]["error_type"] = "configuration"
        
    except Exception as e:
        result["error"] = f"Authentication failed: {str(e)}"
        result["details"]["error_type"] = "authentication"
        # Extract useful error info if available
        error_str = str(e)
        if "AADSTS" in error_str:
            result["details"]["azure_error_code"] = error_str.split("AADSTS")[1].split(":")[0] if ":" in error_str else "unknown"
    
    return result


# =============================================================================
# PHASE 9 STEP 1 + STEP 2: SAFETY & HARDENING HELPERS
# =============================================================================
# Step 1 (2026-03-20): Basic safety gating
# Step 2 (2026-03-20): Hardened validation, comprehensive readiness checks
# =============================================================================

import re

# Placeholder values that indicate unconfigured credentials (exact matches)
_PLACEHOLDER_VALUES = {
    "your-tenant-id-here",
    "your-client-id-here", 
    "your-client-secret-here",
    "your-onedrive-user-email-or-id",
    "your-user-id-here",
    "your-folder-here",
    "placeholder",
    "changeme",
    "xxx",
    "TODO",
    "REPLACE_ME",
    "",
    None,
}

# Patterns that indicate placeholder values (regex)
_PLACEHOLDER_PATTERNS = [
    r"^your[-_]",           # Starts with "your-" or "your_"
    r"[-_]here$",           # Ends with "-here" or "_here"
    r"^placeholder",        # Starts with "placeholder"
    r"^xxx+$",              # Just x's
    r"^changeme$",          # "changeme"
    r"^TODO",               # Starts with TODO
    r"^REPLACE",            # Starts with REPLACE
    r"^\s*$",               # Whitespace only
]


def _is_placeholder_value(value: str) -> bool:
    """
    Check if a value looks like a placeholder.
    
    Args:
        value: The value to check
        
    Returns:
        True if the value appears to be a placeholder, False otherwise
    """
    if value is None:
        return True
    if value == "":
        return True
    if value in _PLACEHOLDER_VALUES:
        return True
    
    # Check against patterns
    value_lower = value.lower().strip()
    for pattern in _PLACEHOLDER_PATTERNS:
        if re.search(pattern, value_lower, re.IGNORECASE):
            return True
    
    return False


def _check_config_value(val: str, required: bool = True) -> str:
    """
    Check a configuration value's status.
    
    Args:
        val: The value to check
        required: Whether the value is required (default True)
        
    Returns:
        Status string: "missing", "placeholder", "configured", or "optional_missing"
    """
    if val is None or val == "":
        return "missing" if required else "optional_missing"
    if _is_placeholder_value(val):
        return "placeholder"
    return "configured"


def is_graph_api_configured() -> bool:
    """
    Check if Microsoft Graph API credentials are properly configured.
    
    This is a NON-THROWING check that returns True only if all required
    credentials are present and are not placeholder values.
    
    Checks:
        - MICROSOFT_TENANT_ID (required)
        - MICROSOFT_CLIENT_ID (required)
        - MICROSOFT_CLIENT_SECRET (required)
    
    Use this to gate Graph-dependent features safely without crashing.
    
    Returns:
        bool: True if all auth credentials are valid, False otherwise
        
    Example:
        if is_graph_api_configured():
            # Safe to use Graph API
            token = get_access_token()
        else:
            # Fall back to legacy behavior or return config error
            return {"error": "Graph API not configured"}
    """
    tenant_id = os.environ.get("MICROSOFT_TENANT_ID")
    client_id = os.environ.get("MICROSOFT_CLIENT_ID")
    client_secret = os.environ.get("MICROSOFT_CLIENT_SECRET")
    
    # Check all required auth values are present and not placeholders
    if _is_placeholder_value(tenant_id):
        return False
    if _is_placeholder_value(client_id):
        return False
    if _is_placeholder_value(client_secret):
        return False
    
    return True


def is_graph_fully_configured() -> bool:
    """
    Check if Graph API AND OneDrive file operations are fully configured.
    
    This is a stricter check than is_graph_api_configured() - it also verifies
    that the user ID and base folder are configured for file operations.
    
    Checks:
        - MICROSOFT_TENANT_ID (required)
        - MICROSOFT_CLIENT_ID (required)
        - MICROSOFT_CLIENT_SECRET (required)
        - MICROSOFT_USER_ID (required for file operations)
        - ONEDRIVE_BASE_FOLDER (required for file operations)
    
    Returns:
        bool: True if all required configuration is present, False otherwise
    """
    if not is_graph_api_configured():
        return False
    
    user_id = os.environ.get("MICROSOFT_USER_ID")
    base_folder = os.environ.get("ONEDRIVE_BASE_FOLDER")
    
    if _is_placeholder_value(user_id):
        return False
    if _is_placeholder_value(base_folder):
        return False
    
    return True


def get_graph_config_status() -> dict:
    """
    Get detailed status of Graph API configuration.
    
    Returns a dict suitable for API responses or diagnostics without
    exposing actual credential values.
    
    Returns:
        dict: Configuration status with missing/placeholder indicators
    """
    tenant_id = os.environ.get("MICROSOFT_TENANT_ID")
    client_id = os.environ.get("MICROSOFT_CLIENT_ID")
    client_secret = os.environ.get("MICROSOFT_CLIENT_SECRET")
    user_id = os.environ.get("MICROSOFT_USER_ID")
    base_folder = os.environ.get("ONEDRIVE_BASE_FOLDER")
    
    auth_configured = is_graph_api_configured()
    fully_configured = is_graph_fully_configured()
    
    if fully_configured:
        message = "Graph API fully configured - ready for Phase 10 PoC"
    elif auth_configured:
        message = "Graph API auth configured, but file operations not configured (need MICROSOFT_USER_ID, ONEDRIVE_BASE_FOLDER)"
    else:
        message = "Graph API credentials not configured - Phase 10 PoC required"
    
    return {
        "configured": auth_configured,
        "fully_configured": fully_configured,
        "tenant_id": _check_config_value(tenant_id),
        "client_id": _check_config_value(client_id),
        "client_secret": _check_config_value(client_secret),
        "user_id": _check_config_value(user_id),
        "base_folder": _check_config_value(base_folder),
        "message": message
    }


def get_graph_readiness_report() -> dict:
    """
    Get a comprehensive readiness report for Phase 10 PoC.
    
    This provides detailed diagnostics for admin troubleshooting,
    including exactly what is missing and what is ready.
    
    Returns:
        dict: Comprehensive readiness report
    """
    config_status = get_graph_config_status()
    
    # Identify blockers
    blockers = []
    if config_status["tenant_id"] != "configured":
        blockers.append("MICROSOFT_TENANT_ID not set or placeholder")
    if config_status["client_id"] != "configured":
        blockers.append("MICROSOFT_CLIENT_ID not set or placeholder")
    if config_status["client_secret"] != "configured":
        blockers.append("MICROSOFT_CLIENT_SECRET not set or placeholder")
    if config_status["user_id"] != "configured":
        blockers.append("MICROSOFT_USER_ID not set or placeholder")
    if config_status["base_folder"] != "configured":
        blockers.append("ONEDRIVE_BASE_FOLDER not set or placeholder")
    
    # Identify what's ready
    ready_items = []
    if config_status["tenant_id"] == "configured":
        ready_items.append("Azure AD tenant configured")
    if config_status["client_id"] == "configured":
        ready_items.append("Application client ID configured")
    if config_status["client_secret"] == "configured":
        ready_items.append("Application secret configured")
    if config_status["user_id"] == "configured":
        ready_items.append("OneDrive user ID configured")
    if config_status["base_folder"] == "configured":
        ready_items.append("OneDrive base folder configured")
    
    # Determine overall readiness
    if config_status["fully_configured"]:
        readiness = "READY"
        readiness_message = "All configuration present - ready for live PoC testing"
    elif config_status["configured"]:
        readiness = "PARTIAL"
        readiness_message = "Auth ready, file operations blocked - need user/folder config"
    else:
        readiness = "NOT_READY"
        readiness_message = "Core auth not configured - cannot proceed with PoC"
    
    return {
        "readiness": readiness,
        "readiness_message": readiness_message,
        "auth_configured": config_status["configured"],
        "file_operations_configured": config_status["fully_configured"],
        "blockers": blockers,
        "ready_items": ready_items,
        "config_status": config_status,
        "next_steps": _get_next_steps(blockers),
        "safe_tests_available": config_status["configured"],  # Auth tests work if auth configured
    }


def _get_next_steps(blockers: list) -> list:
    """Generate next steps based on blockers."""
    steps = []
    
    if not blockers:
        steps.append("Configuration complete - proceed to live PoC testing")
        steps.append("Test with GET /api/system/graph-health first")
        return steps
    
    if any("TENANT_ID" in b for b in blockers):
        steps.append("Obtain Azure AD tenant ID from Microsoft 365 admin portal")
    if any("CLIENT_ID" in b for b in blockers):
        steps.append("Register application in Azure AD and obtain client ID")
    if any("CLIENT_SECRET" in b for b in blockers):
        steps.append("Create client secret for registered application")
    if any("USER_ID" in b for b in blockers):
        steps.append("Set MICROSOFT_USER_ID to the OneDrive user's email or object ID")
    if any("BASE_FOLDER" in b for b in blockers):
        steps.append("Set ONEDRIVE_BASE_FOLDER to the folder path (e.g., 'ReceiptOCR' or 'Documents/Receipts')")
    
    return steps
