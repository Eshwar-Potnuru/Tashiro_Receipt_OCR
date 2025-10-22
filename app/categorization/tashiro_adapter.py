#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tashiro Categorization Adapter
Integrates the Tashiro expense categorization engine with the existing pipeline
"""

from typing import Dict, Any, List, Optional
import logging

from app.categorization.expense_engine import (
    ExpenseCategorizationEngine, 
    CategoryMatch, 
    ExpenseCategory,
    TaxClassification
)

logger = logging.getLogger(__name__)

class TashiroCategorizer:
    """
    Adapter to integrate Tashiro expense categorization into the receipt pipeline
    """
    
    def __init__(self):
        self.engine = ExpenseCategorizationEngine()
    
    def categorize_receipt(self, raw_text: str, vendor: Optional[str] = None, 
                          total_amount: Optional[float] = None) -> Dict[str, Any]:
        """
        Categorize a receipt and return structured results
        
        Args:
            raw_text: Full OCR text from receipt
            vendor: Detected vendor name
            total_amount: Receipt total amount
            
        Returns:
            Dictionary with categorization results
        """
        try:
            # Get categorization matches
            matches = self.engine.categorize_receipt(
                ocr_text=raw_text,
                vendor_name=vendor or "",
                amount=total_amount or 0.0
            )
            
            if not matches:
                # Default to "Other" category if no matches found
                matches = [CategoryMatch(
                    category=ExpenseCategory.OTHER,
                    confidence=0.3,
                    matched_keywords=["未分類"],
                    tax_classification=TaxClassification.UNKNOWN
                )]
            
            primary_match = matches[0]
            
            # Get display information for primary category
            display_info = self.engine.get_category_display_info(primary_match.category)
            
            # Format categorization result
            result = {
                "primary_category": {
                    "category": primary_match.category.value,
                    "category_english": primary_match.category.name.title(),
                    "confidence": primary_match.confidence,
                    "color": display_info["color"],
                    "icon": display_info["icon"],
                    "tax_classification": primary_match.tax_classification.value,
                    "matched_keywords": primary_match.matched_keywords
                },
                "all_categories": [
                    {
                        "category": match.category.value,
                        "category_english": match.category.name.title(),
                        "confidence": match.confidence,
                        "color": self.engine.get_category_display_info(match.category)["color"],
                        "icon": self.engine.get_category_display_info(match.category)["icon"],
                        "tax_classification": match.tax_classification.value,
                        "matched_keywords": match.matched_keywords
                    }
                    for match in matches[:3]  # Top 3 matches
                ],
                "categorization_summary": {
                    "total_matches": len(matches),
                    "high_confidence_matches": len([m for m in matches if m.confidence > 0.7]),
                    "has_tax_info": any(m.tax_classification != TaxClassification.UNKNOWN for m in matches),
                    "vendor_matched": vendor is not None and len(vendor.strip()) > 0
                },
                "tashiro_workflow_data": {
                    "business_unit": self._determine_business_unit(raw_text, vendor),
                    "approval_level": self._determine_approval_level(total_amount or 0),
                    "journal_entry_code": self._get_journal_entry_code(primary_match.category),
                    "requires_receipt_attachment": True,
                    "processing_notes": self._generate_processing_notes(matches, raw_text)
                }
            }
            
            logger.info(f"Categorized receipt: {primary_match.category.value} "
                       f"({primary_match.confidence:.1%} confidence)")
            
            return result
            
        except Exception as e:
            logger.exception(f"Error categorizing receipt: {e}")
            
            # Return default categorization on error
            return {
                "primary_category": {
                    "category": "その他",
                    "category_english": "Other",
                    "confidence": 0.1,
                    "color": "#95A5A6",
                    "icon": "📋",
                    "tax_classification": "税区分不明",
                    "matched_keywords": ["エラー"]
                },
                "all_categories": [],
                "categorization_summary": {
                    "total_matches": 0,
                    "high_confidence_matches": 0,
                    "has_tax_info": False,
                    "vendor_matched": False
                },
                "tashiro_workflow_data": {
                    "business_unit": "未割り当て",
                    "approval_level": "要確認",
                    "journal_entry_code": "999",
                    "requires_receipt_attachment": True,
                    "processing_notes": "自動分類でエラーが発生しました。手動で確認してください。"
                }
            }
    
    def _determine_business_unit(self, text: str, vendor: Optional[str]) -> str:
        """Determine business unit based on text content"""
        
        # Business unit keywords based on Tashiro workflow
        unit_keywords = {
            "本社": ["本社", "東京", "HQ", "headquarters"],
            "営業部": ["営業", "sales", "商談", "クライアント"],
            "製造部": ["製造", "工場", "production", "材料"],
            "技術部": ["技術", "開発", "R&D", "research"],
            "管理部": ["管理", "admin", "人事", "総務"]
        }
        
        text_lower = text.lower()
        
        for unit, keywords in unit_keywords.items():
            if any(keyword.lower() in text_lower for keyword in keywords):
                return unit
        
        return "一般"  # Default unit
    
    def _determine_approval_level(self, amount: float) -> str:
        """Determine required approval level based on amount"""
        
        if amount >= 100000:  # 100,000 yen or more
            return "取締役承認"  # Director approval
        elif amount >= 50000:  # 50,000 yen or more
            return "部長承認"    # Department manager approval
        elif amount >= 10000:  # 10,000 yen or more
            return "課長承認"    # Section manager approval
        else:
            return "担当者処理"  # Staff processing
    
    def _get_journal_entry_code(self, category: ExpenseCategory) -> str:
        """Get journal entry code for accounting system"""
        
        # Journal entry codes based on Tashiro accounting system
        codes = {
            ExpenseCategory.MEALS: "611",          # 食費
            ExpenseCategory.TRANSPORT: "612",      # 交通費
            ExpenseCategory.COMMUNICATION: "613",  # 通信費
            ExpenseCategory.ACCOMMODATION: "614",  # 宿泊費
            ExpenseCategory.ENTERTAINMENT: "615",  # 接待費
            ExpenseCategory.SUPPLIES: "616",       # 消耗品費
            ExpenseCategory.UTILITIES: "617",      # 水道光熱費
            ExpenseCategory.RENT: "618",           # 地代家賃
            ExpenseCategory.TAXES: "619",          # 租税公課
            ExpenseCategory.TRAVEL: "620",         # 旅費
            ExpenseCategory.EQUIPMENT: "621",      # 備品費
            ExpenseCategory.MAINTENANCE: "622",    # 修繕費
            ExpenseCategory.FUEL: "623",           # 燃料費
            ExpenseCategory.INSURANCE: "624",      # 保険料
            ExpenseCategory.EDUCATION: "625",      # 研修費
            ExpenseCategory.OTHER: "699"           # その他
        }
        
        return codes.get(category, "699")
    
    def _generate_processing_notes(self, matches: List[CategoryMatch], raw_text: str) -> str:
        """Generate processing notes for the receipt"""
        
        notes = []
        
        if not matches:
            notes.append("自動分類できませんでした。")
        elif matches[0].confidence < 0.5:
            notes.append("分類の信頼度が低いため、確認が必要です。")
        
        # Check for mixed categories
        if len(matches) > 1 and matches[1].confidence > 0.4:
            notes.append(f"複数カテゴリの可能性: {matches[1].category.value}")
        
        # Check for special conditions
        if "レシート" not in raw_text and "領収書" not in raw_text:
            notes.append("正式な領収書ではない可能性があります。")
        
        # Tax information notes
        tax_matches = [m for m in matches if m.tax_classification != TaxClassification.UNKNOWN]
        if not tax_matches:
            notes.append("税区分情報が不明です。")
        
        return " ".join(notes) if notes else "正常に処理されました。"

# Integration function for existing pipeline
def add_tashiro_categorization(result_dict: Dict[str, Any], raw_text: str, 
                              vendor: Optional[str] = None, 
                              total_amount: Optional[float] = None) -> Dict[str, Any]:
    """
    Add Tashiro categorization to existing extraction result
    
    Args:
        result_dict: Existing extraction result dictionary
        raw_text: Full OCR text
        vendor: Detected vendor name
        total_amount: Receipt total amount
        
    Returns:
        Enhanced result dictionary with categorization
    """
    try:
        categorizer = TashiroCategorizer()
        categorization = categorizer.categorize_receipt(raw_text, vendor, total_amount)
        
        # Add categorization to result
        result_dict.update({
            "tashiro_categorization": categorization,
            "expense_category": categorization["primary_category"]["category"],
            "expense_confidence": categorization["primary_category"]["confidence"],
            "tax_classification": categorization["primary_category"]["tax_classification"],
            "business_unit": categorization["tashiro_workflow_data"]["business_unit"],
            "approval_level": categorization["tashiro_workflow_data"]["approval_level"]
        })
        
        return result_dict
        
    except Exception as e:
        logger.exception(f"Failed to add Tashiro categorization: {e}")
        return result_dict