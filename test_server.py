#!/usr/bin/env python
import sys
import os

# Add current directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

print(f"Current directory: {current_dir}")
print(f"Python path: {sys.path}")

try:
    from app.main import app
    print("✅ App import successful")

    import uvicorn
    print("🚀 Starting server on http://127.0.0.1:8005")
    uvicorn.run(app, host="127.0.0.1", port=8005)
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
