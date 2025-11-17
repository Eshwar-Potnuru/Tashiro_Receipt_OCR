import time
import threading
from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Request, BackgroundTasks, Body
from fastapi.responses import JSONResponse, FileResponse
from typing import Optional, Dict, Any
import os
import uuid
from pathlib import Path
import base64
from PIL import Image
import io

from app.utils.image_processing import optimize_image_for_ocr

from app.extractors.enhanced_field_extractor import EnhancedFieldExtractor
from app.ocr.multi_engine_ocr import MultiEngineOCR
from app.exporters.excel_exporter import ExcelExporter
from app.history.submission_history import SubmissionHistory
from accumulator import append_to_location, ACCUM_DIR
from validators import (
    get_available_locations,
    normalize_location,
    validate_required_fields,
)

router = APIRouter()
_locations_cache: Dict[str, Any] = get_available_locations()
_ocr_max_concurrent = max(1, int(os.getenv("OCR_MAX_CONCURRENT", "2")))
_ocr_concurrency_guard = threading.Semaphore(_ocr_max_concurrent)


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
    multi_engine_ocr = None

try:
    # Initialize enhanced field extractor
    enhanced_extractor = EnhancedFieldExtractor()
    print("Enhanced field extractor initialized")
except Exception as e:
    print(f"Enhanced extractor initialization failed: {e}")
    enhanced_extractor = None

try:
    excel_exporter = ExcelExporter()
    print("ExcelExporter initialized")
except Exception as e:
    print(f"ExcelExporter initialization failed: {e}")
    excel_exporter = None

try:
    submission_history = SubmissionHistory()
    print("SubmissionHistory initialized")
except Exception as e:
    print(f"SubmissionHistory initialization failed: {e}")
    submission_history = None

def _process_analysis_job(queue_id: str, image_bytes: bytes, metadata: Optional[str], payload_hash: Optional[str],
                          source_image_b64: str, thumbnail_b64: Optional[str], preprocess_stats: Dict[str, Any]):
    try:
        submission_history.mark_analysis_processing(queue_id)
        analysis_data, timings = _run_analysis_pipeline(
            queue_id,
            image_bytes,
            metadata,
            payload_hash,
            source_image_b64,
            thumbnail_b64,
            preprocess_stats
        )
        submission_history.store_analysis(queue_id, analysis_data, metadata, payload_hash, timings)
    except Exception as exc:
        submission_history.mark_analysis_failed(queue_id, str(exc))


def _run_analysis_pipeline(queue_id: str, image_bytes: bytes, metadata: Optional[str], payload_hash: Optional[str],
                           source_image_b64: str, thumbnail_b64: Optional[str], preprocess_stats: Dict[str, Any]):
    timings: Dict[str, Any] = {'preprocess': preprocess_stats}

    wait_start = time.perf_counter()
    _ocr_concurrency_guard.acquire()
    timings['queue_wait'] = round(time.perf_counter() - wait_start, 3)

    try:
        stage_start = time.perf_counter()
        ocr_result = multi_engine_ocr.extract_structured(image_bytes)
        timings['ocr'] = round(time.perf_counter() - stage_start, 3)

        if not ocr_result.get('success'):
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

    finally:
        _ocr_concurrency_guard.release()

    extracted_data['ocr_engine'] = engine_used
    extracted_data['source_image'] = source_image_b64
    extracted_data['thumbnail'] = thumbnail_b64
    extracted_data.setdefault('diagnostics', {})
    extracted_data['diagnostics'].update({
        'queue_id': queue_id,
        'engines_attempted': ocr_result.get('engines_attempted', []),
        'payload_hash': payload_hash,
        'timings': timings
    })

    return extracted_data, timings


@router.post("/mobile/analyze")
async def analyze_receipt(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    metadata: Optional[str] = Form(None),
    processing_mode: str = Form('sync')
):
    """Analyze a receipt image and extract structured data using Document AI + enhanced extraction."""
    try:
        if multi_engine_ocr is None or enhanced_extractor is None or submission_history is None:
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
                'cache_hit': True
            })
            submission_history.store_analysis(queue_id, cached_analysis, metadata, payload_hash, {'cache_hit': True})
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
                preprocess_stats
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
            preprocess_stats
        )
        submission_history.store_analysis(queue_id, analysis_data, metadata, payload_hash, timings)

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
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

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
        operator_payload = payload.get("operator") or {}
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

        result = append_to_location(fields, canonical, operator, force=force)
        status_code = 200
        if result.get("status") == "duplicate":
            status_code = 409

        if result.get("filepath"):
            rel_download = f"/api/accumulation/file?location={canonical}"
            result["download_url"] = rel_download
        result["duplicate"] = result.get("status") == "duplicate"

        return JSONResponse(status_code=status_code, content=result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Accumulation failed: {exc}")
