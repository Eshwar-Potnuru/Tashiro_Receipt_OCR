#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OCR.space API integration for receipt OCR
Free tier: 25,000 requests/month
"""

import logging
import requests
import json
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image
import io
import base64
import os

from .ocr_engine import OCRBox

logger = logging.getLogger(__name__)

class OCRSpaceOCR:
    """
    OCR.space API integration
    Free tier: 25,000 requests/month
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize OCR.space OCR engine

        Args:
            api_key: OCR.space API key (optional, can be set via env var)
        """
        self.api_key = api_key or os.getenv('OCR_SPACE_API_KEY')
        self.base_url = "https://api.ocr.space/parse/image"

        if not self.api_key:
            logger.warning("⚠️ OCR.space API key not found. Set OCR_SPACE_API_KEY environment variable.")
            logger.info("💡 Get your free API key at: https://ocr.space/ocrapi")

    def _compress_for_api(self, image: Image.Image, max_size_kb: int = 900) -> Image.Image:
        """
        Compress image to fit OCR.space 1MB limit
        """
        # Convert to RGB if needed
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Calculate current size
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=85)
        current_size_kb = len(buffer.getvalue()) / 1024
        
        if current_size_kb <= max_size_kb:
            return image
        
        logger.info(f"🔧 Compressing image from {current_size_kb:.1f} KB to under {max_size_kb} KB")
        
        # Resize if image is very large
        width, height = image.size
        if width > 2000 or height > 2000:
            # Maintain aspect ratio while reducing size
            ratio = min(2000/width, 2000/height)
            new_width = int(width * ratio)
            new_height = int(height * ratio)
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            logger.info(f"📏 Resized to {new_width}x{new_height}")
        
        return image
    
    def _aggressive_compress(self, image: Image.Image) -> Image.Image:
        """
        Aggressive compression for very large mobile photos
        """
        # Convert to RGB
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Resize to maximum 1600px on longest side
        width, height = image.size
        max_dimension = max(width, height)
        if max_dimension > 1600:
            ratio = 1600 / max_dimension
            new_width = int(width * ratio)
            new_height = int(height * ratio)
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            logger.info(f"📏 Aggressively resized to {new_width}x{new_height}")
        
        return image

    def extract_text(self, image: Image.Image) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Extract text from image using OCR.space API
        Includes automatic image compression for mobile photos

        Args:
            image: PIL Image to process

        Returns:
            Tuple of (full_text, annotations)
        """
        if not self.api_key:
            raise RuntimeError("OCR.space API key not configured")

        try:
            logger.info(f"🔄 Processing image with OCR.space: {image.size}")
            
            # Compress image if needed for API limits
            compressed_image = self._compress_for_api(image)
            
            # Convert image to base64 with optimized settings
            buffer = io.BytesIO()
            compressed_image.save(buffer, format='JPEG', quality=85, optimize=True)
            
            # Check final size
            image_data = buffer.getvalue()
            size_kb = len(image_data) / 1024
            logger.info(f"📊 Final image size: {size_kb:.1f} KB")
            
            # If still too large, apply aggressive compression
            if size_kb > 1000:
                logger.warning(f"⚠️ Image still large ({size_kb:.1f} KB), applying aggressive compression")
                compressed_image = self._aggressive_compress(image)
                buffer = io.BytesIO()
                compressed_image.save(buffer, format='JPEG', quality=60, optimize=True)
                image_data = buffer.getvalue()
                size_kb = len(image_data) / 1024
                logger.info(f"📊 After aggressive compression: {size_kb:.1f} KB")
            
            image_base64 = base64.b64encode(image_data).decode('utf-8')

            # Prepare API request with optimized settings
            payload = {
                'apikey': self.api_key,
                'base64Image': f'data:image/jpeg;base64,{image_base64}',
                'language': 'jpn',  # Japanese
                'isCreateSearchablePdf': 'false',
                'isSearchablePdfHideTextLayer': 'true',
                'detectOrientation': 'true',
                'scale': 'true',
                'OCREngine': '2',  # Engine 2 is better for receipts
                'isTable': 'true'  # Better for receipt structure
            }

            logger.info("🔍 Sending image to OCR.space API...")

            # Make API request
            response = requests.post(
                self.base_url,
                data=payload,
                timeout=30
            )

            response.raise_for_status()
            result = response.json()

            # Check for API errors
            if result.get('IsErroredOnProcessing'):
                error_message = result.get('ErrorMessage', ['Unknown error'])[0]
                raise RuntimeError(f"OCR.space API error: {error_message}")

            # Parse results
            parsed_text = result.get('ParsedResults', [])
            if not parsed_text:
                logger.warning("⚠️ No text found in OCR.space response")
                return "", []

            # Extract text and create annotations
            full_text = ""
            annotations = []

            for result_item in parsed_text:
                # Get the parsed text
                parsed_text_content = result_item.get('ParsedText', '').strip()
                if parsed_text_content:
                    full_text += parsed_text_content + '\n'

                    # Try to get line-level information from TextOverlay
                    text_overlay = result_item.get('TextOverlay', {})
                    lines = text_overlay.get('Lines', [])

                    if lines:
                        # Use line-level bounding boxes
                        for line in lines:
                            line_text = line.get('LineText', '').strip()
                            if line_text:
                                # Get bounding box for the line
                                words = line.get('Words', [])
                                if words:
                                    # Use first word's bounding box for the line
                                    word = words[0]
                                    bbox = word.get('WordTextLocation', [])

                                    if len(bbox) >= 4:
                                        # Convert to our format [x1,y1,x2,y2,x3,y3,x4,y4]
                                        x1, y1 = bbox[0], bbox[1]
                                        x2, y2 = bbox[2], bbox[1]
                                        x3, y3 = bbox[2], bbox[3]
                                        x4, y4 = bbox[0], bbox[3]

                                        box_coords = [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]

                                        annotations.append({
                                            'text': line_text,
                                            'box': box_coords,
                                            'confidence': 0.8
                                        })
                    else:
                        # No line-level data, create a single annotation for the whole text
                        # Estimate bounding box based on image size
                        img_width, img_height = image.size
                        annotations.append({
                            'text': parsed_text_content,
                            'box': [[0, 0], [img_width, 0], [img_width, img_height], [0, img_height]],
                            'confidence': 0.8
                        })

            full_text = full_text.strip()

            full_text = full_text.strip()

            logger.info(f"✅ OCR.space processed: {len(annotations)} text regions")
            if full_text:
                preview = full_text.replace('\n', ' ')[:100]
                logger.info(f"📋 Preview: {preview}...")

            return full_text, annotations

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ OCR.space API request failed: {e}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"❌ Failed to parse OCR.space response: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ OCR.space processing error: {e}")
            raise

    def extract(self, image: Image.Image) -> Tuple[str, List[OCRBox]]:
        """
        Extract text from image (compatible with existing OCR interface)
        Includes advanced preprocessing for better OCR quality

        Returns:
            Tuple of (raw_text, ocr_boxes)
        """
        # Apply OCR.space-optimized preprocessing
        from .preprocess import preprocess_for_ocr_space
        
        logger.info("🔄 Preprocessing image for OCR.space...")
        preprocessed_image = preprocess_for_ocr_space(image)
        logger.info("✅ Preprocessing complete")
        
        raw_text, annotations = self.extract_text(preprocessed_image)

        # Convert to OCRBox format
        ocr_boxes = []
        for annotation in annotations:
            ocr_boxes.append(OCRBox(
                text=annotation['text'],
                box=annotation['box'],
                confidence=annotation.get('confidence', 0.8)
            ))

        return raw_text, ocr_boxes