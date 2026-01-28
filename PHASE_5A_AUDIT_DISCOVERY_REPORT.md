# Phase 5A: Audit Trail & Compliance - Discovery Report
**Receipt OCR System (Tashiro Iron Works)**  
**Date:** January 27, 2026  
**Status:** Discovery Complete - NO CODE CHANGES

---

## Executive Summary

This report maps the complete "send" lifecycle in the Receipt OCR system to identify optimal insertion points for immutable audit logging. The system currently has **NO user authentication** and **NO audit trail**. All operations are anonymous and untracked.

**Key Findings:**
- Γ£à Clean 3-layer architecture (API ΓåÆ Service ΓåÆ Excel)
- Γ£à Well-defined state transitions (DRAFT ΓåÆ SENT)
- Γ£à Comprehensive error handling with isolation
- Γ¥î **NO actor/user context** - all operations are anonymous
- Γ¥î **NO audit logging** - state changes are untracked
- Γ¥î **NO Excel write traceability** - cannot link drafts to specific Excel rows

**Recommendation:** Implement audit logging at **DraftService layer** with 6 event types covering entire lifecycle.

---

## 1. Send Flow Entry Points & Call Chain

### 1.1 Complete Call Chain

```
ΓöîΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÉ
Γöé LAYER 1: API ENDPOINT (HTTP Boundary)                          Γöé
Γöé File: app/api/drafts.py                                        Γöé
Γöé Function: send_drafts() [Lines 355-424]                        Γöé
Γöé                                                                 Γöé
Γöé Input:  SendDraftsRequest {draft_ids: List[UUID]}             Γöé
Γöé Output: SendDraftsResponse {total, sent, failed, results[]}   Γöé
Γöé                                                                 Γöé
Γöé Error Handling: HTTPException (500) on complete failure        Γöé
ΓööΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÿ
                              Γåô
ΓöîΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÉ
Γöé LAYER 2: SERVICE LAYER (Business Logic + Validation)          Γöé
Γöé File: app/services/draft_service.py                           Γöé
Γöé Function: send_drafts() [Lines 215-434]                       Γöé
Γöé                                                                Γöé
Γöé Responsibilities:                                              Γöé
Γöé   1. Load drafts from repository (get_by_ids)                 Γöé
Γöé   2. Validate all are in DRAFT state                          Γöé
Γöé   3. Run READY-TO-SEND validation (_validate_ready_to_send)   Γöé
Γöé   4. Call SummaryService.send_receipts() [PHASE 3 BOUNDARY]   Γöé
Γöé   5. Mark successfully sent drafts as SENT                     Γöé
Γöé   6. Handle partial failures gracefully                        Γöé
Γöé                                                                Γöé
Γöé State Transition: draft.mark_as_sent() [Line 398]             Γöé
Γöé   - Sets status = SENT                                         Γöé
Γöé   - Sets sent_at = datetime.now()                              Γöé
Γöé                                                                Γöé
Γöé Critical Validation: _validate_ready_to_send() [Lines 461-579]Γöé
Γöé   - Enforces READY-TO-SEND contract                            Γöé
Γöé   - Returns (is_valid, error_messages)                         Γöé
Γöé   - Checks: location, staff, amounts, date, vendor, image_ref  Γöé
ΓööΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÿ
                              Γåô
ΓöîΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÉ
Γöé LAYER 3: SUMMARY SERVICE (Phase 3 Boundary)                   Γöé
Γöé File: app/services/summary_service.py                         Γöé
Γöé Function: send_receipts() [Lines 23-74]                       Γöé
Γöé                                                                Γöé
Γöé Responsibilities:                                              Γöé
Γöé   1. Sort receipts by date (deterministic ordering)            Γöé
Γöé   2. Call BranchLedgerWriter.write_receipt() (Format 02)       Γöé
Γöé   3. Call StaffLedgerWriter.write_receipt() (Format 01)        Γöé
Γöé   4. Isolate failures (one writer cannot block the other)      Γöé
Γöé                                                                Γöé
Γöé Output: {processed, counts, results[]}                         Γöé
Γöé   - results[i].branch: {status, location, row}                 Γöé
Γöé   - results[i].staff: {status, staff_id, row}                  Γöé
ΓööΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÿ
                              Γåô
ΓöîΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÉ
Γöé LAYER 4: EXCEL WRITERS (Persistence Boundary)                 Γöé
Γöé Files: app/excel/branch_ledger_writer.py                      Γöé
Γöé        app/excel/staff_ledger_writer.py                       Γöé
Γöé Function: write_receipt() [Lines 33-95 in each]               Γöé
Γöé                                                                Γöé
Γöé Responsibilities:                                              Γöé
Γöé   1. Open workbook (or recreate if corrupted)                  Γöé
Γöé   2. Get or create month sheet (YYYYσ╣┤Mµ£ê)                     Γöé
Γöé   3. Check for duplicate invoice_number                        Γöé
Γöé   4. Find next empty row (_find_next_empty_row)                Γöé
Γöé   5. Write receipt data to row (_write_row)                    Γöé
Γöé   6. Save workbook                                             Γöé
Γöé                                                                Γöé
Γöé Return: {status, location/staff_id, row} or {status, error}   Γöé
Γöé   - status: "written" | "skipped_duplicate" | "error"          Γöé
Γöé   - row: Excel row number where data was written               Γöé
ΓööΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÿ
```

