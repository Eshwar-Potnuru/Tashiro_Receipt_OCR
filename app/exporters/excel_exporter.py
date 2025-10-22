import pandas as pd
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

class ExcelExporter:
    """Export receipt data to Excel format for Tashiro Ironworks workflow."""

    def __init__(self):
        self.base_dir = Path(__file__).parent.parent.parent
        self.artifacts_dir = self.base_dir / "artifacts"  # Fixed: was self.base_dir.parent / "artifacts"
        self.artifacts_dir.mkdir(exist_ok=True)

    def export_to_excel(self, receipt_data: Dict[str, Any], user_data: Dict[str, Any]) -> str:
        """Export receipt data to Excel file."""
        try:
            # Create filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"receipt_{timestamp}.xlsx"
            filepath = self.artifacts_dir / filename

            print(f"Generating Excel file: {filepath}")
            print(f"Artifacts directory: {self.artifacts_dir}")

            # Prepare data for Excel
            excel_data = self._prepare_excel_data(receipt_data, user_data)

            # Create Excel file with multiple sheets
            with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                # Main receipt data sheet
                main_df = pd.DataFrame([excel_data['main']])
                main_df.to_excel(writer, sheet_name='Receipt_Data', index=False)

                # Field mapping sheet (A-F specification)
                mapping_df = pd.DataFrame([excel_data['field_mapping']])
                mapping_df.to_excel(writer, sheet_name='Field_Mapping', index=False)

                # User information sheet
                user_df = pd.DataFrame([excel_data['user']])
                user_df.to_excel(writer, sheet_name='User_Info', index=False)

                # Raw OCR data sheet
                if 'ocr_text' in receipt_data:
                    ocr_df = pd.DataFrame({'OCR_Text': [receipt_data['ocr_text']]})
                    ocr_df.to_excel(writer, sheet_name='OCR_Raw', index=False)

            # Verify file was created
            if filepath.exists():
                file_size = filepath.stat().st_size
                print(f"Excel file created successfully: {filepath} ({file_size} bytes)")
            else:
                print(f"Excel file was not created: {filepath}")

            return str(filepath)

        except Exception as e:
            print(f"Excel export failed: {e}")
            import traceback
            traceback.print_exc()
            raise

    def _prepare_excel_data(self, receipt_data: Dict[str, Any], user_data: Dict[str, Any]) -> Dict[str, Dict]:
        """Prepare data structure for Excel export."""

        # Main receipt data
        main_data = {
            'Submission_Date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'Receipt_Date': receipt_data.get('date', ''),
            'Vendor_Store': receipt_data.get('vendor', ''),
            'Total_Amount': receipt_data.get('total', ''),
            'Currency': receipt_data.get('currency', 'JPY'),
            'Invoice_Number': receipt_data.get('invoice_number', ''),
            'Tax_Category': receipt_data.get('tax_category', ''),
            'Account_Title': receipt_data.get('account_title', ''),
            'Subtotal': receipt_data.get('subtotal', ''),
            'Tax_Amount': receipt_data.get('tax', ''),
            'Verification_Status': 'Verified',
            'Processing_Status': 'Ready for Review'
        }

        # Field mapping (A-F specification)
        field_mapping = {
            'A_Date': receipt_data.get('date', ''),
            'B_Store_Name': receipt_data.get('vendor', ''),
            'C_Total_Amount': receipt_data.get('total', ''),
            'D_Invoice_Number': receipt_data.get('invoice_number', ''),
            'E_Tax_Category': receipt_data.get('tax_category', ''),
            'F_Account_Title': receipt_data.get('account_title', ''),
            'Reference_Subtotal': receipt_data.get('subtotal', ''),
            'Reference_Tax': receipt_data.get('tax', ''),
            'Reference_Currency': receipt_data.get('currency', 'JPY')
        }

        # User information
        user_info = {
            'Operator_Name': user_data.get('name', ''),
            'Operator_Email': user_data.get('email', ''),
            'Employee_ID': user_data.get('id', ''),
            'Submission_Time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'IP_Address': '',  # Could be added later
            'Device_Type': 'Mobile/Desktop'  # Could be detected
        }

        return {
            'main': main_data,
            'field_mapping': field_mapping,
            'user': user_info
        }