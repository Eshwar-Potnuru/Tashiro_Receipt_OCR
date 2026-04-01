from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import os
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta

# Rate limiter will be initialized in create_app() to avoid .env encoding issues on Windows
limiter = None

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
from app.api.hq_transfer import router as hq_transfer_router  # Phase 7A-3: Internal HQ transfer
from app.api.hq_view import router as hq_view_router  # Phase 7.2: HQ read-only view
from app.api.system import router as system_router  # Phase 9A.4: System health endpoints
from app.api.excel_source import router as excel_source_router  # Phase 10: Excel Source of Truth
from app.routes.auth import router as auth_router  # Phase 5B.1: Authentication


logger = logging.getLogger("uvicorn.error")
logger.setLevel(logging.INFO)


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


class ApiTimingMiddleware(BaseHTTPMiddleware):
    """Targeted timing logs for key API paths to diagnose cross-user freezes."""

    TIMED_PREFIXES = (
        "/api/drafts",
        "/api/auth/login",
    )

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        should_time = path.startswith(self.TIMED_PREFIXES)

        if not should_time:
            return await call_next(request)

        started_at = time.perf_counter()
        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            user = getattr(request.state, "user", None)
            logger.info(
                "api_timing method=%s path=%s status=%s duration_ms=%s user_id=%s role=%s",
                request.method,
                path,
                getattr(response, "status_code", "unknown"),
                duration_ms,
                getattr(user, "user_id", None),
                getattr(user, "role", None),
            )
            return response
        except Exception:
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            user = getattr(request.state, "user", None)
            logger.exception(
                "api_timing_error method=%s path=%s duration_ms=%s user_id=%s role=%s",
                request.method,
                path,
                duration_ms,
                getattr(user, "user_id", None),
                getattr(user, "role", None),
            )
            raise


