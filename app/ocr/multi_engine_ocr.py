#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Multi-Engine OCR Wrapper for Japanese Receipt Processing
Integrates high-performance OCR engines with existing OCR system
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image
import os
import io

# Import existing OCR system
from .ocr_engine import OCREngine as BaseOCREngine, OCRBox

# Import enhanced engines
try:
    from ..extractors.google_vision_extractor import GoogleVisionExtractor
    GOOGLE_VISION_AVAILABLE = True
except ImportError:
    GOOGLE_VISION_AVAILABLE = False

try:
    from ..extractors.openai_vision_extractor import OpenAIVisionExtractor
    OPENAI_VISION_AVAILABLE = True
except ImportError:
    OPENAI_VISION_AVAILABLE = False

try:
    from .enhanced_japanese_ocr import EnhancedJapaneseOCR
    ENHANCED_JAPANESE_AVAILABLE = True
except ImportError:
    ENHANCED_JAPANESE_AVAILABLE = False

try:
    from .ocr_space_ocr import OCRSpaceOCR
    OCR_SPACE_AVAILABLE = True
except ImportError:
    OCR_SPACE_AVAILABLE = False

# Keep PaddleOCR reference for compatibility
PADDLEOCR_AVAILABLE = True  # Enabled for testing

logger = logging.getLogger(__name__)

