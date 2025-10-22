from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
    api_key_status = "✅" if os.getenv('OCR_SPACE_API_KEY') else "❌"
    print(f"🔑 OCR.space API Key loaded: {api_key_status}")
    if not os.getenv('OCR_SPACE_API_KEY'):
        print("⚠️ WARNING: OCR_SPACE_API_KEY not found in environment!")
except ImportError:
    print("⚠️ python-dotenv not installed, .env file not loaded")
    api_key_status = "❌"
except Exception as e:
    print(f"⚠️ Error loading .env file: {e}")
    api_key_status = "❌"

from app.api.routes import router as api_router


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
        print(f"📁 Base directory: {base_dir}")
        print(f"📁 Templates directory: {base_dir / 'app' / 'templates'}")
        print(f"📁 Static directory: {base_dir / 'app' / 'static'}")
        print(f"📁 Artifacts directory: {artifacts_dir}")
        print(f"📁 Templates exists: {(base_dir / 'app' / 'templates').exists()}")
        print(f"📁 Static exists: {(base_dir / 'app' / 'static').exists()}")
        print(f"📁 Artifacts exists: {artifacts_dir.exists()}")

        # Ensure artifacts directory exists and is writable
        try:
            artifacts_dir.mkdir(exist_ok=True)
            # Test if directory is writable
            test_file = artifacts_dir / ".test_write"
            test_file.write_text("test")
            test_file.unlink()
            print("✅ Artifacts directory is writable")
        except Exception as e:
            print(f"❌ Artifacts directory error: {e}")
            # Try to create in a different location if needed
            import tempfile
            temp_dir = Path(tempfile.gettempdir()) / "tashiro_artifacts"
            temp_dir.mkdir(exist_ok=True)
            artifacts_dir = temp_dir
            print(f"📁 Using temp artifacts directory: {artifacts_dir}")

        templates = Jinja2Templates(directory=str(base_dir / "app" / "templates"))
        app.mount("/static", StaticFiles(directory=str(base_dir / "app" / "static")), name="static")
        app.mount("/artifacts", StaticFiles(directory=str(artifacts_dir)), name="artifacts")

        print("✅ App initialization successful")

        return app

    except Exception as e:
        print(f"❌ Critical error during app initialization: {e}")
        import traceback
        traceback.print_exc()
        raise

    @app.get("/health", tags=["health"])
    def health_check():
        """Health check endpoint."""
        return {"status": "healthy", "timestamp": "2025-01-22T12:00:00Z"}

    @app.get("/", response_class=HTMLResponse, tags=["ui"])
    def homepage(request: Request) -> HTMLResponse:
        return templates.TemplateResponse("mobile_intake_unified.html", {"request": request})

    @app.get("/mobile", response_class=HTMLResponse, tags=["ui"])
    def mobile_intake(request: Request) -> HTMLResponse:
        return templates.TemplateResponse("mobile_intake_unified.html", {"request": request})

    @app.get("/debug", response_class=HTMLResponse, tags=["ui"])
    def debug_test(request: Request) -> HTMLResponse:
        return templates.TemplateResponse("debug.html", {"request": request})

    app.include_router(api_router, prefix="/api")

    return app


app = create_app()