def create_app() -> FastAPI:
    global limiter
    try:
        # Initialize rate limiter here to avoid .env encoding issues at module load
        limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
        
        app = FastAPI(
            title="Receipt OCR Service",
            description="API for extracting structured data from receipt images and PDFs.",
            version="0.1.0",
        )

        # Add rate limiter to app state
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

        # Add CORS middleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:8001", "http://127.0.0.1:8001", "http://localhost:3000", "http://127.0.0.1:3000"],  # Specific origins
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],  # Explicit methods (security hardening)
            allow_headers=["Authorization", "Content-Type", "X-Requested-With", "Accept"],  # Explicit headers
        )

        # Security headers middleware
        @app.middleware("http")
        async def add_security_headers(request: Request, call_next):
            response = await call_next(request)
            # Prevent MIME type sniffing
            response.headers["X-Content-Type-Options"] = "nosniff"
            # Prevent clickjacking
            response.headers["X-Frame-Options"] = "DENY"
            # Enable XSS filter
            response.headers["X-XSS-Protection"] = "1; mode=block"
            # Control referrer information
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            # Prevent caching of sensitive data
            if request.url.path.startswith("/api/"):
                response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            return response

        app.add_middleware(ApiTimingMiddleware)

        # Add global exception handler to ensure JSON responses for API errors
        @app.exception_handler(Exception)
        async def global_exception_handler(request: Request, exc: Exception):
            """Global exception handler that returns JSON for API requests."""
            if request.url.path.startswith("/api/"):
                # Return JSON error for API endpoints
                return JSONResponse(
                    status_code=500,
                    content={"detail": "Internal server error", "type": "server_error"}
                )
            else:
                # Let FastAPI handle non-API errors normally
                raise exc

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
        app.mount("/accumulation", StaticFiles(directory=str(base_dir / "app" / "Data" / "accumulation")), name="accumulation")

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

        from fastapi import Depends, Header
        from app.auth.dependencies import get_current_user
        from app.models.user import User
        from typing import Optional as Opt
        from jose import jwt, JWTError

        @app.get("/office", response_class=HTMLResponse, tags=["ui"])
        def office_view(
            request: Request,
            authorization: Opt[str] = Header(None)
        ) -> HTMLResponse:
            """Phase 5E: Admin/HQ business office operations view

            Backend enforces authentication when Authorization header present.
            Role-specific enforcement (ADMIN only) is checked here.
            
            This dual-layer approach:
            - Backend: Blocks unauthenticated/WORKER access when auth header present
            - Frontend: JavaScript checks localStorage token for browser redirects
            """
            # Import the JWT secret from the auth module to ensure consistency
            from app.auth.jwt import SECRET_KEY as JWT_SECRET_KEY
            
            # If Authorization header present, verify it
            if authorization:
                try:
                    # Extract and verify JWT token
                    token = authorization.replace("Bearer ", "").strip()
                    
                    # Decode token (using same secret as app.auth.jwt)
                    payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
                    
                    # Check role - only ADMIN allowed
                    role = payload.get("role")
                    if role != "ADMIN":
                        raise HTTPException(status_code=403, detail="Forbidden: ADMIN role required for office view")
                        
                except JWTError as e:
                    raise HTTPException(status_code=401, detail=f"Invalid authentication token: {str(e)}")
                except HTTPException:
                    raise  # Re-raise 403 errors
                except Exception as e:
                    raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")
            
            # Serve the page (JavaScript will check localStorage token for browser access)
            return templates.TemplateResponse("office_view_admin_new.html", {"request": request})

        @app.get("/debug", response_class=HTMLResponse, tags=["ui"])
        def debug_test(request: Request) -> HTMLResponse:
            return templates.TemplateResponse("debug.html", {"request": request})

        @app.get("/diagnostics", response_class=HTMLResponse, tags=["ui"])
        def diagnostics_page(request: Request) -> HTMLResponse:
            """System diagnostics page"""
            return templates.TemplateResponse("diagnostics.html", {"request": request})

        @app.get("/drafts", response_class=HTMLResponse, tags=["ui"])
        def draft_management(request: Request) -> HTMLResponse:
            """Phase 4D: Draft management UI"""
            return templates.TemplateResponse("draft_management.html", {"request": request})

        @app.get("/phase10-demo", response_class=HTMLResponse, tags=["ui"])
        def phase10_demo(request: Request) -> HTMLResponse:
            """Phase 10: Excel as Source of Truth - Demo page"""
            return templates.TemplateResponse("phase10_demo.html", {"request": request})

        @app.get("/hq", response_class=HTMLResponse, tags=["ui"])
        def hq_view(
            request: Request,
            authorization: Opt[str] = Header(None)
        ) -> HTMLResponse:
            """Phase 7.2: HQ read-only view for office-month batches

            Backend enforces authentication when Authorization header present.
            Role-specific enforcement (HQ only) is checked here.
            
            This dual-layer approach:
            - Backend: Blocks unauthenticated/non-HQ access when auth header present
            - Frontend: JavaScript checks localStorage token for browser redirects
            """
            # Import the JWT secret from the auth module to ensure consistency
            from app.auth.jwt import SECRET_KEY as JWT_SECRET_KEY
            
            # If Authorization header present, verify it
            if authorization:
                try:
                    # Extract and verify JWT token
                    token = authorization.replace("Bearer ", "").strip()
                    
                    # Decode token (using same secret as app.auth.jwt)
                    payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
                    
                    # Check role - only HQ allowed
                    role = payload.get("role")
                    if role != "HQ":
                        raise HTTPException(status_code=403, detail="Forbidden: HQ role required for HQ view")
                        
                except JWTError as e:
                    raise HTTPException(status_code=401, detail=f"Invalid authentication token: {str(e)}")
                except HTTPException:
                    raise  # Re-raise 403 errors
                except Exception as e:
                    raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")
            
            # Serve the page (JavaScript will check localStorage token for browser access)
            return templates.TemplateResponse("hq_view_new.html", {"request": request})

        app.include_router(api_router, prefix="/api")
        app.include_router(drafts_router)  # Phase 4B: Draft API endpoints
        app.include_router(audits_router)  # Phase 5A Step 3: Audit API endpoints
        app.include_router(hq_transfer_router)  # Phase 7A-3: Internal HQ transfer endpoints
        app.include_router(hq_view_router)  # Phase 7.2: HQ read-only view endpoints
        app.include_router(system_router)  # Phase 9A.4: System health endpoints
        app.include_router(excel_source_router)  # Phase 10: Excel Source of Truth API
        app.include_router(auth_router)  # Phase 5B.1: Authentication endpoints

        return app

    except Exception as e:
        print(f"Critical error during app initialization: {e}")
        import traceback
        traceback.print_exc()
        raise


