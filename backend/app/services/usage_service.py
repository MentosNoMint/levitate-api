import time
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.db.models import VirtualKey, UsageEvent, Credential
from app.redis_client import redis_client
from app.routing.selector import CredentialSelector
from app.security.egress import scan_for_leak, scan_for_regex_leaks
from app.core.constants import get_vkey_rpm_key, get_vkey_tokens_key

async def check_key_limits(vkey: VirtualKey, model_name: str) -> None:
    if vkey.allowed_model_groups:
        allowed = False
        for group in vkey.allowed_model_groups:
            if group.lower() in model_name.lower():
                allowed = True
                break
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Model {model_name} is not allowed for this key"
            )
            
    if vkey.rpm_limit is not None:
        rpm_key = get_vkey_rpm_key(vkey.id)
        current_rpm = await redis_client.incrby(rpm_key, 1)
        if current_rpm == 1:
            await redis_client.expire(rpm_key, 60)
        if current_rpm > vkey.rpm_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded for this key"
            )
            
    if vkey.monthly_token_limit is not None:
        token_key = get_vkey_tokens_key(vkey.id)
        used = await redis_client.get(token_key)
        used_val = int(used) if used else 0
        if used_val >= vkey.monthly_token_limit:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Monthly token limit exceeded for this key"
            )

async def log_usage_event(
    db: AsyncSession,
    vkey_id: Optional[uuid.UUID],
    cred_id: Optional[uuid.UUID],
    model_name: str,
    usage: Optional[Any],
    latency_ms: int,
    status_str: str
) -> None:
    prompt_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
    completion_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
    
    event = UsageEvent(
        virtual_key_id=vkey_id,
        credential_id=cred_id,
        model=model_name,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        est_cost=0.0,
        latency_ms=latency_ms,
        status=status_str
    )
    db.add(event)
    await db.commit()

async def stream_response_generator(
    cred: Any, 
    first_chunk: Any, 
    response_gen: Any, 
    secret_to_scan: str, 
    vkey: Any, 
    model_name: str, 
    db: Any,
    start_time: float
):
    total_prompt_tokens = 0
    total_completion_tokens = 0
    stream_error = None
    
    async def iterate_chunks():
        yield first_chunk
        async for chunk in response_gen:
            yield chunk

    try:
        async for chunk in iterate_chunks():
            if hasattr(chunk, "model_dump_json"):
                chunk_data = chunk.model_dump_json()
            else:
                chunk_data = str(chunk)
                
            if getattr(cred, "type", None) != "antigravity":
                if scan_for_leak({}, chunk_data, [secret_to_scan]) or scan_for_regex_leaks(chunk_data):
                    raise Exception("Potential secret leak detected in streaming response")
                
            if hasattr(chunk, "usage") and chunk.usage:
                total_prompt_tokens = chunk.usage.prompt_tokens
                total_completion_tokens = chunk.usage.completion_tokens
                
            yield f"data: {chunk_data}\n\n"
            
        yield "data: [DONE]\n\n"
    except Exception as e:
        stream_error = e
        yield f"data: {{\"error\": \"{str(e)}\"}}\n\n"
    finally:
        total_tokens = total_prompt_tokens + total_completion_tokens
        latency_ms = int((time.time() - start_time) * 1000)
        
        class UsageObj:
            def __init__(self, p, c):
                self.prompt_tokens = p
                self.completion_tokens = c
                
        usage_obj = UsageObj(total_prompt_tokens, total_completion_tokens)
        
        async def cleanup():
            from app.db.session import AsyncSessionLocal
            async with AsyncSessionLocal() as local_db:
                await CredentialSelector.release(str(cred.id), total_tokens, local_db)
                if vkey.id and total_tokens > 0:
                    vkey_token_key = get_vkey_tokens_key(vkey.id)
                    await redis_client.incrby(vkey_token_key, total_tokens)
                
                status_str = "success"
                if stream_error is not None:
                    status_str = "failure"
                    err_str = str(stream_error).lower()
                    is_rate_limit = False
                    is_quota = False
                    
                    if "rate limit" in err_str or "429" in err_str or "too many requests" in err_str or "per minute" in err_str:
                        is_rate_limit = True
                    elif "quota" in err_str or "billing" in err_str or "exhausted" in err_str:
                        if "billing" in err_str or "per day" in err_str or "daily" in err_str or "per-day" in err_str:
                            is_quota = True
                        else:
                            is_rate_limit = True
                        
                    stmt = select(Credential).where(Credential.id == cred.id)
                    result = await local_db.execute(stmt)
                    db_cred = result.scalar_one_or_none()
                    if db_cred:
                        if is_rate_limit:
                            db_cred.status = "cooldown"
                            db_cred.reset_at = datetime.now(timezone.utc) + timedelta(minutes=1)
                        elif is_quota:
                            db_cred.status = "exhausted"
                        else:
                            db_cred.status = "degraded"
                        await local_db.commit()
                        
                await log_usage_event(local_db, vkey.id, cred.id, model_name, usage_obj, latency_ms, status_str)
            
        await asyncio.shield(cleanup())
