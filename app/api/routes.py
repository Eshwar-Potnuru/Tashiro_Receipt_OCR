import time
import threading
import logging
import json
from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Request, BackgroundTasks, Body, Query
from fastapi.responses import JSONResponse, FileResponse
from typing import Optional, Dict, Any, List
import os
import uuid
from pathlib import Path
import base64
from PIL import Image
import io

from app.utils.image_processing import optimize_image_for_ocr
from app.utils.logging_utils import log_ocr_event, log_batch_event
from app.pipeline.multi_receipt_pipeline import MultiReceiptPipeline

from app.extractors.enhanced_field_extractor import EnhancedFieldExtractor
from app.ocr.multi_engine_ocr import MultiEngineOCR
from app.exporters.excel_exporter import ExcelExporter
from app.history.submission_history import SubmissionHistory
from app.models.schema import ExtractionConfig
from app.services.receipt_builder import ReceiptBuilder
from app.services.validation_service import ValidationService
from accumulator import ACCUM_DIR, test_template_system, get_staff_for_location, validate_staff_member, append_to_month_sheet
from template_formatter import append_to_formatted_template
from validators import (
    get_available_locations,
    normalize_location,
    validate_required_fields,
)

router = APIRouter()
logger = logging.getLogger(__name__)
_locations_cache: Dict[str, Any] = get_available_locations()
_ocr_max_concurrent = max(1, int(os.getenv("OCR_MAX_CONCURRENT", "2")))
_ocr_concurrency_guard = threading.Semaphore(_ocr_max_concurrent)
DEMO_AUTOSAVE_SAMPLE = os.getenv("DEMO_AUTOSAVE_SAMPLE", "true").lower() == "true"
DEMO_SAMPLE_PATH = Path(__file__).resolve().parents[2] / "artifacts" / "sample_receipt.json"
ARTIFACTS_DIR = Path(__file__).resolve().parents[2] / "artifacts"


def _build_demo_sample_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """Project analysis data to the ExtractionResult-compatible keys used by the Excel demo.

    We intentionally drop large blobs (source_image, thumbnail) and keep only the fields
    required by scripts/demo_hq_export.py to instantiate ExtractionResult.
    """

    allowed_keys = {
        "invoice_number",
        "vendor",
        "date",
        "currency",
        "subtotal",
        "tax",
        "total",
        "normalized_currency",
        "normalized_subtotal",
        "normalized_tax",
        "normalized_total",
        "inferred_tax",
        "financial_consistency_ok",
        "line_items",
        "raw_text",
        "fields_confidence",
        "verified",
        "verification_issues",
        "missing_required_fields",
        "warnings",
        "processing_time_ms",
        "category_summary",
        "primary_category",
        "overall_confidence",
        "confidence_source",
        "tashiro_categorization",
        "expense_category",
        "expense_confidence",
        "tax_classification",
        "business_unit",
        "approval_level",
        "engine_used",
        "confidence_docai",
        "confidence_standard",
        "docai_raw_entities",
        "docai_raw_fields",
        "extracted_values",
        "corrected_values",
        "merged_fields",
        "merge_strategy",
    }

    projected: Dict[str, Any] = {k: v for k, v in data.items() if k in allowed_keys}
    projected.setdefault("line_items", [])
    projected.setdefault("fields_confidence", {})
    projected.setdefault("verification_issues", [])
    projected.setdefault("missing_required_fields", [])
    projected.setdefault("warnings", [])

    if "processing_time_ms" not in projected:
        timings = data.get("timings") or {}
        total_ms = timings.get("total_ms") if isinstance(timings, dict) else None
        projected["processing_time_ms"] = int(total_ms) if total_ms is not None else 0

    return projected


