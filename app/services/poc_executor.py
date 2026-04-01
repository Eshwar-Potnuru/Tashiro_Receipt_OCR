"""
Phase 10 PoC Executor Service (Phase 9 Step 3)

This module provides a deterministic, safe, and well-documented execution
path for Phase 10 live PoC validation. It defines the exact sequence of
tests to run when Microsoft 365 credentials are provided.

Key Design Principles:
    - Non-destructive by default (all read-only tests run first)
    - Write tests are opt-in with explicit approval required
    - Clear separation between validation phases
    - Structured failure classification for fast diagnosis
    - No production behavior changes
    - Easy to run on credential day

Usage:
    from app.services.poc_executor import (
        run_poc_validation,
        run_read_only_tests,
        run_write_tests,
        PoCResult,
    )
    
    # Run all read-only validations
    result = run_read_only_tests()
    
    # If read-only tests pass, optionally run write test
    if result.all_passed and explicitly_approved:
        write_result = run_write_tests(test_file_id, test_worksheet)
    
    # Or run complete PoC sequence
    full_result = run_poc_validation(include_write_tests=False)

Author: Phase 9 Step 3 - Live PoC Execution Preparation
Date: 2026-03-20
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Any, Optional


logger = logging.getLogger(__name__)


# =============================================================================
# FAILURE CLASSIFICATION
# =============================================================================

class FailureCategory(Enum):
    """
    Categorized failure modes for fast diagnosis on PoC day.
    
    Each category maps to a specific remediation path.
    """
    CONFIG_MISSING = "config_missing"
    CONFIG_PLACEHOLDER = "config_placeholder"
    AUTH_INVALID_TENANT = "auth_invalid_tenant"
    AUTH_INVALID_CLIENT = "auth_invalid_client"
    AUTH_INVALID_SECRET = "auth_invalid_secret"
    AUTH_PERMISSION_DENIED = "auth_permission_denied"
    DRIVE_ACCESS_DENIED = "drive_access_denied"
    DRIVE_USER_NOT_FOUND = "drive_user_not_found"
    FOLDER_NOT_FOUND = "folder_not_found"
    FOLDER_NOT_A_FOLDER = "folder_not_a_folder"
    FILE_NOT_FOUND = "file_not_found"
    FILE_NOT_EXCEL = "file_not_excel"
    WORKSHEET_NOT_FOUND = "worksheet_not_found"
    GRAPH_THROTTLED = "graph_throttled"
    GRAPH_TIMEOUT = "graph_timeout"
    GRAPH_SERVER_ERROR = "graph_server_error"
    WRITE_CONFLICT = "write_conflict"
    WRITE_PERMISSION_DENIED = "write_permission_denied"
    UNKNOWN = "unknown"


def classify_failure(error: Exception, context: str = None) -> FailureCategory:
    """
    Classify an exception into a failure category for diagnosis.
    
    Args:
        error: The exception that occurred
        context: Optional context about what operation was attempted
        
    Returns:
        FailureCategory enum value
    """
    error_str = str(error).lower()
    
    # Check for Graph API errors with status codes
    from app.services.graph_client import GraphAPIError
    if isinstance(error, GraphAPIError):
        if error.status_code == 401:
            if "invalid_client" in error_str:
                return FailureCategory.AUTH_INVALID_CLIENT
            elif "invalid_tenant" in error_str or "tenant" in error_str:
                return FailureCategory.AUTH_INVALID_TENANT
            return FailureCategory.AUTH_PERMISSION_DENIED
        elif error.status_code == 403:
            if "drive" in context if context else False:
                return FailureCategory.DRIVE_ACCESS_DENIED
            return FailureCategory.AUTH_PERMISSION_DENIED
        elif error.status_code == 404:
            if "user" in error_str or "mailbox" in error_str:
                return FailureCategory.DRIVE_USER_NOT_FOUND
            elif "folder" in (context or ""):
                return FailureCategory.FOLDER_NOT_FOUND
            elif "file" in (context or "") or "item" in error_str:
                return FailureCategory.FILE_NOT_FOUND
            elif "worksheet" in (context or ""):
                return FailureCategory.WORKSHEET_NOT_FOUND
            return FailureCategory.FILE_NOT_FOUND
        elif error.status_code == 412:
            return FailureCategory.WRITE_CONFLICT
        elif error.status_code == 429:
            return FailureCategory.GRAPH_THROTTLED
        elif error.status_code >= 500:
            return FailureCategory.GRAPH_SERVER_ERROR
    
    # Check for ValueError (configuration issues)
    if isinstance(error, ValueError):
        if "placeholder" in error_str:
            return FailureCategory.CONFIG_PLACEHOLDER
        elif "not set" in error_str or "missing" in error_str:
            return FailureCategory.CONFIG_MISSING
    
    # Check for timeout
    if "timeout" in error_str or "timed out" in error_str:
        return FailureCategory.GRAPH_TIMEOUT
    
    # Check for worksheet not found
    if "worksheet" in error_str and "not found" in error_str:
        return FailureCategory.WORKSHEET_NOT_FOUND
    
    return FailureCategory.UNKNOWN


def get_failure_remediation(category: FailureCategory) -> str:
    """
    Get remediation guidance for a failure category.
    
    Args:
        category: The failure category
        
    Returns:
        Human-readable remediation guidance
    """
    remediation_map = {
        FailureCategory.CONFIG_MISSING: 
            "Set the missing environment variable. Check .env file.",
        FailureCategory.CONFIG_PLACEHOLDER:
            "Replace placeholder value with real credential. Check for 'your-' or '-here' patterns.",
        FailureCategory.AUTH_INVALID_TENANT:
            "Verify MICROSOFT_TENANT_ID is correct. Format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        FailureCategory.AUTH_INVALID_CLIENT:
            "Verify MICROSOFT_CLIENT_ID matches Azure AD app registration.",
        FailureCategory.AUTH_INVALID_SECRET:
            "Verify MICROSOFT_CLIENT_SECRET is valid and not expired.",
        FailureCategory.AUTH_PERMISSION_DENIED:
            "Check Azure AD app has required permissions: Files.ReadWrite.All, User.Read.All",
        FailureCategory.DRIVE_ACCESS_DENIED:
            "App doesn't have permission to access the user's OneDrive. Grant Files.ReadWrite.All.",
        FailureCategory.DRIVE_USER_NOT_FOUND:
            "MICROSOFT_USER_ID doesn't match a valid user. Use email or object ID.",
        FailureCategory.FOLDER_NOT_FOUND:
            "ONEDRIVE_BASE_FOLDER doesn't exist on OneDrive. Create the folder first.",
        FailureCategory.FOLDER_NOT_A_FOLDER:
            "ONEDRIVE_BASE_FOLDER path exists but is a file, not a folder.",
        FailureCategory.FILE_NOT_FOUND:
            "Excel file not found at expected path. Check folder structure.",
        FailureCategory.FILE_NOT_EXCEL:
            "File exists but is not a valid Excel workbook.",
        FailureCategory.WORKSHEET_NOT_FOUND:
            "Worksheet name doesn't match expected format. Check month sheet naming (YYYYMM).",
        FailureCategory.GRAPH_THROTTLED:
            "Rate limited by Graph API. Wait and retry in a few minutes.",
        FailureCategory.GRAPH_TIMEOUT:
            "Request timed out. Check network connectivity. May be transient.",
        FailureCategory.GRAPH_SERVER_ERROR:
            "Microsoft Graph API server error. Usually transient. Retry later.",
        FailureCategory.WRITE_CONFLICT:
            "File was modified concurrently. ETag conflict. Normal during concurrent access.",
        FailureCategory.WRITE_PERMISSION_DENIED:
            "File is read-only or user lacks write permission.",
        FailureCategory.UNKNOWN:
            "Unexpected error. Check detailed error message and logs.",
    }
    return remediation_map.get(category, "Unknown failure. Check logs.")


# =============================================================================
# RESULTS
# =============================================================================

@dataclass
class TestStep:
    """Result of a single test step."""
    name: str
    passed: bool
    error: Optional[str] = None
    failure_category: Optional[FailureCategory] = None
    details: Dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    is_read_only: bool = True
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "error": self.error,
            "failure_category": self.failure_category.value if self.failure_category else None,
            "remediation": get_failure_remediation(self.failure_category) if self.failure_category else None,
            "details": self.details,
            "duration_ms": self.duration_ms,
            "is_read_only": self.is_read_only,
        }


@dataclass
class PoCResult:
    """Complete PoC validation result."""
    timestamp: str
    all_passed: bool
    read_only_passed: bool
    write_tests_passed: Optional[bool]  # None if not run
    write_tests_run: bool
    steps: List[TestStep]
    summary: str
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "all_passed": self.all_passed,
            "read_only_passed": self.read_only_passed,
            "write_tests_passed": self.write_tests_passed,
            "write_tests_run": self.write_tests_run,
            "steps": [s.to_dict() for s in self.steps],
            "summary": self.summary,
            "passed_count": sum(1 for s in self.steps if s.passed),
            "failed_count": sum(1 for s in self.steps if not s.passed),
            "total_count": len(self.steps),
        }


# =============================================================================
# POC VALIDATION STEPS (READ-ONLY)
# =============================================================================

def _step_config_check() -> TestStep:
    """
    Step 1: Configuration readiness check.
    
    Verifies all required environment variables are set and not placeholders.
    """
    import time
    start = time.time()
    
    try:
        from app.services.graph_auth import (
            is_graph_fully_configured,
            get_graph_readiness_report
        )
        
        report = get_graph_readiness_report()
        configured = is_graph_fully_configured()
        
        if configured:
            return TestStep(
                name="config_check",
                passed=True,
                details={
                    "readiness": report["readiness"],
                    "ready_items": report["ready_items"]
                },
                duration_ms=int((time.time() - start) * 1000),
                is_read_only=True
            )
        else:
            return TestStep(
                name="config_check",
                passed=False,
                error=f"Configuration incomplete: {', '.join(report['blockers'])}",
                failure_category=FailureCategory.CONFIG_MISSING,
                details={
                    "blockers": report["blockers"],
                    "config_status": report["config_status"]
                },
                duration_ms=int((time.time() - start) * 1000),
                is_read_only=True
            )
    except Exception as e:
        return TestStep(
            name="config_check",
            passed=False,
            error=str(e),
            failure_category=classify_failure(e, "config"),
            duration_ms=int((time.time() - start) * 1000),
            is_read_only=True
        )


def _step_auth_test() -> TestStep:
    """
    Step 2: Authentication test.
    
    Acquires an OAuth token using client credentials flow.
    """
    import time
    start = time.time()
    
    try:
        from app.services.graph_auth import test_graph_auth
        
        result = test_graph_auth()
        
        if result["success"]:
            return TestStep(
                name="auth_test",
                passed=True,
                details={
                    "token_acquired": True,
                    "message": result["details"].get("message")
                },
                duration_ms=int((time.time() - start) * 1000),
                is_read_only=True
            )
        else:
            error_msg = result.get("error", "Unknown auth error")
            return TestStep(
                name="auth_test",
                passed=False,
                error=error_msg,
                failure_category=classify_failure(Exception(error_msg), "auth"),
                details=result.get("details", {}),
                duration_ms=int((time.time() - start) * 1000),
                is_read_only=True
            )
    except Exception as e:
        return TestStep(
            name="auth_test",
            passed=False,
            error=str(e),
            failure_category=classify_failure(e, "auth"),
            duration_ms=int((time.time() - start) * 1000),
            is_read_only=True
        )


def _step_drive_access() -> TestStep:
    """
    Step 3: OneDrive access test.
    
    Verifies we can access the user's drive.
    """
    import time
    start = time.time()
    
    try:
        from app.services.graph_client import graph_get, get_user_id
        
        user_id = get_user_id()
        drive_info = graph_get(f"users/{user_id}/drive", timeout=30)
        
        return TestStep(
            name="drive_access",
            passed=True,
            details={
                "drive_id": drive_info.get("id"),
                "drive_name": drive_info.get("name"),
                "drive_type": drive_info.get("driveType")
            },
            duration_ms=int((time.time() - start) * 1000),
            is_read_only=True
        )
    except Exception as e:
        return TestStep(
            name="drive_access",
            passed=False,
            error=str(e),
            failure_category=classify_failure(e, "drive"),
            duration_ms=int((time.time() - start) * 1000),
            is_read_only=True
        )


def _step_base_folder_check() -> TestStep:
    """
    Step 4: Base folder existence check.
    
    Verifies ONEDRIVE_BASE_FOLDER exists and is a folder.
    """
    import time
    start = time.time()
    
    try:
        from app.services.graph_client import graph_get, get_user_id, get_base_folder
        
        user_id = get_user_id()
        base_folder = get_base_folder()
        
        folder_info = graph_get(f"users/{user_id}/drive/root:/{base_folder}", timeout=30)
        
        if folder_info.get("folder"):
            return TestStep(
                name="base_folder_check",
                passed=True,
                details={
                    "folder_name": folder_info.get("name"),
                    "folder_id": folder_info.get("id"),
                    "child_count": folder_info.get("folder", {}).get("childCount", 0)
                },
                duration_ms=int((time.time() - start) * 1000),
                is_read_only=True
            )
        else:
            return TestStep(
                name="base_folder_check",
                passed=False,
                error=f"Path '{base_folder}' is not a folder",
                failure_category=FailureCategory.FOLDER_NOT_A_FOLDER,
                duration_ms=int((time.time() - start) * 1000),
                is_read_only=True
            )
    except Exception as e:
        return TestStep(
            name="base_folder_check",
            passed=False,
            error=str(e),
            failure_category=classify_failure(e, "folder"),
            duration_ms=int((time.time() - start) * 1000),
            is_read_only=True
        )


def _step_subfolder_structure_check() -> TestStep:
    """
    Step 5: Expected subfolder structure check.
    
    Verifies 'staff' and 'locations' subfolders exist (or can be created).
    This is a soft check - missing folders can be created.
    """
    import time
    start = time.time()
    
    try:
        from app.services.graph_client import graph_get, get_user_id, get_base_folder
        from app.config.onedrive_structure import STAFF_FOLDER, LOCATION_FOLDER
        
        user_id = get_user_id()
        base_folder = get_base_folder()
        
        # Check staff folder
        staff_exists = False
        locations_exists = False
        
        try:
            staff_path = f"{base_folder}/{STAFF_FOLDER}"
            graph_get(f"users/{user_id}/drive/root:/{staff_path}", timeout=30)
            staff_exists = True
        except:
            pass
        
        try:
            locations_path = f"{base_folder}/{LOCATION_FOLDER}"
            graph_get(f"users/{user_id}/drive/root:/{locations_path}", timeout=30)
            locations_exists = True
        except:
            pass
        
        # Both exist = passed, otherwise warning
        if staff_exists and locations_exists:
            return TestStep(
                name="subfolder_structure_check",
                passed=True,
                details={
                    "staff_folder_exists": True,
                    "locations_folder_exists": True,
                    "message": "Required subfolders exist"
                },
                duration_ms=int((time.time() - start) * 1000),
                is_read_only=True
            )
        else:
            # Not a hard failure - folders can be created
            return TestStep(
                name="subfolder_structure_check",
                passed=True,  # Soft pass with warning
                details={
                    "staff_folder_exists": staff_exists,
                    "locations_folder_exists": locations_exists,
                    "warning": "Some subfolders missing - will be created on first write"
                },
                duration_ms=int((time.time() - start) * 1000),
                is_read_only=True
            )
            
    except Exception as e:
        return TestStep(
            name="subfolder_structure_check",
            passed=False,
            error=str(e),
            failure_category=classify_failure(e, "folder"),
            duration_ms=int((time.time() - start) * 1000),
            is_read_only=True
        )


def _step_sample_file_read(test_file_path: Optional[str] = None) -> TestStep:
    """
    Step 6: Sample Excel file read test.
    
    If a test file path is provided, attempts to read its worksheet list.
    Otherwise skips with a note.
    
    Args:
        test_file_path: Optional path to a test Excel file relative to base folder
    """
    import time
    start = time.time()
    
    if not test_file_path:
        return TestStep(
            name="sample_file_read",
            passed=True,
            details={
                "skipped": True,
                "reason": "No test file specified",
                "note": "To test: provide test_file_path parameter"
            },
            duration_ms=int((time.time() - start) * 1000),
            is_read_only=True
        )
    
    try:
        from app.services.onedrive_file_manager import get_file_id, get_file_metadata
        from app.services.excel_reader import get_worksheet_names
        
        # Get file ID
        file_id = get_file_id(test_file_path)
        
        # Get metadata
        metadata = get_file_metadata(file_id)
        
        # Get worksheet names
        worksheets = get_worksheet_names(file_id)
        
        return TestStep(
            name="sample_file_read",
            passed=True,
            details={
                "file_path": test_file_path,
                "file_id": file_id,
                "file_name": metadata.get("name"),
                "file_size": metadata.get("size"),
                "worksheet_count": len(worksheets),
                "worksheet_names": worksheets[:5],  # First 5 only
            },
            duration_ms=int((time.time() - start) * 1000),
            is_read_only=True
        )
    except Exception as e:
        return TestStep(
            name="sample_file_read",
            passed=False,
            error=str(e),
            failure_category=classify_failure(e, "file"),
            details={"test_file_path": test_file_path},
            duration_ms=int((time.time() - start) * 1000),
            is_read_only=True
        )


def _step_worksheet_read(file_id: str = None, worksheet_name: str = None) -> TestStep:
    """
    Step 7: Worksheet data read test.
    
    If file_id and worksheet_name provided, reads sample data.
    """
    import time
    start = time.time()
    
    if not file_id or not worksheet_name:
        return TestStep(
            name="worksheet_read",
            passed=True,
            details={
                "skipped": True,
                "reason": "No file_id/worksheet_name specified"
            },
            duration_ms=int((time.time() - start) * 1000),
            is_read_only=True
        )
    
    try:
        from app.services.excel_reader import get_used_range_address, get_last_used_row
        
        # Get used range
        used_range = get_used_range_address(file_id, worksheet_name)
        
        # Get last row
        last_row = get_last_used_row(file_id, worksheet_name)
        
        return TestStep(
            name="worksheet_read",
            passed=True,
            details={
                "file_id": file_id,
                "worksheet_name": worksheet_name,
                "used_range": used_range,
                "last_used_row": last_row,
            },
            duration_ms=int((time.time() - start) * 1000),
            is_read_only=True
        )
    except Exception as e:
        return TestStep(
            name="worksheet_read",
            passed=False,
            error=str(e),
            failure_category=classify_failure(e, "worksheet"),
            details={
                "file_id": file_id,
                "worksheet_name": worksheet_name
            },
            duration_ms=int((time.time() - start) * 1000),
            is_read_only=True
        )


# =============================================================================
# POC VALIDATION STEPS (WRITE - REQUIRES EXPLICIT APPROVAL)
# =============================================================================

def _step_write_test(
    file_id: str,
    worksheet_name: str,
    test_row: List[Any],
    dry_run: bool = True
) -> TestStep:
    """
    Step W1: Optional write test.
    
    WARNING: This step MODIFIES DATA if dry_run=False.
    
    Writes a test row to verify write capability, then optionally deletes it.
    
    Args:
        file_id: Target file ID
        worksheet_name: Target worksheet
        test_row: Row data to write
        dry_run: If True, only validates without writing
    """
    import time
    start = time.time()
    
    if dry_run:
        return TestStep(
            name="write_test",
            passed=True,
            details={
                "dry_run": True,
                "message": "Write test skipped (dry_run=True)",
                "to_execute": f"Would write to {worksheet_name} with {len(test_row)} columns"
            },
            duration_ms=int((time.time() - start) * 1000),
            is_read_only=True  # Dry run is read-only
        )
    
    try:
        from app.services.onedrive_file_manager import get_file_metadata
        from app.services.excel_writer import append_row
        from app.services.excel_reader import get_last_used_row
        
        # Get current state
        before_row = get_last_used_row(file_id, worksheet_name)
        
        # Get ETag
        metadata = get_file_metadata(file_id)
        etag = metadata.get("eTag")
        
        # Attempt write
        new_etag = append_row(file_id, worksheet_name, test_row, etag)
        
        # Verify write
        after_row = get_last_used_row(file_id, worksheet_name)
        
        return TestStep(
            name="write_test",
            passed=True,
            details={
                "dry_run": False,
                "row_before": before_row,
                "row_after": after_row,
                "etag_updated": new_etag != etag,
                "message": "Write successful - test row appended"
            },
            duration_ms=int((time.time() - start) * 1000),
            is_read_only=False
        )
    except Exception as e:
        return TestStep(
            name="write_test",
            passed=False,
            error=str(e),
            failure_category=classify_failure(e, "write"),
            details={"dry_run": False},
            duration_ms=int((time.time() - start) * 1000),
            is_read_only=False
        )


def _step_etag_conflict_test(file_id: str, worksheet_name: str, dry_run: bool = True) -> TestStep:
    """
    Step W2: ETag conflict handling test.
    
    WARNING: This step may MODIFY DATA if dry_run=False.
    
    Deliberately uses an invalid ETag to verify 412 handling.
    
    Args:
        file_id: Target file ID
        worksheet_name: Target worksheet
        dry_run: If True, only validates without testing
    """
    import time
    start = time.time()
    
    if dry_run:
        return TestStep(
            name="etag_conflict_test",
            passed=True,
            details={
                "dry_run": True,
                "message": "ETag conflict test skipped (dry_run=True)"
            },
            duration_ms=int((time.time() - start) * 1000),
            is_read_only=True
        )
    
    try:
        from app.services.excel_writer import append_row, ETagConflictError
        
        # Use invalid ETag to force conflict
        fake_etag = '"invalid-etag-12345"'
        
        try:
            append_row(file_id, worksheet_name, ["Test"], fake_etag)
            # If no error, something is wrong
            return TestStep(
                name="etag_conflict_test",
                passed=False,
                error="Expected ETag conflict but write succeeded",
                details={"dry_run": False},
                duration_ms=int((time.time() - start) * 1000),
                is_read_only=False
            )
        except ETagConflictError:
            # This is expected behavior
            return TestStep(
                name="etag_conflict_test",
                passed=True,
                details={
                    "dry_run": False,
                    "conflict_detected": True,
                    "message": "ETag conflict correctly detected and raised"
                },
                duration_ms=int((time.time() - start) * 1000),
                is_read_only=False
            )
    except Exception as e:
        return TestStep(
            name="etag_conflict_test",
            passed=False,
            error=str(e),
            failure_category=classify_failure(e, "write"),
            details={"dry_run": False},
            duration_ms=int((time.time() - start) * 1000),
            is_read_only=False
        )


# =============================================================================
# POC RUNNER FUNCTIONS
# =============================================================================

def run_read_only_tests(
    test_file_path: Optional[str] = None,
    test_file_id: Optional[str] = None,
    test_worksheet: Optional[str] = None
) -> PoCResult:
    """
    Run all read-only PoC validation tests.
    
    This is SAFE and NON-DESTRUCTIVE.
    
    Args:
        test_file_path: Optional path to test Excel file (relative to base folder)
        test_file_id: Optional file ID for worksheet tests
        test_worksheet: Optional worksheet name for deep read tests
        
    Returns:
        PoCResult with all test results
    """
    steps = []
    
    # Step 1: Config check
    steps.append(_step_config_check())
    if not steps[-1].passed:
        return _build_result(steps, write_tests_run=False)
    
    # Step 2: Auth test
    steps.append(_step_auth_test())
    if not steps[-1].passed:
        return _build_result(steps, write_tests_run=False)
    
    # Step 3: Drive access
    steps.append(_step_drive_access())
    if not steps[-1].passed:
        return _build_result(steps, write_tests_run=False)
    
    # Step 4: Base folder check
    steps.append(_step_base_folder_check())
    if not steps[-1].passed:
        return _build_result(steps, write_tests_run=False)
    
    # Step 5: Subfolder structure
    steps.append(_step_subfolder_structure_check())
    
    # Step 6: Sample file read (optional)
    steps.append(_step_sample_file_read(test_file_path))
    
    # Step 7: Worksheet read (optional)
    steps.append(_step_worksheet_read(test_file_id, test_worksheet))
    
    return _build_result(steps, write_tests_run=False)


def run_write_tests(
    file_id: str,
    worksheet_name: str,
    test_row: List[Any] = None,
    dry_run: bool = True
) -> PoCResult:
    """
    Run write validation tests.
    
    WARNING: If dry_run=False, this MODIFIES DATA.
    
    Args:
        file_id: Target file ID
        worksheet_name: Target worksheet
        test_row: Row data to write (default: ["POC_TEST", timestamp])
        dry_run: If True, validates without writing (default: True)
        
    Returns:
        PoCResult with write test results
    """
    if test_row is None:
        test_row = ["POC_TEST", datetime.now().isoformat(), "Validation"]
    
    steps = []
    
    # Write test
    steps.append(_step_write_test(file_id, worksheet_name, test_row, dry_run))
    
    # ETag conflict test
    steps.append(_step_etag_conflict_test(file_id, worksheet_name, dry_run))
    
    return _build_result(steps, write_tests_run=not dry_run)


def run_poc_validation(
    include_write_tests: bool = False,
    write_file_id: Optional[str] = None,
    write_worksheet: Optional[str] = None,
    test_file_path: Optional[str] = None,
    write_dry_run: bool = True
) -> PoCResult:
    """
    Run complete Phase 10 PoC validation sequence.
    
    This is the main entry point for PoC day execution.
    
    Args:
        include_write_tests: Whether to include write tests (default: False)
        write_file_id: File ID for write tests (required if include_write_tests)
        write_worksheet: Worksheet for write tests (required if include_write_tests)
        test_file_path: Optional path to test file for read tests
        write_dry_run: If True, write tests validate without writing (default: True)
        
    Returns:
        Complete PoCResult
    """
    # Run read-only tests
    read_result = run_read_only_tests(test_file_path=test_file_path)
    
    if not include_write_tests:
        return read_result
    
    # Check read-only passed before write tests
    if not read_result.read_only_passed:
        return read_result
    
    # Validate write parameters
    if not write_file_id or not write_worksheet:
        read_result.steps.append(TestStep(
            name="write_validation",
            passed=False,
            error="write_file_id and write_worksheet required for write tests",
            is_read_only=True
        ))
        return _build_result(read_result.steps, write_tests_run=False)
    
    # Run write tests
    write_result = run_write_tests(
        file_id=write_file_id,
        worksheet_name=write_worksheet,
        dry_run=write_dry_run
    )
    
    # Combine results
    all_steps = read_result.steps + write_result.steps
    return _build_result(all_steps, write_tests_run=not write_dry_run)


def _build_result(steps: List[TestStep], write_tests_run: bool) -> PoCResult:
    """Build a PoCResult from test steps."""
    read_only_steps = [s for s in steps if s.is_read_only]
    write_steps = [s for s in steps if not s.is_read_only]
    
    read_only_passed = all(s.passed for s in read_only_steps)
    write_passed = all(s.passed for s in write_steps) if write_steps else None
    all_passed = read_only_passed and (write_passed if write_passed is not None else True)
    
    # Build summary
    if all_passed:
        summary = "All PoC validation tests passed"
    else:
        failed = [s.name for s in steps if not s.passed]
        summary = f"PoC validation failed: {', '.join(failed)}"
    
    return PoCResult(
        timestamp=datetime.now().isoformat(),
        all_passed=all_passed,
        read_only_passed=read_only_passed,
        write_tests_passed=write_passed,
        write_tests_run=write_tests_run,
        steps=steps,
        summary=summary
    )


# =============================================================================
# CONFIGURATION ASSUMPTIONS DOCUMENTATION
# =============================================================================

def get_configuration_assumptions() -> dict:
    """
    Get documented configuration assumptions for the PoC.
    
    Returns all hardcoded assumptions that the client environment must satisfy.
    """
    from app.config.onedrive_structure import (
        STAFF_FOLDER, LOCATION_FOLDER,
        FORMAT1_TEMPLATE_NAME, FORMAT2_TEMPLATE_NAME
    )
    
    return {
        "environment_variables": {
            "MICROSOFT_TENANT_ID": {
                "required": True,
                "format": "UUID (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)",
                "source": "Azure AD > App registrations > Directory (tenant) ID"
            },
            "MICROSOFT_CLIENT_ID": {
                "required": True,
                "format": "UUID",
                "source": "Azure AD > App registrations > Application (client) ID"
            },
            "MICROSOFT_CLIENT_SECRET": {
                "required": True,
                "format": "Client secret value",
                "source": "Azure AD > App registrations > Certificates & secrets"
            },
            "MICROSOFT_USER_ID": {
                "required": True,
                "format": "Email or Object ID",
                "source": "Microsoft 365 Admin > Users > UPN or Object ID"
            },
            "ONEDRIVE_BASE_FOLDER": {
                "required": True,
                "format": "Folder path (e.g., 'ReceiptOCR' or 'Documents/Receipts')",
                "source": "Create this folder on the user's OneDrive"
            },
            "USE_GRAPH_API_WRITERS": {
                "required": False,
                "format": "'true' or 'false'",
                "default": "false",
                "note": "Only set to 'true' after PoC passes"
            }
        },
        "azure_ad_permissions": {
            "application_permissions": [
                "Files.ReadWrite.All (required for OneDrive access)",
                "User.Read.All (required for user lookup)"
            ],
            "admin_consent": "Required for application permissions"
        },
        "folder_structure": {
            "base_folder": "Set via ONEDRIVE_BASE_FOLDER",
            "subfolders": {
                "staff": {
                    "path": f"{STAFF_FOLDER}",
                    "purpose": "Individual staff ledger files (Format①)",
                    "file_naming": "{STAFF_NAME}_{LOCATION}.xlsx"
                },
                "locations": {
                    "path": f"{LOCATION_FOLDER}",
                    "purpose": "Location aggregate ledger files (Format②)",
                    "file_naming": "{LOCATION}_Accumulated.xlsx"
                }
            },
            "note": "Subfolders are created automatically on first write"
        },
        "excel_file_expectations": {
            "format1_template": FORMAT1_TEMPLATE_NAME,
            "format2_template": FORMAT2_TEMPLATE_NAME,
            "worksheet_naming": "Monthly sheets named as YYYYMM (e.g., '202603')",
            "note": "Template sheets should exist in OneDrive or be created"
        }
    }
