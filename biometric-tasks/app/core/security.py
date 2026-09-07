from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta
import uuid

import logging
import secrets as _secrets

from app.core.config import settings

logger = logging.getLogger(__name__)


def _resolve_secret_key() -> str:
    """
    JWT signing key, from JWT_SECRET_KEY in .env.

    If it's unset we mint a random key for this process rather than falling back
    to a shared default. A known default is the worst option available: it lets
    anyone with a copy of the source forge a token for any user, including
    super_admin. An ephemeral key fails safe instead — tokens simply stop
    validating when the process restarts, which is visible and harmless.
    """
    key = (settings.JWT_SECRET_KEY or "").strip()
    if key:
        return key

    logger.critical(
        "JWT_SECRET_KEY is not set — using a random key generated for this "
        "process. All sessions will be invalidated on restart (and every worker "
        "will sign differently). Set JWT_SECRET_KEY in .env. Generate one with: "
        'python -c "import secrets; print(secrets.token_urlsafe(64))"'
    )
    return _secrets.token_urlsafe(64)


SECRET_KEY = _resolve_secret_key()
ALGORITHM  = settings.JWT_ALGORITHM

ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES
REFRESH_TOKEN_EXPIRE_DAYS   = settings.REFRESH_TOKEN_EXPIRE_DAYS

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ─── Password ─────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


# ─── Access Token ─────────────────────────────────────────────────────────────

def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["type"] = "access"
    payload["jti"] = str(uuid.uuid4())
    payload["exp"] = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# ─── Refresh Token ────────────────────────────────────────────────────────────

def create_refresh_token(data: dict) -> tuple[str, str]:
    """Returns (refresh_token_string, jti)"""
    payload = data.copy()
    payload["type"] = "refresh"
    jti = str(uuid.uuid4())
    payload["jti"] = jti
    payload["exp"] = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token, jti


# ─── Decode Token ─────────────────────────────────────────────────────────────

def decode_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
