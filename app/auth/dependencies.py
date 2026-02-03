"""Phase 5B.1: Authentication Dependencies

FastAPI dependencies for protecting routes and extracting user identity.

Usage:
    @router.get("/protected")
    async def protected_route(current_user: User = Depends(get_current_user)):
        return {"user": current_user.email}
"""

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.jwt import verify_access_token
from app.models.user import User
from app.repositories.user_repository import UserRepository

# HTTP Bearer token security
security = HTTPBearer()


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """Extract and verify current user from JWT token.
    
    Attaches user to request.state.user for access in other parts of the request.
    
    Args:
        request: FastAPI request object
        credentials: Bearer token from Authorization header
    
    Returns:
        User object if authenticated
    
    Raises:
        HTTPException 401: If token is invalid, expired, or user not found/inactive
    
    Example:
        Authorization: Bearer <jwt-token>
    """
    token = credentials.credentials
    
    # Verify token
    token_data = verify_access_token(token)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Load user from database
    repo = UserRepository()
    user = repo.get_user_by_id(token_data.user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Attach to request state for easy access
    request.state.user = user
    
    return user


async def get_optional_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))
) -> Optional[User]:
    """Extract user from JWT token if present, otherwise return None.
    
    For routes that support both authenticated and anonymous access.
    
    Args:
        request: FastAPI request object
        credentials: Bearer token from Authorization header (optional)
    
    Returns:
        User object if authenticated, None if no token or invalid token
    """
    if not credentials:
        return None
    
    token = credentials.credentials
    
    # Verify token
    token_data = verify_access_token(token)
    if not token_data:
        return None
    
    # Load user from database
    repo = UserRepository()
    user = repo.get_user_by_id(token_data.user_id)
    
    if not user or not user.is_active:
        return None
    
    # Attach to request state
    request.state.user = user
    
    return user
