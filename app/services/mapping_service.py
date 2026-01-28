"""MappingService: orchestrate ExtractionResult → Receipt mapping."""

from __future__ import annotations

from typing import Optional

from app.models.schema import ExtractionConfig, ExtractionResult, Receipt
from app.services.config_service import ConfigService
from app.services.receipt_builder import ReceiptBuilder
from app.services.validation_service import ValidationService


class MappingService:
    """Coordinate mapping across builder, validation, and config services."""

    def __init__(
        self,
        *,
        config_service: Optional[ConfigService] = None,
        receipt_builder: Optional[ReceiptBuilder] = None,
        validation_service: Optional[ValidationService] = None,
    ) -> None:
        self.config_service = config_service or ConfigService()
        self.receipt_builder = receipt_builder or ReceiptBuilder()
        self.validation_service = validation_service or ValidationService()

    def map_to_receipt(self, extraction_result: ExtractionResult) -> Receipt:
        """Produce a canonical Receipt from an ExtractionResult.

        No side effects: purely functional mapping and validation.
        """

        if extraction_result is None:
            raise ValueError("extraction_result is required")

        # Run advisory validation on ExtractionResult
        validated = self.validation_service.validate(
            extraction_result,
            ExtractionConfig(),
        )

        validation_warnings = list(validated.warnings or [])
        validation_errors = list(validated.verification_issues or [])

        receipt = self.receipt_builder.build_receipt(
            validated,
            config_service=self.config_service,
            validation_warnings=validation_warnings,
            validation_errors=validation_errors,
        )

        return receipt
