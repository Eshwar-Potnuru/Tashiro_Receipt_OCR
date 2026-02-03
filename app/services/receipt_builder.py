"""ReceiptBuilder: construct canonical Receipt objects from OCR outputs."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4

from datetime import datetime
import re
import logging

from app.models.schema import ExtractionResult, Receipt
from app.services.config_service import ConfigService

logger = logging.getLogger(__name__)


def _extract_entity_text(entities: Dict[str, Any], field_name: str) -> Optional[str]:
    """Extract text value from entities dict for a given field."""
    entity = entities.get(field_name)
    if isinstance(entity, dict):
        return entity.get("text") or entity.get("value")
    elif isinstance(entity, str):
        return entity
    return None


def _extract_entity_confidence(confidence_scores: Dict[str, float], field_name: str) -> Optional[float]:
    """Extract confidence score for a given field."""
    return confidence_scores.get(field_name)


def _sanitize_iso_date(value: Any) -> Optional[str]:
    """Return ISO 8601 date (YYYY-MM-DD) or None if not parseable.

    Accepts common OCR artifacts like strings with non-digit separators or invalid year/month/day.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, str):
        candidate = value.strip()
        # Normalize full-width digits and separators
        trans = str.maketrans({
            "／": "/",
            "－": "-",
            "ー": "-",
            "―": "-",
            "―": "-",
            "　": " ",
        })
        candidate = candidate.translate(trans)
        # Remove common time-only tokens and trailing garbage (e.g., "20時01分000101")
        candidate = re.sub(r"\d+時\d+分.*$", "", candidate)
        # Look for Japanese date patterns first: 2025年 7月2日
        m = re.search(r"(?P<y>\d{4})\D+(?P<m>\d{1,2})\D+(?P<d>\d{1,2})", candidate)
        if m:
            try:
                y = int(m.group("y"))
                mm = int(m.group("m"))
                dd = int(m.group("d"))
                return datetime(y, mm, dd).date().isoformat()
            except Exception:
                pass

        # Replace slashes and dots with hyphens for ISO-like parsing
        candidate2 = candidate.replace("/", "-").replace(".", "-")
        # Trim any leading/trailing non-digit/non-hyphen chars
        while candidate2 and not candidate2[0].isdigit():
            candidate2 = candidate2[1:]
        while candidate2 and not candidate2[-1].isdigit():
            candidate2 = candidate2[:-1]

        # Try common YYYY-MM-DD or YYYY-M-D formats
        m2 = re.search(r"(?P<y>\d{4})[-\s]*(?P<m>\d{1,2})[-\s]*(?P<d>\d{1,2})", candidate2)
        if m2:
            try:
                y = int(m2.group("y"))
                mm = int(m2.group("m"))
                dd = int(m2.group("d"))
                return datetime(y, mm, dd).date().isoformat()
            except Exception:
                pass

        # Fallback: attempt ISO parsing
        try:
            return datetime.fromisoformat(candidate2).date().isoformat()
        except Exception:
            return None
    return None


def _parse_amount(value: Any) -> Optional[float]:
    """Parse amount value, removing currency symbols and handling various formats.
    
    Handles:
    - Currency symbols: ¥, ￥, 円, $, €, £
    - Thousands separators: comma
    - Japanese/Chinese numerals and markers
    - Already numeric values (int, float)
    
    Returns None if value cannot be parsed.
    """
    if value is None:
        return None
    
    # Already numeric
    if isinstance(value, (int, float)):
        return float(value)
    
    # Convert to string and clean
    try:
        s = str(value).strip()
        # Remove currency symbols and Japanese markers
        s = s.replace("¥", "").replace("￥", "").replace("円", "")
        s = s.replace("$", "").replace("€", "").replace("£", "")
        # Remove thousands separators
        s = s.replace(",", "")
        # Remove any remaining non-numeric characters except decimal point
        s = re.sub(r"[^0-9.]", "", s)
        
        if s == "":
            return None
            
        return float(s)
    except (ValueError, TypeError):
        return None


def _safe_dict(val: Any) -> Dict[str, Any]:
    """Return a dict for the given value or empty dict if None/invalid."""
    if isinstance(val, dict):
        return val
    return {}


