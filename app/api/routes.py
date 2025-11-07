from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Request
from fastapi.responses import JSONResponse
from typing import Optional, Dict, Any
import os
import uuid
from pathlib import Path
import base64
from PIL import Image
import io

from app.extractors.enhanced_field_extractor import EnhancedFieldExtractor
from app.ocr.multi_engine_ocr import MultiEngineOCR
from app.exporters.excel_exporter import ExcelExporter
from app.history.submission_history import SubmissionHistory

router = APIRouter()

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

@router.post("/mobile/analyze")
async def analyze_receipt(
    file: UploadFile = File(...),
    metadata: Optional[str] = Form(None)
):
    """Analyze a receipt image and extract structured data using Document AI + enhanced extraction."""
    try:
        if multi_engine_ocr is None or enhanced_extractor is None:
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
            # Reopen image with PIL for thumbnail generation
            image = Image.open(io.BytesIO(file_content))

            # Convert to RGB if necessary (handles RGBA, P, etc.)
            if image.mode not in ('RGB', 'L'):
                image = image.convert('RGB')

            # Create thumbnail (max 200px width/height, maintain aspect ratio)
            image.thumbnail((200, 200), Image.Resampling.LANCZOS)

            # Convert to base64
            thumb_buffer = io.BytesIO()
            image.save(thumb_buffer, format='JPEG', quality=70)
            thumbnail_b64 = base64.b64encode(thumb_buffer.getvalue()).decode('utf-8')

        except Exception as e:
            # Continue without thumbnail
            pass

        # Debug: Check file_content size before OCR
        print(f"  - File content size before OCR: {len(file_content)} bytes")
        
        # Extract structured data using multi-engine OCR
        ocr_result = multi_engine_ocr.extract_structured(file_content)
        
        if not ocr_result.get('success'):
            raise HTTPException(status_code=500, detail="OCR extraction failed")
        
        # Print raw OCR output for debugging
        raw_text = ocr_result.get('raw_text', '')
        engine_used = ocr_result.get('engine_used', 'unknown')
        structured_data = ocr_result.get('structured_data', {})
        
        # Extract fields using enhanced Document AI + pattern-based extractor
        extracted_data = enhanced_extractor.extract_fields_with_document_ai(
            structured_data=structured_data,
            raw_text=raw_text
        )
        
        # Add metadata
        extracted_data['ocr_engine'] = engine_used
        extracted_data['source_image'] = source_image_b64
        extracted_data['thumbnail'] = thumbnail_b64
        
        # Print final extracted fields for debugging (without base64 data)
        debug_data = {k: v for k, v in extracted_data.items() if k not in ['source_image', 'thumbnail']}
        print(f"Parsed fields from multi-engine OCR: {debug_data}")

        # Store in history for later submission
        submission_history.store_analysis(queue_id, extracted_data, metadata)

        # Return analysis result
        return {
            "queue_id": queue_id,
            "fields": extracted_data,
            "verification": {
                "verified": True,  # Basic verification
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

@router.get("/history")
async def get_history(limit: int = 50):
    """Get submission history."""
    try:
        history = submission_history.get_recent_submissions(limit)
        return history
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch history: {str(e)}")
