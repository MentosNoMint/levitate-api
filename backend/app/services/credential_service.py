import uuid
import json
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.db.models import Credential
from app.crypto.cipher import encrypt_secret, decrypt_secret
from app.providers.byo_upstream import BYOUpstreamProvider
from app.providers.antigravity import AntigravityProvider
from app.api.schemas.credential import CredentialCreate, CredentialUpdate
from app.core.constants import DEFAULT_ANTIGRAVITY_MODELS, get_credential_access_token_key
from app.redis_client import redis_client
from app.security.egress import is_safe_url


def _derive_display_status(cred: Credential) -> str:
    """Reconcile UI status with group quotas when DB status lags."""
    status = cred.status or "active"
    if status in {"reauth_required", "disabled", "cooldown", "degraded", "error"}:
        return status
    quotas = cred.model_quotas or {}
    if cred.type == "antigravity" and quotas:
        def _frac(key: str):
            try:
                value = quotas.get(key)
                return None if value is None else float(value)
            except (TypeError, ValueError):
                return None
        gemini = _frac("_group:gemini")
        others = _frac("_group:others")
        if gemini is not None and others is not None and gemini <= 0.0 and others <= 0.0:
            return "exhausted"
    return status

async def list_credentials(db: AsyncSession, user_id: uuid.UUID) -> List[Dict[str, Any]]:
    stmt = select(Credential).where(Credential.user_id == user_id).order_by(Credential.name)
    result = await db.execute(stmt)
    creds = result.scalars().all()
    
    res = []
    for c in creds:
        tier = None
        load_error = None
        quota_error = None
        if c.type == "antigravity":
            try:
                secret_data = decrypt_secret(c.encrypted_secret)
                secret_dict = json.loads(secret_data)
                if isinstance(secret_dict, dict):
                    tier = secret_dict.get("tier")
                    load_error = secret_dict.get("load_error")
                    quota_error = secret_dict.get("quota_error")
            except Exception:
                pass
        
        res.append({
            "id": c.id,
            "type": c.type,
            "name": c.name,
            "provider": c.provider,
            "base_url": c.base_url,
            "models": c.models,
            "quota_total_tokens": c.quota_total_tokens,
            "quota_used_tokens": c.quota_used_tokens,
            "quota_window": c.quota_window,
            "reset_at": c.reset_at,
            "rpm_limit": c.rpm_limit,
            "concurrency_limit": c.concurrency_limit,
            "priority": c.priority,
            "weight": c.weight,
            "status": _derive_display_status(c),
            "expires_at": c.expires_at,
            "last_check_at": c.last_check_at,
            "model_quotas": c.model_quotas,
            "tier": tier,
            "load_error": load_error,
            "quota_error": quota_error
        })
    return res

async def create_credential(db: AsyncSession, payload: CredentialCreate, user_id: uuid.UUID) -> Dict[str, Any]:
    encrypted = encrypt_secret(payload.secret)
    reset_val = None
    if payload.quota_window:
        reset_val = datetime.now(timezone.utc) + timedelta(seconds=payload.quota_window)
    
    models_list = DEFAULT_ANTIGRAVITY_MODELS if payload.type == "antigravity" else payload.models
    
    cred = Credential(
        user_id=user_id,
        type=payload.type,
        name=payload.name,
        provider=payload.provider,
        encrypted_secret=encrypted,
        base_url=payload.base_url,
        models=models_list,
        quota_total_tokens=payload.quota_total_tokens,
        quota_window=payload.quota_window,
        reset_at=reset_val,
        rpm_limit=payload.rpm_limit,
        concurrency_limit=payload.concurrency_limit,
        priority=payload.priority,
        weight=payload.weight
    )
    db.add(cred)
    await db.commit()
    return {"id": cred.id, "status": "created"}

