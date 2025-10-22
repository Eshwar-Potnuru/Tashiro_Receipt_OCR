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
    try:
        print("🏭 Tashiro Ironworks Receipt OCR System")
        print("=" * 50)
        print("🚀 Starting server...")

        # Get port from environment (Railway provides PORT)
        port_env = os.environ.get("PORT")
        if port_env:
            try:
                port = int(port_env)
                print(f"📡 Using Railway PORT: {port}")
            except ValueError:
                print(f"⚠️ Invalid PORT value: {port_env}, using default 8000")
                port = 8000
        else:
            port = 8000
            print("📡 No PORT environment variable, using default 8000")

        print(f"📱 Mobile interface: http://localhost:{port}/mobile")
        print(f"🖥️  Desktop interface: http://localhost:{port}/")
        print(f"📚 API Documentation: http://localhost:{port}/docs")
        print("=" * 50)

        # Create the FastAPI application
        print("🔧 Creating FastAPI application...")
        app = create_app()
        print("✅ Application created successfully")

        # Start the server
        print(f"🌐 Starting uvicorn server on port {port}...")
        uvicorn.run(
            app,
            host='0.0.0.0',  # Allow external access for mobile testing
            port=port,       # Use Railway's PORT environment variable
            reload=False,    # Disable reload for production stability
            access_log=True,
            log_level="info"
        )

    except Exception as e:
        print(f"❌ Critical error during startup: {e}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    main()