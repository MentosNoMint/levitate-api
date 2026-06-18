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
                    (Credential.reset_at <= now) | (Credential.status == "cooldown")
                )
                result = await db.execute(stmt)
                credentials = result.scalars().all()

                for cred in credentials:
                    if cred.status == "cooldown":
                        if cred.reset_at and now < cred.reset_at:
                            continue
                    
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
                credentials = result.scalars().all()

                for cred in credentials:
                    now = datetime.now(timezone.utc)
                    is_healthy = await check_credential_health(cred)
                    
                    if is_healthy:
                        cred.status = "active"
                    else:
                        cred.status = "degraded"
                    cred.last_check_at = now
                    
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
                credentials = result.scalars().all()

                for cred in credentials:
                    provider = AntigravityProvider(cred)
                    try:
                        await provider.get_access_token()
                    except Exception:
                        cred.status = "cooldown"
                        cred.reset_at = datetime.now(timezone.utc) + timedelta(minutes=5)
                        
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