class ReceiptBuilder:
    """Build ExtractionResult from various OCR sources.

    Public entrypoints are intentionally thin; they will be expanded with real
    mapping/merge logic in subsequent steps.
    """

    def build_from_standard_ocr(
        self,
        ocr_payload: Dict[str, Any],
        *,
        raw_text: Optional[str] = None,
        processing_time_ms: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExtractionResult:
        """Construct an ExtractionResult from the standard OCR stack.

        Parameters
        ----------
        ocr_payload: dict
            Raw structured data from the standard OCR pipeline (e.g., merged fields, confidences).
        raw_text: str | None
            Full text content if available.
        processing_time_ms: int | None
            End-to-end processing time in milliseconds if available.
        metadata: dict | None
            Optional request/context metadata for future use.
        """
        payload: Dict[str, Any] = ocr_payload or {}

        # Prefer direct fields, then fall back to common nested containers used by the standard stack.
        structured: Dict[str, Any] = (
            payload.get("structured_data")
            or payload.get("entities")
            or {}
        )

        # Raw text preference: explicit arg > payload > structured blob.
        raw_text_value = raw_text or payload.get("raw_text") or structured.get("raw_text") or ""

        # Compute processing_time_ms if not provided, using standard timing keys (queue_wait + ocr + field_extractor in seconds).
        if processing_time_ms is None:
            timings = (payload.get("diagnostics") or {}).get("timings") or {}
            if timings:
                processing_time_ms = round(
                    (timings.get("queue_wait", 0.0)
                     + timings.get("ocr", 0.0)
                     + timings.get("field_extractor", 0.0))
                    * 1000
                )
            else:
                processing_time_ms = payload.get("processing_time_ms") or 0

        line_items = payload.get("line_items") or structured.get("line_items") or []
        fields_confidence = payload.get("fields_confidence") or structured.get("fields_confidence") or {}
        if isinstance(fields_confidence, dict):
            fields_confidence = {
                k: (v.get("confidence") if isinstance(v, dict) else v)
                for k, v in fields_confidence.items()
                if (not isinstance(v, dict)) or (isinstance(v.get("confidence"), (int, float))) or isinstance(v, (int, float))
            }
        if isinstance(fields_confidence, dict):
            fields_confidence = {
                k: (v.get("confidence") if isinstance(v, dict) else v)
                for k, v in fields_confidence.items()
                if (not isinstance(v, dict)) or (isinstance(v.get("confidence"), (int, float))) or isinstance(v, (int, float))
            }

        # Extract entities and confidence scores
        entities = structured.get("entities", {})
        confidence_scores = structured.get("confidence_scores", {})

        # Extract field values from entities
        vendor_raw = _extract_entity_text(entities, "vendor")
        date = _extract_entity_text(entities, "date")
        invoice_number = _extract_entity_text(entities, "invoice_number")
        currency = _extract_entity_text(entities, "currency")
        subtotal = _extract_entity_text(entities, "subtotal")
        tax = _extract_entity_text(entities, "tax")
        total = _extract_entity_text(entities, "total")

        # Fallback to direct payload fields if entities don't have them
        vendor_raw = vendor_raw or payload.get("vendor") or structured.get("vendor")
        
        # ENHANCED VENDOR FILTERING (same as Document AI)
        vendor = None
        generic_headers = ["領収書", "レシート", "Receipt", "RECEIPT", "領収証", "お会計票", "ご利用明細"]
        
        if vendor_raw and vendor_raw not in generic_headers:
            vendor = vendor_raw
        
        # If vendor is generic or missing, extract real company from raw text
        if not vendor or vendor in generic_headers:
            if raw_text_value:
                # Pattern 1: 株式会社 (Corporation)
                corp_match = re.search(r'([^\s]+株式会社|株式会社[^\s]+)', raw_text_value)
                if corp_match:
                    vendor = corp_match.group(1)
                
                # Pattern 2: Store name patterns
                if not vendor or vendor in generic_headers:
                    store_patterns = [
                        r'((?:MEGA)?ドン・キホーテ[^\n]+店)',
                        r'(ローソン[^\n]+店?)',
                        r'(セブン(?:-)?イレブン[^\n]+店?)',
                        r'(ファミリーマート[^\n]+店?)',
                        r'([^\n]*郵便局)',
                        r'(イオン[^\n]+店?)',
                        r'(マルエツ[^\n]+店?)',
                        r'([^\s]+(?:スーパー|ストア|マート)[^\n]*)',
                    ]
                    for pattern in store_patterns:
                        match = re.search(pattern, raw_text_value)
                        if match:
                            vendor = match.group(1).strip()
                            break
                
                # Pattern 3: Extract from T-number line
                if not vendor or vendor in generic_headers:
                    t_number_match = re.search(r'([^\n]+)\n[^\n]*登録番号\s*T\d+', raw_text_value)
                    if t_number_match:
                        potential_vendor = t_number_match.group(1).strip()
                        if potential_vendor and potential_vendor not in generic_headers and len(potential_vendor) > 3:
                            vendor = potential_vendor
        
        date = date or payload.get("date") or structured.get("date")
        invoice_number = invoice_number or payload.get("invoice_number") or structured.get("invoice_number")
        currency = currency or payload.get("currency") or structured.get("currency")
        subtotal = subtotal or payload.get("subtotal") or structured.get("subtotal")
        tax = tax or payload.get("tax") or structured.get("tax")
        total = total or payload.get("total") or structured.get("total")

        # Build confidence dict from entities
        if not fields_confidence:
            fields_confidence = {}
            for field in ["vendor", "date", "invoice_number", "currency", "subtotal", "tax", "total"]:
                conf = _extract_entity_confidence(confidence_scores, field)
                if conf is not None:
                    fields_confidence[field] = conf

        # Extract categorization fields from entities
        expense_category = _extract_entity_text(entities, "account_title")
        expense_confidence = _extract_entity_confidence(confidence_scores, "account_title") or _extract_entity_confidence(confidence_scores, "confidence")
        
        # Convert confidence percentage to 0-1 scale if needed
        if expense_confidence and expense_confidence > 1:
            expense_confidence = expense_confidence / 100.0

        # Parse numeric amounts - remove currency symbols and convert to float
        subtotal_parsed = _parse_amount(subtotal)
        tax_parsed = _parse_amount(tax)
        total_parsed = _parse_amount(total)
        
        # ENHANCED TAX EXTRACTION from raw text if missing (same as Document AI)
        if tax_parsed is None and raw_text_value:
            # Pattern 1: "(内消費税等(10%) ¥10)"
            tax_match = re.search(r'\(\s*内消費税等?\s*\(\s*(\d+)%\s*\)\s*[¥￥]?\s*([\d,]+)\s*\)', raw_text_value)
            if not tax_match:
                tax_match = re.search(r'内消費税等?\s*\(\s*(\d+)%\s*\)\s*[¥￥]?\s*([\d,]+)', raw_text_value)
            
            if tax_match:
                tax_amount_str = tax_match.group(2).replace(',', '')
                tax_parsed = float(tax_amount_str)
            
            # Pattern 2: "消費税 10% ¥10"
            if not tax_parsed:
                tax_match2 = re.search(r'消費税等?\s*(?:\d+%)?\ s*[¥￥]?\s*([\d,]+)', raw_text_value)
                if tax_match2:
                    tax_amount_str = tax_match2.group(1).replace(',', '')
                    tax_parsed = float(tax_amount_str)
            
            # Pattern 3: "課税計(10%) ¥110" - calculate tax from taxed amount
            if not tax_parsed:
                taxed_match = re.search(r'課税計\s*\(\s*(\d+)%\s*\)\s*[¥￥]?\s*([\d,]+)', raw_text_value)
                if taxed_match and total_parsed:
                    tax_rate = int(taxed_match.group(1)) / 100
                    taxed_amount = float(taxed_match.group(2).replace(',', ''))
                    tax_parsed = round(taxed_amount * tax_rate / (1 + tax_rate), 2)
        
        # ENHANCED TOTAL AMOUNT EXTRACTION for Japanese receipts (same as Document AI)
        if total_parsed is None and raw_text_value:
            # Pattern 1: 合計 (total)
            total_match = re.search(r'合計[\s　]*[¥￥]?\s*([\d,]+)', raw_text_value)
            if total_match:
                total_parsed = _parse_amount(total_match.group(1))
            
            # Pattern 2: お預り金額 (amount received)
            if not total_parsed:
                total_match = re.search(r'お預(?:り|かり)金額[\s　]*[¥￥]?\s*([\d,]+)', raw_text_value)
                if total_match:
                    total_parsed = _parse_amount(total_match.group(1))
            
            # Pattern 3: 合計金額 (total amount)
            if not total_parsed:
                total_match = re.search(r'合計金額[\s　]*[¥￥]?\s*([\d,]+)', raw_text_value)
                if total_match:
                    total_parsed = _parse_amount(total_match.group(1))
            
            # Pattern 4: 総額 / 総計 (grand total)
            if not total_parsed:
                total_match = re.search(r'(?:総額|総計)[\s　]*[¥￥]?\s*([\d,]+)', raw_text_value)
                if total_match:
                    total_parsed = _parse_amount(total_match.group(1))
            
            # Pattern 5: お支払い金額 (payment amount)
            if not total_parsed:
                total_match = re.search(r'お支払い?金?額[\s　]*[¥￥]?\s*([\d,]+)', raw_text_value)
                if total_match:
                    total_parsed = _parse_amount(total_match.group(1))
            
            # Pattern 6: Total (English)
            if not total_parsed:
                total_match = re.search(r'(?:Total|TOTAL)[\s:：]*[¥￥$]?\s*([\d,]+\.?\d*)', raw_text_value, re.IGNORECASE)
                if total_match:
                    total_parsed = _parse_amount(total_match.group(1))
            
            # Pattern 7: 代金合計 (total price)
            if not total_parsed:
                total_match = re.search(r'代金合計[\s　]*[¥￥]?\s*([\d,]+)', raw_text_value)
                if total_match:
                    total_parsed = _parse_amount(total_match.group(1))
            
            # Pattern 8: Calculate from subtotal + tax
            if not total_parsed and subtotal_parsed and tax_parsed:
                expected_total = subtotal_parsed + tax_parsed
                all_amounts = re.findall(r'[¥￥]?\s*([\d,]+)', raw_text_value)
                for amt_str in all_amounts:
                    amt = _parse_amount(amt_str)
                    if amt and abs(amt - expected_total) < 1:
                        total_parsed = amt
                        break

        # TODO: Map vendor/date/currency/subtotal/tax/total/line_items from structured payload once contract is finalized.
        return ExtractionResult(
            receipt_id=uuid4(),
            vendor=vendor,
            date=_sanitize_iso_date(date),
            invoice_number=invoice_number,
            currency=currency,
            subtotal=subtotal_parsed,
            tax=tax_parsed,
            total=total_parsed,
            line_items=line_items,
            raw_text=raw_text_value,
            fields_confidence=fields_confidence,
            verified=False,
            verification_issues=[],
            processing_time_ms=processing_time_ms,
            engine_used="standard",
            confidence_standard=payload.get("confidence_standard") or structured.get("confidence_standard"),
            confidence_docai=None,
            docai_raw_entities=None,
            docai_raw_fields=None,
            merged_fields=payload.get("entities") or structured.get("entities"),
            merge_strategy=payload.get("merge_strategy") or structured.get("merge_strategy") or "standard_only",
            overall_confidence=payload.get("confidence_standard") or structured.get("confidence_standard"),
            confidence_source="standard",
            expense_category=expense_category,
            expense_confidence=expense_confidence,
        )

    def build_from_document_ai(
        self,
        docai_payload: Dict[str, Any],
        *,
        raw_text: Optional[str] = None,
        processing_time_ms: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExtractionResult:
        """Construct an ExtractionResult from Document AI output.

        Maps canonical fields from Document AI payloads; missing fields are allowed.
        TODO: tighten mapping once Document AI contract stabilizes (line items, currency hints, etc.).
        """
        payload: Dict[str, Any] = docai_payload or {}

        # Prefer direct fields, then nested docai structures.
        structured: Dict[str, Any] = (
            payload.get("structured_data")
            or payload.get("entities")
            or {}
        )

        # Raw text preference: explicit arg > payload > structured blob.
        raw_text_value = raw_text or payload.get("raw_text") or structured.get("raw_text") or ""

        # Compute processing_time_ms if not provided, using the same timing keys (seconds -> ms).
        if processing_time_ms is None:
            timings = (payload.get("diagnostics") or {}).get("timings") or {}
            if timings:
                processing_time_ms = round(
                    (timings.get("queue_wait", 0.0)
                     + timings.get("ocr", 0.0)
                     + timings.get("field_extractor", 0.0))
                    * 1000
                )
            else:
                processing_time_ms = payload.get("processing_time_ms") or 0

        line_items = payload.get("line_items") or structured.get("line_items") or []
        fields_confidence = payload.get("fields_confidence") or structured.get("fields_confidence") or {}
        if isinstance(fields_confidence, dict):
            fields_confidence = {
                k: (v.get("confidence") if isinstance(v, dict) else v)
                for k, v in fields_confidence.items()
                if (not isinstance(v, dict)) or (isinstance(v.get("confidence"), (int, float))) or isinstance(v, (int, float))
            }

        # Extract entities - Document AI returns entities in canonical format
        # e.g., {"vendor": {"text": "店名", "confidence": 0.9}, "total": {"text": "110", "confidence": 0.85}}
        entities = structured.get("entities", {})
        
        # Helper to extract text from entity dict or return as-is if string
        def _extract_entity_text(entity):
            if entity is None:
                return None
            if isinstance(entity, dict):
                return entity.get("text") or entity.get("value")
            return str(entity) if entity else None
        
        # Extract canonical field values from entities
        vendor_raw = _extract_entity_text(entities.get("vendor")) or payload.get("vendor") or structured.get("vendor")
        
        # ENHANCED VENDOR FILTERING: Exclude generic receipt headers
        vendor = None
        generic_headers = ["領収書", "レシート", "Receipt", "RECEIPT", "領収証", "お会計票", "ご利用明細"]
        
        logger.info(f"Document AI vendor extraction - raw: {vendor_raw}, is_generic: {vendor_raw in generic_headers if vendor_raw else False}")
        logger.info(f"Raw text available: {len(raw_text_value)} characters")
        
        if vendor_raw and vendor_raw not in generic_headers:
            vendor = vendor_raw
            logger.info(f"Using raw vendor (not generic): {vendor}")
        
        # If vendor is generic or missing, try to extract real company name from raw text
        if not vendor or vendor in generic_headers:
            if raw_text_value:
                # Pattern 1: Look for 株式会社 (Corporation)
                corp_match = re.search(r'([^\s]+株式会社|株式会社[^\s]+)', raw_text_value)
                if corp_match:
                    vendor = corp_match.group(1)
                    logger.info(f"Extracted corporation vendor: {vendor}")
                
                # Pattern 2: Look for store names with specific patterns
                if not vendor or vendor in generic_headers:
                    # Common patterns: MEGAドン・キホーテ, ローソン, セブンイレブン, etc.
                    store_patterns = [
                        r'((?:MEGA)?ドン・キホーテ[^\n]+店)',
                        r'(ローソン[^\n]+店?)',
                        r'(セブン(?:-)?イレブン[^\n]+店?)',
                        r'(ファミリーマート[^\n]+店?)',
                        r'([^\n]*郵便局)',
                        r'(イオン[^\n]+店?)',
                        r'(マルエツ[^\n]+店?)',
                        r'([^\s]+(?:スーパー|ストア|マート)[^\n]*)',
                    ]
                    for pattern in store_patterns:
                        match = re.search(pattern, raw_text_value)
                        if match:
                            vendor = match.group(1).strip()
                            logger.info(f"Extracted store vendor: {vendor}")
                            break
                
                # Pattern 3: Extract from "登録番号 T###" line (usually company is nearby)
                if not vendor or vendor in generic_headers:
                    # Look for lines before the T-number registration
                    t_number_match = re.search(r'([^\n]+)\n[^\n]*登録番号\s*T\d+', raw_text_value)
                    if t_number_match:
                        potential_vendor = t_number_match.group(1).strip()
                        # Filter out common non-vendor lines
                        if potential_vendor and potential_vendor not in generic_headers and len(potential_vendor) > 3:
                            vendor = potential_vendor
                            logger.info(f"Extracted vendor near T-number: {vendor}")
        
        date = _extract_entity_text(entities.get("date")) or payload.get("date") or structured.get("date")
        invoice_number = _extract_entity_text(entities.get("invoice_number")) or payload.get("invoice_number") or structured.get("invoice_number")
        currency = _extract_entity_text(entities.get("currency")) or payload.get("currency") or structured.get("currency")
        subtotal = _extract_entity_text(entities.get("subtotal")) or payload.get("subtotal") or structured.get("subtotal")
        tax = _extract_entity_text(entities.get("tax")) or payload.get("tax") or structured.get("tax")
        total = _extract_entity_text(entities.get("total")) or payload.get("total") or structured.get("total")

        # Parse numeric amounts to remove currency symbols
        subtotal_parsed = _parse_amount(subtotal)
        tax_parsed = _parse_amount(tax)
        total_parsed = _parse_amount(total)
        
        # ENHANCED TOTAL AMOUNT EXTRACTION for Japanese receipts
        if total_parsed is None and raw_text_value:
            # Pattern 1: 合計 (total) - most common
            total_match = re.search(r'合計[\s　]*[¥￥]?\s*([\d,]+)', raw_text_value)
            if total_match:
                total_parsed = _parse_amount(total_match.group(1))
                logger.info(f"Extracted total from 合計: ¥{total_parsed}")
            
            # Pattern 2: お預り金額 / お預かり金額 (amount received)
            if not total_parsed:
                total_match = re.search(r'お預(?:り|かり)金額[\s　]*[¥￥]?\s*([\d,]+)', raw_text_value)
                if total_match:
                    total_parsed = _parse_amount(total_match.group(1))
                    logger.info(f"Extracted total from お預り金額: ¥{total_parsed}")
            
            # Pattern 3: 合計金額 (total amount)
            if not total_parsed:
                total_match = re.search(r'合計金額[\s　]*[¥￥]?\s*([\d,]+)', raw_text_value)
                if total_match:
                    total_parsed = _parse_amount(total_match.group(1))
                    logger.info(f"Extracted total from 合計金額: ¥{total_parsed}")
            
            # Pattern 4: 総額 / 総計 (grand total)
            if not total_parsed:
                total_match = re.search(r'(?:総額|総計)[\s　]*[¥￥]?\s*([\d,]+)', raw_text_value)
                if total_match:
                    total_parsed = _parse_amount(total_match.group(1))
                    logger.info(f"Extracted total from 総額/総計: ¥{total_parsed}")
            
            # Pattern 5: お支払い金額 / お支払額 (payment amount)
            if not total_parsed:
                total_match = re.search(r'お支払い?金?額[\s　]*[¥￥]?\s*([\d,]+)', raw_text_value)
                if total_match:
                    total_parsed = _parse_amount(total_match.group(1))
                    logger.info(f"Extracted total from お支払額: ¥{total_parsed}")
            
            # Pattern 6: Total / TOTAL (English)
            if not total_parsed:
                total_match = re.search(r'(?:Total|TOTAL)[\s:：]*[¥￥$]?\s*([\d,]+\.?\d*)', raw_text_value, re.IGNORECASE)
                if total_match:
                    total_parsed = _parse_amount(total_match.group(1))
                    logger.info(f"Extracted total from Total: {total_parsed}")
            
            # Pattern 7: 代金合計 (total price)
            if not total_parsed:
                total_match = re.search(r'代金合計[\s　]*[¥￥]?\s*([\d,]+)', raw_text_value)
                if total_match:
                    total_parsed = _parse_amount(total_match.group(1))
                    logger.info(f"Extracted total from 代金合計: ¥{total_parsed}")
            
            # Pattern 8: Last resort - find largest amount if subtotal and tax are available
            if not total_parsed and subtotal_parsed and tax_parsed:
                # Calculate expected total
                expected_total = subtotal_parsed + tax_parsed
                # Look for amounts close to this in text
                all_amounts = re.findall(r'[¥￥]?\s*([\d,]+)', raw_text_value)
                for amt_str in all_amounts:
                    amt = _parse_amount(amt_str)
                    if amt and abs(amt - expected_total) < 1:  # Within 1 yen
                        total_parsed = amt
                        logger.info(f"Calculated total from subtotal+tax: ¥{total_parsed}")
                        break
        
        # ENHANCED TAX EXTRACTION: Parse from raw text if entities missing
        if tax_parsed is None and raw_text_value:
            # Pattern 1: "内消費税等(10%) ¥10" or "(内消費税等(10%) ¥10)"
            tax_match = re.search(r'\(\s*内消費税等?\s*\(\s*(\d+)%\s*\)\s*[¥￥]?\s*([\d,]+)\s*\)', raw_text_value)
            if not tax_match:
                tax_match = re.search(r'内消費税等?\s*\(\s*(\d+)%\s*\)\s*[¥￥]?\s*([\d,]+)', raw_text_value)
            
            if tax_match:
                tax_rate = int(tax_match.group(1))
                tax_amount_str = tax_match.group(2).replace(',', '')
                tax_parsed = float(tax_amount_str)
                logger.info(f"Extracted tax from raw text: {tax_rate}% = ¥{tax_parsed}")
            
            # Pattern 2: "消費税 10% ¥10" or "消費税等 ¥10"
            if not tax_parsed:
                tax_match2 = re.search(r'消費税等?\s*(?:\d+%)?\s*[¥￥]?\s*([\d,]+)', raw_text_value)
                if tax_match2:
                    tax_amount_str = tax_match2.group(1).replace(',', '')
                    tax_parsed = float(tax_amount_str)
                    logger.info(f"Extracted tax from alternative pattern: ¥{tax_parsed}")
            
            # Pattern 3: "課税計(10%) ¥110" with tax embedded
            if not tax_parsed:
                taxed_match = re.search(r'課税計\s*\(\s*(\d+)%\s*\)\s*[¥￥]?\s*([\d,]+)', raw_text_value)
                if taxed_match and total_parsed:
                    tax_rate = int(taxed_match.group(1)) / 100
                    taxed_amount = float(taxed_match.group(2).replace(',', ''))
                    # Calculate tax from taxed amount
                    tax_parsed = round(taxed_amount * tax_rate / (1 + tax_rate), 2)
                    logger.info(f"Calculated tax from taxed amount: ¥{tax_parsed}")

        # --- Infer tax classification and expense category heuristics ---
        def _parse_amount_for_builder(val: any) -> Optional[float]:
            if val is None:
                return None
            try:
                s = str(val)
                s = s.replace("¥", "").replace("￥", "").replace("円", "").replace(",", "").strip()
                s = re.sub(r"[^0-9\.]", "", s)
                if s == "":
                    return None
                return float(s)
            except Exception:
                return None

        def _infer_tax_category_internal(payload: Dict[str, any], raw_text: str) -> Tuple[Optional[str], Optional[float]]:
            # Use parsed amounts for inference
            tax_val = tax_parsed or _parse_amount_for_builder(payload.get("tax") or structured.get("tax"))
            subtotal_val = subtotal_parsed or _parse_amount_for_builder(payload.get("subtotal") or structured.get("subtotal"))
            total_val = total_parsed or _parse_amount_for_builder(payload.get("total") or structured.get("total"))
            txt = (raw_text or "")
            # If explicit percent in text, use it
            m = re.search(r"(\d{1,2})\s*%", txt)
            if m:
                perc = int(m.group(1))
                if perc in (8, 10):
                    return (f"課税{perc}%", 0.9)
            # If both tax and subtotal available, compute rate
            if tax_val is not None and subtotal_val:
                if subtotal_val > 0:
                    rate = tax_val / subtotal_val
                    if abs(rate - 0.1) < 0.03:
                        return ("課税10%", 0.9)
                    if abs(rate - 0.08) < 0.03:
                        return ("課税8%", 0.9)
            # If tax present relative to total
            if tax_val is not None and total_val:
                if total_val > 0:
                    rate = tax_val / total_val
                    if abs(rate - 0.1) < 0.03:
                        return ("課税10%", 0.8)
                    if abs(rate - 0.08) < 0.03:
                        return ("課税8%", 0.8)
            # Presence of '税込' suggests tax applied but rate unknown
            if "税込" in txt or "内税" in txt:
                return ("課税(不明)", 0.5)
            return (None, None)

        def _infer_account_title_internal(vendor: Optional[str], raw_text: str) -> Tuple[Optional[str], Optional[float]]:
            v = (vendor or "")
            vl = v.lower()
            txt = (raw_text or "")
            # Convenience stores and supermarkets -> 食費
            if any(k in vl for k in ("lawson", "ローソン", "コンビニ", "セブン", "7-11", "familymart", "ファミリ", "ファミマ", "ヨーク", "イオン", "スーパー", "マルエツ", "松尾")):
                return ("食費", 0.9)
            # Restaurants/cafes
            if any(k in txt for k in ("レストラン", "定食", "居酒屋", "カフェ", "喫茶", "食堂")) or any(k in vl for k in ("restaurant", "cafe", "coffee")):
                return ("食費", 0.9)
            # Fuel/gas
            if any(k in vl for k in ("ガソリン", "出光", "エネオス", "ENEOS")) or "ガソリン" in txt:
                return ("燃料費", 0.9)
            # Postage/communication
            if "郵便" in txt or "ゆうびん" in txt:
                return ("通信費", 0.8)
            return (None, None)

        inferred_tax, tax_conf = _infer_tax_category_internal(payload, raw_text_value)
        inferred_cat, cat_conf = _infer_account_title_internal(vendor, raw_text_value)

        return ExtractionResult(
            receipt_id=uuid4(),
            vendor=vendor,
            date=_sanitize_iso_date(date),
            invoice_number=invoice_number,
            currency=currency,
            subtotal=subtotal_parsed,
            tax=tax_parsed,
            total=total_parsed,
            line_items=line_items,
            raw_text=raw_text_value,
            fields_confidence=fields_confidence,
            verified=False,
            verification_issues=[],
            processing_time_ms=processing_time_ms,
            engine_used="document_ai",
            confidence_docai=payload.get("confidence_docai") or structured.get("confidence_docai"),
            confidence_standard=None,
            docai_raw_entities=_safe_dict(payload.get("docai_raw_entities") or structured.get("docai_raw_entities")),
            docai_raw_fields=_safe_dict(payload.get("docai_raw_fields") or structured.get("docai_raw_fields")),
            merged_fields=payload.get("entities") or structured.get("entities"),
            merge_strategy=payload.get("merge_strategy") or structured.get("merge_strategy") or "docai_over_standard",
            overall_confidence=payload.get("confidence_docai") or structured.get("confidence_docai"),
            confidence_source="document_ai",
            expense_category=inferred_cat,
            expense_confidence=cat_conf,
            tax_classification=inferred_tax,
        )

    def build_auto(
        self,
        standard_result: Optional[ExtractionResult],
        docai_result: Optional[ExtractionResult],
        *,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExtractionResult:
        """Merge Document AI and Standard OCR results into one canonical ExtractionResult.

        Precedence is Document AI over Standard on a field-by-field basis; missing values are allowed.
        Merge logic is intentionally minimal and deterministic; no validation/normalization is performed here.
        """

        # Helper to prefer Document AI value when present (None means fallback to standard).
        def pick(docai_value: Any, standard_value: Any) -> Any:
            return docai_value if docai_value is not None else standard_value

        # Canonical fields with docai-over-standard precedence.
        vendor = pick(getattr(docai_result, "vendor", None), getattr(standard_result, "vendor", None))
        date = _sanitize_iso_date(pick(getattr(docai_result, "date", None), getattr(standard_result, "date", None)))
        invoice_number = pick(getattr(docai_result, "invoice_number", None), getattr(standard_result, "invoice_number", None))
        currency = pick(getattr(docai_result, "currency", None), getattr(standard_result, "currency", None))
        subtotal = pick(getattr(docai_result, "subtotal", None), getattr(standard_result, "subtotal", None))
        tax = pick(getattr(docai_result, "tax", None), getattr(standard_result, "tax", None))
        total = pick(getattr(docai_result, "total", None), getattr(standard_result, "total", None))

        # Line items: prefer docai list when populated, otherwise standard.
        docai_line_items = getattr(docai_result, "line_items", None)
        standard_line_items = getattr(standard_result, "line_items", None)
        line_items = docai_line_items if docai_line_items else (standard_line_items or [])

        # Raw text: prefer docai when available.
        raw_text = getattr(docai_result, "raw_text", None) or getattr(standard_result, "raw_text", "")

        # Processing time: prefer docai if present, else standard, else 0.
        processing_time_ms = (
            getattr(docai_result, "processing_time_ms", None)
            if docai_result and getattr(docai_result, "processing_time_ms", None) is not None
            else getattr(standard_result, "processing_time_ms", None)
        ) or 0

        # Confidence handling.
        confidence_docai = getattr(docai_result, "confidence_docai", None)
        confidence_standard = getattr(standard_result, "confidence_standard", None)
        overall_confidence = confidence_docai or confidence_standard
        confidence_source = "document_ai" if confidence_docai is not None else (
            "standard" if confidence_standard is not None else None
        )

        fields_confidence = (
            getattr(docai_result, "fields_confidence", None)
            or getattr(standard_result, "fields_confidence", None)
            or {}
        )

        merged_fields = {
            "vendor": vendor,
            "date": date,
            "invoice_number": invoice_number,
            "currency": currency,
            "subtotal": subtotal,
            "tax": tax,
            "total": total,
            "line_items": line_items,
            "raw_text": raw_text,
        }

        # Preserve tax classification and expense category from Document AI when present,
        # otherwise fall back to the standard result values.
        tax_classification = (
            getattr(docai_result, "tax_classification", None)
            or getattr(standard_result, "tax_classification", None)
        )
        expense_category = (
            getattr(docai_result, "expense_category", None)
            or getattr(standard_result, "expense_category", None)
        )
        expense_confidence = (
            getattr(docai_result, "expense_confidence", None)
            or getattr(standard_result, "expense_confidence", None)
        )

        return ExtractionResult(
            receipt_id=uuid4(),
            vendor=vendor,
            date=date,
            invoice_number=invoice_number,
            currency=currency,
            subtotal=subtotal,
            tax=tax,
            total=total,
            line_items=line_items,
            raw_text=raw_text,
            fields_confidence=fields_confidence,
            verified=False,
            verification_issues=[],
            processing_time_ms=processing_time_ms,
            engine_used="document_ai+standard",
            confidence_docai=confidence_docai,
            confidence_standard=confidence_standard,
            docai_raw_entities=getattr(docai_result, "docai_raw_entities", None),
            docai_raw_fields=getattr(docai_result, "docai_raw_fields", None),
            merged_fields=merged_fields,
            merge_strategy="docai_over_standard",
            overall_confidence=overall_confidence,
            confidence_source=confidence_source,
            # Preserve inferred classification/accounting when merging
            tax_classification=tax_classification,
            expense_category=expense_category,
            expense_confidence=expense_confidence,
        )

    # -----------------
    # Receipt mapping
    # -----------------
    def build_receipt(
        self,
        extraction: ExtractionResult,
        *,
        config_service: ConfigService,
        validation_warnings: Optional[list] = None,
        validation_errors: Optional[list] = None,
    ) -> Receipt:
        """Convert an ExtractionResult into a normalized Receipt.

        - Applies vendor overrides
        - Normalizes amounts to Decimal
        - Splits tax buckets (10% / 8%) per provided values or classification
        - Binds business_location_id and staff_id deterministically
        - Attaches validation warnings/errors
        """

        warnings = list(validation_warnings or [])
        errors = list(validation_errors or [])

        vendor_raw = extraction.vendor
        vendor_canonical = config_service.get_vendor_canonical(vendor_raw)

        receipt_date = _sanitize_iso_date(extraction.date)

        # Location normalization
        location_name = getattr(extraction, "business_unit", None) or None
        canonical_location = config_service.normalize_location(location_name)
        business_location_id = canonical_location.upper() if canonical_location else None

        # Staff binding (deterministic first match if present)
        staff_id = self._bind_staff(config_service, canonical_location)

        # Amount normalization
        _, _, total = self._normalize_amounts(
            extraction.subtotal,
            extraction.tax,
            extraction.total,
        )

        tax_10, tax_8 = self._normalize_tax_buckets(
            extraction,
            total_amount=total,
            tax_amount=self._to_decimal(extraction.tax),
        )

        # Mandatory fields check (non-blocking)
        for field_name, value in (
            ("receipt_date", receipt_date),
            ("vendor_name", vendor_canonical or vendor_raw),
            ("total_amount", total),
            ("business_location_id", business_location_id),
        ):
            if value in (None, ""):
                errors.append(f"missing_{field_name}")

        ocr_flags = list(set([*warnings, *errors])) if (warnings or errors) else []

        return Receipt(
            receipt_date=receipt_date,
            vendor_name=vendor_canonical or vendor_raw,
            invoice_number=extraction.invoice_number,
            total_amount=total,
            tax_10_amount=tax_10,
            tax_8_amount=tax_8,
            memo=None,
            business_location_id=business_location_id,
            staff_id=staff_id,
            ocr_engine=extraction.engine_used,
            ocr_confidence=extraction.overall_confidence,
            ocr_flags=ocr_flags,
            created_at=None,
            updated_at=None,
        )

    # -----------------
    # Helpers
    # -----------------
    @staticmethod
    def _to_decimal(val: Any) -> Optional[Decimal]:
        if val is None:
            return None
        if isinstance(val, Decimal):
            return val
        try:
            return Decimal(str(val))
        except Exception:
            return None

    def _normalize_amounts(
        self,
        subtotal: Any,
        tax: Any,
        total: Any,
    ) -> Tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
        subtotal_dec = self._to_decimal(subtotal)
        tax_dec = self._to_decimal(tax)
        total_dec = self._to_decimal(total)
        return subtotal_dec, tax_dec, total_dec

    def _normalize_tax_buckets(
        self,
        extraction: ExtractionResult,
        *,
        total_amount: Optional[Decimal],
        tax_amount: Optional[Decimal],
    ) -> Tuple[Optional[Decimal], Optional[Decimal]]:
        """Apply tax bucket rules: explicit > classification > None."""
        explicit_tax10 = getattr(extraction, "tax_10", None)
        explicit_tax8 = getattr(extraction, "tax_8", None)

        tax10 = self._to_decimal(explicit_tax10)
        tax8 = self._to_decimal(explicit_tax8)

        if tax10 is not None or tax8 is not None:
            return tax10, tax8

        tax_class = getattr(extraction, "tax_classification", None) or ""
        tax_class_norm = str(tax_class).lower()

        if "10" in tax_class_norm:
            return total_amount, None
        if "8" in tax_class_norm:
            return None, total_amount

        return None, None

    def _bind_staff(
        self,
        config_service: ConfigService,
        canonical_location: Optional[str],
    ) -> Optional[str]:
        if not canonical_location:
            return None
        staff_list = config_service.get_staff_for_location(canonical_location) or []
        if not staff_list:
            return None
        staff = staff_list[0]
        return staff.get("id")


__all__ = ["ReceiptBuilder"]
