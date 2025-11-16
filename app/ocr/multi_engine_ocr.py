#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Multi-Engine OCR System
Combines multiple OCR engines for optimal text extraction
"""

import logging
import io
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Optional, Any, Tuple, List
from PIL import Image

logger = logging.getLogger(__name__)

# OCR Engine imports with error handling
try:
    from app.ocr.google_vision_ocr import GoogleVisionOCR
    GOOGLE_VISION_AVAILABLE = True
except Exception as e:
    logger.warning(f"Google Vision OCR not available: {e}")
    GoogleVisionOCR = None
    GOOGLE_VISION_AVAILABLE = False

try:
    from app.ocr.openai_vision_ocr import OpenAIVisionOCR
    OPENAI_VISION_AVAILABLE = True
except Exception as e:
    logger.warning(f"OpenAI Vision OCR not available: {e}")
    OpenAIVisionOCR = None
    OPENAI_VISION_AVAILABLE = False

try:
    from app.ocr.ocr_space_ocr import OCRSpaceOCR
    OCR_SPACE_AVAILABLE = True
except Exception as e:
    logger.warning(f"OCR.space OCR not available: {e}")
    OCRSpaceOCR = None
    OCR_SPACE_AVAILABLE = False

try:
    from app.ocr.document_ai_ocr import DocumentAIOCR
    DOCUMENT_AI_AVAILABLE = True
except Exception as e:
    logger.warning(f"Document AI OCR not available: {e}")
    DocumentAIOCR = None
    DOCUMENT_AI_AVAILABLE = False

class MultiEngineOCR:
    """Multi-engine OCR system with fallback capabilities"""
    
    def __init__(self):
        """Initialize available OCR engines with graceful fallback"""
        logger.info("Initializing Multi-Engine OCR system...")
        
        # Engine toggles / configuration
        self.document_ai_enabled = os.getenv('DOCUMENT_AI_ENABLED', 'false').lower() == 'true'

        # Initialize engines
        self.document_ai = None
        self.google_vision = None
        self.openai_vision = None
        self.ocr_space = None
        
        # Safe initialization with try-catch for each engine
        if DOCUMENT_AI_AVAILABLE:
            try:
                self.document_ai = DocumentAIOCR()
            except Exception as e:
                logger.warning(f"Document AI initialization failed: {e}")
        
        if GOOGLE_VISION_AVAILABLE:
            try:
                self.google_vision = GoogleVisionOCR()
            except Exception as e:
                logger.warning(f"Google Vision initialization failed: {e}")
        
        if OPENAI_VISION_AVAILABLE:
            try:
                self.openai_vision = OpenAIVisionOCR()
            except Exception as e:
                logger.warning(f"OpenAI Vision initialization failed: {e}")
        
        if OCR_SPACE_AVAILABLE:
            try:
                self.ocr_space = OCRSpaceOCR()
            except Exception as e:
                logger.warning(f"OCR.space initialization failed: {e}")
        
        # Check engine availability safely
        self.engines_available = {}
        
        for engine_name, engine_obj in [
            ('document_ai', self.document_ai),
            ('google_vision', self.google_vision),
            ('openai', self.openai_vision),
            ('ocr_space', self.ocr_space)
        ]:
            try:
                self.engines_available[engine_name] = (
                    engine_obj is not None and 
                    hasattr(engine_obj, 'is_available') and 
                    engine_obj.is_available()
                )
            except Exception:
                self.engines_available[engine_name] = False
        
        available_count = sum(self.engines_available.values())
        logger.info(f"OCR engines initialized: {available_count}/4 available")
        logger.info(f"Available: {[k for k, v in self.engines_available.items() if v]}")
    
    def extract_structured(self, image_data: bytes) -> Dict[str, Any]:
        """Extract structured data using all available engines with aggregation."""
        logger.info("Starting structured extraction...")

        if not image_data:
            logger.error("Invalid image data: empty payload")
            return {
                'structured_data': {},
                'raw_text': '',
                'engine_used': '',
                'success': False,
                'error': 'Invalid image data (0 bytes)'
            }

        logger.info(f"Received image data size: {len(image_data)} bytes")

        if len(image_data) < 100:
            logger.error(f"Invalid image data: {len(image_data)} bytes")
            return {
                'structured_data': {},
                'raw_text': '',
                'engine_used': '',
                'success': False,
                'error': f'Invalid image data ({len(image_data)} bytes)'
            }

        raw_text_sources: Dict[str, str] = {}
        structured_data: Dict[str, Any] = {}
        engines_attempted = []

        # Document AI (structured data)
        if self.document_ai_enabled and self.engines_available.get('document_ai', False):
            try:
                logger.info("Running document_ai extraction...")
                doc_data = self.document_ai.extract_structured_data(image_data)
                engines_attempted.append('document_ai')
                if doc_data:
                    structured_data = dict(doc_data)
                    doc_raw = doc_data.get('raw_text') or ''
                    if doc_raw.strip():
                        raw_text_sources['document_ai'] = doc_raw
                        logger.info(f"document_ai produced raw text length {len(doc_raw)}")
            except Exception as e:
                logger.error(f"document_ai failed: {e}")

        # Google Vision + OpenAI Vision in parallel
        parallel_engines = []
        if self.engines_available.get('google_vision', False):
            parallel_engines.append(('google_vision', self.google_vision.extract_text))
        if self.engines_available.get('openai', False):
            parallel_engines.append(('openai', self.openai_vision.extract_text))

        parallel_texts, parallel_attempts = self._run_parallel_text_engines(image_data, parallel_engines)
        raw_text_sources.update(parallel_texts)
        engines_attempted.extend(parallel_attempts)

        combined_text, contributing_engines = self._combine_texts(raw_text_sources)

        if structured_data:
            # Ensure combined raw text is reflected in structured payload
            if combined_text:
                structured_data['raw_text'] = combined_text
        else:
            structured_data = {'raw_text': combined_text, 'entities': {}}

        success = bool(combined_text.strip())

        # Fallback to OCR.space if we still have insufficient text
        if (not success or len(combined_text.strip()) < 30) and self.engines_available.get('ocr_space', False):
            try:
                logger.info("Running ocr_space extraction as fallback...")
                engines_attempted.append('ocr_space')
                image = Image.open(io.BytesIO(image_data))
                text, _ = self.ocr_space.extract_text(image)
                if text and len(text.strip()) > 10:
                    raw_text_sources['ocr_space'] = text
                    combined_text, contributing_engines = self._combine_texts(raw_text_sources)
                    structured_data['raw_text'] = combined_text
                    success = bool(combined_text.strip())
                    logger.info(f"ocr_space produced raw text length {len(text)}")
                else:
                    logger.info("ocr_space returned insufficient text")
            except Exception as e:
                logger.error(f"ocr_space failed: {e}")

        engine_used = '+'.join(contributing_engines)

        if not success:
            logger.error("All OCR engines failed to produce usable text")

        return {
            'structured_data': structured_data,
            'raw_text': combined_text,
            'engine_used': engine_used,
            'success': success,
            'engines_attempted': engines_attempted
        }
    
    def extract(self, image_data: bytes) -> str:
        """Legacy method for backward compatibility"""
        result = self.extract_structured(image_data)
        return result.get('raw_text', '')

    @staticmethod
    def _merge_text_blocks(primary: str, secondary: str) -> str:
        """Merge secondary text into primary while avoiding duplicate lines."""
        if not primary:
            return secondary or ''
        if not secondary:
            return primary

        primary_lines = primary.splitlines()
        secondary_lines = [line for line in secondary.splitlines() if line not in primary_lines]

        if not secondary_lines:
            return primary

        return primary + '\n' + '\n'.join(secondary_lines)

    def _combine_texts(self, text_sources: Dict[str, str]) -> Tuple[str, List[str]]:
        """Combine text outputs from multiple engines, preserving order of preference."""
        combined = ''
        contributing = []
        preferred_order = ['google_vision', 'openai', 'document_ai', 'ocr_space']

        for engine_name in preferred_order:
            text = text_sources.get(engine_name)
            if not text or not text.strip():
                continue
            combined = self._merge_text_blocks(combined, text)
            contributing.append(engine_name)

        return combined, contributing

    def _run_parallel_text_engines(self, image_data: bytes, engines: List[Tuple[str, Any]]) -> Tuple[Dict[str, str], List[str]]:
        """Execute multiple OCR engines concurrently to minimize end-to-end latency."""
        if not engines:
            return {}, []

        texts: Dict[str, str] = {}
        attempted: List[str] = []

        with ThreadPoolExecutor(max_workers=len(engines)) as executor:
            future_map = {}
            for engine_name, engine_func in engines:
                attempted.append(engine_name)
                future = executor.submit(engine_func, image_data)
                future_map[future] = engine_name

            for future in as_completed(future_map):
                engine_name = future_map[future]
                try:
                    engine_text = future.result()
                    if engine_text and len(engine_text.strip()) > 10:
                        texts[engine_name] = engine_text
                        logger.info(f"{engine_name} produced raw text length {len(engine_text)}")
                    else:
                        logger.info(f"{engine_name} returned insufficient text")
                except Exception as exc:
                    logger.error(f"{engine_name} failed: {exc}")

        return texts, attempted

def create_enhanced_ocr() -> MultiEngineOCR:
    """Factory function to create OCR instance"""
    return MultiEngineOCR()