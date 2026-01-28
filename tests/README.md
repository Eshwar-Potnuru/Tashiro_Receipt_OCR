# Phase 4E: Test Foundation Documentation

**Status**: Test foundation complete. All Phase 4D business logic frozen with comprehensive test coverage.

---

## Quick Start

```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx

# Run all tests
pytest tests/ -v

# Run unit tests only
pytest tests/unit/ -v

# Run integration tests only
pytest tests/integration/ -v

# Run specific test file
pytest tests/unit/test_draft_validation.py -v

# Run tests matching pattern
pytest tests/ -k "send_flow" -v
```

---

## Test Coverage Summary

### Unit Tests (24 tests)
**tests/unit/test_draft_validation.py** (13 tests)
- READY-TO-SEND validation rules
- Missing required fields (location, staff, vendor, date)
- Invalid values (negative/zero amounts)
- Staff-location mismatch detection
- Multiple error reporting
- Image reference handling (optional for manual entries)

**tests/unit/test_draft_service_ready_to_send.py** (11 tests)
- Draft CRUD operations (create, read, update, delete)
- Status transitions (DRAFT → SENT)
- Status filtering (list drafts by status)
- Timestamp behavior (created_at immutable, updated_at changes)
- Validation immutability (validation doesn't modify drafts)

### Integration Tests (29 tests)
**tests/integration/test_draft_create_flow.py** (15 tests)
- POST /api/drafts (draft creation)
- GET /api/drafts (list all drafts)
- GET /api/drafts/{id} (retrieve by ID)
- API contract compliance (status codes, response shapes)
- Data persistence verification
- UUID and timestamp format validation

**tests/integration/test_draft_send_flow.py** (12 tests)
- POST /api/drafts/send (send drafts to Excel)
- GET /api/drafts/{id}/validate (check ready-to-send status)
- Valid drafts send successfully
- Invalid drafts are blocked with errors
- Mixed valid/invalid batch sends
- Status changes after send

**tests/integration/test_image_ref_flow.py** (12 tests)
- Image reference persistence across operations
- image_ref in create, retrieve, update, send flows
- Null/omitted image_ref handling (manual entries)
- Format flexibility (UUID, filename, custom formats)

### Total: **53 test methods**

---

## Test Architecture

### Isolated Test Environment
Every test runs with:
- **Fresh temporary database** (SQLite in temp directory)
- **No shared state** between tests
- **Automatic cleanup** after test completion

### Mocking Strategy
**Excel writes are mocked** to prevent side effects:
```python
from unittest.mock import patch

with patch('app.services.summary_service.SummaryService.append_to_summary'):
    # Code that would write to Excel
    api_client.post("/api/drafts/send", json=payload)
```

**Staff API is auto-mocked** for all tests:
- Uses `mock_staff_config` fixture with test staff data
- Automatically patches StaffValidation for consistent behavior

### Key Fixtures (tests/conftest.py)
- `test_db_path`: Temporary database with auto-cleanup
- `draft_repository`: Isolated DraftRepository instance
- `draft_service`: DraftService configured for testing
- `valid_receipt`: Complete receipt passing all validation
- `incomplete_receipt`: Missing required fields (location, staff)
- `invalid_staff_receipt`: Staff ID doesn't match location
- `api_client`: FastAPI TestClient with mocked Excel writes
- `mock_staff_config`: Test staff data structure
- `mock_staff_validation`: Auto-mocked staff API (autouse=True)

---

## What Is Tested

✅ **READY-TO-SEND validation rules**
- Required fields enforcement (location, staff, vendor, date)
- Value validation (positive amounts, valid dates)
- Staff-location relationship validation
- Multiple error reporting

✅ **Draft lifecycle**
- Create → Save → Update → Validate → Send
- Status transitions (DRAFT → SENT)
- Timestamp behavior (created_at immutable, updated_at changes)

✅ **API contracts**
- HTTP status codes (201, 200, 404, 422)
- Response structure (draft_id, status, timestamps, receipt data)
- Request validation (missing required fields → 422)

✅ **Data persistence**
- Drafts persist across requests
- Receipt data stored correctly
- image_ref preserved through all operations

✅ **Business logic enforcement**
- Invalid drafts blocked from sending
- Valid drafts send successfully
- Incomplete drafts can be saved but won't send

---

## What Is NOT Tested (Intentionally)

❌ **Frontend UI** (JavaScript, HTML rendering)
- UI tests would require browser automation
- Out of scope for Phase 4E backend testing

❌ **OCR engines** (Google Vision, OCR.space, DocumentAI)
- OCR accuracy testing requires real receipt images
- OCR engine tests exist separately (tests/test_ocr_engines.py)

❌ **Excel formatting** (column widths, colors, conditional formatting)
- Excel formatting tests exist separately (tests/test_accuracy_metrics.py)
- Phase 4E focuses on draft lifecycle, not formatting

❌ **Authentication** (JWT, session management)
- Not implemented in current system
- Future feature

❌ **Database migrations**
- SQLAlchemy schema management tested manually
- Not part of draft lifecycle testing

---

## Test Principles (Phase 4E Rules)

### Real Value, Not Placeholders
**Every test validates real business logic:**
```python
# ✅ GOOD: Tests actual READY-TO-SEND rule
def test_missing_staff_id_blocks_send(draft_service, incomplete_receipt):
    result = draft_service.validate_ready_to_send(incomplete_receipt)
    assert result.ready is False
    assert "staff_id is required" in result.errors

# ❌ BAD: Placeholder test (forbidden)
def test_validation():
    assert True  # TODO: implement
```

### No Runtime Behavior Changes
**Tests observe existing logic, do not modify:**
- Tests use existing models, services, and APIs
- No refactoring of business logic
- No new API endpoints or features
- Only imports and test code added

### Isolated & Deterministic
**Every test is independent:**
- Fresh database per test
- No dependencies between tests
- Predictable test data via fixtures
- Mocked external services (Excel, staff API)

---

## Running Tests in CI/CD

### GitHub Actions Example
```yaml
name: Test Suite
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - run: pip install -r requirements.txt
      - run: pytest tests/ -v --tb=short
```

### Coverage Report (Optional)
```bash
# Install coverage tool
pip install pytest-cov

# Run with coverage
pytest tests/ --cov=app --cov-report=html

# View report
open htmlcov/index.html
```

---

## Troubleshooting

### Import Errors
**Problem**: `ModuleNotFoundError: No module named 'app'`
**Solution**: Run pytest from project root:
```bash
cd /path/to/Receipt-ocr-v1-git/
pytest tests/ -v
```

### Database Locked Errors
**Problem**: `sqlite3.OperationalError: database is locked`
**Solution**: Each test gets a fresh DB. If you see this, ensure:
- No manual database connections are open
- Use the `test_db_path` fixture for all DB operations
- Don't share database instances between tests

### Excel Write Errors
**Problem**: Tests actually writing to Excel files
**Solution**: Ensure `app.services.summary_service.SummaryService.append_to_summary` is mocked:
```python
from unittest.mock import patch

with patch('app.services.summary_service.SummaryService.append_to_summary'):
    # Your test code here
```

The `api_client` fixture already includes this mock for integration tests.

### Fixture Not Found
**Problem**: `fixture 'valid_receipt' not found`
**Solution**: Fixtures are defined in `tests/conftest.py`. Ensure:
- `conftest.py` exists in `tests/` directory
- pytest is discovering the `tests/` directory
- Run from project root: `pytest tests/`

---

## Adding New Tests

### Unit Test Example
```python
# tests/unit/test_my_feature.py
import pytest

def test_my_validation_rule(draft_service, valid_receipt):
    """Test that my new validation rule works."""
    # Modify receipt to violate rule
    valid_receipt.some_field = "invalid_value"
    
    # Validate
    result = draft_service.validate_ready_to_send(valid_receipt)
    
    # Assert rule is enforced
    assert result.ready is False
    assert "some_field must be valid" in result.errors
```

### Integration Test Example
```python
# tests/integration/test_my_api_flow.py
import pytest

class TestMyAPIFlow:
    def test_my_endpoint(self, api_client, valid_receipt):
        """Test that my API endpoint works."""
        payload = {"receipt": valid_receipt.dict()}
        
        response = api_client.post("/api/my-endpoint", json=payload)
        
        assert response.status_code == 201
        data = response.json()
        assert "my_field" in data
```

---

## Test Data Fixtures

### valid_receipt
Complete receipt passing all READY-TO-SEND validation:
```python
{
    "business_location": "Kobe",
    "staff_id": "test-staff-001",
    "vendor_name": "TEST VENDOR",
    "total_amount": 1000.0,
    "receipt_date": "2026-01-27"
    # ... all required fields
}
```

### incomplete_receipt
Missing required fields (location, staff):
```python
{
    "vendor_name": "INCOMPLETE VENDOR",
    "total_amount": 500.0,
    # business_location: missing
    # staff_id: missing
}
```

### invalid_staff_receipt
Staff ID doesn't match location:
```python
{
    "business_location": "Kobe",
    "staff_id": "tokyo-staff-999",  # Wrong location
    "vendor_name": "TEST VENDOR",
    "total_amount": 1000.0
}
```

---

## Phase 4E Completion Checklist

✅ **Test structure created**
- tests/unit/ directory
- tests/integration/ directory
- tests/conftest.py with fixtures

✅ **Unit tests implemented** (24 tests)
- Validation rule tests
- Service behavior tests

✅ **Integration tests implemented** (29 tests)
- API contract tests
- Data persistence tests
- Send flow tests

✅ **Test utilities configured**
- Isolated database fixtures
- Mock strategy for Excel writes
- Mock strategy for staff API

✅ **Documentation written**
- This README.md
- Inline docstrings in all test files

✅ **No runtime behavior changed**
- All business logic unchanged
- Only test files added
- No refactoring performed

---

## Next Steps (Post Phase 4E)

**Phase 4E is complete.** The draft lifecycle is now frozen with comprehensive test coverage.

Future work:
1. **Run tests in CI/CD** (GitHub Actions, GitLab CI)
2. **Add coverage monitoring** (pytest-cov integration)
3. **Phase 5**: UI improvements (if needed)
4. **Phase 6**: Additional features (image preview, batch operations)

---

## Questions?

**Test failing?** Check:
1. Are you running from project root?
2. Is pytest installed? (`pip install pytest`)
3. Is conftest.py in tests/ directory?
4. Are fixtures available in conftest.py?

**Need more test coverage?** Add tests following patterns in existing files.

**Test taking too long?** Each test creates a fresh database. This is intentional for isolation. Tests should still complete in <30 seconds total.

---

**Phase 4E Test Foundation - Complete** ✅
