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
    print(f"🔑 OCR.space API Key loaded: {'✅' if os.getenv('OCR_SPACE_API_KEY') else '❌'}")
except ImportError:
    print("⚠️ python-dotenv not installed, .env file not loaded")

from app.api.routes import router as api_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Receipt OCR Service",
        description="API for extracting structured data from receipt images and PDFs.",
        version="0.1.0",
    )

    # Get the base directory (receipt-ocr)
    base_dir = Path(__file__).parent.parent

    # Use parent directory artifacts folder (where exports are stored)
    artifacts_dir = base_dir.parent / "artifacts"

    templates = Jinja2Templates(directory=str(base_dir / "app" / "templates"))
    app.mount("/static", StaticFiles(directory=str(base_dir / "app" / "static")), name="static")
    app.mount("/artifacts", StaticFiles(directory=str(artifacts_dir)), name="artifacts")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return Response(status_code=204)  # No content

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