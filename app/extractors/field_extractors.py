import os
import requests
import json
import re
from typing import Dict, Any
from datetime import datetime

class FieldExtractor:
    """Extract structured fields from receipt images using OCR.space API."""

    def __init__(self):
        self.api_key = os.getenv('OCR_SPACE_API_KEY', 'K88575219088957')
        self.api_url = 'https://api.ocr.space/parse/image'

    def extract_fields(self, image_data: bytes, filename: str) -> Dict[str, Any]:
        """Extract structured data from receipt image."""
        try:
            # Try OCR engine 2 first (more accurate for Japanese)
            try:
                result = self._call_ocr_api(image_data, filename, engine=2)
            except Exception as e:
                print(f"Engine 2 failed, trying engine 1: {e}")
                # Fallback to engine 1 if engine 2 fails
                result = self._call_ocr_api(image_data, filename, engine=1)

            if result.get('IsErroredOnProcessing'):
                raise Exception(f"OCR API Error: {result.get('ErrorMessage', 'Unknown error')}")

            # Parse OCR text and extract fields
            parsed_text = result['ParsedResults'][0]['ParsedText'] if result['ParsedResults'] else ""

            # Debug: Log the OCR text for troubleshooting
            print(f"OCR Text extracted: {parsed_text[:500]}...")  # Log first 500 chars

            # Extract fields using primary methods
            extracted_fields = self._parse_receipt_text(parsed_text)

            # If critical fields are missing, try fallback extraction
            if not extracted_fields['total'] or not extracted_fields['vendor']:
                print("Primary extraction incomplete, trying fallback methods...")
                extracted_fields = self._fallback_extraction(parsed_text, extracted_fields)

            return extracted_fields

        except Exception as e:
            print(f"Field extraction failed: {e}")
            return {
                'date': '',
                'vendor': '',
                'total': '',
                'invoice_number': '',
                'tax_category': '',
                'account_title': '',
                'subtotal': '',
                'tax': '',
                'currency': 'JPY'
            }

    def _parse_receipt_text(self, text: str) -> Dict[str, Any]:
        """Parse OCR text to extract receipt fields."""
        lines = [line.strip() for line in text.split('\n') if line.strip()]

        extracted = {
            'date': self._extract_date(lines),
            'vendor': self._extract_vendor(lines),
            'total': self._extract_total(lines),
            'invoice_number': self._extract_invoice(lines),
            'tax_category': self._extract_tax_category(lines),
            'account_title': self._categorize_expense(lines),
            'subtotal': self._extract_subtotal(lines),
            'tax': self._extract_tax(lines),
            'currency': 'JPY'
        }

        return extracted

    def _extract_date(self, lines: list) -> str:
        """Extract date from receipt lines."""
        date_patterns = [
            r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})',  # YYYY-MM-DD
            r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})',  # DD-MM-YYYY
            r'(\d{4})年(\d{1,2})月(\d{1,2})日',     # Japanese format: 2025年7月2日
            r'(\d{4})年(\d{1,2})月(\d{1,2})',       # Japanese format without 日
            r'(\d{4})/(\d{1,2})/(\d{1,2})',        # YYYY/MM/DD
            r'(\d{2})[/-](\d{1,2})[/-](\d{1,2})',  # YY-MM-DD (assume 20xx)
        ]

        for line in lines:
            for pattern in date_patterns:
                match = re.search(pattern, line)
                if match:
                    if '年' in line:  # Japanese format
                        return f"{match.group(1)}-{match.group(2).zfill(2)}-{match.group(3).zfill(2)}"
                    elif len(match.group(1)) == 4:  # YYYY first
                        return f"{match.group(1)}-{match.group(2).zfill(2)}-{match.group(3).zfill(2)}"
                    elif len(match.group(1)) == 2:  # YY-MM-DD format
                        year = f"20{match.group(1)}"  # Assume 20xx
                        return f"{year}-{match.group(2).zfill(2)}-{match.group(3).zfill(2)}"
                    else:  # DD first
                        return f"{match.group(3)}-{match.group(2).zfill(2)}-{match.group(1).zfill(2)}"
        return ''

    def _extract_vendor(self, lines: list) -> str:
        """Extract vendor/store name."""
        # Skip common header/footer lines
        skip_patterns = [
            r'^\s*レシート\s*$', r'^\s*領収書\s*$', r'^\s*RECEIPT\s*$',
            r'^\s*伝票\s*$', r'^\s*注文\s*$', r'^\s*INVOICE\s*$',
            r'^\s*TEL', r'^\s*電話', r'^\s*〒', r'^\s*住所',
            r'^\s*日付', r'^\s*DATE', r'^\s*\d{4}[/-]\d{1,2}[/-]\d{1,2}',
            r'^\s*時間', r'^\s*TIME', r'^\s*現計', r'^\s*お釣',
            r'^\s*小計', r'^\s*合計', r'^\s*消費税',
            r'^\s*登録番号', r'^\s*T印', r'^\s*扱責'
        ]

        for line in lines[:10]:  # Check first 10 lines
            line = line.strip()

            # Skip if matches skip patterns
            if any(re.search(pattern, line, re.IGNORECASE) for pattern in skip_patterns):
                continue

            # Skip lines that are mostly numbers
            if len(line) > 0 and sum(c.isdigit() for c in line) / len(line) > 0.5:
                continue

            # Skip very short lines
            if len(line) < 2:
                continue

            # Skip phone numbers
            if re.search(r'\d{2,4}-\d{2,4}-\d{4}', line):
                continue

            # Look for store names - prefer lines with Japanese characters
            if any(char for char in line if '\u3040' <= char <= '\u309f' or '\u30a0' <= char <= '\u30ff' or '\u4e00' <= char <= '\u9fff'):
                # Additional check: store names usually contain restaurant keywords or are substantial
                store_keywords = ['食堂', '店', 'レストラン', 'ショップ', 'ストア', 'スーパー', 'コンビニ', '酒店', '薬局', '医院', 'クリーニング']
                if any(keyword in line for keyword in store_keywords) or len(line) >= 3:
                    return line

            # Also accept English store names
            if len(line) > 3 and not line.startswith(('TEL', 'TEL:', '電話', '〒', '住所')):
                return line

        return ''

    def _extract_total(self, lines: list) -> str:
        """Extract total amount."""
        amount_patterns = [
            r'合計[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)',  # 合計: 1000
            r'総額[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)',  # 総額: 1000
            r'TOTAL[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)',
            r'小計[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)',
            r'[¥\\]([0-9,]+\.?[0-9]*)\s*$',  # ¥1000 at end of line
            r'([0-9,]+\.?[0-9]*)\s*円\s*$',  # 1000円 at end of line
            r'^\s*([0-9,]+\.?[0-9]*)\s*$',  # Just numbers on a line (often totals)
            r'金額[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)',  # 金額: 1000
            r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',  # General number pattern with commas
        ]

        # First pass: look for explicit total indicators
        for line in reversed(lines):  # Check from bottom up
            line_lower = line.lower()
            for pattern in amount_patterns[:7]:  # Skip the general pattern first
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    amount = match.group(1).replace(',', '')
                    # Validate it's a reasonable amount
                    try:
                        value = float(amount)
                        if 1 <= value <= 1000000:  # Reasonable receipt amount
                            return amount
                    except ValueError:
                        continue

        # Second pass: look for any reasonable amounts if no explicit totals found
        all_amounts = []
        for line in lines:
            matches = re.findall(r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', line)
            for match in matches:
                amount = match.replace(',', '')
                try:
                    value = float(amount)
                    if 1 <= value <= 1000000:  # Reasonable receipt amount
                        all_amounts.append((value, line))
                except ValueError:
                    continue

        # Return the largest reasonable amount found (often the total)
        if all_amounts:
            all_amounts.sort(key=lambda x: x[0], reverse=True)
            return str(int(all_amounts[0][0]))

        return ''

    def _extract_invoice(self, lines: list) -> str:
        """Extract invoice/receipt number."""
        invoice_patterns = [
            r'伝票[番号No\.]*[:\s]*([A-Za-z0-9\-]+)',
            r'レシート[番号No\.]*[:\s]*([A-Za-z0-9\-]+)',
            r'注文[番号No\.]*[:\s]*([A-Za-z0-9\-]+)',
            r'INVOICE[:\s]*([A-Za-z0-9\-]+)',
            r'NO\.[:\s]*([A-Za-z0-9\-]+)',
            r'No\.[:\s]*([A-Za-z0-9\-]+)',
            r'登録番号[:\s]*([A-Za-z0-9\-]+)',
            r'([A-Za-z]\d{12,})',  # Registration numbers like T7380001003643
        ]

        # First, try to find registration numbers (most specific)
        for line in lines:
            match = re.search(r'([A-Za-z]\d{12,})', line)
            if match:
                return match.group(1)

        # Then try other patterns, but avoid phone numbers
        for line in lines:
            # Skip lines that look like phone numbers
            if re.search(r'\d{2,4}-\d{2,4}-\d{4}', line):
                continue

            for pattern in invoice_patterns[:6]:  # Skip the registration pattern we already tried
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    candidate = match.group(1)
                    # Avoid short numbers that might be part of phone numbers
                    if len(candidate) >= 3:
                        return candidate

        return ''

    def _extract_tax_category(self, lines: list) -> str:
        """Extract tax category."""
        text = ' '.join(lines).lower()

        if '軽減税率' in text or '8%' in text:
            return '軽減税率'
        elif '標準税率' in text or '10%' in text:
            return '標準税率'
        elif '課税' in text:
            return '課税'
        elif '非課税' in text:
            return '非課税'

        return '課税'  # Default

    def _categorize_expense(self, lines: list) -> str:
        """Categorize expense based on content."""
        text = ' '.join(lines).lower()

        # Japanese expense categories
        if any(word in text for word in ['レストラン', 'ラーメン', '寿司', '定食', '食堂']):
            return '食費'
        elif any(word in text for word in ['タクシー', 'バス', '電車', '交通']):
            return '交通費'
        elif any(word in text for word in ['コンビニ', 'スーパー', '食品']):
            return '消耗品費'
        elif any(word in text for word in ['ホテル', '旅館', '宿泊']):
            return '宿泊費'
        elif any(word in text for word in ['電話', '通信', 'インターネット']):
            return '通信費'
        elif any(word in text for word in ['文房具', '書籍', '研修']):
            return '消耗品費'

        return 'その他'  # Default

    def _extract_subtotal(self, lines: list) -> str:
        """Extract subtotal."""
        subtotal_patterns = [
            r'小計[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)',
            r'小計額[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)',
            r'SUBTOTAL[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)',
        ]

        for line in lines:
            for pattern in subtotal_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    return match.group(1).replace(',', '')
        return ''

    def _extract_tax(self, lines: list) -> str:
        """Extract tax amount."""
        tax_patterns = [
            r'消費税[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)',
            r'内税額[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)',
            r'税[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)',
            r'TAX[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)',
            r'\(消費税\s+等[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)\)',  # (消費税 等 ¥258)
        ]

        for line in lines:
            for pattern in tax_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    return match.group(1).replace(',', '')
        return ''

    def _call_ocr_api(self, image_data: bytes, filename: str, engine: int = 2) -> dict:
        """Call OCR.space API with specified engine."""
        files = {'file': (filename, image_data, 'application/octet-stream')}
        data = {
            'apikey': self.api_key,
            'language': 'jpn',
            'isOverlayRequired': True,
            'detectOrientation': True,
            'scale': True,
            'OCREngine': engine,
        }

        response = requests.post(self.api_url, files=files, data=data)
        response.raise_for_status()
        return response.json()

    def _fallback_extraction(self, text: str, current_fields: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback extraction methods when primary extraction fails."""
        lines = [line.strip() for line in text.split('\n') if line.strip()]

        # Fallback for vendor: look for any substantial line that might be a store name
        if not current_fields['vendor']:
            for line in lines[:15]:  # Check more lines
                line = line.strip()
                if 3 <= len(line) <= 20 and not any(char.isdigit() for char in line[:5]):
                    # Look for lines with mixed content (letters + potential store indicators)
                    if re.search(r'[a-zA-Z]', line) or any(char for char in line if '\u3040' <= char <= '\u309f' or '\u30a0' <= char <= '\u30ff' or '\u4e00' <= char <= '\u9fff'):
                        current_fields['vendor'] = line
                        break

        # Fallback for total: if no total found, look for the largest amount
        if not current_fields['total']:
            amounts = []
            for line in lines:
                # Find all monetary amounts
                matches = re.findall(r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', line)
                for match in matches:
                    amount = match.replace(',', '')
                    try:
                        value = float(amount)
                        if 10 <= value <= 100000:  # Reasonable receipt range
                            amounts.append(value)
                    except ValueError:
                        continue

            if amounts:
                current_fields['total'] = str(int(max(amounts)))

        return current_fields