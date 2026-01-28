#!/usr/bin/env python3
import os
import sys

# Add the path to make imports work
sys.path.insert(0, '/app')

print("=== Path Resolution Debug ===")

# Check current working directory
print(f"Current working directory: {os.getcwd()}")

# Check file location
file_path = os.path.abspath(__file__)
print(f"This file path: {file_path}")

# Simulate the path resolution from multi_engine_ocr.py
script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
google_creds_path = os.path.join(script_dir, 'config', 'google_vision_key.json')
print(f"Constructed path: {google_creds_path}")
print(f"File exists: {os.path.exists(google_creds_path)}")

# Check environment variable
env_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
print(f"Environment variable: {env_path}")
if env_path:
    print(f"Env file exists: {os.path.exists(env_path)}")

# List files in expected directory
config_dir = os.path.join(script_dir, 'config')
print(f"Config directory: {config_dir}")
if os.path.exists(config_dir):
    print("Files in config directory:")
    for f in os.listdir(config_dir):
        print(f"  - {f}")
else:
    print("Config directory does not exist!")