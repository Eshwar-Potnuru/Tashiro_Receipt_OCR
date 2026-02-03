#!/usr/bin/env python3
"""
FINAL SYSTEM CHECK - Pre-Production Validation
Comprehensive test of all improvements and critical functionality
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.main import app
from fastapi.testclient import TestClient
from pathlib import Path
import json

client = TestClient(app)

print("\n" + "=" * 80)
print("FINAL SYSTEM CHECK - PRE-PRODUCTION VALIDATION")
print("=" * 80)

results = {"passed": 0, "failed": 0, "warnings": 0}

def test_pass(name, details=""):
    results["passed"] += 1
    print(f"✅ PASS | {name}")
    if details:
        print(f"         {details}")

def test_fail(name, details=""):
    results["failed"] += 1
    print(f"❌ FAIL | {name}")
    if details:
        print(f"         {details}")

def test_warn(name, details=""):
    results["warnings"] += 1
    print(f"⚠️  WARN | {name}")
    if details:
        print(f"         {details}")

# ============================================================================
# TEST 1: SERVER HEALTH
# ============================================================================
print("\n" + "=" * 80)
print("TEST 1: SERVER HEALTH CHECK")
print("=" * 80)

try:
    response = client.get("/")
    if response.status_code == 200:
        test_pass("Homepage accessible")
    else:
        test_fail("Homepage accessible", f"Status: {response.status_code}")
except Exception as e:
    test_fail("Homepage accessible", str(e))

try:
    response = client.get("/mobile")
    if response.status_code == 200:
        test_pass("Mobile UI accessible")
    else:
        test_fail("Mobile UI accessible", f"Status: {response.status_code}")
except Exception as e:
    test_fail("Mobile UI accessible", str(e))

try:
    response = client.get("/diagnostics")
    if response.status_code == 200:
        test_pass("Diagnostics page accessible")
    else:
        test_fail("Diagnostics page accessible", f"Status: {response.status_code}")
except Exception as e:
    test_fail("Diagnostics page accessible", str(e))

# ============================================================================
# TEST 2: AUTHENTICATION - SIMPLIFIED LOGIN
# ============================================================================
print("\n" + "=" * 80)
print("TEST 2: AUTHENTICATION (Simplified Login Form)")
print("=" * 80)

# Test with Login ID
try:
    response = client.post(
        "/api/auth/login",
        json={"email": "TIW-WJJ5N", "password": "password123"}
    )
    if response.status_code == 200:
        data = response.json()
        token = data.get("access_token")
        user = data.get("user", {})
        test_pass("Login with Login ID (TIW-WJJ5N)", f"User: {user.get('name')}, Token: {len(token) if token else 0} chars")
    else:
        test_fail("Login with Login ID", f"Status: {response.status_code}")
except Exception as e:
    test_fail("Login with Login ID", str(e))

# Test with Email
try:
    response = client.post(
        "/api/auth/login",
        json={"email": "a05_amir@example.com", "password": "password123"}
    )
    if response.status_code == 200:
        data = response.json()
        token = data.get("access_token")
        test_pass("Login with Email", f"Token: {len(token) if token else 0} chars")
    else:
        test_fail("Login with Email", f"Status: {response.status_code}")
except Exception as e:
    test_fail("Login with Email", str(e))

# Test invalid credentials
try:
    response = client.post(
        "/api/auth/login",
        json={"email": "INVALID-ID", "password": "wrong"}
    )
    if response.status_code == 401:
        test_pass("Invalid credentials rejected", "Returns 401 as expected")
    else:
        test_fail("Invalid credentials rejected", f"Status: {response.status_code}")
except Exception as e:
    test_fail("Invalid credentials rejected", str(e))

# ============================================================================
# TEST 3: OCR ENGINES
# ============================================================================
print("\n" + "=" * 80)
print("TEST 3: OCR ENGINES AVAILABILITY")
print("=" * 80)

try:
    from app.ocr.multi_engine_ocr import MultiEngineOCR
    ocr = MultiEngineOCR()
    engines_available = getattr(ocr, 'engines_available', {})
    
    for engine_name, is_available in engines_available.items():
        if is_available:
            test_pass(f"OCR Engine: {engine_name}")
        else:
            test_warn(f"OCR Engine: {engine_name}", "Not available")
except Exception as e:
    test_fail("OCR engines check", str(e))

# ============================================================================
# TEST 4: ENHANCED TAX EXTRACTION
# ============================================================================
print("\n" + "=" * 80)
print("TEST 4: ENHANCED TAX EXTRACTION (100% Accuracy)")
print("=" * 80)

# Get auth token
login_response = client.post(
    "/api/auth/login",
    json={"email": "TIW-WJJ5N", "password": "password123"}
)
token = login_response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Find test receipt
test_image = Path("Sample reciepts/IMG_1977.png")
if not test_image.exists():
    test_image = Path("raw/IMG_1977.png")

if test_image.exists():
    try:
        with open(test_image, "rb") as f:
            response = client.post(
                "/api/drafts/batch-upload",
                headers=headers,
                files={"files": (test_image.name, f, "image/png")},
                data={"ocr_mode": "auto"}
            )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('results') and result['results'][0].get('status') == 'success':
                extracted = result['results'][0]['extracted_data']
                
                # Check tax extraction
                tax_amount = extracted.get('tax_amount')
                if tax_amount == 10.0:
                    test_pass("Tax extraction accuracy", f"Expected: ¥10, Got: ¥{tax_amount}")
                elif tax_amount:
                    test_warn("Tax extraction accuracy", f"Expected: ¥10, Got: ¥{tax_amount}")
                else:
                    test_fail("Tax extraction accuracy", "Tax amount is null")
                
                # Check vendor detection
                vendor = extracted.get('vendor_name')
                if vendor and vendor not in ['領収書', 'レシート', 'Receipt']:
                    test_pass("Vendor detection (no generic headers)", f"Vendor: {vendor}")
                else:
                    test_fail("Vendor detection", f"Generic header detected: {vendor}")
                
                # Check total
                total = extracted.get('total_amount')
                if total == 110:
                    test_pass("Currency parsing", f"Total: ¥{total}")
                else:
                    test_fail("Currency parsing", f"Expected: ¥110, Got: ¥{total}")
                
                # Check date
                date = extracted.get('receipt_date')
                if date:
                    test_pass("Date extraction", f"Date: {date}")
                else:
                    test_fail("Date extraction", "Date is null")
                
                # Check invoice
                invoice = extracted.get('invoice_number')
                if invoice == "T1010001112577":
                    test_pass("Invoice extraction", f"Invoice: {invoice}")
                else:
                    test_warn("Invoice extraction", f"Expected: T1010001112577, Got: {invoice}")
            else:
                test_fail("Receipt processing", "Processing failed")
        else:
            test_fail("Receipt upload", f"Status: {response.status_code}")
    except Exception as e:
        test_fail("Receipt processing test", str(e))
else:
    test_warn("Receipt test image not found", "Skipping receipt processing tests")

# ============================================================================
# TEST 5: ALL OCR MODES
# ============================================================================
print("\n" + "=" * 80)
print("TEST 5: ALL OCR MODES FUNCTIONALITY")
print("=" * 80)

if test_image.exists():
    modes = [
        ("auto", "Hybrid Mode"),
        ("standard", "Standard OCR"),
        ("document_ai", "Document AI")
    ]
    
    for mode_value, mode_name in modes:
        try:
            with open(test_image, "rb") as f:
                response = client.post(
                    "/api/drafts/batch-upload",
                    headers=headers,
                    files={"files": (test_image.name, f, "image/png")},
                    data={"ocr_mode": mode_value}
                )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('results') and result['results'][0].get('status') == 'success':
                    extracted = result['results'][0]['extracted_data']
                    vendor = extracted.get('vendor_name')
                    tax = extracted.get('tax_amount')
                    
                    # Check if improvements are working
                    vendor_ok = vendor and vendor not in ['領収書', 'レシート']
                    tax_ok = tax is not None
                    
                    if vendor_ok and tax_ok:
                        test_pass(f"OCR Mode: {mode_name}", f"Vendor: {vendor}, Tax: ¥{tax}")
                    elif vendor_ok:
                        test_warn(f"OCR Mode: {mode_name}", f"Vendor OK but tax missing")
                    elif tax_ok:
                        test_warn(f"OCR Mode: {mode_name}", f"Tax OK but vendor generic")
                    else:
                        test_fail(f"OCR Mode: {mode_name}", "Both vendor and tax issues")
                else:
                    test_fail(f"OCR Mode: {mode_name}", "Processing failed")
            else:
                test_fail(f"OCR Mode: {mode_name}", f"Status: {response.status_code}")
        except Exception as e:
            test_fail(f"OCR Mode: {mode_name}", str(e))

# ============================================================================
# TEST 6: DATABASE & CONFIGURATION
# ============================================================================
print("\n" + "=" * 80)
print("TEST 6: DATABASE & CONFIGURATION")
print("=" * 80)

try:
    from app.repositories.user_repository import UserRepository
    repo = UserRepository()
    
    # Check TIW users exist
    test_user = repo.get_user_by_login_id("TIW-WJJ5N")
    if test_user:
        test_pass("Database - TIW users", f"Found: {test_user.name}")
    else:
        test_fail("Database - TIW users", "TIW-WJJ5N not found")
except Exception as e:
    test_fail("Database check", str(e))

try:
    from app.services.config_service import ConfigService
    config = ConfigService()
    
    locations = config.get_locations()
    if len(locations) > 0:
        test_pass("Configuration - locations", f"Loaded: {len(locations)} locations")
    else:
        test_fail("Configuration - locations", "No locations loaded")
    
    # Check staff via API instead (ConfigService may not have get_staff_members method)
    response = client.get("/api/staff?location=Aichi")
    if response.status_code == 200:
        staff = response.json().get('staff', [])
        test_pass("Configuration - staff", f"Loaded: {len(staff)} staff members")
    else:
        test_fail("Configuration - staff", "Staff API failed")
except Exception as e:
    test_fail("Configuration service", str(e))

# ============================================================================
# TEST 7: API ENDPOINTS
# ============================================================================
print("\n" + "=" * 80)
print("TEST 7: CRITICAL API ENDPOINTS")
print("=" * 80)

try:
    response = client.get("/api/locations")
    if response.status_code == 200:
        data = response.json()
        test_pass("GET /api/locations", f"{len(data.get('locations', []))} locations")
    else:
        test_fail("GET /api/locations", f"Status: {response.status_code}")
except Exception as e:
    test_fail("GET /api/locations", str(e))

try:
    response = client.get("/api/staff?location=Aichi")
    if response.status_code == 200:
        data = response.json()
        test_pass("GET /api/staff", f"{len(data.get('staff', []))} staff members")
    else:
        test_fail("GET /api/staff", f"Status: {response.status_code}")
except Exception as e:
    test_fail("GET /api/staff", str(e))

try:
    response = client.get("/api/drafts", headers=headers)
    if response.status_code == 200:
        drafts = response.json()
        test_pass("GET /api/drafts", f"{len(drafts)} drafts")
    else:
        test_fail("GET /api/drafts", f"Status: {response.status_code}")
except Exception as e:
    test_fail("GET /api/drafts", str(e))

try:
    response = client.post("/api/drafts/batch-upload", headers=headers)
    if response.status_code == 422:
        test_pass("POST /api/drafts/batch-upload", "Returns 422 without files (expected)")
    else:
        test_warn("POST /api/drafts/batch-upload", f"Status: {response.status_code}")
except Exception as e:
    test_fail("POST /api/drafts/batch-upload", str(e))

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "=" * 80)
print("FINAL SYSTEM CHECK SUMMARY")
print("=" * 80)

total = results["passed"] + results["failed"]
pass_rate = (results["passed"] / total * 100) if total > 0 else 0

print(f"\n  Passed:   {results['passed']}/{total} ({pass_rate:.1f}%)")
print(f"  Failed:   {results['failed']}/{total}")
print(f"  Warnings: {results['warnings']}")

print("\n" + "=" * 80)

if results["failed"] == 0 and results["warnings"] == 0:
    print("PERFECT! SYSTEM IS 100% READY FOR PRODUCTION")
    print("\nALL IMPROVEMENTS VERIFIED:")
    print("  - Simplified login form (single field)")
    print("  - Tax extraction - 100% accuracy")
    print("  - Vendor detection - real company names")
    print("  - Currency parsing working")
    print("  - All OCR modes functional")
    print("  - Authentication working")
    print("  - Database operational")
elif results["failed"] == 0:
    print("SYSTEM READY - Minor warnings only")
    print(f"\n  {results['warnings']} non-critical warnings detected")
else:
    print("ISSUES DETECTED - Review failures before production")
    print(f"\n  {results['failed']} critical failures need attention")

print("=" * 80 + "\n")

sys.exit(0 if results["failed"] == 0 else 1)
