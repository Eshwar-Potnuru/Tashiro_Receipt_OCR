"""Phase 5B.1: User Model for Authentication

User model with identity and role management.

Design Decisions:
- UUID for user_id (distributed-friendly)
- Email as unique identifier
- Role enum for access control
- Password stored as bcrypt hash
- SQLite persistence (same DB as drafts)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, EmailStr, Field


class UserRole(str, Enum):
    """User role types for access control.
    
    WORKER: Regular employee (can create/edit own drafts)
    ADMIN: Location admin (can manage location users)
    HQ: Headquarters (can view all drafts, manage system)
    """
    WORKER = "WORKER"
    ADMIN = "ADMIN"
    HQ = "HQ"


class User(BaseModel):
    """User domain model for authentication and identity.
    
    Attributes:
        user_id: Unique identifier (UUID)
        login_id: Human-friendly login identifier (e.g., PY-XXXXX)
        name: Display name
        email: Unique email address (used for login)
        password_hash: Bcrypt hashed password
        role: User role (WORKER, ADMIN, HQ)
        is_active: Whether user account is active
        created_at: Account creation timestamp
    """
    
    user_id: UUID = Field(default_factory=uuid4)
    login_id: Optional[str] = Field(None, description="Human-friendly login ID")
    name: str = Field(..., min_length=1, max_length=100)
    email: Optional[EmailStr] = Field(None, description="Unique email for login (optional)")
    password_hash: str = Field(..., description="Bcrypt hash of password")
    role: UserRole = Field(default=UserRole.WORKER)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.now)

    class Config:
        use_enum_values = True


class UserCreate(BaseModel):
    """Request model for creating a new user."""
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8, description="Plain password (will be hashed)")
    role: UserRole = Field(default=UserRole.WORKER)


class UserResponse(BaseModel):
    """Public user info (no password hash)."""
    user_id: UUID
    login_id: Optional[str]
    name: str
    email: Optional[str]
    role: UserRole
    is_active: bool
    created_at: datetime

    @classmethod
    def from_user(cls, user: User) -> UserResponse:
        """Convert User to safe response model."""
        return cls(
            user_id=user.user_id,
            login_id=user.login_id,
            name=user.name,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at
        )
