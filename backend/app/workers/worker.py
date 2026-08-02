import asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.db.models import Credential
from app.redis_client import redis_client
from app.providers.byo_upstream import BYOUpstreamProvider
from app.providers.antigravity import AntigravityProvider
from app.core.constants import get_credential_tokens_key, get_credential_concurrency_key, get_credential_cooldown_key
import logging

logger = logging.getLogger(__name__)

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
                        # Cooldown is tracked by an ephemeral Redis key. Reviving a
                        # cooled-down credential must NEVER touch quota counters or
                        # reset_at — a 429 is not a quota-window expiry (#6, N1).
                        cooldown_key = get_credential_cooldown_key(cred.id)
                        if await redis_client.get(cooldown_key):
                            continue
                        cred.status = "active"
                        # Fall through: if the quota window also expired while the
                        # credential was cooling down, reset counters below.

                    # Quota window expiry only (query already excludes antigravity
                    # from the reset_at branch; antigravity cooldown revival above
                    # must not zero counters — fetch_quota owns that state)
                    if cred.type == "antigravity":
                        continue

                    reset_at = cred.reset_at
                    if reset_at is None:
                        continue
                    if reset_at.tzinfo is None:
                        reset_at = reset_at.replace(tzinfo=timezone.utc)
                    if now < reset_at:
                        continue

                    cred.quota_used_tokens = 0
                    cred.status = "active"

                    tokens_key = get_credential_tokens_key(cred.id)
                    concurrency_key = get_credential_concurrency_key(cred.id)
                    await redis_client.set(tokens_key, "0")
                    await redis_client.set(concurrency_key, "0")

                    if cred.quota_window:
                        # Roll forward from the previous reset_at (not from now)
                        # so the quota window does not drift (#16)
                        new_reset = reset_at + timedelta(seconds=cred.quota_window)
                        while new_reset <= now:
                            new_reset += timedelta(seconds=cred.quota_window)
                        cred.reset_at = new_reset
                    else:
                        cred.reset_at = None

                await db.commit()
        except Exception as e:
            logger.exception("Error in periodic_quota_resets: %s", e)
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
                        "status": cred.status,
                        "last_check_at": cred.last_check_at,
                        "quota_total_tokens": cred.quota_total_tokens,
                        "quota_used_tokens": cred.quota_used_tokens,
                        "reset_at": cred.reset_at,
                        "model_quotas": cred.model_quotas,
                    }
                    for cred in result.scalars().all()
                ]

            for cred_data in creds_data:
                # Include last_check_at/model_quotas/quota fields so
                # fetch_quota's 15-minute cache actually engages (#2)
                temp_cred = Credential(
                    id=cred_data["id"],
                    type=cred_data["type"],
                    name=cred_data["name"],
                    provider=cred_data["provider"],
                    encrypted_secret=cred_data["encrypted_secret"],
                    base_url=cred_data["base_url"],
                    models=cred_data["models"],
                    status=cred_data["status"],
                    last_check_at=cred_data["last_check_at"],
                    quota_total_tokens=cred_data["quota_total_tokens"],
                    quota_used_tokens=cred_data["quota_used_tokens"],
                    reset_at=cred_data["reset_at"],
                    model_quotas=cred_data["model_quotas"]
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
                                # Cooldown revival is periodic_quota_resets' job and
                                # is driven by the Redis cooldown key, not reset_at (N3)
                        else:
                            if temp_cred.type != "antigravity":
                                db_cred.status = "degraded"
                        db_cred.last_check_at = now
                        await db.commit()
        except Exception as e:
            logger.exception("Error in periodic_health_checks: %s", e)
        await asyncio.sleep(300)

async def periodic_token_refreshes():
    while True:
        try:
            async with AsyncSessionLocal() as db:
                stmt = select(Credential).where(
                    Credential.type == "antigravity",
                    Credential.status.notin_(["reauth_required", "disabled", "exhausted"]),
                )
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
                except Exception as exc:
                    async with AsyncSessionLocal() as db:
                        stmt = select(Credential).where(Credential.id == temp_cred.id)
                        res = await db.execute(stmt)
                        db_cred = res.scalar_one_or_none()
                        if db_cred:
                            if db_cred.status in {"reauth_required", "disabled", "exhausted"}:
                                continue
                            err = str(exc).lower()
                            if "invalid_grant" in err:
                                db_cred.status = "reauth_required"
                                db_cred.reset_at = None
                                await db.commit()
                            else:
                                db_cred.status = "cooldown"
                                await db.commit()
                                # Cooldown expiry lives in Redis; reset_at keeps
                                # tracking the quota window (#6, N1)
                                await redis_client.set(get_credential_cooldown_key(db_cred.id), "1", ex=300)
        except Exception as e:
            logger.exception("Error in periodic_token_refreshes: %s", e)
        await asyncio.sleep(600)

async def start_worker():
    await asyncio.gather(
        periodic_quota_resets(),
        periodic_health_checks(),
        periodic_token_refreshes()
    )
