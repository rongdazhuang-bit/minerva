"""Password hashing and verification using bcrypt rounds from settings."""

import bcrypt

from app.config import settings


def hash_password(plain: str) -> str:
    """Return bcrypt ASCII digest suitable for persistence."""

    salt = bcrypt.gensalt(rounds=settings.bcrypt_rounds)
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Compare plaintext password against stored bcrypt digest."""

    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
