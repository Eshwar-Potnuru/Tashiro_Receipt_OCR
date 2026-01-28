#!/usr/bin/env python3
"""
Setup script for Google Cloud Vision API integration.
This script helps configure Google Cloud credentials and test the Vision API.
"""

import os
import json
import subprocess
import sys
from pathlib import Path


def check_python_version():
    """Check if Python version is compatible."""
    if sys.version_info < (3, 8):
        print("❌ Python 3.8+ is required for Google Cloud Vision API")
        return False
    print(f"✅ Python version: {sys.version.split()[0]}")
    return True


def install_dependencies():
    """Install required dependencies."""
    print("📦 Installing Google Cloud Vision dependencies...")

    try:
        # Install google-cloud-vision
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            "--upgrade", "google-cloud-vision"
        ])
        print("✅ Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        return False


def setup_credentials():
    """Guide user through Google Cloud credentials setup."""
    print("\n🔐 Google Cloud Vision API Setup")
    print("=" * 50)

    print("\n📋 Required steps:")
    print("1. Go to Google Cloud Console: https://console.cloud.google.com/")
    print("2. Create a new project or select existing one")
    print("3. Enable the Vision API:")
    print("   - Go to 'APIs & Services' > 'Library'")
    print("   - Search for 'Cloud Vision API'")
    print("   - Click 'Enable'")
    print("4. Create a Service Account:")
    print("   - Go to 'IAM & Admin' > 'Service Accounts'")
    print("   - Click 'Create Service Account'")
    print("   - Name: 'receipt-ocr-service'")
    print("   - Role: 'Viewer' (basic) or 'Cloud Vision Client' if available")
    print("5. Create JSON Key:")
    print("   - Click on the service account")
    print("   - Go to 'Keys' tab")
    print("   - Click 'Add Key' > 'Create new key' > 'JSON'")
    print("   - Download the JSON file")

    credentials_path = input("\n📁 Enter the path to your downloaded JSON credentials file: ").strip()

    if not os.path.exists(credentials_path):
        print(f"❌ File not found: {credentials_path}")
        return False

    # Validate JSON structure
    try:
        with open(credentials_path, 'r') as f:
            creds = json.load(f)

        required_fields = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email']
        missing_fields = [field for field in required_fields if field not in creds]

        if missing_fields:
            print(f"❌ Invalid credentials file. Missing fields: {missing_fields}")
            return False

        if creds.get('type') != 'service_account':
            print("❌ This doesn't appear to be a service account key")
            return False

        print(f"✅ Valid service account credentials for project: {creds.get('project_id')}")

    except json.JSONDecodeError:
        print("❌ Invalid JSON file")
        return False

    # Copy credentials to project directory
    project_dir = Path(__file__).parent
    creds_dest = project_dir / "google_credentials.json"

    try:
        import shutil
        shutil.copy2(credentials_path, creds_dest)
        print(f"✅ Credentials copied to: {creds_dest}")

        # Set environment variable
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(creds_dest)

        # Update .env file
        env_file = project_dir / ".env"
        env_content = ""
        if env_file.exists():
            with open(env_file, 'r') as f:
                env_content = f.read()

        # Remove any existing GOOGLE_APPLICATION_CREDENTIALS
        lines = env_content.split('\n')
        lines = [line for line in lines if not line.startswith('GOOGLE_APPLICATION_CREDENTIALS=')]

        # Add new line
        lines.append(f'GOOGLE_APPLICATION_CREDENTIALS={creds_dest}')

        with open(env_file, 'w') as f:
            f.write('\n'.join(lines))

        print("✅ Environment variable set in .env file")

        return True

    except Exception as e:
        print(f"❌ Failed to setup credentials: {e}")
        return False


def test_api_connection():
    """Test the Google Vision API connection."""
    print("\n🧪 Testing Google Vision API connection...")

    try:
        from app.extractors.google_vision_extractor import test_google_vision_connection

        success = test_google_vision_connection()
        if success:
            print("\n🎉 Google Vision API setup completed successfully!")
            print("\n💡 Next steps:")
            print("1. Update your main.py to use GoogleVisionExtractor instead of OCRSpaceExtractor")
            print("2. Test with actual receipt images")
            print("3. Monitor your Google Cloud billing for API usage")
            return True
        else:
            print("\n❌ API test failed. Please check your credentials and try again.")
            return False

    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("💡 Make sure you're running this from the receipt-ocr directory")
        return False


def main():
    """Main setup function."""
    print("🚀 Google Cloud Vision API Setup for Receipt OCR")
    print("=" * 55)

    # Check Python version
    if not check_python_version():
        return

    # Install dependencies
    if not install_dependencies():
        return

    # Setup credentials
    if not setup_credentials():
        return

    # Test connection
    if test_api_connection():
        print("\n✅ Setup complete! You can now use Google Vision API for OCR.")
    else:
        print("\n❌ Setup failed. Please check the errors above and try again.")


if __name__ == "__main__":
    main()