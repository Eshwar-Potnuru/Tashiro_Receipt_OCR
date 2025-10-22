from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageOps

try:
    import easyocr  # type: ignore
except ImportError:  # pragma: no cover - handled via runtime guard
    easyocr = None

try:
    import pytesseract  # type: ignore
except ImportError:  # pragma: no cover - handled via runtime guard
    pytesseract = None
else:  # pragma: no cover - runtime configuration
    tess_cmd = os.environ.get("TESSERACT_CMD")
    if tess_cmd:
        pytesseract.pytesseract.tesseract_cmd = tess_cmd

logger = logging.getLogger(__name__)


@dataclass
class OCRBox:
    text: str
    box: List[List[float]]
    confidence: float


class OCREngine:
    def __init__(
        self,
        languages: Optional[List[str]] = None,
        use_gpu: bool = False,
        detector: bool = True,
        primary_engine: str = "easyocr",
        fallback_enabled: bool = True,
    ) -> None:
        # Prioritize Japanese for Tashiro Ironworks receipts
        self.languages = languages or ["ja", "en"]  # Japanese first, then English
        self.use_gpu = use_gpu
        self.detector = detector
        self.primary_engine = primary_engine.lower()
        self.fallback_enabled = fallback_enabled
        self._reader_cache: Dict[Tuple[str, ...], Any] = {}
        if pytesseract is not None:
            tess_cmd = os.environ.get("TESSERACT_CMD")
            if tess_cmd:
                pytesseract.pytesseract.tesseract_cmd = tess_cmd
        if self.primary_engine == "easyocr":
            if easyocr is None:
                logger.warning("EasyOCR not available; will attempt fallback engine.")
            else:
                self._reader_cache[tuple(self.languages)] = easyocr.Reader(self.languages, gpu=self.use_gpu, detector=self.detector)
        elif self.primary_engine == "tesseract":
            if pytesseract is None:
                logger.warning("pytesseract not available; OCR will fail unless fallback is enabled.")
        else:
            logger.warning("Unknown OCR engine '%s'; defaulting to EasyOCR if available.", primary_engine)
            if easyocr is not None:
                self.primary_engine = "easyocr"
                self._reader_cache[tuple(self.languages)] = easyocr.Reader(self.languages, gpu=self.use_gpu, detector=self.detector)
            elif pytesseract is not None:
                self.primary_engine = "tesseract"
            else:
                logger.error("No OCR engines available.")

    def _run_easyocr(self, image: Image.Image) -> List[OCRBox]:
        if easyocr is None:
            raise RuntimeError("EasyOCR reader not initialised")

        # Enhanced language strategy for Japanese receipts
        language_attempts: List[Tuple[str, ...]] = []
        base_languages = tuple(self.languages)
        
        # Try Japanese-only first for better accuracy on Japanese receipts
        if "ja" in base_languages:
            language_attempts.append(("ja",))
        
        # Then try combined languages
        language_attempts.append(base_languages)
        
        # Finally try English-only as fallback
        if "en" in base_languages and len(base_languages) > 1:
            language_attempts.append(("en",))

        best_boxes: List[OCRBox] = []
        best_score = 0.0
        
        for lang_tuple in language_attempts:
            try:
                reader = self._get_easyocr_reader(lang_tuple)
                array = np.array(image)
                
                logger.info(f"Running OCR with languages: {lang_tuple}")
                logger.info(f"Image array shape: {array.shape}")
                
                # Enhanced EasyOCR parameters optimized for Japanese receipts
                results = reader.readtext(
                    array, 
                    detail=1, 
                    paragraph=False,
                    width_ths=0.4,   # More aggressive character separation
                    height_ths=0.4,  # Better line detection for receipts
                    mag_ratio=1.8,   # Optimal for receipt text size
                    text_threshold=0.5,  # Lower threshold for faint text
                    link_threshold=0.2,  # Conservative character linking
                    low_text=0.2,    # Detect very faint text
                    slope_ths=0.1,   # Handle slight rotation
                    ycenter_ths=0.3, # Tighter line grouping
                    x_ths=0.8,       # Better horizontal text alignment
                    y_ths=0.3        # Tighter vertical text grouping
                )
                
                logger.info(f"OCR extracted {len(results)} text regions")
                
                boxes: List[OCRBox] = []
                total_confidence = 0.0
                
                logger.info("Processing OCR results...")
                for i, (box, text, confidence) in enumerate(results):
                    cleaned_text = text.strip()
                    if cleaned_text:  # Only include non-empty text
                        logger.debug(f"OCR Box {i}: '{cleaned_text}' (confidence: {confidence:.3f})")
                        boxes.append(
                            OCRBox(
                                text=cleaned_text,
                                box=[[float(x), float(y)] for x, y in box],
                                confidence=float(confidence),
                            )
                        )
                        total_confidence += confidence
                
                # Calculate average confidence as quality score
                avg_confidence = total_confidence / len(boxes) if boxes else 0.0
                
                # Prefer results with higher confidence and more detected text
                score = avg_confidence * (1 + len(boxes) * 0.1)
                
                if score > best_score:
                    best_score = score
                    best_boxes = boxes
                    
                logger.info(f"OCR attempt with {lang_tuple}: {len(boxes)} boxes, avg confidence: {avg_confidence:.3f}")
                
            except Exception as e:
                logger.warning(f"OCR failed for languages {lang_tuple}: {e}")
                continue

        return best_boxes

    def _run_tesseract(self, image: Image.Image) -> List[OCRBox]:
        if pytesseract is None:
            raise RuntimeError("Neither EasyOCR nor pytesseract are available.")
        if image.mode != "L":
            grayscale = image.convert("L")
        else:
            grayscale = image
        if grayscale.width < 900:
            scale = max(2, math.ceil(900 / grayscale.width))
            new_size = (grayscale.width * scale, grayscale.height * scale)
            grayscale = grayscale.resize(new_size, Image.Resampling.LANCZOS)
        normalized = ImageOps.autocontrast(grayscale)
        if "ja" in self.languages:
            normalized = grayscale
        lang_argument = self._build_tesseract_languages()
        config_parts = ["--psm 6"]
        if "ja" in self.languages or "jpn" in lang_argument:
            config_parts.append("--oem 1")
        config = " ".join(config_parts)
        try:
            data = pytesseract.image_to_data(
                normalized,
                output_type=pytesseract.Output.DICT,
                lang=lang_argument,
                config=config,
            )
        except pytesseract.TesseractError:
            fallback_lang = "eng" if lang_argument != "eng" else lang_argument
            data = pytesseract.image_to_data(
                normalized,
                output_type=pytesseract.Output.DICT,
                lang=fallback_lang,
                config="--psm 6",
            )

        numeric_texts: Optional[List[str]] = None
        if "ja" in self.languages:
            try:
                numeric_result = pytesseract.image_to_data(
                    normalized,
                    output_type=pytesseract.Output.DICT,
                    lang=lang_argument,
                    config="--psm 6 -c classify_bln_numeric_mode=1",
                )
                numeric_texts = numeric_result.get("text")
            except pytesseract.TesseractError:
                numeric_texts = None
        boxes: List[OCRBox] = []
        for i in range(len(data["text"])):
            text = data["text"][i].strip()
            if numeric_texts and i < len(numeric_texts):
                numeric_candidate = numeric_texts[i].strip()
                if numeric_candidate and any(ch.isdigit() for ch in numeric_candidate):
                    text = numeric_candidate
            if not text:
                continue
            conf_str = data["conf"][i]
            try:
                confidence = float(conf_str) / 100.0
            except ValueError:
                confidence = 0.0
            x, y, w, h = (data["left"][i], data["top"][i], data["width"][i], data["height"][i])
            box = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
            boxes.append(OCRBox(text=text, box=[[float(px), float(py)] for px, py in box], confidence=confidence))
        return boxes

    def extract(self, image: Image.Image) -> tuple[str, List[OCRBox]]:
        try:
            boxes = self._run_primary(image)
            if (
                self.primary_engine == "easyocr"
                and self.fallback_enabled
                and self._should_force_fallback(boxes)
            ):
                raise RuntimeError("EasyOCR output quality below threshold")
        except Exception as exc:  # pragma: no cover - fallback path
            logger.exception("Primary OCR engine '%s' failed.", self.primary_engine)
            if not self.fallback_enabled:
                raise
            boxes = self._run_fallback(image, exc)
        raw_text = "\n".join(box.text for box in boxes if box.text)
        return raw_text, boxes

    def _run_primary(self, image: Image.Image) -> List[OCRBox]:
        if self.primary_engine == "easyocr":
            return self._run_easyocr(image)
        if self.primary_engine == "tesseract":
            return self._run_tesseract(image)
        raise RuntimeError(f"Unsupported OCR engine '{self.primary_engine}'")

    def _run_fallback(self, image: Image.Image, exc: Exception) -> List[OCRBox]:
        fallback_order = [engine for engine in ["easyocr", "tesseract"] if engine != self.primary_engine]
        for engine in fallback_order:
            try:
                if engine == "easyocr":
                    return self._run_easyocr(image)
                if engine == "tesseract":
                    return self._run_tesseract(image)
            except Exception as fallback_exc:  # pragma: no cover
                logger.exception("Fallback OCR engine '%s' also failed.", engine)
                last_exception = fallback_exc
        raise RuntimeError("OCR failed using all available engines") from exc

    def _get_easyocr_reader(self, languages: Sequence[str]) -> Any:
        lang_tuple = tuple(languages)
        if lang_tuple not in self._reader_cache or self._reader_cache[lang_tuple] is None:
            if easyocr is None:
                raise RuntimeError("EasyOCR is not installed")
            logger.debug("Initialising EasyOCR reader for languages: %s", ",".join(lang_tuple))
            self._reader_cache[lang_tuple] = easyocr.Reader(list(lang_tuple), gpu=self.use_gpu, detector=self.detector)
        reader = self._reader_cache[lang_tuple]
        if reader is None:
            raise RuntimeError("Failed to initialise EasyOCR reader")
        return reader

    @staticmethod
    def _is_mostly_ascii(text: str, threshold: float = 0.65) -> bool:
        if not text:
            return False
        printable_chars = [ch for ch in text if not ch.isspace()]
        if not printable_chars:
            return False
        ascii_count = sum(1 for ch in printable_chars if ord(ch) < 128)
        ratio = ascii_count / len(printable_chars)
        return ratio >= threshold

    @staticmethod
    def _should_force_fallback(boxes: List[OCRBox]) -> bool:
        if not boxes:
            return True
        text = "".join(box.text for box in boxes if box.text)
        printable_chars = [ch for ch in text if not ch.isspace()]
        if not printable_chars:
            return True
        ascii_letters = sum(1 for ch in printable_chars if ch.isascii() and ch.isalpha())
        digits = sum(1 for ch in printable_chars if ch.isdigit())
        non_ascii = sum(1 for ch in printable_chars if not ch.isascii())

        # Japanese receipts often contain non-ASCII characters; accept smaller counts before falling back.
        if non_ascii >= 3:
            return False

        # If we barely captured any alphabetic characters but lots of digits, EasyOCR underperformed.
        if ascii_letters < 5 and digits >= max(8, ascii_letters * 2):
            return True

        return False

    def _build_tesseract_languages(self) -> str:
        mapping = {"en": "eng", "ja": "jpn"}
        languages: List[str] = []
        for lang in self.languages:
            mapped = mapping.get(lang, lang)
            if mapped not in languages:
                languages.append(mapped)
        if not languages:
            languages.append("eng")
        return "+".join(languages)