class MultiEngineOCR:
    """
    Multi-Engine OCR system with automatic engine selection
    Provides high-accuracy alternatives to the existing OCR system
    """
    
    def __init__(self, preferred_engine: str = "auto"):
        """
        Initialize multi-engine OCR system
        
        Args:
            preferred_engine: "google_vision", "paddleocr", "easyocr", or "auto"
        """
        self.preferred_engine = preferred_engine
        self.available_engines = self._detect_available_engines()
        self.active_engine = None
        self.engine_type = None
        self.fallback_engine = None
        
        logger.info(f"🔍 Available OCR engines: {list(self.available_engines.keys())}")
        
        # Initialize engines
        self._initialize_engines()
    
    def _detect_available_engines(self) -> Dict[str, bool]:
        """Detect which OCR engines are available"""
        engines = {
            "google_vision": GOOGLE_VISION_AVAILABLE and self._check_google_credentials(),
            "openai_vision": OPENAI_VISION_AVAILABLE and self._check_openai_key(),
            "enhanced_japanese": ENHANCED_JAPANESE_AVAILABLE,  # High-quality Japanese OCR
            "ocr_space": OCR_SPACE_AVAILABLE and self._check_ocr_space_key(),
            "paddleocr": self._check_paddleocr_available(),
            "easyocr": True  # Always use existing fallback
        }
        
        return {k: v for k, v in engines.items() if v}
    
    def _check_paddleocr_available(self) -> bool:
        """Check if PaddleOCR is available without network calls"""
        if not PADDLEOCR_AVAILABLE:
            return False
        
        try:
            # Test if we can import the module without initializing
            import importlib
            paddle_spec = importlib.util.find_spec("paddleocr")
            # Temporarily enable PaddleOCR for testing
            return paddle_spec is not None  # and os.getenv('ENABLE_PADDLEOCR', 'true').lower() == 'true'
        except Exception:
            return False
    
    def _check_google_credentials(self) -> bool:
        """Check if Google Vision credentials are configured"""
        return (
            os.getenv('GOOGLE_APPLICATION_CREDENTIALS') is not None or
            os.path.exists('google-vision-credentials.json')
        )
    
    def _check_openai_key(self) -> bool:
        """Check if OpenAI API key is configured"""
        return os.getenv('OPENAI_API_KEY') is not None
    
    def _check_ocr_space_key(self) -> bool:
        """Check if OCR.space API key is configured"""
        return os.getenv('OCR_SPACE_API_KEY') is not None
    
    def _initialize_engines(self):
        """Initialize OCR engines in priority order"""
        
        # Priority order (best to fallback) - Premium engines first for superior quality
        engine_priority = ["google_vision", "openai_vision", "enhanced_japanese", "ocr_space", "paddleocr", "easyocr"]
        
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
            raise RuntimeError("No OCR engines available")
        
        # Initialize primary engine
        try:
            if selected_engine == "enhanced_japanese":
                self.active_engine = EnhancedJapaneseOCR(use_gpu=True)
                logger.info("🚀 Primary Engine: Enhanced Japanese OCR (GPU-Accelerated for Speed)")
                
            elif selected_engine == "google_vision":
                credentials_path = (
                    os.getenv('GOOGLE_APPLICATION_CREDENTIALS') or 
                    'google-vision-credentials.json'
                )
                self.active_engine = GoogleVisionExtractor(credentials_path)
                logger.info("🚀 Primary Engine: Google Cloud Vision API (High Accuracy)")
                
            elif selected_engine == "openai_vision":
                self.active_engine = OpenAIVisionExtractor()
                logger.info("🚀 Primary Engine: OpenAI Vision API (Structured Field Extraction)")
                
            elif selected_engine == "enhanced_japanese":
                self.active_engine = OCRSpaceOCR()
                logger.info("🚀 Primary Engine: OCR.space API (Free Cloud OCR)")
                
            elif selected_engine == "paddleocr":
                # Lazy import to avoid startup issues
                from .enhanced_paddle_ocr import PaddleOCREngine
                self.active_engine = PaddleOCREngine(use_gpu=False)
                logger.info("🚀 Primary Engine: Enhanced PaddleOCR (Free, High Accuracy)")
                
            elif selected_engine == "easyocr":
                self.active_engine = BaseOCREngine(
                    languages=["ja", "en"],
                    use_gpu=False,
                    primary_engine="easyocr"
                )
                logger.info("🚀 Primary Engine: EasyOCR (Existing System)")
                
            self.engine_type = selected_engine
            
            # Always initialize EasyOCR fallback if it's not the primary
            if selected_engine != "easyocr":
                try:
                    self.fallback_engine = BaseOCREngine(
                        languages=["ja", "en"],
                        use_gpu=False,
                        primary_engine="easyocr"
                    )
                    logger.info("⚡ Fallback Engine: EasyOCR initialized")
                except Exception as e:
                    logger.warning(f"Fallback engine initialization failed: {e}")
                    
        except Exception as e:
            logger.error(f"Failed to initialize {selected_engine}: {e}")
            # Fallback to EasyOCR if available
            if selected_engine != "easyocr" and "easyocr" in self.available_engines:
                logger.info("🔄 Falling back to EasyOCR...")
                try:
                    self.active_engine = BaseOCREngine(
                        languages=["ja", "en"],
                        use_gpu=False,
                        primary_engine="easyocr"
                    )
                    self.engine_type = "easyocr"
                    logger.info("✅ Fallback successful")
                except Exception as fallback_error:
                    logger.error(f"Fallback also failed: {fallback_error}")
                    raise
            else:
                raise
    
    def extract(self, image: Image.Image) -> Tuple[str, List[OCRBox]]:
        """
        Extract text from image using the best available OCR engine
        
        Returns:
            Tuple of (raw_text, ocr_boxes)
        """
        try:
            # Handle different engine types
            if self.engine_type == "openai_vision":
                # OpenAI Vision returns structured data, not raw OCR text
                # We'll return the raw_text from the structured extraction
                structured_data = self.active_engine.extract_fields(self._image_to_bytes(image), "multi_engine_image.jpg")
                
                if structured_data.get('error'):
                    raise Exception(f"OpenAI Vision extraction failed: {structured_data['error']}")
                
                # Extract raw text if available, otherwise create from structured data
                raw_text = structured_data.get('raw_text', '')
                if not raw_text and structured_data.get('vendor'):
                    # Create basic text representation from structured data
                    raw_text = f"{structured_data.get('vendor', '')}\n"
                    if structured_data.get('date'):
                        raw_text += f"Date: {structured_data['date']}\n"
                    if structured_data.get('total'):
                        raw_text += f"Total: ¥{structured_data['total']}\n"
                
                # Create dummy OCR boxes since OpenAI doesn't provide position data
                ocr_boxes = [OCRBox(text=raw_text, box=[0, 0, image.size[0], image.size[1]], confidence=0.9)]
                
                logger.info(f"✅ OpenAI Vision extraction successful: {len(raw_text)} characters")
                return raw_text, ocr_boxes
                
            elif self.engine_type in ["enhanced_japanese", "google_vision", "ocr_space", "paddleocr"]:
                image_bytes = self._image_to_bytes(image)
                
                if self.engine_type == "google_vision":
                    # Google Vision extractor returns OCR.space-compatible dict
                    result = self.active_engine.extract_text(image_bytes, "multi_engine_image.jpg")
                    if result.get('IsErroredOnProcessing'):
                        raise Exception(result.get('ErrorMessage', 'Google Vision extraction failed'))
                    
                    raw_text = result['ParsedResults'][0]['ParsedText'] if result['ParsedResults'] else ""
                    
                    # Create basic OCR boxes from text (Google Vision doesn't provide detailed boxes in our format)
                    ocr_boxes = [OCRBox(
                        text=raw_text,
                        box=[0, 0, image.size[0], image.size[1]],
                        confidence=result.get('metadata', {}).get('confidence', 0.9)
                    )]
                else:
                    # Other engines return (raw_text, annotations)
                    raw_text, annotations = self.active_engine.extract_text(image_bytes, "multi_engine_image.jpg")
                    
                    # Convert to OCRBox format
                    ocr_boxes = []
                    for annotation in annotations:
                        ocr_boxes.append(OCRBox(
                            text=annotation['text'],
                            box=annotation['box'], 
                            confidence=annotation['confidence']
                        ))
                
                logger.info(f"✅ OCR successful with {self.engine_type}: {len(ocr_boxes)} text regions found")
                return raw_text, ocr_boxes
                
            elif self.engine_type == "easyocr":
                # Use existing OCR system - it returns (raw_text, ocr_boxes) already
                raw_text, ocr_boxes = self.active_engine.extract(image)
                
                logger.info(f"✅ OCR successful with EasyOCR: {len(ocr_boxes)} text regions found")
                return raw_text, ocr_boxes
                
        except Exception as e:
            logger.error(f"❌ Primary OCR engine ({self.engine_type}) failed: {e}")
            
            # Try fallback engine if available
            if self.fallback_engine:
                logger.info("🔄 Attempting fallback to EasyOCR...")
                try:
                    raw_text, ocr_boxes = self.fallback_engine.extract(image)
                    
                    logger.info(f"✅ Fallback OCR successful: {len(ocr_boxes)} text regions found")
                    return raw_text, ocr_boxes
                    
                except Exception as fallback_error:
                    logger.error(f"❌ Fallback OCR also failed: {fallback_error}")
            
            # If all else fails, return empty
            logger.error("❌ All OCR engines failed")
            return "", []
    
    def _image_to_bytes(self, image: Image.Image) -> bytes:
        """Convert PIL Image to bytes for engines that need it"""
        # Ensure image is in RGB mode (no alpha channel) for JPEG compatibility
        if image.mode in ('RGBA', 'LA', 'P'):
            # Create white background for transparent images
            background = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode == 'P':
                image = image.convert('RGBA')
            background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
            image = background
        elif image.mode != 'RGB':
            image = image.convert('RGB')
            
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=95)
        return buffer.getvalue()
    
    def get_engine_status(self) -> Dict[str, Any]:
        """Get detailed information about available OCR engines and setup"""
        
        setup_info = {
            "google_vision": {
                "available": GOOGLE_VISION_AVAILABLE,
                "credentials_configured": self._check_google_credentials(),
                "accuracy": "95-98%",
                "cost": "$1.50/1000 images (first 1000 free monthly)",
                "speed": "1-3 seconds",
                "setup": [
                    "pip install google-cloud-vision",
                    "Get API key from https://console.cloud.google.com/",
                    "Download credentials JSON file", 
                    "Set GOOGLE_APPLICATION_CREDENTIALS environment variable"
                ]
            },
            "openai_vision": {
                "available": OPENAI_VISION_AVAILABLE,
                "credentials_configured": self._check_openai_key(),
                "accuracy": "90-95%",
                "cost": "$0.0013/1000 tokens (~$0.005/image)",
                "speed": "2-5 seconds",
                "setup": [
                    "pip install openai",
                    "Get API key from https://platform.openai.com/",
                    "Set OPENAI_API_KEY environment variable"
                ]
            },
            "paddleocr": {
                "available": PADDLEOCR_AVAILABLE,
                "accuracy": "92-95%", 
                "cost": "Free",
                "speed": "3-5 seconds",
                "setup": [
                    "pip install paddlepaddle paddleocr",
                    "First run downloads Japanese model (~100MB)"
                ]
            },
            "easyocr": {
                "available": True,
                "accuracy": "85-90% (when working)",
                "cost": "Free", 
                "speed": "5-10 seconds",
                "status": "Currently experiencing PyTorch issues",
                "setup": [
                    "pip uninstall torch torchvision easyocr",
                    "pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu",
                    "pip install easyocr"
                ]
            }
        }
        
        return {
            "active_engine": self.engine_type,
            "available_engines": list(self.available_engines.keys()),
            "fallback_available": self.fallback_engine is not None,
            "engines": setup_info,
            "recommendation": self._get_recommendation()
        }
    
    def _get_recommendation(self) -> str:
        """Get setup recommendation based on current state"""
        
        if self.engine_type in ["google_vision", "openai_vision"]:
            return "✅ Optimal setup - Premium AI engines provide GPT-like accuracy and structured extraction"
        elif self.engine_type == "paddleocr":
            return "✅ Good setup - PaddleOCR provides excellent free performance"
        elif self.engine_type == "easyocr":
            if GOOGLE_VISION_AVAILABLE and OPENAI_VISION_AVAILABLE:
                return "💡 Consider upgrading to Google Vision or OpenAI Vision for superior accuracy"
            elif GOOGLE_VISION_AVAILABLE:
                return "💡 Consider upgrading to Google Vision API for better accuracy"
            elif OPENAI_VISION_AVAILABLE:
                return "💡 Consider upgrading to OpenAI Vision for structured field extraction"
            elif PADDLEOCR_AVAILABLE:
                return "💡 Consider upgrading to PaddleOCR for better performance" 
            else:
                return "⚠️ Fix PyTorch installation or install alternative OCR engines"
        else:
            return "❌ No functional OCR engines - please install at least one option"

