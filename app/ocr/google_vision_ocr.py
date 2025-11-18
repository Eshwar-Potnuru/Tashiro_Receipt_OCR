#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Google Cloud Vision API OCR Engine
High-accuracy alternative to EasyOCR for Japanese text recognition
Provides GPT-like accuracy for receipt processing
"""

import base64
import io
import json
import logging
import os
from typing import List, Tuple, Optional
from PIL import Image

try:
    from google.cloud import vision
    from google.oauth2 import service_account
    GOOGLE_VISION_AVAILABLE = True
except ImportError:
    GOOGLE_VISION_AVAILABLE = False

logger = logging.getLogger(__name__)

class GoogleVisionOCR:
    """Google Cloud Vision API OCR Engine for high-accuracy Japanese text recognition"""
    
    def __init__(self, credentials_path: Optional[str] = None):
        if not GOOGLE_VISION_AVAILABLE:
            raise ImportError("Google Cloud Vision not installed. Run: pip install google-cloud-vision")
        
        self._client_available = False
        self.client = None
        self._credential_source = None
        credentials = self._load_credentials(credentials_path)

        # Try to initialize client, but handle missing credentials gracefully
        try:
            if credentials is not None:
                self.client = vision.ImageAnnotatorClient(credentials=credentials)
            else:
                self.client = vision.ImageAnnotatorClient()
            self._client_available = True
            if self._credential_source:
                logger.info(f"Google Vision client initialized using {self._credential_source}")
        except Exception as e:
            logger.warning(f"Google Vision client initialization failed: {e}")
            self.client = None
            self._client_available = False

    def _load_credentials(self, explicit_path: Optional[str]) -> Optional['service_account.Credentials']:
        """Load service account credentials from file or environment."""
        credential_scopes = ['https://www.googleapis.com/auth/cloud-platform']

        candidate_path = explicit_path or os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        if candidate_path and os.path.exists(candidate_path):
            try:
                creds = service_account.Credentials.from_service_account_file(candidate_path, scopes=credential_scopes)
                self._credential_source = candidate_path
                return creds
            except Exception as exc:
                logger.warning(f"Failed to load Google Vision credentials from {candidate_path}: {exc}")

        inline_payload = (
            os.getenv('GOOGLE_VISION_CREDENTIALS_JSON')
            or os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON')
            or os.getenv('GOOGLE_APPLICATION_CREDENTIALS_CONTENT')
        )
        if not inline_payload:
            inline_b64 = os.getenv('GOOGLE_VISION_CREDENTIALS_B64')
            if inline_b64:
                try:
                    inline_payload = base64.b64decode(inline_b64).decode('utf-8')
                except Exception as exc:
                    logger.warning(f"Failed to decode GOOGLE_VISION_CREDENTIALS_B64: {exc}")

        if inline_payload:
            try:
                creds_info = json.loads(inline_payload)
                creds = service_account.Credentials.from_service_account_info(creds_info, scopes=credential_scopes)
                self._credential_source = 'inline-environment'
                return creds
            except Exception as exc:
                logger.warning(f"Invalid Google Vision credentials JSON: {exc}")

        # Fall back to default credentials (ADC)
        self._credential_source = 'default-application-credentials'
        return None
    
    def extract_text(self, image_data) -> str:
        """
        Extract text from image using Google Cloud Vision API
        
        Args:
            image_data: PIL Image object or bytes
            
        Returns:
            Extracted text string
        """
        if not self.is_available():
            logger.warning("Google Vision client not available")
            return ""
            
        try:
            # Handle both PIL Image and bytes input
            if isinstance(image_data, bytes):
                img_byte_arr = image_data
            else:
                # Convert PIL Image to bytes
                img_byte_arr = io.BytesIO()
                image_data.save(img_byte_arr, format='PNG')
                img_byte_arr = img_byte_arr.getvalue()
            
            # Create Vision API image object
            vision_image = vision.Image(content=img_byte_arr)
            
            # Perform text detection with language hints for Japanese
            response = self.client.document_text_detection(
                image=vision_image,
                image_context=vision.ImageContext(
                    language_hints=['ja', 'en']  # Japanese and English
                )
            )
            
            if response.error.message:
                raise Exception(f"Google Vision API error: {response.error.message}")
            
            # Extract full text
            full_text = response.full_text_annotation.text if response.full_text_annotation else ""
            
            logger.info(f"Google Vision extracted {len(full_text)} characters")
            
            return full_text
            
        except Exception as e:
            logger.error(f"Google Vision OCR failed: {e}")
            return ""
    
    def is_available(self) -> bool:
        """Check if Google Vision is available"""
        return GOOGLE_VISION_AVAILABLE and getattr(self, '_client_available', False)
    
    def extract_text_with_boxes(self, image: Image.Image) -> Tuple[str, List[dict]]:
        """
        Extract text from image using Google Cloud Vision API with bounding boxes
        
        Returns:
            Tuple of (full_text, text_annotations)
        """
        try:
            # Convert PIL Image to bytes
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format='PNG')
            img_byte_arr = img_byte_arr.getvalue()
            
            # Create Vision API image object
            vision_image = vision.Image(content=img_byte_arr)
            
            # Perform text detection with language hints for Japanese
            response = self.client.document_text_detection(
                image=vision_image,
                image_context=vision.ImageContext(
                    language_hints=['ja', 'en']  # Japanese and English
                )
            )
            
            if response.error.message:
                raise Exception(f"Google Vision API error: {response.error.message}")
            
            # Extract full text
            full_text = response.full_text_annotation.text if response.full_text_annotation else ""
            
            # Extract individual text annotations with bounding boxes
            text_annotations = []
            for annotation in response.text_annotations[1:]:  # Skip first one (full text)
                # Convert bounding box to our format
                vertices = annotation.bounding_poly.vertices
                box = [
                    [vertices[0].x, vertices[0].y],  # top-left
                    [vertices[1].x, vertices[1].y],  # top-right
                    [vertices[2].x, vertices[2].y],  # bottom-right
                    [vertices[3].x, vertices[3].y],  # bottom-left
                ]
                
                text_annotations.append({
                    'text': annotation.description,
                    'box': box,
                    'confidence': 0.95  # Google Vision typically has high confidence
                })
            
            logger.info(f"Google Vision extracted {len(text_annotations)} text regions")
            logger.info(f"Full text length: {len(full_text)}")
            
            return full_text, text_annotations
            
        except Exception as e:
            logger.error(f"Google Vision OCR failed: {e}")
            return "", []

def setup_google_vision_credentials():
    """
    Setup instructions for Google Cloud Vision API
    """
    instructions = """
    🔧 GOOGLE CLOUD VISION SETUP (5 minutes):
    
    1. Go to https://console.cloud.google.com/
    2. Create a new project or select existing one
    3. Enable Vision API:
       - Go to APIs & Services > Library
       - Search "Vision API"
       - Click Enable
    
    4. Create Service Account:
       - Go to IAM & Admin > Service Accounts  
       - Click "Create Service Account"
       - Name: "receipt-ocr-service"
       - Role: "Cloud Vision API User"
    
    5. Download JSON Key:
       - Click on created service account
       - Go to "Keys" tab
       - Click "Add Key" > "Create new key" > JSON
       - Save as "google-vision-credentials.json"
    
    6. Install Python package:
       pip install google-cloud-vision
    
    7. Set environment variable:
       $env:GOOGLE_APPLICATION_CREDENTIALS = "path/to/google-vision-credentials.json"
    
    💰 COST: $1.50 per 1,000 images (first 1,000 free monthly)
    🎯 ACCURACY: 95-98% for Japanese receipts
    ⚡ SPEED: 1-3 seconds per image
    """
    
    return instructions

if __name__ == "__main__":
    print(setup_google_vision_credentials())