import time
import hashlib
from typing import Optional, Any
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db.models import VirtualKey, Credential
from app.crypto.cipher import decrypt_secret
from app.security.egress import is_safe_url, scan_for_leak, scan_for_regex_leaks
from app.routing.selector import CredentialSelector
from app.providers.byo_upstream import BYOUpstreamProvider
from app.providers.antigravity import AntigravityProvider
from app.services import usage_service
from app.redis_client import redis_client
from app.core.constants import get_vkey_tokens_key
from app.core.error_classifier import classify_upstream_error

router = APIRouter()

async def _mark_antigravity_group_exhausted(db_cred: Credential, model_name: str) -> None:
    """Mark a specific quota group as exhausted without killing the whole credential."""
    from app.core.constants import get_model_quota_group
    group = get_model_quota_group(model_name)
    group_key = f"_group:{group}"

    quotas = dict(db_cred.model_quotas or {})
    quotas[group_key] = 0.0
    db_cred.model_quotas = quotas

    # Determine global status from group fractions
    gemini_frac = quotas.get("_group:gemini")
    others_frac = quotas.get("_group:others")

    if gemini_frac is not None and others_frac is not None:
        if gemini_frac <= 0.0 and others_frac <= 0.0:
            db_cred.status = "exhausted"
        else:
            db_cred.status = "active"
    else:
        db_cred.status = "active"

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
    
    MAX_RETRIES = 10
    attempt = 0
    while attempt < MAX_RETRIES:
        attempt += 1
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
                
        if cred.type != "antigravity":
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
                simple_cred = type("SimpleCred", (), {"id": cred.id, "type": cred.type})()
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
                
                if cred.type != "antigravity":
                    response_str = str(response)
                    if scan_for_leak({}, response_str, [raw_secret]) or scan_for_regex_leaks(response_str):
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
            
            is_rate_limit, is_quota = classify_upstream_error(e)
                
            stmt = select(Credential).where(Credential.id == cred.id)
            result = await db.execute(stmt)
            db_cred = result.scalar_one_or_none()
            if db_cred:
                if is_rate_limit:
                    db_cred.status = "cooldown"
                    db_cred.reset_at = datetime.now(timezone.utc) + timedelta(minutes=1)
                elif is_quota:
                    if db_cred.type == "antigravity":
                        await _mark_antigravity_group_exhausted(db_cred, matched_model)
                    else:
                        db_cred.status = "exhausted"
                else:
                    db_cred.status = "degraded"
                await db.commit()
                
            exclude_ids.append(str(cred.id))
            continue
            
    if last_exception:
        if hasattr(last_exception, "status_code"):
            raise last_exception
        raise HTTPException(status_code=502, detail=f"All credentials failed after {MAX_RETRIES} attempts: {str(last_exception)}")
    raise HTTPException(status_code=503, detail="No eligible credentials available")

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
    
    MAX_RETRIES = 10
    attempt = 0
    while attempt < MAX_RETRIES:
        attempt += 1
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
            
            is_rate_limit, is_quota = classify_upstream_error(e)
                
            stmt = select(Credential).where(Credential.id == cred.id)
            result = await db.execute(stmt)
            db_cred = result.scalar_one_or_none()
            if db_cred:
                if is_rate_limit:
                    db_cred.status = "cooldown"
                    db_cred.reset_at = datetime.now(timezone.utc) + timedelta(minutes=1)
                elif is_quota:
                    if db_cred.type == "antigravity":
                        await _mark_antigravity_group_exhausted(db_cred, matched_model)
                    else:
                        db_cred.status = "exhausted"
                else:
                    db_cred.status = "degraded"
                await db.commit()
                
            exclude_ids.append(str(cred.id))
            continue
            
    if last_exception:
        if hasattr(last_exception, "status_code"):
            raise last_exception
        raise HTTPException(status_code=502, detail=f"All credentials failed after {MAX_RETRIES} attempts: {str(last_exception)}")
    raise HTTPException(status_code=503, detail="No eligible credentials available")


@router.get("/models")
async def list_models(
    db: AsyncSession = Depends(get_db),
    vkey: VirtualKey = Depends(verify_key)
):
    stmt = select(Credential).where(Credential.status == "active", Credential.user_id == vkey.user_id)
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