def get_setup_guide() -> str:
    """Get comprehensive setup guide for all OCR options"""
    
    return """
🎯 JAPANESE RECEIPT OCR SETUP GUIDE

⭐ OPTION 1: Google Cloud Vision API (BEST - GPT-like accuracy)
   Accuracy: 95-98% • Cost: $1.50/1000 images • Speed: 1-3s
   
   PowerShell Setup:
   pip install google-cloud-vision
   # Get credentials from: https://console.cloud.google.com/
   # Download JSON file and set:
   $env:GOOGLE_APPLICATION_CREDENTIALS = "path\\to\\credentials.json"

⭐ OPTION 2: PaddleOCR (RECOMMENDED - Free & Good)  
   Accuracy: 92-95% • Cost: Free • Speed: 3-5s
   
   PowerShell Setup:
   pip install paddlepaddle paddleocr

⭐ OPTION 3: Fix EasyOCR (Current - Needs repair)
   Accuracy: 85-90% • Cost: Free • Speed: 5-10s
   
   PowerShell Setup:
   pip uninstall torch torchvision easyocr -y
   pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu  
   pip install easyocr

💡 QUICK START: Try PaddleOCR first (free), then upgrade to Google Vision for maximum accuracy.
"""

# Convenience function for easy integration
def create_enhanced_ocr(preferred_engine: str = "auto") -> MultiEngineOCR:
    """Create and return an enhanced OCR engine instance"""
    return MultiEngineOCR(preferred_engine=preferred_engine)