def _write_demo_sample(data: Dict[str, Any]) -> None:
    """Persist the latest analysis payload for the Excel demo if enabled.

    Uses default=str to avoid serialization errors (e.g., Decimal, UUID).
    """
    if not DEMO_AUTOSAVE_SAMPLE:
        return

    try:
        DEMO_SAMPLE_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = _build_demo_sample_payload(data)
        # Ensure date is ISO if present
        if payload.get("date") and isinstance(payload.get("date"), str):
            from app.services.receipt_builder import _sanitize_iso_date
            payload["date"] = _sanitize_iso_date(payload.get("date"))
        DEMO_SAMPLE_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    except Exception:
        logger.exception("Failed to write demo sample_receipt.json")


def _refresh_locations_cache() -> Dict[str, Any]:
    global _locations_cache
    try:
        _locations_cache = get_available_locations()
    except Exception:
        pass
    return _locations_cache

@router.post("/mobile/test-upload")
async def test_upload(file: UploadFile = File(...)):
    """Test endpoint to debug file upload issues"""
    try:
        file_content = await file.read()
        
        return {
            "filename": file.filename,
            "content_type": file.content_type,
            "size": len(file_content),
            "first_bytes": file_content[:50].hex() if len(file_content) > 0 else "No data"
        }
    except Exception as e:
        return {"error": str(e)}

# Initialize components with error handling
try:
    # Initialize multi-engine OCR
    multi_engine_ocr = MultiEngineOCR()
    print("Multi-engine OCR initialized")
except Exception as e:
    print(f"Multi-engine OCR initialization failed: {e}")
    logger.exception("Multi-engine OCR initialization failed")
    multi_engine_ocr = None

try:
    # Initialize enhanced field extractor
    enhanced_extractor = EnhancedFieldExtractor()
    print("Enhanced field extractor initialized")
except Exception as e:
    print(f"Enhanced extractor initialization failed: {e}")
    logger.exception("Enhanced extractor initialization failed")
    enhanced_extractor = None

try:
    excel_exporter = ExcelExporter()
    print("ExcelExporter initialized")
except Exception as e:
    print(f"ExcelExporter initialization failed: {e}")
    logger.exception("ExcelExporter initialization failed")
    excel_exporter = None

try:
    submission_history = SubmissionHistory()
    print("SubmissionHistory initialized")
except Exception as e:
    print(f"SubmissionHistory initialization failed: {e}")
    logger.exception("SubmissionHistory initialization failed")
    submission_history = None

try:
    receipt_builder = ReceiptBuilder()
    print("ReceiptBuilder initialized")
except Exception as e:
    print(f"ReceiptBuilder initialization failed: {e}")
    logger.exception("ReceiptBuilder initialization failed")
    receipt_builder = None

try:
    validation_service = ValidationService()
    print("ValidationService initialized")
except Exception as e:
    print(f"ValidationService initialization failed: {e}")
    logger.exception("ValidationService initialization failed")
    validation_service = None

def _process_analysis_job(queue_id: str, image_bytes: bytes, metadata: Optional[str], payload_hash: Optional[str],
                          source_image_b64: str, thumbnail_b64: Optional[str], preprocess_stats: Dict[str, Any],
                          engine_preference: str, source_filename: str, image_format: str = 'jpg'):
    try:
        submission_history.mark_analysis_processing(queue_id)
        analysis_data, timings = _run_analysis_pipeline(
            queue_id,
            image_bytes,
            metadata,
            payload_hash,
            source_image_b64,
            thumbnail_b64,
            preprocess_stats,
            engine_preference,
            source_filename,
            image_format  # Pass format through
        )
        submission_history.store_analysis(queue_id, analysis_data, metadata, payload_hash, timings)
    except Exception as exc:
        logger.exception("Background analysis job failed", extra={"queue_id": queue_id})
        submission_history.mark_analysis_failed(queue_id, str(exc))


