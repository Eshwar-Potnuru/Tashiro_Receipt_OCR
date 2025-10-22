#!/usr/bin/env python3
"""
Tashiro Ironworks Receipt OCR System
Main execution script - Run this file to start the complete system
"""

import sys
import os
from pathlib import Path

# Add current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from app.main import create_app
import uvicorn

def main():
    """Main entry point for the Tashiro Receipt OCR System"""

    print("🏭 Tashiro Ironworks Receipt OCR System")
    print("=" * 50)
    print("🚀 Starting server...")

    # Get port from environment (Railway provides PORT)
    port = int(os.environ.get("PORT", 8000))

    print(f"📱 Mobile interface: http://localhost:{port}/mobile")
    print(f"🖥️  Desktop interface: http://localhost:{port}/")
    print(f"📚 API Documentation: http://localhost:{port}/docs")
    print("=" * 50)

    # Create the FastAPI application
    app = create_app()

    # Start the server
    uvicorn.run(
        app,
        host='0.0.0.0',  # Allow external access for mobile testing
        port=port,       # Use Railway's PORT environment variable
        reload=False,    # Disable reload for production stability
        access_log=True
    )

if __name__ == "__main__":
    main()