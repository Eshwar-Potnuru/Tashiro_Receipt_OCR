"""
Comprehensive System Check - All Features Verification
Before Phase 5 - Ensuring Nothing is Corrupted
"""

import sys
from pathlib import Path
from app.main import app
from fastapi.testclient import TestClient
from app.services.draft_service import DraftService
from app.models.schema import Receipt
from app.models.draft import DraftStatus
import json

print("\n" + "="*80)
print("COMPREHENSIVE SYSTEM CHECK - PRE-PHASE 5 VERIFICATION")
print("="*80)

client = TestClient(app)
draft_service = DraftService()

# Track results
results = {
    'passed': [],
    'failed': [],
    'warnings': []
}

def test(name, func):
    """Run a test and track results"""
    try:
        print(f"\n{'='*80}")
        print(f"TEST: {name}")
        print(f"{'='*80}")
        func()
        results['passed'].append(name)
        print(f"✅ PASSED: {name}")
    except Exception as e:
        results['failed'].append(f"{name}: {str(e)}")
        print(f"❌ FAILED: {name}")
        print(f"   Error: {str(e)}")

# =============================================================================
# CORE FUNCTIONALITY TESTS
# =============================================================================

def test_1_server_initialization():
    """Test 1: Server initializes correctly"""
    print("Checking server initialization...")
    assert app is not None, "App not initialized"
    print("  ✓ FastAPI app initialized")
    
    response = client.get("/health")
    assert response.status_code == 200, f"Health check failed: {response.status_code}"
    print("  ✓ Health endpoint working")
    
    response = client.get("/")
    assert response.status_code == 200, f"Homepage failed: {response.status_code}"
    print("  ✓ Homepage loads")

def test_2_static_files():
    """Test 2: Static files accessible"""
    print("Checking static file access...")
    
    response = client.get("/static/js/drafts.js")
    assert response.status_code == 200, "drafts.js not accessible"
    print("  ✓ drafts.js accessible")
    
    # Verify no syntax errors in drafts.js
    content = response.text
    assert 'function openDraftModal' in content, "openDraftModal function missing"
    assert 'function enterEditMode' in content, "enterEditMode function missing"
    assert 'function confirmDeleteDraft' in content, "confirmDeleteDraft function missing"
    print("  ✓ All Phase 4F functions present")

def test_3_api_endpoints():
    """Test 3: API endpoints responding"""
    print("Checking API endpoints...")
    
    # Locations API
    response = client.get("/api/locations")
    assert response.status_code == 200, "Locations API failed"
    data = response.json()
    assert 'locations' in data, "Locations data missing"
    assert len(data['locations']) > 0, "No locations found"
    print(f"  ✓ Locations API working ({len(data['locations'])} locations)")
    
    # Staff API
    response = client.get("/api/staff?location=Aichi")
    assert response.status_code == 200, "Staff API failed"
    data = response.json()
    assert 'staff' in data, "Staff data missing"
    print(f"  ✓ Staff API working ({len(data['staff'])} staff members)")
    
    # Drafts API
    response = client.get("/api/drafts")
    assert response.status_code == 200, "Drafts list API failed"
    drafts = response.json()
    assert isinstance(drafts, list), "Drafts should be an array"
    print(f"  ✓ Drafts API working ({len(drafts)} drafts)")

# =============================================================================
# DRAFT SYSTEM TESTS (Phase 4)
# =============================================================================

def test_4_draft_creation():
    """Test 4: Draft creation (Phase 4D)"""
    print("Testing draft creation...")
    
    receipt = Receipt(
        receipt_date='2026-01-27',
        vendor_name='System Check Vendor',
        invoice_number='SYS-CHECK-001',
        total_amount=10000,
        tax_10_amount=909,
        tax_8_amount=0,
        business_location_id='Aichi',
        staff_id='aic_001'
    )
    
    draft = draft_service.save_draft(receipt, image_ref='system-check-test')
    assert draft.draft_id is not None, "Draft ID not generated"
    assert draft.status == DraftStatus.DRAFT, f"Wrong status: {draft.status}"
    assert draft.receipt.vendor_name == 'System Check Vendor', "Receipt data not saved"
    print(f"  ✓ Draft created: {draft.draft_id}")
    
    return draft.draft_id

