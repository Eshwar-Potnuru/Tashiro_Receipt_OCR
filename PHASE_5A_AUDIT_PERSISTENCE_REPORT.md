# Phase 5A: Audit Persistence Layer Discovery Report
**Date:** January 27, 2026  
**Purpose:** Identify current database technology and recommend audit table integration strategy

---

## 1. Database Technology

### Primary Database: SQLite 3

**Location:** `app/data/drafts.db`  
**Size:** 32 KB (33 drafts currently stored)  
**Connection Pattern:** Connection-per-operation (no connection pooling)  
**Thread Safety:** SQLite file locks (safe for single-user, caution for multi-user)

**Evidence:**
- File: `app/repositories/draft_repository.py`
- Import: `import sqlite3`
- Connection: `sqlite3.connect(self.db_path)` (lines 82, 126, 158, 186, 217, etc.)

### No Other Databases Found

**Findings:**
- Γ¥î No PostgreSQL
- Γ¥î No MySQL/MariaDB
- Γ¥î No MongoDB or NoSQL
- Γ£à Single SQLite file for all persistence

**CSV Logging (Legacy, Pre-Phase 4):**
- File: `app/data/submission_logs/submission_log.csv`
- Contains: Excel submission logs from old system
- Status: Appears unused by current codebase (no Python references found)
- Recommendation: Can be ignored for Phase 5A audit trail

---

## 2. Current Tables & Schema

### Table: `draft_receipts`

**Purpose:** Stores draft receipts before sending to Excel

**Schema (7 columns):**
```sql
CREATE TABLE draft_receipts (
    draft_id TEXT PRIMARY KEY,        -- UUID as string
    receipt_json TEXT NOT NULL,       -- Pydantic-serialized Receipt object
    status TEXT NOT NULL,             -- "DRAFT" or "SENT"
    created_at TEXT NOT NULL,         -- ISO timestamp (YYYY-MM-DDTHH:MM:SS)
    updated_at TEXT NOT NULL,         -- ISO timestamp (YYYY-MM-DDTHH:MM:SS)
    sent_at TEXT,                     -- ISO timestamp, NULL if not sent
    image_ref TEXT                     -- queue_id reference, NULL for legacy
)
```

**Column Details:**
| # | Column Name    | Type | Nullable | Primary Key | Notes |
|---|----------------|------|----------|-------------|-------|
| 1 | draft_id       | TEXT | NULL (PK)| YES         | UUID stored as string |
| 2 | receipt_json   | TEXT | NOT NULL | NO          | Full JSON blob of Receipt |
| 3 | status         | TEXT | NOT NULL | NO          | Enum: "DRAFT" or "SENT" |
| 4 | created_at     | TEXT | NOT NULL | NO          | ISO format timestamp |
| 5 | updated_at     | TEXT | NOT NULL | NO          | ISO format timestamp |
| 6 | sent_at        | TEXT | NULL     | NO          | Set when status ΓåÆ SENT |
| 7 | image_ref      | TEXT | NULL     | NO          | Added in Phase 4C-3 |

**Indexes:**
- Only automatic index on PRIMARY KEY (draft_id)
- ΓÜá∩╕Å No indexes on status, created_at, or image_ref (potential performance concern)

**Current Data:**
- Row count: 33 drafts
- Mix of DRAFT and SENT status

### No History/Audit Tables Found

**Key Finding:** Γ¥î No existing audit, history, or changelog tables

**Implication:** Phase 5A will be the FIRST audit logging implementation

---

## 3. Migration Strategy

### Current Approach: Manual ALTER TABLE at Startup

**Pattern:** Repository `__init__()` calls `_init_schema()`

**Evidence from `draft_repository.py` lines 70-108:**
```python
def _init_schema(self) -> None:
    """Create draft_receipts table if it doesn't exist."""
    conn = sqlite3.connect(self.db_path)
    try:
        # 1. Create table with CREATE TABLE IF NOT EXISTS
        conn.execute("""
            CREATE TABLE IF NOT EXISTS draft_receipts (...)
        """)
        
        # 2. Add new columns with ALTER TABLE (wrapped in try/except)
        try:
            conn.execute("""
                ALTER TABLE draft_receipts ADD COLUMN image_ref TEXT
            """)
        except sqlite3.OperationalError:
            # Column already exists, safe to ignore
            pass
        
        conn.commit()
    finally:
        conn.close()
```

