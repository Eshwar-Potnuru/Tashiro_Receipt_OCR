#!/usr/bin/env python3
"""
Fix OCR import issues in multi_engine_ocr.py
"""

import re

def fix_multi_engine_ocr():
    """Fix the import issues in multi_engine_ocr.py"""
    file_path = r"app\ocr\multi_engine_ocr.py"
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Replace all instances of OCRSpaceAPI with OCRSpaceOCR
        content = content.replace('OCRSpaceAPI', 'OCRSpaceOCR')
        content = content.replace('from app.ocr.ocr_space_api import OCRSpaceOCR', 'from app.ocr.ocr_space_ocr import OCRSpaceOCR')
        
        # Write back the fixed content
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("✅ Fixed multi_engine_ocr.py imports")
        return True
        
    except Exception as e:
        print(f"❌ Error fixing multi_engine_ocr.py: {e}")
        return False

if __name__ == "__main__":
    print("Fixing OCR import issues...")
    if fix_multi_engine_ocr():
        print("🎉 All imports fixed successfully!")
    else:
        print("💥 Some imports failed to fix")