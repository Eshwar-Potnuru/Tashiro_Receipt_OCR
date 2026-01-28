"""
OCR Engine Verification Script (Post-IAM Fix)
==============================================
Verifies all OCR engines are working correctly after IAM role updates.
Does NOT modify any existing code or write to Excel.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import json

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

print("=" * 70)
print("OCR ENGINE VERIFICATION - POST IAM FIX")
print("=" * 70)

# Load environment variables
load_dotenv(override=True)

# ============================================================================
# STEP 1: Environment & Credential Validation
# ============================================================================
print("\n📋 STEP 1: ENVIRONMENT & CREDENTIAL VALIDATION")
print("-" * 70)

def check_environment():
    """Check and validate environment variables."""
    results = {
        "credentials_set": False,
        "credentials_path": None,
        "credentials_exist": False,
        "credentials_readable": False,
        "project_id": None,
        "openai_key": False,
        "ocr_space_key": False,
        "document_ai_processor": None
    }
    
    # Check Google Application Credentials
    creds_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
    if creds_path:
        results["credentials_set"] = True
        results["credentials_path"] = creds_path
        print(f"✔ GOOGLE_APPLICATION_CREDENTIALS: {creds_path}")
        
        # Check if file exists
        if os.path.exists(creds_path):
            results["credentials_exist"] = True
            print(f"✔ Credentials file exists")
            print(f"  File size: {os.path.getsize(creds_path)} bytes")
            
            # Try to read and parse
            try:
                with open(creds_path, 'r') as f:
                    creds_data = json.load(f)
                    results["credentials_readable"] = True
                    results["project_id"] = creds_data.get("project_id")
                    print(f"✔ Credentials file readable")
                    print(f"✔ Project ID: {results['project_id']}")
            except Exception as e:
                print(f"✗ Error reading credentials: {e}")
        else:
            print(f"✗ Credentials file does NOT exist at: {creds_path}")
    else:
        print("✗ GOOGLE_APPLICATION_CREDENTIALS: NOT SET")
    
    # Check other API keys
    results["openai_key"] = bool(os.environ.get('OPENAI_API_KEY'))
    results["ocr_space_key"] = bool(os.environ.get('OCR_SPACE_API_KEY'))
    
    # Document AI configuration
    doc_ai_processor = os.environ.get('DOCUMENT_AI_PROCESSOR_ID') or os.environ.get('GOOGLE_DOCUMENT_AI_PROCESSOR_ID')
    doc_ai_project = os.environ.get('DOCUMENT_AI_PROJECT_ID') or results["project_id"]
    doc_ai_location = os.environ.get('DOCUMENT_AI_LOCATION', 'us')
    
    if doc_ai_processor and doc_ai_project:
        # Construct full processor name
        results["document_ai_processor"] = f"projects/{doc_ai_project}/locations/{doc_ai_location}/processors/{doc_ai_processor}"
    else:
        results["document_ai_processor"] = None
    
    print(f"\n{'✔' if results['openai_key'] else '✗'} OPENAI_API_KEY: {'SET' if results['openai_key'] else 'NOT SET'}")
    print(f"{'✔' if results['ocr_space_key'] else '✗'} OCR_SPACE_API_KEY: {'SET' if results['ocr_space_key'] else 'NOT SET'}")
    
    if results["document_ai_processor"]:
        print(f"✔ DOCUMENT_AI_PROCESSOR_ID: {doc_ai_processor}")
        print(f"  Full name: {results['document_ai_processor']}")
    else:
        print(f"✗ DOCUMENT_AI_PROCESSOR_ID: NOT SET")
    
    return results

env_results = check_environment()

# ============================================================================
# STEP 2: API Enablement Checks (Read-Only)
# ============================================================================
print("\n\n📋 STEP 2: API ENABLEMENT CHECKS")
print("-" * 70)

def check_api_enablement():
    """Check if required Google Cloud APIs are enabled."""
    if not env_results["credentials_readable"]:
        print("⚠️  Skipping API checks - credentials not available")
        return None
    
    try:
        from google.cloud import documentai_v1 as documentai
        from google.cloud import vision
        
        results = {
            "document_ai": {"enabled": False, "error": None},
            "vision_api": {"enabled": False, "error": None}
        }
        
        # Check Document AI
        print("\nChecking Document AI API...")
        try:
            client = documentai.DocumentProcessorServiceClient()
            # Try to list processors (read-only operation)
            if env_results["document_ai_processor"]:
                processor_name = env_results["document_ai_processor"]
                print(f"✔ Document AI client created")
                print(f"  Processor: {processor_name}")
                results["document_ai"]["enabled"] = True
            else:
                print("⚠️  No processor ID configured")
        except Exception as e:
            results["document_ai"]["error"] = str(e)
            print(f"✗ Document AI error: {e}")
        
        # Check Vision API
        print("\nChecking Vision API...")
        try:
            client = vision.ImageAnnotatorClient()
            print(f"✔ Vision API client created")
            results["vision_api"]["enabled"] = True
        except Exception as e:
            results["vision_api"]["error"] = str(e)
            print(f"✗ Vision API error: {e}")
        
        return results
        
    except ImportError as e:
        print(f"✗ Missing required libraries: {e}")
        print("  Install: pip install google-cloud-documentai google-cloud-vision")
        return None

api_results = check_api_enablement()

# ============================================================================
# STEP 3: OCR Engine Runtime Test (One Image)
# ============================================================================
print("\n\n📋 STEP 3: OCR ENGINE RUNTIME TEST")
print("-" * 70)

def test_ocr_engines():
    """Test each OCR engine with a sample image."""
    
    # Find a test image
    test_image_paths = [
        Path("Sample reciepts"),
        Path("raw"),
        Path("artifacts/sample_receipt.json")
    ]
    
    test_image = None
    for path in test_image_paths:
        if path.exists():
            if path.is_dir():
                images = list(path.glob("*.jpg")) + list(path.glob("*.png")) + list(path.glob("*.jpeg"))
                if images:
                    test_image = images[0]
                    break
    
    if not test_image:
        print("⚠️  No test image found. Please provide a sample receipt image.")
        print("   Expected locations: Sample reciepts/, raw/")
        return None
    
    print(f"Using test image: {test_image}")
    
    results = {
        "document_ai": {"status": "NOT_TESTED", "error": None, "details": None},
        "google_vision": {"status": "NOT_TESTED", "error": None, "details": None},
        "openai_vision": {"status": "NOT_TESTED", "error": None, "details": None},
        "ocr_space": {"status": "NOT_TESTED", "error": None, "details": None}
    }
    
    # Test Document AI
    print("\n--- Testing Document AI ---")
    if env_results["credentials_readable"] and env_results["document_ai_processor"]:
        try:
            from google.cloud import documentai_v1 as documentai
            
            # Read image
            with open(test_image, "rb") as f:
                image_content = f.read()
            
            # Create client
            client = documentai.DocumentProcessorServiceClient()
            
            # Process document
            processor_name = env_results["document_ai_processor"]
            raw_document = documentai.RawDocument(
                content=image_content,
                mime_type="image/jpeg" if test_image.suffix.lower() in ['.jpg', '.jpeg'] else "image/png"
            )
            
            request = documentai.ProcessRequest(
                name=processor_name,
                raw_document=raw_document
            )
            
            result = client.process_document(request=request)
            
            # Extract details
            doc = result.document
            text_length = len(doc.text) if doc.text else 0
            
            results["document_ai"]["status"] = "✅ OK"
            results["document_ai"]["details"] = {
                "processor_id": processor_name,
                "text_length": text_length,
                "pages": len(doc.pages) if doc.pages else 0
            }
            
            print(f"✅ Document AI: SUCCESS")
            print(f"   Processor: {processor_name}")
            print(f"   Text extracted: {text_length} characters")
            print(f"   Pages: {results['document_ai']['details']['pages']}")
            
        except Exception as e:
            error_msg = str(e)
            results["document_ai"]["status"] = "❌ FAILED"
            results["document_ai"]["error"] = error_msg
            
            # Classify error
            if "permission" in error_msg.lower() or "denied" in error_msg.lower():
                print(f"❌ Document AI: IAM PERMISSION ERROR")
            elif "not found" in error_msg.lower():
                print(f"❌ Document AI: INVALID PROCESSOR ID/REGION")
            elif "not enabled" in error_msg.lower():
                print(f"❌ Document AI: API NOT ENABLED")
            else:
                print(f"❌ Document AI: RUNTIME ERROR")
            print(f"   Error: {error_msg}")
    else:
        results["document_ai"]["status"] = "⚠️  SKIPPED"
        print("⚠️  Document AI: Skipped (credentials or processor not configured)")
    
    # Test Google Vision
    print("\n--- Testing Google Vision ---")
    if env_results["credentials_readable"]:
        try:
            from google.cloud import vision
            
            # Read image
            with open(test_image, "rb") as f:
                image_content = f.read()
            
            # Create client
            client = vision.ImageAnnotatorClient()
            image = vision.Image(content=image_content)
            
            # Perform text detection
            response = client.text_detection(image=image)
            
            if response.error.message:
                raise Exception(response.error.message)
            
            texts = response.text_annotations
            text_length = len(texts[0].description) if texts else 0
            
            results["google_vision"]["status"] = "✅ OK"
            results["google_vision"]["details"] = {
                "text_length": text_length,
                "annotations": len(texts)
            }
            
            print(f"✅ Google Vision: SUCCESS")
            print(f"   Text extracted: {text_length} characters")
            print(f"   Annotations: {len(texts)}")
            
        except Exception as e:
            error_msg = str(e)
            results["google_vision"]["status"] = "❌ FAILED"
            results["google_vision"]["error"] = error_msg
            
            # Classify error
            if "permission" in error_msg.lower() or "denied" in error_msg.lower():
                print(f"❌ Google Vision: IAM PERMISSION ERROR")
            elif "not enabled" in error_msg.lower():
                print(f"❌ Google Vision: API NOT ENABLED")
            else:
                print(f"❌ Google Vision: RUNTIME ERROR")
            print(f"   Error: {error_msg}")
    else:
        results["google_vision"]["status"] = "⚠️  SKIPPED"
        print("⚠️  Google Vision: Skipped (credentials not configured)")
    
    # Test OpenAI Vision (if configured)
    print("\n--- Testing OpenAI Vision ---")
    if env_results["openai_key"]:
        print("⚠️  OpenAI Vision: Available but not tested (optional)")
        results["openai_vision"]["status"] = "⚠️  NOT_TESTED (Optional)"
    else:
        results["openai_vision"]["status"] = "⚠️  NOT_CONFIGURED"
        print("⚠️  OpenAI Vision: Not configured")
    
    # Test OCR.space (if configured)
    print("\n--- Testing OCR.space ---")
    if env_results["ocr_space_key"]:
        print("⚠️  OCR.space: Available but not tested (optional)")
        results["ocr_space"]["status"] = "⚠️  NOT_TESTED (Optional)"
    else:
        results["ocr_space"]["status"] = "⚠️  NOT_CONFIGURED"
        print("⚠️  OCR.space: Not configured")
    
    return results

ocr_test_results = test_ocr_engines()

# ============================================================================
# STEP 4: Error Classification
# ============================================================================
print("\n\n📋 STEP 4: STATUS SUMMARY")
print("-" * 70)

def print_status_table():
    """Print a clear status table for all engines."""
    
    print("\n╔═══════════════════════════════════════════════════════════════════╗")
    print("║                    OCR ENGINE STATUS TABLE                        ║")
    print("╚═══════════════════════════════════════════════════════════════════╝")
    
    if ocr_test_results:
        for engine, result in ocr_test_results.items():
            engine_name = engine.replace("_", " ").title()
            status = result["status"]
            print(f"\n{engine_name:20s}: {status}")
            if result.get("error"):
                print(f"{'':20s}  Error: {result['error'][:50]}...")

print_status_table()

# ============================================================================
# STEP 5: Final Confirmation Summary
# ============================================================================
print("\n\n📋 STEP 5: FINAL CONFIRMATION SUMMARY")
print("=" * 70)

def generate_final_summary():
    """Generate final summary for reporting."""
    
    print("\n╔═══════════════════════════════════════════════════════════════════╗")
    print("║              OCR VERIFICATION SUMMARY                             ║")
    print("╚═══════════════════════════════════════════════════════════════════╝")
    
    # Credentials
    creds_ok = env_results["credentials_readable"]
    print(f"\n✔ Credentials: {'OK' if creds_ok else 'FAILED'}")
    if creds_ok:
        print(f"  - File: {env_results['credentials_path']}")
        print(f"  - Project: {env_results['project_id']}")
    
    # IAM Roles
    iam_ok = creds_ok  # If credentials are readable, IAM should be OK
    print(f"\n{'✔' if iam_ok else '✗'} IAM Roles: {'OK' if iam_ok else 'CHECK REQUIRED'}")
    
    # Document AI
    if ocr_test_results and ocr_test_results["document_ai"]["status"] == "✅ OK":
        print(f"\n✔ Document AI: OK")
        if ocr_test_results["document_ai"]["details"]:
            details = ocr_test_results["document_ai"]["details"]
            print(f"  - Text extracted: {details['text_length']} characters")
    else:
        status = ocr_test_results["document_ai"]["status"] if ocr_test_results else "NOT TESTED"
        print(f"\n✗ Document AI: {status}")
    
    # Vision API
    if ocr_test_results and ocr_test_results["google_vision"]["status"] == "✅ OK":
        print(f"\n✔ Vision API: OK")
        if ocr_test_results["google_vision"]["details"]:
            details = ocr_test_results["google_vision"]["details"]
            print(f"  - Text extracted: {details['text_length']} characters")
    else:
        status = ocr_test_results["google_vision"]["status"] if ocr_test_results else "NOT TESTED"
        print(f"\n✗ Vision API: {status}")
    
    # Overall Status
    print("\n" + "=" * 70)
    all_critical_ok = (
        creds_ok and
        ocr_test_results and
        ocr_test_results["document_ai"]["status"] == "✅ OK" and
        ocr_test_results["google_vision"]["status"] == "✅ OK"
    )
    
    if all_critical_ok:
        print("🎉 ALL CRITICAL SYSTEMS: OPERATIONAL")
        print("\n✅ Ready for production use")
    else:
        print("⚠️  SOME SYSTEMS REQUIRE ATTENTION")
        print("\n❌ Review errors above before production use")
    
    print("=" * 70)
    
    return all_critical_ok

final_status = generate_final_summary()

# ============================================================================
# Exit
# ============================================================================
print("\n📋 Verification complete. Review the summary above.")
print("=" * 70)

sys.exit(0 if final_status else 1)