**Migration Characteristics:**
- Γ£à **Idempotent:** `IF NOT EXISTS` and try/except make it safe to run multiple times
- Γ£à **Automatic:** Runs on every repository instantiation
- Γ£à **Simple:** No migration framework required
- ΓÜá∩╕Å **No versioning:** Cannot track which migrations have been applied
- ΓÜá∩╕Å **No rollback:** Cannot undo schema changes
- ΓÜá∩╕Å **No ordering:** If multiple ALTER TABLE statements exist, order depends on code sequence

**Historical Evidence:**
- `image_ref` column was added in Phase 4C-3 using this pattern
- Still works correctly (column exists in production DB)

### No Migration Framework Detected

**Findings:**
- Γ¥î No Alembic (common for SQLAlchemy)
- Γ¥î No Django migrations
- Γ¥î No schema_migrations or version tracking table
- Γ¥î No migration scripts directory

**Confirmed by:**
- Database inspection: No tables named `*migration*` or `*version*`
- Code search: No references to `alembic`, `migrate`, or `schema_version`

---

## 4. Recommended Audit Table Integration Strategy

### Option A: Follow Existing Pattern (RECOMMENDED)

**Approach:** Create `AuditRepository` with `_init_schema()` method

**Pros:**
- Γ£à **Consistent with current architecture:** Matches `DraftRepository` pattern
- Γ£à **Minimal risk:** Proven pattern (used successfully for `image_ref` migration)
- Γ£à **Simple to implement:** No new dependencies or frameworks
- Γ£à **Automatic deployment:** Schema created on first use
- Γ£à **Separate database file possible:** Can use `app/data/audit.db` for isolation

**Cons:**
- ΓÜá∩╕Å No formal versioning (acceptable for MVP)
- ΓÜá∩╕Å Manual coordination if multiple schema changes needed

**Implementation Pattern:**
```python
# app/repositories/audit_repository.py (NEW FILE)

class AuditRepository:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            app_dir = Path(__file__).parent.parent
            data_dir = app_dir / "data"
            data_dir.mkdir(exist_ok=True)
            db_path = str(data_dir / "audit.db")  # Separate file
        
        self.db_path = db_path
        self._init_schema()
    
    def _init_schema(self) -> None:
        """Create audit_events table if it doesn't exist."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    draft_id TEXT,
                    data_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            
            # Create indexes for common queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_event_type 
                ON audit_events(event_type)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_draft_id 
                ON audit_events(draft_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp 
                ON audit_events(timestamp)
            """)
            
            conn.commit()
        finally:
            conn.close()
```

**Deployment Safety:**
1. New file `app/data/audit.db` created automatically
2. If file exists, `CREATE TABLE IF NOT EXISTS` is no-op
3. Indexes created with `IF NOT EXISTS` (idempotent)
4. No impact on existing `drafts.db`

---

### Option B: Share drafts.db (Alternative)

**Approach:** Add `audit_events` table to existing `drafts.db`

**Pros:**
- Γ£à Single database file (simpler backup)
- Γ£à Can use foreign keys between tables (draft_id reference)

**Cons:**
- ΓÜá∩╕Å Schema changes affect production database
- ΓÜá∩╕Å Harder to isolate audit data
- ΓÜá∩╕Å Backup/restore of one affects the other

**Not Recommended:** Separation of concerns is better for audit immutability

---

### Option C: Introduce Alembic (Not Recommended for Phase 5A)

**Why Not:**
- Γ¥î Adds complexity (new dependency)
- Γ¥î Requires SQLAlchemy models (system uses Pydantic)
- Γ¥î Overkill for simple append-only audit table
- Γ£à Could revisit in Phase 5B if schema complexity grows

---

## 5. Proposed Audit Table Schema

### Table: `audit_events`

**Purpose:** Immutable log of all draft lifecycle events

**Schema (7 columns):**
```sql
CREATE TABLE audit_events (
    event_id TEXT PRIMARY KEY,           -- UUID as string (unique event identifier)
    event_type TEXT NOT NULL,            -- Enum: DRAFT_CREATED, SEND_SUCCEEDED, etc.
    timestamp TEXT NOT NULL,             -- ISO timestamp when event occurred (UTC)
    actor TEXT NOT NULL,                 -- Who performed action ("SYSTEM" for Phase 5A)
    draft_id TEXT,                       -- Target draft UUID (NULL for SEND_ATTEMPTED)
    data_json TEXT NOT NULL,             -- Event-specific data (errors, results, changes)
    created_at TEXT NOT NULL             -- When audit record was inserted (immutability check)
)
```

**Field Descriptions:**