async def update_credential(db: AsyncSession, credential_id: uuid.UUID, payload: CredentialUpdate, user_id: uuid.UUID) -> Dict[str, Any]:
    stmt = select(Credential).where(Credential.id == credential_id, Credential.user_id == user_id)
    result = await db.execute(stmt)
    cred = result.scalar_one_or_none()
    if not cred:
        raise HTTPException(status_code=404, detail="Credential not found")

    ALLOWED_UPDATE_FIELDS = {"name", "provider", "base_url", "models", "quota_total_tokens",
                              "quota_window", "rpm_limit", "concurrency_limit", "priority", "weight", "status"}
    # Nullable fields may be explicitly cleared with null (#22)
    NULLABLE_UPDATE_FIELDS = {"base_url", "models", "quota_total_tokens", "quota_window", "rpm_limit", "concurrency_limit"}
    secret_changed = False
    reactivated = False

    for k, v in payload.dict(exclude_unset=True).items():
        if k == "secret" and v is not None:
            cred.encrypted_secret = encrypt_secret(v)
            secret_changed = True
        elif k == "models" and cred.type == "antigravity":
            continue
        elif k not in ALLOWED_UPDATE_FIELDS:
            continue
        elif v is None and k not in NULLABLE_UPDATE_FIELDS:
            continue
        else:
            if k == "status" and v == "active" and cred.status != "active":
                reactivated = True
            setattr(cred, k, v)
            if k == "quota_window":
                if v:
                    cred.reset_at = datetime.now(timezone.utc) + timedelta(seconds=v)
                else:
                    cred.reset_at = None

    if reactivated:
        cred.reset_at = None

    # Antigravity models are owned by fetchAvailableModels sync.
    # Only seed the bootstrap catalog when the list is empty.
    if cred.type == "antigravity" and not cred.models:
        cred.models = DEFAULT_ANTIGRAVITY_MODELS

    if cred.type == "antigravity" and (secret_changed or reactivated):
        cred.model_quotas = {}
        cred.reset_at = None
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(cred, "model_quotas")

    await db.commit()
    if secret_changed or reactivated:
        await redis_client.delete(get_credential_access_token_key(cred.id))
    return {"status": "updated"}

async def delete_credential(db: AsyncSession, credential_id: uuid.UUID, user_id: uuid.UUID) -> Dict[str, Any]:
    stmt = select(Credential).where(Credential.id == credential_id, Credential.user_id == user_id)
    result = await db.execute(stmt)
    cred = result.scalar_one_or_none()
    if not cred:
        raise HTTPException(status_code=404, detail="Credential not found")
    await db.delete(cred)
    await db.commit()
    return {"status": "deleted"}

async def test_credential(db: AsyncSession, credential_id: uuid.UUID, user_id: uuid.UUID) -> Dict[str, Any]:
    stmt = select(Credential).where(Credential.id == credential_id, Credential.user_id == user_id)
    result = await db.execute(stmt)
    cred = result.scalar_one_or_none()
    if not cred:
        raise HTTPException(status_code=404, detail="Credential not found")

    try:
        if cred.type == "antigravity":
            provider = AntigravityProvider(cred)
            refresh_result = await provider.fetch_quota(force=True)
            if "error" in refresh_result or refresh_result.get("status") == "error":
                err_msg = refresh_result.get("error") or refresh_result.get("load_error") or refresh_result.get("quota_error") or "Failed to connect to Google API"
                return {"status": "failed", "error": err_msg}
            return {"status": "success", "message": "Credential connects successfully"}
        else:
            # The test request hits cred.base_url directly — apply the same
            # egress safety check as the request path (SSRF vector) (#12)
            if cred.base_url and not await is_safe_url(cred.base_url):
                return {"status": "failed", "error": "base_url rejected by the egress safety check"}
            provider = BYOUpstreamProvider(cred)
            model = cred.models[0] if cred.models else "gpt-3.5-turbo"
            await provider.chat_completion(
                model=model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1
            )
            return {"status": "success", "message": "Credential connects successfully"}
    except Exception as e:
        return {"status": "failed", "error": str(e)}

async def refresh_credential_quota(db: AsyncSession, credential_id: uuid.UUID, user_id: uuid.UUID) -> Dict[str, Any]:
    stmt = select(Credential).where(Credential.id == credential_id, Credential.user_id == user_id)
    result = await db.execute(stmt)
    cred = result.scalar_one_or_none()
    if not cred:
        raise HTTPException(status_code=404, detail="Credential not found")
        
    if cred.type != "antigravity":
        raise HTTPException(
            status_code=400,
            detail="Quota refresh is only supported for Antigravity credentials."
        )

    provider = AntigravityProvider(cred)
    refresh_result = await provider.fetch_quota(force=True)
    return refresh_result

async def refresh_all_quotas(db: AsyncSession, user_id: uuid.UUID) -> Dict[str, Any]:
    stmt = select(Credential).where(Credential.type == "antigravity", Credential.user_id == user_id)
    result = await db.execute(stmt)
    creds = result.scalars().all()
    
    results = {}
    for cred in creds:
        provider = AntigravityProvider(cred)
        res = await provider.fetch_quota(force=True)
        results[str(cred.id)] = res
        
    return {"status": "success", "results": results}
