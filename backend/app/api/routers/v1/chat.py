import time
import hashlib
from typing import Optional, Any
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db.models import VirtualKey, Credential
from app.crypto.cipher import decrypt_secret
from app.security.egress import is_safe_url, scan_for_leak
from app.routing.selector import CredentialSelector
from app.providers.byo_upstream import BYOUpstreamProvider
from app.providers.antigravity import AntigravityProvider
from app.services import usage_service
from app.redis_client import redis_client
from app.core.constants import get_vkey_tokens_key

router = APIRouter()

def get_provider(cred: Any) -> Any:
    if cred.type == "antigravity":
        return AntigravityProvider(cred)
    return BYOUpstreamProvider(cred)

async def verify_key(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
) -> VirtualKey:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header"
        )
    
    token = authorization.split(" ")[1]
    hashed = hashlib.sha256(token.encode()).hexdigest()
    
    stmt = select(VirtualKey).where(
        VirtualKey.hashed_key == hashed,
        VirtualKey.status == "active"
    )
    result = await db.execute(stmt)
    vkey = result.scalar_one_or_none()
    
    if not vkey:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API key"
        )
        
    return vkey

@router.post("/chat/completions")
async def chat_completions(
    payload: dict,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
    vkey: VirtualKey = Depends(verify_key)
):
    model_name = payload.get("model")
    if not model_name:
        raise HTTPException(status_code=400, detail="Missing model parameter")
        
    await usage_service.check_key_limits(vkey, model_name)
    
    token = authorization.split(" ")[1]
    exclude_ids = []
    estimated_tokens = 1000
    
    messages = payload.get("messages", [])
    stream = payload.get("stream", False)
    
    start_time = time.time()
    last_exception = None
    
    while True:
        cred, matched_model = await CredentialSelector.select_and_book(
            db, model_name, user_id=vkey.user_id, estimated_tokens=estimated_tokens, exclude_ids=exclude_ids
        )
        if not cred:
            if last_exception:
                if hasattr(last_exception, "status_code"):
                    raise last_exception
                raise HTTPException(status_code=500, detail=str(last_exception))
            raise HTTPException(status_code=503, detail="No eligible credentials available")
            
        if cred.base_url:
            if not await is_safe_url(cred.base_url):
                await CredentialSelector.release(str(cred.id), 0, db)
                exclude_ids.append(str(cred.id))
                continue
                
        if scan_for_leak({}, str(messages), [token]):
            await CredentialSelector.release(str(cred.id), 0, db)
            raise HTTPException(status_code=400, detail="Potential secret leak detected in request")
            
        await db.commit()
        is_upstream_error = False
        try:
            raw_secret = decrypt_secret(cred.encrypted_secret)
            provider = get_provider(cred)
            extra_kwargs = {k: v for k, v in payload.items() if k not in ["model", "messages", "stream"]}
            if stream:
                is_upstream_error = True
                response = await provider.chat_completion(
                    model=matched_model,
                    messages=messages,
                    stream=True,
                    **extra_kwargs
                )
                try:
                    first_chunk = await response.__anext__()
                except Exception as stream_err:
                    raise stream_err
                is_upstream_error = False
                
                simple_vkey = type("SimpleVKey", (), {"id": vkey.id})()
                simple_cred = type("SimpleCred", (), {"id": cred.id})()
                return StreamingResponse(
                    usage_service.stream_response_generator(
                        simple_cred, first_chunk, response, raw_secret, simple_vkey, matched_model, None, start_time
                    ),
                    media_type="text/event-stream"
                )
            else:
                is_upstream_error = True
                response = await provider.chat_completion(
                    model=matched_model,
                    messages=messages,
                    **extra_kwargs
                )
                is_upstream_error = False
                
                response_str = str(response)
                if scan_for_leak({}, response_str, [raw_secret]):
                    raise Exception("Potential secret leak detected in response")
                    
                usage = getattr(response, "usage", None)
                tokens_used = usage.total_tokens if usage else 0
                latency_ms = int((time.time() - start_time) * 1000)
                
                await CredentialSelector.release(str(cred.id), tokens_used, db)
                
                if vkey.id and tokens_used > 0:
                    vkey_token_key = get_vkey_tokens_key(vkey.id)
                    await redis_client.incrby(vkey_token_key, tokens_used)
                    
                await usage_service.log_usage_event(db, vkey.id, cred.id, matched_model, usage, latency_ms, "success")
                return response
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            
            if not is_upstream_error:
                from app.db.session import AsyncSessionLocal
                try:
                    async with AsyncSessionLocal() as local_db:
                        await CredentialSelector.release(str(cred.id), 0, local_db)
                except Exception:
                    pass
                raise HTTPException(status_code=500, detail=str(e))
                
            await CredentialSelector.release(str(cred.id), 0, db)
            latency_ms = int((time.time() - start_time) * 1000)
            await usage_service.log_usage_event(db, vkey.id, cred.id, matched_model, None, latency_ms, "failure")
            
            last_exception = e
            
            err_str = str(e).lower()
            is_rate_limit = False
            is_quota = False
            
            if hasattr(e, "status_code") and e.status_code == 429:
                is_rate_limit = True
            elif "429" in err_str or "rate limit" in err_str or "too many requests" in err_str or "per minute" in err_str:
                is_rate_limit = True
            elif "quota" in err_str or "billing" in err_str or "exhausted" in err_str:
                if "billing" in err_str or "per day" in err_str or "daily" in err_str or "per-day" in err_str:
                    is_quota = True
                else:
                    is_rate_limit = True
                
            stmt = select(Credential).where(Credential.id == cred.id)
            result = await db.execute(stmt)
            db_cred = result.scalar_one_or_none()
            if db_cred:
                if is_rate_limit:
                    db_cred.status = "cooldown"
                    db_cred.reset_at = datetime.now(timezone.utc) + timedelta(minutes=1)
                elif is_quota:
                    db_cred.status = "exhausted"
                else:
                    db_cred.status = "degraded"
                await db.commit()
                
            exclude_ids.append(str(cred.id))
            continue

