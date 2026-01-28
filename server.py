#!/usr/bin/env python3
"""
Simple server script to run the unified Receipt OCR interface
"""

import sys
import os
from pathlib import Path

# Add the project directory to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load environment variables from .env file BEFORE importing app
try:
    from dotenv import load_dotenv
    # Load .env and set environment variables IMMEDIATELY
    load_dotenv(override=True)
    
    # Explicitly set GOOGLE_APPLICATION_CREDENTIALS in os.environ
    # This ensures child processes (like uvicorn reload) inherit it
    google_creds = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
    if google_creds:
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = google_creds
        print(f"[OK] Google credentials set: {google_creds}")
        print(f"[OK] File exists: {Path(google_creds).exists()}")
    else:
        print("[WARNING] GOOGLE_APPLICATION_CREDENTIALS not set in .env")
    
    print("[OK] Environment variables loaded from .env file")
except ImportError:
    print("[ERROR] python-dotenv not installed")
except Exception as e:
    print(f"[ERROR] Error loading .env file: {e}")

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Launch the Tashiro Receipt OCR FastAPI server")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to expose")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for local development")
    parser.add_argument("--log-level", default="info", help="Uvicorn log level")
    args = parser.parse_args()

    try:
        import uvicorn
        from app.main import app

        print("Starting Tashiro Ironworks Receipt OCR Server...")
        print("Unified Mobile/Desktop Interface")
        print(f"Server available at: http://{args.host}:{args.port}")
        if args.reload:
            print("Auto-reload enabled (development mode)")

        uvicorn.run(
            "app.main:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            reload_dirs=[str(project_root)],
            log_level=args.log_level
        )

    except ImportError as e:
        print(f"Missing dependencies: {e}")
        print("Please install requirements: pip install -r requirements.txt")

    except Exception as e:
        print(f"Server startup failed: {e}")


if __name__ == "__main__":
    main()