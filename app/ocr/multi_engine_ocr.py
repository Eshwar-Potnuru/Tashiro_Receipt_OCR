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
    from ..extractors.enhanced_japanese_extractor import EnhancedJapaneseExtractor
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
        
        # Initialize enhanced Japanese extractor for post-processing
        if ENHANCED_JAPANESE_AVAILABLE:
            self.enhanced_extractor = EnhancedJapaneseExtractor()
            logger.info("✅ Enhanced Japanese field extractor initialized")
        else:
            self.enhanced_extractor = None
    
    def _detect_available_engines(self) -> Dict[str, bool]:
        """Detect which OCR engines are available"""
        engines = {
            "google_vision": GOOGLE_VISION_AVAILABLE and self._check_google_credentials(),
            "openai_vision": OPENAI_VISION_AVAILABLE and self._check_openai_key(),
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
        engine_priority = ["google_vision", "openai_vision", "paddleocr", "easyocr"]
        
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
            if selected_engine == "google_vision":
                credentials_path = (
                    os.getenv('GOOGLE_APPLICATION_CREDENTIALS') or 
                    'google-vision-credentials.json'
                )
                self.active_engine = GoogleVisionExtractor(credentials_path)
                logger.info("🚀 Primary Engine: Google Cloud Vision API (High Accuracy)")
                
            elif selected_engine == "openai_vision":
                self.active_engine = OpenAIVisionExtractor()
                logger.info("🚀 Primary Engine: OpenAI Vision API (Structured Field Extraction)")
                
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
    
    def _image_to_bytes(self, image: Image.Image) -> bytes:
        """Convert PIL Image to bytes for API calls"""
        buffer = io.BytesIO()
        # Save as JPEG for API compatibility
        image.save(buffer, format='JPEG', quality=95)
        return buffer.getvalue()
    
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
                try:
                    # Use the receipt extraction prompt
                    prompt = """
あなたは日本語の領収書のOCRテキストを読み取る専門家です。

この領収書画像から、すべてのテキストを可能な限り正確に抽出してください。
- 日本語の漢字、ひらがな、カタカナを正しく読み取る
- 日付、金額、店舗名などの重要な情報を含む
- テキストのレイアウトを保ちながら、読みやすい形式で出力

抽出したテキストのみを出力してください。説明は不要です。
"""
                    structured_data = self.active_engine.extract_with_custom_prompt(self._image_to_bytes(image), prompt, "multi_engine_image.jpg")
                    
                    raw_text = structured_data.get('corrected_text', '')
                    
                    # Create dummy OCR boxes since OpenAI doesn't provide position data
                    ocr_boxes = [OCRBox(text=raw_text, box=[0, 0, image.size[0], image.size[1]], confidence=0.9)]
                    
                    logger.info(f"✅ OpenAI Vision extraction successful: {len(raw_text)} characters")
                    return raw_text, ocr_boxes
                    
                except Exception as e:
                    logger.error(f"OpenAI Vision extraction failed: {e}")
                    raise Exception(f"OpenAI Vision extraction failed: {e}")
                
            elif self.engine_type in ["google_vision"]:
                image_bytes = self._image_to_bytes(image)
                
                if self.engine_type == "google_vision":
                    # Google Vision extractor returns OCR.space-compatible dict
                    ocr_result = self.active_engine.extract_text(image_bytes, "multi_engine_image.jpg")
                    if ocr_result.get('IsErroredOnProcessing'):
                        raise Exception(ocr_result.get('ErrorMessage', 'Google Vision extraction failed'))
                    
                    raw_text = ocr_result['ParsedResults'][0]['ParsedText'] if ocr_result['ParsedResults'] else ""
                    
                    # Apply OpenAI corrective pass for mis-segmented kanji and date formats
                    if OPENAI_VISION_AVAILABLE and self._should_apply_openai_correction(raw_text):
                        try:
                            corrected_text = self._apply_openai_correction(raw_text, image_bytes)
                            if corrected_text and len(corrected_text) > len(raw_text) * 0.8:  # Ensure meaningful correction
                                logger.info("✅ OpenAI correction applied - improved text quality")
                                raw_text = corrected_text
                                # Update the OCR result with corrected text
                                if ocr_result['ParsedResults']:
                                    ocr_result['ParsedResults'][0]['ParsedText'] = raw_text
                        except Exception as correction_error:
                            logger.warning(f"OpenAI correction failed, using original text: {correction_error}")
                    
                    # Use enhanced Japanese extractor for structured field extraction
                    if self.enhanced_extractor and ocr_result.get('metadata', {}).get('structured_layout'):
                        try:
                            structured_result = self.enhanced_extractor.extract_fields_enhanced(ocr_result, "multi_engine_image.jpg")
                            logger.info("✅ Enhanced Japanese field extraction successful")
                            # Return the structured result directly - this indicates structured extraction
                            return structured_result, []
                        except Exception as enhanced_error:
                            logger.warning(f"Enhanced extraction failed, falling back to basic: {enhanced_error}")
                    
                    # Fallback: Create basic OCR boxes from text
                    ocr_boxes = [OCRBox(
                        text=raw_text,
                        box=[0, 0, image.size[0], image.size[1]],
                        confidence=ocr_result.get('metadata', {}).get('confidence', 0.9)
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
    
    def _should_apply_openai_correction(self, raw_text: str) -> bool:
        """
        Determine if OpenAI correction should be applied based on text characteristics
        
        Args:
            raw_text: Raw OCR text from Google Vision
            
        Returns:
            True if correction should be applied
        """
        if not raw_text or len(raw_text.strip()) < 50:
            return False
            
        # Check for indicators of poor OCR quality that OpenAI can help with
        indicators = [
            '日' in raw_text and ('年' not in raw_text or '月' not in raw_text),  # Fragmented dates
            '合計' in raw_text and '¥' not in raw_text and '￥' not in raw_text,  # Missing currency symbols
            len([c for c in raw_text if ord(c) > 0x3000 and ord(c) < 0x9FFF]) < 10,  # Too few kanji characters
            'レジ' in raw_text or '領収' in raw_text,  # Japanese receipt indicators
        ]
        
        return any(indicators)
    
    def _apply_openai_correction(self, raw_text: str, image_bytes: bytes) -> Optional[str]:
        """
        Apply OpenAI Vision correction to improve OCR text quality
        
        Args:
            raw_text: Raw OCR text from Google Vision
            image_bytes: Original image bytes
            
        Returns:
            Corrected text or None if correction failed
        """
        try:
            # Initialize OpenAI extractor if not already done
            if not hasattr(self, '_openai_extractor'):
                if OPENAI_VISION_AVAILABLE:
                    self._openai_extractor = OpenAIVisionExtractor()
                else:
                    return None
            
            # Create a focused prompt for correction
            correction_prompt = f"""
あなたは日本語の領収書のOCRテキストを修正する専門家です。

元のOCRテキスト:
{raw_text}

このテキストを分析し、以下の問題を修正してください：
1. 誤って分割された漢字を正しく結合する
2. 日付形式を正しい日本語形式に修正する（例: 2024年1月15日）
3. 金額に通貨記号（¥または￥）が欠けている場合は追加する
4. 店舗名や商品名が正しく読み取れていない場合は修正する
5. 合計や小計の金額が正しくない場合は修正する

修正した完全なテキストのみを出力してください。説明は不要です。
"""
            
            # Use OpenAI Vision with the correction prompt
            corrected_result = self._openai_extractor.extract_with_custom_prompt(
                image_bytes, 
                correction_prompt,
                filename="correction_image.jpg"
            )
            
            if corrected_result and 'corrected_text' in corrected_result:
                corrected_text = corrected_result['corrected_text'].strip()
                if corrected_text and len(corrected_text) > len(raw_text) * 0.5:  # Ensure meaningful result
                    return corrected_text
            
            return None
            
        except Exception as e:
            logger.warning(f"OpenAI correction failed: {e}")
            return None
    
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