import asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.db.models import Credential
from app.redis_client import redis_client
from app.providers.byo_upstream import BYOUpstreamProvider
from app.providers.antigravity import AntigravityProvider
from app.core.constants import get_credential_tokens_key, get_credential_concurrency_key

async def periodic_quota_resets():
    while True:
        try:
            async with AsyncSessionLocal() as db:
                now = datetime.now(timezone.utc)
                stmt = select(Credential).where(
                    ((Credential.reset_at <= now) & (Credential.type != "antigravity")) |
                    (Credential.status == "cooldown")
                )
                result = await db.execute(stmt)
                credentials = result.scalars().all()

                for cred in credentials:
                    if cred.status == "cooldown":
                        if cred.reset_at and now < cred.reset_at:
                            continue
                    
                    if cred.type == "antigravity":
                        cred.status = "active"
                        cred.reset_at = None
                    else:
                        cred.quota_used_tokens = 0
                        cred.status = "active"
                        
                        tokens_key = get_credential_tokens_key(cred.id)
                        concurrency_key = get_credential_concurrency_key(cred.id)
                        await redis_client.set(tokens_key, "0")
                        await redis_client.set(concurrency_key, "0")

                        if cred.quota_window:
                            cred.reset_at = now + timedelta(seconds=cred.quota_window)
                        else:
                            cred.reset_at = None

                await db.commit()
        except Exception:
            pass
        await asyncio.sleep(10)

async def check_credential_health(cred: Credential) -> bool:
    try:
        if cred.type == "antigravity":
            provider = AntigravityProvider(cred)
            res = await provider.fetch_quota()
            if res.get("status") in ("active", "exhausted"):
                return True
            return False
        else:
            provider = BYOUpstreamProvider(cred)
            model = cred.models[0] if cred.models else "gpt-3.5-turbo"
            await provider.chat_completion(
                model=model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1
            )
            return True
    except Exception:
        return False

async def periodic_health_checks():
    while True:
        try:
            async with AsyncSessionLocal() as db:
                stmt = select(Credential)
                result = await db.execute(stmt)
                creds_data = [
                    {
                        "id": cred.id,
                        "type": cred.type,
                        "name": cred.name,
                        "provider": cred.provider,
                        "encrypted_secret": cred.encrypted_secret,
                        "base_url": cred.base_url,
                        "models": cred.models,
                    }
                    for cred in result.scalars().all()
                ]

            for cred_data in creds_data:
                temp_cred = Credential(
                    id=cred_data["id"],
                    type=cred_data["type"],
                    name=cred_data["name"],
                    provider=cred_data["provider"],
                    encrypted_secret=cred_data["encrypted_secret"],
                    base_url=cred_data["base_url"],
                    models=cred_data["models"]
                )
                is_healthy = await check_credential_health(temp_cred)
                now = datetime.now(timezone.utc)
                
                async with AsyncSessionLocal() as db:
                    stmt = select(Credential).where(Credential.id == temp_cred.id)
                    res = await db.execute(stmt)
                    db_cred = res.scalar_one_or_none()
                    if db_cred:
                        if is_healthy:
                            if temp_cred.type == "antigravity":
                                # Antigravity status is managed by fetch_quota, don't overwrite
                                pass
                            else:
                                # Only reset to active from degraded or expired cooldown
                                # Never overwrite 'exhausted' — that requires quota reset
                                if db_cred.status == "degraded":
                                    db_cred.status = "active"
                                elif db_cred.status == "cooldown" and db_cred.reset_at and now >= db_cred.reset_at:
                                    db_cred.status = "active"
                        else:
                            if temp_cred.type != "antigravity":
                                db_cred.status = "degraded"
                        db_cred.last_check_at = now
                        await db.commit()
        except Exception:
            pass
        await asyncio.sleep(60)

async def periodic_token_refreshes():
    while True:
        try:
            async with AsyncSessionLocal() as db:
                stmt = select(Credential).where(Credential.type == "antigravity")
                result = await db.execute(stmt)
                creds_data = [
                    {
                        "id": cred.id,
                        "type": cred.type,
                        "name": cred.name,
                        "provider": cred.provider,
                        "encrypted_secret": cred.encrypted_secret,
                    }
                    for cred in result.scalars().all()
                ]

            for cred_data in creds_data:
                temp_cred = Credential(
                    id=cred_data["id"],
                    type=cred_data["type"],
                    name=cred_data["name"],
                    provider=cred_data["provider"],
                    encrypted_secret=cred_data["encrypted_secret"]
                )
                provider = AntigravityProvider(temp_cred)
                try:
                    await provider.get_access_token()
                except Exception:
                    async with AsyncSessionLocal() as db:
                        stmt = select(Credential).where(Credential.id == temp_cred.id)
                        res = await db.execute(stmt)
                        db_cred = res.scalar_one_or_none()
                        if db_cred:
                            db_cred.status = "cooldown"
                            db_cred.reset_at = datetime.now(timezone.utc) + timedelta(minutes=5)
                            await db.commit()
        except Exception:
            pass
        await asyncio.sleep(600)

async def start_worker():
    await asyncio.gather(
        periodic_quota_resets(),
        periodic_health_checks(),
        periodic_token_refreshes()
    )
