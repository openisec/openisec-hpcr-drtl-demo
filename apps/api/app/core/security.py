import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jose import JWTError, jwt

from app.core.config import get_settings

settings = get_settings()
ph = PasswordHasher()

# ---- Password hashing (Argon2id) ----

def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return ph.verify(hashed, plain)
    except VerifyMismatchError:
        return False


# ---- JWT tokens ----

def create_access_token(subject: str, extra: dict | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": subject, "exp": expire, **(extra or {})}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None


# ---- Input Guardrail ----

# Whitelist: allow only plain text characters (no code constructs)
_DISALLOWED_PATTERNS = [
    r"<script[\s\S]*?>",          # XSS
    r"javascript\s*:",             # JS injection
    r"(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|--)\s",  # SQL injection
    r"(\{\{|\}\}|{%|%})",          # Template injection
    r"(system\(|exec\(|eval\(|subprocess)",  # Code execution
    r"ignore previous instructions",  # Prompt injection
    r"(you are now|act as|pretend you)",  # Role hijacking
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _DISALLOWED_PATTERNS]

# PII patterns
_PII_PATTERNS = [
    (re.compile(r'\b[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}\b'), "[EMAIL]"),
    (re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'), "[CARD]"),
    (re.compile(r'\b\d{3}-\d{2}-\d{4}\b'), "[SSN]"),
]


def validate_input(text: str, max_chars: int = 4000) -> tuple[bool, str]:
    """Returns (is_valid, reason). Empty reason = OK."""
    if len(text) > max_chars:
        return False, f"Input exceeds {max_chars} characters"
    for pattern in _COMPILED_PATTERNS:
        if pattern.search(text):
            return False, "Input contains disallowed content"
    return True, ""


def mask_pii(text: str) -> str:
    for pattern, replacement in _PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def generate_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)
