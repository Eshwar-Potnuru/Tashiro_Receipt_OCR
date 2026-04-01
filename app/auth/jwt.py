"""Phase 5B.1: JWT Token Management

JWT token creation and verification for user authentication.

Design Decisions:
- Algorithm: HS256 (symmetric key)
- Secret: From JWT_SECRET environment variable (REQUIRED)
- Expiry: 24 hours default (configurable)
- Claims: sub (user_id), email, role, exp

Security Notes:
- JWT_SECRET must be set in production (no default fallback)
- Secret should be at least 32 characters
- Use cryptographically random value: python -c "import secrets; print(secrets.token_hex(32))"
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr

from app.models.user import UserRole

logger = logging.getLogger(__name__)

# JWT configuration - SECURITY: No default fallback in production
_jwt_secret = os.getenv("JWT_SECRET")
_is_dev_mode = os.getenv("ENVIRONMENT", "development").lower() in ("development", "dev", "local", "test")

if not _jwt_secret:
    if _is_dev_mode:
        # Only allow dev default in explicit development mode
        _jwt_secret = "dev-secret-key-DO-NOT-USE-IN-PRODUCTION"
        logger.warning("⚠️ JWT_SECRET not set - using development default. DO NOT use in production!")
    else:
        raise RuntimeError(
            "CRITICAL: JWT_SECRET environment variable must be set. "
            "Generate with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )

if len(_jwt_secret) < 32 and not _is_dev_mode:
    raise RuntimeError(f"CRITICAL: JWT_SECRET must be at least 32 characters (current: {len(_jwt_secret)})")

SECRET_KEY = _jwt_secret
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24


class TokenData(BaseModel):
    """Data extracted from JWT token.
    
    Attributes:
        user_id: User UUID
        email: Optional user email (None for HQ users without email)
        role: User role (WORKER, ADMIN, HQ)
        login_id: Optional login ID (Phase 5D-4.1)
    """
    user_id: UUID
    email: Optional[str] = None
    role: UserRole
    login_id: Optional[str] = None


def create_access_token(
    user_id: UUID,
    email: Optional[str],
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
        "role": role_str,
        "exp": expire
    }
    
    # Only include email if provided (HQ users may not have email)
    if email:
        to_encode["email"] = email
    
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
        email: Optional[str] = payload.get("email")  # Optional for HQ users
        role_str: str = payload.get("role")
        login_id: Optional[str] = payload.get("login_id")  # Phase 7.2: Include login_id
        
        if not user_id_str or not role_str:
            return None
        
        return TokenData(
            user_id=UUID(user_id_str),
            email=email,
            role=UserRole(role_str),
            login_id=login_id
        )
    except JWTError:
        return None