### 1.2 Detailed File Locations

**API Layer:**
- **File:** `app/api/drafts.py`
- **Endpoint:** `POST /api/drafts/send`
- **Function:** `send_drafts(request: SendDraftsRequest)` [Lines 355-424]
- **Inputs:** `SendDraftsRequest {draft_ids: List[UUID]}`
- **Returns:** `SendDraftsResponse {total, sent, failed, results[]}`

**Service Layer:**
- **File:** `app/services/draft_service.py`
- **Function:** `send_drafts(draft_ids: List[UUID])` [Lines 215-434]
- **Validation:** `_validate_ready_to_send(draft)` [Lines 461-579]
- **State Transition:** `draft.mark_as_sent()` [Called at line 398]
  - Located in: `app/models/draft.py` [Lines 166-185]
  - Sets: `status = SENT`, `sent_at = datetime.now()`

**Summary Service (Phase 3 Boundary):**
- **File:** `app/services/summary_service.py`
- **Function:** `send_receipts(receipts)` [Lines 23-74]
- **Called at:** `draft_service.py` line 348
- **Returns:** Per-receipt results with Excel write status

**Excel Writers:**
- **Branch (Format 02):** `app/excel/branch_ledger_writer.py`
  - `write_receipt()` [Lines 33-95]
- **Staff (Format 01):** `app/excel/staff_ledger_writer.py`
  - `write_receipt()` [Lines 33-95]

---

## 2. User/Actor Context Analysis

### 2.1 Current State: NO USER CONTEXT EXISTS

**Finding:** The system has **NO authentication, authorization, or user tracking**.

**Evidence:**
1. **No FastAPI dependencies for auth:**
   - No `Depends(get_current_user)` in any endpoint
   - No JWT tokens, session cookies, or OAuth
   - All endpoints are publicly accessible

2. **No user fields in models:**
   - `DraftReceipt` model: No `created_by`, `updated_by`, or `sent_by` fields
   - `Receipt` model: No user identification
   - Database schema: No `user_id` column in `draft_receipts` table

3. **No request context tracking:**
   - No middleware capturing IP address or session
   - No logging of who performed operations
   - No audit trail of any kind

### 2.2 Implications

**Current Behavior:**
- Γ£à Drafts can be created anonymously
- Γ£à Drafts can be edited by anyone
- Γ£à Drafts can be sent to Excel by anyone
- Γ¥î Cannot answer "Who sent this receipt?"
- Γ¥î Cannot answer "Who created this draft?"
- Γ¥î Cannot answer "Who last edited this draft?"

**For Phase 5A Audit Trail:**
- **Option 1:** Record "actor = ANONYMOUS" for all operations
- **Option 2:** Add basic session tracking (IP address, timestamp)
- **Option 3:** Defer user auth to Phase 5B, use "SYSTEM" as actor

**Recommendation:** Use **"SYSTEM"** as actor for Phase 5A. This allows audit logging to proceed without blocking on authentication implementation. Phase 5B can retrofit user identification later.

---

## 3. Available Data at Send Time

### 3.1 Draft Data (Complete)

**Source:** `DraftReceipt` model loaded from repository

```python
# Available at: draft_service.py line 290-293
drafts = self.repository.get_by_ids(draft_ids)

# Each draft contains:
draft.draft_id          # UUID - unique draft identifier
draft.status            # "DRAFT" or "SENT"
draft.created_at        # datetime - when draft was first created
draft.updated_at        # datetime - last modification timestamp
draft.sent_at           # datetime | None - when marked as SENT
draft.image_ref         # str | None - links to uploaded image (queue_id)
```

### 3.2 Receipt Data (Complete)

**Source:** `draft.receipt` (canonical Receipt model)

