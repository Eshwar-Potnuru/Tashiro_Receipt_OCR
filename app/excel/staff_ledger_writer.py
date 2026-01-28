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
        
        Staff sheet has the same structure as location sheet.
        We just need to find the first empty row and write to it.
        NO row insertion - just fill existing empty rows.
        
        Returns:
            Row number (1-based) of the first empty row ready for data
        """
        data_start = 3  # First data row in staff template
        key_cols = (1, 2, 4, 7, 9, 10, 12)  # A=staff, B=date, D=vendor, G=invoice, I/J=tax, L=total
        
        # Find footer row to know where to stop scanning
        footer_row = None
        search_limit = min(ws.max_row + 1, data_start + 100)
        
        for row in range(data_start, search_limit):
            for col in range(1, min(ws.max_column + 1, 20)):
                cell_val = ws.cell(row=row, column=col).value
                if cell_val and isinstance(cell_val, str):
                    if "合計" in cell_val:
                        footer_row = row
                        break
            if footer_row:
                break
        
        max_scan = footer_row - 1 if footer_row else min(data_start + 50, ws.max_row)
        
        # Scan from data_start to find first completely empty row
        for row in range(data_start, max_scan + 1):
            is_empty = True
            for col in key_cols:
                val = ws.cell(row=row, column=col).value
                if val not in (None, "", " "):
                    is_empty = False
                    break
            
            if is_empty:
                self.logger.info(f"Staff: Found empty row at {row}")
                return row
        
        # If no empty row found, use the row right before footer
        if footer_row:
            self.logger.warning(f"Staff: No empty rows found, writing at {footer_row - 1} (before footer)")
            return footer_row - 1
        
        # Last resort: write at a reasonable row
        fallback = data_start + 10
        self.logger.warning(f"Staff: Could not determine empty row, using fallback {fallback}")
        return fallback

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
        
        # Calculate tax-inclusive amounts from tax portions (same as location sheet)
        tax_10 = float(receipt.tax_10_amount) if receipt.tax_10_amount else 0
        tax_8 = float(receipt.tax_8_amount) if receipt.tax_8_amount else 0
        
        # Calculate tax-inclusive amounts (only if we have tax amounts)
        tax_10_inclusive = tax_10 * 11 if tax_10 > 0 else None
        tax_8_inclusive = tax_8 * 13.5 if tax_8 > 0 else None
        
        # Map to Excel columns - ONLY write data columns, NEVER formulas
        mapping = {
            1: receipt.receipt_date,      # A Payment date
            2: description,               # B Description/vendor
            6: receipt.invoice_number,    # F Invoice number
            8: tax_10_inclusive,          # H 10% tax-inclusive amount
            9: tax_8_inclusive,           # I 8% tax-inclusive amount
            11: receipt.total_amount,     # K Tax-included total
            # N, P, Q, R are FORMULA columns - NEVER write to them
        }

        self.logger.info(f"Writing staff data to row {row_idx}")
        for col_idx, value in mapping.items():
            if value is not None:
                target_cell = ws.cell(row=row_idx, column=col_idx)
                target_cell.value = value
                self._inherit_style(ws, row_idx, col_idx)

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
