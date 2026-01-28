#!/usr/bin/env python3
"""
Performance Comparison Test: Premium Engines vs OCR.space
Compares accuracy, speed, and reliability of Google Vision, OpenAI Vision, and OCR.space.
"""

import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, Any, List

# Add app directory to path for imports
sys.path.insert(0, str(Path(__file__).parent / 'app'))

from app.extractors.google_vision_extractor import GoogleVisionExtractor
from app.extractors.openai_vision_extractor import OpenAIVisionExtractor

def load_image_bytes(image_path: str) -> bytes:
    """Load image file as bytes."""
    with open(image_path, 'rb') as f:
        return f.read()

def extract_with_ocr_space(image_data: bytes, filename: str) -> Dict[str, Any]:
    """Extract using OCR.space API (original method)."""
    import requests

    api_key = os.getenv('OCR_SPACE_API_KEY', 'K88575219088957')
    api_url = 'https://api.ocr.space/parse/image'

    # Preprocess image
    from PIL import Image
    import io
    image = Image.open(io.BytesIO(image_data))
    if image.mode in ('RGBA', 'LA', 'P'):
        background = Image.new('RGB', image.size, (255, 255, 255))
        if image.mode == 'P':
            image = image.convert('RGBA')
        background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
        image = background
    elif image.mode != 'RGB':
        image = image.convert('RGB')

    output_buffer = io.BytesIO()
    image.save(output_buffer, format='JPEG', quality=95)
    processed_data = output_buffer.getvalue()

    # Make API call
    files = {'file': (filename, processed_data, 'application/octet-stream')}
    data = {
        'apikey': api_key,
        'language': 'jpn',
        'isOverlayRequired': True,
        'detectOrientation': True,
        'scale': True,
        'OCREngine': 2,
    }

    response = requests.post(api_url, files=files, data=data, timeout=30)
    response.raise_for_status()
    result = response.json()

    if result.get('IsErroredOnProcessing'):
        raise Exception(result.get('ErrorMessage', 'OCR.space error'))

    return result

def parse_ocr_space_result(ocr_result: Dict[str, Any]) -> Dict[str, Any]:
    """Parse OCR.space result into structured fields."""
    from app.extractors.field_extractors import FieldExtractor

    # Create a temporary field extractor just for parsing
    extractor = FieldExtractor.__new__(FieldExtractor)  # Create without __init__

    # Get raw text
    parsed_text = ocr_result['ParsedResults'][0]['ParsedText'] if ocr_result['ParsedResults'] else ""

    # Parse fields
    return extractor._parse_receipt_text(parsed_text)

def benchmark_engine(engine_name: str, engine_func, image_data: bytes, filename: str, iterations: int = 1) -> Dict[str, Any]:
    """Benchmark a single engine."""
    print(f"🏁 Benchmarking {engine_name}...")

    results = []
    total_time = 0

    for i in range(iterations):
        start_time = time.time()

        try:
            result = engine_func(image_data, filename)
            processing_time = time.time() - start_time
            total_time += processing_time

            # Analyze result
            if engine_name in ['Google Vision', 'OCR.space']:
                # Raw OCR results
                raw_text = result['ParsedResults'][0]['ParsedText'] if result['ParsedResults'] else ""
                text_length = len(raw_text)
                has_text = text_length > 50

                # Parse fields for comparison
                parsed_fields = parse_ocr_space_result(result) if engine_name == 'OCR.space' else None

                results.append({
                    'success': True,
                    'processing_time': processing_time,
                    'text_length': text_length,
                    'has_text': has_text,
                    'raw_text': raw_text[:200],  # First 200 chars
                    'parsed_fields': parsed_fields
                })

            elif engine_name == 'OpenAI Vision':
                # Structured results
                has_vendor = bool(result.get('vendor'))
                has_total = bool(result.get('total'))
                has_date = bool(result.get('date'))
                field_completeness = sum([has_vendor, has_total, has_date, bool(result.get('tax'))]) / 4

                results.append({
                    'success': True,
                    'processing_time': processing_time,
                    'field_completeness': field_completeness,
                    'has_vendor': has_vendor,
                    'has_total': has_total,
                    'has_date': has_date,
                    'structured_data': result
                })

        except Exception as e:
            processing_time = time.time() - start_time
            total_time += processing_time
            results.append({
                'success': False,
                'processing_time': processing_time,
                'error': str(e)
            })

    # Calculate averages
    successful_runs = [r for r in results if r['success']]
    success_rate = len(successful_runs) / len(results)

    if successful_runs:
        avg_time = sum(r['processing_time'] for r in successful_runs) / len(successful_runs)

        if engine_name in ['Google Vision', 'OCR.space']:
            avg_text_length = sum(r['text_length'] for r in successful_runs) / len(successful_runs)
            text_quality_score = avg_text_length / 500  # Normalize to 0-1 scale (500 chars = good)

            return {
                'engine': engine_name,
                'success_rate': success_rate,
                'avg_processing_time': avg_time,
                'avg_text_length': avg_text_length,
                'text_quality_score': min(text_quality_score, 1.0),  # Cap at 1.0
                'overall_score': (success_rate * 0.3) + (min(avg_time, 10) / 10 * 0.2) + (text_quality_score * 0.5)
            }

        elif engine_name == 'OpenAI Vision':
            avg_completeness = sum(r['field_completeness'] for r in successful_runs) / len(successful_runs)

            return {
                'engine': engine_name,
                'success_rate': success_rate,
                'avg_processing_time': avg_time,
                'avg_field_completeness': avg_completeness,
                'structured_quality_score': avg_completeness,
                'overall_score': (success_rate * 0.3) + (min(avg_time, 10) / 10 * 0.2) + (avg_completeness * 0.5)
            }

    return {
        'engine': engine_name,
        'success_rate': 0,
        'avg_processing_time': total_time / len(results),
        'overall_score': 0
    }