def _run_analysis_pipeline(queue_id: str, image_bytes: bytes, metadata: Optional[str], payload_hash: Optional[str],
                           source_image_b64: str, thumbnail_b64: Optional[str], preprocess_stats: Dict[str, Any],
                           engine_preference: str, source_filename: str, image_format: str = 'jpg'):
    if receipt_builder is None or validation_service is None:
        raise RuntimeError("Receipt builder not available")

    timings: Dict[str, Any] = {'preprocess': preprocess_stats}

    wait_start = time.perf_counter()
    _ocr_concurrency_guard.acquire()
    timings['queue_wait'] = round(time.perf_counter() - wait_start, 3)

    try:
        stage_start = time.perf_counter()
        try:
            ocr_result = multi_engine_ocr.extract_structured(image_bytes, engine=engine_preference)
        except Exception as exc:
            log_ocr_event({
                "file": source_filename,
                "queue_id": queue_id,
                "engine": engine_preference,
                "merge_strategy": None,
                "confidence_docai": None,
                "confidence_standard": None,
                "status": "error",
                "error_message": str(exc)
            })
            raise

        timings['ocr'] = round(time.perf_counter() - stage_start, 3)

        log_ocr_event({
            "file": source_filename,
            "queue_id": queue_id,
            "engine": ocr_result.get('engine_used', engine_preference),
            "merge_strategy": ocr_result.get('merge_strategy'),
            "confidence_docai": ocr_result.get('confidence_docai'),
            "confidence_standard": ocr_result.get('confidence_standard'),
            "status": "success" if ocr_result.get('success') else "error",
            "error_message": None if ocr_result.get('success') else "OCR extraction failed"
        })

        if not ocr_result.get('success'):
            logger.error(
                "OCR extraction returned success=False",
                extra={
                    "queue_id": queue_id,
                    "engine_preference": engine_preference,
                    "engines_attempted": ocr_result.get('engines_attempted'),
                    "engine_used": ocr_result.get('engine_used'),
                }
            )
            raise RuntimeError("OCR extraction failed")

        raw_text = ocr_result.get('raw_text', '')
        engine_used = ocr_result.get('engine_used', 'unknown')
        structured_data = ocr_result.get('structured_data', {})

        stage_start = time.perf_counter()
        extracted_data = enhanced_extractor.extract_fields_with_document_ai(
            structured_data=structured_data,
            raw_text=raw_text
        )
        timings['field_extractor'] = round(time.perf_counter() - stage_start, 3)

        builder_payload: Dict[str, Any] = {
            **extracted_data,
            "structured_data": structured_data,
            "raw_text": raw_text,
            "diagnostics": {"timings": timings},
            "engine_used": engine_used,
            "merge_strategy": ocr_result.get('merge_strategy'),
            "confidence_docai": ocr_result.get('confidence_docai'),
            "confidence_standard": ocr_result.get('confidence_standard'),
            "docai_raw_entities": structured_data.get('docai_raw_entities'),
            "docai_raw_fields": structured_data.get('docai_raw_fields'),
            "entities": structured_data.get('entities'),
            "line_items": extracted_data.get('line_items') or structured_data.get('line_items'),
            "fields_confidence": extracted_data.get('field_confidence') or extracted_data.get('fields_confidence') or structured_data.get('fields_confidence'),
        }

        standard_result = receipt_builder.build_from_standard_ocr(
            builder_payload,
            raw_text=raw_text,
            processing_time_ms=None,
            metadata=None,
        )

        docai_present = bool(
            structured_data.get('docai_raw_entities')
            or structured_data.get('docai_raw_fields')
            or ocr_result.get('confidence_docai') is not None
        )
        docai_result = receipt_builder.build_from_document_ai(
            builder_payload,
            raw_text=raw_text,
            processing_time_ms=None,
            metadata=None,
        ) if docai_present else None

        if engine_preference == 'document_ai' and docai_result:
            canonical_result = docai_result
        elif engine_preference == 'standard':
            canonical_result = standard_result
        elif docai_result:
            canonical_result = receipt_builder.build_auto(standard_result, docai_result, metadata=None)
        else:
            canonical_result = standard_result

        validated_result = validation_service.validate(
            canonical_result,
            ExtractionConfig()
        )

        analysis_result = validated_result.model_dump()

        analysis_result["engine_used"] = engine_used
        analysis_result["ocr_engine"] = engine_used
        analysis_result["confidence_docai"] = analysis_result.get("confidence_docai") or ocr_result.get('confidence_docai')
        analysis_result["confidence_standard"] = analysis_result.get("confidence_standard") or ocr_result.get('confidence_standard')
        analysis_result["docai_raw_entities"] = analysis_result.get("docai_raw_entities") or structured_data.get('docai_raw_entities')
        analysis_result["docai_raw_fields"] = analysis_result.get("docai_raw_fields") or structured_data.get('docai_raw_fields')
        analysis_result["merged_fields"] = analysis_result.get("merged_fields") or structured_data.get('entities')
        analysis_result["merge_strategy"] = analysis_result.get("merge_strategy") or ocr_result.get('merge_strategy')
        analysis_result["overall_confidence"] = analysis_result.get("overall_confidence") or analysis_result.get("confidence_docai") or analysis_result.get("confidence_standard")
        analysis_result["raw_text"] = analysis_result.get("raw_text") or raw_text
        if "field_confidence" in extracted_data:
            analysis_result.setdefault("field_confidence", extracted_data.get("field_confidence"))
        for passthrough_key in ("invoice_number", "tax_category", "account_title", "confidence"):
            if passthrough_key in extracted_data and passthrough_key not in analysis_result:
                analysis_result[passthrough_key] = extracted_data[passthrough_key]

        analysis_result['source_image'] = source_image_b64
        analysis_result['thumbnail'] = thumbnail_b64
        analysis_result.setdefault('diagnostics', {})
        analysis_result['diagnostics'].update({
            'queue_id': queue_id,
            'engines_attempted': ocr_result.get('engines_attempted', []),
            'payload_hash': payload_hash,
            'timings': timings,
            'image_format': image_format  # Store format to avoid 404s
        })

    finally:
        _ocr_concurrency_guard.release()

    return analysis_result, timings


