#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Enhanced Japanese Receipt Field Extractor
Optimized for Japanese receipts with advanced OCR preprocessing, field-specific regex,
and AI-powered post-processing for maximum accuracy.
"""

import os
import re
import json
import unicodedata
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from rapidfuzz import fuzz
import logging

# Import existing extractors for fallback
try:
    from .field_extractors import FieldExtractor
    FIELD_EXTRACTOR_AVAILABLE = True
except ImportError:
    FIELD_EXTRACTOR_AVAILABLE = False

logger = logging.getLogger(__name__)


class EnhancedJapaneseExtractor:
    """
    Enhanced field extractor optimized for Japanese receipts.
    Uses structured OCR data with advanced post-processing.
    """

    def __init__(self):
        """Initialize the enhanced Japanese extractor."""
        self.vendor_database = self._load_vendor_database()
        self.field_patterns = self._initialize_field_patterns()

    def _load_vendor_database(self) -> Dict[str, str]:
        """Load vendor name database for fuzzy matching and categorization."""
        # Comprehensive Japanese vendor database
        vendor_db = {
            # Convenience Stores
            "ローソン": "convenience_store",
            "ローソンストア": "convenience_store",
            "ファミリーマート": "convenience_store",
            "ファミマ": "convenience_store",
            "セブンイレブン": "convenience_store",
            "セブン-イレブン": "convenience_store",
            "ミニストップ": "convenience_store",
            "デイリーヤマザキ": "convenience_store",
            "ヤマザキ": "convenience_store",
            "ニューデイズ": "convenience_store",
            "ポプラ": "convenience_store",

            # Restaurants & Food
            "マクドナルド": "restaurant",
            "マック": "restaurant",
            "モスバーガー": "restaurant",
            "モス": "restaurant",
            "ケンタッキー": "restaurant",
            "KFC": "restaurant",
            "ピザハット": "restaurant",
            "ピザ": "restaurant",
            "ドミノピザ": "restaurant",
            "すき家": "restaurant",
            "吉野家": "restaurant",
            "松屋": "restaurant",
            "かつや": "restaurant",
            "大戸屋": "restaurant",
            "くら寿司": "restaurant",
            "スシロー": "restaurant",
            "はま寿司": "restaurant",
            "くら": "restaurant",
            "すし": "restaurant",

            # Supermarkets
            "イオン": "supermarket",
            "イオンモール": "supermarket",
            "イトーヨーカドー": "supermarket",
            "イトーヨーカ堂": "supermarket",
            "西友": "supermarket",
            "西友ストア": "supermarket",
            "ライフ": "supermarket",
            "ライフコーポレーション": "supermarket",
            "マルエツ": "supermarket",
            "オーケー": "supermarket",
            "ベルク": "supermarket",
            "ヤオコー": "supermarket",
            "コープ": "supermarket",
            "生協": "supermarket",

            # Drug Stores
            "マツモトキヨシ": "drugstore",
            "マツキヨ": "drugstore",
            "ツルハドラッグ": "drugstore",
            "ツルハ": "drugstore",
            "スギ薬局": "drugstore",
            "スギ": "drugstore",
            "ウエルシア": "drugstore",
            "ウエルシア薬局": "drugstore",
            "ココカラファイン": "drugstore",
            "ココカラ": "drugstore",
            "サンドラッグ": "drugstore",
            "サンドラッグ": "drugstore",

            # Department Stores
            "高島屋": "department_store",
            "三越": "department_store",
            "伊勢丹": "department_store",
            "松屋": "department_store",
            "東急百貨店": "department_store",
            "阪急百貨店": "department_store",
            "大丸": "department_store",

            # Other Common Categories
            "スターバックス": "cafe",
            "ドトール": "cafe",
            "タリーズ": "cafe",
            "コメダ": "cafe",
            "カフェ": "cafe",
            "郵便局": "post_office",
            "日本郵便": "post_office",
            "銀行": "bank",
            "ATM": "bank",
            "ガソリンスタンド": "gas_station",
            "ENEOS": "gas_station",
            "出光": "gas_station",
            "コスモ": "gas_station",
            "薬局": "pharmacy",
            "医院": "medical",
            "クリーニング": "cleaning",
            "理容室": "barber",
            "美容院": "beauty_salon"
        }

        return vendor_db

    def _initialize_field_patterns(self) -> Dict[str, List[str]]:
        """Initialize comprehensive field-specific regex patterns for Japanese receipts."""
        return {
            'date': [
                r'(\d{4}[年/-]\d{1,2}[月/-]\d{1,2}日?)',  # 2025年7月2日, 2025/7/2, 2025-7-2
                r'(\d{4}年\s*\d{1,2}月\s*\d{1,2}日?)',     # 2025年 7月 2日
                r'(\d{1,2}[/-]\d{1,2}[/-]\d{4})',         # 7/2/2025, 07-02-2025
                r'(\d{4}\.\d{1,2}\.\d{1,2})',             # 2025.7.2
                r'(\d{2})[/-](\d{1,2})[/-](\d{1,2})',     # 25-7-2 (assume 20xx)
            ],
            'invoice_number': [
                r'(T-?\d{8,15})',                                   # Japanese invoice/登録番号 starting with T and long digits
                r'(?:No\.?|番号|伝票|レシート)\s*[:\s]*([A-Za-z0-9\-]+)',  # No.: 123, 番号: ABC123
                r'([A-Za-z]-?\d{3,14})',                                 # T001234, R123456, T-12345678901234
                r'(\d{4,12})',                                          # Pure numeric: 12345678
            ],
            'subtotal': [
                r'(?:小計|小\s*計)\s*[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)',  # 小計: 2848, 小 計 ¥2848
                r'[¥\\]?([0-9,]+\.?[0-9]*)\s*(?:小計|小\s*計)',        # ¥2848 小計
            ],
            'tax': [
                r'(?:消費税|内消費税|税)\s*[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)',  # 消費税: 258, 税 ¥258
                r'[¥\\]?([0-9,]+\.?[0-9]*)\s*(?:消費税|内消費税|税)',        # ¥258 消費税
                r'\(\s*(?:消費税|内消費税|税)\s*[¥\\]?([0-9,]+\.?[0-9]*)\s*\)',  # (消費税 ¥258)
            ],
            'total': [
                r'(?:合計|総額|お買上計|合\s*計)\s*[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)',  # 合計: 3106, 合 計 ¥3106
                r'[¥\\]?([0-9,]+\.?[0-9]*)\s*(?:合計|総額|お買上計|合\s*計)',        # ¥3106 合計
            ],
            'payment': [
                r'(?:現金|お預り|預り金|支払い)\s*[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)',  # 現金: 5000, お預り ¥5000
                r'[¥\\]?([0-9,]+\.?[0-9]*)\s*(?:現金|お預り|預り金|支払い)',        # ¥5000 現金
            ],
            'change': [
                r'(?:お釣り|釣銭|おつり)\s*[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)',  # お釣り: 1894, 釣銭 ¥1894
                r'[¥\\]?([0-9,]+\.?[0-9]*)\s*(?:お釣り|釣銭|おつり)',        # ¥1894 お釣り
            ]
        }

    def extract_fields_enhanced(self, ocr_result: Dict[str, Any], filename: str = "receipt.jpg") -> Dict[str, Any]:
        """
        Extract fields from enhanced OCR result with Japanese-specific processing.

        Args:
            ocr_result: OCR result from Google Vision DOCUMENT_TEXT_DETECTION
            filename: Original filename

        Returns:
            Structured field extraction results
        """
        try:
            print(f"🎯 Enhanced Japanese field extraction for: {filename}")

            # Extract raw text and structured blocks
            raw_text = ""
            text_blocks = []

            if ocr_result.get('ParsedResults') and ocr_result['ParsedResults']:
                raw_text = ocr_result['ParsedResults'][0].get('ParsedText', '')
                text_blocks = ocr_result.get('metadata', {}).get('text_blocks', [])

            if not raw_text and text_blocks:
                # Reconstruct text from blocks if needed
                raw_text = '\n'.join([block.get('text', '') for block in text_blocks])

            # Normalize Japanese text
            normalized_text = self._normalize_japanese_text(raw_text)

            # Extract fields using position-aware processing
            extracted_fields = self._extract_fields_by_position(text_blocks, normalized_text)

            # Apply post-processing logic
            processed_fields = self._apply_post_processing_logic(extracted_fields)

            # Categorize vendor and expense
            category_result = self._categorize_expense_enhanced(processed_fields, normalized_text)

            # Calculate confidence scores
            confidence_scores = self._calculate_field_confidence(processed_fields)

            # Prepare final result
            result = {
                'date': processed_fields.get('date', ''),
                'vendor': processed_fields.get('vendor', ''),
                'total': processed_fields.get('total', ''),
                'invoice_number': processed_fields.get('invoice_number', ''),
                'tax_category': processed_fields.get('tax_category', '標準税率'),
                'account_title': category_result['category'],
                'confidence': category_result['confidence'],
                'subtotal': processed_fields.get('subtotal', ''),
                'tax': processed_fields.get('tax', ''),
                'currency': 'JPY',
                'payment': processed_fields.get('payment', ''),
                'change': processed_fields.get('change', ''),
                'field_confidence': confidence_scores,
                'raw_text': raw_text,
                'normalized_text': normalized_text,
                'processing_method': 'enhanced_japanese',
                'ocr_engine': ocr_result.get('metadata', {}).get('engine', 'unknown')
            }

            # Save to validation dataset
            self._save_to_validation_dataset(result, filename)

            print(f"✅ Enhanced Japanese extraction complete: {result['vendor']} - ¥{result['total']} ({result['account_title']})")
            return result

        except Exception as e:
            print(f"❌ Enhanced Japanese extraction failed: {e}")
            # Fallback to basic extractor if available
            if FIELD_EXTRACTOR_AVAILABLE:
                try:
                    fallback_extractor = FieldExtractor()
                    return fallback_extractor.extract_fields(None, filename)  # Will use OCR.space fallback
                except Exception as fallback_error:
                    print(f"❌ Fallback extraction also failed: {fallback_error}")

            return self._get_error_result(str(e), filename)

    def _normalize_japanese_text(self, text: str) -> str:
        """
        Normalize Japanese text: full-width to half-width, clean currency symbols.

        Args:
            text: Raw OCR text

        Returns:
            Normalized text
        """
        if not text:
            return ""

        # Normalize full-width characters to half-width
        normalized = unicodedata.normalize('NFKC', text)

        # Clean up common OCR artifacts
        normalized = re.sub(r'[¥\\円]', '¥', normalized)  # Standardize currency symbols
        normalized = re.sub(r'\s+', ' ', normalized)      # Normalize whitespace
        normalized = normalized.strip()

        return normalized

    def _extract_fields_by_position(self, text_blocks: List[Dict], normalized_text: str) -> Dict[str, Any]:
        """
        Extract fields using position-aware processing based on text block locations.

        Args:
            text_blocks: Structured text blocks from DOCUMENT_TEXT_DETECTION
            normalized_text: Normalized full text

        Returns:
            Extracted field values
        """
        fields = {}

        # Classify blocks by position
        header_blocks = [b for b in text_blocks if b.get('block_type') == 'header']
        body_blocks = [b for b in text_blocks if b.get('block_type') == 'body']
        footer_blocks = [b for b in text_blocks if b.get('block_type') == 'footer']

        # Extract vendor from header (top area)
        fields['vendor'] = self._extract_vendor_from_blocks(header_blocks)

        # Extract date from header
        fields['date'] = self._extract_date_from_blocks(header_blocks + body_blocks[:2])  # First few body blocks too

        # Extract invoice number from anywhere (often in header or footer)
        fields['invoice_number'] = self._extract_invoice_from_blocks(text_blocks)

        # Extract amounts from footer (bottom area - totals, tax, payment)
        amount_fields = self._extract_amounts_from_blocks(footer_blocks)
        fields.update(amount_fields)

        # Fallback to regex extraction on full text if needed
        if not fields.get('date'):
            fields['date'] = self._extract_date_regex(normalized_text)
        if not fields.get('total'):
            fields['total'] = self._extract_total_regex(normalized_text)
        if not fields.get('tax'):
            fields['tax'] = self._extract_tax_regex(normalized_text)

        return fields

    def _extract_vendor_from_blocks(self, header_blocks: List[Dict]) -> str:
        """Extract vendor name from header blocks."""
        for block in header_blocks:
            text = block.get('text', '')
            # Look for substantial text that's likely a store name
            if len(text) >= 2 and not any(skip in text for skip in ['レシート', '領収書', 'RECEIPT', '日付', '時間', 'TEL', '〒']):
                # Check if it matches known vendors
                for vendor_name in self.vendor_database.keys():
                    if vendor_name in text:
                        return vendor_name

                # Return first substantial text as vendor
                return text.strip()

        return ""

    def _extract_date_from_blocks(self, blocks: List[Dict]) -> str:
        """Extract date from specified blocks."""
        for block in blocks:
            text = block.get('text', '')
            date = self._extract_date_regex(text)
            if date:
                return date
        return ""

    def _extract_invoice_from_blocks(self, text_blocks: List[Dict]) -> str:
        """Extract invoice number from any block."""
        for block in text_blocks:
            text = block.get('text', '')
            for pattern in self.field_patterns['invoice_number']:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    candidate = match.group(1)
                    if self._is_valid_invoice_number(candidate):
                        return candidate
        return ""

    def _extract_amounts_from_blocks(self, footer_blocks: List[Dict]) -> Dict[str, str]:
        """Extract monetary amounts from footer blocks."""
        amounts = {}

        # Combine all footer text for comprehensive extraction
        footer_text = ' '.join([block.get('text', '') for block in footer_blocks])

        # Extract each amount type
        amounts['total'] = self._extract_total_regex(footer_text)
        amounts['tax'] = self._extract_tax_regex(footer_text)
        amounts['subtotal'] = self._extract_subtotal_regex(footer_text)
        amounts['payment'] = self._extract_payment_regex(footer_text)
        amounts['change'] = self._extract_change_regex(footer_text)

        return amounts

    def _extract_date_regex(self, text: str) -> str:
        """Extract date using regex patterns."""
        for pattern in self.field_patterns['date']:
            match = re.search(pattern, text)
            if match:
                try:
                    if '年' in text:  # Japanese format
                        year = int(match.group(1))
                        month = int(match.group(2))
                        day = int(match.group(3))
                    elif len(match.group(1)) == 4:  # YYYY format
                        year = int(match.group(1))
                        month = int(match.group(2))
                        day = int(match.group(3))
                    elif len(match.group(1)) == 2:  # YY format
                        year = 2000 + int(match.group(1))
                        month = int(match.group(2))
                        day = int(match.group(3))
                    else:  # DD/MM/YYYY or similar
                        if pattern == r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})':
                            month = int(match.group(1))
                            day = int(match.group(2))
                            year = int(match.group(3))
                        else:
                            day = int(match.group(1))
                            month = int(match.group(2))
                            year = int(match.group(3))

                    # Validate date
                    if 2020 <= year <= 2030 and 1 <= month <= 12 and 1 <= day <= 31:
                        return f"{year}-{month:02d}-{day:02d}"
                except (ValueError, IndexError):
                    continue
        return ""

    def _extract_total_regex(self, text: str) -> str:
        """Extract total amount using regex."""
        for pattern in self.field_patterns['total']:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amount = self._normalize_amount(match.group(1))
                if amount and 1 <= float(amount) <= 1000000:
                    return amount
        return ""

    def _extract_tax_regex(self, text: str) -> str:
        """Extract tax amount using regex."""
        for pattern in self.field_patterns['tax']:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amount = self._normalize_amount(match.group(1))
                if amount and 0 <= float(amount) <= 50000:  # Tax can be 0
                    return amount
        return ""

    def _extract_subtotal_regex(self, text: str) -> str:
        """Extract subtotal amount using regex."""
        for pattern in self.field_patterns['subtotal']:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amount = self._normalize_amount(match.group(1))
                if amount and 1 <= float(amount) <= 1000000:
                    return amount
        return ""

    def _extract_payment_regex(self, text: str) -> str:
        """Extract payment amount using regex."""
        for pattern in self.field_patterns['payment']:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amount = self._normalize_amount(match.group(1))
                if amount and 1 <= float(amount) <= 1000000:
                    return amount
        return ""

    def _extract_change_regex(self, text: str) -> str:
        """Extract change amount using regex."""
        for pattern in self.field_patterns['change']:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amount = self._normalize_amount(match.group(1))
                if amount and 0 <= float(amount) <= 100000:  # Change can be 0
                    return amount
        return ""

    def _normalize_amount(self, amount_str: str) -> str:
        """Normalize amount string: remove commas, ensure valid number."""
        if not amount_str:
            return ""

        # Remove commas and currency symbols
        cleaned = re.sub(r'[¥\\,円]', '', amount_str.strip())

        try:
            # Convert to float then back to int string (removes decimals if .00)
            value = float(cleaned)
            return str(int(value))
        except ValueError:
            return ""

    def _is_valid_invoice_number(self, candidate: str) -> bool:
        """Validate invoice number candidate."""
        if not candidate or len(candidate) < 2:
            return False

        # Must contain at least one digit
        if not any(c.isdigit() for c in candidate):
            return False

        # Length constraints
        if len(candidate) > 15:
            return False

        # Avoid obvious non-invoice patterns
        if any(char in candidate for char in ['%', ':', '/', '@']):
            return False

        return True

    def _apply_post_processing_logic(self, fields: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply post-processing logic to resolve conflicts and validate relationships.

        Args:
            fields: Raw extracted fields

        Returns:
            Processed fields with logic applied
        """
        processed = fields.copy()

        # Logic 1: If both 小計 and 合計 exist, prefer 合計 as total
        subtotal = processed.get('subtotal', '')
        total = processed.get('total', '')

        if subtotal and total:
            try:
                subtotal_val = float(subtotal)
                total_val = float(total)

                # If subtotal + tax would equal total, keep both
                tax = processed.get('tax', '')
                if tax:
                    tax_val = float(tax)
                    if abs((subtotal_val + tax_val) - total_val) < 2:  # Within ¥2 tolerance
                        pass  # Keep all values
                    else:
                        # Check if total might be the correct one
                        pass
            except ValueError:
                pass

        # Logic 2: Handle 税込 amounts (tax-inclusive totals)
        # If we find 税込 in the text and have a total, it might be tax-inclusive

        # Logic 3: Validate payment vs total + change relationship
        payment = processed.get('payment', '')
        change_amt = processed.get('change', '')

        if payment and total and change_amt:
            try:
                payment_val = float(payment)
                total_val = float(total)
                change_val = float(change_amt)

                # Payment should equal total + change (within tolerance)
                expected_payment = total_val + change_val
                if abs(payment_val - expected_payment) > 5:  # More than ¥5 difference
                    print(f"⚠️ Payment validation failed: {payment_val} != {total_val} + {change_val} = {expected_payment}")
            except ValueError:
                pass

        return processed

    def _categorize_expense_enhanced(self, fields: Dict[str, Any], text: str) -> Dict[str, float]:
        """
        Enhanced expense categorization using vendor database and fuzzy matching.

        Args:
            fields: Extracted fields including vendor
            text: Full normalized text

        Returns:
            Dict with category and confidence score
        """
        vendor = fields.get('vendor', '')

        # First, try exact match in vendor database
        if vendor in self.vendor_database:
            return {
                'category': self.vendor_database[vendor],
                'confidence': 0.95
            }

        # Try fuzzy matching for vendor name
        best_match = None
        best_score = 0

        for db_vendor, category in self.vendor_database.items():
            # Fuzzy match with multiple algorithms
            ratio_score = fuzz.ratio(vendor.lower(), db_vendor.lower())
            token_score = fuzz.token_sort_ratio(vendor.lower(), db_vendor.lower())

            # Use the better score
            score = max(ratio_score, token_score)

            if score > best_score and score > 70:  # Minimum threshold
                best_match = category
                best_score = score

        if best_match:
            confidence = min(0.9, best_score / 100)  # Cap at 90%
            return {
                'category': best_match,
                'confidence': confidence
            }

        # Fallback to keyword-based categorization
        return self._categorize_by_keywords(text)

    def _categorize_by_keywords(self, text: str) -> Dict[str, float]:
        """Fallback categorization using keyword matching."""
        text_lower = text.lower()

        # Define keyword categories (similar to original field_extractors.py)
        categories = {
            '食費': ['レストラン', 'ラーメン', '寿司', '定食', '食堂', 'カフェ', 'バー', '居酒屋',
                   '焼肉', 'すし', '天ぷら', 'ラーメン', 'うどん', 'そば', '丼', '定食', 'ファミレス',
                   'ファストフード', 'マクドナルド', 'ケンタッキー', 'ピザ', 'ハンバーガー', 'コーヒー',
                   'ジュース', 'ソフトドリンク', 'コンビニ', 'スーパー', 'デリ', '惣菜', '弁当',
                   'おにぎり', 'サンドイッチ', 'パン', 'ケーキ', 'デザート'],
            '交通費': ['タクシー', 'バス', '電車', '地下鉄', '新幹線', '飛行機', '空港', '駅',
                     'ターミナル', '交通', '乗車券', '切符', '定期券', '高速道路', '高速',
                     '有料道路', '駐車場', 'パーキング', 'ガソリン', 'スタンド', 'レンタカー'],
            '消耗品費': ['文房具', 'ペン', 'ノート', 'ファイル', 'クリップ', 'ホッチキス', 'テープ',
                       'インク', 'トナー', 'コピー用紙', '封筒', '切手', 'はがき', 'ティッシュ',
                       'トイレットペーパー', '洗剤', '石鹸', 'シャンプー', '歯磨き', '化粧品',
                       '日用品', 'スーパー', 'コンビニ', 'ドラッグストア', '薬局']
        }

        scores = {}
        for category, keywords in categories.items():
            score = sum(5 for keyword in keywords if keyword in text_lower)
            if score > 0:
                scores[category] = score

        if scores:
            best_category = max(scores, key=scores.get)
            max_score = scores[best_category]
            confidence = min(0.85, max_score / 50)  # Normalize to 0-85%
            return {
                'category': best_category,
                'confidence': confidence
            }

        return {
            'category': 'その他',
            'confidence': 0.0
        }

    def _calculate_field_confidence(self, fields: Dict[str, Any]) -> Dict[str, float]:
        """Calculate confidence scores for each extracted field."""
        confidence = {}

        # Date confidence
        date = fields.get('date', '')
        if date:
            confidence['date'] = 0.95  # High confidence if extracted
        else:
            confidence['date'] = 0.0

        # Vendor confidence
        vendor = fields.get('vendor', '')
        if vendor:
            confidence['vendor'] = 0.90  # High confidence if extracted
        else:
            confidence['vendor'] = 0.0

        # Amount confidences (based on reasonableness)
        for field_name in ['total', 'tax', 'subtotal', 'payment', 'change']:
            amount = fields.get(field_name, '')
            if amount:
                try:
                    value = float(amount)
                    # Basic reasonableness checks
                    if field_name == 'total' and 10 <= value <= 100000:
                        confidence[field_name] = 0.95
                    elif field_name == 'tax' and 0 <= value <= 5000:
                        confidence[field_name] = 0.90
                    elif field_name in ['subtotal', 'payment'] and 10 <= value <= 100000:
                        confidence[field_name] = 0.90
                    elif field_name == 'change' and 0 <= value <= 10000:
                        confidence[field_name] = 0.85
                    else:
                        confidence[field_name] = 0.60  # Reasonable but borderline
                except ValueError:
                    confidence[field_name] = 0.0
            else:
                confidence[field_name] = 0.0

        # Invoice number confidence
        invoice = fields.get('invoice_number', '')
        if invoice:
            confidence['invoice_number'] = 0.85
        else:
            confidence['invoice_number'] = 0.0

        return confidence

    def _save_to_validation_dataset(self, result: Dict[str, Any], filename: str):
        """Save extraction result to validation dataset for continuous improvement."""
        try:
            # Create artifacts/ocr_results directory if it doesn't exist
            results_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'artifacts', 'ocr_results')
            os.makedirs(results_dir, exist_ok=True)

            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_filename = os.path.splitext(filename)[0]
            json_filename = f"{base_filename}_{timestamp}.json"
            text_filename = f"{base_filename}_{timestamp}.txt"

            # Save structured result as JSON
            json_path = os.path.join(results_dir, json_filename)
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            # Save raw text for reference
            text_path = os.path.join(results_dir, text_filename)
            with open(text_path, 'w', encoding='utf-8') as f:
                f.write(result.get('raw_text', ''))

            print(f"💾 Validation data saved: {json_filename}")

        except Exception as e:
            print(f"⚠️ Failed to save validation data: {e}")

    def _get_error_result(self, error_msg: str, filename: str) -> Dict[str, Any]:
        """Return error result structure."""
        return {
            'date': '',
            'vendor': '',
            'total': '',
            'invoice_number': '',
            'tax_category': '',
            'account_title': '',
            'confidence': 0.0,
            'subtotal': '',
            'tax': '',
            'currency': 'JPY',
            'error': error_msg,
            'processing_method': 'enhanced_japanese',
            'filename': filename
        }


# Convenience function for easy integration
def create_enhanced_japanese_extractor() -> EnhancedJapaneseExtractor:
    """Create and return an enhanced Japanese extractor instance."""
    return EnhancedJapaneseExtractor()