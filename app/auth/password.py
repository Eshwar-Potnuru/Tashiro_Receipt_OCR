"""Phase 5B.1: Password Security Utilities

Provides bcrypt-based password hashing and verification.

Security Notes:
- Uses bcrypt for password hashing (work factor 12)
- Plain passwords are never stored
- Hashes are stored as strings in database
"""

from passlib.context import CryptContext

# Bcrypt context with work factor 12
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a plain password using bcrypt.
    
    Args:
        password: Plain text password
    
    Returns:
        Bcrypt hash as string (safe to store in database)
    
    Example:
        >>> hashed = hash_password("mypassword")
        >>> hashed.startswith("$2b$")
        True
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against its hash.
    
    Args:
        plain_password: Plain text password to check
        hashed_password: Bcrypt hash from database
    
    Returns:
        True if password matches, False otherwise
    
    Example:
        >>> hashed = hash_password("mypassword")
        >>> verify_password("mypassword", hashed)
        True
        >>> verify_password("wrongpassword", hashed)
        False
    """
    return pwd_context.verify(plain_password, hashed_password)
