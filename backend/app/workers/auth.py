from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

_SECRET = "job-matcher-jwt-secret-change-in-prod"
_ALGORITHM = "HS256"
_EXPIRY_DAYS = 7


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=_EXPIRY_DAYS)
    return jwt.encode({"sub": user_id, "exp": expire}, _SECRET, algorithm=_ALGORITHM)


def decode_token(token: str) -> str:
    """Returns user_id or raises JWTError."""
    payload = jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])
    sub = payload.get("sub")
    if not sub:
        raise JWTError("Missing sub claim")
    return sub
