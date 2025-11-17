"""Per-location Excel accumulation utilities for Receipt OCR."""
from __future__ import annotations

import csv
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from validators import (
    get_available_locations,
    normalize_location,
    normalize_number,
    parse_date,
)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "app" / "Data"
ACCUM_DIR = DATA_DIR / "accumulation"
LOG_DIR = DATA_DIR / "submission_logs"
LOG_FILE = LOG_DIR / "submission_log.csv"
CANONICAL_HEADERS = [
    "Business Office",
    "Order Number",
    "Invoice Number",
    "Order Date",
    "Store Name",
    "Item Description",
    "Quantity",
    "Amount",
    "Tax Category",
    "Account Title",
    "Subtotal",
    "Tax Amount",
    "Currency",
    "Responsible Person",
    "Operator Full Name",
    "Operator Email",
    "Operator Employee ID",
    "Processed Timestamp",
    "Source File",
    "Notes",
]

LOG_HEADERS = [
    "timestamp",
    "location",
    "order_number",
    "invoice_number",
    "operator_name",
    "status",
    "file_path",
    "message",
]


def _ensure_directories() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    ACCUM_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)


def _prepare_row(data: Dict[str, Any], location: str, operator: Dict[str, Any]) -> Dict[str, Any]:
    order_date = parse_date(data.get("order_date") or data.get("date")) or data.get("order_date") or data.get("date") or ""
    order_number = normalize_number(data.get("order_number")) or normalize_number(data.get("invoice_number"))
    invoice_number = normalize_number(data.get("invoice_number"))
    processed_ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    row = {
        "Business Office": location,
        "Order Number": order_number or "",
        "Invoice Number": invoice_number or "",
        "Order Date": order_date,
        "Store Name": data.get("store_name") or data.get("client_name") or data.get("vendor") or "",
        "Item Description": data.get("item_description") or data.get("account_title") or "",
        "Quantity": data.get("quantity") or data.get("item_quantity") or "",
        "Amount": data.get("amount") or data.get("total") or data.get("subtotal") or "",
        "Tax Category": data.get("tax_category") or "",
        "Account Title": data.get("account_title") or "",
        "Subtotal": data.get("subtotal") or "",
        "Tax Amount": data.get("tax") or data.get("tax_amount") or "",
        "Currency": data.get("currency") or "",
        "Responsible Person": data.get("responsible_person") or data.get("staff_member") or "",
        "Operator Full Name": operator.get("name", ""),
        "Operator Email": operator.get("email", ""),
        "Operator Employee ID": operator.get("employee_id") or operator.get("id") or "",
        "Processed Timestamp": processed_ts,
        "Source File": data.get("source_file") or data.get("source_image") or data.get("queue_id") or "",
        "Notes": data.get("notes") or "",
    }

    # Guarantee all headers exist
    for header in CANONICAL_HEADERS:
        row.setdefault(header, "")
    return row


def _log_submission(status: str, location: str, row: Dict[str, Any], filepath: Path, message: str = "") -> None:
    """Append an entry into the submission log CSV."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    write_header = not LOG_FILE.exists()
    payload = {
        "timestamp": datetime.utcnow().isoformat(timespec="seconds"),
        "location": location,
        "order_number": row.get("Order Number", ""),
        "invoice_number": row.get("Invoice Number", ""),
        "operator_name": row.get("Operator Full Name", ""),
        "status": status,
        "file_path": str(filepath),
        "message": message,
    }
    with LOG_FILE.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LOG_HEADERS)
        if write_header:
            writer.writeheader()
        writer.writerow(payload)


def append_to_location(
    data: Dict[str, Any],
    location: str,
    operator: Dict[str, Any],
    *,
    force: bool = False,
) -> Dict[str, Any]:
    """Append a receipt row to the per-location accumulation workbook."""
    _ensure_directories()
    config = get_available_locations()
    normalized_location = normalize_location(location, config)
    if not normalized_location:
        raise ValueError(f"Unrecognized business location: {location}")

    filepath = ACCUM_DIR / f"{normalized_location}_Accumulated.xlsx"
    row = _prepare_row(data, normalized_location, operator)

    if filepath.exists():
        existing_df = pd.read_excel(filepath)
        if "Client Name" in existing_df.columns and "Store Name" not in existing_df.columns:
            existing_df = existing_df.rename(columns={"Client Name": "Store Name"})
    else:
        existing_df = pd.DataFrame(columns=CANONICAL_HEADERS)

    for header in CANONICAL_HEADERS:
        if header not in existing_df.columns:
            existing_df[header] = ""

    existing_df = existing_df[CANONICAL_HEADERS]

    def _has_duplicate(df: pd.DataFrame, row_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        order_no = row_data.get("Order Number")
        invoice_no = row_data.get("Invoice Number")
        if df.empty:
            return None
        if order_no and order_no in df.get("Order Number", pd.Series(dtype=str)).astype(str).values:
            record = df[df["Order Number"].astype(str) == order_no].iloc[0].to_dict()
            record["matched_on"] = "order_number"
            return record
        if invoice_no and invoice_no in df.get("Invoice Number", pd.Series(dtype=str)).astype(str).values:
            record = df[df["Invoice Number"].astype(str) == invoice_no].iloc[0].to_dict()
            record["matched_on"] = "invoice_number"
            return record
        return None

    duplicate = _has_duplicate(existing_df, row)
    if duplicate and not force:
        _log_submission("duplicate", normalized_location, row, filepath, "Duplicate detected")
        return {
            "status": "duplicate",
            "location": normalized_location,
            "filepath": str(filepath),
            "duplicate": duplicate,
            "appended_rows": 0,
        }

    updated_df = pd.concat([existing_df, pd.DataFrame([row])], ignore_index=True)
    updated_df = updated_df[CANONICAL_HEADERS]

    temp_path = filepath.with_suffix(".tmp.xlsx")
    backup_path = None
    if filepath.exists():
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_path = filepath.with_name(f"{filepath.stem}_backup_{timestamp}.xlsx")
        shutil.copy2(filepath, backup_path)

    with pd.ExcelWriter(temp_path, engine="openpyxl") as writer:
        updated_df.to_excel(writer, index=False)

    temp_path.replace(filepath)
    _log_submission("ok", normalized_location, row, filepath, "Row appended")

    return {
        "status": "success",
        "location": normalized_location,
        "filepath": str(filepath),
        "backup": str(backup_path) if backup_path else None,
        "appended_rows": 1,
        "row": row,
    }
