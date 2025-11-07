"""
OCR.space API Wrapper for compatibility
"""

import logging
from typing import Optional
from PIL import Image
import io

logger = logging.getLogger(__name__)

class OCRSpaceAPI:
    """OCR.space API wrapper with unified interface"""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize OCR.space API wrapper"""
        try:
            from app.ocr.ocr_space_ocr import OCRSpaceOCR
            self.ocr_engine = OCRSpaceOCR(api_key)
            logger.info("OCR.space API initialized")
        except Exception as e:
            logger.error(f"Failed to initialize OCR.space: {str(e)}")
            self.ocr_engine = None
    
    def is_available(self) -> bool:
        """Check if OCR.space is available"""
        return self.ocr_engine is not None and hasattr(self.ocr_engine, 'api_key') and self.ocr_engine.api_key
    
    def extract_text(self, image_data: bytes) -> str:
        """
        Extract text from image bytes
        
        Args:
            image_data: Image bytes
            
        Returns:
            Extracted text string
        """
        if not self.is_available():
            raise Exception("OCR.space not available")
        
        try:
            # Convert bytes to PIL Image
            image = Image.open(io.BytesIO(image_data))
            
            # Call the original extract_text method which returns (text, boxes)
            text, boxes = self.ocr_engine.extract_text(image)
            
            logger.info(f"OCR.space extracted {len(text)} characters")
            return text
            
        except Exception as e:
            logger.error(f"OCR.space extraction failed: {str(e)}")
            raise