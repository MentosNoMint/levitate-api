import uuid
import hashlib
from typing import List, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.db.models import VirtualKey
from app.api.schemas.virtual_key import VirtualKeyCreate, VirtualKeyUpdate
from app.redis_client import redis_client
from app.core.constants import get_vkey_tokens_key


async def list_virtual_keys(db: AsyncSession, user_id: uuid.UUID) -> List[Dict[str, Any]]:
    stmt = select(VirtualKey).where(VirtualKey.user_id == user_id).order_by(VirtualKey.name)
    result = await db.execute(stmt)
    keys = result.scalars().all()
    
    res = []
    for k in keys:
        token_key = get_vkey_tokens_key(k.id)
        used = await redis_client.get(token_key)
        used_tokens = int(used) if used else 0
        
        res.append({
            "id": k.id,
            "user_id": k.user_id,
            "name": k.name,
            "monthly_token_limit": k.monthly_token_limit,
            "rpm_limit": k.rpm_limit,
            "allowed_model_groups": k.allowed_model_groups,
            "status": k.status,
            "monthly_usage": used_tokens
        })
    return res


async def create_virtual_key(db: AsyncSession, payload: VirtualKeyCreate, current_user_id: uuid.UUID) -> Dict[str, Any]:
    raw_token = f"sk-gateway-{uuid.uuid4().hex}"
    hashed = hashlib.sha256(raw_token.encode()).hexdigest()
    
    uid = uuid.UUID(payload.user_id) if payload.user_id else current_user_id
    
    vkey = VirtualKey(
        user_id=uid,
        name=payload.name,
        hashed_key=hashed,
        monthly_token_limit=payload.monthly_token_limit,
        rpm_limit=payload.rpm_limit,
        allowed_model_groups=payload.allowed_model_groups
    )
    db.add(vkey)
    await db.commit()
    return {
        "id": vkey.id,
        "key": raw_token,
        "status": "created"
    }


async def update_virtual_key(
    db: AsyncSession,
    vkey_id: uuid.UUID,
    payload: VirtualKeyUpdate,
    current_user_id: uuid.UUID,
    current_user_role: str,
) -> Dict[str, Any]:
    stmt = select(VirtualKey).where(VirtualKey.id == vkey_id)
    result = await db.execute(stmt)
    vkey = result.scalar_one_or_none()
    if not vkey:
        raise HTTPException(status_code=404, detail="Virtual Key not found")

    if vkey.user_id != current_user_id and current_user_role != "admin":
        raise HTTPException(status_code=404, detail="Virtual Key not found")

    for k, v in payload.model_dump(exclude_unset=True).items():
        # These fields may be explicitly cleared with null (#22)
        if k in ["monthly_token_limit", "rpm_limit", "allowed_model_groups"]:
            setattr(vkey, k, v)
        elif v is not None:
            setattr(vkey, k, v)

    await db.commit()
    return {"status": "updated"}


async def delete_virtual_key(
    db: AsyncSession,
    vkey_id: uuid.UUID,
    current_user_id: uuid.UUID,
    current_user_role: str,
) -> Dict[str, Any]:
    stmt = select(VirtualKey).where(VirtualKey.id == vkey_id)
    result = await db.execute(stmt)
    vkey = result.scalar_one_or_none()
    if not vkey:
        raise HTTPException(status_code=404, detail="Virtual Key not found")

    if vkey.user_id != current_user_id and current_user_role != "admin":
        raise HTTPException(status_code=404, detail="Virtual Key not found")

    await db.delete(vkey)
    await db.commit()
    return {"status": "deleted"}