@router.post("/mobile/analyze")
async def analyze_receipt(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    metadata: Optional[str] = Form(None),
    processing_mode: str = Form('sync'),
    engine: str = Form('auto')
):
    """Analyze a receipt image and extract structured data using Document AI + enhanced extraction."""
    try:
        if multi_engine_ocr is None or enhanced_extractor is None or submission_history is None or receipt_builder is None or validation_service is None:
            raise HTTPException(status_code=500, detail="OCR service not available")

        # Generate unique queue ID
        queue_id = str(uuid.uuid4())

        # Read file content - use file.file to access the underlying file
        file_content = await file.read()
        
        # If the content is too small, try accessing the underlying file object
        if len(file_content) < 100:
            try:
                # Reset and read from the underlying file object
                file.file.seek(0)
                file_content = file.file.read()
                print(f"  - Used file.file.read(), size: {len(file_content)} bytes")
            except Exception as e:
                print(f"  - file.file.read() failed: {e}")
        
        # Debug file information
        print(f"File upload debug:")
        print(f"  - Filename: {file.filename}")
        print(f"  - Content type: {file.content_type}")
        print(f"  - File size: {len(file_content)} bytes")
        source_filename = file.filename or 'uploaded_receipt'
        
        # Validate file size
        if len(file_content) < 100:  # Less than 100 bytes is likely corrupted
            raise HTTPException(status_code=400, detail=f"File too small ({len(file_content)} bytes). Please upload a valid image file.")
        
        # Validate file is a valid image and get info
        try:
            # Open image from file_content
            image = Image.open(io.BytesIO(file_content))
            image_format = image.format
            image_size = image.size
            print(f"  - Image format: {image_format}")
            print(f"  - Image size: {image_size}")
            # Don't call verify() as it corrupts the image data
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid image file: {str(e)}")

        # Save image to artifacts/ocr_results for draft display
        try:
            results_dir = ARTIFACTS_DIR / 'ocr_results'
            results_dir.mkdir(parents=True, exist_ok=True)
            
            # Determine image extension from format
            image = Image.open(io.BytesIO(file_content))
            ext = 'jpg' if image.format in ('JPEG', 'JPG') else (image.format.lower() if image.format else 'png')
            
            # Save with queue_id as filename
            image_path = results_dir / f"{queue_id}.{ext}"
            with open(image_path, 'wb') as f:
                f.write(file_content)
            print(f"  - Saved image to: {image_path}")
            print(f"  - Image format: {ext}")
        except Exception as e:
            print(f"  - Failed to save image file: {e}")
            ext = 'jpg'  # Default fallback
            # Continue anyway - image save is optional for core functionality

        # Encode image as base64 for frontend display
        source_image_b64 = base64.b64encode(file_content).decode('utf-8')

        # Generate thumbnail for history
        thumbnail_b64 = None
        try:
            image = Image.open(io.BytesIO(file_content))
            if image.mode not in ('RGB', 'L'):
                image = image.convert('RGB')
            image.thumbnail((200, 200), Image.Resampling.LANCZOS)
            thumb_buffer = io.BytesIO()
            image.save(thumb_buffer, format='JPEG', quality=70)
            thumbnail_b64 = base64.b64encode(thumb_buffer.getvalue()).decode('utf-8')
        except Exception:
            pass

        optimized_bytes, preprocess_stats = optimize_image_for_ocr(file_content)
        payload_hash = preprocess_stats.get('optimized_hash')

        cached_analysis = submission_history.get_cached_analysis(payload_hash) if payload_hash else None
        if cached_analysis:
            cached_analysis['source_image'] = source_image_b64
            cached_analysis['thumbnail'] = thumbnail_b64
            cached_analysis.setdefault('diagnostics', {})
            cached_analysis['diagnostics'].update({
                'queue_id': queue_id,
                'payload_hash': payload_hash,
                'cache_hit': True,
                'image_format': ext  # Store format to avoid 404s
            })
            submission_history.store_analysis(queue_id, cached_analysis, metadata, payload_hash, {'cache_hit': True})
            _write_demo_sample(cached_analysis)
            return {
                "queue_id": queue_id,
                "status": "completed",
                "fields": cached_analysis,
                "verification": {
                    "verified": True,
                    "issues": []
                }
            }

        processing_mode = (processing_mode or 'sync').lower()
        engine_preference = (engine or 'auto').lower()
        if engine_preference not in {'auto', 'standard', 'document_ai'}:
            engine_preference = 'auto'

        if processing_mode == 'async':
            submission_history.create_pending_analysis(queue_id, metadata, payload_hash, preprocess_stats)
            background_tasks.add_task(
                _process_analysis_job,
                queue_id,
                optimized_bytes,
                metadata,
                payload_hash,
                source_image_b64,
                thumbnail_b64,
                preprocess_stats,
                engine_preference,
                source_filename,
                ext  # Pass image format to background task
            )
            return {
                "queue_id": queue_id,
                "status": "queued",
                "preprocess": preprocess_stats
            }

        submission_history.mark_analysis_processing(queue_id)
        analysis_data, timings = _run_analysis_pipeline(
            queue_id,
            optimized_bytes,
            metadata,
            payload_hash,
            source_image_b64,
            thumbnail_b64,
            preprocess_stats,
            engine_preference,
            source_filename,
            ext  # Pass image format
        )
        submission_history.store_analysis(queue_id, analysis_data, metadata, payload_hash, timings)
        _write_demo_sample(analysis_data)

        return {
            "queue_id": queue_id,
            "status": "completed",
            "fields": analysis_data,
            "verification": {
                "verified": True,
                "issues": []
            }
        }

    except Exception as e:
        print(f"Analysis error: {str(e)}")
        logger.exception("Analysis failed")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.post("/mobile/analyze_batch")