| Field       | Type | Nullable | Description | Example Value |
|-------------|------|----------|-------------|---------------|
| event_id    | TEXT | NOT NULL | UUID for this audit record | "27a60a39-46aa-..." |
| event_type  | TEXT | NOT NULL | Type of event (7 types) | "SEND_SUCCEEDED" |
| timestamp   | TEXT | NOT NULL | When action occurred (UTC) | "2026-01-27T10:40:05Z" |
| actor       | TEXT | NOT NULL | Who did it (user_id or "SYSTEM") | "SYSTEM" |
| draft_id    | TEXT | NULL | Related draft UUID | "7c1df874-52ba-..." |
| data_json   | TEXT | NOT NULL | Full event context (JSON) | `{"sent_at": "...", "excel_result": {...}}` |
| created_at  | TEXT | NOT NULL | Audit record creation time | "2026-01-27T10:40:05.123Z" |

**Why TEXT for timestamps?**
- Consistent with `draft_receipts` table
- SQLite doesn't have native DATETIME type
- ISO format is sortable and human-readable
- Easy to parse in Python: `datetime.fromisoformat()`

**Why separate timestamp and created_at?**
- `timestamp`: When the business event occurred (e.g., draft sent at 10:40:05)
- `created_at`: When audit record was written (should be Γëê same, detects backdating)

**Why NULL for draft_id?**
- Some events don't target a specific draft (e.g., `SEND_ATTEMPTED` targets multiple)
- Allows batch operation logging

---

### Indexes for Performance

**Recommended Indexes:**
```sql
-- Query: Get all events for a specific draft
CREATE INDEX IF NOT EXISTS idx_audit_draft_id 
ON audit_events(draft_id);

-- Query: Get all events of a specific type
CREATE INDEX IF NOT EXISTS idx_audit_event_type 
ON audit_events(event_type);

-- Query: Get events in a date range
CREATE INDEX IF NOT EXISTS idx_audit_timestamp 
ON audit_events(timestamp);

-- Query: Get user activity (Phase 5B)
CREATE INDEX IF NOT EXISTS idx_audit_actor 
ON audit_events(actor);
```

**Index Rationale:**
- `draft_id`: Most common query (show history for one draft)
- `event_type`: Filter by operation type (e.g., all validation failures)
- `timestamp`: Date range queries for reports
- `actor`: Future-proofing for Phase 5B user tracking

**Storage Impact:**
- Indexes add ~30-40% overhead to table size
- For 10,000 audit events: ~5 KB per index = 20 KB total
- Acceptable tradeoff for query performance

---

### Data Type Decisions

**Why JSON blob (data_json) instead of normalized columns?**

Γ£à **Flexibility:** Different event types have different fields
- `SEND_SUCCEEDED` needs `excel_result` (complex nested object)
- `SEND_VALIDATION_FAILED` needs `validation_errors` (array of strings)
- `DRAFT_UPDATED` needs `changes` (diff of old/new values)

Γ£à **Simplicity:** One table, no joins
- Alternative: Separate tables per event type (7 tables)
- Or: EAV (Entity-Attribute-Value) pattern (complex queries)

Γ£à **Precedent:** `draft_receipts` uses `receipt_json` successfully

Γ¥î **Query Complexity:** Cannot filter by nested JSON fields efficiently
- Acceptable: Audit queries are typically by event_type or draft_id
- JSON filtering is rare (usually export and analyze externally)

**SQLite JSON Support:**
- SQLite 3.9+ has JSON functions (json_extract, json_array_length)
- Can query JSON if needed: `WHERE json_extract(data_json, '$.sent_at') IS NOT NULL`
- Not needed for Phase 5A queries

---

## 6. Concurrency & Locking Concerns

### Current System: Single-User Desktop Application

**Reality Check:**
- Application is a local FastAPI server accessed by one user
- No production multi-user deployment yet
- SQLite file locks are sufficient for current scope

### SQLite Locking Behavior

**Write Lock:**
- Only ONE writer at a time (exclusive lock on entire database)
- Writers block other writers (serialized)
- Readers can proceed while writer waits (WAL mode only)

**Default Mode (DELETE journal):**
- Writers block ALL operations (readers and writers)
- Very safe, very slow under concurrency

**WAL Mode (Write-Ahead Logging):**
- Writers don't block readers (readers see old data)
- Multiple readers can proceed simultaneously
- Still only ONE writer at a time

### Current Configuration: Default Mode

**Evidence:** No WAL configuration found in `DraftRepository`

**Implication:**
- Concurrent writes would block (serialized by SQLite)
- Draft save + Audit log write = two separate transactions (NOT atomic)

### Risks for Phase 5A

#### Risk 1: Audit Write Failure Doesn't Prevent Draft State Change

