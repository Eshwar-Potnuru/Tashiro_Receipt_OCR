#!/usr/bin/env python3
"""
Debug script to analyze field extraction issues with Japanese receipts
Shows raw OCR text and field parsing process
"""

import os
import sys
import io
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent / 'app'))

from app.extractors.field_extractors import FieldExtractor

def debug_field_extraction():
    """Debug field extraction for sample receipts."""
    print("🔍 Debugging Field Extraction for Japanese Receipts")
    print("=" * 60)

    # Load environment
    load_dotenv()

    # Initialize extractor
    extractor = FieldExtractor()

    # Test images
    test_images = [
        'Reciept_01.png',
        'Reciept_02.png'
    ]

    for image_name in test_images:
        image_path = Path(__file__).parent / image_name
        if not image_path.exists():
            print(f"⚠️ Image not found: {image_path}")
            continue

        print(f"\n📸 Analyzing: {image_name}")
        print("-" * 40)

        # Load image
        with open(image_path, 'rb') as f:
            image_data = f.read()

        print(f"📏 Image size: {len(image_data)/1024:.1f} KB")

        # Extract fields
        try:
            result = extractor.extract_fields(image_data, image_name)

            print("📊 Extracted Fields:")
            for key, value in result.items():
                if key != 'error' and key != 'debug_info':
                    print(f"  {key}: '{value}'")

            if 'error' in result:
                print(f"  ❌ Error: {result['error']}")

            # Show debug info if available
            if 'debug_info' in result:
                print("🐛 Debug Info:")
                for key, value in result['debug_info'].items():
                    print(f"  {key}: {value}")

        except Exception as e:
            print(f"❌ Extraction failed: {e}")

def debug_raw_ocr():
    """Debug raw OCR output without field parsing."""
    print("\n🔍 Debugging Raw OCR Output")
    print("=" * 60)

    # Load environment
    load_dotenv()

    # Initialize extractor
    extractor = FieldExtractor()

    # Test images
    test_images = [
        ('Reciept_01.png', 'Google Vision preferred'),
        ('Reciept_02.png', 'OpenAI Vision preferred')
    ]

    for image_name, engine_pref in test_images:
        image_path = Path(__file__).parent / image_name
        if not image_path.exists():
            print(f"⚠️ Image not found: {image_path}")
            continue

        print(f"\n📸 Raw OCR for: {image_name} ({engine_pref})")
        print("-" * 50)

        # Load image
        with open(image_path, 'rb') as f:
            image_data = f.read()

        # Get raw text using multi-engine OCR
        try:
            from app.ocr.multi_engine_ocr import MultiEngineOCR

            ocr_system = MultiEngineOCR(preferred_engine='auto')
            image = Image.open(io.BytesIO(image_data))
            raw_text, boxes = ocr_system.extract(image)

            print("📝 Raw OCR Text:")
            print("-" * 20)
            print(repr(raw_text))  # Show raw text with escapes
            print("-" * 20)
            print("Readable text:")
            print(raw_text)
            print("-" * 20)

            # Show text split by lines
            lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
            print("Line-by-line analysis:")
            for i, line in enumerate(lines[:20]):  # First 20 lines
                print("2d")

            if len(lines) > 20:
                print(f"  ... and {len(lines) - 20} more lines")

        except Exception as e:
            print(f"❌ Raw OCR failed: {e}")

if __name__ == "__main__":
    debug_field_extraction()
    debug_raw_ocr()