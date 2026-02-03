#!/usr/bin/env python3
"""Test if OCR engines are properly configured and available."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    print("🔍 Checking OCR Engine Configuration...")
    print()
    
    # Check environment variables
    print("📋 Environment Variables:")
    print(f"  GOOGLE_APPLICATION_CREDENTIALS: {os.getenv('GOOGLE_APPLICATION_CREDENTIALS', '(not set)')}")
    print(f"  GOOGLE_CLOUD_PROJECT: {os.getenv('GOOGLE_CLOUD_PROJECT', '(not set)')}")
    print(f"  GOOGLE_CLOUD_LOCATION: {os.getenv('GOOGLE_CLOUD_LOCATION', '(not set)')}")
    print(f"  GOOGLE_CLOUD_PROCESSOR_ID: {os.getenv('GOOGLE_CLOUD_PROCESSOR_ID', '(not set)')}")
    print()
    
    # Try to import and initialize OCR engines
    try:
        from app.ocr.multi_engine_ocr import MultiEngineOCR
        
        print("✅ MultiEngineOCR imported successfully")
        
        # Create instance
        ocr = MultiEngineOCR()
        print("✅ MultiEngineOCR instance created")
        print()
        
        # Check which engines are available
        print("🔧 OCR Engines Status:")
        engines_available = getattr(ocr, 'engines_available', {})
        
        if not engines_available:
            print("  ⚠️  No engines_available attribute found")
        else:
            for engine_name, is_available in engines_available.items():
                status = "✅ Available" if is_available else "❌ Not Available"
                print(f"  {engine_name:20s}: {status}")
        
        print()
        
        # Try to list available engines
        if hasattr(ocr, 'list_engines'):
            print("📊 Available Engines (from list_engines):")
            try:
                engines = ocr.list_engines()
                for engine in engines:
                    print(f"  - {engine}")
            except Exception as e:
                print(f"  Error listing engines: {e}")
        
        print()
        print("=" * 60)
        print("✅ OCR Engine check complete")
        print("=" * 60)
        
    except ImportError as e:
        print(f"❌ Failed to import MultiEngineOCR: {e}")
        print()
        print("This means the OCR module is not properly set up.")
    except Exception as e:
        print(f"❌ Error initializing OCR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
