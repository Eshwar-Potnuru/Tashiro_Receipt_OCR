from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


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
    vendor: Optional[str]
    date: Optional[str]
    currency: Optional[str]
    subtotal: Optional[float]
    tax: Optional[float]
    total: Optional[float]
    line_items: List[LineItem]
    raw_text: str
    fields_confidence: Dict[str, float]
    verified: bool
    verification_issues: List[str]
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


class ExtractionError(BaseModel):
    detail: str


class ExtractionRequestMetadata(BaseModel):
    config: ExtractionConfig = Field(default_factory=ExtractionConfig)
