#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tashiro Receipt-to-Excel Field Mapping System
Based on PowerPoint workflow specification

Maps receipt fields A,B,C,D,E,F to Excel columns in 各個人出金伝票別紙データ.xlsx
Handles mixed receipts, tax classification (内税/外税), and automatic accounting categorization.

TODO: Link this legacy mapper into `app/services/mapping_service.py` once orchestration rules are signed off.
"""

import re
import json
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

class TaxType(Enum):
    """Tax classification types from PowerPoint slides"""
    INCLUSIVE = "内税"      # Tax included in price
    EXCLUSIVE = "外税"      # Tax separate from price  
    NO_TAX_INFO = "税抜き"  # No tax information
    MANUAL_JUDGMENT = "要判断"  # Requires manual judgment

class FieldType(Enum):
    """Receipt field types (A-F from updated specification)"""
    DATE = "A"                  # 日付 - Date
    STORE_NAME = "B"           # 店名 - Store Name  
    TOTAL_AMOUNT = "C"         # 金額(合計額) - Total Amount
    INVOICE_NUMBER = "D"       # インボイス番号 - Invoice Number
    TAX_CATEGORY = "E"         # 税区分 - Tax Category
    ACCOUNT_TITLE = "F"        # 勘定科目 - Accounting Item/Account Title

@dataclass
class ReceiptField:
    """Represents a mapped receipt field"""
    field_type: FieldType
    value: Any
    confidence: float
    excel_column: str
    requires_split: bool = False
    split_categories: List[str] = None

@dataclass
class SplitLineItem:
    """For handling mixed receipts that need category splitting"""
    description: str
    amount: float
    category: str
    tax_rate: float
    excel_mapping: Dict[str, Any]

class TashiroFieldMapper:
    """
    Maps receipt OCR data to Excel columns for 各個人出金伝票別紙データ.xlsx
    Implements the exact workflow from PowerPoint slides
    """
    
    def __init__(self):
        self.excel_column_mapping = self._build_excel_mapping()
        self.tax_patterns = self._build_tax_patterns()
        self.mixed_receipt_rules = self._build_mixed_receipt_rules()
        
    def _build_excel_mapping(self) -> Dict[FieldType, str]:
        """Define mapping from receipt fields to Excel columns (Updated A-F Specification)"""
        return {
            FieldType.DATE: "日付",                    # A - Date
            FieldType.STORE_NAME: "店舗名",            # B - Store Name  
            FieldType.TOTAL_AMOUNT: "金額",            # C - Total Amount
            FieldType.INVOICE_NUMBER: "インボイス番号",  # D - Invoice Number
            FieldType.TAX_CATEGORY: "税区分",          # E - Tax Category
            FieldType.ACCOUNT_TITLE: "勘定科目"        # F - Account Title
        }
    
    def _build_tax_patterns(self) -> Dict[str, TaxType]:
        """Build patterns for tax classification detection"""
        return {
            # Inclusive tax patterns (内税)
            r"内税|税込み?|込み|税込価格|総額": TaxType.INCLUSIVE,
            r"tax\s*included|inclusive": TaxType.INCLUSIVE,
            
            # Exclusive tax patterns (外税)
            r"外税|税別|税抜き?|別途消費税|プラス税": TaxType.EXCLUSIVE,
            r"tax\s*excluded|exclusive|plus\s*tax": TaxType.EXCLUSIVE,
            
            # No tax info patterns
            r"税抜き?価格|本体価格|税なし": TaxType.NO_TAX_INFO,
            r"no\s*tax|tax\s*free|non-taxable": TaxType.NO_TAX_INFO,
        }
    
    def _build_mixed_receipt_rules(self) -> Dict[str, Dict]:
        """Rules for handling mixed receipts (food + daily goods, etc.)"""
        return {
            "food_indicators": {
                "keywords": ["食品", "弁当", "パン", "おにぎり", "サンドイッチ", "飲み物", "お茶", "コーヒー", "水"],
                "tax_rate": 0.08,  # Reduced tax rate for food
                "category": "食費",
                "account_code": "611"
            },
            "daily_goods": {
                "keywords": ["雑貨", "文具", "ペン", "ノート", "ティッシュ", "洗剤", "石鹸"],
                "tax_rate": 0.10,  # Standard tax rate
                "category": "消耗品費", 
                "account_code": "616"
            },
            "communication": {
                "keywords": ["通信", "電話", "携帯", "プリペイド", "チャージ"],
                "tax_rate": 0.00,  # Non-taxable
                "category": "通信費",
                "account_code": "613"
            },
            "tax_payments": {
                "keywords": ["印紙", "手数料", "登録料", "税金", "公課"],
                "tax_rate": 0.00,  # Non-taxable
                "category": "租税公課",
                "account_code": "619"
            }
        }
    
    def map_receipt_to_excel(self, ocr_data: Dict[str, Any], 
                           line_items: List[Dict] = None) -> Dict[str, Any]:
        """
        Main function: Map receipt OCR data to Excel format
        
        Args:
            ocr_data: Raw OCR extraction result
            line_items: Detailed line items if available
            
        Returns:
            Dictionary ready for Excel export with proper field mapping
        """
        
        result = {
            "excel_fields": {},
            "split_items": [],
            "tax_analysis": {},
            "requires_manual_review": False,
            "processing_notes": []
        }
        
        # Step 1: Map basic fields (A-F)
        basic_fields = self._map_basic_fields(ocr_data)
        result["excel_fields"].update(basic_fields)
        
        # Step 2: Analyze tax classification
        tax_analysis = self._analyze_tax_classification(ocr_data)
        result["tax_analysis"] = tax_analysis
        
        # Step 3: Handle mixed receipts if line items available
        if line_items:
            split_analysis = self._analyze_mixed_receipt(line_items, tax_analysis)
            result["split_items"] = split_analysis["items"]
            result["requires_manual_review"] = split_analysis["needs_review"]
            result["processing_notes"].extend(split_analysis["notes"])
        
        # Step 4: Apply automatic rules (food → 10% tax even if not written)
        result = self._apply_automatic_rules(result, ocr_data)
        
        # Step 5: Final validation and Excel structure
        excel_output = self._format_for_excel(result)
        
        return excel_output
    
    def _map_basic_fields(self, ocr_data: Dict[str, Any]) -> Dict[str, Any]:
        """Map basic receipt fields A-F to Excel columns (Updated Specification)"""
        
        mapped_fields = {}
        
        # Field A: Date (日付)
        if ocr_data.get("date"):
            # Ensure proper date format for Excel
            date_value = self._standardize_date(ocr_data["date"])
            mapped_fields[self.excel_column_mapping[FieldType.DATE]] = date_value
        
        # Field B: Store Name (店名)
        if ocr_data.get("vendor"):
            mapped_fields[self.excel_column_mapping[FieldType.STORE_NAME]] = ocr_data["vendor"]
        
        # Field C: Total Amount (金額(合計額))
        if ocr_data.get("total"):
            mapped_fields[self.excel_column_mapping[FieldType.TOTAL_AMOUNT]] = float(ocr_data["total"])
        
        # Field D: Invoice Number (インボイス番号)
        invoice_number = self._extract_invoice_number(ocr_data)
        mapped_fields[self.excel_column_mapping[FieldType.INVOICE_NUMBER]] = invoice_number
        
        # Field E: Tax Category (税区分)
        tax_category = self._determine_tax_category(ocr_data)
        mapped_fields[self.excel_column_mapping[FieldType.TAX_CATEGORY]] = tax_category
        
        # Field F: Account Title (勘定科目)
        account_title = self._determine_account_title(ocr_data)
        mapped_fields[self.excel_column_mapping[FieldType.ACCOUNT_TITLE]] = account_title
        
        return mapped_fields
    
    def _analyze_tax_classification(self, ocr_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze tax classification (内税/外税/manual judgment)"""
        
        raw_text = ocr_data.get("raw_text", "").lower()
        
        tax_analysis = {
            "detected_type": TaxType.MANUAL_JUDGMENT.value,  # Convert enum to string
            "confidence": 0.0,
            "evidence": [],
            "calculated_rate": None,
            "excel_value": "要確認"
        }
        
        # Check for explicit tax type indicators
        for pattern, tax_type in self.tax_patterns.items():
            if re.search(pattern, raw_text, re.IGNORECASE):
                tax_analysis["detected_type"] = tax_type.value  # Convert enum to string
                tax_analysis["evidence"].append(f"Pattern matched: {pattern}")
                tax_analysis["confidence"] = 0.8
                break
        
        # Calculate tax rate if amounts are available
        total = ocr_data.get("total", 0)
        tax = ocr_data.get("tax", 0)
        subtotal = ocr_data.get("subtotal", 0)
        
        if total > 0 and tax > 0:
            if tax_analysis["detected_type"] == TaxType.INCLUSIVE.value:
                # 内税: total includes tax
                rate = tax / total
            else:
                # 外税: tax is separate
                rate = tax / (total - tax) if (total - tax) > 0 else 0
            
            tax_analysis["calculated_rate"] = round(rate * 100, 1)
            
            # Determine standard rates
            if 9.5 <= tax_analysis["calculated_rate"] <= 10.5:
                tax_analysis["excel_value"] = "課税10%"
            elif 7.5 <= tax_analysis["calculated_rate"] <= 8.5:
                tax_analysis["excel_value"] = "課税8%"
            else:
                tax_analysis["excel_value"] = f"課税{tax_analysis['calculated_rate']:.1f}%"
        
        return tax_analysis
    
    def _analyze_mixed_receipt(self, line_items: List[Dict], 
                             tax_analysis: Dict) -> Dict[str, Any]:
        """Handle mixed receipts that need category splitting"""
        
        split_result = {
            "items": [],
            "needs_review": False,
            "notes": []
        }
        
        if not line_items:
            return split_result
        
        categorized_items = []
        
        for item in line_items:
            description = item.get("description", "").lower()
            amount = item.get("total_price", 0) or item.get("unit_price", 0)
            
            # Determine category based on description
            matched_category = None
            for category_name, rules in self.mixed_receipt_rules.items():
                for keyword in rules["keywords"]:
                    if keyword in description:
                        matched_category = category_name
                        break
                if matched_category:
                    break
            
            if matched_category:
                rules = self.mixed_receipt_rules[matched_category]
                split_item = SplitLineItem(
                    description=item.get("description", ""),
                    amount=amount,
                    category=rules["category"],
                    tax_rate=rules["tax_rate"],
                    excel_mapping={
                        "摘要": item.get("description", ""),
                        "金額": amount,
                        "税区分": f"課税{rules['tax_rate']*100:.0f}%" if rules['tax_rate'] > 0 else "非課税",
                        "勘定科目": rules["category"],
                        "勘定科目コード": rules["account_code"]
                    }
                )
                categorized_items.append(split_item)
            else:
                # Uncategorized item - needs manual review
                split_result["needs_review"] = True
                split_result["notes"].append(f"要確認: {description}")
        
        # Check if we have multiple categories (mixed receipt)
        categories = set(item.category for item in categorized_items)
        if len(categories) > 1:
            split_result["notes"].append("混合レシート: 複数カテゴリに分割")
            split_result["needs_review"] = True
        
        split_result["items"] = categorized_items
        return split_result
    
    def _apply_automatic_rules(self, result: Dict, ocr_data: Dict) -> Dict:
        """Apply automatic rules like 'food → 10% tax even if not written'"""
        
        # Rule: Food receipts get 10% tax rate even if not explicitly stated
        raw_text = ocr_data.get("raw_text", "").lower()
        vendor = ocr_data.get("vendor", "").lower()
        
        food_indicators = ["食", "弁当", "レストラン", "カフェ", "マクドナルド", "すき家"]
        
        if any(indicator in raw_text or indicator in vendor for indicator in food_indicators):
            # This appears to be a food receipt
            if result["tax_analysis"]["detected_type"] == TaxType.MANUAL_JUDGMENT.value:
                result["tax_analysis"]["detected_type"] = TaxType.INCLUSIVE.value
                result["tax_analysis"]["excel_value"] = "課税10%"
                result["tax_analysis"]["confidence"] = 0.7
                result["tax_analysis"]["evidence"].append("自動ルール: 食品 → 10%税率")
                result["processing_notes"].append("食品レシート: 10%税率を自動適用")
        
        return result
    
    def _format_for_excel(self, result: Dict) -> Dict[str, Any]:
        """Format the final result for Excel export"""
        
        excel_output = {
            "individual_expense_data": {
                **result["excel_fields"],
                "税区分": result["tax_analysis"]["excel_value"],
                "処理区分": "自動処理" if not result["requires_manual_review"] else "要確認",
                "処理日時": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            },
            "split_accounting": [item.excel_mapping for item in result["split_items"]],
            "metadata": {
                "processing_notes": result["processing_notes"],
                "tax_analysis": result["tax_analysis"],
                "requires_manual_review": result["requires_manual_review"],
                "excel_ready": True
            }
        }
        
        return excel_output
    
    def _standardize_date(self, date_str: str) -> str:
        """Standardize date format for Excel compatibility"""
        if not date_str:
            return ""
        
        # Try to parse various date formats
        date_patterns = [
            r"(\d{4})-(\d{1,2})-(\d{1,2})",  # YYYY-MM-DD
            r"(\d{4})/(\d{1,2})/(\d{1,2})",  # YYYY/MM/DD
            r"(\d{1,2})/(\d{1,2})/(\d{4})",  # MM/DD/YYYY
            r"(\d{4})年(\d{1,2})月(\d{1,2})日", # Japanese format
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, date_str)
            if match:
                groups = match.groups()
                if len(groups) == 3:
                    # Determine format and convert to YYYY-MM-DD
                    if "年" in pattern:
                        return f"{groups[0]}-{groups[1].zfill(2)}-{groups[2].zfill(2)}"
                    elif pattern.startswith(r"(\d{1,2})"):
                        return f"{groups[2]}-{groups[0].zfill(2)}-{groups[1].zfill(2)}"
                    else:
                        return f"{groups[0]}-{groups[1].zfill(2)}-{groups[2].zfill(2)}"
        
        return date_str  # Return as-is if no pattern matches
    
    def _extract_key_description(self, raw_text: str) -> str:
        """Extract key descriptive phrases from raw OCR text"""
        lines = raw_text.split('\n')
        
        # Skip header lines (store name, address, etc.)
        content_lines = []
        skip_patterns = ["株式会社", "〒", "TEL", "営業時間", "ありがとう"]
        
        for line in lines:
            line = line.strip()
            if line and not any(pattern in line for pattern in skip_patterns):
                content_lines.append(line)
        
        # Take relevant middle lines that likely contain item descriptions
        if len(content_lines) > 3:
            relevant_lines = content_lines[1:-2]  # Skip first and last few lines
            return " / ".join(relevant_lines[:3])  # Limit to first 3 relevant lines
        
        return " / ".join(content_lines[:2])
    
    def _extract_invoice_number(self, ocr_data: Dict[str, Any]) -> str:
        """Extract invoice number from receipt data based on real Japanese receipt patterns"""
        raw_text = ocr_data.get("raw_text", "")
        
        # Real receipt patterns from examples:
        # Example 1: 登録番号 T7380001003643
        # Example 2: レシートNo.9205 取引:9139 店:758
        
        invoice_patterns = [
            # Pattern 1: 登録番号 (Registration number) - Real pattern from example 1
            r"登録番号[\s\-:：]*([T]\d{13})",
            r"registration[\s\-:：]*([T]\d{13})",
            
            # Pattern 2: レシートNo. with transaction info - Real pattern from example 2
            r"レシートNo\.(\d+)(?:\s*取引:(\d+))?(?:\s*店:(\d+))?",
            r"receipt\s*no\.?[\s\-:：]*(\d+)",
            
            # Pattern 3: General patterns
            r"(?:インボイス|invoice)[\s\-:：]*([A-Z0-9\-]{8,})",
            r"(?:番号|No\.?)[\s\-:：]*([A-Z0-9\-]{6,})",
            r"T\d{13}",  # Japanese qualified invoice number format
            r"(?:領収書|レシート)[\s\-:：]*No\.?[\s]*([A-Z0-9\-]{6,})",
        ]
        
        for pattern in invoice_patterns:
            match = re.search(pattern, raw_text, re.IGNORECASE)
            if match:
                groups = match.groups()
                if len(groups) > 1 and groups[1]:
                    # Multiple groups - combine them (レシートNo.9205 取引:9139 店:758)
                    return " ".join([g for g in groups if g])
                else:
                    return groups[0].strip()
        
        # Fallback: Look for any T-number (registration number)
        t_number_match = re.search(r"T\d{13}", raw_text)
        if t_number_match:
            return t_number_match.group(0)
        
        return ""
    
    def _determine_tax_category(self, ocr_data: Dict[str, Any]) -> str:
        """Determine tax category based on real Japanese receipt patterns"""
        raw_text = ocr_data.get("raw_text", "")
        
        # Real patterns from examples:
        # Example 1: (10%内税対象 ¥2,848) (10%内税額 ¥258) (消費税 等 ¥258)
        # Example 2: 内税率10%対象額, 内税率8%対象額
        
        # Enhanced tax category detection based on real patterns
        tax_patterns = [
            # Specific patterns from real receipts
            (r"10%内税対象", "10%内税"),
            (r"8%内税対象", "8%内税"),
            (r"内税率10%対象額", "10%内税"),
            (r"内税率8%対象額", "8%内税"),
            (r"消費税.*10%", "10%消費税"),
            (r"消費税.*8%", "8%消費税"),
            (r"軽減税率.*8%", "8%軽減税率"),
            
            # General tax patterns
            (r"内税|税込み?|込み", "内税"),
            (r"外税|税別|税抜き?", "外税"),
            (r"非課税|免税", "非課税"),
            (r"軽減", "軽減税率"),
        ]
        
        detected_categories = []
        
        for pattern, category in tax_patterns:
            if re.search(pattern, raw_text, re.IGNORECASE):
                detected_categories.append(category)
        
        if detected_categories:
            # Return the most specific category found
            primary_category = detected_categories[0]
            if "10%" in primary_category or "内税" in primary_category:
                return "課税10%"
            elif "8%" in primary_category or "軽減" in primary_category:
                return "軽減税率8%"
            elif "外税" in primary_category:
                return "外税"
            elif "非課税" in primary_category:
                return "非課税"
            else:
                return "課税"
        
        # Default determination based on vendor type (from real examples)
        vendor = ocr_data.get("vendor", "").lower()
        
        # Food establishments typically have mixed tax rates
        if any(food_indicator in vendor for food_indicator in ["食堂", "レストラン", "カフェ"]):
            return "軽減税率8%"  # Food items typically 8%
        
        # Supermarkets typically have mixed items
        if any(market_indicator in vendor for market_indicator in ["スーパー", "ベニマル", "イオン"]):
            return "課税10%"  # General items 10%
        
        return "課税10%"  # Default to standard tax rate
    
    def _determine_account_title(self, ocr_data: Dict[str, Any]) -> str:
        """Determine accounting item/account title based on real Japanese receipt patterns"""
        vendor = ocr_data.get("vendor", "")
        raw_text = ocr_data.get("raw_text", "")
        
        # Real examples analysis:
        # Example 1 (郡山桑野食堂): めし【小】, 味噌汁, ほっけ, etc. → 食費
        # Example 2 (ヨークベニマル): 冷たい鶏中華, ぶっかけとろろそば, etc. → 食費
        
        # Enhanced account title mapping based on real receipt patterns
        account_mappings = {
            "食費": [
                # Food items from real examples
                "めし", "味噌汁", "ほっけ", "玉子焼", "おくら",
                "鶏中華", "とろろそば", "茄子", "とうもろこし",
                
                # Common food keywords
                "食堂", "レストラン", "カフェ", "弁当", "おにぎり", "サンドイッチ",
                "パン", "お茶", "コーヒー", "水", "飲み物", "食品", "食材",
                "惣菜", "お菓子", "アイス", "冷凍", "生鮮", "肉", "魚", "野菜",
                
                # Store types that typically sell food
                "ベニマル", "スーパー", "コンビニ", "イオン", "ライフ", "西友"
            ],
            "消耗品費": [
                "文具", "事務用品", "ペン", "紙", "ノート", "コピー", "印刷",
                "ファイル", "封筒", "テープ", "のり", "はさみ", "ホチキス",
                "電池", "ティッシュ", "洗剤", "石鹸", "タオル", "雑貨"
            ],
            "交通費": [
                "電車", "バス", "タクシー", "交通", "切符", "定期", "IC",
                "Suica", "PASMO", "運賃", "乗車券", "回数券"
            ],
            "車両費": [
                "ガソリン", "燃料", "駐車", "車", "整備", "オイル", "タイヤ",
                "車検", "修理", "洗車", "高速", "ETC"
            ],
            "通信費": [
                "電話", "携帯", "インターネット", "通信", "Wi-Fi", "プロバイダ",
                "スマホ", "ケータイ", "回線", "データ"
            ],
            "水道光熱費": [
                "電気", "ガス", "水道", "光熱", "電力", "都市ガス", "プロパン"
            ],
            "地代家賃": [
                "家賃", "賃料", "駐車場", "事務所", "テナント", "賃貸", "物件"
            ],
            "旅費交通費": [
                "宿泊", "ホテル", "出張", "新幹線", "航空", "飛行機", "旅行",
                "民宿", "ビジネスホテル", "温泉"
            ],
            "接待交際費": [
                "接待", "会食", "懇親会", "贈答", "ギフト", "お中元", "お歳暮",
                "慶弔", "祝儀", "香典"
            ]
        }
        
        # Combine vendor and text content for analysis
        full_text = f"{vendor} {raw_text}".lower()
        
        # Check for specific patterns first (higher priority)
        for account, keywords in account_mappings.items():
            match_count = sum(1 for keyword in keywords if keyword.lower() in full_text)
            if match_count > 0:
                return account
        
        # Special handling for known store types
        vendor_lower = vendor.lower()
        if any(store in vendor_lower for store in ["食堂", "レストラン", "カフェ"]):
            return "食費"
        elif any(store in vendor_lower for store in ["ベニマル", "スーパー", "コンビニ"]):
            return "食費"  # Assume grocery shopping
        elif any(store in vendor_lower for store in ["ガソリン", "エネオス", "出光"]):
            return "車両費"
        
        # Default account title for unrecognized items
        return "消耗品費"

# Example usage and testing
if __name__ == "__main__":
    mapper = TashiroFieldMapper()
    
    # Test with sample receipt data
    sample_receipt = {
        "vendor": "ファミリーマート",
        "date": "2024-10-15",
        "total": 1200.0,
        "tax": 109.0,
        "subtotal": 1091.0,
        "raw_text": "ファミリーマート\nおにぎり 150円\nお茶 100円\n文具ペン 200円\n内税込み\n合計 1200円",
        "line_items": [
            {"description": "おにぎり", "unit_price": 150},
            {"description": "お茶", "unit_price": 100},
            {"description": "文具ペン", "unit_price": 200}
        ]
    }
    
    print("=== Testing Tashiro Receipt-to-Excel Field Mapping ===")
    
    result = mapper.map_receipt_to_excel(sample_receipt, sample_receipt["line_items"])
    
    print("\nExcel Output:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    print(f"\nMixed Receipt Detected: {len(result['split_accounting']) > 1}")
    print(f"Requires Manual Review: {result['metadata']['requires_manual_review']}")
    print(f"Tax Classification: {result['individual_expense_data']['税区分']}")