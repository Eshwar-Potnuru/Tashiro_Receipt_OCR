"""Phase 5B.1: Authentication API Routes

Provides user authentication endpoints.

Endpoints:
- POST /api/auth/login - User login with email/password
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.auth.jwt import create_access_token
from app.auth.password import verify_password
from app.models.user import UserResponse
from app.repositories.user_repository import UserRepository

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    """Login request payload.
    
    Attributes:
        email: User identifier (email or login_id like PY-XXXXX)
        password: Plain text password
    """
    email: str
    password: str


class LoginResponse(BaseModel):
    """Login response payload.
    
    Attributes:
        access_token: JWT access token
        token_type: Token type (always "bearer")
        user: Public user information
    """
    access_token: str
    token_type: str
    user: UserResponse


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest) -> LoginResponse:
    """Authenticate user and return JWT token.
    
    Phase 5D-4: Supports login with email OR user_id (dev flexibility).
    Lookup priority: 1) email, 2) user_id
    
    Args:
        request: Login credentials (email/user_id + password)
    
    Returns:
        LoginResponse with access token and user info
    
    Raises:
        HTTPException 401: If credentials invalid or account inactive
    
    Example:
        POST /api/auth/login
        {
            "email": "worker@example.com",  # or "w01_sam"
            "password": "password123"
        }
    """
    repo = UserRepository()
    
    # Phase 5D-4.1: Try email first, then login_id (PY-XXXXX)
    user = repo.get_user_by_email(request.email)
    
    if not user:
        # Try as login_id (for dev users like 'PY-V48XE')
        user = repo.get_user_by_login_id(request.email)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    # Verify password
    if not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    # Check if account is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is inactive"
        )
    
    # Create JWT token with user_id, email, role, name, login_id
    access_token = create_access_token(
        user_id=user.user_id,
        email=user.email,
        role=user.role,
        name=user.name,  # Phase 5D-4: Include display name in JWT
        login_id=user.login_id  # Phase 5D-4.1: Include login_id in JWT
    )
    
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.from_user(user)
    )
