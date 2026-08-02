import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import get_vkey_rpm_key, get_vkey_tokens_key, get_model_quota_group
from app.core.error_classifier import classify_upstream_error_kind
from app.db.models import VirtualKey, UsageEvent
from app.redis_client import redis_client
from app.routing.selector import CredentialSelector
from app.security.egress import scan_for_leak, scan_for_regex_leaks


logger = logging.getLogger(__name__)


def _seconds_until_next_month() -> int:
    now = datetime.now(timezone.utc)
    if now.month == 12:
        nxt = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        nxt = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return max(60, int((nxt - now).total_seconds()))


async def incr_vkey_monthly_tokens(vkey_id, tokens: int) -> None:
    """Add to the virtual key's monthly usage; the counter expires at the end
    of the calendar month so the monthly limit actually resets (#7)."""
    token_key = get_vkey_tokens_key(vkey_id)
    await redis_client.incrby(token_key, tokens)
    ttl = await redis_client.ttl(token_key)
    if ttl is None or ttl < 0:
        await redis_client.expire(token_key, _seconds_until_next_month())


async def check_key_limits(vkey: VirtualKey, model_name: str) -> None:
    if vkey.allowed_model_groups:
        # Classify the model the same way routing does; a substring match can
        # never satisfy the "others" group and over-matches "gemini" (#8)
        model_group = get_model_quota_group(model_name)
        allowed_groups = {str(g).strip().lower() for g in vkey.allowed_model_groups}
        if model_group not in allowed_groups:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Model {model_name} is not allowed for this key",
            )

    if vkey.rpm_limit is not None:
        rpm_key = get_vkey_rpm_key(vkey.id)
        current_rpm = await redis_client.incrby(rpm_key, 1)
        # Re-arm the TTL whenever it is missing, not only on the first hit —
        # a crash between INCRBY and EXPIRE must not brick the key forever (#20)
        rpm_ttl = await redis_client.ttl(rpm_key)
        if rpm_ttl is None or rpm_ttl < 0:
            await redis_client.expire(rpm_key, 60)
        if current_rpm > vkey.rpm_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded for this key",
            )

    if vkey.monthly_token_limit is not None:
        token_key = get_vkey_tokens_key(vkey.id)
        used = await redis_client.get(token_key)
        used_value = int(used) if used else 0
        if used_value >= vkey.monthly_token_limit:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Monthly token limit exceeded for this key",
            )


async def log_usage_event(
    db: AsyncSession,
    vkey_id: Optional[uuid.UUID],
    cred_id: Optional[uuid.UUID],
    model_name: str,
    usage: Optional[Any],
    latency_ms: int,
    status_str: str,
) -> None:
    event = UsageEvent(
        virtual_key_id=vkey_id,
        credential_id=cred_id,
        model=model_name,
        prompt_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
        completion_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
        est_cost=0.0,
        latency_ms=latency_ms,
        status=status_str,
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
    start_time: float,
    session_context: Optional[tuple] = None,
    tip_context: Optional[dict] = None,
):
    from app.routing.conversation_tip import (
        accumulate_stream_delta,
        build_assistant_message_from_stream,
        new_stream_assistant_state,
        remember_tip,
    )

    total_prompt_tokens = 0
    total_completion_tokens = 0
    stream_error = None
    assistant_state = new_stream_assistant_state() if tip_context else None

    async def iterate_chunks():
        yield first_chunk
        async for chunk in response_gen:
            yield chunk

    try:
        async for chunk in iterate_chunks():
            if assistant_state is not None:
                accumulate_stream_delta(assistant_state, chunk)
            if hasattr(chunk, "model_dump_json"):
                chunk_data = chunk.model_dump_json()
            else:
                chunk_data = str(chunk)
            if getattr(cred, "type", None) != "antigravity":
                if scan_for_leak({}, chunk_data, [secret_to_scan]) or scan_for_regex_leaks(chunk_data):
                    raise Exception("Potential secret leak detected in streaming response")
            if getattr(chunk, "usage", None):
                total_prompt_tokens = chunk.usage.prompt_tokens
                total_completion_tokens = chunk.usage.completion_tokens
            yield f"data: {chunk_data}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as exc:
        stream_error = exc
        yield f"data: {{\"error\": \"{str(exc)}\"}}\n\n"
    finally:
        total_tokens = total_prompt_tokens + total_completion_tokens
        latency_ms = int((time.time() - start_time) * 1000)

        class UsageObj:
            def __init__(self, prompt, completion):
                self.prompt_tokens = prompt
                self.completion_tokens = completion

        usage_obj = UsageObj(total_prompt_tokens, total_completion_tokens)

        async def cleanup():
            from app.api.routers.v1.chat import _handle_credential_failure
            from app.db.models import Credential
            from app.db.session import AsyncSessionLocal
            from sqlalchemy import select

            async with AsyncSessionLocal() as local_db:
                await CredentialSelector.release(str(cred.id), total_tokens, local_db)
                if vkey.id and total_tokens > 0:
                    await incr_vkey_monthly_tokens(vkey.id, total_tokens)

                status_str = "success"
                if stream_error is not None:
                    status_str = "failure"
                    kind = classify_upstream_error_kind(stream_error)
                    result = await local_db.execute(select(Credential).where(Credential.id == cred.id))
                    db_cred = result.scalar_one_or_none()
                    if db_cred is not None:
                        session_id = None
                        if session_context:
                            user_id, session_id, binding_model, _provider = session_context
                            # Ensure vkey exposes user_id for the shared failure handler.
                            if not hasattr(vkey, "user_id"):
                                vkey.user_id = user_id
                            model_for_binding = binding_model or model_name
                        else:
                            model_for_binding = model_name
                        await _handle_credential_failure(
                            local_db, vkey, db_cred, session_id, model_for_binding, kind
                        )

                await log_usage_event(
                    local_db, vkey.id, cred.id, model_name, usage_obj, latency_ms, status_str
                )

                if (
                    stream_error is None
                    and tip_context
                    and tip_context.get("session_id")
                    and assistant_state is not None
                ):
                    request_messages = tip_context.get("messages") or []
                    if isinstance(request_messages, list) and request_messages:
                        assistant_message = build_assistant_message_from_stream(assistant_state)
                        await remember_tip(
                            list(request_messages) + [assistant_message],
                            tip_context.get("user_id"),
                            tip_context.get("model") or model_name,
                            tip_context.get("session_id"),
                            tip_context.get("credential_id", getattr(cred, "id", None)),
                        )

        await asyncio.shield(cleanup())
