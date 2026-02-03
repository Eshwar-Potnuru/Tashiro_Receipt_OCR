#!/usr/bin/env python3
"""
Migrate user login_ids from PY- prefix to TIW- prefix.
This updates existing users to match the new naming convention.
"""

import sys
import os
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.repositories.user_repository import UserRepository

def main():
    repo = UserRepository()
    db_path = repo.db_path
    
    print("🔄 Migrating user login_ids from PY- to TIW-...")
    print()
    
    conn = sqlite3.connect(db_path)
    try:
        # Get all users with PY- prefix
        cursor = conn.execute("SELECT user_id, login_id, name FROM users WHERE login_id LIKE 'PY-%'")
        users = cursor.fetchall()
        
        if not users:
            print("✅ No users with PY- prefix found. Migration not needed.")
            return
        
        print(f"📊 Found {len(users)} users with PY- prefix:")
        print()
        
        updated_count = 0
        for user_id, old_login_id, name in users:
            # Replace PY- with TIW-
            new_login_id = old_login_id.replace('PY-', 'TIW-', 1)
            
            conn.execute(
                "UPDATE users SET login_id = ? WHERE user_id = ?",
                (new_login_id, user_id)
            )
            
            print(f"  {old_login_id:12s} → {new_login_id:12s} | {name}")
            updated_count += 1
        
        conn.commit()
        
        print()
        print("=" * 60)
        print(f"✅ Successfully migrated {updated_count} users to TIW- prefix")
        print("=" * 60)
        print()
        print("You can now login with the new login IDs:")
        print("Example: TIW-WJJ5N / password123")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

if __name__ == "__main__":
    main()
