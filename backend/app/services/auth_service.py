import os
import json
import httpx
from typing import Optional, Dict, Any
from urllib.parse import quote, parse_qs, unquote
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.db.models import User, Credential
from app.security.auth import sign_user_token, verify_user_token
from app.crypto.cipher import encrypt_secret, decrypt_secret
from app.providers.antigravity import AntigravityProvider
from app.core.constants import DEFAULT_ANTIGRAVITY_MODELS
import logging

logger = logging.getLogger(__name__)

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/admin/auth/callback")

ANTIGRAVITY_OAUTH_CLIENT_ID = os.getenv("ANTIGRAVITY_OAUTH_CLIENT_ID", "")
ANTIGRAVITY_OAUTH_CLIENT_SECRET = os.getenv("ANTIGRAVITY_OAUTH_CLIENT_SECRET", "")

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

ALLOWED_ADMIN_EMAILS = [
    email.strip().lower() 
    for email in os.getenv("ALLOWED_ADMIN_EMAILS", "").split(",") 
    if email.strip()
]

# Environment configuration
app_env = os.getenv("APP_ENV", "").strip().lower()
env_allow_mock = os.getenv("ALLOW_MOCK_AUTH", "true").strip().lower()

AUTH_METHOD = os.getenv("AUTH_METHOD", "both").strip().lower()
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()

if AUTH_METHOD not in ("google", "token", "both"):
    AUTH_METHOD = "both"

if app_env == "production":
    ALLOW_MOCK_AUTH = False
    if AUTH_METHOD in ("token", "both"):
        if not ADMIN_TOKEN or len(ADMIN_TOKEN) < 16:
            raise RuntimeError("ADMIN_TOKEN must be securely configured and at least 16 characters long in production mode!")
else:
    ALLOW_MOCK_AUTH = env_allow_mock not in ("false", "0", "no", "off")

def get_google_oauth_configured() -> bool:
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)

async def get_login_url(action: Optional[str] = None, token: Optional[str] = None) -> str:
    if action == "add_credential" and token:
        client_id = ANTIGRAVITY_OAUTH_CLIENT_ID
        scopes = "https://www.googleapis.com/auth/cloud-platform%20https://www.googleapis.com/auth/userinfo.email%20https://www.googleapis.com/auth/userinfo.profile%20https://www.googleapis.com/auth/cclog%20https://www.googleapis.com/auth/experimentsandconfigs"
        # Keep the admin session token out of the URL: store it server-side
        # behind a short-lived random state id (#11)
        import secrets as _secrets
        from app.redis_client import redis_client
        state_id = _secrets.token_urlsafe(16)
        await redis_client.set(f"gateway:oauth_state:{state_id}", token, ex=600)
        state = quote(f"action=add_credential&sid={state_id}")
        prompt_params = "&access_type=offline&prompt=consent"
    else:
        if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
            if not ALLOW_MOCK_AUTH:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="OAuth credentials are not configured"
                )
            return "/admin/auth/mock"
        client_id = GOOGLE_CLIENT_ID
        scopes = "openid%20email%20profile"
        state = "oauth_state"
        prompt_params = ""

    authorization_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        "response_type=code&"
        f"client_id={client_id}&"
        f"redirect_uri={quote(GOOGLE_REDIRECT_URI)}&"
        f"scope={scopes}&"
        f"state={state}"
        f"{prompt_params}"
    )
    return authorization_url