**Scenario:**
```
1. DraftService.send_drafts() calls draft.mark_as_sent()
2. DraftRepository.save(draft) succeeds ΓåÆ draft is SENT
3. AuditLogger.log_event() fails (disk full, permission denied)
4. Result: Draft is SENT but no audit record exists
```

**Severity:** ΓÜá∩╕Å MODERATE
- Audit trail has gaps
- Compliance risk (cannot prove what was sent)

**Mitigation Options:**

**Option A: Rollback draft on audit failure**
```python
# Pseudocode in DraftService.send_drafts()
try:
    draft.mark_as_sent()
    self.repository.save(draft)
    self.audit_logger.log_event(SEND_SUCCEEDED, draft_id=draft.draft_id, ...)
except AuditException:
    # Rollback: Load draft again, set status back to DRAFT
    draft.status = DraftStatus.DRAFT
    self.repository.save(draft)
    raise
```
- Γ£à Maintains consistency (draft only SENT if audit succeeds)
- Γ¥î Complex error handling
- Γ¥î Race condition if multiple processes

**Option B: Accept eventual consistency**
```python
# Always write audit, log failure but don't rollback
try:
    self.audit_logger.log_event(...)
except Exception as e:
    logger.error(f"AUDIT FAILURE: {e}")  # Alert operator
    # Draft remains SENT (Excel write already happened)
```
- Γ£à Simpler implementation
- Γ£à Matches Excel write behavior (no rollback if Excel locked)
- ΓÜá∩╕Å Audit gaps possible (monitor logs for AUDIT FAILURE)

**Recommendation:** **Option B** for Phase 5A
- Rationale: Excel write is ALREADY not transactional
- Audit is "best effort" like Excel writes
- Phase 5B can add proper distributed transactions if needed

---

#### Risk 2: Concurrent Audit Writes

**Scenario:**
- Two API requests call `send_drafts()` simultaneously
- Both try to write to `audit.db` at the same time
- SQLite serializes writes (one waits for the other)

**Severity:** Γ£à LOW
- SQLite handles this correctly (one waits, then proceeds)
- Worst case: Slight delay (milliseconds)
- No data corruption or lost events

**Evidence:**
- Connection-per-operation pattern prevents shared connections
- Each write is a separate transaction (auto-commit)

---

#### Risk 3: Database File Locked (Excel-Like Issue)

**Scenario:**
- Audit database file is locked by antivirus, backup software, or file explorer
- Audit write fails with `sqlite3.OperationalError: database is locked`

**Severity:** ΓÜá∩╕Å MODERATE
- Same risk as Excel files being locked
- System already handles this for Excel (returns error to user)

**Mitigation:**
- Use same error handling pattern as Excel writers
- Retry logic with timeout (3 attempts, 100ms delay)
- Return meaningful error to user: "Cannot write audit log, please close any programs accessing audit.db"

---

#### Risk 4: Disk Full

**Scenario:**
- Audit table grows large (100k+ events)
- Disk runs out of space
- Both draft and audit writes fail

**Severity:** ΓÜá∩╕Å MODERATE (system-wide failure)

**Current Status:**
- No disk space monitoring
- No log rotation or archiving

**Mitigation (Phase 5B):**
- Monitor audit table size
- Archive old events to external storage (e.g., events older than 1 year)
- Alert operator when disk space < 10%

**Phase 5A:** Accept risk (manual monitoring by operator)

---

### Concurrency Recommendations

**Phase 5A (MVP):**
1. Γ£à Use separate `audit.db` file (isolates audit locking from drafts)
2. Γ£à Connection-per-operation (current pattern, no change)
3. Γ£à Wrap audit writes in try/except, log failures, don't crash
4. Γ£à Add retry logic with timeout (3 attempts, 100ms sleep)
5. Γ¥î Do NOT use transactions across draft + audit (separate files)

**Phase 5B (Production Hardening):**
1. ΓÜá∩╕Å Enable WAL mode: `PRAGMA journal_mode=WAL;`
2. ΓÜá∩╕Å Add connection pooling (if multi-user)
3. ΓÜá∩╕Å Migrate to PostgreSQL for true ACID transactions
4. ΓÜá∩╕Å Add audit log archival/rotation

---

## 7. Summary & Recommendations

### Key Findings

