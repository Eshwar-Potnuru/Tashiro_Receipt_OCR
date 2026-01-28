"""Location ledger writer (Format 02) for Phase 3B."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, Optional

from app.excel.excel_template_loader import ExcelTemplateLoader
from app.excel.excel_repository import ExcelRepository
from app.excel.insertion_rules import InsertionRules
from app.services.config_service import ConfigService
from app.models.schema import Receipt


class BranchLedgerWriter:
    """Write receipts into business location monthly sheets (Format 02)."""

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
        """Write a single receipt; returns per-receipt result dict."""
        try:
            target_path = self.template_loader.ensure_location_workbook(receipt.business_location_id)
            
            # Try to open workbook; if corrupted, delete and recreate
            try:
                wb = self.repository.open(target_path)
            except (KeyError, Exception) as open_err:
                # File is corrupted, delete and recreate from template
                self.logger.warning(f"Corrupted workbook detected: {open_err}, recreating from template")
                try:
                    target_path.unlink(missing_ok=True)
                except Exception:
                    pass
                target_path = self.template_loader.ensure_location_workbook(receipt.business_location_id)
                wb = self.repository.open(target_path)

            sheet_name = self._month_sheet_name(receipt.receipt_date)
            
            self.logger.info(f"Receipt date: {receipt.receipt_date}, target sheet: {repr(sheet_name)}")
            
            # Use accumulator-style sheet resolution: duplicate from existing sheet if needed
            ws = self._get_or_create_month_sheet(wb, sheet_name)
            
            self.logger.info(f"Using sheet '{ws.title}' for {sheet_name}")

            if self._is_duplicate(ws, receipt.invoice_number):
                self.logger.warning(f"Skipping duplicate invoice: {receipt.invoice_number}")
                wb.close()
                return {"status": "skipped_duplicate", "location": receipt.business_location_id}

            # Find the next empty row to write to (NO ROW INSERTION)
            write_row = self._find_next_empty_row(ws)
            
            self.logger.info(f"Writing to row {write_row} (no row insertion)")
            
            # Write data directly to the empty row - DO NOT INSERT ROWS
            # The template already has empty rows with formulas in place
            self._write_row(ws, write_row, receipt)
            
            self.logger.info(f"Wrote receipt to row {write_row} in sheet '{ws.title}'")

            # Save workbook
            self.logger.info(f"Saving workbook to {target_path}")
            try:
                self.repository.save(wb, target_path, is_staff=False)
                self.logger.info(f"Successfully saved workbook")
            except PermissionError as pe:
                self.logger.error(f"Permission denied saving {target_path} - file may be open in Excel")
                raise ValueError(f"Cannot save {target_path.name} - please close it in Excel") from pe
            
            return {"status": "written", "location": receipt.business_location_id, "row": write_row}
        except ValueError as ve:
            # Re-raise validation errors
            self.logger.error(f"Validation error: {ve}")
            raise
        except Exception as exc:
            self.logger.exception("Failed to write receipt", extra={"location": receipt.business_location_id})
            return {"status": "error", "error": str(exc), "location": receipt.business_location_id}
        finally:
            try:
                wb.close()  # type: ignore
            except Exception:
                pass

    # -----------------
    # Internals
    # -----------------
    def _month_sheet_name(self, receipt_date: Optional[str]) -> str:
        if not receipt_date:
            raise ValueError("receipt_date is required for month resolution")
        try:
            dt = datetime.fromisoformat(receipt_date)
        except Exception as exc:
            raise ValueError(f"Invalid receipt_date: {receipt_date}") from exc
        return f"{dt.year}年{dt.month}月"
    
    def _get_or_create_month_sheet(self, wb, target_name: str):
        """Get existing month sheet or create from external clean template ONLY.
        
        NEVER duplicates from existing workbook sheets to prevent data corruption.
        """
        self.logger.info(f"Workbook sheets: {[repr(s) for s in wb.sheetnames]}")
        self.logger.info(f"Looking for sheet: {repr(target_name)}")
        
        # If exact sheet exists, use it directly
        if target_name in wb.sheetnames:
            self.logger.info(f"Found existing sheet '{target_name}'")
            return wb[target_name]
        
        # Create new sheet from external clean template
        self.logger.info(f"Creating '{target_name}' from external template")
        new_ws = self.template_loader.create_month_sheet_from_template(wb, target_name)
        return new_ws
    
    def _find_next_empty_row(self, ws) -> int:
        """Find the next empty row in the table to write to.
        
        The template has a fixed table structure with rows already in place.
        We just need to find the first empty row and write to it.
        NO row insertion - just fill existing empty rows.
        
        Returns:
            Row number (1-based) of the first empty row ready for data
        """
        data_start = 6  # First data row in the template
        key_cols = (1, 3, 4, 6)  # A=支払日, C=摘要, D=担当者, F=支出
        
        # Find footer row to know where to stop scanning
        footer_row = None
        search_limit = min(ws.max_row + 1, data_start + 100)
        
        for row in range(data_start, search_limit):
            for col in range(1, min(ws.max_column + 1, 20)):
                cell_val = ws.cell(row=row, column=col).value
                if cell_val and isinstance(cell_val, str):
                    if "合計" in cell_val or "残高" in cell_val:
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
                self.logger.info(f"Found empty row at {row}")
                return row
        
        # If no empty row found, use the row right before footer
        if footer_row:
            self.logger.warning(f"No empty rows found, writing at {footer_row - 1} (before footer)")
            return footer_row - 1
        
        # Last resort: write at a reasonable row
        fallback = data_start + 10
        self.logger.warning(f"Could not determine empty row, using fallback {fallback}")
        return fallback

    def _is_duplicate(self, ws, invoice_number: Optional[str]) -> bool:
        if not invoice_number:
            return False
        target = str(invoice_number).strip().lower()
        for row in range(1, ws.max_row + 1):
            cell_val = ws.cell(row=row, column=8).value
            if cell_val is None:
                continue
            if str(cell_val).strip().lower() == target:
                return True
        return False

    def _write_row(self, ws, row_idx: int, receipt: Receipt) -> None:
        staff_display = self._resolve_staff_name(receipt)
        
        # Calculate tax-inclusive amounts from tax portions
        # If receipt.tax_XX_amount is the TAX portion, calculate tax-inclusive amount
        # For 10% tax: tax-inclusive = (tax / 0.10) + tax = tax * 11
        # For 8% tax: tax-inclusive = (tax / 0.08) + tax = tax * 13.5
        
        tax_10 = float(receipt.tax_10_amount) if receipt.tax_10_amount else 0
        tax_8 = float(receipt.tax_8_amount) if receipt.tax_8_amount else 0
        
        # Calculate tax-inclusive amounts (only if we have tax amounts)
        tax_10_inclusive = tax_10 * 11 if tax_10 > 0 else None
        tax_8_inclusive = tax_8 * 13.5 if tax_8 > 0 else None
        
        # Map to Excel columns - ONLY write data columns, NEVER formulas
        mapping = {
            1: receipt.receipt_date,          # A 支払日
            3: receipt.vendor_name,           # C 摘要
            4: staff_display,                 # D 担当者
            8: receipt.invoice_number,        # H インボイス (Fixed: was column G)
            9: tax_10_inclusive,              # I 10%税込額
            10: tax_8_inclusive,              # J 8%税込額
            11: None,                         # K 非課税額 (tax-exempt - not in Receipt model)
            12: receipt.total_amount,         # L 税込合計
            # M, N, O, P, Q, R are FORMULA columns - NEVER write to them
        }

        self.logger.info(f"Writing to row {row_idx}")
        for col_idx, value in mapping.items():
            if value is not None:  # Only write non-None values
                target_cell = ws.cell(row=row_idx, column=col_idx)
                target_cell.value = value
                self._inherit_style(ws, row_idx, col_idx)

    def _inherit_style(self, ws, row: int, col: int) -> None:
        """Copy style from the previous row in the same column when available."""
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
            # Silently ignore style inheritance errors - not critical
            pass

    def _resolve_staff_name(self, receipt: Receipt) -> Optional[str]:
        loc = receipt.business_location_id
        if not loc or not receipt.staff_id:
            return receipt.staff_id
        staff_list = self.config_service.get_staff_for_location(loc) or []
        for staff in staff_list:
            if staff.get("id") == receipt.staff_id:
                return staff.get("name") or receipt.staff_id
        return receipt.staff_id

    def _unmerge_row_range(self, ws, start_row: int, end_row: int) -> None:
        """Unmerge any cells that overlap with the specified row range."""
        merged_ranges = list(ws.merged_cells.ranges)
        for merged_range in merged_ranges:
            # Check if this merged range overlaps with our target rows
            if merged_range.min_row <= end_row and merged_range.max_row >= start_row:
                try:
                    ws.unmerge_cells(str(merged_range))
                    self.logger.info(f"Unmerged cells: {merged_range}")
                except Exception as e:
                    self.logger.warning(f"Failed to unmerge {merged_range}: {e}")
