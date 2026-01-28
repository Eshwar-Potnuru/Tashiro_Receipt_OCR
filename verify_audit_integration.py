"""Phase 5A Step 2: Integration Verification

End-to-end test that verifies audit events are created for the complete
draft lifecycle with real persistence (not mocked).
"""

import sys
import tempfile
import shutil
from pathlib import Path
from uuid import uuid4

# Import the services
from app.models.draft import DraftReceipt, DraftStatus
from app.models.schema import Receipt
from app.models.audit import AuditEventType
from app.repositories.draft_repository import DraftRepository
from app.repositories.audit_repository import AuditRepository
from app.services.draft_service import DraftService
from app.services.audit_logger import AuditLogger
from app.services.config_service import ConfigService


def test_complete_audit_lifecycle():
    """Test that all draft operations emit correct audit events."""
    print("\n" + "="*80)
    print("Phase 5A Step 2: End-to-End Audit Integration Test")
    print("="*80)
    
    # Create temporary directories for test databases
    test_dir = Path(tempfile.mkdtemp(prefix="audit_test_"))
    draft_db_path = test_dir / "drafts.db"
    audit_db_path = test_dir / "audit.db"
    
    print(f"\n1. Test environment created:")
    print(f"   - Draft DB: {draft_db_path}")
    print(f"   - Audit DB: {audit_db_path}")
    
    try:
        # Initialize services with test databases
        draft_repo = DraftRepository(db_path=str(draft_db_path))
        audit_repo = AuditRepository(db_path=str(audit_db_path))
        audit_logger = AuditLogger(repository=audit_repo)
        config_service = ConfigService()
        
        draft_service = DraftService(
            repository=draft_repo,
            summary_service=None,  # Won't test send in this integration test
            config_service=config_service,
            audit_logger=audit_logger,
        )
        
        print("✅ Services initialized")
        
        # Test 1: Create draft → DRAFT_CREATED event
        print("\n2. Test DRAFT_CREATED event:")
        receipt = Receipt(
            vendor_name="LAWSON",
            receipt_date="2026-01-27",
            total_amount=1500.0,
            tax_10_amount=136.0,
            tax_8_amount=0.0,
            business_location_id="aichi",
            staff_id="staff-001",
        )
        
        draft = draft_service.save_draft(receipt, image_ref="test-queue-001")
        print(f"   - Draft created: {draft.draft_id}")
        
        # Verify DRAFT_CREATED event
        events = audit_repo.get_events_for_draft(draft.draft_id)
        assert len(events) == 1, f"Expected 1 event, got {len(events)}"
        assert events[0].event_type == AuditEventType.DRAFT_CREATED
        assert events[0].data["vendor_name"] == "LAWSON"
        assert events[0].data["total_amount"] == 1500.0
        print("   ✅ DRAFT_CREATED event verified")
        print(f"      - Event ID: {events[0].event_id}")
        print(f"      - Timestamp: {events[0].timestamp}")
        print(f"      - Actor: {events[0].actor}")
        
        # Test 2: Update draft → DRAFT_UPDATED event
        print("\n3. Test DRAFT_UPDATED event:")
        updated_receipt = Receipt(
            vendor_name="FamilyMart",
            receipt_date="2026-01-28",
            total_amount=2000.0,
            tax_10_amount=182.0,
            tax_8_amount=0.0,
            business_location_id="osaka",
            staff_id="staff-002",
        )
        
        updated_draft = draft_service.update_draft(draft.draft_id, updated_receipt)
        print(f"   - Draft updated: {updated_draft.draft_id}")
        
        # Verify DRAFT_UPDATED event
        events = audit_repo.get_events_for_draft(draft.draft_id)
        print(f"   - Events found: {len(events)}")
        for i, evt in enumerate(events):
            print(f"     [{i}] {evt.event_type.value} at {evt.timestamp}")
        assert len(events) == 2, f"Expected 2 events, got {len(events)}"
        # Events are in DESC order (newest first), so [0] is UPDATED, [1] is CREATED
        assert events[0].event_type == AuditEventType.DRAFT_UPDATED
        assert events[0].data["vendor_name"] == "FamilyMart"
        assert events[0].data["total_amount"] == 2000.0
        print("   ✅ DRAFT_UPDATED event verified")
        print(f"      - Event ID: {events[0].event_id}")
        print(f"      - Timestamp: {events[0].timestamp}")
        
        # Test 3: Create another draft for delete test
        print("\n4. Test DRAFT_DELETED event:")
        receipt_to_delete = Receipt(
            vendor_name="7-Eleven",
            receipt_date="2026-01-26",
            total_amount=800.0,
            tax_10_amount=73.0,
            tax_8_amount=0.0,
            business_location_id="aichi",
            staff_id="staff-001",
        )
        
        draft_to_delete = draft_service.save_draft(receipt_to_delete, image_ref="test-queue-002")
        delete_draft_id = draft_to_delete.draft_id
        print(f"   - Draft created for deletion: {delete_draft_id}")
        
        # Delete the draft
        deleted = draft_service.delete_draft(delete_draft_id)
        assert deleted, "Draft should be deleted"
        print(f"   - Draft deleted: {delete_draft_id}")
        
        # Verify DRAFT_DELETED event
        events = audit_repo.get_events_for_draft(delete_draft_id)
        assert len(events) == 2, f"Expected 2 events (created+deleted), got {len(events)}"
        # Events are in DESC order (newest first), so [0] is DELETED, [1] is CREATED
        assert events[0].event_type == AuditEventType.DRAFT_DELETED
        assert events[0].data["status_before_delete"] == "DRAFT"
        assert events[1].event_type == AuditEventType.DRAFT_CREATED
        print("   ✅ DRAFT_DELETED event verified")
        print(f"      - Event ID: {events[0].event_id}")
        print(f"      - Timestamp: {events[0].timestamp}")
        
        # Test 4: Verify all audit events queryable
        print("\n5. Test audit event queries:")
        
        # Get recent events
        recent_events = audit_repo.get_recent_events(limit=10)
        print(f"   - Recent events: {len(recent_events)}")
        
        # Get by type
        created_events = audit_repo.get_events_by_type(AuditEventType.DRAFT_CREATED)
        print(f"   - DRAFT_CREATED events: {len(created_events)}")
        assert len(created_events) == 2, "Should have 2 DRAFT_CREATED events"
        
        updated_events = audit_repo.get_events_by_type(AuditEventType.DRAFT_UPDATED)
        print(f"   - DRAFT_UPDATED events: {len(updated_events)}")
        assert len(updated_events) == 1, "Should have 1 DRAFT_UPDATED event"
        
        deleted_events = audit_repo.get_events_by_type(AuditEventType.DRAFT_DELETED)
        print(f"   - DRAFT_DELETED events: {len(deleted_events)}")
        assert len(deleted_events) == 1, "Should have 1 DRAFT_DELETED event"
        
        # Total count
        total_count = audit_repo.count_events()
        print(f"   - Total audit events: {total_count}")
        assert total_count == 4, f"Expected 4 total events, got {total_count}"
        print("   ✅ All queries verified")
        
        # Test 5: Verify audit immutability
        print("\n6. Test audit immutability:")
        assert not hasattr(audit_repo, 'update_event'), "AuditRepository should not have update_event"
        assert not hasattr(audit_repo, 'delete_event'), "AuditRepository should not have delete_event"
        print("   ✅ No update/delete methods exist")
        
        # Test 6: Verify database files exist
        print("\n7. Verify database files:")
        assert draft_db_path.exists(), "Draft database should exist"
        assert audit_db_path.exists(), "Audit database should exist"
        print(f"   - Draft DB size: {draft_db_path.stat().st_size} bytes")
        print(f"   - Audit DB size: {audit_db_path.stat().st_size} bytes")
        print("   ✅ Both databases created successfully")
        
        print("\n" + "="*80)
        print("✅ PHASE 5A STEP 2 INTEGRATION TEST PASSED")
        print("="*80)
        print("\nSummary:")
        print(f"  - {len(created_events)} DRAFT_CREATED events")
        print(f"  - {len(updated_events)} DRAFT_UPDATED events")
        print(f"  - {len(deleted_events)} DRAFT_DELETED events")
        print(f"  - {total_count} total audit events")
        print(f"  - All events immutable (no update/delete methods)")
        print(f"  - Audit DB: {audit_db_path}")
        print("\nNext Steps:")
        print("  - Phase 5A Step 3: Add audit API endpoints")
        print("  - Phase 5A Step 4: Add UI for viewing audit trail")
        print()
        
        return True
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        if test_dir.exists():
            shutil.rmtree(test_dir)
            print(f"\n🧹 Cleaned up test directory: {test_dir}")


if __name__ == "__main__":
    success = test_complete_audit_lifecycle()
    sys.exit(0 if success else 1)