```python
# Available at: draft_service.py line 343
receipts = [draft.receipt for draft in drafts_to_send]

# Each receipt contains:
receipt.vendor_name              # str
receipt.receipt_date             # str (ISO format YYYY-MM-DD)
receipt.total_amount             # float
receipt.tax_10_amount            # float
receipt.tax_8_amount             # float
receipt.invoice_number           # str
receipt.business_location_id     # str (e.g., "Aichi", "Kashima")
receipt.staff_id                 # str (e.g., "aic_001", "kas_002")

# Additional fields if present:
receipt.diagnostics              # Dict with image_format, OCR metadata
receipt.subtotal_before_tax      # float (calculated)
receipt.payment_method           # str
receipt.memo                     # str
```

### 3.3 Excel Write Results (Partial)

**Source:** `summary_result` from `SummaryService.send_receipts()`

```python
# Available at: draft_service.py line 348
summary_result = self.summary_service.send_receipts(receipts)

# Contains:
summary_result["processed"]      # int - number of receipts processed
summary_result["counts"]         # Dict {success, skipped, error}
summary_result["results"]        # List of per-receipt results

# Per-receipt result structure:
excel_result = {
    "receipt_id": "...",
    "branch": {
        "status": "written" | "skipped_duplicate" | "error",
        "location": "Aichi",
        "row": 42  # Excel row number where data was written
    },
    "staff": {
        "status": "written" | "skipped_duplicate" | "error",
        "staff_id": "aic_001",
        "row": 15  # Excel row number where data was written
    }
}
```

### 3.4 Data Gaps for Audit Trail

**Missing Data Points:**
1. Γ¥î **Actor/User:** Who initiated the send operation
2. Γ¥î **Request Context:** Client IP, user agent, session ID
3. Γ¥î **Excel File Paths:** Cannot determine which specific Excel file was written to
4. Γ¥î **Validation Failures:** History of drafts that failed validation
5. Γ¥î **Edit History:** Cannot see what changed between draft saves

**Excel Traceability Issue:**
- We get `row` number (e.g., row 42) from Excel writer
- We do NOT get the file path or sheet name in the result
- File path is determined internally by: `template_loader.ensure_location_workbook(location_id)`
- Sheet name is determined by: `_month_sheet_name(receipt_date)` ΓåÆ "2026σ╣┤1µ£ê"

**Recommendation:** Enhance Excel write results to include:
- `file_path`: Full path to the Excel file
- `sheet_name`: Name of the sheet where data was written
- This data is already available inside the writers, just not returned

---

## 4. Existing Logging & Error Handling

### 4.1 Current Logging Behavior

**API Layer (app/api/drafts.py):**
- Γ¥î No explicit logging in `send_drafts()` endpoint
- Γ£à HTTPException raised on complete failure (line 420-423)
- Γ¥î Success/failure not logged

**Service Layer (app/services/draft_service.py):**
- Γ¥î No logging in `send_drafts()` method
- Γ¥î State transitions not logged
- Γ¥î Validation failures not logged
- Γ£à Exceptions caught and returned in results dict (lines 348-361, 398-411)

**Summary Service (app/services/summary_service.py):**
- Γ¥î No logging in `send_receipts()` method
- Γ£à Defensive exception handling with `_safe_write()` (lines 69-72)

**Excel Writers (app/excel/branch_ledger_writer.py):**
- Γ£à **Comprehensive logging present:**
  - Line 43: Warning on corrupted workbook
  - Line 53: Info on receipt date and target sheet
  - Line 58: Info on sheet usage
  - Line 61: Warning on duplicate invoice
  - Line 68: Info on write row
  - Line 74: Info on successful write
  - Line 77-80: Info on save operation
  - Line 82: Error on permission denied
  - Line 88: Error on validation failure
  - Line 91: Exception logging with context

**Staff Writer has identical logging pattern.**

### 4.2 Exception Handling Analysis

**Isolation Strategy:**
```
API Layer ΓåÆ Catches all exceptions ΓåÆ Returns 500 HTTP error
  Γåô
Service Layer ΓåÆ Catches per-draft exceptions ΓåÆ Returns {"status": "error", "error": msg}
  Γåô
Summary Service ΓåÆ Catches per-receipt exceptions ΓåÆ Returns {"status": "error", "error": msg}
  Γåô
Excel Writers ΓåÆ Catches all exceptions ΓåÆ Returns {"status": "error", "error": msg}
```

