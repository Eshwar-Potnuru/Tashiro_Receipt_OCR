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
            # Validate receipt has required fields for location write
            if not receipt.business_location_id:
                error_msg = "business_location_id is required for location ledger write"
                self.logger.error(error_msg)
                return {"status": "error", "error": error_msg, "location": None}
            
            if not receipt.receipt_date:
                error_msg = "receipt_date is required for location ledger write"
                self.logger.error(error_msg)
                return {"status": "error", "error": error_msg, "location": receipt.business_location_id}
            
            self.logger.info(f"Location write starting: location={receipt.business_location_id}, date={receipt.receipt_date}")
            
            target_path = self.template_loader.ensure_location_workbook(receipt.business_location_id)
            self.logger.info(f"Target workbook path: {target_path}")
            
            # Try to open workbook; if corrupted, delete and recreate
            try:
                wb = self.repository.open(target_path)
                self.logger.info(f"Successfully opened workbook: {target_path}")
            except (KeyError, Exception) as open_err:
                # File is corrupted, delete and recreate from template
                self.logger.warning(f"Corrupted workbook detected: {open_err}, recreating from template")
                try:
                    target_path.unlink(missing_ok=True)
                    self.logger.info(f"Deleted corrupted workbook: {target_path}")
                except Exception as del_err:
                    self.logger.error(f"Failed to delete corrupted workbook: {del_err}")
                target_path = self.template_loader.ensure_location_workbook(receipt.business_location_id)
                self.logger.info(f"Recreated workbook at: {target_path}")
                wb = self.repository.open(target_path)

            sheet_name = self._month_sheet_name(receipt.receipt_date)
            alternate_sheet_names = self._month_sheet_aliases(receipt.receipt_date)
            
            self.logger.info(f"Receipt date: {receipt.receipt_date}, target sheet: {repr(sheet_name)}")
            
            # Use accumulator-style sheet resolution: duplicate from existing sheet if needed
            ws = self._get_or_create_month_sheet(wb, sheet_name, alternate_sheet_names)
            
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
            error_msg = f"Validation error in location writer: {ve}"
            self.logger.error(error_msg, exc_info=True)
            raise
        except Exception as exc:
            error_msg = f"Failed to write receipt to location: {str(exc)}"
            self.logger.exception(error_msg, extra={"location": receipt.business_location_id})
            return {"status": "error", "error": error_msg, "location": receipt.business_location_id}
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

    def _month_sheet_aliases(self, receipt_date: Optional[str]) -> list[str]:
        if not receipt_date:
            return []
        try:
            dt = datetime.fromisoformat(receipt_date)
        except Exception:
            return []
        year = dt.year
        month = dt.month
        return [
            f"{year}{month:02d}",
            f"{year}-{month:02d}",
            f"{year}/{month:02d}",
            f"{year}年{month}月分",
            f"{year}年{month}月度",
        ]
    
    def _get_or_create_month_sheet(self, wb, target_name: str, alternate_names: Optional[list[str]] = None):
        """Get existing month sheet or create from external clean template ONLY.
        
        NEVER duplicates from existing workbook sheets to prevent data corruption.
        """
        self.logger.info(f"Workbook sheets: {[repr(s) for s in wb.sheetnames]}")
        self.logger.info(f"Looking for sheet: {repr(target_name)}")
        candidates = [target_name]
        if alternate_names:
            for name in alternate_names:
                if name not in candidates:
                    candidates.append(name)

        for name in candidates:
            if name in wb.sheetnames:
                self.logger.info(f"Found existing sheet '{name}'")
                return wb[name]
        
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
        key_cols = (1, 3, 4, 6, 7, 8, 9, 10, 12)  # Important data columns used to detect empty rows
        
        self.logger.info(f"Finding next empty row in sheet '{ws.title}', starting from row {data_start}")
        
        # Find footer row to know where to stop scanning
        footer_row = None
        # Always scan at least one data row when workbook is mostly empty
        search_limit = max(data_start + 1, min(ws.max_row + 1, data_start + 100))
        
        for row in range(data_start, search_limit):
            for col in range(1, min(ws.max_column + 1, 20)):
                cell_val = ws.cell(row=row, column=col).value
                if cell_val and isinstance(cell_val, str):
                    if "合計" in cell_val or "残高" in cell_val:
                        footer_row = row
                        self.logger.info(f"Found footer row at {row}: {cell_val}")
                        break
            if footer_row:
                break
        
        # Ensure we scan a reasonable block even if max_row is small (fresh workbook)
        max_scan = footer_row - 1 if footer_row else max(data_start + 50, ws.max_row)
        if max_scan < data_start:
            max_scan = data_start + 50
        
        self.logger.info(f"Scanning rows {data_start} to {max_scan} for empty row")
        
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
        """Detect duplicate invoice numbers without writing them to cells.

        We scan the entire sheet for a matching invoice string (case-insensitive)
        so legacy rows that still contain invoice numbers remain protected, while
        new rows avoid writing invoice text per Phase 5F requirements.
        """

        if not invoice_number:
            return False
        target = str(invoice_number).strip().lower()
        for row in range(1, ws.max_row + 1):
            for col in range(1, ws.max_column + 1):
                cell_val = ws.cell(row=row, column=col).value
                if cell_val is None:
                    continue
                if str(cell_val).strip().lower() == target:
                    return True
        return False

    def _write_row(self, ws, row_idx: int, receipt: Receipt) -> None:
        staff_display = self._resolve_staff_name(receipt)
        description = self._compose_description(receipt)
        
        # Resolve dynamic column indices by header labels (fallback to expected columns)
        pay_date_col = self._find_column_by_header(ws, ["支払日", "支払い日", "日付", "精算日"], default_col=1)
        vendor_col = self._find_column_by_header(ws, ["摘要", "店舗", "店名", "ショップ", "取引先"], default_col=3)
        staff_col = self._find_column_by_header(ws, ["担当", "担当者", "責任者", "Staff"], default_col=4)
        invoice_flag_col = self._find_column_by_header(ws, ["インボ", "invoice", "インボイス", "適格"], default_col=7)
        account_col = self._find_column_by_header(ws, ["勘定科目", "科目", "account"], default_col=8)
        expense_col = self._find_column_by_header(ws, ["支出", "出金", "金額"], default_col=6)
        tax10_col = self._find_column_by_header(ws, ["10%", "１０％", "10％"], default_col=11)  # Column K
        tax8_col = self._find_column_by_header(ws, ["8%", "８％", "8％", "軽減"], default_col=12)  # Column L
        # NOTE: Column N (14) contains formula =IF(K+L+M=0,"",K+L+M) for automatic tax sum
        # Do NOT write total_amount to Column N; let the formula calculate it from K+L+M

        # Build mapping with required changes from Reiha feedback
        mapping = {}

        # 支払日 (keep existing behavior if header present)
        if pay_date_col:
            mapping[pay_date_col] = receipt.receipt_date

        # 店名 / 摘要 → Column C (or detected vendor/description column)
        mapping[vendor_col] = description

        # 担当者 → existing staff column
        mapping[staff_col] = staff_display

        # 勘定科目
        if account_col:
            mapping[account_col] = receipt.account_title

        # Invoice flag Yes/No only (never write invoice number)
        invoice_header_value = self._get_header_value(ws, invoice_flag_col)
        has_invoice = bool(receipt.invoice_number)
        invoice_flag = self._invoice_flag_text(invoice_header_value, has_invoice)
        mapping[invoice_flag_col] = invoice_flag

        # Column K (非課税額) must be blank → do nothing

        # Tax amounts: write raw OCR values (no multipliers)
        # Column K: 10% tax, Column L: 8% tax
        if tax10_col and tax10_col != invoice_flag_col:  # avoid clobbering the flag column
            mapping[tax10_col] = receipt.tax_10_amount
        if tax8_col:
            mapping[tax8_col] = receipt.tax_8_amount

        # 支出 (expense/total amount as printed on receipt)
        if expense_col:
            mapping[expense_col] = receipt.total_amount
        # Column N (tax sum formula) is auto-calculated from K+L+M; do not write to it

        self.logger.info(f"Writing to row {row_idx}")
        for col_idx, value in mapping.items():
            if value is not None:
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

    def _find_column_by_header(self, ws, candidates, default_col: Optional[int]) -> Optional[int]:
        """Find a column index by searching header labels (top 10 rows)."""

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
        """Return Yes/No or 有/無 depending on template language."""

        if header_value and any(tok in header_value for tok in ["有", "無", "有無"]):
            return "有" if has_invoice else "無"
        return "Yes" if has_invoice else "No"

    def _resolve_staff_name(self, receipt: Receipt) -> Optional[str]:
        loc = receipt.business_location_id
        if not loc or not receipt.staff_id:
            return receipt.staff_id
        staff_list = self.config_service.get_staff_for_location(loc) or []
        for staff in staff_list:
            if staff.get("id") == receipt.staff_id:
                return staff.get("name") or receipt.staff_id
        return receipt.staff_id

    def _compose_description(self, receipt: Receipt) -> Optional[str]:
        if receipt.vendor_name and receipt.memo:
            return f"{receipt.vendor_name} / {receipt.memo}"
        return receipt.vendor_name or receipt.memo

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
