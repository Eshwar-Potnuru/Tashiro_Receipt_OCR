"""Pytest configuration and shared fixtures for Tashiro Receipt OCR tests.

Phase 4E: Test Foundation
- Provides isolated test database
- Mock Excel writes (no side effects)
- Shared fixtures for common test scenarios
"""

import os
import tempfile
from pathlib import Path
from typing import Generator
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.draft import DraftReceipt, DraftStatus
from app.models.schema import Receipt
from app.repositories.draft_repository import DraftRepository
from app.services.draft_service import DraftService


@pytest.fixture(scope="function")
def test_db_path() -> Generator[str, None, None]:
    """Create a temporary database for each test."""
    with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as f:
        db_path = f.name
    
    yield db_path
    
    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture(scope="function")
def draft_repository(test_db_path: str) -> DraftRepository:
    """Provide a DraftRepository with isolated test database."""
    return DraftRepository(db_path=test_db_path)


@pytest.fixture(scope="function")
def draft_service(draft_repository: DraftRepository) -> DraftService:
    """Provide a DraftService with test repository."""
    service = DraftService(repository=draft_repository)
    return service


@pytest.fixture
def valid_receipt() -> Receipt:
    """A valid receipt that passes all validation rules."""
    return Receipt(
        receipt_date="2026-01-27",
        vendor_name="Test Vendor Co.",
        invoice_number="INV-12345",
        total_amount=10000.00,
        tax_10_amount=909.09,
        tax_8_amount=0.00,
        business_location_id="Kashima",
        staff_id="kas_001"
    )


@pytest.fixture
def incomplete_receipt() -> Receipt:
    """A receipt missing required fields."""
    return Receipt(
        receipt_date="2026-01-27",
        vendor_name="Test Vendor",
        invoice_number="",
        total_amount=5000.00,
        tax_10_amount=454.55,
        tax_8_amount=0.00,
        business_location_id=None,  # Missing
        staff_id=None  # Missing
    )


@pytest.fixture
def invalid_staff_receipt() -> Receipt:
    """Receipt with staff_id that doesn't match location."""
    return Receipt(
        receipt_date="2026-01-27",
        vendor_name="Test Vendor",
        invoice_number="INV-999",
        total_amount=3000.00,
        tax_10_amount=272.73,
        tax_8_amount=0.00,
        business_location_id="Kashima",
        staff_id="tok_001"  # Tokyo staff, not Kashima
    )


@pytest.fixture
def api_client():
    """FastAPI test client with mocked Excel writes."""
    from app.main import app
    
    # Mock Excel exports to prevent file writes during tests
    with patch('app.exporters.excel_exporter.ExcelExporter.export_to_excel'):
        with patch('app.services.summary_service.SummaryService.send_receipts'):
            client = TestClient(app)
            yield client


@pytest.fixture
def mock_staff_config():
    """Mock staff configuration for validation tests."""
    return {
        "Kashima": [
            {"id": "kas_001", "name": "Test Staff 1"},
            {"id": "kas_002", "name": "Test Staff 2"}
        ],
        "Tokyo": [
            {"id": "tok_001", "name": "Tokyo Staff 1"}
        ],
        "Aichi": [
            {"id": "aic_001", "name": "Aichi Staff 1"}
        ]
    }


@pytest.fixture(autouse=True)
def mock_staff_validation(mock_staff_config, monkeypatch):
    """Auto-mock staff validation for all tests."""
    def mock_get_staff(self, location: str):
        return mock_staff_config.get(location, [])
    
    monkeypatch.setattr(
        "app.services.config_service.ConfigService.get_staff_for_location",
        mock_get_staff
    )