class ImageGenerationRequest(BaseModel):
    prompt: str
    model: Optional[str] = "gemini-3.1-flash-image"
    n: Optional[int] = 1
    size: Optional[str] = "1024x1024"
    response_format: Optional[str] = "url"

@router.post("/images/generations")
async def images_generations(
    payload: ImageGenerationRequest,
    db: AsyncSession = Depends(get_db),
    vkey: VirtualKey = Depends(verify_key)
):
    model_name = payload.model or "gemini-3.1-flash-image"
    await usage_service.check_key_limits(vkey, model_name)
    
    exclude_ids = []
    start_time = time.time()
    last_exception = None
    
    MAX_RETRIES = 10
    attempt = 0
    while attempt < MAX_RETRIES:
        attempt += 1
        cred, matched_model = await CredentialSelector.select_and_book(
            db, model_name, user_id=vkey.user_id, estimated_tokens=1500, exclude_ids=exclude_ids
        )
        if not cred:
            if last_exception:
                if hasattr(last_exception, "status_code"):
                    raise last_exception
                raise HTTPException(status_code=500, detail=str(last_exception))
            raise HTTPException(status_code=503, detail="No eligible credentials available")
            
        try:
            raw_secret = decrypt_secret(cred.encrypted_secret)
            provider = get_provider(cred)
            response = await provider.chat_completion(
                model=matched_model,
                messages=[{"role": "user", "content": payload.prompt}],
                stream=False
            )
            
            msg = getattr(response.choices[0], "message", {})
            raw_images = msg.get("images", []) if isinstance(msg, dict) else getattr(msg, "images", [])
            images = []
            if raw_images:
                for img_item in raw_images:
                    url_obj = img_item.get("image_url", {}) if isinstance(img_item, dict) else getattr(img_item, "image_url", {})
                    url_val = url_obj.get("url", "") if isinstance(url_obj, dict) else getattr(url_obj, "url", "")
                    if "base64," in url_val:
                        images.append(url_val.split("base64,")[1])
                    else:
                        images.append(url_val)
            
            if not images:
                raise Exception("No image was generated by the provider")
                
            await CredentialSelector.release(str(cred.id), 1500, db)
            
            if vkey.id:
                vkey_token_key = get_vkey_tokens_key(vkey.id)
                await redis_client.incrby(vkey_token_key, 1500)
                
            latency_ms = int((time.time() - start_time) * 1000)
            await usage_service.log_usage_event(db, vkey.id, cred.id, matched_model, response.usage, latency_ms, "success")
            
            response_format = payload.response_format or "url"
            data_list = []
            for img in images[:payload.n]:
                if response_format == "b64_json":
                    data_list.append({"b64_json": img})
                else:
                    data_list.append({"url": f"data:image/jpeg;base64,{img}"})
                    
            return {
                "created": int(time.time()),
                "data": data_list
            }
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            
            from app.db.session import AsyncSessionLocal
            try:
                async with AsyncSessionLocal() as local_db:
                    await CredentialSelector.release(str(cred.id), 0, local_db)
            except Exception:
                pass
                
            latency_ms = int((time.time() - start_time) * 1000)
            await usage_service.log_usage_event(db, vkey.id, cred.id, matched_model, None, latency_ms, "failure")
            
            last_exception = e
            exclude_ids.append(str(cred.id))
            
            is_rate_limit, is_quota = classify_upstream_error(e)
                
            stmt = select(Credential).where(Credential.id == cred.id)
            result = await db.execute(stmt)
            db_cred = result.scalar_one_or_none()
            if db_cred:
                if is_rate_limit:
                    db_cred.status = "cooldown"
                    db_cred.reset_at = datetime.now(timezone.utc) + timedelta(minutes=1)
                elif is_quota:
                    if db_cred.type == "antigravity":
                        await _mark_antigravity_group_exhausted(db_cred, matched_model)
                    else:
                        db_cred.status = "exhausted"
                else:
                    db_cred.status = "degraded"
                await db.commit()
            
            continue
            
    if last_exception:
        if hasattr(last_exception, "status_code"):
            raise last_exception
        raise HTTPException(status_code=502, detail=f"All credentials failed after {MAX_RETRIES} attempts: {str(last_exception)}")
    raise HTTPException(status_code=503, detail="No eligible credentials available")
