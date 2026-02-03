#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Multi-Engine OCR System
Combines multiple OCR engines for optimal text extraction
"""

import logging
import io
import os
from concurrent.futures import ThreadPoolExecutor, wait, ALL_COMPLETED
import time
from typing import Dict, Optional, Any, Tuple, List
from PIL import Image

logger = logging.getLogger(__name__)

# OCR Engine imports with error handling
try:
    from app.extractors.field_extractors import extract_receipt_fields
    FIELD_EXTRACTOR_AVAILABLE = True
except ImportError:
    FIELD_EXTRACTOR_AVAILABLE = False
    logger.warning("Field extractor not available")

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
    from app.ocr.document_ai_ocr import DocumentAIOCREngine
    from app.ocr.document_ai_mapping import map_document_ai_payload, validate_structured_payload
    from app.ocr.document_ai_merge import merge_structured_data
    DOCUMENT_AI_AVAILABLE = True
except Exception as e:
    logger.warning(f"Document AI OCR not available: {e}")
    DocumentAIOCREngine = None
    DOCUMENT_AI_AVAILABLE = False

class MultiEngineOCR:
    """Multi-engine OCR system with fallback capabilities"""
    
    def __init__(self):
        """Initialize available OCR engines with graceful fallback"""
        logger.info("Initializing Multi-Engine OCR system...")
        
        # Engine toggles / configuration
        docai_env_flag = os.getenv('DOCUMENT_AI_ENABLED')
        self.document_ai_enabled = (
            docai_env_flag.lower() == 'true'
            if docai_env_flag is not None
            else False
        )

        # Shared executor for parallel OCR calls
        max_workers = int(os.getenv('OCR_PARALLELISM', '4'))
        self.parallel_executor = ThreadPoolExecutor(max_workers=max_workers)

        # Initialize engines
        self.document_ai = None
        self.google_vision = None
        self.openai_vision = None
        self.ocr_space = None
        self.parallel_timeout = float(os.getenv('OCR_ENGINE_TIMEOUT_SECONDS', '12'))
        
        # Safe initialization with try-catch for each engine
        if DOCUMENT_AI_AVAILABLE:
            try:
                self.document_ai = DocumentAIOCREngine()
            except Exception as e:
                logger.warning(f"Document AI initialization failed: {e}")

        # If env flag is unset but credentials exist, enable Document AI automatically
        if (
            docai_env_flag is None
            and self.document_ai is not None
            and hasattr(self.document_ai, 'is_available')
        ):
            try:
                if self.document_ai.is_available():
                    self.document_ai_enabled = True
                    logger.info("Document AI enabled automatically (credentials detected)")
            except Exception:
                pass
        
        if GOOGLE_VISION_AVAILABLE:
            try:
                # Priority 1: Check for JSON credentials in environment (Railway/cloud)
                creds_json = os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON')
                if creds_json:
                    logger.info("Using GOOGLE_APPLICATION_CREDENTIALS_JSON from environment (Railway)")
                    # GoogleVisionOCR will handle the JSON parsing
                    self.google_vision = GoogleVisionOCR(credentials_path=None)
                else:
                    # Priority 2: Check for file path in environment
                    google_creds_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
                    
                    # Priority 3: Search for credentials file locally
                    if not google_creds_path:
                        script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                        # Try multiple possible filenames
                        possible_keys = [
                            'aim-tashiro-poc-dec6e8e0cdb7.json',  # Current key
                            'aim-tashiro-poc-09a7f137eb05.json',  # Legacy key  
                            'google_vision_key.json'               # Original key
                        ]
                        for key_file in possible_keys:
                            test_path = os.path.join(script_dir, 'config', key_file)
                            if os.path.exists(test_path):
                                google_creds_path = test_path
                                break
                        
                        # Fallback: try from current working directory
                        if not google_creds_path or not os.path.exists(google_creds_path):
                            current_dir = os.getcwd()
                            for key_file in possible_keys:
                                test_path = os.path.join(current_dir, 'config', key_file)
                                if os.path.exists(test_path):
                                    google_creds_path = test_path
                                    break
                    
                    if google_creds_path and os.path.exists(google_creds_path):
                        logger.info(f"Using Google Vision credentials file: {google_creds_path}")
                        os.environ.setdefault('GOOGLE_APPLICATION_CREDENTIALS', google_creds_path)
                        self.google_vision = GoogleVisionOCR(credentials_path=google_creds_path)
                    else:
                        logger.info("No credentials file found, trying default credentials")
                        self.google_vision = GoogleVisionOCR(credentials_path=None)
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
    
    def extract_structured(self, image_data: bytes, engine: Optional[str] = None) -> Dict[str, Any]:
        """Extract structured data with optional engine preference overrides."""

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

        engine_pref = (engine or 'auto').lower()
        if engine_pref not in {'auto', 'standard', 'document_ai'}:
            engine_pref = 'auto'

        if engine_pref == 'document_ai':
            return self._run_document_ai_only(image_data)

        raw_text_sources: Dict[str, str] = {}
        structured_data: Dict[str, Any] = {}
        document_ai_structured: Optional[Dict[str, Any]] = None
        engines_attempted: List[str] = []
        merge_strategy = 'standard_only'
        docai_confidence: Optional[float] = None

        include_document_ai = (
            engine_pref != 'standard'
            and self.document_ai_enabled
            and self.engines_available.get('document_ai', False)
        )

        parallel_engines = []
        if self.engines_available.get('google_vision', False):
            parallel_engines.append(('google_vision', self.google_vision.extract_text))
        if self.engines_available.get('openai', False):
            parallel_engines.append(('openai', self.openai_vision.extract_text))
        if include_document_ai:
            def document_ai_text_only(image_bytes: bytes) -> str:
                nonlocal document_ai_structured
                try:
                    document_ai_structured = self._invoke_document_ai(image_bytes)
                    if document_ai_structured:
                        return document_ai_structured.get('raw_text', '')
                except Exception as exc:
                    logger.error(f"Document AI failed: {exc}")
                return ''

            parallel_engines.append(('document_ai', document_ai_text_only))

        parallel_texts, parallel_attempts = self._run_parallel_text_engines_fast(image_data, parallel_engines)
        raw_text_sources.update(parallel_texts)
        engines_attempted.extend(parallel_attempts)

        combined_text, contributing_engines = self._combine_texts(raw_text_sources)
        standard_confidence = self._estimate_standard_confidence(raw_text_sources, engines_attempted)
        had_standard_text = any(engine != 'document_ai' for engine in contributing_engines)

        if document_ai_structured:
            docai_confidence = self._compute_docai_confidence(document_ai_structured)
            structured_data = (
                merge_structured_data(structured_data, document_ai_structured)
                if structured_data
                else document_ai_structured
            )
            structured_data['docai_raw_entities'] = document_ai_structured.get('docai_raw_entities')
            structured_data['docai_raw_fields'] = document_ai_structured.get('docai_raw_fields')
            merge_strategy = 'hybrid' if had_standard_text else 'docai_over_standard'
        elif engine_pref == 'document_ai':
            merge_strategy = 'docai_over_standard'

        if structured_data:
            if combined_text:
                structured_data['raw_text'] = combined_text
        else:
            structured_data = {'raw_text': combined_text, 'entities': {}}

        if structured_data:
            if combined_text:
                structured_data['raw_text'] = combined_text
        else:
            structured_data = {'raw_text': combined_text, 'entities': {}}

        # Extract fields from combined text if no canonical entities from Document AI
        canonical_entities = structured_data.get('entities', {})
        has_canonical_fields = any(key in canonical_entities for key in ['vendor', 'date', 'total', 'invoice_number'])
        
        if not has_canonical_fields and combined_text and FIELD_EXTRACTOR_AVAILABLE:
            try:
                extracted_fields = extract_receipt_fields(combined_text)
                if extracted_fields:
                    # Convert extracted fields to entities format
                    entities = {}
                    confidence_scores = {}
                    for field_name, field_value in extracted_fields.items():
                        if field_value and field_value != 'N/A':
                            entities[field_name] = {'text': str(field_value), 'source': 'pattern_extraction'}
                            # Use the actual confidence if available (for categorization), else default to 0.7
                            if field_name == 'confidence':
                                # This is the categorization confidence, store it directly
                                confidence_scores['account_title'] = field_value / 100.0 if field_value > 1 else field_value
                            elif field_name == 'account_title':
                                # Category field, confidence comes from 'confidence' key
                                pass  # Will be handled by the 'confidence' key
                            else:
                                confidence_scores[field_name] = 0.7  # Medium confidence for pattern-based extraction
                    
                    structured_data['entities'] = entities
                    structured_data['confidence_scores'] = confidence_scores
            except Exception as e:
                logger.error(f"Field extraction failed: {e}")

        structured_data = validate_structured_payload(structured_data)
        docai_raw_entities = structured_data.get('docai_raw_entities')
        docai_raw_fields = structured_data.get('docai_raw_fields')

        success = bool(combined_text.strip()) or bool(structured_data.get('entities'))
        engine_used = '+'.join(contributing_engines)
        if document_ai_structured and 'document_ai' not in contributing_engines:
            engine_used = (engine_used + '+document_ai').strip('+')

        if not success:
            logger.error("All OCR engines failed to produce usable text")

        return {
            'structured_data': structured_data,
            'raw_text': combined_text,
            'engine_used': engine_used,
            'success': success,
            'engines_attempted': engines_attempted,
            'merge_strategy': merge_strategy,
            'confidence_docai': docai_confidence,
            'confidence_standard': standard_confidence,
            'docai_raw_entities': docai_raw_entities,
            'docai_raw_fields': docai_raw_fields
        }
    
    def extract(self, image_data: bytes) -> str:
        """Legacy method for backward compatibility"""
        result = self.extract_structured(image_data)
        return result.get('raw_text', '')

    def _run_document_ai_only(self, image_data: bytes) -> Dict[str, Any]:
        engines_attempted = ['document_ai']
        logger.info("Document AI only mode invoked")
        structured = self._invoke_document_ai(image_data)

        if not structured:
            logger.warning("Document AI unavailable; falling back to standard OCR")
            fallback = self.extract_structured(image_data, engine='standard')
            if isinstance(fallback, dict):
                attempts = fallback.get('engines_attempted', []) or []
                if isinstance(attempts, list):
                    fallback['engines_attempted'] = engines_attempted + attempts
            return fallback

        raw_text = structured.get('raw_text', '')
        success = bool(raw_text.strip()) or bool(structured.get('entities'))
        docai_confidence = self._compute_docai_confidence(structured)

        return {
            'structured_data': structured,
            'raw_text': raw_text,
            'engine_used': 'document_ai',
            'success': success,
            'engines_attempted': engines_attempted,
            'merge_strategy': 'docai_over_standard',
            'confidence_docai': docai_confidence,
            'confidence_standard': None,
            'docai_raw_entities': structured.get('docai_raw_entities'),
            'docai_raw_fields': structured.get('docai_raw_fields')
        }

    def _invoke_document_ai(self, image_data: bytes) -> Dict[str, Any]:
        if not self.document_ai or not hasattr(self.document_ai, 'extract_structured_data'):
            logger.warning("Document AI wrapper missing or not callable")
            return {}

        raw_payload = self.document_ai.extract_structured_data(image_data)
        if not raw_payload:
            logger.warning("Document AI returned empty payload")
            return {}

        mapped = map_document_ai_payload(raw_payload)
        mapped['docai_raw_fields'] = raw_payload.get('fields')
        mapped['docai_raw_entities'] = raw_payload.get('entities')
        return validate_structured_payload(mapped)

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

    @staticmethod
    def _compute_docai_confidence(structured: Dict[str, Any]) -> Optional[float]:
        scores = structured.get('confidence_scores') if isinstance(structured, dict) else None
        if not scores:
            return None
        values = [value for value in scores.values() if isinstance(value, (int, float))]
        if not values:
            return None
        avg = sum(values) / len(values)
        return max(0.0, min(avg, 1.0))

    @staticmethod
    def _estimate_standard_confidence(text_sources: Dict[str, str], attempts: List[str]) -> Optional[float]:
        standard_attempts = [engine for engine in attempts if engine != 'document_ai']
        if not standard_attempts:
            return None
        successes = sum(
            1 for engine in standard_attempts
            if text_sources.get(engine) and text_sources.get(engine).strip()
        )
        return successes / len(standard_attempts)

    def _run_parallel_text_engines_fast(self, image_data: bytes, engines: List[Tuple[str, Any]]) -> Tuple[Dict[str, str], List[str]]:
        """Execute multiple OCR engines concurrently with early termination for speed."""
        if not engines:
            return {}, []

        texts: Dict[str, str] = {}
        attempted: List[str] = []

        future_map = {}
        start_time = time.perf_counter()
        
        logger.info(f"Starting {len(engines)} OCR engines in parallel with {self.parallel_timeout}s timeout")
        
        for engine_name, engine_func in engines:
            attempted.append(engine_name)
            future = self.parallel_executor.submit(engine_func, image_data)
            future_map[future] = engine_name

        # Wait for completion with reduced timeout for speed
        completed, pending = wait(set(future_map.keys()), timeout=self.parallel_timeout, return_when=ALL_COMPLETED)

        for future in completed:
            engine_name = future_map[future]
            try:
                engine_text = future.result()
                if engine_text and len(engine_text.strip()) > 10:
                    texts[engine_name] = engine_text
                    logger.info(f"{engine_name} produced text ({len(engine_text)} chars)")
                else:
                    logger.info(f"{engine_name} returned insufficient text")
            except Exception as exc:
                logger.error(f"{engine_name} failed: {exc}")

        # Cancel pending futures to save resources
        for future in pending:
            engine_name = future_map[future]
            future.cancel()
            logger.warning(f"{engine_name} timed out after {self.parallel_timeout}s")

        elapsed = time.perf_counter() - start_time
        logger.info(f"Parallel OCR completed in {elapsed:.2f}s, {len(texts)} engines succeeded")

        return texts, attempted

    def _run_parallel_text_engines(self, image_data: bytes, engines: List[Tuple[str, Any]]) -> Tuple[Dict[str, str], List[str]]:
        """Execute multiple OCR engines concurrently to minimize end-to-end latency."""
        if not engines:
            return {}, []

        texts: Dict[str, str] = {}
        attempted: List[str] = []

        future_map = {}
        start_time = time.perf_counter()
        for engine_name, engine_func in engines:
            attempted.append(engine_name)
            future = self.parallel_executor.submit(engine_func, image_data)
            future_map[future] = engine_name

        completed, pending = wait(set(future_map.keys()), timeout=self.parallel_timeout, return_when=ALL_COMPLETED)

        for future in completed:
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

        if pending:
            elapsed = round(time.perf_counter() - start_time, 2)
            for future in pending:
                engine_name = future_map[future]
                cancelled = future.cancel()
                logger.warning(
                    f"{engine_name} timed out after {elapsed}s (timeout {self.parallel_timeout}s). Cancelled={cancelled}"
                )

        return texts, attempted

def create_enhanced_ocr() -> MultiEngineOCR:
    """Factory function to create OCR instance"""
    return MultiEngineOCR()