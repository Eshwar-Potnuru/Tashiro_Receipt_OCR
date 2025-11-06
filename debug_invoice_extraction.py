#!/usr/bin/env python3
"""
Debug script for testing invoice number extraction improvements
"""

from app.extractors.field_extractors import FieldExtractor
import os

def test_invoice_extraction():
    """Test invoice number extraction with sample receipts."""
    extractor = FieldExtractor()

    test_files = ['Reciept_01.png', 'Reciept_02.png']
    for filename in test_files:
        if os.path.exists(filename):
            print(f'\n🧪 Testing Invoice Extraction: {filename}')
            print('=' * 50)

            try:
                with open(filename, 'rb') as f:
                    image_data = f.read()

                # Extract fields
                result = extractor.extract_fields(image_data, filename)

                print(f'📄 Invoice Number: {result.get("invoice_number", "N/A")}')
                print(f'🏪 Vendor: {result.get("vendor", "N/A")}')
                print(f'💰 Total: ¥{result.get("total", "N/A")}')
                print(f'🧾 Tax: ¥{result.get("tax", "N/A")}')
                print(f'📊 Subtotal: ¥{result.get("subtotal", "N/A")}')

            except Exception as e:
                print(f'❌ Error: {e}')
        else:
            print(f'\n⚠️ {filename} not found')

def test_specific_invoice_patterns():
    """Test specific invoice patterns."""
    print('\n🔍 Testing Invoice Pattern Recognition')
    print('=' * 50)

    extractor = FieldExtractor()

    # Test various invoice patterns
    test_lines = [
        "伝票番号: T-001",
        "レシートNo.: R123456",
        "注文番号 789012",
        "INVOICE: INV-2025-001",
        "登録番号 T7380001003643",
        "No. 456789",
        "伝票: ABC123",
        "レシート 010",  # This should be avoided
        "小計 ¥940",    # This should be avoided
        "合計 ¥1560",   # This should be avoided
    ]

    for line in test_lines:
        result = extractor._extract_invoice([line])
        status = "✅" if result else "❌"
        print(f'{status} "{line}" -> "{result}"')

if __name__ == "__main__":
    test_specific_invoice_patterns()
    test_invoice_extraction()