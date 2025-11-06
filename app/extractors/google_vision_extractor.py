"""
Google Cloud Vision API OCR Extractor for receipt processing.
Provides high-accuracy OCR with excellent Japanese text recognition.
Optimized for Japanese receipts with DOCUMENT_TEXT_DETECTION and advanced preprocessing.
"""

import os
import io
import re
import cv2
import numpy as np
import unicodedata
from typing import Dict, Any, Optional, List, Tuple
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
        Extract text from receipt image using Google Vision API with DOCUMENT_TEXT_DETECTION.

        Args:
            image_data: Raw image bytes
            filename: Original filename (for logging)

        Returns:
            Dict containing OCR results and metadata with structured document layout
        """
        try:
            print(f"🔍 Processing {filename} with Google Vision DOCUMENT_TEXT_DETECTION...")

            # Preprocess image for optimal Japanese OCR
            processed_image_data = self._preprocess_image_opencv(image_data, filename)

            # Create Vision API image object
            image = vision.Image(content=processed_image_data)

            # Configure DOCUMENT_TEXT_DETECTION with Japanese language hints
            image_context = vision.ImageContext(language_hints=["ja", "en"])

            # Use DOCUMENT_TEXT_DETECTION for structured layout understanding
            features = [
                vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)
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

            # Extract structured document text
            full_text = ""
            confidence = 0.0
            text_blocks = []

            if response.full_text_annotation:
                full_text = response.full_text_annotation.text
                confidence = response.full_text_annotation.confidence or 0.0

                # Extract structured blocks with position information
                for page in response.full_text_annotation.pages:
                    for block in page.blocks:
                        block_text = ""
                        block_confidence = 0.0
                        vertices = []

                        # Get block bounding box
                        if block.bounding_box and block.bounding_box.vertices:
                            vertices = [(v.x, v.y) for v in block.bounding_box.vertices]

                        # Extract text from paragraphs in this block
                        for paragraph in block.paragraphs:
                            for word in paragraph.words:
                                word_text = "".join([symbol.text for symbol in word.symbols])
                                block_text += word_text
                                # Average confidence across symbols
                                if word.symbols:
                                    word_conf = sum(s.confidence for s in word.symbols if s.confidence) / len(word.symbols)
                                    block_confidence = max(block_confidence, word_conf)

                        if block_text.strip():
                            text_blocks.append({
                                'text': block_text.strip(),
                                'confidence': block_confidence,
                                'bounding_box': vertices,
                                'block_type': self._classify_block_type(vertices, page)
                            })

                print(f"📊 Google Vision DOCUMENT_TEXT_DETECTION: {len(text_blocks)} blocks, confidence: {confidence:.2f}")
            else:
                print("⚠️ No text detected in image")

            # Return enhanced result with structured data
            result = {
                'IsErroredOnProcessing': False,
                'ParsedResults': [{
                    'ParsedText': full_text,
                    'TextOverlay': {
                        'Lines': [],  # Could be populated with detailed line info
                        'HasOverlay': True,
                        'Message': f'Google Vision DOCUMENT_TEXT_DETECTION - Confidence: {confidence:.2%}'
                    }
                }],
                'ProcessingTimeInMilliseconds': '0',  # Not provided by Vision API
                'SearchablePDFURL': '',  # Not applicable
                'metadata': {
                    'engine': 'Google Vision API (DOCUMENT_TEXT_DETECTION)',
                    'confidence': confidence,
                    'language': 'ja',
                    'filename': filename,
                    'text_blocks': text_blocks,
                    'structured_layout': True
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
                    'engine': 'Google Vision API (DOCUMENT_TEXT_DETECTION)',
                    'error': str(e)
                }
            }

    def _preprocess_image_opencv(self, image_data: bytes, filename: str) -> bytes:
        """
        Advanced OpenCV preprocessing pipeline optimized for Japanese receipts.
        Steps: Convert to grayscale, denoise, adaptive threshold, sharpen, auto-crop borders.

        Args:
            image_data: Raw image bytes
            filename: Original filename

        Returns:
            Processed image bytes
        """
        try:
            # Convert bytes to numpy array
            nparr = np.frombuffer(image_data, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if image is None:
                print("⚠️ Failed to decode image, using original")
                return image_data

            original_shape = image.shape
            print(f"🖼️ OpenCV preprocessing: {original_shape}")

            # Step 1: Convert to grayscale
            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            else:
                gray = image

            # Step 2: Denoise (fastNlMeansDenoising)
            denoised = cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21)

            # Step 3: Adaptive threshold for contrast enhancement
            thresh = cv2.adaptiveThreshold(
                denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
            )

            # Step 4: Slight sharpening kernel to enhance text edges
            kernel = np.array([[-1,-1,-1],
                             [-1, 9,-1],
                             [-1,-1,-1]])
            sharpened = cv2.filter2D(thresh, -1, kernel)

            # Step 5: Auto-crop white borders
            cropped = self._auto_crop_borders(sharpened)

            # Step 6: Ensure minimum size for OCR
            min_height, min_width = 400, 400
            if cropped.shape[0] < min_height or cropped.shape[1] < min_width:
                scale_factor = max(min_height / cropped.shape[0], min_width / cropped.shape[1])
                new_width = int(cropped.shape[1] * scale_factor)
                new_height = int(cropped.shape[0] * scale_factor)
                cropped = cv2.resize(cropped, (new_width, new_height), interpolation=cv2.INTER_CUBIC)

            # Step 7: Final resize if too large (Google Vision limit: 75MP)
            max_pixels = 75 * 1024 * 1024
            current_pixels = cropped.shape[0] * cropped.shape[1]

            if current_pixels > max_pixels:
                scale_factor = (max_pixels / current_pixels) ** 0.5
                new_width = int(cropped.shape[1] * scale_factor)
                new_height = int(cropped.shape[0] * scale_factor)
                cropped = cv2.resize(cropped, (new_width, new_height), interpolation=cv2.INTER_AREA)

            # Convert back to JPEG bytes
            success, encoded_img = cv2.imencode('.jpg', cropped, [cv2.IMWRITE_JPEG_QUALITY, 95])
            if success:
                processed_data = encoded_img.tobytes()
                print(f"🖼️ OpenCV preprocessing complete: {original_shape} -> {cropped.shape}, {len(image_data)/1024:.1f}KB -> {len(processed_data)/1024:.1f}KB")
                return processed_data
            else:
                print("⚠️ OpenCV encoding failed, using original")
                return image_data

        except Exception as e:
            print(f"⚠️ OpenCV preprocessing failed: {e}, using original")
            return image_data

    def _auto_crop_borders(self, image: np.ndarray) -> np.ndarray:
        """
        Auto-crop white borders from receipt image.

        Args:
            image: Grayscale image array

        Returns:
            Cropped image array
        """
        try:
            # Threshold to find content area
            _, thresh = cv2.threshold(image, 250, 255, cv2.THRESH_BINARY_INV)

            # Find contours
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if contours:
                # Find the largest contour (main content)
                largest_contour = max(contours, key=cv2.contourArea)
                x, y, w, h = cv2.boundingRect(largest_contour)

                # Add small padding
                padding = 10
                x = max(0, x - padding)
                y = max(0, y - padding)
                w = min(image.shape[1] - x, w + 2 * padding)
                h = min(image.shape[0] - y, h + 2 * padding)

                cropped = image[y:y+h, x:x+w]
                return cropped
            else:
                return image

        except Exception as e:
            print(f"⚠️ Auto-crop failed: {e}")
            return image

    def _classify_block_type(self, vertices: List[Tuple[int, int]], page) -> str:
        """
        Classify text block type based on position (top=store, middle=items, bottom=totals).

        Args:
            vertices: List of (x,y) coordinates for block bounding box
            page: Vision API page object with dimensions

        Returns:
            Block type classification
        """
        if not vertices or len(vertices) < 4:
            return "unknown"

        try:
            # Get page dimensions
            page_height = page.height
            page_width = page.width

            # Calculate block center Y position
            y_coords = [v[1] for v in vertices]
            block_center_y = sum(y_coords) / len(y_coords)

            # Classify based on relative position
            relative_y = block_center_y / page_height

            if relative_y < 0.25:
                return "header"  # Top 25% - store name, date
            elif relative_y < 0.75:
                return "body"    # Middle 50% - items, descriptions
            else:
                return "footer"  # Bottom 25% - totals, tax, payment

        except Exception as e:
            print(f"⚠️ Block classification failed: {e}")
            return "unknown"

    def preprocess_image(self, image_data: bytes, filename: str) -> bytes:
        """
        Legacy preprocessing method - now delegates to OpenCV preprocessing.

        Args:
            image_data: Raw image bytes
            filename: Original filename

        Returns:
            Processed image bytes
        """
        return self._preprocess_image_opencv(image_data, filename)


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