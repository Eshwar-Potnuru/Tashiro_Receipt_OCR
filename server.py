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

try:
    import uvicorn
    from app.main import app
    
    if __name__ == "__main__":
        print("🚀 Starting Tashiro Ironworks Receipt OCR Server...")
        print("📱 Unified Mobile/Desktop Interface")
        print("🌐 Server will be available at: http://localhost:8000")
        
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0", 
            port=8000,
            reload=True,
            reload_dirs=[str(project_root)],
            log_level="info"
        )
        
except ImportError as e:
    print(f"❌ Missing dependencies: {e}")
    print("📦 Please install requirements: pip install -r requirements.txt")
    
except Exception as e:
    print(f"❌ Server startup failed: {e}")