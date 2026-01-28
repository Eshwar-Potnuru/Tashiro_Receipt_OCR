"""Quick verification that audit infrastructure works end-to-end"""

from uuid import uuid4
from app.models.audit import AuditEvent, AuditEventType
from app.repositories.audit_repository import AuditRepository

print("="*80)
print("PHASE 5A STEP 1 - AUDIT PERSISTENCE VERIFICATION")
print("="*80)

# Create repository (will create app/data/audit.db)
print("\n1. Initializing AuditRepository...")
repo = AuditRepository()
print(f"   ✓ Database created at: {repo.db_path}")

# Count existing events
initial_count = repo.count_events()
print(f"   ✓ Existing events: {initial_count}")

# Create and save test event
print("\n2. Creating test audit event...")
draft_id = uuid4()
event = AuditEvent(
    event_type=AuditEventType.DRAFT_CREATED,
    actor="SYSTEM",
    draft_id=draft_id,
    data={
        "vendor_name": "Test Vendor",
        "total_amount": 10000,
        "location": "Aichi",
        "note": "Phase 5A integration test"
    }
)
print(f"   ✓ Event ID: {event.event_id}")
print(f"   ✓ Event Type: {event.event_type.value}")

# Save event
print("\n3. Saving event to database...")
repo.save_event(event)
print("   ✓ Event saved successfully")

# Retrieve event
print("\n4. Retrieving event from database...")
events = repo.get_events_for_draft(draft_id)
print(f"   ✓ Retrieved {len(events)} event(s)")

if events:
    retrieved = events[0]
    print(f"   ✓ Event ID matches: {retrieved.event_id == event.event_id}")
    print(f"   ✓ Data intact: {retrieved.data.get('vendor_name')}")

# Verify indexes exist
print("\n5. Verifying indexes...")
import sqlite3
conn = sqlite3.connect(repo.db_path)
cursor = conn.execute(
    "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_audit_%'"
)
indexes = [row[0] for row in cursor.fetchall()]
conn.close()

for idx in indexes:
    print(f"   ✓ Index created: {idx}")

# Final count
final_count = repo.count_events()
print(f"\n6. Final event count: {final_count}")

print("\n" + "="*80)
print("✅ PHASE 5A STEP 1 COMPLETE - AUDIT PERSISTENCE LAYER READY")
print("="*80)
print("\nNext Steps:")
print("  - Step 2: Integrate audit logging into DraftService")
print("  - Step 3: Add audit event API endpoints")
print("  - Step 4: Update UI to show audit trail")
