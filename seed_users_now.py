#!/usr/bin/env python3
"""Manually seed the database with users from config/users_seed_dev.json"""

import sys
import os
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.repositories.user_repository import UserRepository

def main():
    seed_file = Path(__file__).parent / "config" / "users_seed_dev.json"
    
    if not seed_file.exists():
        print(f"❌ Seed file not found: {seed_file}")
        return
    
    try:
        with open(seed_file, 'r') as f:
            users = json.load(f)
        
        repo = UserRepository()
        worker_count = 0
        admin_count = 0
        hq_count = 0
        
        print(f"📂 Loading {len(users)} users from {seed_file.name}...")
        print()
        
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
            
            print(f"✅ {login_id:12s} | {user_data['role']:8s} | {user_data['display_name']}")
        
        print()
        print("=" * 60)
        print(f"✅ Successfully seeded {len(users)} users:")
        print(f"   - Workers: {worker_count}")
        print(f"   - Admins: {admin_count}")
        print(f"   - HQ: {hq_count}")
        print("=" * 60)
        print()
        print("You can now login with any of these users.")
        print("Example: TIW-WJJ5N / password123")
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
