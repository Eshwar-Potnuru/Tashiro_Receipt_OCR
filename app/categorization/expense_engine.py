#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tashiro Ironworks - Expense Categorization Engine
Based on workflow analysis of company documents

Features:
- 18-column business office structure support
- Tax classification (10% food service, communication, etc.)
- Mixed category support per receipt
- Japanese expense category detection
"""

import re
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

class ExpenseCategory(Enum):
    """Japanese expense categories based on Tashiro workflow"""
    MEALS = "食費"  # Food expenses (10% tax)
    TRANSPORT = "交通費"  # Transportation
    COMMUNICATION = "通信費"  # Communication expenses  
    ACCOMMODATION = "宿泊費"  # Hotel/lodging
    ENTERTAINMENT = "接待費"  # Entertainment/business meals
    SUPPLIES = "消耗品費"  # Office supplies/consumables
    UTILITIES = "水道光熱費"  # Utilities
    RENT = "地代家賃"  # Rent/lease
    TAXES = "租税公課"  # Taxes and public charges
    TRAVEL = "旅費"  # Travel expenses
    EQUIPMENT = "備品費"  # Equipment
    MAINTENANCE = "修繕費"  # Maintenance/repairs
    FUEL = "燃料費"  # Fuel costs
    INSURANCE = "保険料"  # Insurance
    EDUCATION = "研修費"  # Training/education
    OTHER = "その他"  # Other expenses

class TaxClassification(Enum):
    """Tax classifications for receipt items"""
    TAXABLE_10 = "課税10%"  # 10% consumption tax
    TAXABLE_8 = "課税8%"    # 8% reduced tax rate  
    NON_TAXABLE = "非課税"   # Non-taxable
    TAX_FREE = "免税"       # Tax-free
    UNKNOWN = "税区分不明"   # Unknown tax status

@dataclass
class CategoryMatch:
    """Represents a categorization match"""
    category: ExpenseCategory
    confidence: float
    matched_keywords: List[str]
    tax_classification: TaxClassification
    business_unit: Optional[str] = None

class ExpenseCategorizationEngine:
    """
    AI-powered expense categorization based on Tashiro Ironworks workflow
    """
    
    def __init__(self):
        self.category_keywords = self._build_category_keywords()
        self.vendor_patterns = self._build_vendor_patterns()
        self.tax_indicators = self._build_tax_indicators()
        
    def _build_category_keywords(self) -> Dict[ExpenseCategory, List[str]]:
        """Build keyword patterns for each expense category"""
        return {
            ExpenseCategory.MEALS: [
                # Food-related keywords
                "食事", "飲食", "レストラン", "居酒屋", "カフェ", "弁当",
                "食堂", "料理", "グルメ", "ランチ", "ディナー", "朝食",
                "コンビニ", "スーパー", "食品", "パン", "肉", "魚", "野菜",
                # Common restaurant names
                "マクドナルド", "スターバックス", "すき家", "吉野家", "松屋",
                "ファミマ", "セブン", "ローソン", "イオン"
            ],
            
            ExpenseCategory.TRANSPORT: [
                "交通", "電車", "バス", "タクシー", "地下鉄", "新幹線",
                "航空", "飛行機", "切符", "乗車券", "運賃", "料金",
                "JR", "私鉄", "高速", "駐車場", "ガソリン", "燃料",
                "ETC", "IC", "Suica", "PASMO"
            ],
            
            ExpenseCategory.COMMUNICATION: [
                "通信", "電話", "携帯", "スマホ", "インターネット", "プロバイダ",
                "回線", "Wi-Fi", "データ", "通話", "メール", "FAX",
                "NTT", "ドコモ", "au", "ソフトバンク", "楽天"
            ],
            
            ExpenseCategory.ACCOMMODATION: [
                "宿泊", "ホテル", "旅館", "民宿", "ビジネスホテル", "リゾート",
                "宿", "泊", "部屋代", "滞在", "チェックイン", "予約"
            ],
            
            ExpenseCategory.ENTERTAINMENT: [
                "接待", "懇親", "宴会", "パーティー", "歓迎会", "送別会",
                "忘年会", "新年会", "会食", "打ち合わせ", "商談", "営業"
            ],
            
            ExpenseCategory.SUPPLIES: [
                "消耗品", "文具", "事務用品", "コピー用紙", "ペン", "ファイル",
                "クリップ", "ホチキス", "電池", "トナー", "インク",
                "掃除用品", "洗剤", "ティッシュ"
            ],
            
            ExpenseCategory.UTILITIES: [
                "電気", "ガス", "水道", "光熱費", "電力", "東京電力", "関西電力",
                "都市ガス", "プロパン", "上下水道"
            ],
            
            ExpenseCategory.TAXES: [
                "税金", "印紙", "登録", "手数料", "印紙税", "登録免許税",
                "固定資産税", "自動車税", "住民税", "法人税"
            ]
        }
    
    def _build_vendor_patterns(self) -> Dict[str, ExpenseCategory]:
        """Build vendor name to category mapping"""
        return {
            # Convenience stores (usually food/supplies)
            r"セブン.*イレブン|7.*eleven": ExpenseCategory.MEALS,
            r"ファミリーマート|ファミマ": ExpenseCategory.MEALS,
            r"ローソン": ExpenseCategory.MEALS,
            
            # Restaurants
            r"マクドナルド|McDonald": ExpenseCategory.MEALS,
            r"スターバックス|Starbucks": ExpenseCategory.MEALS,
            r"すき家|吉野家|松屋": ExpenseCategory.MEALS,
            
            # Transportation
            r"JR.*|東日本旅客鉄道": ExpenseCategory.TRANSPORT,
            r"東京メトロ|都営地下鉄": ExpenseCategory.TRANSPORT,
            r"タクシー|TAXI": ExpenseCategory.TRANSPORT,
            
            # Hotels
            r"ホテル.*|Hotel.*": ExpenseCategory.ACCOMMODATION,
            r"旅館|民宿": ExpenseCategory.ACCOMMODATION,
            
            # Office supplies
            r"文具.*|事務.*": ExpenseCategory.SUPPLIES,
            r"コピー.*|印刷.*": ExpenseCategory.SUPPLIES,
        }
    
    def _build_tax_indicators(self) -> Dict[str, TaxClassification]:
        """Build patterns for tax classification detection"""
        return {
            r"税率.*10%|消費税.*10%|10%.*税": TaxClassification.TAXABLE_10,
            r"税率.*8%|消費税.*8%|8%.*税": TaxClassification.TAXABLE_8,
            r"非課税|税抜|tax.*free": TaxClassification.NON_TAXABLE,
            r"免税|duty.*free": TaxClassification.TAX_FREE,
            r"内税|tax.*included": TaxClassification.TAXABLE_10,  # Default to 10%
        }
    
    def categorize_receipt(self, ocr_text: str, vendor_name: str = "", 
                          amount: float = 0.0) -> List[CategoryMatch]:
        """
        Categorize a receipt based on OCR text and vendor information
        
        Args:
            ocr_text: Full OCR extracted text
            vendor_name: Detected vendor/store name
            amount: Receipt amount
            
        Returns:
            List of CategoryMatch objects with confidence scores
        """
        full_text = f"{ocr_text} {vendor_name}".lower()
        matches = []
        
        # Check vendor patterns first (highest confidence)
        vendor_match = self._match_vendor_patterns(vendor_name)
        if vendor_match:
            matches.append(vendor_match)
        
        # Check keyword patterns
        keyword_matches = self._match_keywords(full_text)
        matches.extend(keyword_matches)
        
        # Detect tax classification
        tax_class = self._detect_tax_classification(ocr_text)
        
        # Apply tax classification to matches
        for match in matches:
            match.tax_classification = tax_class
            
        # Handle special cases based on Tashiro workflow
        matches = self._apply_tashiro_rules(matches, full_text, amount)
        
        # Sort by confidence and remove duplicates
        unique_matches = self._deduplicate_matches(matches)
        
        return sorted(unique_matches, key=lambda x: x.confidence, reverse=True)
    
    def _match_vendor_patterns(self, vendor_name: str) -> Optional[CategoryMatch]:
        """Match vendor name patterns with high confidence"""
        if not vendor_name:
            return None
            
        vendor_lower = vendor_name.lower()
        
        for pattern, category in self.vendor_patterns.items():
            if re.search(pattern, vendor_lower, re.IGNORECASE):
                return CategoryMatch(
                    category=category,
                    confidence=0.9,
                    matched_keywords=[vendor_name],
                    tax_classification=TaxClassification.UNKNOWN
                )
        return None
    
    def _match_keywords(self, text: str) -> List[CategoryMatch]:
        """Match text against keyword patterns"""
        matches = []
        
        for category, keywords in self.category_keywords.items():
            matched_keywords = []
            total_score = 0
            
            for keyword in keywords:
                if keyword.lower() in text:
                    matched_keywords.append(keyword)
                    # Weight longer keywords higher
                    total_score += len(keyword) / 10
            
            if matched_keywords:
                # Calculate confidence based on number and length of matches
                confidence = min(0.8, total_score / 10 + len(matched_keywords) * 0.1)
                
                matches.append(CategoryMatch(
                    category=category,
                    confidence=confidence,
                    matched_keywords=matched_keywords,
                    tax_classification=TaxClassification.UNKNOWN
                ))
        
        return matches
    
    def _detect_tax_classification(self, text: str) -> TaxClassification:
        """Detect tax classification from receipt text"""
        text_lower = text.lower()
        
        for pattern, tax_class in self.tax_indicators.items():
            if re.search(pattern, text_lower, re.IGNORECASE):
                return tax_class
        
        # Default classification based on Tashiro workflow
        # Food items typically have 10% tax
        if any(keyword in text_lower for keyword in ["食", "飲", "料理", "弁当"]):
            return TaxClassification.TAXABLE_10
            
        return TaxClassification.UNKNOWN
    
    def _apply_tashiro_rules(self, matches: List[CategoryMatch], 
                           text: str, amount: float) -> List[CategoryMatch]:
        """Apply Tashiro-specific business rules"""
        
        # Rule 1: Food items without tax indication default to 10% taxable
        for match in matches:
            if (match.category == ExpenseCategory.MEALS and 
                match.tax_classification == TaxClassification.UNKNOWN):
                match.tax_classification = TaxClassification.TAXABLE_10
                match.confidence += 0.1
        
        # Rule 2: Communication expenses are typically non-taxable
        for match in matches:
            if match.category == ExpenseCategory.COMMUNICATION:
                match.tax_classification = TaxClassification.NON_TAXABLE
        
        # Rule 3: High amounts likely to be accommodation or equipment
        if amount > 50000:  # Over 50,000 yen
            high_value_match = CategoryMatch(
                category=ExpenseCategory.ACCOMMODATION,
                confidence=0.6,
                matched_keywords=["高額取引"],
                tax_classification=TaxClassification.TAXABLE_10
            )
            matches.append(high_value_match)
        
        return matches
    
    def _deduplicate_matches(self, matches: List[CategoryMatch]) -> List[CategoryMatch]:
        """Remove duplicate category matches, keeping highest confidence"""
        seen_categories = {}
        
        for match in matches:
            category = match.category
            if (category not in seen_categories or 
                match.confidence > seen_categories[category].confidence):
                seen_categories[category] = match
        
        return list(seen_categories.values())
    
    def get_category_display_info(self, category: ExpenseCategory) -> Dict[str, str]:
        """Get display information for a category"""
        
        category_colors = {
            ExpenseCategory.MEALS: "#FF6B6B",
            ExpenseCategory.TRANSPORT: "#4ECDC4", 
            ExpenseCategory.COMMUNICATION: "#45B7D1",
            ExpenseCategory.ACCOMMODATION: "#96CEB4",
            ExpenseCategory.ENTERTAINMENT: "#FECA57",
            ExpenseCategory.SUPPLIES: "#FF9FF3",
            ExpenseCategory.UTILITIES: "#54A0FF",
            ExpenseCategory.RENT: "#5F27CD",
            ExpenseCategory.TAXES: "#00D2D3",
            ExpenseCategory.TRAVEL: "#FF9F43",
            ExpenseCategory.EQUIPMENT: "#1DD1A1",
            ExpenseCategory.MAINTENANCE: "#F0932B",
            ExpenseCategory.FUEL: "#EB4D4B",
            ExpenseCategory.INSURANCE: "#6C5CE7",
            ExpenseCategory.EDUCATION: "#A29BFE",
            ExpenseCategory.OTHER: "#95A5A6"
        }
        
        category_icons = {
            ExpenseCategory.MEALS: "🍽️",
            ExpenseCategory.TRANSPORT: "🚗", 
            ExpenseCategory.COMMUNICATION: "📱",
            ExpenseCategory.ACCOMMODATION: "🏨",
            ExpenseCategory.ENTERTAINMENT: "🎉",
            ExpenseCategory.SUPPLIES: "📎",
            ExpenseCategory.UTILITIES: "💡",
            ExpenseCategory.RENT: "🏢",
            ExpenseCategory.TAXES: "🏛️",
            ExpenseCategory.TRAVEL: "✈️",
            ExpenseCategory.EQUIPMENT: "💻",
            ExpenseCategory.MAINTENANCE: "🔧",
            ExpenseCategory.FUEL: "⛽",
            ExpenseCategory.INSURANCE: "🛡️",
            ExpenseCategory.EDUCATION: "📚",
            ExpenseCategory.OTHER: "📋"
        }
        
        return {
            "name": category.value,
            "color": category_colors.get(category, "#95A5A6"),
            "icon": category_icons.get(category, "📋"),
            "english_name": category.name.title()
        }


# Example usage and testing
if __name__ == "__main__":
    engine = ExpenseCategorizationEngine()
    
    # Test categorization
    test_cases = [
        ("マクドナルド 食事代 税込み1,200円", "マクドナルド", 1200),
        ("JR東日本 乗車券 新宿→東京", "JR東日本", 200),
        ("ホテルニューオータニ 宿泊費", "ホテルニューオータニ", 25000),
        ("通信費 携帯電話料金", "NTTドコモ", 8000),
    ]
    
    print("=== Tashiro Expense Categorization Test ===")
    
    for text, vendor, amount in test_cases:
        print(f"\nTesting: {text}")
        matches = engine.categorize_receipt(text, vendor, amount)
        
        for i, match in enumerate(matches[:2], 1):  # Show top 2 matches
            display_info = engine.get_category_display_info(match.category)
            print(f"  {i}. {display_info['icon']} {display_info['name']} "
                  f"({match.confidence:.1%} confidence)")
            print(f"     Tax: {match.tax_classification.value}")
            print(f"     Keywords: {', '.join(match.matched_keywords)}")


def calculate_taxed_total(subtotal, tax):
    try:
        return round(float(subtotal) + float(tax), 2)
    except:
        return None