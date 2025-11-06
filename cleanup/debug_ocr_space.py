#!/usr/bin/env python3
"""
Debug script to inspect OCR.space API responses directly.
"""

import os
import requests
import json
from pathlib import Path

def debug_ocr_space_response():
    """Debug OCR.space API response structure."""

    # Use the same API key as the engine
    api_key = os.getenv('OCR_SPACE_API_KEY', 'K88575219088957')
    api_url = 'https://api.ocr.space/parse/image'

    # Find a test image
    current_dir = Path('.')
    image_files = list(current_dir.glob('*.png')) + list(current_dir.glob('*.jpg')) + list(current_dir.glob('*.jpeg'))
    if not image_files:
        print("❌ No test images found in current directory")
        return

    image_path = image_files[0]
    print(f"🖼️ Using test image: {image_path}")

    # Read image data
    with open(image_path, 'rb') as f:
        image_data = f.read()

    print(f"📏 Image size: {len(image_data)} bytes")

    # Prepare the exact same request as the engine
    # Determine MIME type based on file extension
    filename = image_path.name
    if filename.lower().endswith('.png'):
        mime_type = 'image/png'
    elif filename.lower().endswith('.jpg') or filename.lower().endswith('.jpeg'):
        mime_type = 'image/jpeg'
    elif filename.lower().endswith('.gif'):
        mime_type = 'image/gif'
    elif filename.lower().endswith('.bmp'):
        mime_type = 'image/bmp'
    elif filename.lower().endswith('.tiff') or filename.lower().endswith('.tif'):
        mime_type = 'image/tiff'
    elif filename.lower().endswith('.webp'):
        mime_type = 'image/webp'
    else:
        mime_type = 'application/octet-stream'
    
    files = {'file': (filename, image_data, mime_type)}
    data = {
        'apikey': api_key,
        'language': 'jpn',
        'isOverlayRequired': True,
        'detectOrientation': True,
        'scale': True,
        'OCREngine': 2,
    }

    print("📡 Making OCR.space API request...")
    print(f"📡 Request data: {data}")
    print(f"📡 File info: name={filename}, size={len(image_data)}, mime_type={mime_type}")

    try:
        response = requests.post(api_url, files=files, data=data, timeout=30)
        print(f"📡 Response status: {response.status_code}")
        print(f"📡 Response content-type: {response.headers.get('content-type')}")
        print(f"📡 Response length: {len(response.text)} characters")

        # Show response preview
        response_preview = response.text[:500]
        print(f"📡 Response preview: {response_preview}")
        if len(response.text) > 500:
            print(f"... ({len(response.text) - 500} more characters)")

        # Try to parse as JSON
        try:
            result = response.json()
            print("✅ Response is valid JSON")
            print(f"� JSON type: {type(result)}")
            print(f"� JSON keys: {list(result.keys()) if isinstance(result, dict) else 'Not a dict'}")

            # Check for error indicators
            if isinstance(result, dict):
                if result.get('IsErroredOnProcessing'):
                    print(f"❌ API Error: {result.get('ErrorMessage', 'Unknown error')}")
                elif result.get('ErrorMessage'):
                    print(f"⚠️ Error Message: {result.get('ErrorMessage')}")

        except json.JSONDecodeError as e:
            print(f"❌ Response is not valid JSON: {e}")

    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")

if __name__ == "__main__":
    debug_ocr_space_response()