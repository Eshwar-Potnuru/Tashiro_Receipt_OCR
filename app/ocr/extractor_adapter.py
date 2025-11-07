#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OCR Result Normalizer
Converts different OCR engine outputs to a standardized format
"""

import logging
from typing import Dict, Any, Tuple, List

logger = logging.getLogger(__name__)

def normalize_result(engine_name: str, result) -> Dict[str, Any]:
    """
    Normalize OCR results from different engines into a consistent format

    Args:
        engine_name: Name of the OCR engine ("google_vision", "openai", etc.)
        result: Raw result from the OCR engine

    Returns:
        Normalized dictionary with at least a "text" key
    """
    try:
        if engine_name == "google_vision":
            # Google Vision returns (full_text, text_annotations)
            if isinstance(result, tuple) and len(result) == 2:
                full_text, annotations = result
                return {
                    "text": full_text,
                    "annotations": annotations,
                    "engine": "google_vision",
                    "confidence": 0.95  # Google Vision typically has high confidence
                }
            else:
                logger.warning(f"Unexpected Google Vision result format: {type(result)}")
                return {
                    "text": str(result),
                    "engine": "google_vision",
                    "error": "unexpected_format"
                }

        elif engine_name == "openai":
            # OpenAI extract_from_text returns a dictionary
            if isinstance(result, dict):
                # Ensure it has a text key
                if "text" in result:
                    return {
                        "text": result["text"],
                        "structured": result.get("structured"),
                        "engine": "openai",
                        "confidence": 0.90
                    }
                elif "error" in result:
                    # Return the original text if available, otherwise the error
                    return {
                        "text": result.get("raw_response", result.get("error", "OpenAI processing failed")),
                        "engine": "openai",
                        "error": result["error"],
                        "confidence": 0.0
                    }
                else:
                    logger.warning(f"Unexpected OpenAI result format: {result}")
                    return {
                        "text": str(result),
                        "engine": "openai",
                        "error": "unexpected_format"
                    }
            else:
                logger.warning(f"OpenAI result is not a dictionary: {type(result)}")
                return {
                    "text": str(result),
                    "engine": "openai",
                    "error": "invalid_format"
                }

        elif engine_name == "ocr_space":
            # OCR.space typically returns a dictionary with ParsedResults
            if isinstance(result, dict) and "ParsedResults" in result:
                parsed = result["ParsedResults"]
                if parsed and len(parsed) > 0:
                    text = parsed[0].get("ParsedText", "")
                    return {
                        "text": text,
                        "engine": "ocr_space",
                        "confidence": 0.85
                    }
                else:
                    return {
                        "text": "",
                        "engine": "ocr_space",
                        "error": "no_parsed_results"
                    }
            else:
                logger.warning(f"Unexpected OCR.space result format: {type(result)}")
                return {
                    "text": str(result),
                    "engine": "ocr_space",
                    "error": "unexpected_format"
                }

        else:
            # Generic fallback for unknown engines
            logger.warning(f"Unknown engine: {engine_name}")
            return {
                "text": str(result),
                "engine": engine_name,
                "error": "unknown_engine"
            }

    except Exception as e:
        logger.error(f"Error normalizing result from {engine_name}: {e}")
        return {
            "text": str(result) if result else "",
            "engine": engine_name,
            "error": str(e),
            "confidence": 0.0
        }