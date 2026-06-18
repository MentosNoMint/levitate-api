import uuid
import random
from datetime import datetime, timezone, timedelta
from typing import Dict, Any
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.db.models import VirtualKey, UsageEvent, AuditLog, Credential

async def get_stats(db: AsyncSession, user_id: uuid.UUID) -> Dict[str, Any]:
    vkeys_stmt = select(VirtualKey.id).where(VirtualKey.user_id == user_id)
    vkeys_res = await db.execute(vkeys_stmt)
    user_vkey_ids = vkeys_res.scalars().all()

    if not user_vkey_ids:
        return {
          "total_requests": 0,
          "success_rate": 100.0,
          "token_consumption": {"prompt": 0, "completion": 0, "total": 0},
          "token_usage_history": []
        }

    total_requests_stmt = select(func.count(UsageEvent.id)).where(UsageEvent.virtual_key_id.in_(user_vkey_ids))
    res_total = await db.execute(total_requests_stmt)
    total_requests = res_total.scalar() or 0

    success_stmt = select(func.count(UsageEvent.id)).where(UsageEvent.virtual_key_id.in_(user_vkey_ids), UsageEvent.status == "success")
    res_success = await db.execute(success_stmt)
    success_count = res_success.scalar() or 0

    prompt_tokens_stmt = select(func.sum(UsageEvent.prompt_tokens)).where(UsageEvent.virtual_key_id.in_(user_vkey_ids))
    res_prompt = await db.execute(prompt_tokens_stmt)
    prompt_tokens = res_prompt.scalar() or 0

    completion_tokens_stmt = select(func.sum(UsageEvent.completion_tokens)).where(UsageEvent.virtual_key_id.in_(user_vkey_ids))
    res_completion = await db.execute(completion_tokens_stmt)
    completion_tokens = res_completion.scalar() or 0

    success_rate = (success_count / total_requests) if total_requests > 0 else 1.0

    since = datetime.now(timezone.utc) - timedelta(hours=24)
    history_stmt = select(
        UsageEvent.created_at,
        UsageEvent.prompt_tokens,
        UsageEvent.completion_tokens
    ).where(
        UsageEvent.virtual_key_id.in_(user_vkey_ids),
        UsageEvent.created_at >= since
    )
    res_history = await db.execute(history_stmt)
    events = res_history.all()

    now = datetime.now(timezone.utc)
    start_hour = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=23)
    buckets = []
    for i in range(24):
        bucket_time = start_hour + timedelta(hours=i)
        buckets.append({
            "timestamp": bucket_time.strftime("%H:00"),
            "value": 0
        })

    for event_created_at, prompt, completion in events:
        if event_created_at.tzinfo is None:
            event_created_at = event_created_at.replace(tzinfo=timezone.utc)
        if event_created_at >= start_hour:
            idx = int((event_created_at - start_hour).total_seconds() // 3600)
            if 0 <= idx < 24:
                buckets[idx]["value"] += (prompt + completion)

    token_usage_history = [{"timestamp": b["timestamp"], "value": b["value"]} for b in buckets]

    return {
      "total_requests": total_requests,
      "success_rate": round(success_rate * 100, 2),
      "token_consumption": {
        "prompt": prompt_tokens,
        "completion": completion_tokens,
        "total": prompt_tokens + completion_tokens
      },
      "token_usage_history": token_usage_history
    }

async def get_logs(db: AsyncSession, user_id: uuid.UUID) -> Dict[str, Any]:
    vkeys_stmt = select(VirtualKey.id).where(VirtualKey.user_id == user_id)
    vkeys_res = await db.execute(vkeys_stmt)
    user_vkey_ids = vkeys_res.scalars().all()

    if not user_vkey_ids:
        return {"usage_events": [], "audit_logs": []}

    usage_stmt = select(UsageEvent).where(UsageEvent.virtual_key_id.in_(user_vkey_ids)).order_by(UsageEvent.created_at.desc()).limit(100)
    audit_stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(100)
    
    usage_res = await db.execute(usage_stmt)
    audit_res = await db.execute(audit_stmt)
    
    usage_events = usage_res.scalars().all()
    audit_logs = audit_res.scalars().all()
    
    return {
        "usage_events": [{
            "id": str(u.id),
            "virtual_key_id": str(u.virtual_key_id) if u.virtual_key_id else None,
            "credential_id": str(u.credential_id) if u.credential_id else None,
            "model": u.model,
            "prompt_tokens": u.prompt_tokens,
            "completion_tokens": u.completion_tokens,
            "est_cost": u.est_cost,
            "latency_ms": u.latency_ms,
            "status": u.status,
            "created_at": u.created_at.isoformat() if u.created_at else None
        } for u in usage_events],
        "audit_logs": [{
            "id": str(a.id),
            "event_type": a.event_type,
            "metadata": a.payload_metadata,
            "created_at": a.created_at.isoformat() if a.created_at else None
        } for a in audit_logs]
    }

async def clear_logs(db: AsyncSession, user_id: uuid.UUID) -> Dict[str, Any]:
    vkeys_stmt = select(VirtualKey.id).where(VirtualKey.user_id == user_id)
    vkeys_res = await db.execute(vkeys_stmt)
    user_vkey_ids = vkeys_res.scalars().all()

    if user_vkey_ids:
        await db.execute(delete(UsageEvent).where(UsageEvent.virtual_key_id.in_(user_vkey_ids)))
        await db.execute(delete(AuditLog))
        await db.commit()
    return {"status": "cleared"}

async def simulate_log(db: AsyncSession, user_id: uuid.UUID) -> Dict[str, Any]:
    vkeys_stmt = select(VirtualKey).where(VirtualKey.user_id == user_id)
    vkeys_res = await db.execute(vkeys_stmt)
    vkey = vkeys_res.scalars().first()

    if not vkey:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must have at least one virtual key to run simulations."
        )

    cred_stmt = select(Credential).where(Credential.status == "active")
    cred_res = await db.execute(cred_stmt)
    cred = cred_res.scalars().first()

    prompt = random.randint(100, 2000)
    completion = random.randint(50, 1000)
    cost = (prompt + completion) * 0.000015
    
    event = UsageEvent(
        virtual_key_id=vkey.id,
        credential_id=cred.id if cred else None,
        model="gpt-4o" if (cred and "openai" in cred.provider.lower()) else "claude-3-5-sonnet",
        prompt_tokens=prompt,
        completion_tokens=completion,
        est_cost=cost,
        latency_ms=random.randint(100, 800),
        status="success" if random.random() > 0.1 else "error",
        created_at=datetime.now(timezone.utc)
    )
    db.add(event)
    
    audit = AuditLog(
        event_type="simulation",
        payload_metadata={"model": event.model, "cost": cost}
    )
    db.add(audit)
    
    await db.commit()
    return {"status": "success"}