| Aspect | Current State | Phase 5A Impact |
|--------|---------------|-----------------|
| **Database** | SQLite 3 | Γ£à Compatible, no changes needed |
| **Tables** | 1 table (draft_receipts) | Γ₧ò Add 1 table (audit_events) |
| **Migration** | Manual ALTER TABLE at startup | Γ£à Follow same pattern |
| **Indexes** | Only PK on draft_receipts | Γ₧ò Add 4 indexes on audit_events |
| **Concurrency** | Connection-per-operation, file locks | ΓÜá∩╕Å Accept eventual consistency |
| **Versioning** | None (idempotent schema init) | Γ£à No change needed |
| **Backup** | Manual (no automation) | ΓÜá∩╕Å Separate audit.db file |

### Recommended Implementation Plan

**Step 1: Create AuditRepository**
- New file: `app/repositories/audit_repository.py`
- Pattern: Copy `DraftRepository` structure
- Database: `app/data/audit.db` (separate file)
- Schema: `audit_events` table with 4 indexes

**Step 2: Test Schema Creation**
- Unit test: Create repository, verify table exists
- Unit test: Insert event, verify retrieval
- Integration test: Concurrent writes (verify no corruption)

**Step 3: Add Error Handling**
- Wrap audit writes in try/except
- Log failures with `logger.error("AUDIT FAILURE: ...")`
- Add retry logic (3 attempts, 100ms delay)
- Do NOT crash on audit failure (graceful degradation)

**Step 4: Monitor**
- Add log statement on every audit write
- Alert operator if `AUDIT FAILURE` appears in logs
- Manual check: Query `audit_events` count daily

### Safety Checklist

Γ£à **Idempotent:** `CREATE TABLE IF NOT EXISTS` prevents errors on restart  
Γ£à **Non-destructive:** No ALTER TABLE on existing tables  
Γ£à **Isolated:** Separate `audit.db` file, no impact on `drafts.db`  
Γ£à **Backward compatible:** System works if audit writes fail (logs error)  
Γ£à **Testable:** Can delete `audit.db` file to reset, table recreates  
Γ£à **No data loss:** Existing `drafts.db` untouched  

### Risks Accepted for Phase 5A MVP

ΓÜá∩╕Å **Eventual consistency:** Audit write failure doesn't rollback draft state  
ΓÜá∩╕Å **No versioning:** Schema changes require manual coordination  
ΓÜá∩╕Å **No archival:** Audit table grows indefinitely (manual cleanup)  
ΓÜá∩╕Å **File locking:** Same risk as Excel files (retry + error message)  
ΓÜá∩╕Å **No WAL mode:** Slower concurrent writes (acceptable for single-user)  

**All risks are acceptable for Phase 5A MVP scope.**

---

## Appendix A: Complete Audit Table DDL

```sql
-- Create audit events table (immutable append-only log)
CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,           -- UUID as string
    event_type TEXT NOT NULL,            -- DRAFT_CREATED, SEND_SUCCEEDED, etc.
    timestamp TEXT NOT NULL,             -- ISO timestamp (UTC) when event occurred
    actor TEXT NOT NULL,                 -- Who performed action ("SYSTEM" for Phase 5A)
    draft_id TEXT,                       -- Target draft UUID (nullable)
    data_json TEXT NOT NULL,             -- Event-specific data (JSON blob)
    created_at TEXT NOT NULL             -- Audit record creation time (immutability check)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_audit_draft_id ON audit_events(draft_id);
CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_events(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_events(actor);
```

---

## Appendix B: Example Audit Record (JSON)

```json
{
  "event_id": "a1b2c3d4-5678-90ab-cdef-1234567890ab",
  "event_type": "SEND_SUCCEEDED",
  "timestamp": "2026-01-27T10:40:05.123456Z",
  "actor": "SYSTEM",
  "draft_id": "27a60a39-46aa-4b18-828b-8988911f8931",
  "data_json": "{\"sent_at\": \"2026-01-27T10:40:05Z\", \"excel_result\": {\"branch\": {\"status\": \"written\", \"location\": \"Aichi\", \"file_path\": \"Template/.../Format_02_Branch_Ledger.xlsx\", \"sheet_name\": \"2026σ╣┤1µ£ê\", \"row\": 42}, \"staff\": {\"status\": \"written\", \"staff_id\": \"aic_001\", \"file_path\": \"Template/.../Format_01_Staff_Ledger.xlsx\", \"sheet_name\": \"2026σ╣┤1µ£ê\", \"row\": 15}}}",
  "created_at": "2026-01-27T10:40:05.234567Z"
}
```

**Note:** `data_json` is double-encoded (JSON string inside JSON field) for SQLite storage.

---

**END OF PERSISTENCE DISCOVERY REPORT**

**Next Action:** Approve table schema and begin Phase 5A implementation with `AuditRepository`.
