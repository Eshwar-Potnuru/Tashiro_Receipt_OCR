#!/usr/bin/env python3
"""Quick script to check if users exist in the database."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.repositories.user_repository import UserRepository

def main():
    repo = UserRepository()
    
    # Try to get the user TIW-WJJ5N
    user = repo.get_user_by_login_id("TIW-WJJ5N")
    
    if user:
        print("✅ User TIW-WJJ5N found in database:")
        print(f"   Login ID: {user.login_id}")
        print(f"   Email: {user.email}")
        print(f"   Name: {user.name}")
        print(f"   Role: {user.role}")
        print(f"   Active: {user.is_active}")
    else:
        print("❌ User TIW-WJJ5N NOT found in database!")
        print("\nThis means the database was not seeded with dev users.")
        print("The seed_dev_users() function only runs when ENV=dev is set.")

if __name__ == "__main__":
    main()
