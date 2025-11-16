"""
Enhanced Field Extractor with Document AI Support
Combines Document AI structured extraction with pattern-based fallback
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.extractors.field_extractors import FieldExtractor

logger = logging.getLogger(__name__)

class EnhancedFieldExtractor:
    """Enhanced field extractor with Document AI integration"""
    
    def __init__(self):
        # Initialize base field extractor for fallback
        self.base_extractor = FieldExtractor()
        logger.info("Enhanced field extractor with Document AI support initialized")
        self.vendor_overrides = self._load_vendor_overrides()
        self.vendor_lookup = self._build_vendor_lookup(self.vendor_overrides)
    
    def extract_fields_with_document_ai(self, structured_data: Dict[str, Any], raw_text: str = None) -> Dict[str, Any]:
        """
        Extract fields using Document AI structured data with pattern-based fallback
        
        Args:
            structured_data: Document AI structured response
            raw_text: Raw OCR text for fallback
            
        Returns:
            Dict with extracted fields
        """
        logger.info("Extracting fields using Document AI + pattern fallback")
        
        # Initialize result with defaults
        result = {
            'date': '',
            'vendor': '',
            'total': '',
            'invoice_number': '',
            'tax_category': '',
            'account_title': '',
            'confidence': 0,
            'subtotal': '',
            'tax': '',
            'currency': 'JPY'
        }
        
        field_confidence: Dict[str, Dict[str, Any]] = {}

        # Use Document AI entities first
        entities = structured_data.get('entities', {})
        confidence_scores = structured_data.get('confidence_scores', {})

        # Extract fields from Document AI
        doc_ai_fields, doc_ai_confidence = self._extract_from_document_ai(entities, confidence_scores)
        result.update(doc_ai_fields)
        field_confidence.update(doc_ai_confidence)
        
        # Calculate overall confidence from Document AI
        if confidence_scores:
            avg_confidence = sum(confidence_scores.values()) / len(confidence_scores)
            result['confidence'] = int(avg_confidence * 100)
        
        # Fallback to pattern-based extraction for missing fields
        fallback_text = raw_text or structured_data.get('raw_text', '')
        if fallback_text:
            pattern_fields = self.base_extractor._parse_receipt_text(fallback_text)

            # Fill in missing fields without re-running OCR
            for key, value in pattern_fields.items():
                if not result.get(key) and value:
                    result[key] = value
                    field_confidence[key] = {
                        'source': 'pattern_fallback',
                        'confidence': 0.45
                    }
                    logger.info(f"Used pattern fallback for {key}: {value}")
        
        # Enhanced total extraction with multiple strategies
        if not result.get('total') or result['total'] in ['', '0']:
            total_value, total_source = self._extract_total_enhanced(structured_data, raw_text)
            if total_value:
                result['total'] = total_value
                field_confidence['total'] = {
                    'source': total_source,
                    'confidence': 0.65 if 'document_ai' in total_source else 0.5
                }
        
        # Enhanced vendor extraction
        if not result.get('vendor'):
            vendor_value, vendor_source = self._extract_vendor_enhanced(structured_data, raw_text)
            if vendor_value:
                result['vendor'] = vendor_value
                field_confidence['vendor'] = {
                    'source': vendor_source,
                    'confidence': 0.6
                }
        
        # Enhanced date extraction
        if not result.get('date'):
            date_value, date_source = self._extract_date_enhanced(structured_data, raw_text)
            if date_value:
                result['date'] = date_value
                field_confidence['date'] = {
                    'source': date_source,
                    'confidence': 0.6
                }

        self._apply_vendor_overrides(result, field_confidence)

        result['field_confidence'] = field_confidence
        
        logger.info(f"Final extracted fields: {result}")
        return result
    
    def _extract_from_document_ai(self, entities: Dict[str, Any], confidence_scores: Dict[str, float]) -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]]]:
        """Extract fields from Document AI entities"""
        result = {}
        confidence_details: Dict[str, Dict[str, Any]] = {}
        
        # Map Document AI entity types to our field names
        entity_mapping = {
            'total_amount': 'total',
            'net_amount': 'total',
            'total': 'total',
            'supplier_name': 'vendor',
            'vendor_name': 'vendor',
            'merchant_name': 'vendor',
            'invoice_date': 'date',
            'receipt_date': 'date',
            'date': 'date',
            'invoice_id': 'invoice_number',
            'receipt_id': 'invoice_number',
            'document_id': 'invoice_number',
            'subtotal_amount': 'subtotal',
            'tax_amount': 'tax',
            'vat_amount': 'tax'
        }
        
        for entity_type, entity_data in entities.items():
            field_name = entity_mapping.get(entity_type)
            if field_name:
                if isinstance(entity_data, dict):
                    text_value = entity_data.get('text', '')
                else:
                    text_value = str(entity_data)
                
                # Clean and format the value
                cleaned_value = self._clean_field_value(field_name, text_value)
                if cleaned_value:
                    result[field_name] = cleaned_value
                    confidence_details[field_name] = {
                        'source': 'document_ai',
                        'confidence': confidence_scores.get(entity_type, 0.8)
                    }
                    logger.info(f"Document AI extracted {field_name}: {cleaned_value}")
        
        return result, confidence_details
    
    def _clean_field_value(self, field_name: str, value: str) -> str:
        """Clean and format field values"""
        if not value:
            return ''
        
        if field_name == 'total':
            # Extract numeric value from total
            return self._clean_amount(value)
        elif field_name == 'date':
            # Format date consistently
            return self._format_date(value)
        elif field_name in ['tax', 'subtotal']:
            # Clean monetary amounts
            return self._clean_amount(value)
        else:
            # General cleaning
            return value.strip()
    
    def _clean_amount(self, amount_str: str) -> str:
        """Clean monetary amount string to extract numeric value"""
        if not amount_str:
            return ''
        
        # Remove currency symbols and formatting
        cleaned = re.sub(r'[¥$€£,\s]', '', amount_str)
        
        # Extract numbers (including decimals)
        numbers = re.findall(r'\d+\.?\d*', cleaned)
        if numbers:
            # Take the largest number (likely the total)
            largest = max(numbers, key=lambda x: float(x) if '.' in x else int(x))
            return largest
        
        return ''
    
    def _format_date(self, date_str: str) -> str:
        """Format date string consistently"""
        if not date_str:
            return ''
        
        # Try to parse and reformat date
        date_patterns = [
            r'(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})',
            r'(\d{4})-(\d{2})-(\d{2})',
            r'(\d{2})/(\d{2})/(\d{4})'
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, date_str)
            if match:
                try:
                    if len(match.group(1)) == 4:  # YYYY-MM-DD format
                        year, month, day = match.groups()
                    else:  # MM/DD/YYYY format
                        month, day, year = match.groups()
                    
                    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                except:
                    continue
        
        return date_str.strip()
    
    def _extract_total_enhanced(self, structured_data: Dict[str, Any], raw_text: str = None) -> Tuple[str, str]:
        """Enhanced total extraction with multiple strategies"""
        
        # Strategy 1: Document AI totals
        totals = structured_data.get('totals', {})
        if totals.get('total'):
            amount = self._clean_amount(str(totals['total']))
            if amount and amount != '0':
                logger.info(f"Found total from Document AI totals: {amount}")
                return amount, 'document_ai_totals'
        
        # Strategy 2: Look for highest confidence total in entities
        entities = structured_data.get('entities', {})
        confidence_scores = structured_data.get('confidence_scores', {})
        
        total_candidates = []
        for key, entity in entities.items():
            if 'total' in key.lower() or 'amount' in key.lower():
                text = entity.get('text', '') if isinstance(entity, dict) else str(entity)
                confidence = confidence_scores.get(key, 0)
                amount = self._clean_amount(text)
                if amount and amount != '0':
                    total_candidates.append((amount, confidence))
        
        if total_candidates:
            # Sort by confidence and take the best
            best_total = max(total_candidates, key=lambda x: x[1])
            logger.info(f"Found total from Document AI entities: {best_total[0]} (confidence: {best_total[1]})")
            return best_total[0], 'document_ai_entities'
        
        # Strategy 2: Pattern-based fallback
        if raw_text:
            # Use a simple pattern-based total extraction
            total_patterns = [
                r'合計[\s\D]*?¥?([0-9,]+)',
                r'計[\s\D]*?¥?([0-9,]+)', 
                r'小計[\s\D]*?¥?([0-9,]+)',
                r'¥([0-9,]+)',
                r'([0-9,]+)円'
            ]
            
            for pattern in total_patterns:
                matches = re.findall(pattern, raw_text)
                if matches:
                    # Get the largest number found
                    amounts = []
                    for match in matches:
                        try:
                            amount = int(match.replace(',', ''))
                            if amount > 50:  # Reasonable minimum for receipt total
                                amounts.append(amount)
                        except:
                            continue
                    
                    if amounts:
                        best_total = str(max(amounts))
                        logger.info(f"Found total from pattern matching: {best_total}")
                        return best_total, 'pattern_total'
        
        logger.warning("No total found with any strategy")
        return '', ''
    
    def _extract_vendor_enhanced(self, structured_data: Dict[str, Any], raw_text: str = None) -> Tuple[str, str]:
        """Enhanced vendor extraction"""
        
        # Strategy 1: Document AI entities
        entities = structured_data.get('entities', {})
        vendor_keys = ['supplier_name', 'vendor_name', 'merchant_name', 'vendor']
        
        for key in vendor_keys:
            if key in entities:
                entity = entities[key]
                vendor = entity.get('text', '') if isinstance(entity, dict) else str(entity)
                if vendor and vendor.strip():
                    logger.info(f"Found vendor from Document AI: {vendor}")
                    return vendor.strip(), 'document_ai_vendor'
        
        # Strategy 2: Pattern-based fallback
        if raw_text:
            # Simple vendor extraction patterns
            vendor_patterns = [
                r'(.*店)',  # Ends with 店
                r'(.*市場)',  # Ends with 市場  
                r'(.*スーパー)',  # Ends with スーパー
                r'([^\n]+食堂)',  # Ends with 食堂
                r'(ドン・キホーテ[^\n]*)',  # Don Quijote variations
                r'(セブン-イレブン[^\n]*)',  # 7-Eleven variations
            ]
            
            for pattern in vendor_patterns:
                match = re.search(pattern, raw_text)
                if match:
                    vendor = match.group(1).strip()
                    if vendor and len(vendor) > 1:
                        logger.info(f"Found vendor from pattern matching: {vendor}")
                        return vendor, 'pattern_vendor'
        
        return '', ''
    
    def _extract_date_enhanced(self, structured_data: Dict[str, Any], raw_text: str = None) -> Tuple[str, str]:
        """Enhanced date extraction"""
        
        # Strategy 1: Document AI entities
        entities = structured_data.get('entities', {})
        date_keys = ['invoice_date', 'receipt_date', 'date']
        
        for key in date_keys:
            if key in entities:
                entity = entities[key]
                date_str = entity.get('text', '') if isinstance(entity, dict) else str(entity)
                if date_str:
                    formatted_date = self._format_date(date_str)
                    if formatted_date:
                        logger.info(f"Found date from Document AI: {formatted_date}")
                        return formatted_date, 'document_ai_date'
        
        # Strategy 2: Pattern-based fallback
        if raw_text:
            # Simple date extraction patterns
            date_patterns = [
                r'(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})',
                r'(\d{4})-(\d{2})-(\d{2})',
                r'(\d{2})/(\d{2})/(\d{4})'
            ]
            
            for pattern in date_patterns:
                match = re.search(pattern, raw_text)
                if match:
                    try:
                        if len(match.group(1)) == 4:  # YYYY-MM-DD format
                            year, month, day = match.groups()
                        else:  # MM/DD/YYYY format
                            month, day, year = match.groups()
                        
                        formatted_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                        logger.info(f"Found date from pattern matching: {formatted_date}")
                        return formatted_date, 'pattern_date'
                    except:
                        continue
        
        return '', ''

    def _load_vendor_overrides(self) -> List[Dict[str, Any]]:
        config_path = Path(__file__).resolve().parents[2] / 'config' / 'vendor_overrides.json'
        if not config_path.exists():
            return []
        try:
            with open(config_path, 'r', encoding='utf-8') as handle:
                return json.load(handle)
        except Exception as exc:
            logger.warning(f"Failed to load vendor overrides: {exc}")
            return []

    def _build_vendor_lookup(self, overrides: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        lookup: Dict[str, Dict[str, Any]] = {}
        for entry in overrides:
            aliases = entry.get('aliases', [])
            canonical = entry.get('canonical_name')
            for alias in aliases:
                key = self._normalize_vendor_key(alias)
                if key:
                    lookup[key] = {
                        'canonical_name': canonical,
                        'default_account_title': entry.get('default_account_title')
                    }
        return lookup

    def _normalize_vendor_key(self, vendor_name: Optional[str]) -> Optional[str]:
        if not vendor_name:
            return None
        normalized = vendor_name.replace(' ', '').replace('-', '').lower()
        return normalized

    def _apply_vendor_overrides(self, result: Dict[str, Any], field_confidence: Dict[str, Dict[str, Any]]):
        vendor = result.get('vendor')
        key = self._normalize_vendor_key(vendor)
        if not key:
            return
        override = self.vendor_lookup.get(key)
        if not override:
            return

        canonical_name = override.get('canonical_name')
        if canonical_name:
            result['vendor'] = canonical_name
            field_confidence['vendor'] = {
                'source': 'vendor_override',
                'confidence': 0.8
            }

        default_account = override.get('default_account_title')
        if default_account and not result.get('account_title'):
            result['account_title'] = default_account
            field_confidence['account_title'] = {
                'source': 'vendor_override',
                'confidence': 0.7
            }