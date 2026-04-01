"""
System API Routes (Phase 9A.4, Updated in Phase 9 Steps 2 & 3)

API endpoints for system health, monitoring, and diagnostics.

Endpoints:
    GET /api/system/graph-health - Graph API health status
    GET /api/system/queue-stats - Request queue statistics
    GET /api/system/graph-config - Graph API configuration status (Phase 9 Step 1)
    GET /api/system/graph-readiness - Phase 10 PoC readiness report (Phase 9 Step 2)
    POST /api/system/graph-test-auth - Test Graph API authentication (Phase 9 Step 2)
    POST /api/system/graph-test-onedrive - Test OneDrive access (Phase 9 Step 2)
    POST /api/system/graph-test-all - Run all connectivity tests (Phase 9 Step 2)
    POST /api/system/poc-run-readonly - Run Phase 10 PoC read-only tests (Phase 9 Step 3)
    POST /api/system/poc-run-full - Run complete Phase 10 PoC validation (Phase 9 Step 3)
    GET /api/system/poc-config-assumptions - Get documented config assumptions (Phase 9 Step 3)

Author: Phase 9A.4 - Request Queue, Rate Limiting & Retry Engine
Updated: Phase 9 Step 1 - Safety stabilization (2026-03-20)
Updated: Phase 9 Step 2 - Hardening & PoC readiness (2026-03-20)
Updated: Phase 9 Step 3 - Live PoC execution preparation (2026-03-20)
Date: 2026-02-28
"""

import logging
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, Optional
from datetime import datetime

# Create router for system endpoints
router = APIRouter(prefix="/api/system", tags=["system"])
logger = logging.getLogger(__name__)


# Optional: Admin authentication dependency
# Uncomment and modify for your auth system
# from app.routes.auth import get_current_user, require_admin
# 
# async def require_admin_access(user = Depends(get_current_user)):
#     if user.get('role') != 'admin':
#         raise HTTPException(status_code=403, detail="Admin access required")
#     return user


# =============================================================================
# PHASE 9 STEP 1: GRAPH CONFIG STATUS ENDPOINT (2026-03-20)
# =============================================================================

@router.get("/graph-config")
async def get_graph_config() -> Dict[str, Any]:
    """
    Get Microsoft Graph API configuration status.
    
    Returns configuration status WITHOUT exposing actual credential values.
    Use this endpoint to check if Graph API is ready for use.
    
    This endpoint always succeeds - it checks configuration, not connectivity.
    
    Returns:
        JSON with configuration status:
        {
            "configured": false,
            "tenant_id": "missing" | "placeholder" | "configured",
            "client_id": "missing" | "placeholder" | "configured",
            "client_secret": "missing" | "placeholder" | "configured",
            "user_id": "missing" | "placeholder" | "configured",
            "base_folder": "missing" | "placeholder" | "configured",
            "message": "Graph API ready" | "Graph API credentials not configured..."
        }
    """
    try:
        from app.services.graph_auth import get_graph_config_status
        
        status = get_graph_config_status()
        status["timestamp"] = datetime.utcnow().isoformat() + "Z"
        return status
        
    except ImportError:
        return {
            "configured": False,
            "error": "Graph auth module not available",
            "message": "Graph API module not installed",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }


