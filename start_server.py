#!/usr/bin/env python3
"""
Simple server startup script for Tashiro OCR system
"""
import os
import sys
from pathlib import Path


def _ensure_project_venv() -> None:
    """Re-exec under project .venv Python when available.

    This prevents dependency mismatches when users run `python start_server.py`
    with a global interpreter that lacks required packages.
    """
    project_root = Path(__file__).resolve().parent
    venv_python = project_root / ".venv" / "Scripts" / "python.exe"
    if not venv_python.exists():
        return

    current_python = Path(sys.executable).resolve()
    target_python = venv_python.resolve()
    if current_python == target_python:
        return

    print(f"🔁 Switching to project virtual environment: {target_python}")
    os.execv(str(target_python), [str(target_python), str(Path(__file__).resolve()), *sys.argv[1:]])

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_ensure_project_venv()

from app.main import app
import uvicorn

if __name__ == "__main__":
    print("🚀 Starting Tashiro Receipt OCR Server...")
    print("📍 URL: http://localhost:8001")
    print("📱 Mobile UI: http://localhost:8001/mobile")
    print("🔧 API Docs: http://localhost:8001/docs")
    print("❌ Press Ctrl+C to stop")
    print("-" * 50)

    # Keep server running continuously
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8001,
        reload=False,
        log_level="info",
        access_log=True
    )