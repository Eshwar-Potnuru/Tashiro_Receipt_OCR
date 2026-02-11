"""Individual staff ledger writer (Format 01) for Phase 3C."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, Optional

from app.excel.excel_template_loader import ExcelTemplateLoader
from app.excel.excel_repository import ExcelRepository
from app.excel.insertion_rules import InsertionRules
from app.models.schema import Receipt
from app.services.config_service import ConfigService


class StaffLedgerWriter:
    """Write receipts into per-staff monthly ledgers (Format 01)."""

    def __init__(
        self,
        *,
        template_loader: Optional[ExcelTemplateLoader] = None,
        repository: Optional[ExcelRepository] = None,
        insertion_rules: Optional[InsertionRules] = None,
        config_service: Optional[ConfigService] = None,
    ) -> None:
        self.template_loader = template_loader or ExcelTemplateLoader()
        self.repository = repository or ExcelRepository()
        self.insertion_rules = insertion_rules or InsertionRules()
        self.config_service = config_service or ConfigService()
        self.logger = logging.getLogger(__name__)

    def write_receipt(self, receipt: Receipt) -> Dict[str, object]:
        if not receipt.staff_id:
            return {"status": "skipped_missing_staff_id", "reason": "staff_id required", "receipt_id": str(receipt.receipt_id)}

        wb = None
        try:
            staff_display = self._resolve_staff_name(receipt)
            target_path = self.template_loader.ensure_staff_workbook(
                staff_name=staff_display or receipt.staff_id,
                location_id=receipt.business_location_id or "unknown",
                staff_id=receipt.staff_id,
            )
            wb = self.repository.open(target_path)

            sheet_name = self._target_sheet_name(receipt.receipt_date)
            resolved_sheet = self._ensure_month_sheet(wb, sheet_name)
            ws = wb[resolved_sheet]

            # Find next empty row to fill (NO ROW INSERTION)
            # Same logic as location sheet - just fill existing empty rows
            write_row = self._find_next_empty_row(ws)
            self.logger.info(f"Staff sheet '{resolved_sheet}' write_row: {write_row}, max_row: {ws.max_row} (no insertion)")
            
            # Write data directly to the empty row - DO NOT INSERT ROWS
            # The template already has empty rows with formulas in place
            self._write_row(ws, write_row, receipt)

            self.repository.save(wb, target_path, is_staff=True)
            return {
                "status": "written",
                "staff": receipt.staff_id,
                "sheet": resolved_sheet,
                "row": write_row,
            }
        except Exception as exc:
            self.logger.exception("Failed to write staff ledger", extra={"staff": receipt.staff_id})
            return {"status": "error", "error": str(exc), "staff": receipt.staff_id}
        finally:
            try:
                if wb:
                    wb.close()
            except Exception:
                pass

    # -----------------
    # Internals
    # -----------------
    def _target_sheet_name(self, receipt_date: Optional[str]) -> str:
        try:
            dt = datetime.fromisoformat(receipt_date) if receipt_date else datetime.now()
        except Exception:
            dt = datetime.now()
        return f"{dt.year}{dt.month:02d}"

    def _ensure_month_sheet(self, workbook, target_sheet: str) -> str:
        existing = self._match_existing_sheet(workbook, target_sheet)
        if existing:
            return existing

        source_name = "原本" if "原本" in workbook.sheetnames else workbook.sheetnames[0]
        source_sheet = workbook[source_name]
        duplicated = workbook.copy_worksheet(source_sheet)
        duplicated.title = target_sheet
        return target_sheet

    def _match_existing_sheet(self, workbook, target_sheet: str) -> Optional[str]:
        desired = self._sanitize_name(target_sheet)
        for name in workbook.sheetnames:
            if self._sanitize_name(name) == desired:
                return name
        return None

    @staticmethod
    def _sanitize_name(name: str) -> str:
        return "".join(str(name).split())

    def _find_next_empty_row(self, ws) -> int:
        """Find the next empty row in the table to write to.
        
        Staff sheet structure:
        - Row 1-2: Headers  
        - Row 3+: Data starts here
        - Last rows: Footer (合計)
        
        Logic (CORRECTED - CHECK FOR ACTUAL DATA VALUES):
        1. Scan forward from row 3
        2. Check if the row has ANY visible data (not just formulas)
        3. Find first row where ALL key columns are truly empty
        4. Stop before footer row
        
        Returns:
            Row number (1-based) of the first empty row ready for data
        """
        data_start = 3  # First data row in staff template
        key_cols = (1, 2, 3, 6, 7, 11, 12, 14)  # 担当者, 支払日, 摘要, invoice, total, tax columns
        
        # Find footer row to know where to stop scanning
        footer_row = None
        # Scan up to 200 rows minimum to find footer
        max_search = max(ws.max_row, data_start + 200)
        
        for row in range(data_start, min(max_search, 10000)):
            for col in range(1, min(ws.max_column + 1, 20)):
                cell = ws.cell(row=row, column=col)
                # Check the actual VALUE not just if cell exists
                cell_val = cell.value
                if cell_val and isinstance(cell_val, str):
                    if "合計" in cell_val or "残高" in cell_val or "計" == cell_val.strip():
                        footer_row = row
                        self.logger.info(f"Staff: Found footer at row {footer_row}")
                        break
            if footer_row:
                break
        
        if not footer_row:
            self.logger.warning(f"Staff: No footer found, using max_row={ws.max_row} + 50")
            footer_row = ws.max_row + 50
        
        # Scan forward from data_start to find first completely empty row
        # Focus on PRIMARY DATA columns that we write to (staff, date, vendor)
        # These should be truly empty if row is unused
        max_scan = footer_row - 1
        primary_cols = (1, 2, 3)  # Staff name, Date, Description - must be empty for unused row
        
        for row in range(data_start, max_scan + 1):
            is_empty = True
            # Check primary columns that contain actual user data (not formulas)
            for col in primary_cols:
                cell = ws.cell(row=row, column=col)
                val = cell.value
                
                # Use same logic as location writer - simple and proven
                if val not in (None, "", " "):
                    is_empty = False
                    break
            
            if is_empty:
                self.logger.info(f"Staff: Found empty row at {row}")
                return row
        
        # If no empty row found, write just before footer
        next_row = footer_row - 1
        self.logger.warning(f"Staff: No empty rows found, writing at {next_row} (before footer)")
        return next_row

    def _find_totals_row(self, ws) -> Optional[int]:
        for row in range(1, ws.max_row + 1):
            for col in range(1, ws.max_column + 1):
                value = ws.cell(row=row, column=col).value
                if isinstance(value, str) and value.strip() == "合計":
                    return row
        return None

    def _write_row(self, ws, row_idx: int, receipt: Receipt) -> None:
        staff_display = self._resolve_staff_name(receipt)
        description = self._compose_description(receipt)

        # Resolve dynamic column indices by header labels (fallback to expected columns)
        staff_col = self._find_column_by_header(ws, ["担当者", "担当", "Staff"], default_col=1)
        date_col = self._find_column_by_header(ws, ["支払日", "支払い日", "日付", "精算日", "Date"], default_col=2)
        account_col = self._find_column_by_header(ws, ["勘定科目", "科目", "account"], default_col=3)
        desc_col = self._find_column_by_header(ws, ["摘要", "内容", "Description", "取引先", "店"], default_col=4)
        invoice_flag_col = self._find_column_by_header(ws, ["インボ", "invoice", "インボイス", "適格"], default_col=8)
        expense_col = self._find_column_by_header(ws, ["支出", "出金", "金額"], default_col=6)
        # NOTE: Column N (14) contains formula =IF(K+L+M=0,"",K+L+M) for automatic tax sum
        # Do NOT look for total_col; let the formula calculate it from K+L+M
        tax10_col = self._find_column_by_header(ws, ["10%", "１０％", "10％"], default_col=11)  # Column K
        tax8_col = self._find_column_by_header(ws, ["8%", "８％", "8％", "軽減"], default_col=12)  # Column L

        # Map to Excel columns with raw OCR values (no tax-inclusive computations)
        mapping = {}

        if staff_col:
            mapping[staff_col] = staff_display
        if date_col:
            mapping[date_col] = receipt.receipt_date
        if account_col:
            mapping[account_col] = receipt.account_title
        if desc_col:
            mapping[desc_col] = description

        if invoice_flag_col:
            header_value = self._get_header_value(ws, invoice_flag_col)
            has_invoice = bool(receipt.invoice_number)
            mapping[invoice_flag_col] = self._invoice_flag_text(header_value, has_invoice)

        # Column E (収入) and Column G (empty) intentionally left untouched

        if expense_col:
            mapping[expense_col] = receipt.total_amount
        # Column N (tax sum formula) is auto-calculated; write K and L for tax amounts
        if tax10_col:
            mapping[tax10_col] = receipt.tax_10_amount
        if tax8_col:
            mapping[tax8_col] = receipt.tax_8_amount

        self.logger.info(f"Writing staff data to row {row_idx}")
        for col_idx, value in mapping.items():
            if value is not None:
                target_cell = ws.cell(row=row_idx, column=col_idx)
                target_cell.value = value
                self._inherit_style(ws, row_idx, col_idx)

    def _get_header_value(self, ws, col: Optional[int]) -> Optional[str]:
        if not col:
            return None
        max_rows = min(ws.max_row, 10)
        for row in range(1, max_rows + 1):
            val = ws.cell(row=row, column=col).value
            if isinstance(val, str) and val.strip():
                return val.strip()
        return None

    def _invoice_flag_text(self, header_value: Optional[str], has_invoice: bool) -> str:
        """Return invoice presence flag.
        
        Always returns Japanese: "有" (present) or "無" (absent)
        This matches Reiha's requirement for staff Excel column I (インボイス).
        """
        return "有" if has_invoice else "無"

    def _find_column_by_header(self, ws, candidates, default_col: Optional[int]) -> Optional[int]:
        """Locate a column by header text (top 10 rows)."""

        max_rows = min(ws.max_row, 10)
        for row in range(1, max_rows + 1):
            for col in range(1, ws.max_column + 1):
                val = ws.cell(row=row, column=col).value
                if not isinstance(val, str):
                    continue
                for cand in candidates:
                    if cand.lower() in val.lower():
                        return col
        return default_col

    def _inherit_style(self, ws, row: int, col: int) -> None:
        if row <= 1:
            return
        try:
            src = ws.cell(row=row - 1, column=col)
            dst = ws.cell(row=row, column=col)
            
            # Copy style properties safely
            if hasattr(src, 'font') and src.font:
                dst.font = src.font.copy() if hasattr(src.font, 'copy') else src.font
            if hasattr(src, 'fill') and src.fill:
                dst.fill = src.fill.copy() if hasattr(src.fill, 'copy') else src.fill
            if hasattr(src, 'border') and src.border:
                dst.border = src.border.copy() if hasattr(src.border, 'copy') else src.border
            if hasattr(src, 'alignment') and src.alignment:
                dst.alignment = src.alignment.copy() if hasattr(src.alignment, 'copy') else src.alignment
            if hasattr(src, 'number_format') and src.number_format:
                dst.number_format = src.number_format
        except Exception as e:
            # Silently ignore style inheritance errors
            pass

    def _resolve_staff_name(self, receipt: Receipt) -> Optional[str]:
        if not receipt.staff_id:
            return None
        if receipt.business_location_id:
            staff_list = self.config_service.get_staff_for_location(receipt.business_location_id)
            for staff in staff_list:
                if staff.get("id") == receipt.staff_id:
                    return staff.get("name") or receipt.staff_id
        return receipt.staff_id

    def _compose_description(self, receipt: Receipt) -> Optional[str]:
        if receipt.vendor_name and receipt.memo:
            return f"{receipt.vendor_name} / {receipt.memo}"
        return receipt.vendor_name or receipt.memo
