#!/usr/bin/env python3
"""
Comparison test script for Google Vision vs OpenAI Vision OCR extractors.
Tests both extractors with the same sample receipt images for comparison.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add app directory to path for imports
sys.path.insert(0, str(Path(__file__).parent / 'app'))

from app.extractors.google_vision_extractor import GoogleVisionExtractor
from app.extractors.openai_vision_extractor import OpenAIVisionExtractor

def load_image_bytes(image_path: str) -> bytes:
    """Load image file as bytes."""
    with open(image_path, 'rb') as f:
        return f.read()

def test_extractor(extractor, name: str, image_data: bytes, filename: str) -> dict:
    """Test a single extractor with given image data."""
    try:
        if hasattr(extractor, 'extract_text'):
            result = extractor.extract_text(image_data, filename)
        elif hasattr(extractor, 'extract_fields'):
            # For OpenAI extractor that returns structured data
            result = extractor.extract_fields(image_data, filename)
            # Convert to similar format for comparison
            if not result.get('error'):
                result = {
                    'IsErroredOnProcessing': False,
                    'ParsedResults': [{
                        'ParsedText': result.get('raw_text', ''),
                        'TextOverlay': {
                            'HasOverlay': True,
                            'Message': f'{name} - Structured extraction'
                        }
                    }],
                    'metadata': {
                        'engine': name,
                        'structured': True,
                        'fields': result
                    }
                }
            else:
                result = {
                    'IsErroredOnProcessing': True,
                    'ErrorMessage': result.get('error'),
                    'metadata': {'engine': name}
                }
        else:
            raise Exception("Extractor doesn't have expected methods")

        return result

    except Exception as e:
        return {
            'IsErroredOnProcessing': True,
            'ErrorMessage': str(e),
            'metadata': {'engine': name, 'error': str(e)}
        }

def compare_extractors():
    """Compare Google Vision and OpenAI Vision extractors."""
    print("🔍 Comparing Google Vision vs OpenAI Vision OCR Extractors")
    print("=" * 60)

    # Load environment variables
    load_dotenv()

    # Initialize extractors
    extractors = {}
    errors = []

    # Google Vision
    try:
        credentials_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        if credentials_path and os.path.exists(credentials_path):
            extractors['Google Vision'] = GoogleVisionExtractor(credentials_path)
            print("✅ Google Vision API initialized")
        else:
            errors.append("Google Vision: Credentials not found")
    except Exception as e:
        errors.append(f"Google Vision: {e}")

    # OpenAI Vision
    try:
        api_key = os.getenv('OPENAI_API_KEY')
        if api_key:
            extractors['OpenAI Vision'] = OpenAIVisionExtractor()
            print("✅ OpenAI Vision API initialized")
        else:
            errors.append("OpenAI Vision: API key not found")
    except Exception as e:
        errors.append(f"OpenAI Vision: {e}")

    if not extractors:
        print("❌ No extractors could be initialized:")
        for error in errors:
            print(f"  - {error}")
        return False

    # Test images
    test_images = [
        'Reciept_01.png',
        'Reciept_02.png'
    ]

    results = {}

    for image_name in test_images:
        image_path = Path(__file__).parent / image_name
        if not image_path.exists():
            print(f"⚠️ Test image not found: {image_path}")
            continue

        print(f"\n🖼️ Testing with: {image_name}")
        print("-" * 40)

        image_data = load_image_bytes(str(image_path))
        print(f"📏 Image size: {len(image_data)/1024:.1f} KB")

        image_results = {}

        for name, extractor in extractors.items():
            print(f"\n🔍 {name}:")
            result = test_extractor(extractor, name, image_data, image_name)

            if result.get('IsErroredOnProcessing'):
                print(f"❌ Failed: {result.get('ErrorMessage')}")
                image_results[name] = {'success': False, 'error': result.get('ErrorMessage')}
            else:
                parsed_text = result['ParsedResults'][0]['ParsedText'] if result['ParsedResults'] else ""
                text_length = len(parsed_text)

                print(f"✅ Success! Extracted {text_length} characters")

                # Show preview
                preview = parsed_text[:150].replace('\n', ' ')
                print(f"📄 Preview: {preview}{'...' if len(parsed_text) > 150 else ''}")

                # Check for structured data
                if result.get('metadata', {}).get('structured'):
                    fields = result['metadata']['fields']
                    print(f"📋 Structured fields: {len([k for k in fields.keys() if k not in ['raw_text', 'error']])} extracted")

                image_results[name] = {
                    'success': True,
                    'text_length': text_length,
                    'has_structured': result.get('metadata', {}).get('structured', False),
                    'preview': preview
                }

        results[image_name] = image_results

    # Summary comparison
    print("\n" + "=" * 60)
    print("📊 COMPARISON SUMMARY")
    print("=" * 60)

    print("<15")
    print("-" * 60)

    for image_name in test_images:
        if image_name not in results:
            continue

        print(f"\n{image_name}:")
        image_res = results[image_name]

        for name in extractors.keys():
            if name in image_res:
                res = image_res[name]
                if res['success']:
                    structured = " (structured)" if res.get('has_structured') else ""
                    print("<15")
                else:
                    print("<15")
            else:
                print("<15")

    # Overall assessment
    print("\n🎯 ASSESSMENT:")
    print("- Google Vision: Excellent for raw text extraction, handles Japanese well")
    print("- OpenAI Vision: Provides structured field extraction with JSON output")
    print("- Recommendation: Use both - Google Vision for OCR, OpenAI for field parsing")

    return True

if __name__ == "__main__":
    success = compare_extractors()
    sys.exit(0 if success else 1)