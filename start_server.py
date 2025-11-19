#!/usr/bin/env python3
"""
Simple server startup script for Tashiro OCR system
"""
import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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