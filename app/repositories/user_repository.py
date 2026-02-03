"""Phase 5B.1: User Repository for SQLite Persistence

SQLite-based persistence for User objects.

Design Decisions:
- Uses same database as drafts (app/Data/drafts.db)
- Email is unique constraint
- Thread-safe with connection-per-operation pattern
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

from app.models.user import User, UserRole


class UserRepository:
    """SQLite-based persistence for User objects.
    
    Storage Strategy:
        - SQLite database at app/Data/drafts.db (same as drafts)
        - Single table: users
        - Email has UNIQUE constraint
        - Automatic schema creation on first use
    
    Thread Safety:
        - Connection-per-operation pattern
        - SQLite handles concurrency via file locks
    """

    def __init__(self, db_path: Optional[str] = None):
        """Initialize repository with database path.
        
        Args:
            db_path: Path to SQLite database file. If None, uses default
                    location at app/Data/drafts.db
        """
        if db_path is None:
            # Default: app/Data/drafts.db (same as drafts)
            app_dir = Path(__file__).parent.parent
            data_dir = app_dir / "Data"
            data_dir.mkdir(exist_ok=True)
            db_path = str(data_dir / "drafts.db")
        
        self.db_path = db_path
        self._init_schema()

    def _init_schema(self) -> None:
        """Create users table if it doesn't exist.
        
        Schema:
            user_id: TEXT PRIMARY KEY (UUID as string)
            login_id: TEXT UNIQUE (human-friendly identifier like PY-XXXXX)
            name: TEXT NOT NULL
            email: TEXT NOT NULL UNIQUE
            password_hash: TEXT NOT NULL
            role: TEXT NOT NULL (WORKER, ADMIN, HQ)
            is_active: INTEGER NOT NULL (0 or 1)
            created_at: TEXT NOT NULL (ISO timestamp)
        """
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    login_id TEXT UNIQUE,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL,
                    is_active INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            # Add login_id column if it doesn't exist (backward compatible)
            try:
                conn.execute("ALTER TABLE users ADD COLUMN login_id TEXT")
                conn.commit()
            except sqlite3.OperationalError:
                # Column already exists
                pass
            conn.commit()
        finally:
            conn.close()

    def create_user(self, user: User) -> User:
        """Create a new user.
        
        Args:
            user: User object to create
        
        Returns:
            The created user (same instance)
        
        Raises:
            sqlite3.IntegrityError: If email already exists
        """
        conn = sqlite3.connect(self.db_path)
        try:
            # user.role is already a string due to use_enum_values=True
            conn.execute("""
                INSERT INTO users (
                    user_id, login_id, name, email, password_hash, role, is_active, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(user.user_id),
                user.login_id,
                user.name,
                user.email,
                user.password_hash,
                user.role,  # Already a string from Pydantic
                1 if user.is_active else 0,
                user.created_at.isoformat()
            ))
            conn.commit()
            return user
        finally:
            conn.close()

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email address.
        
        Args:
            email: Email address
        
        Returns:
            User if found, None otherwise
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("""
                SELECT user_id, login_id, name, email, password_hash, role, is_active, created_at
                FROM users WHERE email = ?
            """, (email,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            return User(
                user_id=UUID(row[0]),
                login_id=row[1],
                name=row[2],
                email=row[3],
                password_hash=row[4],
                role=UserRole(row[5]),
                is_active=bool(row[6]),
                created_at=datetime.fromisoformat(row[7])
            )
        finally:
            conn.close()

    def get_user_by_id(self, user_id: UUID) -> Optional[User]:
        """Get user by user_id.
        
        Args:
            user_id: User UUID
        
        Returns:
            User if found, None otherwise
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("""
                SELECT user_id, login_id, name, email, password_hash, role, is_active, created_at
                FROM users WHERE user_id = ?
            """, (str(user_id),))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            return User(
                user_id=UUID(row[0]),
                login_id=row[1],
                name=row[2],
                email=row[3],
                password_hash=row[4],
                role=UserRole(row[5]),
                is_active=bool(row[6]),
                created_at=datetime.fromisoformat(row[7])
            )
        finally:
            conn.close()

    def get_user_by_login_id(self, login_id: str) -> Optional[User]:
        """Get user by login_id (human-friendly identifier).
        
        Args:
            login_id: Login ID (e.g., PY-XXXXX)
        
        Returns:
            User if found, None otherwise
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("""
                SELECT user_id, login_id, name, email, password_hash, role, is_active, created_at
                FROM users WHERE login_id = ?
            """, (login_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            return User(
                user_id=UUID(row[0]),
                login_id=row[1],
                name=row[2],
                email=row[3],
                password_hash=row[4],
                role=UserRole(row[5]),
                is_active=bool(row[6]),
                created_at=datetime.fromisoformat(row[7])
            )
        finally:
            conn.close()

    def upsert_user(self, login_id: str, email: Optional[str], plain_password: str, role: str, display_name: str) -> User:
        """Create or update user (for dev seeding).
        
        Phase 5D-4.2: Upsert logic for dev user provisioning.
        - Creates user if not exists (generates UUID for user_id)
        - Updates role/email/name if user exists
        - Stores login_id as human-friendly identifier (required)
        - Email is optional (can be None)
        - Only hashes password if user is new
        
        Args:
            login_id: Human-friendly login ID (e.g., PY-XXXXX) - required
            email: User email (optional, can be None)
            plain_password: Plain text password (will be hashed)
            role: User role (WORKER, ADMIN, HQ)
            display_name: Display name
        
        Returns:
            Created or updated User object
        """
        from app.auth.password import hash_password
        
        if not login_id:
            raise ValueError("login_id is required")
        
        conn = sqlite3.connect(self.db_path)
        try:
            # Check if user exists by login_id
            existing = self.get_user_by_login_id(login_id)
            
            if existing:
                # Update existing user (only role/email/name, not password)
                conn.execute("""
                    UPDATE users
                    SET name = ?, email = ?, role = ?
                    WHERE login_id = ?
                """, (display_name, email, role, login_id))
                conn.commit()
                
                # Return updated user
                return User(
                    user_id=existing.user_id,
                    login_id=login_id,
                    name=display_name,
                    email=email,
                    password_hash=existing.password_hash,
                    role=UserRole(role),
                    is_active=True,
                    created_at=existing.created_at
                )
            else:
                # Create new user with hashed password and generated UUID
                password_hash = hash_password(plain_password)
                created_at = datetime.now()
                user_id = uuid4()
                
                conn.execute("""
                    INSERT INTO users (
                        user_id, login_id, name, email, password_hash, role, is_active, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(user_id),
                    login_id,
                    display_name,
                    email,
                    password_hash,
                    role,
                    1,
                    created_at.isoformat()
                ))
                conn.commit()
                
                return User(
                    user_id=user_id,
                    login_id=login_id,
                    name=display_name,
                    email=email,
                    password_hash=password_hash,
                    role=UserRole(role),
                    is_active=True,
                    created_at=created_at
                )
        finally:
            conn.close()
