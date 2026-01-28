"""
Detailed IAM and API Diagnostic
================================
Checks exact IAM roles and API enablement status.
"""

import os
import json
from dotenv import load_dotenv
from google.auth import default
from google.auth.transport.requests import Request

print("=" * 70)
print("DETAILED IAM AND API DIAGNOSTIC")
print("=" * 70)

# Load environment
load_dotenv(override=True)

# Check credentials
creds_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
if not creds_path or not os.path.exists(creds_path):
    print("✗ Credentials file not found")
    exit(1)

print(f"\n✔ Credentials file: {creds_path}")

# Load credentials JSON
with open(creds_path, 'r') as f:
    creds_data = json.load(f)

print(f"✔ Project ID: {creds_data.get('project_id')}")
print(f"✔ Client Email: {creds_data.get('client_email')}")
print(f"✔ Type: {creds_data.get('type')}")

# Try to authenticate
print("\n" + "-" * 70)
print("AUTHENTICATION TEST")
print("-" * 70)

try:
    credentials, project = default()
    print(f"✔ Credentials loaded")
    print(f"  Project: {project}")
    print(f"  Service Account: {credentials.service_account_email if hasattr(credentials, 'service_account_email') else 'N/A'}")
    
    # Try to refresh token
    print("\nRefreshing token...")
    request = Request()
    credentials.refresh(request)
    print("✔ Token refreshed successfully")
    
    # Check if token is valid
    if credentials.valid:
        print("✔ Credentials are valid")
    else:
        print("✗ Credentials are NOT valid")
        
except Exception as e:
    print(f"✗ Authentication failed: {e}")

# Test API access
print("\n" + "-" * 70)
print("API ACCESS TEST")
print("-" * 70)

# Test Document AI
print("\n1. Document AI API:")
try:
    from google.cloud import documentai_v1 as documentai
    
    credentials, project = default()
    client = documentai.DocumentProcessorServiceClient(credentials=credentials)
    
    # Try to list processors (this requires documentai.processors.list permission)
    processor_id = os.environ.get('DOCUMENT_AI_PROCESSOR_ID')
    location = os.environ.get('DOCUMENT_AI_LOCATION', 'us')
    
    if processor_id and project:
        parent = f"projects/{project}/locations/{location}"
        try:
            # This will fail if API is not enabled or no permission
            processors = client.list_processors(parent=parent)
            print(f"✔ API is accessible and enabled")
            print(f"  Can list processors in {location}")
        except Exception as list_error:
            error_str = str(list_error)
            if "403" in error_str:
                print(f"✗ API enabled but PERMISSION DENIED")
                print(f"  Service account needs 'Document AI API User' role")
            elif "401" in error_str:
                print(f"✗ AUTHENTICATION ERROR")
                print(f"  Credentials are not being accepted")
            elif "404" in error_str or "not found" in error_str.lower():
                print(f"✗ API NOT ENABLED for project {project}")
                print(f"  Enable at: https://console.cloud.google.com/apis/library/documentai.googleapis.com")
            else:
                print(f"✗ Error: {error_str}")
    else:
        print("⚠️  Missing processor ID or project configuration")
        
except Exception as e:
    print(f"✗ Failed to access Document AI: {e}")

# Test Vision API
print("\n2. Vision API:")
try:
    from google.cloud import vision
    
    credentials, project = default()
    client = vision.ImageAnnotatorClient(credentials=credentials)
    
    # Try a simple operation
    print(f"✔ Client created")
    print(f"  Testing with empty image (should fail gracefully)...")
    
    try:
        # This will fail with invalid image, but tells us if API is accessible
        image = vision.Image()
        response = client.text_detection(image=image)
    except Exception as test_error:
        error_str = str(test_error)
        if "403" in error_str:
            print(f"✗ API enabled but PERMISSION DENIED")
            print(f"  Service account needs 'Cloud Vision API User' role")
        elif "401" in error_str:
            print(f"✗ AUTHENTICATION ERROR")
            print(f"  Credentials are not being accepted")
        elif "404" in error_str or "not enabled" in error_str.lower():
            print(f"✗ API NOT ENABLED for project {project}")
            print(f"  Enable at: https://console.cloud.google.com/apis/library/vision.googleapis.com")
        elif "invalid" in error_str.lower() and "image" in error_str.lower():
            print(f"✔ API is accessible (failed on empty image as expected)")
        else:
            print(f"✗ Error: {error_str}")
        
except Exception as e:
    print(f"✗ Failed to access Vision API: {e}")

# Print recommendations
print("\n" + "=" * 70)
print("RECOMMENDATIONS")
print("=" * 70)

print("\nIf you see 401 AUTHENTICATION ERROR:")
print("  1. Verify service account key is not expired")
print("  2. Check project ID matches in .env and credentials JSON")
print("  3. Try regenerating the service account key")

print("\nIf you see 403 PERMISSION DENIED:")
print("  1. Grant 'Document AI API User' role:")
print("     gcloud projects add-iam-policy-binding aim-tashiro-poc \\")
print("       --member='serviceAccount:{email}' \\")
print("       --role='roles/documentai.apiUser'")
print()
print("  2. Grant 'Cloud Vision API User' role:")
print("     gcloud projects add-iam-policy-binding aim-tashiro-poc \\")
print("       --member='serviceAccount:{email}' \\")
print("       --role='roles/cloudvision.user'")

print("\nIf APIs are NOT ENABLED:")
print("  1. Enable Document AI: https://console.cloud.google.com/apis/library/documentai.googleapis.com")
print("  2. Enable Vision API: https://console.cloud.google.com/apis/library/vision.googleapis.com")

print("\n" + "=" * 70)
