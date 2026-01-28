#!/usr/bin/env python3
"""
Edge case testing - Ensure system handles various scenarios properly
"""

import template_formatter
import openpyxl
from pathlib import Path

def test_edge_cases():
    """Test various edge cases and error scenarios."""
    
    print("🧪 EDGE CASE TESTING")
    print("=" * 50)
    
    test_results = []
    
    # 1. Test duplicate detection
    print("1️⃣ TESTING DUPLICATE DETECTION")
    print("-" * 30)
    
    duplicate_data = {
        'date': '2024-11-19',
        'amount': 5555,
        'description': '重複テスト',
        'invoice_number': 'DUPLICATE-TEST-555'
    }
    
    # First append (should succeed)
    result1 = template_formatter.append_to_formatted_template(
        duplicate_data, 'Tokyo', {'name': '重複テスト1'}
    )
    
    if result1.get('status') == 'success':
        print("✅ First append successful")
        
        # Second append with same invoice (should be blocked)
        result2 = template_formatter.append_to_formatted_template(
            duplicate_data, 'Tokyo', {'name': '重複テスト2'}
        )
        
        if result2.get('status') == 'duplicate':
            print("✅ Duplicate detection working")
            test_results.append("✅ Duplicate detection")
        else:
            print(f"❌ Duplicate not detected: {result2.get('status')}")
            test_results.append("❌ Duplicate detection failed")
            
        # Third append with force flag (should succeed)
        result3 = template_formatter.append_to_formatted_template(
            duplicate_data, 'Tokyo', {'name': '重複テスト3'}, force=True
        )
        
        if result3.get('status') == 'success':
            print("✅ Force flag working")
            test_results.append("✅ Force flag working")
        else:
            print(f"❌ Force flag not working: {result3.get('status')}")
            test_results.append("❌ Force flag failed")
    else:
        print(f"❌ Initial append failed: {result1.get('status')}")
        test_results.append("❌ Basic append failed")
    
    # 2. Test with minimal data
    print("\n2️⃣ TESTING MINIMAL DATA")
    print("-" * 30)
    
    minimal_data = {
        'amount': 100,
        'invoice_number': 'MIN-001'
    }
    
    result = template_formatter.append_to_formatted_template(
        minimal_data, 'Tokyo', {'name': 'ミニマルテスト'}
    )
    
    if result.get('status') == 'success':
        print("✅ Minimal data handled correctly")
        test_results.append("✅ Minimal data handling")
    else:
        print(f"❌ Minimal data failed: {result.get('status')}")
        test_results.append("❌ Minimal data handling failed")
    
    # 3. Test with Japanese characters
    print("\n3️⃣ TESTING JAPANESE CHARACTERS")
    print("-" * 30)
    
    japanese_data = {
        'date': '2024-11-19',
        'amount': 2500,
        'description': '日本語文字テスト・特殊文字！＠＃',
        'vendor_name': 'テスト商店（株）',
        'invoice_number': 'JPN-テスト-001'
    }
    
    result = template_formatter.append_to_formatted_template(
        japanese_data, 'Tokyo', {'name': '日本語テスト'}
    )
    
    if result.get('status') == 'success':
        print("✅ Japanese characters handled correctly")
        test_results.append("✅ Japanese character handling")
        
        # Verify the data was written correctly
        tokyo_file = Path('app/Data/accumulation/Tokyo_Accumulated.xlsx')
        wb = openpyxl.load_workbook(tokyo_file)
        ws = wb['2025年11月']
        
        row_num = result.get('row_number')
        written_desc = ws.cell(row_num, 3).value  # Column C
        
        if written_desc and '日本語文字テスト' in str(written_desc):
            print("✅ Japanese data verification successful")
            test_results.append("✅ Japanese data verification")
        else:
            print(f"❌ Japanese data not written correctly: {written_desc}")
            test_results.append("❌ Japanese data verification failed")
        
        wb.close()
    else:
        print(f"❌ Japanese characters failed: {result.get('status')}")
        test_results.append("❌ Japanese character handling failed")
    
    # 4. Test invalid location
    print("\n4️⃣ TESTING INVALID LOCATION")
    print("-" * 30)
    
    try:
        result = template_formatter.append_to_formatted_template(
            {'amount': 100}, 'InvalidLocation', {'name': 'テスト'}
        )
        print(f"❌ Should have failed but got: {result.get('status')}")
        test_results.append("❌ Invalid location not caught")
    except (ValueError, Exception) as e:
        print(f"✅ Invalid location properly rejected: {type(e).__name__}")
        test_results.append("✅ Invalid location handling")
    
    # 5. Test large amounts and numbers
    print("\n5️⃣ TESTING LARGE NUMBERS")
    print("-" * 30)
    
    large_data = {
        'date': '2024-11-19',
        'amount': 9999999999,  # Very large amount
        'description': '大きな数値テスト',
        'invoice_number': 'LARGE-999999999'
    }
    
    result = template_formatter.append_to_formatted_template(
        large_data, 'Tokyo', {'name': '大数値テスト'}
    )
    
    if result.get('status') == 'success':
        print("✅ Large numbers handled correctly")
        test_results.append("✅ Large number handling")
    else:
        print(f"❌ Large numbers failed: {result.get('status')}")
        test_results.append("❌ Large number handling failed")
    
    # Summary
    print("\n" + "=" * 50)
    print("🎯 EDGE CASE TEST SUMMARY")
    print("=" * 50)
    
    passed = sum(1 for result in test_results if result.startswith("✅"))
    total = len(test_results)
    
    print(f"\n📊 Results: {passed}/{total} tests passed")
    
    for result in test_results:
        print(f"   {result}")
    
    if passed == total:
        print(f"\n🎉 ALL EDGE CASES PASSED!")
        print("✅ System robust and ready for production")
    elif passed >= total * 0.8:
        print(f"\n⚠️  MOSTLY GOOD - {total - passed} issues need attention")
    else:
        print(f"\n❌ MULTIPLE ISSUES - Review needed")
    
    return passed == total

if __name__ == "__main__":
    all_passed = test_edge_cases()
    if all_passed:
        print("\n🚀 EDGE CASE TESTING COMPLETE - SYSTEM ROBUST!")
    else:
        print("\n🔧 EDGE CASE ISSUES - REVIEW NEEDED")