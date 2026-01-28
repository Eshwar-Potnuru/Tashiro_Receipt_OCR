from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
import os
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
    
    # Log critical environment variables at startup
    print("=" * 60)
    print("Environment Configuration:")
    
    api_key_status = "OK" if os.getenv('OCR_SPACE_API_KEY') else "MISSING"
    print(f"  OCR.space API Key: {api_key_status}")
    
    google_creds = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
    if google_creds:
        print(f"  Google Credentials: {google_creds}")
        print(f"  Credentials file exists: {Path(google_creds).exists()}")
    else:
        print("  Google Credentials: NOT SET")
    
    doc_ai_project = os.getenv('DOCUMENT_AI_PROJECT_ID')
    doc_ai_processor = os.getenv('DOCUMENT_AI_PROCESSOR_ID')
    doc_ai_location = os.getenv('DOCUMENT_AI_LOCATION', 'us')
    print(f"  Document AI Project: {doc_ai_project}")
    print(f"  Document AI Processor: {doc_ai_processor}")
    print(f"  Document AI Location: {doc_ai_location}")
    print("=" * 60)
    
    if not os.getenv('OCR_SPACE_API_KEY'):
        print("WARNING: OCR_SPACE_API_KEY not found in environment!")
except ImportError:
    print("python-dotenv not installed, .env file not loaded")
    api_key_status = "MISSING"
except Exception as e:
    print(f"Error loading .env file: {e}")
    api_key_status = "MISSING"

from app.api.routes import router as api_router
from app.api.drafts import router as drafts_router
from app.api.audits import router as audits_router  # Phase 5A Step 3


class BlockTrackerMiddleware(BaseHTTPMiddleware):
    """Block suspicious tracking/analytics requests to reduce log noise."""
    
    BLOCKED_PATTERNS = [
        '/hybridaction/',  # Chinese browser extensions
        'zybTrackerStatisticsAction',  # Specific tracker
        '__callback__',  # JSONP callbacks from extensions
    ]
    
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        # Check if request matches blocked patterns
        if any(pattern in path or pattern in str(request.url) for pattern in self.BLOCKED_PATTERNS):
            # Return empty response without logging
            return PlainTextResponse('', status_code=204)
        
        return await call_next(request)


def create_app() -> FastAPI:
    try:
        app = FastAPI(
            title="Receipt OCR Service",
            description="API for extracting structured data from receipt images and PDFs.",
            version="0.1.0",
        )

        # Get the base directory (receipt-ocr)
        base_dir = Path(__file__).parent.parent

        # Use artifacts folder within the project directory
        artifacts_dir = base_dir / "artifacts"

        # Debug directory paths
        print(f"Base directory: {base_dir}")
        print(f"Templates directory: {base_dir / 'app' / 'templates'}")
        print(f"Static directory: {base_dir / 'app' / 'static'}")
        print(f"Artifacts directory: {artifacts_dir}")
        print(f"Templates exists: {(base_dir / 'app' / 'templates').exists()}")
        print(f"Static exists: {(base_dir / 'app' / 'static').exists()}")
        print(f"Artifacts exists: {artifacts_dir.exists()}")

        # Ensure artifacts directory exists and is writable
        try:
            artifacts_dir.mkdir(exist_ok=True)
            # Test if directory is writable
            test_file = artifacts_dir / ".test_write"
            test_file.write_text("test")
            test_file.unlink()
            print("Artifacts directory is writable")
        except Exception as e:
            print(f"Artifacts directory error: {e}")
            # Try to create in a different location if needed
            try:
                import tempfile
                temp_dir = Path(tempfile.gettempdir()) / "tashiro_artifacts"
                temp_dir.mkdir(exist_ok=True)
                artifacts_dir = temp_dir
                print(f"Using temp artifacts directory: {artifacts_dir}")
            except Exception as temp_e:
                print(f"Temp directory creation also failed: {temp_e}")
                # Fall back to current directory
                artifacts_dir = Path.cwd() / "artifacts_fallback"
                artifacts_dir.mkdir(exist_ok=True)
                print(f"Using fallback artifacts directory: {artifacts_dir}")

        templates = Jinja2Templates(directory=str(base_dir / "app" / "templates"))
        app.mount("/static", StaticFiles(directory=str(base_dir / "app" / "static")), name="static")
        app.mount("/artifacts", StaticFiles(directory=str(artifacts_dir)), name="artifacts")

        # Add tracker blocking middleware (Phase 4F Fix 2)
        app.add_middleware(BlockTrackerMiddleware)

        print("App initialization successful")

        @app.get("/health", tags=["health"])
        def health_check():
            """Health check endpoint."""
            return {"status": "healthy", "timestamp": "2025-01-22T12:00:00Z"}

        @app.get("/", response_class=HTMLResponse, tags=["ui"])
        def homepage(request: Request) -> HTMLResponse:
            return templates.TemplateResponse("mobile_intake_unified_manual.html", {"request": request})

        @app.get("/mobile", response_class=HTMLResponse, tags=["ui"])
        def mobile_intake(request: Request) -> HTMLResponse:
            return templates.TemplateResponse("mobile_intake_unified_manual.html", {"request": request})

        @app.get("/debug", response_class=HTMLResponse, tags=["ui"])
        def debug_test(request: Request) -> HTMLResponse:
            return templates.TemplateResponse("debug.html", {"request": request})

        @app.get("/drafts", response_class=HTMLResponse, tags=["ui"])
        def draft_management(request: Request) -> HTMLResponse:
            """Phase 4D: Draft management UI"""
            return templates.TemplateResponse("draft_management.html", {"request": request})

        app.include_router(api_router, prefix="/api")
        app.include_router(drafts_router)  # Phase 4B: Draft API endpoints
        app.include_router(audits_router)  # Phase 5A Step 3: Audit API endpoints

        return app

    except Exception as e:
        print(f"Critical error during app initialization: {e}")
        import traceback
        traceback.print_exc()
        raise


app = create_app()