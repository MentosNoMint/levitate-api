import random
import asyncio
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Credential
from app.redis_client import redis_client
from app.core.constants import get_credential_tokens_key, get_credential_concurrency_key, get_lock_credential_key

class CredentialSelector:
    @staticmethod
    async def get_active_credentials(
        db: AsyncSession, 
        model_name: str, 
        user_id: uuid.UUID,
        exclude_ids: Optional[List[str]] = None
    ) -> List[Credential]:
        now = datetime.now(timezone.utc)
        stmt = select(Credential).where(
            Credential.status == "active",
            Credential.user_id == user_id
        )
        if exclude_ids:
            uuid_excludes = []
            for eid in exclude_ids:
                if isinstance(eid, str):
                    try:
                        uuid_excludes.append(uuid.UUID(eid))
                    except ValueError:
                        pass
                else:
                    uuid_excludes.append(eid)
            stmt = stmt.where(~Credential.id.in_(uuid_excludes))
            
        result = await db.execute(stmt)
        all_creds = result.scalars().all()
        
        eligible = []
        for cred in all_creds:
            if cred.expires_at and cred.expires_at <= now:
                continue
            if cred.models:
                if model_name in cred.models:
                    eligible.append(cred)
        return eligible

    @staticmethod
    async def check_and_reset_quota(db: AsyncSession, credential: Credential) -> None:
        if not credential.reset_at:
            return
        now = datetime.now(timezone.utc)
        reset_at = credential.reset_at
        if reset_at.tzinfo is None:
            reset_at = reset_at.replace(tzinfo=timezone.utc)
        if now >= reset_at:
            credential.quota_used_tokens = 0
            redis_key = get_credential_tokens_key(credential.id)
            await redis_client.set(redis_key, "0")
            
            if credential.quota_window:
                new_reset = datetime.fromtimestamp(
                    now.timestamp() + credential.quota_window, 
                    tz=timezone.utc
                )
                credential.reset_at = new_reset
            else:
                credential.reset_at = None
                
            await db.commit()

    @classmethod
    async def select_and_book(
        cls, 
        db: AsyncSession, 
        model_name: str, 
        user_id: uuid.UUID,
        estimated_tokens: int = 1000,
        exclude_ids: Optional[List[str]] = None
    ) -> Optional[Credential]:
        credentials = await cls.get_active_credentials(db, model_name, user_id, exclude_ids=exclude_ids)
        if not credentials:
            return None

        for cred in credentials:
            await cls.check_and_reset_quota(db, cred)

        priority_groups = {}
        for cred in credentials:
            priority_groups.setdefault(cred.priority, []).append(cred)

        sorted_priorities = sorted(priority_groups.keys())

        for priority in sorted_priorities:
            group = priority_groups[priority]
            candidates = []
            
            for cred in group:
                concurrency_key = get_credential_concurrency_key(cred.id)
                tokens_key = get_credential_tokens_key(cred.id)
                
                curr_concurrency = await redis_client.get(concurrency_key)
                curr_tokens = await redis_client.get(tokens_key)
                
                concurrency_val = int(curr_concurrency) if curr_concurrency else 0
                tokens_val = int(curr_tokens) if curr_tokens else cred.quota_used_tokens

                if cred.concurrency_limit is not None and concurrency_val >= cred.concurrency_limit:
                    continue
                if cred.quota_total_tokens is not None and (tokens_val + estimated_tokens) > cred.quota_total_tokens:
                    continue
                
                candidates.append(cred)

            if not candidates:
                continue

            while candidates:
                total_weight = sum(c.weight for c in candidates)
                if total_weight <= 0:
                    selected = random.choice(candidates)
                else:
                    r = random.uniform(0, total_weight)
                    upto = 0.0
                    selected = None
                    for c in candidates:
                        if upto + c.weight >= r:
                            selected = c
                            break
                        upto += c.weight
                    if not selected:
                        selected = candidates[-1]

                booked = await cls._try_book(selected, estimated_tokens)
                if booked:
                    return selected
                else:
                    candidates.remove(selected)

        return None

    @staticmethod
    async def _try_book(credential: Credential, estimated_tokens: int) -> bool:
        lock_key = get_lock_credential_key(credential.id)
        concurrency_key = get_credential_concurrency_key(credential.id)
        tokens_key = get_credential_tokens_key(credential.id)
        
        acquired = await redis_client.set(lock_key, "1", ex=5, nx=True)
        if not acquired:
            return False

        try:
            curr_concurrency = await redis_client.get(concurrency_key)
            curr_tokens = await redis_client.get(tokens_key)
            
            concurrency_val = int(curr_concurrency) if curr_concurrency else 0
            tokens_val = int(curr_tokens) if curr_tokens else credential.quota_used_tokens

            if credential.concurrency_limit is not None and concurrency_val >= credential.concurrency_limit:
                return False
            if credential.quota_total_tokens is not None and (tokens_val + estimated_tokens) > credential.quota_total_tokens:
                return False

            await redis_client.incrby(concurrency_key, 1)
            return True
        finally:
            await redis_client.delete(lock_key)

    @staticmethod
    async def release(credential_id: str, actual_tokens_used: int, db: AsyncSession) -> None:
        concurrency_key = get_credential_concurrency_key(str(credential_id))
        tokens_key = get_credential_tokens_key(str(credential_id))

        curr = await redis_client.get(concurrency_key)
        if curr and int(curr) > 0:
            await redis_client.decrby(concurrency_key, 1)
        else:
            await redis_client.set(concurrency_key, "0")

        if actual_tokens_used > 0:
            new_tokens_used = await redis_client.incrby(tokens_key, actual_tokens_used)
            
            cred_uuid = uuid.UUID(str(credential_id)) if isinstance(credential_id, str) else credential_id
            stmt = select(Credential).where(Credential.id == cred_uuid)
            result = await db.execute(stmt)
            cred = result.scalar_one_or_none()
            if cred:
                cred.quota_used_tokens = new_tokens_used
                await db.commit()
