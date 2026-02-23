"""Phase 5B.2 Integration Tests: Draft Ownership Tracking

Tests for creator_user_id tracking in draft receipts.

Phase 5B.2 Scope:
- Track creator_user_id for authenticated requests
- Leave creator_user_id as NULL for unauthenticated requests
- Preserve creator_user_id on updates (no overwrite)
- NO visibility enforcement (that's Phase 5B.3)

Test Categories:
1. Draft creation with authentication
2. Draft creation without authentication
3. Draft updates preserve creator_user_id
4. Draft listing returns creator_user_id
5. Legacy drafts have NULL creator_user_id
"""

import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from app.main import app
from app.repositories.draft_repository import DraftRepository
from app.models.user import UserRole


@pytest.fixture
def client():
    """Create test client for API requests."""
    return TestClient(app)


@pytest.fixture
def draft_repository():
    """Create DraftRepository for database operations."""
    return DraftRepository()


@pytest.fixture
def worker_token(client):
    """Get JWT token for a worker user."""
    from app.repositories.user_repository import UserRepository
    from app.auth.password import hash_password
    from app.models.user import User
    from uuid import uuid4
    
    repo = UserRepository()
    
    # Check if user already exists
    existing = repo.get_user_by_email("worker_p5b2@example.com")
    if not existing:
        # Create user directly with repository
        user = User(
            user_id=uuid4(),
            name="Phase 5B.2 Worker",
            email="worker_p5b2@example.com",
            password_hash=hash_password("password123"),
            role=UserRole.WORKER,
            is_active=True
        )
        repo.create_user(user)
    
    # Login and get token
    login_response = client.post(
        "/api/auth/login",
        json={"email": "worker_p5b2@example.com", "password": "password123"}
    )
    
    assert login_response.status_code == 200, f"Failed to login: {login_response.text}"
    return login_response.json()["access_token"]


@pytest.fixture
def admin_token(client):
    """Get JWT token for an admin user."""
    from app.repositories.user_repository import UserRepository
    from app.auth.password import hash_password
    from app.models.user import User
    from uuid import uuid4
    
    repo = UserRepository()
    
    # Check if user already exists
    existing = repo.get_user_by_email("admin_p5b2@example.com")
    if not existing:
        # Create user directly with repository
        user = User(
            user_id=uuid4(),
            name="Phase 5B.2 Admin",
            email="admin_p5b2@example.com",
            password_hash=hash_password("admin123"),
            role=UserRole.ADMIN,
            is_active=True
        )
        repo.create_user(user)
    
    # Login and get token
    login_response = client.post(
        "/api/auth/login",
        json={"email": "admin_p5b2@example.com", "password": "admin123"}
    )
    
    assert login_response.status_code == 200, f"Failed to login: {login_response.text}"
    return login_response.json()["access_token"]


@pytest.fixture
def sample_receipt():
    """Sample receipt data for testing."""
    return {
        "receipt_date": "2026-01-26",
        "vendor_name": "Phase 5B.2 Test Vendor",
        "invoice_number": "P5B2-001",
        "total_amount": 5000.00,
        "tax_10_amount": 454.55,
        "tax_8_amount": 0.00,
        "business_location_id": "aichi",
        "staff_id": "staff_p5b2"
    }


# ============================================================================
# Test 1: Authenticated Draft Creation Sets creator_user_id
# ============================================================================

def test_create_draft_authenticated_sets_creator_id(client, worker_token, sample_receipt, draft_repository):
    """Test that authenticated draft creation sets creator_user_id."""
    # Create draft with authentication
    response = client.post(
        "/api/drafts",
        json={"receipt": sample_receipt},
        headers={"Authorization": f"Bearer {worker_token}"}
    )
    
    assert response.status_code == 201, f"Failed to create draft: {response.text}"
    data = response.json()
    
    # Verify creator_user_id is set in API response
    assert "creator_user_id" in data, "creator_user_id missing from response"
    assert data["creator_user_id"] is not None, "creator_user_id should not be NULL for authenticated request"
    
    # Verify creator_user_id is stored in database
    draft_id = data["draft_id"]
    draft = draft_repository.get_by_id(draft_id)
    assert draft is not None, "Draft not found in database"
    assert draft.creator_user_id is not None, "creator_user_id should be stored in database"
    
    # Cleanup
    draft_repository.delete(draft_id)


# ============================================================================
# Test 2: Unauthenticated Draft Creation Is Rejected
# ============================================================================

def test_create_draft_unauthenticated_rejected(client, sample_receipt):
    """Test that unauthenticated draft creation is blocked by auth middleware."""
    response = client.post(
        "/api/drafts",
        json={"receipt": sample_receipt}
    )

    assert response.status_code == 403, f"Unexpected status: {response.status_code} body={response.text}"
    data = response.json()
    assert data.get("detail") == "Not authenticated"


# ============================================================================
# Test 3: Draft Updates Preserve creator_user_id
# ============================================================================

