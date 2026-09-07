"""
Security module for GridSphere IoT Core
Handles password hashing, JWT token creation/validation, and cryptography
"""
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta
import uuid
import os
import logging

logger = logging.getLogger(__name__)

# =====================
# CONFIGURATION
# =====================

# SECRET_KEY should be set via environment variable in production
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_THIS_SECRET_IN_PRODUCTION")
ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "14400"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# =====================
# PASSWORD HASHING CONTEXT
# =====================

# Configure bcrypt with explicit settings for production compatibility
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,  # Balance between security and performance
    bcrypt__ident="2b"  # Force bcrypt 2b algorithm
)


# =====================
# PASSWORD UTILITIES
# =====================

def _truncate_password(password: str, max_bytes: int = 72) -> str:
    """
    Truncate password to max_bytes for bcrypt compatibility.
    bcrypt has a 72-byte limit on password length.
    """
    password_bytes = password.encode('utf-8')
    if len(password_bytes) > max_bytes:
        # Truncate at byte level, not character level
        truncated = password_bytes[:max_bytes].decode('utf-8', errors='ignore')
        logger.warning(f"Password truncated from {len(password_bytes)} to {max_bytes} bytes")
        return truncated
    return password


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.
    
    Args:
        password: Plain text password
        
    Returns:
        Hashed password string
    """
    if not password:
        raise ValueError("Password cannot be empty")
    
    # Truncate for bcrypt compatibility
    truncated = _truncate_password(password)
    
    try:
        return pwd_context.hash(truncated)
    except Exception as e:
        logger.error(f"Password hashing failed: {e}")
        raise ValueError(f"Failed to hash password: {e}")


def verify_password(password: str, hashed: str) -> bool:
    """
    Verify a password against its hash.
    
    Args:
        password: Plain text password to verify
        hashed: Stored hash to compare against
        
    Returns:
        True if password matches, False otherwise
    """
    if not password or not hashed:
        return False
    
    # Truncate for bcrypt compatibility (same as during hashing)
    truncated = _truncate_password(password)
    
    try:
        return pwd_context.verify(truncated, hashed)
    except Exception as e:
        logger.error(f"Password verification failed: {e}")
        return False


def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    Validate password meets security requirements.
    
    Args:
        password: Password to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter"
    
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter"
    
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one number"
    
    return True, ""


# =====================
# JWT TOKEN UTILITIES
# =====================

def create_access_token(data: dict) -> str:
    """
    Create a new JWT access token.
    
    Args:
        data: Payload data to encode
        
    Returns:
        Encoded JWT token string
    """
    payload = data.copy()
    payload["type"] = "access"
    payload["jti"] = str(uuid.uuid4())  # Unique token ID for revocation
    payload["iat"] = datetime.utcnow()  # Issued at
    payload["exp"] = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict) -> tuple[str, str]:
    """
    Create a new JWT refresh token.
    
    Args:
        data: Payload data to encode
        
    Returns:
        Tuple of (refresh_token_string, jti)
        jti is stored in DB for rotation/revocation
    """
    payload = data.copy()
    payload["type"] = "refresh"
    jti = str(uuid.uuid4())
    payload["jti"] = jti
    payload["iat"] = datetime.utcnow()
    payload["exp"] = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token, jti


def decode_token(token: str) -> dict | None:
    """
    Decode and validate a JWT token.
    
    Args:
        token: JWT token string
        
    Returns:
        Decoded payload dict if valid, None if invalid/expired
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.info("Token has expired")
        return None
    except jwt.JWTError as e:
        logger.warning(f"Invalid token: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error decoding token: {e}")
        return None


def get_token_remaining_seconds(token: str) -> int | None:
    """
    Get remaining validity time of a token in seconds.
    
    Args:
        token: JWT token string
        
    Returns:
        Seconds until expiration, or None if invalid
    """
    payload = decode_token(token)
    if not payload or "exp" not in payload:
        return None
    
    exp_timestamp = payload["exp"]
    exp_datetime = datetime.fromtimestamp(exp_timestamp)
    remaining = exp_datetime - datetime.utcnow()
    
    return max(0, int(remaining.total_seconds()))


def is_token_expiring_soon(token: str, threshold_minutes: int = 5) -> bool:
    """
    Check if token is about to expire.
    
    Args:
        token: JWT token string
        threshold_minutes: Minutes before expiration to consider "soon"
        
    Returns:
        True if token expires within threshold
    """
    remaining = get_token_remaining_seconds(token)
    if remaining is None:
        return True
    
    return remaining < (threshold_minutes * 60)


# =====================
# SECURITY HEADERS (For Middleware)
# =====================

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": "default-src 'self'",
}


# =====================
# PRODUCTION WARNINGS
# =====================

def check_production_settings() -> list[str]:
    """
    Check if security settings are production-ready.
    Returns list of warnings.
    """
    warnings = []
    
    if SECRET_KEY == "CHANGE_THIS_SECRET_IN_PRODUCTION":
        warnings.append("SECRET_KEY is using default value - CHANGE IT!")
    
    if len(SECRET_KEY) < 32:
        warnings.append("SECRET_KEY should be at least 32 characters")
    
    if ACCESS_TOKEN_EXPIRE_MINUTES > 60:
        warnings.append("Access token expiration > 60 minutes - consider reducing")
    
    return warnings


# Log warnings on startup
_warnings = check_production_settings()
for warning in _warnings:
    logger.warning(f"⚠️ SECURITY: {warning}")
