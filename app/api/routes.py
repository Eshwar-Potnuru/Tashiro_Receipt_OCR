from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Request
from fastapi.responses import JSONResponse
from typing import Optional, Dict, Any
import os
import uuid
from pathlib import Path
import base64
from PIL import Image
import io

from app.extractors.field_extractors import FieldExtractor
from app.exporters.excel_exporter import ExcelExporter
from app.history.submission_history import SubmissionHistory

router = APIRouter()

# Initialize components with error handling
try:
    field_extractor = FieldExtractor()
    print("✅ FieldExtractor initialized")
except Exception as e:
    print(f"❌ FieldExtractor initialization failed: {e}")
    field_extractor = None

try:
    excel_exporter = ExcelExporter()
    print("✅ ExcelExporter initialized")
except Exception as e:
    print(f"❌ ExcelExporter initialization failed: {e}")
    excel_exporter = None

try:
    submission_history = SubmissionHistory()
    print("✅ SubmissionHistory initialized")
except Exception as e:
    print(f"❌ SubmissionHistory initialization failed: {e}")
    submission_history = None

@router.post("/mobile/analyze")
async def analyze_receipt(
    file: UploadFile = File(...),
    metadata: Optional[str] = Form(None)
):
    """Analyze a receipt image and extract structured data."""
    try:
        if field_extractor is None:
            raise HTTPException(status_code=500, detail="OCR service not available")

        # Generate unique queue ID
        queue_id = str(uuid.uuid4())

        # Read file content
        file_content = await file.read()

        # Encode image as base64 for frontend display
        source_image_b64 = base64.b64encode(file_content).decode('utf-8')

        # Generate thumbnail for history
        thumbnail_b64 = None
        try:
            # Open image with PIL
            image = Image.open(io.BytesIO(file_content))

            # Create thumbnail (max 200px width/height, maintain aspect ratio)
            image.thumbnail((200, 200), Image.Resampling.LANCZOS)

            # Convert to base64
            thumb_buffer = io.BytesIO()
            image.save(thumb_buffer, format='JPEG', quality=70)
            thumbnail_b64 = base64.b64encode(thumb_buffer.getvalue()).decode('utf-8')

        except Exception as e:
            print(f"Thumbnail generation failed: {e}")
            # Continue without thumbnail

        # Extract fields using OCR
        extracted_data = field_extractor.extract_fields(file_content, file.filename)

        # Add source image to extracted data
        extracted_data['source_image'] = source_image_b64
        extracted_data['thumbnail'] = thumbnail_b64

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