@router.get("/graph-health")
async def get_graph_health() -> Dict[str, Any]:
    """
    Get Microsoft Graph API health status.
    
    Returns comprehensive health metrics including:
        - Overall status (healthy/degraded/unhealthy)
        - Success rate over 5-minute window
        - Throttle count
        - Response time percentiles
        - Circuit breaker state
        - Lifetime statistics
        
    This endpoint is useful for monitoring dashboards and alerting.
    
    Note (Phase 9 Step 1): Returns "not_configured" status if Graph API
    credentials are missing or placeholder values.
    
    Returns:
        JSON health report
        
    Example Response:
        {
            "status": "healthy",
            "timestamp": "2026-02-28T10:30:00Z",
            "successRate": 0.98,
            "throttleCount": 2,
            "avgResponseMs": 150.5,
            "circuitBreaker": {
                "isOpen": false,
                "consecutiveFailures": 0
            }
        }
    """
    # Phase 9 Step 1: Check if Graph API is configured before attempting health check
    try:
        from app.services.graph_auth import is_graph_api_configured
        
        if not is_graph_api_configured():
            return {
                "status": "not_configured",
                "message": "Graph API credentials not configured. Phase 10 PoC required.",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
    except ImportError:
        pass  # If import fails, fall through to normal health check logic
    
    try:
        from app.services.graph_health_monitor import get_health_report
        
        report = get_health_report()
        return report
        
    except ImportError:
        logger.warning("Graph health monitor not available")
        return {
            "status": "unknown",
            "error": "Health monitor not initialized",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    except Exception as e:
        logger.error(f"Error getting graph health: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get health report: {str(e)}"
        )


@router.get("/queue-stats")
async def get_queue_stats() -> Dict[str, Any]:
    """
    Get request queue statistics.
    
    Returns queue metrics including:
        - Pending requests
        - Processing count
        - Completed/failed totals
        - Average wait time
        - Pause status (if rate limited)
        
    Returns:
        JSON with queue statistics
        
    Example Response:
        {
            "pending": 3,
            "processing": 2,
            "completed": 150,
            "failed": 5,
            "avgWaitMs": 45.2,
            "isPaused": false
        }
    """
    try:
        from app.services.request_queue import get_queue_stats
        
        stats = get_queue_stats()
        stats["timestamp"] = datetime.utcnow().isoformat() + "Z"
        return stats
        
    except ImportError:
        logger.warning("Request queue not available")
        return {
            "status": "unknown",
            "error": "Request queue not initialized",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    except Exception as e:
        logger.error(f"Error getting queue stats: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get queue stats: {str(e)}"
        )


@router.get("/graph-status")
async def get_graph_status() -> Dict[str, Any]:
    """
    Get combined Graph API status summary.
    
    Provides a single endpoint with key health indicators
    from both the health monitor and request queue.
    
    Returns:
        JSON with combined status
    """
    try:
        from app.services.graph_health_monitor import get_health_report, is_circuit_open
        from app.services.request_queue import get_queue_stats, is_queue_healthy
        
        health = get_health_report()
        queue = get_queue_stats()
        
        # Determine overall status
        overall = "healthy"
        if health.get("status") == "unhealthy" or is_circuit_open():
            overall = "unhealthy"
        elif health.get("status") == "degraded" or not is_queue_healthy():
            overall = "degraded"
        
        return {
            "status": overall,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            
            # Key metrics
            "successRate": health.get("successRate", 1.0),
            "throttleCount": health.get("throttleCount", 0),
            "circuitOpen": is_circuit_open(),
            
            # Queue
            "queuePending": queue.get("pending", 0),
            "queuePaused": queue.get("isPaused", False),
            "queuePauseRemaining": queue.get("pauseRemainingSeconds", 0),
            
            # Response times
            "avgResponseMs": health.get("avgResponseMs", 0),
            
            # Lifetime
            "totalRequests": health.get("lifetime", {}).get("totalRequests", 0),
            "totalThrottles": health.get("lifetime", {}).get("totalThrottle", 0)
        }
        
    except ImportError as e:
        logger.warning(f"Graph modules not available: {e}")
        return {
            "status": "unknown",
            "error": "Graph monitoring not initialized",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    except Exception as e:
        logger.error(f"Error getting graph status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get graph status: {str(e)}"
        )


@router.post("/graph-health/reset")
async def reset_health_monitor() -> Dict[str, str]:
    """
    Reset health monitor metrics.
    
    Clears all recorded metrics and resets the circuit breaker.
    Use with caution - primarily for testing purposes.
    
    Returns:
        Confirmation message
    """
    # TODO: Add admin authentication check
    # user = await require_admin_access()
    
    try:
        from app.services.graph_health_monitor import reset_health_monitor
        
        reset_health_monitor()
        logger.info("Graph health monitor reset by admin")
        
        return {
            "message": "Health monitor reset successfully",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="Health monitor not available"
        )
    except Exception as e:
        logger.error(f"Error resetting health monitor: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reset: {str(e)}"
        )


@router.get("/ping")
async def ping() -> Dict[str, str]:
    """
    Simple health check endpoint.
    
    Returns:
        {"status": "ok", "timestamp": "..."}
    """
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


# =============================================================================
# PHASE 9 STEP 2: ENHANCED DIAGNOSTICS (2026-03-20)
# =============================================================================
# SAFETY NOTES:
# - All endpoints in this section are INTERNAL/ADMIN DIAGNOSTICS
# - All operations are NON-DESTRUCTIVE (read-only validation)
# - No production data is modified by these endpoints
# - These are safe to expose to admin users for PoC troubleshooting
# =============================================================================

@router.get("/graph-readiness")
async def get_graph_readiness() -> Dict[str, Any]:
    """
    Get comprehensive Phase 10 PoC readiness report.
    
    Provides detailed diagnostics including:
        - Overall readiness status (READY, PARTIAL, NOT_READY)
        - Configuration blockers
        - What's already configured
        - Next steps for completion
    
    This is the primary endpoint for admin troubleshooting and PoC preparation.
    
    Returns:
        JSON with comprehensive readiness report
        
    Example Response:
        {
            "readiness": "PARTIAL",
            "readiness_message": "Auth ready, file operations blocked",
            "auth_configured": true,
            "file_operations_configured": false,
            "blockers": ["ONEDRIVE_BASE_FOLDER not set or placeholder"],
            "ready_items": ["Azure AD tenant configured", "Application client ID configured"],
            "next_steps": ["Set ONEDRIVE_BASE_FOLDER to the folder path"]
        }
    """
    try:
        from app.services.graph_auth import get_graph_readiness_report
        
        report = get_graph_readiness_report()
        report["timestamp"] = datetime.utcnow().isoformat() + "Z"
        return report
        
    except ImportError as e:
        return {
            "readiness": "NOT_READY",
            "error": f"Graph auth module not available: {str(e)}",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    except Exception as e:
        logger.error(f"Error getting readiness report: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get readiness report: {str(e)}"
        )


@router.post("/graph-test-auth")
async def test_graph_auth_endpoint() -> Dict[str, Any]:
    """
    Test Graph API authentication (safe, non-destructive).
    
    Attempts to acquire a fresh token from Azure AD to verify
    credentials are working. Does NOT make any other API calls.
    
    This is the first test to run when setting up new credentials.
    
    Returns:
        JSON with auth test result
        
    Example Response (success):
        {
            "test": "graph_auth",
            "success": true,
            "details": {
                "token_acquired": true,
                "message": "Successfully authenticated with Microsoft Graph API"
            }
        }
        
    Example Response (failure):
        {
            "test": "graph_auth",
            "success": false,
            "error": "Authentication failed: AADSTS700016...",
            "details": {"error_type": "authentication"}
        }
    """
    try:
        from app.services.graph_auth import test_graph_auth, is_graph_api_configured
        
        # Check config first
        if not is_graph_api_configured():
            return {
                "test": "graph_auth",
                "success": False,
                "error": "Graph API not configured",
                "message": "Set MICROSOFT_TENANT_ID, MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET first",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        
        result = test_graph_auth()
        result["timestamp"] = datetime.utcnow().isoformat() + "Z"
        return result
        
    except ImportError as e:
        return {
            "test": "graph_auth",
            "success": False,
            "error": f"Graph auth module not available: {str(e)}",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    except Exception as e:
        logger.error(f"Error testing auth: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Auth test failed: {str(e)}"
        )


@router.post("/graph-test-onedrive")
async def test_onedrive_endpoint() -> Dict[str, Any]:
    """
    Test OneDrive access (safe, non-destructive, read-only).
    
    Verifies:
        - Authentication works
        - User's drive is accessible
        - Base folder exists
    
    Run this after auth test passes to verify OneDrive setup.
    
    Returns:
        JSON with OneDrive test result
        
    Example Response (success):
        {
            "test": "onedrive_access",
            "success": true,
            "details": {
                "drive_name": "OneDrive",
                "drive_type": "business",
                "base_folder_name": "ReceiptOCR"
            }
        }
    """
    try:
        from app.services.graph_auth import is_graph_fully_configured
        from app.services.graph_client import test_onedrive_access
        
        # Check full config first
        if not is_graph_fully_configured():
            return {
                "test": "onedrive_access",
                "success": False,
                "error": "OneDrive not fully configured",
                "message": "Set all required env vars: MICROSOFT_TENANT_ID, MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET, MICROSOFT_USER_ID, ONEDRIVE_BASE_FOLDER",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        
        result = test_onedrive_access()
        result["timestamp"] = datetime.utcnow().isoformat() + "Z"
        return result
        
    except ImportError as e:
        return {
            "test": "onedrive_access",
            "success": False,
            "error": f"Graph client module not available: {str(e)}",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    except Exception as e:
        logger.error(f"Error testing OneDrive: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"OneDrive test failed: {str(e)}"
        )


@router.post("/graph-test-all")
async def test_graph_connectivity_endpoint() -> Dict[str, Any]:
    """
    Run all Graph connectivity tests (safe, non-destructive).
    
    Comprehensive test that runs:
        1. Configuration check
        2. Authentication test
        3. OneDrive access test
    
    Use this for Phase 10 PoC initial validation.
    
    Returns:
        JSON with comprehensive test results
        
    Example Response:
        {
            "test": "graph_connectivity",
            "overall_success": true,
            "tests": {
                "auth": {"success": true, ...},
                "onedrive": {"success": true, ...}
            },
            "readiness_report": {...}
        }
    """
    try:
        from app.services.graph_client import test_graph_connectivity
        
        result = test_graph_connectivity()
        result["timestamp"] = datetime.utcnow().isoformat() + "Z"
        return result
        
    except ImportError as e:
        return {
            "test": "graph_connectivity",
            "overall_success": False,
            "error": f"Graph modules not available: {str(e)}",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    except Exception as e:
        logger.error(f"Error testing connectivity: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Connectivity test failed: {str(e)}"
        )


# =============================================================================
# PHASE 9 STEP 3: POC EXECUTION SURFACES (2026-03-20)
# =============================================================================
# These endpoints provide deterministic, safe PoC validation for credential day.
# All read-only tests are non-destructive and safe to run anytime.
# Write tests require explicit parameters and are clearly documented.
# =============================================================================

@router.post("/poc-run-readonly")
async def run_poc_readonly_tests(
    test_file_path: Optional[str] = None,
    test_file_id: Optional[str] = None,
    test_worksheet: Optional[str] = None
) -> Dict[str, Any]:
    """
    Run Phase 10 PoC read-only validation tests.
    
    SAFE: This endpoint is completely NON-DESTRUCTIVE.
    
    Runs in sequence:
        1. Configuration check
        2. Authentication test
        3. Drive access test
        4. Base folder check
        5. Subfolder structure check
        6. Sample file read (if test_file_path provided)
        7. Worksheet read (if test_file_id and test_worksheet provided)
    
    Args (query params):
        test_file_path: Optional path to test Excel file (relative to base folder)
        test_file_id: Optional file ID for deep worksheet tests
        test_worksheet: Optional worksheet name for data read test
    
    Returns:
        JSON with test results:
        {
            "timestamp": "...",
            "all_passed": true/false,
            "read_only_passed": true/false,
            "write_tests_run": false,
            "steps": [...],
            "summary": "...",
            "passed_count": N,
            "failed_count": N
        }
    
    Example usage:
        # Basic test (no file access)
        POST /api/system/poc-run-readonly
        
        # With file test
        POST /api/system/poc-run-readonly?test_file_path=staff/test.xlsx
    """
    try:
        from app.services.poc_executor import run_read_only_tests
        
        result = run_read_only_tests(
            test_file_path=test_file_path,
            test_file_id=test_file_id,
            test_worksheet=test_worksheet
        )
        return result.to_dict()
        
    except ImportError as e:
        return {
            "all_passed": False,
            "error": f"PoC executor not available: {str(e)}",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    except Exception as e:
        logger.error(f"Error running read-only tests: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"PoC read-only tests failed: {str(e)}"
        )


@router.post("/poc-run-full")
async def run_poc_full_validation(
    test_file_path: Optional[str] = None,
    include_write_tests: bool = False,
    write_file_id: Optional[str] = None,
    write_worksheet: Optional[str] = None,
    write_dry_run: bool = True
) -> Dict[str, Any]:
    """
    Run complete Phase 10 PoC validation sequence.
    
    SAFETY WARNING for write tests:
        - Write tests require include_write_tests=true
        - Write tests are DRY RUN by default (write_dry_run=true)
        - To actually write, set write_dry_run=false
        - write_file_id and write_worksheet are required for write tests
    
    Runs in sequence:
        1. All read-only tests (see /poc-run-readonly)
        2. [Optional] Write test (if include_write_tests=true)
        3. [Optional] ETag conflict test (if include_write_tests=true)
    
    Args (query params):
        test_file_path: Optional path to test Excel file for read tests
        include_write_tests: Whether to include write tests (default: false)
        write_file_id: File ID for write tests (required if include_write_tests)
        write_worksheet: Worksheet for write tests (required if include_write_tests)
        write_dry_run: If true, write tests validate without writing (default: true)
    
    Returns:
        JSON with complete test results
    
    Example usage:
        # Read-only (safe)
        POST /api/system/poc-run-full
        
        # With write dry run (validates capability)
        POST /api/system/poc-run-full?include_write_tests=true&write_file_id=XXX&write_worksheet=Sheet1
        
        # With actual write (MODIFIES DATA)
        POST /api/system/poc-run-full?include_write_tests=true&write_file_id=XXX&write_worksheet=Sheet1&write_dry_run=false
    """
    try:
        from app.services.poc_executor import run_poc_validation
        
        # Validate write parameters
        if include_write_tests and not (write_file_id and write_worksheet):
            return {
                "all_passed": False,
                "error": "write_file_id and write_worksheet required when include_write_tests=true",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        
        result = run_poc_validation(
            include_write_tests=include_write_tests,
            write_file_id=write_file_id,
            write_worksheet=write_worksheet,
            test_file_path=test_file_path,
            write_dry_run=write_dry_run
        )
        
        # Add safety warning if write tests will execute
        response = result.to_dict()
        if include_write_tests and not write_dry_run:
            response["SAFETY_WARNING"] = "Write tests executed with write_dry_run=false - data may have been modified"
        
        return response
        
    except ImportError as e:
        return {
            "all_passed": False,
            "error": f"PoC executor not available: {str(e)}",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    except Exception as e:
        logger.error(f"Error running full PoC: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"PoC validation failed: {str(e)}"
        )


@router.get("/poc-config-assumptions")
async def get_poc_config_assumptions() -> Dict[str, Any]:
    """
    Get documented configuration assumptions for Phase 10 PoC.
    
    Returns all hardcoded assumptions that the client environment must satisfy,
    including environment variables, folder structure, and file naming conventions.
    
    Use this to prepare the client environment before credential day.
    
    Returns:
        JSON with documented assumptions:
        {
            "environment_variables": {...},
            "azure_ad_permissions": {...},
            "folder_structure": {...},
            "excel_file_expectations": {...}
        }
    """
    try:
        from app.services.poc_executor import get_configuration_assumptions
        
        assumptions = get_configuration_assumptions()
        assumptions["timestamp"] = datetime.utcnow().isoformat() + "Z"
        return assumptions
        
    except ImportError as e:
        return {
            "error": f"PoC executor not available: {str(e)}",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    except Exception as e:
        logger.error(f"Error getting config assumptions: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get config assumptions: {str(e)}"
        )
