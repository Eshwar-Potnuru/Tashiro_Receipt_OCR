#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Enhanced OCR Engine with Multiple High-Performance Options
Provides GPT-like accuracy for Japanese receipt processing
"""

import logging
from typing import List, Tuple, Optional, Dict, Any
from PIL import Image
from dataclasses import dataclass
import os
import numpy as np

# Import all available OCR engines
try:
    from .google_vision_ocr import GoogleVisionOCR
    GOOGLE_VISION_AVAILABLE = True
except ImportError:
    GOOGLE_VISION_AVAILABLE = False

try:
    from .paddle_ocr import PaddleOCREngine  
    PADDLEOCR_AVAILABLE = True
except ImportError:
    PADDLEOCR_AVAILABLE = False

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False

logger = logging.getLogger(__name__)

@dataclass
class OCRBox:
    text: str
    box: List[List[float]]
    confidence: float

class EnhancedOCREngine:
    """
    Enhanced OCR Engine with multiple high-performance options
    Automatically selects the best available OCR engine
    """
    
    def __init__(self, preferred_engine: str = "auto"):
        """
        Initialize with preferred OCR engine
        
        Args:
            preferred_engine: "google_vision", "paddleocr", "easyocr", or "auto"
        """
        self.preferred_engine = preferred_engine
        self.available_engines = self._detect_available_engines()
        self.active_engine = None
        
        logger.info(f"Available OCR engines: {list(self.available_engines.keys())}")
        
        # Initialize the best available engine
        self._initialize_best_engine()
    
    def _detect_available_engines(self) -> Dict[str, bool]:
        """Detect which OCR engines are available"""
        engines = {
            "google_vision": GOOGLE_VISION_AVAILABLE and self._check_google_credentials(),
            "paddleocr": PADDLEOCR_AVAILABLE,
            "easyocr": EASYOCR_AVAILABLE
        }
        
        return {k: v for k, v in engines.items() if v}
    
    def _check_google_credentials(self) -> bool:
        """Check if Google Vision credentials are configured"""
        return (
            os.getenv('GOOGLE_APPLICATION_CREDENTIALS') is not None or
            os.path.exists('google-vision-credentials.json')
        )
    
    def _initialize_best_engine(self):
        """Initialize the best available OCR engine"""
        
        # Priority order (best to fallback)
        engine_priority = ["google_vision", "paddleocr", "easyocr"]
        
        if self.preferred_engine != "auto" and self.preferred_engine in self.available_engines:
            selected_engine = self.preferred_engine
        else:
            # Auto-select best available engine
            selected_engine = None
            for engine in engine_priority:
                if engine in self.available_engines:
                    selected_engine = engine
                    break
        
        if not selected_engine:
            raise RuntimeError("No OCR engines available. Please install at least one OCR engine.")
        
        # Initialize the selected engine
        try:
            if selected_engine == "google_vision":
                credentials_path = (
                    os.getenv('GOOGLE_APPLICATION_CREDENTIALS') or 
                    'google-vision-credentials.json'
                )
                self.active_engine = GoogleVisionOCR(credentials_path)
                logger.info("🚀 Using Google Cloud Vision API (High Accuracy)")
                
            elif selected_engine == "paddleocr":
                self.active_engine = PaddleOCREngine(use_gpu=False)
                logger.info("🚀 Using PaddleOCR (Free, Good Accuracy)")
                
            elif selected_engine == "easyocr":
                import easyocr
                self.active_engine = easyocr.Reader(['ja', 'en'], gpu=False)
                logger.info("🚀 Using EasyOCR (Fallback)")
                
            self.engine_type = selected_engine
            
        except Exception as e:
            logger.error(f"Failed to initialize {selected_engine}: {e}")
            raise
    
    def extract(self, image: Image.Image) -> Tuple[str, List[OCRBox]]:
        """
        Extract text from image using the active OCR engine
        
        Returns:
            Tuple of (raw_text, ocr_boxes)
        """
        try:
            if self.engine_type in ["google_vision", "paddleocr"]:
                # Use our custom engines
                raw_text, annotations = self.active_engine.extract_text(image)
                
                # Convert to OCRBox format
                ocr_boxes = []
                for annotation in annotations:
                    ocr_boxes.append(OCRBox(
                        text=annotation['text'],
                        box=annotation['box'], 
                        confidence=annotation['confidence']
                    ))
                
                return raw_text, ocr_boxes
                
            elif self.engine_type == "easyocr":
                # Use EasyOCR directly
                img_array = np.array(image)
                results = self.active_engine.readtext(img_array)
                
                raw_text_parts = []
                ocr_boxes = []
                
                for (box, text, confidence) in results:
                    raw_text_parts.append(text)
                    ocr_boxes.append(OCRBox(
                        text=text,
                        box=[[float(x), float(y)] for x, y in box],
                        confidence=float(confidence)
                    ))
                
                raw_text = '\n'.join(raw_text_parts)
                return raw_text, ocr_boxes
                
        except Exception as e:
            logger.error(f"OCR extraction failed with {self.engine_type}: {e}")
            return "", []
    
    def get_engine_info(self) -> Dict[str, Any]:
        """Get information about the active OCR engine"""
        return {
            "active_engine": self.engine_type,
            "available_engines": list(self.available_engines.keys()),
            "engine_status": {
                "google_vision": "High accuracy, API cost" if GOOGLE_VISION_AVAILABLE else "Not available",
                "paddleocr": "Good accuracy, free" if PADDLEOCR_AVAILABLE else "Not available", 
                "easyocr": "Moderate accuracy, free" if EASYOCR_AVAILABLE else "Not available"
            }
        }

def get_setup_instructions() -> str:
    """Get setup instructions for all OCR engines"""
    
    instructions = """
    🎯 HIGH-PERFORMANCE OCR SETUP OPTIONS:
    
    ⭐ OPTION 1: Google Cloud Vision API (RECOMMENDED - GPT-like accuracy)
    💰 Cost: $1.50/1000 images (first 1000 free monthly)
    🎯 Accuracy: 95-98% for Japanese receipts
    ⚡ Speed: 1-3 seconds
    
    Setup:
    1. pip install google-cloud-vision
    2. Get API key from https://console.cloud.google.com/
    3. Download credentials JSON file
    4. Set: $env:GOOGLE_APPLICATION_CREDENTIALS = "path/to/credentials.json"
    
    ⭐ OPTION 2: PaddleOCR (FREE - Good accuracy)
    💰 Cost: Free
    🎯 Accuracy: 92-95% for Japanese receipts  
    ⚡ Speed: 3-5 seconds
    
    Setup:
    1. pip install paddlepaddle paddleocr
    2. First run downloads Japanese model (~100MB)
    
    ⭐ OPTION 3: Fix EasyOCR (Current - Needs repair)
    💰 Cost: Free
    🎯 Accuracy: 85-90% when working
    ⚡ Speed: 5-10 seconds
    
    Setup:
    1. pip uninstall torch torchvision easyocr
    2. pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
    3. pip install easyocr
    
    RECOMMENDATION: Start with PaddleOCR (free) or Google Vision (best accuracy)
    """
    
    return instructions

if __name__ == "__main__":
    print(get_setup_instructions())