@router.post("/embeddings")
async def embeddings(
    payload: dict,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
    vkey: VirtualKey = Depends(verify_key)
):
    model_name = payload.get("model")
    if not model_name:
        raise HTTPException(status_code=400, detail="Missing model parameter")
        
    await usage_service.check_key_limits(vkey, model_name)
    
    token = authorization.split(" ")[1]
    exclude_ids = []
    estimated_tokens = 100
    
    input_data = payload.get("input", "")
    start_time = time.time()
    last_exception = None
    
    while True:
        cred, matched_model = await CredentialSelector.select_and_book(
            db, model_name, user_id=vkey.user_id, estimated_tokens=estimated_tokens, exclude_ids=exclude_ids
        )
        if not cred:
            if last_exception:
                if hasattr(last_exception, "status_code"):
                    raise last_exception
                raise HTTPException(status_code=500, detail=str(last_exception))
            raise HTTPException(status_code=503, detail="No eligible credentials available")
            
        if cred.base_url:
            if not await is_safe_url(cred.base_url):
                await CredentialSelector.release(str(cred.id), 0, db)
                exclude_ids.append(str(cred.id))
                continue
                
        if scan_for_leak({}, str(input_data), [token]):
            await CredentialSelector.release(str(cred.id), 0, db)
            raise HTTPException(status_code=400, detail="Potential secret leak detected in request")
            
        await db.commit()
        is_upstream_error = False
        try:
            raw_secret = decrypt_secret(cred.encrypted_secret)
            provider = get_provider(cred)
            is_upstream_error = True
            response = await provider.embedding(
                model=matched_model,
                input_data=input_data
            )
            is_upstream_error = False
            
            response_str = str(response)
            if scan_for_leak({}, response_str, [raw_secret]):
                raise Exception("Potential secret leak detected in response")
                
            usage = getattr(response, "usage", None)
            tokens_used = usage.total_tokens if usage else 0
            latency_ms = int((time.time() - start_time) * 1000)
            
            await CredentialSelector.release(str(cred.id), tokens_used, db)
            
            if vkey.id and tokens_used > 0:
                vkey_token_key = get_vkey_tokens_key(vkey.id)
                await redis_client.incrby(vkey_token_key, tokens_used)
                
            await usage_service.log_usage_event(db, vkey.id, cred.id, matched_model, usage, latency_ms, "success")
            return response
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            
            if not is_upstream_error:
                from app.db.session import AsyncSessionLocal
                try:
                    async with AsyncSessionLocal() as local_db:
                        await CredentialSelector.release(str(cred.id), 0, local_db)
                except Exception:
                    pass
                raise HTTPException(status_code=500, detail=str(e))
                
            await CredentialSelector.release(str(cred.id), 0, db)
            latency_ms = int((time.time() - start_time) * 1000)
            await usage_service.log_usage_event(db, vkey.id, cred.id, matched_model, None, latency_ms, "failure")
            
            last_exception = e
            
            err_str = str(e).lower()
            is_rate_limit = False
            is_quota = False
            
            if hasattr(e, "status_code") and e.status_code == 429:
                is_rate_limit = True
            elif "429" in err_str or "rate limit" in err_str or "too many requests" in err_str or "per minute" in err_str:
                is_rate_limit = True
            elif "quota" in err_str or "billing" in err_str or "exhausted" in err_str:
                if "billing" in err_str or "per day" in err_str or "daily" in err_str or "per-day" in err_str:
                    is_quota = True
                else:
                    is_rate_limit = True
                
            stmt = select(Credential).where(Credential.id == cred.id)
            result = await db.execute(stmt)
            db_cred = result.scalar_one_or_none()
            if db_cred:
                if is_rate_limit:
                    db_cred.status = "cooldown"
                    db_cred.reset_at = datetime.now(timezone.utc) + timedelta(minutes=1)
                elif is_quota:
                    db_cred.status = "exhausted"
                else:
                    db_cred.status = "degraded"
                await db.commit()
                
            exclude_ids.append(str(cred.id))
            continue


@router.get("/models")
async def list_models(
    db: AsyncSession = Depends(get_db),
    vkey: VirtualKey = Depends(verify_key)
):
    stmt = select(Credential).where(Credential.status == "active")
    result = await db.execute(stmt)
    creds = result.scalars().all()
    model_names = set()
    for c in creds:
        if c.models:
            for m in c.models:
                model_names.add(m)
    created_time = int(time.time())
    data = [
        {
            "id": name,
            "object": "model",
            "created": created_time,
            "owned_by": "levitate"
        }
        for name in sorted(model_names)
    ]
    return {"object": "list", "data": data}
