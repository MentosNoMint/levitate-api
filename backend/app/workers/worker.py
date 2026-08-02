import asyncio
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import and_, or_, select

from app.core.constants import get_credential_concurrency_key, get_credential_tokens_key
from app.db.models import Credential
from app.db.session import AsyncSessionLocal
from app.providers.antigravity import AntigravityProvider
from app.providers.byo_upstream import BYOUpstreamProvider
from app.redis_client import redis_client

logger = logging.getLogger(__name__)


def _antigravity_groups_exhausted(credential: Credential) -> bool:
    quotas = credential.model_quotas or {}
    try:
        return all(float(quotas[key]) <= 0.0 for key in ("_group:gemini", "_group:others"))
    except (KeyError, TypeError, ValueError):
        return False


async def periodic_quota_resets():
    while True:
        try:
            async with AsyncSessionLocal() as db:
                now = datetime.now(timezone.utc)
                stmt = select(Credential).where(
                    or_(
                        and_(
                            Credential.type != "antigravity",
                            Credential.status.notin_(["reauth_required", "disabled"]),
                            Credential.reset_at.is_not(None),
                            Credential.reset_at <= now,
                        ),
                        and_(
                            Credential.status == "cooldown",
                            Credential.reset_at.is_not(None),
                            Credential.reset_at <= now,
                        ),
                    )
                )
                credentials = (await db.execute(stmt)).scalars().all()
                for credential in credentials:
                    if credential.status == "cooldown":
                        if credential.type == "antigravity" and _antigravity_groups_exhausted(credential):
                            credential.status = "exhausted"
                        else:
                            credential.status = "active"
                        credential.reset_at = None
                        continue

                    # Only ordinary credentials have a local quota counter that
                    # can be reset on a timer. AG quota state comes from Google.
                    if credential.type != "antigravity":
                        credential.quota_used_tokens = 0
                        credential.status = "active"
                        await redis_client.set(get_credential_tokens_key(credential.id), "0")
                        await redis_client.set(get_credential_concurrency_key(credential.id), "0")
                        credential.reset_at = (
                            now + timedelta(seconds=credential.quota_window)
                            if credential.quota_window
                            else None
                        )
                await db.commit()
        except Exception as exc:
            logger.exception("Error in periodic_quota_resets: %s", exc)
        await asyncio.sleep(10)


async def check_credential_health(credential: Credential) -> bool:
    if credential.status in {"reauth_required", "disabled"}:
        return False
    if credential.status == "cooldown" and credential.reset_at:
        reset_at = credential.reset_at
        if reset_at.tzinfo is None:
            reset_at = reset_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) < reset_at:
            return False
    try:
        if credential.type == "antigravity":
            result = await AntigravityProvider(credential).fetch_quota()
            return result.get("status") in ("active", "exhausted")
        model = credential.models[0] if credential.models else "gpt-3.5-turbo"
        await BYOUpstreamProvider(credential).chat_completion(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
        )
        return True
    except Exception:
        return False


async def periodic_health_checks():
    while True:
        try:
            async with AsyncSessionLocal() as db:
                credentials = (await db.execute(select(Credential))).scalars().all()
                credentials_data = [
                    {
                        "id": credential.id,
                        "type": credential.type,
                        "name": credential.name,
                        "provider": credential.provider,
                        "encrypted_secret": credential.encrypted_secret,
                        "base_url": credential.base_url,
                        "models": credential.models,
                        "status": credential.status,
                    }
                    for credential in credentials
                ]

            for data in credentials_data:
                temporary = Credential(**data)
                healthy = await check_credential_health(temporary)
                now = datetime.now(timezone.utc)
                async with AsyncSessionLocal() as db:
                    result = await db.execute(select(Credential).where(Credential.id == temporary.id))
                    credential = result.scalar_one_or_none()
                    if not credential:
                        continue
                    if credential.status in {"reauth_required", "disabled", "exhausted"}:
                        credential.last_check_at = now
                        await db.commit()
                        continue
                    if healthy and credential.type != "antigravity":
                        if credential.status in {"degraded", "error"}:
                            credential.status = "active"
                        elif credential.status == "cooldown" and credential.reset_at:
                            reset_at = credential.reset_at
                            if reset_at.tzinfo is None:
                                reset_at = reset_at.replace(tzinfo=timezone.utc)
                            if now >= reset_at:
                                credential.status = "active"
                                credential.reset_at = None
                    elif not healthy and credential.type != "antigravity":
                        # Probe failure is not quota exhaustion.
                        credential.status = "degraded"
                    credential.last_check_at = now
                    await db.commit()
        except Exception as exc:
            logger.exception("Error in periodic_health_checks: %s", exc)
        await asyncio.sleep(300)


async def periodic_token_refreshes():
    while True:
        try:
            async with AsyncSessionLocal() as db:
                credentials = (await db.execute(
                    select(Credential).where(
                        Credential.type == "antigravity",
                        Credential.status.notin_(["reauth_required", "disabled", "exhausted"]),
                    )
                )).scalars().all()
                credentials_data = [
                    {
                        "id": credential.id,
                        "type": credential.type,
                        "name": credential.name,
                        "provider": credential.provider,
                        "encrypted_secret": credential.encrypted_secret,
                    }
                    for credential in credentials
                ]

            for data in credentials_data:
                temporary = Credential(**data)
                try:
                    await AntigravityProvider(temporary).get_access_token()
                except Exception as exc:
                    async with AsyncSessionLocal() as db:
                        result = await db.execute(select(Credential).where(Credential.id == temporary.id))
                        credential = result.scalar_one_or_none()
                        if not credential:
                            continue
                        if credential.status in {"reauth_required", "disabled", "exhausted"}:
                            continue
                        err = str(exc).lower()
                        if "invalid_grant" in err:
                            credential.status = "reauth_required"
                            credential.reset_at = None
                        else:
                            # Network/5xx while refreshing must never mark exhausted/reauth.
                            credential.status = "cooldown"
                            credential.reset_at = datetime.now(timezone.utc) + timedelta(minutes=5)
                        await db.commit()
        except Exception as exc:
            logger.exception("Error in periodic_token_refreshes: %s", exc)
        await asyncio.sleep(600)


async def start_worker():
    await asyncio.gather(
        periodic_quota_resets(),
        periodic_health_checks(),
        periodic_token_refreshes(),
    )
