#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PaddleOCR Engine - Free Alternative with High Accuracy
Local processing, no API costs, good Japanese support
"""

import logging
from typing import List, Tuple, Optional
from PIL import Image
import numpy as np

try:
    from paddleocr import PaddleOCR
    PADDLEOCR_AVAILABLE = True
except ImportError:
    PADDLEOCR_AVAILABLE = False

logger = logging.getLogger(__name__)

class PaddleOCREngine:
    """PaddleOCR Engine for free, local Japanese text recognition"""
    
    def __init__(self, use_gpu: bool = False):
        if not PADDLEOCR_AVAILABLE:
            raise ImportError("PaddleOCR not installed. Run: pip install paddlepaddle paddleocr")
        
        self.use_gpu = use_gpu
        self.ocr = None  # Lazy initialization to avoid network calls during startup
        
        logger.info("PaddleOCR engine prepared (will initialize on first use)")
    
    def _initialize_ocr(self):
        """Lazy initialization of PaddleOCR to avoid startup network calls"""
        if self.ocr is None:
            logger.info("Initializing PaddleOCR with Japanese language model...")
            try:
                # Initialize PaddleOCR with Japanese and English support
                self.ocr = PaddleOCR(
                    use_angle_cls=True,  # Enable text direction classification
                    lang='japan'         # Japanese language model
                )
                logger.info("✅ PaddleOCR initialized successfully")
            except Exception as e:
                logger.error(f"❌ PaddleOCR initialization failed: {e}")
                raise
    
    def extract_text(self, image: Image.Image) -> Tuple[str, List[dict]]:
        """
        Extract text from image using PaddleOCR
        
        Returns:
            Tuple of (full_text, text_annotations)
        """
        try:
            # Initialize OCR on first use
            self._initialize_ocr()
            
            # Convert PIL Image to numpy array
            img_array = np.array(image)
            
            # Run OCR
            results = self.ocr.ocr(img_array)
            
            if not results or not results[0]:
                logger.warning("No text detected by PaddleOCR")
                return "", []
            
            # Process results
            full_text_parts = []
            text_annotations = []
            
            for line in results[0]:
                if line:
                    box, (text, confidence) = line
                    
                    # Convert box format to our standard
                    formatted_box = [
                        [float(box[0][0]), float(box[0][1])],  # top-left
                        [float(box[1][0]), float(box[1][1])],  # top-right  
                        [float(box[2][0]), float(box[2][1])],  # bottom-right
                        [float(box[3][0]), float(box[3][1])],  # bottom-left
                    ]
                    
                    text_annotations.append({
                        'text': text,
                        'box': formatted_box,
                        'confidence': confidence
                    })
                    
                    full_text_parts.append(text)
            
            full_text = '\n'.join(full_text_parts)
            
            logger.info(f"PaddleOCR extracted {len(text_annotations)} text regions")
            logger.info(f"Full text length: {len(full_text)}")
            
            return full_text, text_annotations
            
        except Exception as e:
            logger.error(f"PaddleOCR failed: {e}")
            return "", []

def setup_paddleocr():
    """
    Setup instructions for PaddleOCR
    """
    instructions = """
    🔧 PADDLEOCR SETUP (2 minutes):
    
    1. Install PaddleOCR:
       pip install paddlepaddle paddleocr
    
    2. First run will download Japanese language model (~100MB)
    
    💰 COST: Free
    🎯 ACCURACY: 92-95% for Japanese receipts  
    ⚡ SPEED: 3-5 seconds per image (local processing)
    📦 SIZE: ~500MB total installation
    """
    
    return instructions

if __name__ == "__main__":
    print(setup_paddleocr())