**Key Properties:**
1. Γ£à **Partial failure support:** One draft failure doesn't block others
2. Γ£à **Error isolation:** Excel writer failures don't crash the service
3. Γ£à **Detailed error messages:** Exceptions are caught and returned in results
4. Γ¥î **No error logging at service layer:** Only Excel writers log errors

### 4.3 Failure Scenarios & Current Handling

| Scenario | Current Behavior | Logged? | Audit Impact |
|----------|------------------|---------|--------------|
| Draft not found | Returned in results: `{"status": "error", "error": "Draft not found"}` | Γ¥î No | Cannot track failed send attempts |
| Already SENT | Returned in results: `{"status": "error", "error": "Already sent at..."}` | Γ¥î No | Cannot see duplicate send attempts |
| Validation failed | Returned in results: `{"status": "validation_failed", "errors": [...]}` | Γ¥î No | Cannot audit incomplete submissions |
| Excel write failed | Returned in results: `{"status": "error", "error": "Excel write failed"}` | Γ£à Yes (Excel layer) | Logged but not audited |
| Permission denied | Exception raised, caught in Excel layer | Γ£à Yes | Logged but not audited |
| Complete failure | HTTPException (500) raised | Γ¥î No | API error only |

### 4.4 Recommendations for Audit Integration

**Add Logging at Service Layer:**
- Currently, only Excel writers log operations
- Service layer should log:
  - Send operation start (draft IDs, count)
  - Validation results (pass/fail per draft)
  - State transitions (DRAFT ΓåÆ SENT)
  - Excel write results (success/failure per draft)
  - Operation summary (total/sent/failed counts)

**Structured Logging Format:**
```python
# Example of what should be added
logger.info("SEND_OPERATION_START", extra={
    "draft_ids": [str(d) for d in draft_ids],
    "draft_count": len(draft_ids),
    "timestamp": datetime.now().isoformat()
})
```

---

## 5. Recommended Audit Event Insertion Point

### 5.1 Analysis of Options

#### Option A: API Layer (app/api/drafts.py)
**Pros:**
- Γ£à Single entry point for all send operations
- Γ£à HTTP context available (could extract IP, headers)
- Γ£à Clear boundary for external actions

**Cons:**
- Γ¥î No access to detailed draft data (must pass through service)
- Γ¥î Cannot track validation failures (filtered by service)
- Γ¥î Cannot track state transitions (happen in service)
- Γ¥î Excel write results not directly visible

**Verdict:** Γ¥î Too high-level, misses critical audit points

---

#### Option B: Service Layer (app/services/draft_service.py) **Γ¡É RECOMMENDED**
**Pros:**
- Γ£à **Access to ALL data:** drafts, validation results, Excel results
- Γ£à **Sees ALL state transitions:** DRAFT ΓåÆ SENT happens here
- Γ£à **Handles partial failures:** Can audit each draft individually
- Γ£à **Single responsibility:** Business logic + audit in same place
- Γ£à **Minimal code changes:** Insert audit calls at 4-6 key points
- Γ£à **Atomic with business logic:** Audit events in same transaction context

**Cons:**
- ΓÜá∩╕Å No HTTP context (but not needed for audit trail)
- ΓÜá∩╕Å Must pass audit events back up to API if needed

**Key Insertion Points in `send_drafts()` method:**
```python
# Line 290: After loading drafts
ΓåÆ AUDIT: SEND_OPERATION_START (draft_ids, count)

# Line 313-324: After validation
ΓåÆ AUDIT: DRAFT_VALIDATION_FAILED (draft_id, errors) [if invalid]
ΓåÆ AUDIT: DRAFT_VALIDATION_PASSED (draft_id) [if valid]

# Line 348: After calling SummaryService
ΓåÆ AUDIT: EXCEL_WRITE_ATTEMPTED (draft_ids, receipts)

# Line 398: After marking as SENT
ΓåÆ AUDIT: DRAFT_SENT_SUCCESS (draft_id, excel_result, sent_at)

# Line 402-411: On state update failure
ΓåÆ AUDIT: DRAFT_SENT_FAILED (draft_id, error, excel_result)

# End of method: After all processing
ΓåÆ AUDIT: SEND_OPERATION_COMPLETE (total, sent, failed, duration)
```

**Verdict:** Γ£à **OPTIMAL - Best balance of access, atomicity, and simplicity**

---

#### Option C: Repository Layer (app/repositories/draft_repository.py)
**Pros:**
- Γ£à Direct access to database operations
- Γ£à Can audit all CRUD operations

