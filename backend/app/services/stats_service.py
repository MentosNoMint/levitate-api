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

async def simulate_log(db: AsyncSession, user_id: uuid.UUID, model: str = None, prompt: str = None) -> Dict[str, Any]:
    vkeys_stmt = select(VirtualKey).where(VirtualKey.user_id == user_id)
    vkeys_res = await db.execute(vkeys_stmt)
    vkey = vkeys_res.scalars().first()

    if not vkey:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must have at least one virtual key to run simulations."
        )

    # Получаем все активные credentials
    cred_stmt = select(Credential).where(Credential.status == "active")
    cred_res = await db.execute(cred_stmt)
    creds = cred_res.scalars().all()

    if not creds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active AI accounts found to make a real test request. Please activate or add at least one account."
        )

    cred = None
    if model:
        # Пытаемся найти аккаунт, который явно поддерживает выбранную модель
        for c in creds:
            if c.models and model in c.models:
                cred = c
                break

    # Если не нашли по модели, берем первый активный
    if not cred:
        cred = creds[0]

    # Если модель не была передана, берем первую поддерживаемую
    if not model:
        if cred.models and len(cred.models) > 0:
            model = cred.models[0]
        else:
            model = "gemini-3.1-pro-high" if cred.type == "antigravity" else "gpt-3.5-turbo"

    if not prompt:
        prompt = "Hello. Output exactly the word 'OK' and nothing else."

    import time
    start_time = time.time()
    err_msg = None
    status_str = "error"
    prompt_tokens = 0
    completion_tokens = 0
    response_content = ""

    if cred.type == "antigravity":
        from app.providers.antigravity import AntigravityProvider
        provider = AntigravityProvider(cred)
    else:
        from app.providers.byo_upstream import BYOUpstreamProvider
        provider = BYOUpstreamProvider(cred)

    try:
        response = await provider.chat_completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200
        )
        latency_ms = int((time.time() - start_time) * 1000)
        
        usage = getattr(response, "usage", None)
        prompt_tokens = usage.prompt_tokens if usage else 1
        completion_tokens = usage.completion_tokens if usage else 1
        
        if response and hasattr(response, "choices") and response.choices:
            choice = response.choices[0]
            if hasattr(choice, "message") and choice.message:
                response_content = getattr(choice.message, "content", "") or ""
            elif hasattr(choice, "delta") and choice.delta:
                response_content = getattr(choice.delta, "content", "") or ""
                
        status_str = "success"
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        err_msg = str(e)
        status_str = "error"

    cost = (prompt_tokens + completion_tokens) * 0.000015
    
    event = UsageEvent(
        virtual_key_id=vkey.id,
        credential_id=cred.id,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        est_cost=cost,
        latency_ms=latency_ms,
        status=status_str,
        created_at=datetime.now(timezone.utc)
    )
    db.add(event)
    
    audit = AuditLog(
        event_type="simulation",
        payload_metadata={
            "model": event.model,
            "cost": cost,
            "real_request": True,
            "error": err_msg,
            "prompt": prompt,
            "response": response_content[:500] if response_content else None
        }
    )
    db.add(audit)
    
    await db.commit()
    
    if status_str == "error":
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Real test request to {model} failed: {err_msg}. Check your account status."
        )
        
    return {
        "status": "success",
        "model": model,
        "latency": latency_ms,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "response": response_content
    }
