import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    SESSION_BINDING_LOCK_TTL_SECONDS,
    SESSION_BINDING_TTL_SECONDS,
    get_credential_concurrency_key,
    get_credential_tokens_key,
    get_lock_credential_key,
    get_model_quota_group,
    get_session_binding_key,
    get_session_binding_lock_key,
    map_model_name,
)
from app.db.models import Credential
from app.redis_client import redis_client

logger = logging.getLogger(__name__)


class CredentialSelector:
    @staticmethod
    def _normalize_model(name: str) -> str:
        return (name or "").lower().replace(" ", "-").replace("(", "").replace(")", "").replace("/", "-")

    @staticmethod
    def _provider_namespace(credential: Credential) -> str:
        # Credential type is stable across OAuth refreshes and is safer than a user label.
        return str(credential.type or credential.provider or "unknown").lower()

    @staticmethod
    def _excluded_ids(exclude_ids: Optional[Iterable[str]]) -> set[uuid.UUID]:
        excluded: set[uuid.UUID] = set()
        for value in exclude_ids or ():
            try:
                excluded.add(value if isinstance(value, uuid.UUID) else uuid.UUID(str(value)))
            except (TypeError, ValueError, AttributeError):
                continue
        return excluded

    @classmethod
    def _model_matches(cls, credential: Credential, model_name: str) -> bool:
        normalized = cls._normalize_model(model_name)
        if credential.type == "antigravity" and ("embedding" in normalized or normalized.startswith("text-embedding")):
            return True
        return bool(
            credential.models
            and any(
                isinstance(model, str)
                and (cls._normalize_model(model) == normalized or model == model_name)
                for model in credential.models
            )
        )

    @staticmethod
    def _quota_value(credential: Credential, model_name: str) -> Optional[float]:
        quotas = credential.model_quotas or {}
        group_key = f"_group:{get_model_quota_group(model_name)}"
        value = quotas.get(group_key)
        if value is None:
            value = quotas.get(model_name)
        try:
            return None if value is None else float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _model_quota_available(cls, credential: Credential, model_name: str) -> bool:
        if credential.type != "antigravity":
            return True
        value = cls._quota_value(credential, model_name)
        if value is None:
            # Active accounts may not have been probed yet. An exhausted account with
            # no model data is never safe to select.
            return credential.status != "exhausted"
        return value > 0.0

    @staticmethod
    def _all_antigravity_groups_exhausted(credential: Credential) -> bool:
        quotas = credential.model_quotas or {}
        values = []
        for key in ("_group:gemini", "_group:others"):
            if key not in quotas:
                return False
            try:
                values.append(float(quotas[key]))
            except (TypeError, ValueError):
                return False
        return bool(values) and all(value <= 0.0 for value in values)

    @classmethod
    async def _refresh_expired_states(cls, db: AsyncSession, credentials: list[Credential]) -> None:
        now = datetime.now(timezone.utc)
        changed = False
        for credential in credentials:
            reset_at = credential.reset_at
            if reset_at and reset_at.tzinfo is None:
                reset_at = reset_at.replace(tzinfo=timezone.utc)
            if credential.type != "antigravity" and reset_at and now >= reset_at and credential.status in {
                "active", "cooldown", "exhausted"
            }:
                credential.quota_used_tokens = 0
                credential.status = "active"
                credential.reset_at = (
                    datetime.fromtimestamp(now.timestamp() + credential.quota_window, tz=timezone.utc)
                    if credential.quota_window
                    else None
                )
                await redis_client.set(get_credential_tokens_key(credential.id), "0")
                changed = True
            elif credential.status == "cooldown" and reset_at and now >= reset_at:
                if credential.type == "antigravity" and cls._all_antigravity_groups_exhausted(credential):
                    credential.status = "exhausted"
                else:
                    credential.status = "active"
                credential.reset_at = None
                changed = True
            elif credential.type == "antigravity" and credential.status == "exhausted":
                # Repair only a fully populated stale global status. If a quota
                # group is missing, keep the terminal state so an unknown target
                # group cannot accidentally select this account.
                quotas = credential.model_quotas or {}
                try:
                    group_values = [
                        float(quotas[key]) for key in ("_group:gemini", "_group:others")
                    ]
                except (KeyError, TypeError, ValueError):
                    group_values = []
                if len(group_values) == 2 and any(value > 0.0 for value in group_values):
                    credential.status = "active"
                    credential.reset_at = None
                    changed = True
        if changed:
            await db.commit()

    @classmethod
    async def get_active_credentials(
        cls,
        db: AsyncSession,
        model_name: str,
        user_id: uuid.UUID,
        exclude_ids: Optional[List[str]] = None,
    ) -> Tuple[List[Credential], str]:
        logger.debug("get_active_credentials: model=%s user_id=%s exclude=%s", model_name, user_id, exclude_ids)
        excluded = cls._excluded_ids(exclude_ids)
        result = await db.execute(select(Credential).where(Credential.user_id == user_id))
        all_credentials = list(result.scalars().all())
        await cls._refresh_expired_states(db, all_credentials)
        now = datetime.now(timezone.utc)

        def find_eligible(candidate_model: str) -> list[Credential]:
            eligible = []
            for credential in all_credentials:
                if credential.id in excluded:
                    continue
                if credential.expires_at:
                    expires_at = credential.expires_at
                    if expires_at.tzinfo is None:
                        expires_at = expires_at.replace(tzinfo=timezone.utc)
                    if expires_at <= now:
                        continue
                if credential.status in {"cooldown", "degraded", "error", "reauth_required", "disabled"}:
                    continue
                if credential.status not in {"active", "exhausted"}:
                    continue
                if credential.status == "exhausted" and credential.type != "antigravity":
                    continue
                if not cls._model_quota_available(credential, candidate_model):
                    continue
                if cls._model_matches(credential, candidate_model):
                    eligible.append(credential)
            return eligible

        eligible = find_eligible(model_name)
        if eligible:
            return eligible, model_name

        mapped_name = map_model_name(model_name)
        if mapped_name != model_name:
            eligible = find_eligible(mapped_name)
            if eligible:
                return eligible, mapped_name
        return [], model_name

    @classmethod
    async def check_and_reset_quota(cls, db: AsyncSession, credential: Credential) -> None:
        """Reset only ordinary credential windows; AG quota comes from Google probing."""
        if credential.type == "antigravity" or not credential.reset_at:
            return
        if credential.status in {"reauth_required", "disabled"}:
            return
        now = datetime.now(timezone.utc)
        reset_at = credential.reset_at
        if reset_at.tzinfo is None:
            reset_at = reset_at.replace(tzinfo=timezone.utc)
        if now < reset_at:
            return
        credential.quota_used_tokens = 0
        credential.status = "active"
        credential.reset_at = (
            datetime.fromtimestamp(now.timestamp() + credential.quota_window, tz=timezone.utc)
            if credential.quota_window
            else None
        )
        await redis_client.set(get_credential_tokens_key(credential.id), "0")
        await db.commit()

    @staticmethod
    async def _acquire_session_lock(key: str) -> Optional[str]:
        token = uuid.uuid4().hex
        for _ in range(100):
            if await redis_client.set(key, token, ex=SESSION_BINDING_LOCK_TTL_SECONDS, nx=True):
                return token
            await asyncio.sleep(0.01)
        return None

    @staticmethod
    async def _release_session_lock(key: str, token: Optional[str]) -> None:
        if token:
            await redis_client.compare_delete(key, token)

    @staticmethod
    async def _acquire_credential_state_lock(credential_id) -> Optional[str]:
        """Serialize durable account-state transitions with booking operations."""
        key = get_lock_credential_key(credential_id)
        token = uuid.uuid4().hex
        for _ in range(100):
            if await redis_client.set(key, token, ex=15, nx=True):
                return token
            await asyncio.sleep(0.01)
        return None

    @staticmethod
    async def _release_credential_state_lock(credential_id, token: Optional[str]) -> None:
        if token:
            await redis_client.compare_delete(get_lock_credential_key(credential_id), token)

    @classmethod
    async def _read_binding(
        cls,
        credentials: list[Credential],
        user_id: uuid.UUID,
        session_id: str,
        matched_model: str,
    ) -> tuple[Optional[str], Optional[uuid.UUID]]:
        namespaces = sorted({cls._provider_namespace(credential) for credential in credentials})
        for namespace in namespaces:
            key = get_session_binding_key(namespace, user_id, session_id, matched_model)
            value = await redis_client.get(key)
            if value:
                try:
                    return key, uuid.UUID(str(value))
                except (TypeError, ValueError):
                    await redis_client.delete(key)
        return None, None

    @classmethod
    async def invalidate_binding(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        session_id: Optional[str],
        model_name: str,
        provider: Optional[str] = None,
    ) -> None:
        if not session_id:
            return
        lock_key = get_session_binding_lock_key(user_id, session_id, model_name)
        lock_token = await cls._acquire_session_lock(lock_key)
        if not lock_token:
            logger.warning("Could not acquire session binding lock while invalidating session=%s", session_id)
            return
        try:
            namespaces = {provider} if provider else set()
            if not namespaces:
                result = await db.execute(select(Credential.type).where(Credential.user_id == user_id))
                namespaces.update(str(value) for value in result.scalars().all() if value)
            for namespace in namespaces:
                await redis_client.delete(get_session_binding_key(namespace, user_id, session_id, model_name))
        finally:
            await cls._release_session_lock(lock_key, lock_token)

    @staticmethod
    async def _token_quota_available(credential: Credential, estimated_tokens: int) -> bool:
        if credential.type == "antigravity" or credential.quota_total_tokens is None:
            return True
        tokens_key = get_credential_tokens_key(credential.id)
        current = await redis_client.get(tokens_key)
        try:
            used_tokens = int(current) if current is not None else int(credential.quota_used_tokens or 0)
        except (TypeError, ValueError):
            used_tokens = int(credential.quota_used_tokens or 0)
        return used_tokens + estimated_tokens <= credential.quota_total_tokens

    @classmethod
    async def _select_without_session(
        cls, credentials: list[Credential], estimated_tokens: int, model_name: str, matched_model: str
    ) -> Optional[Credential]:
        for credential in sorted(credentials, key=lambda item: (item.priority, str(item.id))):
            if await cls._try_book(credential, estimated_tokens, matched_model):
                return credential
        return None

    @classmethod
    async def select_and_book(
        cls,
        db: AsyncSession,
        model_name: str,
        user_id: uuid.UUID,
        estimated_tokens: int = 1000,
        exclude_ids: Optional[List[str]] = None,
        session_id: Optional[str] = None,
    ) -> Tuple[Optional[Credential], str]:
        credentials, matched_model = await cls.get_active_credentials(db, model_name, user_id, exclude_ids)
        if not credentials:
            return None, matched_model
        if not session_id:
            return await cls._select_without_session(credentials, estimated_tokens, model_name, matched_model), matched_model

        lock_key = get_session_binding_lock_key(user_id, session_id, matched_model)
        lock_token = await cls._acquire_session_lock(lock_key)
        if not lock_token:
            return None, matched_model
        try:
            # Re-read after acquiring the conversation lock so status and first-bind
            # decisions cannot be based on a stale snapshot.
            credentials, matched_model = await cls.get_active_credentials(model_name=model_name, user_id=user_id, db=db, exclude_ids=exclude_ids)
            if not credentials:
                return None, matched_model
            binding_key, bound_id = await cls._read_binding(credentials, user_id, session_id, matched_model)
            excluded = cls._excluded_ids(exclude_ids)
            by_id = {credential.id: credential for credential in credentials}

            if bound_id:
                if bound_id in excluded:
                    # A caller must explicitly invalidate before it can fail over.
                    return None, matched_model
                bound = by_id.get(bound_id)
                if bound is None:
                    # The persisted account is no longer eligible (cooldown, quota,
                    # reauth, expiry, or model removal), so its stale binding is safe
                    # to discard and a new healthy account may be chosen.
                    if binding_key:
                        await redis_client.delete(binding_key)
                elif not cls._model_quota_available(bound, matched_model):
                    await redis_client.delete(binding_key)
                elif not await cls._token_quota_available(bound, estimated_tokens):
                    # A local token window is a hard exhaustion condition, unlike
                    # a temporary concurrency lease. Rebind this session so it can
                    # continue on the next eligible account.
                    await redis_client.delete(binding_key)
                    bound.status = "exhausted"
                    await db.commit()
                    credentials = [candidate for candidate in credentials if candidate.id != bound.id]
                else:
                    # A bound account being busy is not a reason to rotate a live
                    # conversation to another account.
                    if await cls._try_book(bound, estimated_tokens, matched_model):
                        if binding_key:
                            await redis_client.expire(binding_key, SESSION_BINDING_TTL_SECONDS)
                        return bound, matched_model
                    return None, matched_model

            selected = await cls._select_without_session(credentials, estimated_tokens, model_name, matched_model)
            if not selected:
                return None, matched_model

            selected_key = get_session_binding_key(
                cls._provider_namespace(selected), user_id, session_id, matched_model
            )
            existing = await redis_client.get(selected_key)
            if existing and str(existing) != str(selected.id):
                await cls._release_booked(selected)
                return None, matched_model
            if await redis_client.set(selected_key, str(selected.id), ex=SESSION_BINDING_TTL_SECONDS, nx=True):
                return selected, matched_model

            # A selector outside this process may have won the first-bind race. Do
            # not return a different account; release the speculative lease.
            winner = await redis_client.get(selected_key)
            if winner and str(winner) == str(selected.id):
                await redis_client.expire(selected_key, SESSION_BINDING_TTL_SECONDS)
                return selected, matched_model
            await cls._release_booked(selected)
            return None, matched_model
        finally:
            await cls._release_session_lock(lock_key, lock_token)

    @classmethod
    async def _release_booked(cls, credential: Credential) -> None:
        await redis_client.decrby_nonnegative(get_credential_concurrency_key(credential.id), 1)

    @classmethod
    async def _try_book(
        cls,
        credential: Credential,
        estimated_tokens: int,
        model_name: str = "",
        matched_model: Optional[str] = None,
    ) -> bool:
        if matched_model is not None:
            model_name = matched_model
        lock_key = get_lock_credential_key(credential.id)
        concurrency_key = get_credential_concurrency_key(credential.id)
        tokens_key = get_credential_tokens_key(credential.id)
        lock_token = uuid.uuid4().hex
        acquired = await redis_client.set(lock_key, lock_token, ex=5, nx=True)
        if not acquired:
            return False
        try:
            curr_concurrency = await redis_client.get(concurrency_key)
            curr_tokens = await redis_client.get(tokens_key)
            concurrency_value = int(curr_concurrency) if curr_concurrency else 0
            tokens_value = int(curr_tokens) if curr_tokens else credential.quota_used_tokens
            if credential.concurrency_limit is not None and concurrency_value >= credential.concurrency_limit:
                return False
            if (
                credential.type != "antigravity"
                and credential.quota_total_tokens is not None
                and tokens_value + estimated_tokens > credential.quota_total_tokens
            ):
                return False
            if credential.type == "antigravity" and not cls._model_quota_available(credential, model_name):
                return False
            await redis_client.incrby(concurrency_key, 1)
            await redis_client.expire(concurrency_key, 120)
            return True
        finally:
            await redis_client.compare_delete(lock_key, lock_token)

    @staticmethod
    async def release(credential_id: str, actual_tokens_used: int, db: AsyncSession) -> None:
        concurrency_key = get_credential_concurrency_key(str(credential_id))
        tokens_key = get_credential_tokens_key(str(credential_id))
        await redis_client.decrby_nonnegative(concurrency_key, 1)

        if actual_tokens_used > 0:
            new_tokens_used = await redis_client.incrby(tokens_key, actual_tokens_used)
            credential_uuid = uuid.UUID(str(credential_id)) if isinstance(credential_id, str) else credential_id
            result = await db.execute(select(Credential).where(Credential.id == credential_uuid))
            credential = result.scalar_one_or_none()
            if credential:
                credential.quota_used_tokens = new_tokens_used
                await db.commit()

    @staticmethod
    def session_binding_key(provider: str, user_id, session_id: str, model_name: str) -> str:
        """Public helper for diagnostics/tests without exposing raw session IDs."""
        return get_session_binding_key(provider, user_id, session_id, model_name)