async def analyze_receipt_batch(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    engine_form: Optional[str] = Form(None),
    engine_query: Optional[str] = Query(None)
):
    """Register a batch of receipts for sequential placeholder processing."""

    if submission_history is None:
        raise HTTPException(status_code=500, detail="Submission history not available")

    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    engine_preference = (engine_form or engine_query or 'standard').lower()
    if engine_preference not in {"document_ai", "standard"}:
        engine_preference = "standard"

    batch_id = str(uuid.uuid4())
    batch_dir = Path(__file__).resolve().parents[2] / "artifacts" / "uploads" / "batches" / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)

    stored_paths: List[str] = []
    filenames: List[str] = []

    for index, upload in enumerate(files):
        filename = upload.filename or f"receipt_{index + 1}.bin"
        safe_name = Path(filename).name
        destination = batch_dir / safe_name
        file_bytes = await upload.read()
        destination.write_bytes(file_bytes)
        stored_paths.append(str(destination))
        filenames.append(safe_name)
        await upload.close()

    submission_history.create_batch(batch_id, filenames, engine_preference)
    log_batch_event({
        "batch_id": batch_id,
        "engine": engine_preference,
        "file_count": len(stored_paths),
        "status": "created"
    })

    pipeline = MultiReceiptPipeline(engine_preference, submission_history)
    background_tasks.add_task(pipeline.process_batch, batch_id, stored_paths)

    return {
        "batch_id": batch_id,
        "file_count": len(stored_paths),
        "engine": engine_preference,
        "status": "pending"
    }

