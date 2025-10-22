import os
import requests
import json
import re
from typing import Dict, Any
from datetime import datetime
from PIL import Image, ImageEnhance, ImageFilter
import io

class FieldExtractor:
    """Extract structured fields from receipt images using OCR.space API."""

    def __init__(self):
        self.api_key = os.getenv('OCR_SPACE_API_KEY', 'K88575219088957')
        self.api_url = 'https://api.ocr.space/parse/image'

    def extract_fields(self, image_data: bytes, filename: str) -> Dict[str, Any]:
        """Extract structured data from receipt image."""
        try:
            print(f"🔍 Starting OCR extraction for file: {filename}, size: {len(image_data)} bytes")

            # Validate that this is actually an image file
            if not self._is_image_file(image_data, filename):
                raise Exception("Uploaded file is not a valid image. Please upload a JPEG, PNG, or other image format.")

            # Preprocess image for better OCR results
            processed_image_data = self._preprocess_image(image_data, filename)
            print(f"🖼️ Image preprocessing complete, new size: {len(processed_image_data)} bytes")

            # Check final file size against OCR.space limits (1MB)
            max_api_size = 1024 * 1024  # 1MB
            if len(processed_image_data) > max_api_size:
                raise Exception(f"Image too large for OCR API ({len(processed_image_data)/1024:.1f}KB > {max_api_size/1024:.1f}KB). Please use a smaller image.")

            # Try OCR engine 2 first (more accurate for Japanese)
            try:
                print("📡 Calling OCR API with engine 2...")
                result = self._call_ocr_api(processed_image_data, filename, engine=2)
                print(f"✅ OCR API call successful, response keys: {list(result.keys())}")
            except Exception as e:
                print(f"❌ Engine 2 failed: {e}, trying engine 1...")
                # Fallback to engine 1 if engine 2 fails
                try:
                    result = self._call_ocr_api(processed_image_data, filename, engine=1)
                    print("✅ OCR API fallback to engine 1 successful")
                except Exception as e2:
                    print(f"❌ Both OCR engines failed: {e2}")
                    raise Exception(f"OCR API completely failed: {e2}")

            if result.get('IsErroredOnProcessing'):
                error_msg = result.get('ErrorMessage', 'Unknown OCR error')
                print(f"❌ OCR processing error: {error_msg}")
                raise Exception(f"OCR API Error: {error_msg}")

            # Parse OCR text and extract fields
            parsed_text = result['ParsedResults'][0]['ParsedText'] if result['ParsedResults'] else ""
            print(f"📝 OCR extracted text length: {len(parsed_text)} characters")
            print(f"📝 OCR text preview: {parsed_text[:200]}...")

            if not parsed_text.strip():
                print("⚠️ OCR returned empty text!")
                raise Exception("OCR returned no text from image - the image may be too blurry or the text may be unreadable")

            # Extract fields using primary methods
            extracted_fields = self._parse_receipt_text(parsed_text)
            print(f"🔍 Primary extraction results: {extracted_fields}")

            # If critical fields are missing, try fallback extraction
            if not extracted_fields['total'] or not extracted_fields['vendor']:
                print("🔄 Primary extraction incomplete, trying fallback methods...")
                extracted_fields = self._fallback_extraction(parsed_text, extracted_fields)
                print(f"🔄 Fallback extraction results: {extracted_fields}")

            # Ensure tax extraction is always attempted (critical requirement)
            if not extracted_fields['tax']:
                print("🔄 Tax not found, attempting additional tax extraction...")
                lines = [line.strip() for line in parsed_text.split('\n') if line.strip()]
                extracted_fields['tax'] = self._extract_tax(lines)
                print(f"🔄 Additional tax extraction result: {extracted_fields['tax']}")

            print(f"✅ Final extraction results: {extracted_fields}")
            return extracted_fields

        except Exception as e:
            print(f"❌ Field extraction failed: {e}")
            # Return empty fields but with error info for debugging
            return {
                'date': '',
                'vendor': '',
                'total': '',
                'invoice_number': '',
                'tax_category': '',
                'account_title': '',
                'subtotal': '',
                'tax': '',
                'currency': 'JPY',
                'error': str(e),
                'debug_info': {
                    'filename': filename,
                    'file_size': len(image_data) if 'image_data' in locals() else 0,
                    'error_type': type(e).__name__
                }
            }

    def _is_image_file(self, image_data: bytes, filename: str) -> bool:
        """Check if the uploaded file is actually an image."""
        try:
            # Check file extension
            valid_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.tif', '.webp']
            if any(filename.lower().endswith(ext) for ext in valid_extensions):
                return True

            # Check MIME type by trying to open with PIL
            from PIL import Image
            try:
                Image.open(io.BytesIO(image_data))
                return True
            except Exception:
                pass

            return False
        except Exception:
            return False

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
        # Priority patterns - most specific to least specific
        total_patterns = [
            r'合計[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)',  # 合計: 1000 (Total - highest priority)
            r'合計\s*[¥\\]?([0-9,]+\.?[0-9]*)',     # 合計 1000 (no colon)
            r'総額[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)',  # 総額: 1000 (Total amount)
            r'TOTAL[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)', # TOTAL: 1000
            r'[¥\\]([0-9,]+\.?[0-9]*)\s*合計',      # ¥1000 合計 (amount before total)
        ]

        # Search for explicit total indicators from bottom up (totals usually at bottom)
        for line in reversed(lines):
            line_lower = line.lower()
            for pattern in total_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    amount = match.group(1).replace(',', '')
                    try:
                        value = float(amount)
                        if 1 <= value <= 1000000:  # Reasonable receipt amount
                            print(f"💰 Found total: {amount} in line: {line.strip()}")
                            return str(int(value))
                    except ValueError:
                        continue

        # If no explicit total found, look for amounts but exclude obvious non-total amounts
        # This is more conservative - only pick amounts that are clearly totals
        print("⚠️ No explicit total found, checking for implicit totals...")

        # Look for the pattern where we have subtotal + tax = total
        subtotal = self._extract_subtotal(lines)
        tax = self._extract_tax(lines)

        if subtotal and tax:
            try:
                subtotal_val = float(subtotal)
                tax_val = float(tax)
                calculated_total = subtotal_val + tax_val

                # Look for this calculated total in the receipt
                total_str = str(int(calculated_total))
                for line in reversed(lines):
                    if total_str in line.replace(',', ''):
                        print(f"💰 Found calculated total: {total_str} (subtotal {subtotal} + tax {tax})")
                        return total_str
            except (ValueError, TypeError):
                pass

        # Last resort: look for reasonable amounts but be very conservative
        # Only consider amounts that appear isolated or with minimal text
        total_candidates = []
        for line in reversed(lines):
            line = line.strip()

            # Skip lines with excluded terms
            exclude_patterns = [
                r'お釣', r'釣銭', r'現計', r'預り', r'小計', r'内税',
                r'消費税', r'税', r'ポイント', r'値引', r'割引'
            ]
            if any(excl in line for excl in exclude_patterns):
                continue

            # Look for isolated amounts (just ¥XXXX or XXXX円)
            isolated_patterns = [
                r'^\s*[¥\\]([0-9,]+\.?[0-9]*)\s*$',      # Just ¥1000
                r'^\s*([0-9,]+\.?[0-9]*)\s*円\s*$',      # Just 1000円
            ]

            for pattern in isolated_patterns:
                match = re.search(pattern, line)
                if match:
                    amount = match.group(1).replace(',', '')
                    try:
                        value = float(amount)
                        if 10 <= value <= 50000:  # Reasonable receipt total range (not too high)
                            total_candidates.append((value, line))
                            break  # Only one amount per line
                    except ValueError:
                        continue

        # Return the first reasonable candidate (from bottom)
        if total_candidates:
            amount, line = total_candidates[0]
            print(f"💰 Found isolated total candidate: {int(amount)} in line: {line}")
            return str(int(amount))

        print("❌ No total amount found")
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
            r'小計額[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)',  # 小計額: 2848 (Subtotal amount)
            r'小計[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)',   # 小計: 1000 (Subtotal)
            r'SUBTOTAL[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)',
        ]

        for line in lines:
            for pattern in subtotal_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    return match.group(1).replace(',', '')
        return ''

    def _extract_tax(self, lines: list) -> str:
        """Extract tax amount - CRITICAL for the business requirement."""
        tax_patterns = [
            # Primary patterns (most specific)
            r'\(消費税\s+等[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)\)',  # (消費税 等 ¥258)
            r'内税額[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)',          # 内税額 ¥258
            r'消費税[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)',          # 消費税 ¥258
            r'税額[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)',            # 税額 ¥258
            r'税[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)',              # 税 ¥258
            r'TAX[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)',             # TAX ¥258

            # Additional patterns for different formats
            r'税込[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)',            # 税込 ¥258
            r'税別[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)',            # 税別 ¥258
            r'内消費税[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)',        # 内消費税 ¥258
        ]

        # First pass: look for explicit tax indicators
        for line in lines:
            for pattern in tax_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    amount = match.group(1).replace(',', '')
                    try:
                        value = float(amount)
                        if 1 <= value <= 50000:  # Reasonable tax amount range
                            print(f"🧾 Found tax amount: {amount} in line: {line.strip()}")
                            return str(int(value))
                    except ValueError:
                        continue

        # Second pass: calculate tax from subtotal and total if available
        # This is a fallback for when tax is not explicitly shown
        subtotal = self._extract_subtotal(lines)
        # Avoid circular recursion - don't call _extract_total here
        # Instead, look for total in the lines directly
        total = ''
        for line in lines:
            # Simple total patterns to avoid recursion
            for pattern in [r'合計[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)', r'TOTAL[:\s]*[¥\\]?([0-9,]+\.?[0-9]*)']:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    total = match.group(1).replace(',', '')
                    break
            if total:
                break

        if subtotal and total:
            try:
                subtotal_val = float(subtotal)
                total_val = float(total)

                # Calculate potential tax amounts
                # Common tax rates: 8% (reduced), 10% (standard)
                potential_tax_8 = subtotal_val * 0.08
                potential_tax_10 = subtotal_val * 0.1

                # Check if total matches subtotal + tax
                if abs((subtotal_val + potential_tax_8) - total_val) < 1:  # Within 1 yen tolerance
                    print(f"🧾 Calculated tax (8%): {potential_tax_8} from subtotal {subtotal_val}")
                    return str(int(potential_tax_8))
                elif abs((subtotal_val + potential_tax_10) - total_val) < 1:
                    print(f"🧾 Calculated tax (10%): {potential_tax_10} from subtotal {subtotal_val}")
                    return str(int(potential_tax_10))

            except (ValueError, TypeError):
                pass

        # Third pass: look for any amounts in lines containing tax-related keywords
        tax_keywords = ['税', '消費税', 'tax', 'TAX']
        for line in lines:
            if any(keyword in line for keyword in tax_keywords):
                # Extract any numbers from tax-related lines
                amounts = re.findall(r'([0-9,]+\.?[0-9]*)', line)
                for amount in amounts:
                    amount = amount.replace(',', '')
                    try:
                        value = float(amount)
                        if 1 <= value <= 50000:  # Reasonable tax range
                            print(f"🧾 Found tax-related amount: {amount} in line: {line.strip()}")
                            return str(int(value))
                    except ValueError:
                        continue

        print("⚠️ No tax amount found")
        return ''

    def _call_ocr_api(self, image_data: bytes, filename: str, engine: int = 2) -> dict:
        """Call OCR.space API with specified engine and retry logic."""
        # Detect if this is a camera image (usually has 'camera' in filename)
        is_camera_image = 'camera' in filename.lower()

        # Ensure filename has a valid extension for OCR API
        if not any(filename.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.tif', '.webp']):
            # Force .jpg extension for API compatibility
            api_filename = f"{filename}.jpg" if '.' not in filename else f"{filename.rsplit('.', 1)[0]}.jpg"
            print(f"📝 Modified filename for API: {filename} -> {api_filename}")
        else:
            api_filename = filename

        files = {'file': (api_filename, image_data, 'application/octet-stream')}
        data = {
            'apikey': self.api_key,
            'language': 'jpn',
            'isOverlayRequired': True,
            'detectOrientation': True,
            'scale': True,
            'OCREngine': engine,
        }

        # Add special parameters for camera images
        if is_camera_image:
            print(f"📷 Detected camera image, applying enhanced OCR settings")
            data.update({
                'scale': True,  # Better scaling for camera images
                'isTable': False,  # Receipts are not tables
                'filetype': 'JPG',  # Camera images are usually JPEG
            })

        print(f"📡 OCR API call details: engine={engine}, camera={is_camera_image}, size={len(image_data)}, filename={api_filename}")

        # Retry logic for timeouts
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                print(f"📡 Attempt {attempt + 1}/{max_retries + 1}...")
                response = requests.post(self.api_url, files=files, data=data, timeout=20)  # Increased timeout
                response.raise_for_status()

                result = response.json()
                print(f"📡 OCR API response status: {response.status_code}")

                return result

            except requests.exceptions.Timeout:
                if attempt < max_retries:
                    print(f"❌ OCR API timeout (20s), retrying in 2 seconds...")
                    import time
                    time.sleep(2)
                    continue
                else:
                    print("❌ OCR API timeout (20s) - final attempt")
                    raise Exception("OCR API timeout - image may be too large or network issue")
            except requests.exceptions.RequestException as e:
                print(f"❌ OCR API request error: {e}")
                raise Exception(f"OCR API request failed: {e}")

    def _preprocess_image(self, image_data: bytes, filename: str) -> bytes:
        """Preprocess image to improve OCR accuracy and ensure file size limits."""
        try:
            # Open image with PIL
            image = Image.open(io.BytesIO(image_data))

            # Convert to RGB if necessary (handles RGBA, P, etc.)
            if image.mode not in ('RGB', 'L'):
                image = image.convert('RGB')

            original_size = image.size
            print(f"🖼️ Original image size: {original_size}, mode: {image.mode}")

            # Detect if this is a camera image
            is_camera_image = 'camera' in filename.lower()

            if is_camera_image:
                print("📷 Applying camera image enhancements...")

                # Enhance contrast for camera images
                enhancer = ImageEnhance.Contrast(image)
                image = enhancer.enhance(1.5)

                # Enhance sharpness
                enhancer = ImageEnhance.Sharpness(image)
                image = enhancer.enhance(1.3)

                # Convert to grayscale for better OCR
                image = image.convert('L')

                # Apply slight blur to reduce noise, then sharpen
                image = image.filter(ImageFilter.GaussianBlur(0.5))
                enhancer = ImageEnhance.Sharpness(image)
                image = enhancer.enhance(2.0)

            # Resize if too large (OCR.space has limits)
            max_size = (2000, 2000)  # Reasonable max size
            if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
                image.thumbnail(max_size, Image.Resampling.LANCZOS)
                print(f"🖼️ Resized image to: {image.size}")

            # Ensure minimum size for OCR
            min_size = (400, 400)
            if image.size[0] < min_size[0] or image.size[1] < min_size[1]:
                # Upscale small images
                scale_factor = max(min_size[0] / image.size[0], min_size[1] / image.size[1])
                new_size = (int(image.size[0] * scale_factor), int(image.size[1] * scale_factor))
                image = image.resize(new_size, Image.Resampling.LANCZOS)
                print(f"🖼️ Upscaled image to: {image.size}")

            # AGGRESSIVE COMPRESSION to meet OCR.space 1MB limit
            max_file_size = 900 * 1024  # 900KB to be safe (under 1MB limit)
            quality = 95
            output_buffer = io.BytesIO()

            # Try progressively lower quality until file size is acceptable
            while quality >= 10:
                output_buffer = io.BytesIO()
                image.save(output_buffer, format='JPEG', quality=quality, optimize=True)

                if len(output_buffer.getvalue()) <= max_file_size:
                    break

                quality -= 10
                print(f"🖼️ File too large ({len(output_buffer.getvalue())/1024:.1f}KB), reducing quality to {quality}")

            processed_data = output_buffer.getvalue()

            # If still too large after minimum quality, resize further
            if len(processed_data) > max_file_size:
                print(f"🖼️ Still too large ({len(processed_data)/1024:.1f}KB), resizing further...")
                # Resize to 75% of current size
                new_width = int(image.size[0] * 0.75)
                new_height = int(image.size[1] * 0.75)
                if new_width >= 400 and new_height >= 400:  # Don't go below minimum
                    image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    output_buffer = io.BytesIO()
                    image.save(output_buffer, format='JPEG', quality=quality, optimize=True)
                    processed_data = output_buffer.getvalue()
                    print(f"🖼️ Final resize to: {image.size}")

            print(f"🖼️ Image preprocessing complete: {original_size} -> {image.size}, {len(image_data)/1024:.1f}KB -> {len(processed_data)/1024:.1f}KB (quality: {quality})")

            return processed_data

        except Exception as e:
            print(f"⚠️ Image preprocessing failed: {e}, using original image")
            return image_data

    def _fallback_extraction(self, text: str, current_fields: Dict[str, Any]) -> Dict[str, Any]:
        """Enhanced fallback extraction methods when primary extraction fails."""
        lines = [line.strip() for line in text.split('\n') if line.strip()]

        print(f"🔄 Starting fallback extraction for missing fields: total={bool(current_fields['total'])}, vendor={bool(current_fields['vendor'])}, tax={bool(current_fields['tax'])}")

        # Enhanced vendor fallback: look for any substantial line that might be a store name
        if not current_fields['vendor']:
            print("🔄 Searching for vendor name...")
            for line in lines[:20]:  # Check more lines
                line = line.strip()
                if 2 <= len(line) <= 25 and not any(char.isdigit() for char in line[:3]):
                    # Look for lines with Japanese characters or store indicators
                    has_japanese = any(char for char in line if '\u3040' <= char <= '\u309f' or '\u30a0' <= char <= '\u30ff' or '\u4e00' <= char <= '\u9fff')
                    has_english = bool(re.search(r'[a-zA-Z]', line))

                    if has_japanese or has_english:
                        # Additional check: avoid obvious non-store lines
                        skip_keywords = ['レシート', '領収書', 'RECEIPT', 'INVOICE', '日付', '時間', 'TEL', '〒', '¥', '円']
                        if not any(skip in line for skip in skip_keywords):
                            current_fields['vendor'] = line
                            print(f"🔄 Found vendor: {line}")
                            break

        # Enhanced total fallback: smarter amount detection
        if not current_fields['total']:
            print("🔄 Searching for total amount...")
            amounts = []
            exclude_terms = ['お釣', '釣銭', '現計', '預り', 'ポイント', '値引', '割引', '小計', '消費税', '税']

            for line in lines:
                # Skip lines with excluded terms
                if any(term in line for term in exclude_terms):
                    continue

                # Find amounts with various patterns
                patterns = [
                    r'[¥\\]([0-9,]+\.?[0-9]*)',  # ¥1000
                    r'([0-9,]+\.?[0-9]*)\s*円',  # 1000円
                    r'^\s*([0-9,]+\.?[0-9]*)\s*$',  # Just numbers
                ]

                for pattern in patterns:
                    matches = re.findall(pattern, line)
                    for match in matches:
                        amount = match.replace(',', '')
                        try:
                            value = float(amount)
                            if 10 <= value <= 100000:  # Reasonable receipt range
                                amounts.append((value, line))
                        except ValueError:
                            continue

            if amounts:
                # Sort by value (highest first) and pick the most reasonable total
                amounts.sort(key=lambda x: x[0], reverse=True)

                # For receipts, the highest amount is often the total (unless it's change)
                # But let's be smarter: prefer amounts that appear near the bottom
                bottom_amounts = amounts[:3]  # Top 3 highest amounts
                current_fields['total'] = str(int(bottom_amounts[0][0]))
                print(f"🔄 Found total: {current_fields['total']} from line: {bottom_amounts[0][1].strip()}")

        # Enhanced tax fallback: try harder to find tax
        if not current_fields['tax']:
            print("🔄 Searching for tax amount...")
            current_fields['tax'] = self._extract_tax(lines)  # Re-run tax extraction

        return current_fields