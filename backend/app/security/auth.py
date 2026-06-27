import os
import time
import json
import base64
import hmac
import hashlib
import uuid
from typing import Optional
from fastapi import Header, HTTPException, status, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.models import User

app_env = os.getenv("APP_ENV", "development").lower()
AUTH_SECRET = os.getenv("AUTH_SECRET") or os.getenv("ENCRYPTION_KEY")

if app_env == "production":
    if not AUTH_SECRET or AUTH_SECRET in (
        "dev-auth-secret-key-32-chars-minimum-for-security",
        "vwW6pdYns-N3IpM4slyoaCUl8hwdY01EizkJvvyytz8=",
        "MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE=",
        "MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE",
        "01234567890123456789012345678901"
    ):
        raise RuntimeError("AUTH_SECRET must be securely configured in production mode!")
else:
    if not AUTH_SECRET:
        AUTH_SECRET = "dev-auth-secret-key-32-chars-minimum-for-security"

def sign_user_token(email: str, user_id: str) -> str:
    payload = {
        "email": email,
        "user_id": user_id,
        "exp": time.time() + 7 * 24 * 3600
    }
    data = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    signature = hmac.new(AUTH_SECRET.encode(), data.encode(), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(signature).decode()
    return f"{data}.{sig_b64}"

def verify_user_token(token: str) -> Optional[dict]:
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        data, sig_b64 = parts[0], parts[1]
        expected_sig = hmac.new(AUTH_SECRET.encode(), data.encode(), hashlib.sha256).digest()
        expected_sig_b64 = base64.urlsafe_b64encode(expected_sig).decode()
        if not hmac.compare_digest(sig_b64, expected_sig_b64):
            return None
        payload = json.loads(base64.urlsafe_b64decode(data.encode()).decode())
        if "exp" in payload and payload["exp"] < time.time():
            return None
        return payload
    except Exception:
        return None

async def get_current_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header"
        )
    token = authorization.split(" ")[1]
    payload = verify_user_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token"
        )
    
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token contains no user ID"
        )
    
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID format"
        )
    
    stmt = select(User).where(User.id == user_uuid)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found in database"
        )
    return user

async def get_current_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user
