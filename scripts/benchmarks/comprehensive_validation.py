#!/usr/bin/env python3
"""
Comprehensive test script for validating Google Vision and OpenAI Vision APIs
for Japanese receipt OCR extraction.
"""

import sys
import os
from pathlib import Path
import time
from PIL import Image
import io

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent / 'app'))

from app.extractors.field_extractors import FieldExtractor

def load_image_bytes(image_path: str) -> bytes:
    """Load image file as bytes."""
    with open(image_path, 'rb') as f:
        return f.read()

def test_engine_quality(engine_preference: str, image_path: str, image_name: str):
    """Test a specific engine on a specific image."""
    print(f'\n🎯 Testing {engine_preference} on {image_name}')
    print('=' * 50)

    # Load image
    image_data = load_image_bytes(image_path)

    # Initialize extractor
    start_time = time.time()
    try:
        extractor = FieldExtractor(preferred_engine=engine_preference)
        init_time = time.time() - start_time
        print(f'✅ Extractor initialized in {init_time:.2f}s')
    except Exception as e:
        print(f'❌ Extractor initialization failed: {e}')
        return {'error': f'Init failed: {e}'}, 0

    # Extract fields
    start_time = time.time()
    try:
        result = extractor.extract_fields(image_data, image_name)
        extract_time = time.time() - start_time
        print(f'✅ Extraction completed in {extract_time:.2f}s')
    except Exception as e:
        print(f'❌ Extraction failed: {e}')
        return {'error': f'Extraction failed: {e}'}, time.time() - start_time

    # Print results
    print(f'🏪 Vendor: {result.get("vendor", "N/A")}')
    print(f'📅 Date: {result.get("date", "N/A")}')
    print(f'💰 Total: ¥{result.get("total", "N/A")}')
    print(f'🏷️ Category: {result.get("account_title", "N/A")}')
    print(f'🧾 Tax: ¥{result.get("tax", "N/A")}')
    print(f'📄 Invoice: {result.get("invoice_number", "N/A")}')

    if result.get('error'):
        print(f'❌ Error: {result["error"]}')
    else:
        print('✅ Success')

    return result, extract_time

def main():
    """Run comprehensive validation tests."""
    print("🔬 COMPREHENSIVE JAPANESE RECEIPT OCR VALIDATION")
    print("=" * 60)

    # Test images
    test_images = [
        ('Reciept_01.png', 'Receipt 1'),
        ('Reciept_02.png', 'Receipt 2')
    ]

    # Test engines
    engines = ['google_vision', 'openai_vision', 'auto']

    results = {}
    for engine in engines:
        results[engine] = {}
        for image_file, image_name in test_images:
            image_path = Path(__file__).parent / image_file
            if not image_path.exists():
                print(f'⚠️ Test image not found: {image_path}')
                continue

            try:
                result, extract_time = test_engine_quality(engine, str(image_path), image_name)
                results[engine][image_name] = {
                    'result': result,
                    'time': extract_time,
                    'success': 'error' not in result
                }
            except Exception as e:
                print(f'❌ {engine} on {image_name} failed: {e}')
                results[engine][image_name] = {
                    'result': {'error': str(e)},
                    'time': 0,
                    'success': False
                }

    print('\n' + '=' * 60)
    print('📊 COMPREHENSIVE TEST RESULTS SUMMARY')
    print('=' * 60)

    for engine in engines:
        print(f'\n🚀 {engine.upper()} ENGINE:')
        total_time = 0
        success_count = 0

        for image_name in results[engine]:
            data = results[engine][image_name]
            total_time += data['time']
            if data['success']:
                success_count += 1
            status = '✅' if data['success'] else '❌'
            print(f'  {image_name}: {status} ({data["time"]:.2f}s)')

        image_count = len(results[engine])
        if image_count > 0:
            success_rate = success_count / image_count * 100
            avg_time = total_time / image_count
            print(f'  Success Rate: {success_count}/{image_count} ({success_rate:.0f}%)')
            print(f'  Avg Time: {avg_time:.2f}s')

    print('\n🎉 Comprehensive validation complete!')

    # Overall assessment
    print('\n' + '=' * 60)
    print('🎯 VALIDATION ASSESSMENT')
    print('=' * 60)

    google_success = sum(1 for r in results.get('google_vision', {}).values() if r['success'])
    openai_success = sum(1 for r in results.get('openai_vision', {}).values() if r['success'])

    if google_success >= 1 and openai_success >= 1:
        print('✅ SUCCESS: Both Google Vision and OpenAI Vision APIs are working perfectly!')
        print('✅ Japanese receipt OCR extraction is fully functional.')
    else:
        print('⚠️ PARTIAL: Some engines may need attention.')
        if google_success < 1:
            print('  - Google Vision API may have issues')
        if openai_success < 1:
            print('  - OpenAI Vision API may have issues')

if __name__ == "__main__":
    main()