def test_5_duplicate_prevention():
    """Test 5: Duplicate prevention (Phase 4F.1)"""
    print("Testing duplicate draft prevention...")
    
    receipt1 = Receipt(
        receipt_date='2026-01-27',
        vendor_name='Duplicate Test 1',
        invoice_number='DUP-001',
        total_amount=5000,
        tax_10_amount=454,
        tax_8_amount=0,
        business_location_id='Kashima',
        staff_id='kas_001'
    )
    
    draft1 = draft_service.save_draft(receipt1, image_ref='dup-test-image')
    draft1_id = draft1.draft_id
    print(f"  ✓ First draft created: {draft1_id}")
    
    # Save again with same image_ref
    receipt2 = Receipt(
        receipt_date='2026-01-27',
        vendor_name='Duplicate Test 2 UPDATED',
        invoice_number='DUP-002',
        total_amount=8000,
        tax_10_amount=727,
        tax_8_amount=0,
        business_location_id='Aichi',
        staff_id='aic_001'
    )
    
    draft2 = draft_service.save_draft(receipt2, image_ref='dup-test-image')
    assert draft2.draft_id == draft1_id, "Duplicate created instead of update!"
    assert draft2.receipt.vendor_name == 'Duplicate Test 2 UPDATED', "Update failed"
    print(f"  ✓ Duplicate prevented - updated existing draft")

def test_6_draft_validation():
    """Test 6: Draft validation (Phase 4E)"""
    print("Testing draft validation...")
    
    # Valid draft
    valid_receipt = Receipt(
        receipt_date='2026-01-27',
        vendor_name='Valid Receipt',
        invoice_number='VAL-001',
        total_amount=1000,
        tax_10_amount=91,
        tax_8_amount=0,
        business_location_id='Aichi',
        staff_id='aic_001'
    )
    valid_draft = draft_service.save_draft(valid_receipt, image_ref='valid-test')
    is_valid, errors = draft_service._validate_ready_to_send(valid_draft)
    assert is_valid == True, f"Valid draft marked invalid: {errors}"
    print(f"  ✓ Valid draft passes validation")
    
    # Invalid draft (missing required fields)
    invalid_receipt = Receipt(
        receipt_date='2026-01-27',
        vendor_name='',  # Missing
        invoice_number='INV-001',
        total_amount=0,  # Invalid
        tax_10_amount=0,
        tax_8_amount=0,
        business_location_id=None,  # Missing
        staff_id=None  # Missing
    )
    invalid_draft = draft_service.save_draft(invalid_receipt, image_ref='invalid-test')
    is_valid, errors = draft_service._validate_ready_to_send(invalid_draft)
    assert is_valid == False, "Invalid draft marked valid!"
    assert len(errors) >= 3, f"Should have multiple errors, got {len(errors)}"
    print(f"  ✓ Invalid draft rejected with {len(errors)} errors")

def test_7_draft_update():
    """Test 7: Draft update (Phase 4F.2)"""
    print("Testing draft update...")
    
    receipt = Receipt(
        receipt_date='2026-01-27',
        vendor_name='Original Vendor',
        invoice_number='UPD-001',
        total_amount=2000,
        tax_10_amount=182,
        tax_8_amount=0,
        business_location_id='Aichi',
        staff_id='aic_001'
    )
    
    draft = draft_service.save_draft(receipt, image_ref='update-test')
    original_id = draft.draft_id
    print(f"  ✓ Draft created: {original_id}")
    
    # Update the draft
    updated_receipt = Receipt(
        receipt_date='2026-01-27',
        vendor_name='Updated Vendor Name',
        invoice_number='UPD-002',
        total_amount=3000,
        tax_10_amount=273,
        tax_8_amount=0,
        business_location_id='Kashima',
        staff_id='kas_001'
    )
    
    updated_draft = draft_service.update_draft(original_id, updated_receipt)
    assert updated_draft.draft_id == original_id, "Draft ID changed!"
    assert updated_draft.receipt.vendor_name == 'Updated Vendor Name', "Update failed"
    print(f"  ✓ Draft updated successfully")