async def handle_oauth_callback(code: str, state: Optional[str], db: AsyncSession) -> str:
    action = None
    admin_token = None
    if state and "action=add_credential" in state:
        decoded_state = unquote(state)
        parsed_state = parse_qs(decoded_state)
        action = parsed_state.get("action", [None])[0]
        sid = parsed_state.get("sid", [None])[0]
        if sid:
            # One-time server-side lookup — the session token never travels
            # through URLs, browser history or Google (#11)
            from app.redis_client import redis_client
            admin_token = await redis_client.get(f"gateway:oauth_state:{sid}")
            await redis_client.delete(f"gateway:oauth_state:{sid}")

    if action != "add_credential":
        if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google OAuth is not configured"
            )

    client_id = ANTIGRAVITY_OAUTH_CLIENT_ID if action == "add_credential" else GOOGLE_CLIENT_ID
    client_secret = ANTIGRAVITY_OAUTH_CLIENT_SECRET if action == "add_credential" else GOOGLE_CLIENT_SECRET

    async with httpx.AsyncClient() as client:
        token_url = "https://oauth2.googleapis.com/token"
        data = {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code"
        }
        token_resp = await client.post(token_url, data=data)
        if token_resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to retrieve Google token: {token_resp.text}"
            )
        
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        
        userinfo_url = "https://www.googleapis.com/oauth2/v3/userinfo"
        headers = {"Authorization": f"Bearer {access_token}"}
        userinfo_resp = await client.get(userinfo_url, headers=headers)
        if userinfo_resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to retrieve Google userinfo"
            )
        
        user_info = userinfo_resp.json()
        email = user_info.get("email")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google OAuth response did not contain email"
            )

    if action == "add_credential":
        admin_payload = verify_user_token(admin_token or "")
        if not admin_payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired admin session token"
            )
        
        admin_user_id = admin_payload.get("user_id")
        if not admin_user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Admin session token does not contain user ID"
            )
        import uuid
        admin_uuid = uuid.UUID(admin_user_id)
        
        cred_name = f"Antigravity Gemini ({email})"
        stmt = select(Credential).where(Credential.name == cred_name, Credential.user_id == admin_uuid)
        result = await db.execute(stmt)
        existing_cred = result.scalar_one_or_none()

        if not refresh_token and not existing_cred:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google OAuth did not return a refresh token. Please disconnect the app in your Google Account settings and try again."
            )

        secret_dict = {
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret
        }

        if not refresh_token and existing_cred:
            try:
                old_secret = decrypt_secret(existing_cred.encrypted_secret)
                old_secret_dict = json.loads(old_secret)
                secret_dict["refresh_token"] = old_secret_dict.get("refresh_token")
            except Exception:
                pass

        encrypted = encrypt_secret(json.dumps(secret_dict))

        if existing_cred:
            existing_cred.encrypted_secret = encrypted
            existing_cred.status = "active"
            if not existing_cred.models:
                existing_cred.models = DEFAULT_ANTIGRAVITY_MODELS
            await db.commit()
            provider = AntigravityProvider(existing_cred)
            try:
                await provider.fetch_quota()
            except Exception as e:
                logger.exception("Error fetching quota during OAuth callback: %s", e)
        else:
            new_cred = Credential(
                user_id=admin_uuid,
                type="antigravity",
                name=cred_name,
                provider="Gemini",
                encrypted_secret=encrypted,
                concurrency_limit=20,
                priority=1,
                weight=5,
                status="active",
                models=DEFAULT_ANTIGRAVITY_MODELS
            )
            db.add(new_cred)
            await db.commit()
            provider = AntigravityProvider(new_cred)
            try:
                await provider.fetch_quota()
            except Exception as e:
                logger.exception("Error fetching quota during OAuth callback: %s", e)
        
        return f"{FRONTEND_URL}/?google_connect=success"
    else:
        stmt = select(User).where(User.email == email)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            role = "admin" if email.strip().lower() in ALLOWED_ADMIN_EMAILS else "user"
            user = User(email=email, role=role)
            db.add(user)
            await db.commit()
            await db.refresh(user)

        token = sign_user_token(email=user.email, user_id=str(user.id))
        return f"{FRONTEND_URL}/?auth_token={token}"

async def handle_mock_login(db: AsyncSession) -> str:
    mock_email = "dev-user@levitate.ai"
    
    stmt = select(User).where(User.email == mock_email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        user = User(email=mock_email, role="admin")
        db.add(user)
        await db.commit()
        await db.refresh(user)

    token = sign_user_token(email=user.email, user_id=str(user.id))
    return f"{FRONTEND_URL}/?auth_token={token}"

async def handle_token_login(token: str, client_ip: str, db: AsyncSession) -> str:
    from app.redis_client import redis_client
    
    if AUTH_METHOD not in ("token", "both"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token authentication is disabled in this environment."
        )
        
    limit_key = f"rate_limit:login:{client_ip}"
    current_attempts = await redis_client.get(limit_key)
    if current_attempts and int(current_attempts) >= 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later."
        )
        
    if not ADMIN_TOKEN or token != ADMIN_TOKEN:
        # Count only failed attempts — pre-incrementing let anyone lock out a
        # legitimate admin IP by sending 5 bogus requests (#29)
        await redis_client.incrby(limit_key, 1)
        attempts_ttl = await redis_client.ttl(limit_key)
        if attempts_ttl is None or attempts_ttl < 0:
            await redis_client.expire(limit_key, 60)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token."
        )

    await redis_client.delete(limit_key)
    
    admin_email = "dev-user@levitate.ai" if app_env != "production" else (ALLOWED_ADMIN_EMAILS[0] if ALLOWED_ADMIN_EMAILS else "admin@levitate.ai")
    
    stmt = select(User).where(User.email == admin_email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        user = User(email=admin_email, role="admin")
        db.add(user)
        await db.commit()
        await db.refresh(user)
    elif user.role != "admin":
        user.role = "admin"
        await db.commit()
        await db.refresh(user)
        
    session_token = sign_user_token(email=user.email, user_id=str(user.id))
    return session_token

