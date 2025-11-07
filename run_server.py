#!/usr/bin/env python
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✓ Environment variables loaded from .env file")
except ImportError:
    print("✗ python-dotenv not installed")
except Exception as e:
    print(f"✗ Error loading .env file: {e}")

from app.main import app
import uvicorn

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)