def test_8_draft_delete():
    """Test 8: Draft deletion (Phase 4F.6)"""
    print("Testing draft deletion...")
    
    receipt = Receipt(
        receipt_date='2026-01-27',
        vendor_name='Delete Test',
        invoice_number='DEL-001',
        total_amount=1000,
        tax_10_amount=91,
        tax_8_amount=0,
        business_location_id='Aichi',
        staff_id='aic_001'
    )
    
    draft = draft_service.save_draft(receipt, image_ref='delete-test')
    draft_id = draft.draft_id
    print(f"  ✓ Draft created for deletion: {draft_id}")
    
    # Delete via API
    response = client.delete(f"/api/drafts/{draft_id}")
    assert response.status_code == 204, f"Delete failed: {response.status_code}"
    print(f"  ✓ Draft deleted via API")
    
    # Verify it's gone
    deleted_draft = draft_service.get_draft(draft_id)
    assert deleted_draft is None, "Draft still exists after deletion!"
    print(f"  ✓ Draft confirmed deleted")

def test_9_validation_in_api():
    """Test 9: Validation status in API response (Phase 4F.4)"""
    print("Testing validation status in API response...")
    
    # Create a draft
    receipt = Receipt(
        receipt_date='2026-01-27',
        vendor_name='API Validation Test',
        invoice_number='API-001',
        total_amount=5000,
        tax_10_amount=454,
        tax_8_amount=0,
        business_location_id='Aichi',
        staff_id='aic_001'
    )
    draft = draft_service.save_draft(receipt, image_ref='api-validation-test')
    
    # Get via API
    response = client.get("/api/drafts")
    assert response.status_code == 200, "API call failed"
    
    drafts = response.json()
    test_draft = next((d for d in drafts if d['draft_id'] == str(draft.draft_id)), None)
    assert test_draft is not None, "Draft not found in API response"
    
    # Check validation fields
    assert 'is_valid' in test_draft, "is_valid field missing"
    assert 'validation_errors' in test_draft, "validation_errors field missing"
    print(f"  ✓ Validation fields present in API")
    print(f"    - is_valid: {test_draft['is_valid']}")
    print(f"    - errors: {len(test_draft['validation_errors'])}")

def test_10_send_validation():
    """Test 10: Send validation (Phase 4F Error Fix 2)"""
    print("Testing send validation (location/staff required)...")
    
    # Create incomplete draft
    incomplete = Receipt(
        receipt_date='2026-01-27',
        vendor_name='Incomplete Draft',
        invoice_number='INC-001',
        total_amount=1000,
        tax_10_amount=91,
        tax_8_amount=0,
        business_location_id=None,  # Missing
        staff_id=None  # Missing
    )
    incomplete_draft = draft_service.save_draft(incomplete, image_ref='incomplete-send-test')
    
    # Try to send incomplete draft
    response = client.post("/api/drafts/send", json={
        "draft_ids": [str(incomplete_draft.draft_id)]
    })
    
    # Should fail validation
    result = response.json()
    assert response.status_code == 200, "Send API failed"
    assert result['failed'] > 0, "Should have failed to send"
    print(f"  ✓ Incomplete draft blocked from sending")
    print(f"    - Total: {result['total']}, Sent: {result['sent']}, Failed: {result['failed']}")

# =============================================================================
# FILE SYSTEM TESTS
# =============================================================================

def test_11_file_structure():
    """Test 11: Critical files and directories exist"""
    print("Checking file structure...")
    
    base_dir = Path(__file__).parent
    
    critical_paths = [
        base_dir / "app" / "main.py",
        base_dir / "app" / "api" / "routes.py",
        base_dir / "app" / "api" / "drafts.py",
        base_dir / "app" / "services" / "draft_service.py",
        base_dir / "app" / "repositories" / "draft_repository.py",
        base_dir / "app" / "static" / "js" / "drafts.js",
        base_dir / "app" / "templates" / "mobile_intake_unified_manual.html",
        base_dir / "app" / "data" / "drafts.db",
        base_dir / "artifacts",
    ]
    
    for path in critical_paths:
        assert path.exists(), f"Missing: {path}"
        print(f"  ✓ {path.relative_to(base_dir)}")

