"""
Google Cloud Vision API OCR Extractor for receipt processing.
Provides high-accuracy OCR with excellent Japanese text recognition.
"""

import os
import io
import re
from typing import Dict, Any, Optional
from google.cloud import vision
from google.oauth2 import service_account
from PIL import Image
import requests


class GoogleVisionExtractor:
    """OCR extractor using Google Cloud Vision API for high-accuracy receipt processing."""

    def __init__(self, credentials_path: Optional[str] = None):
        """
        Initialize Google Vision API client.

        Args:
            credentials_path: Path to Google Cloud service account JSON file.
                            If None, uses GOOGLE_APPLICATION_CREDENTIALS env var.
        """
        try:
            if credentials_path:
                credentials = service_account.Credentials.from_service_account_file(credentials_path)
                self.client = vision.ImageAnnotatorClient(credentials=credentials)
            else:
                # Use environment variable or default credentials
                self.client = vision.ImageAnnotatorClient()

            print("SUCCESS: Google Vision API initialized successfully")
        except Exception as e:
            print(f"ERROR: Failed to initialize Google Vision API: {e}")
            print("INFO: Make sure GOOGLE_APPLICATION_CREDENTIALS is set or credentials_path is provided")
            raise

    def extract_text(self, image_data: bytes, filename: str = "receipt.jpg") -> Dict[str, Any]:
        """
        Extract text from receipt image using Google Vision API.

        Args:
            image_data: Raw image bytes
            filename: Original filename (for logging)

        Returns:
            Dict containing OCR results and metadata
        """
        try:
            print(f"🔍 Processing {filename} with Google Vision API...")

            # Create Vision API image object
            image = vision.Image(content=image_data)

            # Configure text detection with Japanese language hint
            # Note: language_hints are specified in the image context, not TextDetectionParams
            image_context = vision.ImageContext(language_hints=["ja"])

            # Create annotate request
            features = [
                vision.Feature(type_=vision.Feature.Type.TEXT_DETECTION)
            ]

            # Make API request
            response = self.client.annotate_image({
                'image': image,
                'features': features,
                'image_context': image_context,
            })

            # Check for errors
            if response.error.message:
                raise Exception(f"Vision API error: {response.error.message}")

            # Extract text and confidence
            full_text = ""
            confidence = 0.0

            if response.text_annotations:
                # Full text is in the first annotation
                full_text = response.text_annotations[0].description

                # Confidence might not be available for the full text annotation
                # Use the average confidence from individual text blocks if available
                confidence = 0.0
                if hasattr(response.text_annotations[0], 'confidence') and response.text_annotations[0].confidence is not None:
                    confidence = response.text_annotations[0].confidence
                else:
                    # Calculate average confidence from text blocks
                    confidences = []
                    for annotation in response.text_annotations[1:]:  # Skip first (full text)
                        if hasattr(annotation, 'confidence') and annotation.confidence is not None:
                            confidences.append(annotation.confidence)
                    if confidences:
                        confidence = sum(confidences) / len(confidences)

                print(f"📊 Google Vision confidence: {confidence:.2f}")
            else:
                print("⚠️ No text detected in image")

            # Return in OCR.space-compatible format for easy integration
            result = {
                'IsErroredOnProcessing': False,
                'ParsedResults': [{
                    'ParsedText': full_text,
                    'TextOverlay': {
                        'Lines': [],  # Could be populated with detailed line info
                        'HasOverlay': True,
                        'Message': f'Google Vision API - Confidence: {confidence:.2%}'
                    }
                }],
                'ProcessingTimeInMilliseconds': '0',  # Not provided by Vision API
                'SearchablePDFURL': '',  # Not applicable
                'metadata': {
                    'engine': 'Google Vision API',
                    'confidence': confidence,
                    'language': 'ja',
                    'filename': filename
                }
            }

            return result

        except Exception as e:
            print(f"ERROR: Google Vision API extraction failed: {e}")
            return {
                'IsErroredOnProcessing': True,
                'ParsedResults': [],
                'ErrorMessage': str(e),
                'metadata': {
                    'engine': 'Google Vision API',
                    'error': str(e)
                }
            }

    def preprocess_image(self, image_data: bytes, filename: str) -> bytes:
        """
        Preprocess image for better OCR results.
        Google Vision handles most preprocessing internally, but we can optimize.

        Args:
            image_data: Raw image bytes
            filename: Original filename

        Returns:
            Processed image bytes
        """
        try:
            # Open image
            image = Image.open(io.BytesIO(image_data))

            # Convert to RGB if necessary
            if image.mode not in ('RGB', 'L'):
                image = image.convert('RGB')

            # Google Vision works best with images under 20MB and reasonable resolution
            # Resize if extremely large (Vision API recommends under 75MP)
            max_pixels = 75 * 1024 * 1024  # 75 megapixels
            current_pixels = image.size[0] * image.size[1]

            if current_pixels > max_pixels:
                # Calculate scale factor
                scale_factor = (max_pixels / current_pixels) ** 0.5
                new_size = (int(image.size[0] * scale_factor), int(image.size[1] * scale_factor))
                image = image.resize(new_size, Image.Resampling.LANCZOS)
                print(f"🖼️ Resized image for Google Vision: {image.size}")

            # Convert back to bytes
            output_buffer = io.BytesIO()
            image.save(output_buffer, format='JPEG', quality=95, optimize=True)
            processed_data = output_buffer.getvalue()

            print(f"🖼️ Google Vision preprocessing: {len(image_data)/1024:.1f}KB -> {len(processed_data)/1024:.1f}KB")

            return processed_data

        except Exception as e:
            print(f"⚠️ Image preprocessing failed: {e}, using original")
            return image_data


def test_google_vision_connection(credentials_path: Optional[str] = None) -> bool:
    """
    Test Google Vision API connection and credentials.

    Returns:
        True if connection successful, False otherwise
    """
    try:
        extractor = GoogleVisionExtractor(credentials_path)

        # Test with a simple image (1x1 pixel)
        test_image = Image.new('RGB', (1, 1), color='white')
        test_buffer = io.BytesIO()
        test_image.save(test_buffer, format='JPEG')
        test_data = test_buffer.getvalue()

        result = extractor.extract_text(test_data, "test.jpg")

        if result.get('IsErroredOnProcessing'):
            print(f"ERROR: Google Vision test failed: {result.get('ErrorMessage')}")
            return False
        else:
            print("SUCCESS: Google Vision API connection test successful")
            return True

    except Exception as e:
        print(f"ERROR: Google Vision API test failed: {e}")
        return False


if __name__ == "__main__":
    # Test the extractor
    print("Testing Google Vision API extractor...")

    # Check for credentials
    credentials_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
    if not credentials_path:
        print("ERROR: GOOGLE_APPLICATION_CREDENTIALS environment variable not set")
        print("INFO: Set it to the path of your Google Cloud service account JSON file")
        exit(1)

    success = test_google_vision_connection(credentials_path)
    if success:
        print("SUCCESS: Google Vision API is ready to use!")
    else:
        print("ERROR: Google Vision API setup failed")
        exit(1)