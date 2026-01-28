"""Phase 4C-3 Verification: Image Reference Design

This script verifies that image_ref is properly integrated into the draft system.

Tests:
1. DraftReceipt model has image_ref field
2. Draft can be created with image_ref
3. image_ref is persisted to database
4. image_ref is retrieved from database
5. READY-TO-SEND validation blocks drafts without image_ref
6. Backward compatibility: legacy drafts (no image_ref) can be loaded
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from decimal import Decimal
from uuid import uuid4

from app.models.draft import DraftReceipt
from app.models.schema import Receipt
from app.repositories.draft_repository import DraftRepository
from app.services.draft_service import DraftService


def create_receipt_with_valid_data() -> Receipt:
    """Create a valid receipt for testing."""
    return Receipt(
        receipt_id=uuid4(),
        receipt_date="2026-01-26",
        vendor_name="Test Vendor Corp",
        total_amount=Decimal("10000"),
        tax_10_amount=Decimal("909"),
        tax_8_amount=Decimal("0"),
        business_location_id="Aichi",
        staff_id="aic_001",
    )


def test_image_ref_integration():
    """Test that image_ref is properly integrated."""
    service = DraftService()
    repository = DraftRepository()
    
    print("=" * 80)
    print("Phase 4C-3: Image Reference Design Verification")
    print("=" * 80)
    
    # Test 1: DraftReceipt model has image_ref field
    print("\n[TEST 1] DraftReceipt model has image_ref field")
    print("-" * 80)
    receipt = create_receipt_with_valid_data()
    draft = DraftReceipt(receipt=receipt, image_ref="test-queue-id-123")
    assert hasattr(draft, "image_ref"), "DraftReceipt should have image_ref field"
    assert draft.image_ref == "test-queue-id-123", "image_ref should be set"
    print(f"✅ PASS: DraftReceipt.image_ref = {draft.image_ref}")
    
    # Test 2: Draft can be created with image_ref via service
    print("\n[TEST 2] Draft creation with image_ref via service")
    print("-" * 80)
    receipt2 = create_receipt_with_valid_data()
    draft2 = service.save_draft(receipt2, image_ref="queue-456")
    assert draft2.image_ref == "queue-456", "Service should preserve image_ref"
    print(f"✅ PASS: Service created draft with image_ref = {draft2.image_ref}")
    
    # Test 3: image_ref is persisted to database
    print("\n[TEST 3] image_ref persistence to database")
    print("-" * 80)
    draft_id = draft2.draft_id
    retrieved_draft = repository.get_by_id(draft_id)
    assert retrieved_draft is not None, "Draft should be retrievable"
    assert retrieved_draft.image_ref == "queue-456", "image_ref should be persisted"
    print(f"✅ PASS: Retrieved draft.image_ref = {retrieved_draft.image_ref}")
    
    # Test 4: Draft without image_ref (backward compatibility)
    print("\n[TEST 4] Draft without image_ref (backward compatibility)")
    print("-" * 80)
    receipt3 = create_receipt_with_valid_data()
    draft3 = service.save_draft(receipt3, image_ref=None)
    assert draft3.image_ref is None, "Draft should allow None image_ref"
    print(f"✅ PASS: Draft created with image_ref = None (legacy support)")
    
    # Test 5: READY-TO-SEND validation blocks drafts without image_ref
    print("\n[TEST 5] READY-TO-SEND validation blocks missing image_ref")
    print("-" * 80)
    draft_no_image = DraftReceipt(
        receipt=create_receipt_with_valid_data(),
        image_ref=None
    )
    is_valid, errors = service._validate_ready_to_send(draft_no_image)
    assert not is_valid, "Draft without image_ref should fail validation"
    assert any("image_ref is required" in err for err in errors), \
        "Validation should mention image_ref"
    print(f"Valid: {is_valid}")
    print(f"Errors: {errors}")
    print("✅ PASS: Validation correctly blocks missing image_ref")
    
    # Test 6: READY-TO-SEND validation allows drafts WITH image_ref
    print("\n[TEST 6] READY-TO-SEND validation allows valid image_ref")
    print("-" * 80)
    draft_with_image = DraftReceipt(
        receipt=create_receipt_with_valid_data(),
        image_ref="valid-queue-789"
    )
    is_valid, errors = service._validate_ready_to_send(draft_with_image)
    # May have other errors, but NOT image_ref error
    image_ref_errors = [err for err in errors if "image_ref" in err]
    assert len(image_ref_errors) == 0, "Should not have image_ref errors"
    print(f"Valid: {is_valid}")
    print(f"Errors: {errors}")
    print(f"Image ref errors: {image_ref_errors}")
    print("✅ PASS: Validation accepts valid image_ref")
    
    # Test 7: Empty string image_ref is also rejected
    print("\n[TEST 7] Empty string image_ref is rejected")
    print("-" * 80)
    draft_empty_image = DraftReceipt(
        receipt=create_receipt_with_valid_data(),
        image_ref=""
    )
    is_valid, errors = service._validate_ready_to_send(draft_empty_image)
    assert not is_valid, "Draft with empty image_ref should fail"
    assert any("image_ref is required" in err for err in errors), \
        "Validation should reject empty string"
    print(f"Valid: {is_valid}")
    print(f"Errors: {errors}")
    print("✅ PASS: Empty string image_ref correctly rejected")
    
    print("\n" + "=" * 80)
    print("✅ ALL TESTS PASSED")
    print("=" * 80)
    print("\nPhase 4C-3 Implementation Verified:")
    print("  ✓ DraftReceipt has image_ref field")
    print("  ✓ image_ref propagates through service layer")
    print("  ✓ image_ref persists to database")
    print("  ✓ READY-TO-SEND validation enforces image_ref")
    print("  ✓ Backward compatibility maintained")
    print("\nSystem is ready for RDV UI integration.")


if __name__ == "__main__":
    test_image_ref_integration()
