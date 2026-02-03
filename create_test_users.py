"""Phase 5B.1: Create test users for authentication testing.

Creates 3 test users:
- worker@example.com (WORKER role)
- admin@example.com (ADMIN role)
- hq@example.com (HQ role)

All with password: password123
"""

from uuid import uuid4

from app.auth.password import hash_password
from app.models.user import User, UserRole
from app.repositories.user_repository import UserRepository


def create_test_users():
    """Create test users for authentication testing."""
    repo = UserRepository()
    
    test_users = [
        {
            "name": "Test Worker",
            "email": "worker@example.com",
            "password": "password123",
            "role": UserRole.WORKER
        },
        {
            "name": "Test Admin",
            "email": "admin@example.com",
            "password": "password123",
            "role": UserRole.ADMIN
        },
        {
            "name": "Test HQ",
            "email": "hq@example.com",
            "password": "password123",
            "role": UserRole.HQ
        }
    ]
    
    print("Creating test users...")
    
    for user_data in test_users:
        try:
            # Check if user already exists
            existing = repo.get_user_by_email(user_data["email"])
            if existing:
                print(f"✓ User {user_data['email']} already exists (skipped)")
                continue
            
            # Create new user
            user = User(
                user_id=uuid4(),
                name=user_data["name"],
                email=user_data["email"],
                password_hash=hash_password(user_data["password"]),
                role=user_data["role"],
                is_active=True
            )
            
            repo.create_user(user)
            print(f"✓ Created user {user.email} with role {user.role.value}")
            
        except Exception as e:
            print(f"✗ Failed to create {user_data['email']}: {e}")
    
    print("\nTest users created successfully!")
    print("\nLogin credentials:")
    print("  Email: worker@example.com | Password: password123 | Role: WORKER")
    print("  Email: admin@example.com  | Password: password123 | Role: ADMIN")
    print("  Email: hq@example.com     | Password: password123 | Role: HQ")
    print("\nTest login with:")
    print("  curl -X POST http://localhost:8000/api/auth/login \\")
    print("    -H 'Content-Type: application/json' \\")
    print("    -d '{\"email\":\"worker@example.com\",\"password\":\"password123\"}'")


if __name__ == "__main__":
    create_test_users()