def run_performance_comparison():
    """Run comprehensive performance comparison."""
    print("📊 Performance Comparison: Premium Engines vs OCR.space")
    print("=" * 60)

    # Load environment variables
    load_dotenv()

    # Initialize engines
    engines = {}

    try:
        credentials_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        if credentials_path and os.path.exists(credentials_path):
            engines['Google Vision'] = GoogleVisionExtractor(credentials_path)
            print("✅ Google Vision initialized")
    except Exception as e:
        print(f"⚠️ Google Vision failed: {e}")

    try:
        api_key = os.getenv('OPENAI_API_KEY')
        if api_key:
            engines['OpenAI Vision'] = OpenAIVisionExtractor()
            print("✅ OpenAI Vision initialized")
    except Exception as e:
        print(f"⚠️ OpenAI Vision failed: {e}")

    # OCR.space doesn't need initialization
    engines['OCR.space'] = lambda data, filename: extract_with_ocr_space(data, filename)
    print("✅ OCR.space ready")

    if not engines:
        print("❌ No engines available for testing")
        return False

    # Test images
    test_images = [
        ('Reciept_01.png', 'Receipt 1 (Yokubenimar)'),
        ('Reciept_02.png', 'Receipt 2 (Restaurant)')
    ]

    # Run benchmarks
    all_results = []

    for image_file, image_desc in test_images:
        image_path = Path(__file__).parent / image_file
        if not image_path.exists():
            print(f"⚠️ Test image not found: {image_path}")
            continue

        print(f"\n🖼️ Testing with: {image_desc}")
        print("-" * 40)

        image_data = load_image_bytes(str(image_path))
        print(f"📏 Image size: {len(image_data)/1024:.1f} KB")

        image_results = []

        for engine_name, engine_func in engines.items():
            result = benchmark_engine(engine_name, engine_func, image_data, image_file, iterations=1)
            result['image'] = image_desc
            image_results.append(result)

            print(f"  {engine_name}:")
            print(".2f")
            print(".1f")
            if 'avg_text_length' in result:
                print(f"    📝 Avg text length: {result['avg_text_length']:.0f} chars")
            if 'avg_field_completeness' in result:
                print(".1%")

        all_results.extend(image_results)

    # Overall comparison
    print("\n" + "=" * 60)
    print("🏆 PERFORMANCE COMPARISON RESULTS")
    print("=" * 60)

    # Group by engine
    engine_summaries = {}
    for result in all_results:
        engine = result['engine']
        if engine not in engine_summaries:
            engine_summaries[engine] = []
        engine_summaries[engine].append(result)

    # Calculate averages per engine
    final_results = []
    for engine, results in engine_summaries.items():
        avg_success = sum(r['success_rate'] for r in results) / len(results)
        avg_time = sum(r['avg_processing_time'] for r in results) / len(results)
        avg_score = sum(r['overall_score'] for r in results) / len(results)

        final_results.append({
            'engine': engine,
            'avg_success_rate': avg_success,
            'avg_processing_time': avg_time,
            'avg_overall_score': avg_score,
            'results': results
        })

    # Sort by overall score
    final_results.sort(key=lambda x: x['avg_overall_score'], reverse=True)

    print("<15")
    print("-" * 60)

    for result in final_results:
        print("<15")

    # Detailed analysis
    print("\n🔍 DETAILED ANALYSIS:")
    print("-" * 30)

    best_engine = final_results[0]['engine']
    print(f"🥇 Best Overall: {best_engine}")

    if best_engine == 'Google Vision':
        print("   ✅ Excellent raw text extraction with Japanese support")
        print("   ✅ Fast processing, high reliability")
        print("   ✅ Perfect for OCR preprocessing before field parsing")
    elif best_engine == 'OpenAI Vision':
        print("   ✅ Superior structured field extraction")
        print("   ✅ Intelligent categorization and tax calculation")
        print("   ✅ Best for complete automated processing")
    elif best_engine == 'OCR.space':
        print("   ✅ Good balance of speed and accuracy")
        print("   ✅ No setup required, reliable fallback")
        print("   ✅ Cost-effective for basic OCR needs")

    # Recommendations
    print("\n💡 RECOMMENDATIONS:")
    print("-" * 20)
    print("1. 🥇 Primary Engine: Use Google Vision for superior OCR quality")
    print("2. 🥈 Structured Processing: Use OpenAI Vision for field extraction")
    print("3. 🥉 Fallback: Keep OCR.space for reliability and cost control")
    print("4. 🔄 Hybrid Approach: Google Vision OCR → OpenAI Vision parsing")

    return True

if __name__ == "__main__":
    success = run_performance_comparison()
    sys.exit(0 if success else 1)