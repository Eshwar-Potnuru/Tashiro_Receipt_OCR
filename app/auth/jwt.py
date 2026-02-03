"""Phase 5B.1: JWT Token Management

JWT token creation and verification for user authentication.

Design Decisions:
- Algorithm: HS256 (symmetric key)
- Secret: From JWT_SECRET environment variable
- Expiry: 24 hours default (configurable)
- Claims: sub (user_id), email, role, exp
"""

import os
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr

from app.models.user import UserRole


# JWT configuration
SECRET_KEY = os.getenv("JWT_SECRET", "dev-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24


class TokenData(BaseModel):
    """Data extracted from JWT token.
    
    Attributes:
        user_id: User UUID
        email: User email
        role: User role (WORKER, ADMIN, HQ)
        login_id: Optional login ID (Phase 5D-4.1)
    """
    user_id: UUID
    email: EmailStr
    role: UserRole
    login_id: Optional[str] = None


def create_access_token(
    user_id: UUID,
    email: str,
    role: UserRole,
    name: Optional[str] = None,
    login_id: Optional[str] = None,
    expires_delta: Optional[timedelta] = None
) -> str:
    """Create a JWT access token.
    
    Phase 5D-4.1: Added optional login_id field for human-friendly identifiers.
    
    Args:
        user_id: User UUID
        email: User email
        role: User role
        name: Optional display name (Phase 5D-4)
        login_id: Optional login ID (e.g., PY-XXXXX) (Phase 5D-4.1)
        expires_delta: Token expiration time. If None, uses default (24 hours)
    
    Returns:
        JWT token as string
    """
    if expires_delta is None:
        expires_delta = timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    
    expire = datetime.utcnow() + expires_delta
    
    # Handle role as either Enum or string (due to use_enum_values=True)
    role_str = role.value if isinstance(role, UserRole) else role
    
    to_encode = {
        "sub": str(user_id),  # Subject: user_id
        "email": email,
        "role": role_str,
        "exp": expire
    }
    
    # Phase 5D-4: Add name if provided
    if name:
        to_encode["name"] = name
    
    # Phase 5D-4.1: Add login_id if provided
    if login_id:
        to_encode["login_id"] = login_id
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_access_token(token: str) -> Optional[TokenData]:
    """Verify a JWT access token and extract user data.
    
    Args:
        token: JWT token string
    
    Returns:
        TokenData if token is valid, None if invalid/expired
    
    Example:
        >>> from uuid import uuid4
        >>> user_id = uuid4()
        >>> token = create_access_token(user_id, "worker@example.com", UserRole.WORKER)
        >>> data = verify_access_token(token)
        >>> data.user_id == user_id
        True
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        user_id_str: str = payload.get("sub")
        email: str = payload.get("email")
        role_str: str = payload.get("role")
        
        if not user_id_str or not email or not role_str:
            return None
        
        return TokenData(
            user_id=UUID(user_id_str),
            email=email,
            role=UserRole(role_str)
        )
    except JWTError:
        return None
