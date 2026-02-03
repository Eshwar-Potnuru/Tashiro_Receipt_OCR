#!/usr/bin/env python3
"""Check what users currently exist in the database."""

import sys
import os
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.repositories.user_repository import UserRepository

def main():
    repo = UserRepository()
    db_path = repo.db_path
    
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute("SELECT login_id, email, name, role FROM users")
        rows = cursor.fetchall()
        
        if rows:
            print(f"📊 Found {len(rows)} users in database:")
            print()
            for row in rows:
                login_id, email, name, role = row
                email_display = email if email else "(null)"
                print(f"  {login_id:12s} | {role:8s} | {name:20s} | {email_display}")
        else:
            print("📭 Database is empty - no users found.")
            
    finally:
        conn.close()

if __name__ == "__main__":
    main()