def test_12_database_operations():
    """Test 12: Database operations"""
    print("Testing database operations...")
    
    # Count drafts
    from app.repositories.draft_repository import DraftRepository
    repo = DraftRepository()
    
    draft_count = len(repo.list_all())
    print(f"  ✓ Database accessible ({draft_count} drafts)")
    
    # Test CRUD
    test_receipt = Receipt(
        receipt_date='2026-01-27',
        vendor_name='DB Test',
        invoice_number='DB-001',
        total_amount=1000,
        tax_10_amount=91,
        tax_8_amount=0,
        business_location_id='Aichi',
        staff_id='aic_001'
    )
    
    draft = draft_service.save_draft(test_receipt, image_ref='db-test')
    assert draft.draft_id is not None
    print(f"  ✓ CREATE working")
    
    retrieved = repo.get_by_id(draft.draft_id)
    assert retrieved is not None
    print(f"  ✓ READ working")
    
    deleted = repo.delete(draft.draft_id)
    assert deleted == True
    print(f"  ✓ DELETE working")

# =============================================================================
# RUN ALL TESTS
# =============================================================================

print("\nStarting comprehensive system check...")
print("This will verify all core features and Phase 4 functionality\n")

test("1. Server Initialization", test_1_server_initialization)
test("2. Static Files Access", test_2_static_files)
test("3. API Endpoints", test_3_api_endpoints)
test("4. Draft Creation (Phase 4D)", test_4_draft_creation)
test("5. Duplicate Prevention (Phase 4F.1)", test_5_duplicate_prevention)
test("6. Draft Validation (Phase 4E)", test_6_draft_validation)
test("7. Draft Update (Phase 4F.2)", test_7_draft_update)
test("8. Draft Deletion (Phase 4F.6)", test_8_draft_delete)
test("9. Validation in API (Phase 4F.4)", test_9_validation_in_api)
test("10. Send Validation (Phase 4F Fix 2)", test_10_send_validation)
test("11. File Structure", test_11_file_structure)
test("12. Database Operations", test_12_database_operations)

# =============================================================================
# SUMMARY
# =============================================================================

print("\n" + "="*80)
print("COMPREHENSIVE SYSTEM CHECK - RESULTS")
print("="*80)

total_tests = len(results['passed']) + len(results['failed'])
pass_rate = (len(results['passed']) / total_tests * 100) if total_tests > 0 else 0

print(f"\n✅ PASSED: {len(results['passed'])}/{total_tests} tests ({pass_rate:.1f}%)")
for test_name in results['passed']:
    print(f"   ✓ {test_name}")

if results['failed']:
    print(f"\n❌ FAILED: {len(results['failed'])}/{total_tests} tests")
    for failure in results['failed']:
        print(f"   ✗ {failure}")

if results['warnings']:
    print(f"\n⚠️  WARNINGS: {len(results['warnings'])}")
    for warning in results['warnings']:
        print(f"   ! {warning}")

print("\n" + "="*80)
if len(results['failed']) == 0:
    print("✅ ALL SYSTEMS OPERATIONAL - READY FOR PHASE 5")
    print("="*80)
    print("\nVerified Components:")
    print("  ✓ Core server functionality")
    print("  ✓ API endpoints (locations, staff, drafts)")
    print("  ✓ Draft CRUD operations")
    print("  ✓ Phase 4F features (edit, delete, validation)")
    print("  ✓ Duplicate prevention")
    print("  ✓ Validation enforcement")
    print("  ✓ Database integrity")
    print("  ✓ File structure")
    print("\n🚀 System is stable and ready for Phase 5 development!")
else:
    print("⚠️  ISSUES DETECTED - REVIEW FAILURES BEFORE PHASE 5")
    print("="*80)

sys.exit(0 if len(results['failed']) == 0 else 1)