def test_update_draft_preserves_creator_id(client, worker_token, admin_token, sample_receipt, draft_repository):
    """Test that updating a draft does NOT overwrite creator_user_id."""
    # Create draft as worker
    create_response = client.post(
        "/api/drafts",
        json={"receipt": sample_receipt},
        headers={"Authorization": f"Bearer {worker_token}"}
    )
    
    assert create_response.status_code == 201
    draft_id = create_response.json()["draft_id"]
    original_creator_id = create_response.json()["creator_user_id"]
    
    # Update draft as admin (different user)
    updated_receipt = sample_receipt.copy()
    updated_receipt["total_amount"] = 10000.00
    
    update_response = client.put(
        f"/api/drafts/{draft_id}",
        json={"receipt": updated_receipt},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert update_response.status_code == 200
    
    # Verify creator_user_id is preserved (not changed to admin's ID)
    updated_draft = draft_repository.get_by_id(draft_id)
    assert updated_draft.creator_user_id == original_creator_id, \
        "creator_user_id should NOT change on update"
    assert updated_draft.receipt.total_amount == 10000.00, \
        "Receipt data should be updated"
    
    # Cleanup
    draft_repository.delete(draft_id)


# ============================================================================
# Test 4: Draft Listing Returns creator_user_id
# ============================================================================

def test_list_drafts_returns_creator_id(client, worker_token, sample_receipt, draft_repository):
    """Test that listing drafts includes creator_user_id field."""
    # Create draft with authentication
    create_response = client.post(
        "/api/drafts",
        json={"receipt": sample_receipt},
        headers={"Authorization": f"Bearer {worker_token}"}
    )
    
    assert create_response.status_code == 201
    draft_id = create_response.json()["draft_id"]
    
    # List all drafts (Phase 5B.3: now requires auth)
    list_response = client.get(
        "/api/drafts",
        headers={"Authorization": f"Bearer {worker_token}"}
    )
    assert list_response.status_code == 200
    
    drafts = list_response.json()
    created_draft = next((d for d in drafts if d["draft_id"] == draft_id), None)
    
    assert created_draft is not None, "Created draft not found in list"
    assert "creator_user_id" in created_draft, "creator_user_id missing from list response"
    assert created_draft["creator_user_id"] is not None, "creator_user_id should be set"
    
    # Cleanup
    draft_repository.delete(draft_id)


# ============================================================================
# Test 5: Legacy Drafts Have NULL creator_user_id
# ============================================================================

def test_legacy_drafts_have_null_creator_id(client, admin_token, draft_repository):
    """Test that drafts created before Phase 5B.2 have NULL creator_user_id.
    
    Phase 5B.3 Note: Legacy drafts (NULL creator_user_id) are only accessible by ADMIN/HQ.
    """
    # Simulate legacy draft by creating via repository directly (no creator_user_id)
    from app.models.schema import Receipt
    from app.models.draft import DraftReceipt, DraftStatus
    
    legacy_receipt = Receipt(
        receipt_date="2026-01-01",
        vendor_name="Legacy Vendor",
        invoice_number="LEGACY-001",
        total_amount=1000.00,
        tax_10_amount=90.91,
        tax_8_amount=0.00,
        business_location_id="aichi",
        staff_id="staff_legacy"
    )
    
    legacy_draft = DraftReceipt(
        receipt=legacy_receipt,
        status=DraftStatus.DRAFT,
        creator_user_id=None  # Explicitly NULL for legacy
    )
    
    draft_repository.save(legacy_draft)
    
    # Retrieve via API (Phase 5B.3: use admin token since workers can't access legacy drafts)
    response = client.get(
        f"/api/drafts/{legacy_draft.draft_id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    
    data = response.json()
    assert "creator_user_id" in data, "creator_user_id missing from response"
    assert data["creator_user_id"] is None, "Legacy draft should have NULL creator_user_id"
    
    # Cleanup
    draft_repository.delete(legacy_draft.draft_id)


# ============================================================================
# Test 6: Different Users Can Create Drafts
# ============================================================================

def test_multiple_users_create_drafts(client, worker_token, admin_token, sample_receipt, draft_repository):
    """Test that multiple users can create drafts with their respective creator_user_ids."""
    # Create draft as worker
    worker_response = client.post(
        "/api/drafts",
        json={"receipt": sample_receipt},
        headers={"Authorization": f"Bearer {worker_token}"}
    )
    assert worker_response.status_code == 201
    worker_draft_id = worker_response.json()["draft_id"]
    worker_creator_id = worker_response.json()["creator_user_id"]
    
    # Create draft as admin
    admin_response = client.post(
        "/api/drafts",
        json={"receipt": sample_receipt},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert admin_response.status_code == 201
    admin_draft_id = admin_response.json()["draft_id"]
    admin_creator_id = admin_response.json()["creator_user_id"]
    
    # Verify different creator_user_ids
    assert worker_creator_id != admin_creator_id, \
        "Different users should have different creator_user_ids"
    
    # Verify both stored correctly
    worker_draft = draft_repository.get_by_id(worker_draft_id)
    admin_draft = draft_repository.get_by_id(admin_draft_id)
    
    assert worker_draft.creator_user_id == worker_creator_id
    assert admin_draft.creator_user_id == admin_creator_id
    
    # Cleanup
    draft_repository.delete(worker_draft_id)
    draft_repository.delete(admin_draft_id)