# Create app instance for uvicorn
app = create_app()
# Phase 5D-4: Dev user seeding hook (runs on startup in DEV mode only)
@app.on_event("startup")
async def seed_dev_users():
    """Seed development users from config/users_seed_dev.json if ENV=dev."""
    import json
    
    env = os.getenv("ENV", os.getenv("APP_ENV", "")).lower()
    force_seed = os.getenv("SEED_DEV_USERS", "0") == "1"

    # If not explicitly in dev mode, allow seeding when DB is empty or when SEED_DEV_USERS=1
    from app.repositories.user_repository import UserRepository
    repo_check = UserRepository()
    existing_users = repo_check.count_users()

    if env != "dev" and not force_seed and existing_users > 0:
        print(f"DEV SEED: Skipping - environment={env}, force_seed={force_seed}, existing_users={existing_users}")
        return  # Skip seeding in non-dev environments when DB already has users

    seed_file = Path(__file__).parent.parent / "config" / "users_seed_dev.json"
    
    if not seed_file.exists():
        print(f"DEV SEED: Seed file not found: {seed_file}")
        print(f"   Create it using script in config/DEV_USERS_README.md")
        return
    
    try:
        from app.repositories.user_repository import UserRepository
        
        with open(seed_file, 'r') as f:
            users = json.load(f)
        
        repo = UserRepository()
        worker_count = 0
        admin_count = 0
        hq_count = 0
        
        for user_data in users:
            login_id = user_data["login_id"]
            email = user_data.get("email")  # Optional, can be None
            
            repo.upsert_user(
                login_id=login_id,
                email=email,
                plain_password=user_data["password"],
                role=user_data["role"],
                display_name=user_data["display_name"]
            )
            
            if user_data["role"] == "WORKER":
                worker_count += 1
            elif user_data["role"] == "ADMIN":
                admin_count += 1
            elif user_data["role"] == "HQ":
                hq_count += 1
        
        print("=" * 60)
        print(f"DEV SEED: upserted {len(users)} users (workers:{worker_count} admins:{admin_count} hq:{hq_count})")
        print("=" * 60)
        
    except Exception as e:
        print(f"DEV SEED ERROR: {e}")
        import traceback
        traceback.print_exc()


# Phase 5E.2: Cleanup old draft data (24h retention for DRAFT only)
@app.on_event("startup")
async def cleanup_old_drafts():
    """Delete DRAFT rows older than 24 hours to keep DB small.

    Safe by design: skips SENT drafts and ignores rows with NULL created_at.
    Does not touch Excel writers or sent data.
    """
    try:
        from app.repositories.draft_repository import DraftRepository

        repo = DraftRepository()
        deleted = repo.delete_drafts_older_than(hours=24, statuses=["DRAFT"])
        cutoff = datetime.utcnow() - timedelta(hours=24)
        print(f"DRAFT CLEANUP: deleted {deleted} old DRAFT rows (cutoff {cutoff.isoformat()})")
    except Exception as e:
        # Must never block startup
        print(f"DRAFT CLEANUP WARNING: {e}")
