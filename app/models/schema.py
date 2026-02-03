from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


class ExtractionConfig(BaseModel):
    return_annotated: bool = Field(
        default=False,
        description="Whether to return a base64-encoded annotated image with detected fields.",
    )
    verification_tolerance: float = Field(
        default=0.5,
        description="Absolute tolerance used when comparing subtotal + tax to total.",
        ge=0.0,
    )
    verification_percent_tolerance: float = Field(
        default=0.01,
        description="Relative tolerance (as a fraction) used when comparing subtotal + tax to total.",
        ge=0.0,
    )


class LineItem(BaseModel):
    description: str
    qty: Optional[float] = None
    unit_price: Optional[float] = None
    total_price: Optional[float] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    category: Optional[str] = Field(default=None, description="Auto-detected expense category for the line item.")


class ExtractionResult(BaseModel):
    """Normalized receipt payload supporting hybrid Document AI merges."""

    receipt_id: UUID = Field(
        default_factory=uuid4,
        description="Stable receipt identifier; auto-generated if not provided.",
    )
    invoice_number: Optional[str] = Field(
        default=None,
        description="Invoice or order number when present on the receipt.",
    )
    vendor: Optional[str]
    date: Optional[str]
    currency: Optional[str]
    subtotal: Optional[float]
    tax: Optional[float]
    total: Optional[float]
    normalized_currency: Optional[str] = Field(
        default=None,
        description="Currency normalized for financial calculations (mirrors currency when present).",
    )
    normalized_subtotal: Optional[float] = Field(
        default=None,
        description="Normalized subtotal value used for consistency checks.",
    )
    normalized_tax: Optional[float] = Field(
        default=None,
        description="Normalized tax value; may be inferred when tax is missing but subtotal/total exist.",
    )
    normalized_total: Optional[float] = Field(
        default=None,
        description="Normalized total value used for consistency checks.",
    )
    inferred_tax: bool = Field(
        default=False,
        description="True when tax was inferred from subtotal and total in normalization.",
    )
    financial_consistency_ok: Optional[bool] = Field(
        default=None,
        description="Indicates whether normalized_subtotal + normalized_tax aligns with normalized_total (lightweight check).",
    )
    line_items: List[LineItem]
    raw_text: str
    fields_confidence: Dict[str, float]
    verified: bool
    verification_issues: List[str]
    missing_required_fields: List[str] = Field(
        default_factory=list,
        description="Advisory list of missing key receipt fields (non-blocking).",
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Non-blocking validation warnings (informational only).",
    )
    annotated_image_base64: Optional[str] = None
    processing_time_ms: int
    category_summary: Dict[str, float] = Field(
        default_factory=dict,
        description="Aggregated totals by detected expense category.",
    )
    primary_category: Optional[str] = Field(
        default=None,
        description="Dominant expense category inferred for the receipt.",
    )
    # Unified, engine-agnostic confidence signal; downstream should prefer this over engine-specific values
    overall_confidence: Optional[float] = Field(
        default=None,
        description="Primary confidence value to use downstream (Document AI preferred when available).",
    )
    confidence_source: Optional[str] = Field(
        default=None,
        description="Source of overall_confidence (e.g., 'document_ai', 'standard', 'merged').",
    )
    # Tashiro Ironworks specific fields
    tashiro_categorization: Optional[Dict] = Field(
        default=None,
        description="Complete Tashiro categorization analysis with confidence scores and workflow data."
    )
    expense_category: Optional[str] = Field(
        default=None,
        description="Primary Japanese expense category (食費, 交通費, etc.)"
    )
    expense_confidence: Optional[float] = Field(
        default=None,
        description="Confidence score for the primary expense category classification"
    )
    tax_classification: Optional[str] = Field(
        default=None,
        description="Japanese tax classification (課税10%, 課税8%, 非課税, etc.)"
    )
    business_unit: Optional[str] = Field(
        default=None,
        description="Assigned business unit based on content analysis"
    )
    approval_level: Optional[str] = Field(
        default=None,
        description="Required approval level based on amount (担当者処理, 課長承認, etc.)"
    )
    engine_used: Optional[str] = Field(
        default=None,
        description="Primary OCR engine(s) contributing to this extraction (e.g., 'google+document_ai').",
    )
    # Engine-specific confidence (debug/audit). Not authoritative; prefer overall_confidence downstream.
    confidence_docai: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Aggregate confidence reported by Document AI for mapped fields.",
    )
    # Engine-specific confidence (debug/audit). Not authoritative; prefer overall_confidence downstream.
    confidence_standard: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Aggregate confidence reported by the standard OCR stack.",
    )
    # Engine-specific raw payloads (audit only). Not authoritative; downstream should rely on canonical/normalized fields.
    docai_raw_entities: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Raw Document AI entities prior to mapper normalization.",
    )
    # Engine-specific raw payloads (audit only). Not authoritative; downstream should rely on canonical/normalized fields.
    docai_raw_fields: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Raw Document AI fields/kv pairs before sanitizing values.",
    )
    # Edit-readiness scaffolding: future UI can store the originally extracted values
    # and any user-corrected overrides without changing existing field names.
    extracted_values: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Snapshot of extracted values before user edits (optional).",
    )
    corrected_values: Optional[Dict[str, Any]] = Field(
        default=None,
        description="User-corrected values to override extracted fields (optional).",
    )
    merged_fields: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Final merged field set produced by merge logic for auditing.",
    )
    merge_strategy: Optional[str] = Field(
        default=None,
        description="Strategy identifier for how Document AI and standard OCR results were combined.",
    )

    @field_validator("date")
    @classmethod
    def validate_date_format(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        try:
            datetime.fromisoformat(value)
        except ValueError:
            raise ValueError("date must be ISO 8601 formatted string") from None
        return value

    @model_validator(mode="after")
    def _populate_normalized_financials(self) -> "ExtractionResult":
        # Lightweight normalization: mirror existing values when present and infer tax when missing.
        self.normalized_currency = self.currency
        self.normalized_subtotal = self.subtotal
        self.normalized_total = self.total

        if self.tax is not None:
            self.normalized_tax = self.tax
            self.inferred_tax = False
        elif self.subtotal is not None and self.total is not None:
            self.normalized_tax = self.total - self.subtotal
            self.inferred_tax = True

        if (
            self.normalized_subtotal is not None
            and self.normalized_tax is not None
            and self.normalized_total is not None
        ):
            delta = (self.normalized_subtotal + self.normalized_tax) - self.normalized_total
            self.financial_consistency_ok = abs(delta) < 0.01  # loose tolerance; informational only

        # Advisory validation (non-blocking)
        if self.missing_required_fields is None:
            self.missing_required_fields = []
        if self.warnings is None:
            self.warnings = []

        for field_name in ("vendor", "date", "total"):
            if getattr(self, field_name) is None:
                self.missing_required_fields.append(field_name)

        if self.financial_consistency_ok is False:
            self.warnings.append("financial_consistency_check_failed")

        return self


class ExtractionError(BaseModel):
    detail: str


class ExtractionRequestMetadata(BaseModel):
    config: ExtractionConfig = Field(default_factory=ExtractionConfig)


class Receipt(BaseModel):
    """Canonical, UI/Excel-agnostic Receipt (Phase 2F locked contract)."""

    receipt_id: UUID = Field(default_factory=uuid4)
    receipt_date: Optional[str] = None  # ISO YYYY-MM-DD
    vendor_name: Optional[str] = None
    invoice_number: Optional[str] = None

    total_amount: Optional[Decimal] = None
    tax_10_amount: Optional[Decimal] = None
    tax_8_amount: Optional[Decimal] = None
    tax_category: Optional[str] = None  # 税区分 - Tax Category (標準税率/軽減税率)
    account_title: Optional[str] = None  # 勘定科目 - Account Title (食費/交通費/etc)
    memo: Optional[str] = None

    business_location_id: Optional[str] = None  # canonical stable key
    staff_id: Optional[str] = None

    ocr_engine: Optional[str] = None  # e.g., "document_ai"
    ocr_confidence: Optional[float] = None
    ocr_flags: List[str] = Field(default_factory=list)

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {
        "json_encoders": {
            UUID: str,
            Decimal: str,
            datetime: lambda v: v.isoformat() if v else None,
        }
    }

    @field_validator("receipt_date")
    @classmethod
    def _validate_date(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        try:
            datetime.fromisoformat(value)
            return value
        except Exception as exc:  # pragma: no cover - defensive guard
            raise ValueError("receipt_date must be ISO format YYYY-MM-DD") from exc

    @model_validator(mode="after")
    def _coerce_decimal(self) -> "Receipt":
        """Ensure numeric fields are Decimal for consistency."""

        def _to_decimal(val: Any) -> Optional[Decimal]:
            if val is None:
                return None
            if isinstance(val, Decimal):
                return val
            try:
                return Decimal(str(val))
            except Exception:
                return None

        self.total_amount = _to_decimal(self.total_amount)
        self.tax_10_amount = _to_decimal(self.tax_10_amount)
        self.tax_8_amount = _to_decimal(self.tax_8_amount)
        return self