@router.post("/mobile/submit")
async def submit_receipt(
    request: Request
):
    """Submit verified receipt data and generate Excel export."""
    try:
        if excel_exporter is None or submission_history is None:
            raise HTTPException(status_code=500, detail="Export service not available")

        data = await request.json()
        queue_id = data.get("queue_id")
        fields_data = data.get("fields", {})
        user_data = data.get("user", {})

        # Get original analysis
        analysis = submission_history.get_analysis(queue_id)
        if not analysis:
            raise HTTPException(status_code=404, detail="Analysis not found")

        # Update with verified fields
        verified_data = {**analysis, **fields_data}

        # Generate Excel export
        excel_path = excel_exporter.export_to_excel(verified_data, user_data)

        # Store submission
        submission_history.store_submission(queue_id, verified_data, user_data, excel_path)

        return {
            "status": "success",
            "excel_url": f"/artifacts/{Path(excel_path).name}",
            "submission_id": queue_id
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Submission failed: {str(e)}")


@router.get("/mobile/analyze/status/{queue_id}")
async def get_analysis_status_route(queue_id: str):
    status_payload = submission_history.get_analysis_status(queue_id)
    if not status_payload:
        raise HTTPException(status_code=404, detail="Analysis not found")

    response = {
        "queue_id": queue_id,
        "status": status_payload.get('status'),
        "error": status_payload.get('error'),
        "timings": status_payload.get('timings'),
        "metadata": status_payload.get('metadata'),
        "preprocess": status_payload.get('preprocess')
    }

    if status_payload.get('status') == 'completed' and status_payload.get('analysis_data'):
        response['fields'] = status_payload['analysis_data']
        # Defensive autosave: ensure sample_receipt.json reflects latest result even if caller only polls status
        try:
            _write_demo_sample(status_payload['analysis_data'])
        except Exception:
            logger.exception("Failed to autosave sample_receipt.json from status endpoint")

    return response

@router.get("/history")
async def get_history(limit: int = 50):
    """Get submission history."""
    try:
        history = submission_history.get_recent_submissions(limit)
        return history
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch history: {str(e)}")


@router.get("/locations")
async def list_locations():
    cfg = _refresh_locations_cache()
    return cfg


@router.get("/staff")
async def list_staff(location: str):
    cfg = _refresh_locations_cache()
    canonical = normalize_location(location, cfg)
    if not canonical:
        raise HTTPException(status_code=400, detail="Unknown business location")

    staff = get_staff_for_location(canonical) or []
    return {
        "success": True,
        "location": canonical,
        "staff": staff,
    }


@router.get("/accumulation/file")
async def download_accumulation(location: str):
    cfg = _refresh_locations_cache()
    canonical = normalize_location(location, cfg)
    if not canonical:
        raise HTTPException(status_code=400, detail="Unknown business location")
    filepath = ACCUM_DIR / f"{canonical}_Accumulated.xlsx"
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Accumulation file not found")
    return FileResponse(
        path=str(filepath),
        filename=filepath.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.post("/accumulate_receipt")
async def accumulate_receipt(payload: Dict[str, Any] = Body(...)):
    try:
        receipt_fields = payload.get("receipt_data") or payload.get("fields") or {}

        if not receipt_fields:
            fallback_fields = {
                "receipt_date": payload.get("receipt_date"),
                "vendor_name": payload.get("vendor_name"),
                "total_amount": payload.get("total_amount"),
                "invoice_number": payload.get("invoice_number"),
                "order_number": payload.get("order_number"),
                "tax_10": payload.get("tax_10"),
                "tax_8": payload.get("tax_8"),
                "tax_total": payload.get("tax_total"),
                "business_office": payload.get("business_location") or payload.get("location"),
            }
            receipt_fields = {k: v for k, v in fallback_fields.items() if v not in (None, "")}

        operator_payload = payload.get("operator") or {}
        if not operator_payload.get("full_name") and payload.get("operator_name"):
            operator_payload["full_name"] = payload.get("operator_name")
        if not operator_payload.get("name") and payload.get("operator_name"):
            operator_payload["name"] = payload.get("operator_name")
        if not operator_payload.get("email") and payload.get("operator_email"):
            operator_payload["email"] = payload.get("operator_email")
        if not operator_payload.get("employee_id") and payload.get("operator_id"):
            operator_payload["employee_id"] = payload.get("operator_id")

        if not receipt_fields:
            raise HTTPException(status_code=400, detail="Missing receipt data")
        if not operator_payload:
            raise HTTPException(status_code=400, detail="Missing operator information")
        raw_location = (
            payload.get("business_location")
            or payload.get("location")
            or receipt_fields.get("business_office")
        )
        validate_required_fields(
            {
                "business_location": raw_location,
                "order_number": receipt_fields.get("order_number") or payload.get("order_number"),
                "invoice_number": receipt_fields.get("invoice_number") or payload.get("invoice_number"),
            }
        )

        cfg = _refresh_locations_cache()
        canonical = normalize_location(raw_location, cfg)
        if not canonical:
            raise HTTPException(status_code=400, detail="Invalid business location")

        fields = dict(receipt_fields)
        fields["business_location"] = canonical
        if payload.get("staff_member"):
            fields.setdefault("staff_member", payload.get("staff_member"))
        operator = {
            "name": operator_payload.get("full_name") or operator_payload.get("name"),
            "email": operator_payload.get("email"),
            "employee_id": operator_payload.get("employee_id") or operator_payload.get("id"),
        }
        force = bool(payload.get("force"))

        # include queue/source metadata for traceability
        if payload.get("queue_id"):
            fields.setdefault("queue_id", payload["queue_id"])
        if payload.get("source_file"):
            fields.setdefault("source_file", payload["source_file"])

        # Phase 3: route to new SummaryService writers (Format 02 + Format 01)
        from app.services.summary_service import SummaryService
        from app.models.schema import Receipt

        receipt_model = Receipt(
            receipt_date=fields.get("receipt_date"),
            vendor_name=fields.get("vendor_name"),
            invoice_number=fields.get("invoice_number"),
            total_amount=fields.get("total_amount"),
            tax_10_amount=fields.get("tax_10") or fields.get("tax_10_amount"),
            tax_8_amount=fields.get("tax_8") or fields.get("tax_8_amount"),
            memo=fields.get("memo"),
            business_location_id=canonical,
            staff_id=fields.get("staff_member"),
        )

        summary = SummaryService()
        write_result = summary.send_receipts([receipt_model])

        location_path = f"app/Data/accumulation/locations/{canonical}_Accumulated.xlsx"
        staff_path = (
            f"app/Data/accumulation/staff/{receipt_model.staff_id}.xlsx"
            if receipt_model.staff_id else None
        )

        content = {
            "status": "success",
            "location": canonical,
            "staff": receipt_model.staff_id,
            "summary": write_result,
            "download_path": location_path,
        }
        if staff_path:
            content["staff_path"] = staff_path

        return JSONResponse(status_code=200, content=content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Accumulation failed: {exc}")