**Cons:**
- Γ¥î No business context (doesn't know about "send" vs "save")
- Γ¥î No validation results visible
- Γ¥î No Excel write results visible
- Γ¥î Would require auditing at multiple layers

**Verdict:** Γ¥î Too low-level, missing critical context

---

### 5.2 Final Recommendation

**Insert audit logging in `DraftService` (Service Layer)**

**Justification:**
1. **Atomicity:** Audit events happen in same context as state changes
2. **Complete Visibility:** Access to drafts, validation, Excel results
3. **Single Source of Truth:** All send logic flows through this layer
4. **Minimal Changes:** 4-6 audit calls in one method vs. scattered across layers
5. **Future-Proof:** Easy to add user context when authentication is implemented

**Implementation Pattern:**
```python
# Create AuditLogger service
audit_logger = AuditLogger()

# In DraftService.__init__()
self.audit_logger = audit_logger or AuditLogger()

# In send_drafts() method
self.audit_logger.log_event(
    event_type=AuditEventType.SEND_OPERATION_START,
    actor="SYSTEM",  # Will be replaced with user_id in Phase 5B
    data={
        "draft_ids": [str(d) for d in draft_ids],
        "draft_count": len(draft_ids)
    }
)
```

---

## 6. Structured Summary: Lifecycle & Proposed Audit Events

### 6.1 Current Lifecycle States & Transitions

```
ΓöîΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÉ
Γöé STATE MACHINE: Draft Receipt Lifecycle                          Γöé
ΓööΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÿ

    [NEW RECEIPT]
         Γöé
         Γåô
    ΓöîΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÉ
    Γöé  DRAFT  Γöé  ΓåÉ save_draft() creates new draft
    ΓööΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÿ    - status = DRAFT
         Γöé         - sent_at = None
         Γöé         - Editable by anyone
         Γåô
    ΓöîΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÉ
    Γöé  DRAFT  Γöé  ΓåÉ update_draft() modifies existing draft
    ΓööΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÿ    - status remains DRAFT
         Γöé         - updated_at changes
         Γåô
    ΓòöΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòù
    Γòæ send_drafts() invoked                                       Γòæ
    ΓòÜΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓò¥
         Γöé
         Γö£ΓöÇΓåÆ Validation Check (_validate_ready_to_send)
         Γöé   Γö£ΓöÇΓåÆ PASS: Proceed to send
         Γöé   ΓööΓöÇΓåÆ FAIL: Return {"status": "validation_failed"}
         Γöé
         Γö£ΓöÇΓåÆ Excel Write (SummaryService.send_receipts)
         Γöé   Γö£ΓöÇΓåÆ Branch Ledger (Format 02) ΓåÆ {status, row}
         Γöé   ΓööΓöÇΓåÆ Staff Ledger (Format 01) ΓåÆ {status, row}
         Γöé
         Γö£ΓöÇΓåÆ State Transition (draft.mark_as_sent)
         Γöé   Γö£ΓöÇΓåÆ SUCCESS: status = SENT, sent_at = now()
         Γöé   ΓööΓöÇΓåÆ FAILURE: status remains DRAFT, error returned
         Γöé
         Γåô
    ΓöîΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÉ
    Γöé  SENT   Γöé  ΓåÉ Terminal state (immutable)
    ΓööΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÿ    - status = SENT
                   - sent_at = timestamp
                   - Cannot be edited
                   - Cannot be re-sent
                   - Can be deleted (but Excel remains)

ΓòöΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòù
Γòæ STATE TRANSITION RULES                                           Γòæ
ΓòÜΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓò¥
  Γ£à DRAFT ΓåÆ DRAFT   (update_draft, save_draft)
  Γ£à DRAFT ΓåÆ SENT    (send_drafts, successful)
  Γ¥î SENT ΓåÆ DRAFT    (immutable, disallowed)
  Γ¥î SENT ΓåÆ SENT     (no re-send, returns error)
```

### 6.2 Missing Audit Data Points

| Data Point | Currently Available? | Source | Phase 5A Solution |
|------------|---------------------|--------|-------------------|
| **Actor (Who)** | Γ¥î No | N/A | Use "SYSTEM" placeholder |
| **Operation (What)** | ΓÜá∩╕Å Implicit | Function name | Explicit event types |
| **Target (Which draft)** | Γ£à Yes | draft_id | Include in event |
| **Timestamp (When)** | ΓÜá∩╕Å Partial | sent_at only | Add to all events |
| **Outcome (Success/Fail)** | ΓÜá∩╕Å Partial | Returned in results | Audit both outcomes |
| **Validation Errors** | Γ£à Yes | _validate_ready_to_send | Include in audit |
| **Excel Traceability** | ΓÜá∩╕Å Partial | Row number only | Add file path, sheet name |
| **Edit History** | Γ¥î No | N/A | Phase 5B enhancement |
| **Request Context** | Γ¥î No | N/A | Phase 5B enhancement |

### 6.3 Proposed Audit Event Types

#### Event Type 1: DRAFT_CREATED
**When:** New draft saved via `save_draft()`  
**Where:** `draft_service.py` line ~120 (after repository.save)  
**Data:**
```json
{
  "event_type": "DRAFT_CREATED",
  "event_id": "uuid",
  "timestamp": "2026-01-27T10:30:00Z",
  "actor": "SYSTEM",
  "draft_id": "27a60a39-...",
  "image_ref": "queue-123",
  "receipt_data": {
    "vendor_name": "Vendor A",
    "total_amount": 10000,
    "location": "Aichi",
    "staff": "aic_001"
  }
}
```

---

#### Event Type 2: DRAFT_UPDATED
**When:** Existing draft modified via `update_draft()`  
**Where:** `draft_service.py` line ~167 (after repository.save)  
**Data:**
```json
{
  "event_type": "DRAFT_UPDATED",
  "event_id": "uuid",
  "timestamp": "2026-01-27T10:35:00Z",
  "actor": "SYSTEM",
  "draft_id": "27a60a39-...",
  "changes": {
    "vendor_name": {"old": "Vendor A", "new": "Vendor B"},
    "total_amount": {"old": 10000, "new": 12000}
  }
}
```

---

#### Event Type 3: SEND_ATTEMPTED
**When:** Send operation starts  
**Where:** `draft_service.py` line ~290 (start of send_drafts)  
**Data:**
```json
{
  "event_type": "SEND_ATTEMPTED",
  "event_id": "uuid",
  "timestamp": "2026-01-27T10:40:00Z",
  "actor": "SYSTEM",
  "draft_ids": ["27a60a39-...", "7c1df874-..."],
  "draft_count": 2
}
```

---

#### Event Type 4: SEND_VALIDATION_FAILED
**When:** Draft fails READY-TO-SEND validation  
**Where:** `draft_service.py` line ~315 (in validation loop)  
**Data:**
```json
{
  "event_type": "SEND_VALIDATION_FAILED",
  "event_id": "uuid",
  "timestamp": "2026-01-27T10:40:01Z",
  "actor": "SYSTEM",
  "draft_id": "7c1df874-...",
  "validation_errors": [
    "business_location_id is required",
    "total_amount must be positive"
  ]
}
```

---

#### Event Type 5: SEND_SUCCEEDED
**When:** Draft successfully sent to Excel and marked as SENT  
**Where:** `draft_service.py` line ~398 (after mark_as_sent)  
**Data:**
```json
{
  "event_type": "SEND_SUCCEEDED",
  "event_id": "uuid",
  "timestamp": "2026-01-27T10:40:05Z",
  "actor": "SYSTEM",
  "draft_id": "27a60a39-...",
  "sent_at": "2026-01-27T10:40:05Z",
  "excel_result": {
    "branch": {
      "status": "written",
      "location": "Aichi",
      "file": "Template/Staff and Branch/µä¢τƒÑ_Aichi/Format_02_Branch_Ledger.xlsx",
      "sheet": "2026σ╣┤1µ£ê",
      "row": 42
    },
    "staff": {
      "status": "written",
      "staff_id": "aic_001",
      "file": "Template/Staff and Branch/µä¢τƒÑ_Aichi/Format_01_Staff_Ledger.xlsx",
      "sheet": "2026σ╣┤1µ£ê",
      "row": 15
    }
  }
}
```

---

#### Event Type 6: SEND_FAILED
**When:** Draft send fails (Excel write failure or state update failure)  
**Where:** `draft_service.py` line ~410 (in failure handling)  
**Data:**
```json
{
  "event_type": "SEND_FAILED",
  "event_id": "uuid",
  "timestamp": "2026-01-27T10:40:03Z",
  "actor": "SYSTEM",
  "draft_id": "7c1df874-...",
  "error": "Excel write failed: Permission denied",
  "excel_result": {
    "branch": {"status": "error", "error": "File locked"},
    "staff": {"status": "written", "row": 16}
  }
}
```

---

#### Event Type 7: DRAFT_DELETED (Optional - Phase 5B)
**When:** Draft deleted via `delete_draft()`  
**Where:** `draft_service.py` line ~210 (after repository.delete)  
**Data:**
```json
{
  "event_type": "DRAFT_DELETED",
  "event_id": "uuid",
  "timestamp": "2026-01-27T10:45:00Z",
  "actor": "SYSTEM",
  "draft_id": "27a60a39-...",
  "draft_status": "SENT",
  "note": "Deleting SENT draft does not remove from Excel"
}
```

---

### 6.4 Audit Event Schema (Proposed)

```python
# app/models/audit.py (NEW FILE)

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class AuditEventType(str, Enum):
    """Audit event types for receipt processing lifecycle."""
    DRAFT_CREATED = "DRAFT_CREATED"
    DRAFT_UPDATED = "DRAFT_UPDATED"
    SEND_ATTEMPTED = "SEND_ATTEMPTED"
    SEND_VALIDATION_FAILED = "SEND_VALIDATION_FAILED"
    SEND_SUCCEEDED = "SEND_SUCCEEDED"
    SEND_FAILED = "SEND_FAILED"
    DRAFT_DELETED = "DRAFT_DELETED"


class AuditEvent(BaseModel):
    """Immutable audit event record.
    
    Captures who did what, when, and what the outcome was.
    Once written, audit events are NEVER modified or deleted.
    """
    
    event_id: UUID = Field(
        default_factory=uuid4,
        description="Unique identifier for this audit event"
    )
    
    event_type: AuditEventType = Field(
        ...,
        description="Type of operation being audited"
    )
    
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="When this event occurred (UTC)"
    )
    
    actor: str = Field(
        ...,
        description="Who performed this action (user_id or 'SYSTEM')"
    )
    
    draft_id: Optional[UUID] = Field(
        None,
        description="Target draft ID (if applicable)"
    )
    
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Event-specific data (errors, results, changes)"
    )
    
    class Config:
        frozen = True  # Immutable after creation
```

---

## 7. Recommendations for Phase 5A Implementation

### 7.1 Core Requirements

1. **Create AuditEvent model** (`app/models/audit.py`)
   - Define event types (7 types above)
   - Define event schema (immutable)

2. **Create AuditLogger service** (`app/services/audit_logger.py`)
   - `log_event(event_type, actor, data)` method
   - Write to SQLite table: `audit_events`
   - Append-only (no updates, no deletes)

3. **Create AuditRepository** (`app/repositories/audit_repository.py`)
   - Table schema: `audit_events` with indexes
   - `save_event(event)` method
   - `query_events(filters)` method for reporting

4. **Integrate into DraftService**
   - Inject AuditLogger dependency
   - Add 6-7 audit calls at key points
   - Ensure no performance impact (async writes?)

### 7.2 Storage Strategy

**Option A: SQLite (same as drafts.db)**
- Γ£à Simple, no new dependencies
- Γ£à ACID compliance
- Γ£à Can query with SQL
- ΓÜá∩╕Å Scalability concerns (100k+ events)

**Option B: Separate audit.db file**
- Γ£à Isolates audit data
- Γ£à Can be backed up separately
- Γ£à Can be migrated to cloud storage

**Option C: JSON append-only log**
- Γ£à Extremely simple
- Γ£à Easy to archive and analyze
- Γ¥î Cannot query efficiently

**Recommendation:** Start with SQLite in `app/data/audit.db` (Option B). Migrate to PostgreSQL in production if needed.

### 7.3 Performance Considerations

**Audit Logging Must NOT Impact Send Performance:**
1. **Synchronous writes** (Phase 5A): Acceptable for MVP
   - Send already touches disk (Excel writes)
   - Audit write is fast (<1ms with SQLite)

2. **Async writes** (Phase 5B): If performance becomes an issue
   - Queue audit events in memory
   - Background worker writes to DB
   - Risk: Events lost if crash occurs

**Recommendation:** Start synchronous, optimize only if needed.

### 7.4 Query/Reporting Needs

**Phase 5A: Basic Queries**
- Get all events for a draft_id
- Get all SEND_FAILED events in date range
- Count events by type

**Phase 5B: Advanced Queries**
- Show edit history for a draft
- Audit trail for specific user
- Excel write success rate by location

**Recommendation:** Design schema with indexes for common queries:
- `event_type` (for filtering by type)
- `draft_id` (for draft history)
- `timestamp` (for date range queries)
- `actor` (for user activity, Phase 5B)

### 7.5 Excel Traceability Enhancement

**Current Gap:** Excel write results only include `row` number, not file path or sheet name.

**Solution:** Modify Excel writer return values to include:
```python
return {
    "status": "written",
    "location": "Aichi",
    "row": 42,
    "file_path": str(target_path),  # NEW
    "sheet_name": sheet_name        # NEW
}
```

**Files to modify:**
- `app/excel/branch_ledger_writer.py` line 85
- `app/excel/staff_ledger_writer.py` line 85

**Benefit:** Audit events can record EXACT location where data was written.

---

## 8. Conclusion

### 8.1 Key Findings Summary

Γ£à **Clean Architecture:** 3-layer design makes audit insertion straightforward  
Γ£à **Well-Defined States:** DRAFT ΓåÆ SENT transition is atomic and traceable  
Γ£à **Good Error Handling:** Partial failures are isolated and reported  
Γ¥î **No User Context:** All operations are anonymous (use "SYSTEM" placeholder)  
Γ¥î **No Audit Trail:** State changes, validations, and send operations are untracked  
ΓÜá∩╕Å **Partial Excel Traceability:** Row numbers available, but file paths missing  

### 8.2 Recommended Implementation Path

**Phase 5A: Core Audit Infrastructure (This Phase)**
1. Create audit event model and schema (7 event types)
2. Create audit logger service (append-only SQLite)
3. Integrate 6-7 audit calls into DraftService
4. Enhance Excel writers to return file_path and sheet_name
5. Basic query API for audit events

**Phase 5B: Enhanced Traceability (Future)**
1. Add user authentication (replace "SYSTEM" with user_id)
2. Add edit history (track field-level changes in DRAFT_UPDATED)
3. Add request context (IP, user agent, session)
4. Advanced audit queries and reporting UI
5. Export audit log to external compliance systems

### 8.3 Compliance Readiness

With Phase 5A implemented, the system will provide:
- Γ£à **Complete audit trail** of all receipts sent to Excel
- Γ£à **Validation failure tracking** (why receipts were rejected)
- Γ£à **Excel write traceability** (which file, sheet, row)
- Γ£à **Immutable audit log** (append-only, tamper-proof)
- Γ£à **Queryable history** (filter by draft, date, event type)
- ΓÜá∩╕Å **Anonymous actors** (will be resolved in Phase 5B with auth)

**This meets basic compliance requirements for financial record-keeping systems.**

---

## Appendix A: File Reference Table

| Component | File Path | Key Functions/Lines |
|-----------|-----------|---------------------|
| **API Endpoint** | `app/api/drafts.py` | `send_drafts()` [355-424] |
| **Service Logic** | `app/services/draft_service.py` | `send_drafts()` [215-434] |
| **Validation** | `app/services/draft_service.py` | `_validate_ready_to_send()` [461-579] |
| **State Model** | `app/models/draft.py` | `DraftReceipt`, `mark_as_sent()` [166-185] |
| **Repository** | `app/repositories/draft_repository.py` | `save()`, `get_by_ids()` [115-145] |
| **Summary Service** | `app/services/summary_service.py` | `send_receipts()` [23-74] |
| **Branch Writer** | `app/excel/branch_ledger_writer.py` | `write_receipt()` [33-95] |
| **Staff Writer** | `app/excel/staff_ledger_writer.py` | `write_receipt()` [33-95] |
| **Database Schema** | `app/repositories/draft_repository.py` | `_init_schema()` [68-108] |

---

## Appendix B: Audit Event Examples (Real Scenarios)

### Scenario 1: Successful Send
```
1. SEND_ATTEMPTED (10:40:00) - 2 drafts requested
2. SEND_SUCCEEDED (10:40:05) - draft_1 sent, row 42
3. SEND_SUCCEEDED (10:40:05) - draft_2 sent, row 43
```

### Scenario 2: Partial Failure (Validation)
```
1. SEND_ATTEMPTED (10:40:00) - 2 drafts requested
2. SEND_VALIDATION_FAILED (10:40:01) - draft_1 missing location
3. SEND_SUCCEEDED (10:40:05) - draft_2 sent, row 43
```

### Scenario 3: Complete Failure (Excel Locked)
```
1. SEND_ATTEMPTED (10:40:00) - 2 drafts requested
2. SEND_FAILED (10:40:03) - draft_1 Excel permission denied
3. SEND_FAILED (10:40:03) - draft_2 Excel permission denied
```

### Scenario 4: Draft Lifecycle
```
1. DRAFT_CREATED (10:30:00) - New receipt from OCR
2. DRAFT_UPDATED (10:35:00) - User corrected vendor name
3. DRAFT_UPDATED (10:37:00) - User corrected amount
4. SEND_SUCCEEDED (10:40:05) - Sent to Excel
```

---

**END OF DISCOVERY REPORT**

**Next Action:** Approve this design and proceed with Phase 5A implementation, OR request changes to the proposed audit event structure.
