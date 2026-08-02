"""Parent-hash conversation tip sticky (fallback when no explicit session id).

Stores only tip hashes in Redis — never full chat history. OpenAI-style multi-turn
works by looking up hash(messages[:-1]) after each completed turn.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Optional

from app.core.constants import CONVERSATION_TIP_TTL_SECONDS, _binding_part
from app.redis_client import redis_client

logger = logging.getLogger(__name__)


def canonicalize_messages(messages: Any) -> str:
    """Return stable JSON for a messages list (order-preserving, key-sorted)."""
    plain = _to_plain(messages if isinstance(messages, list) else [])
    return json.dumps(plain, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def hash_messages(messages: Any) -> str:
    return hashlib.sha256(canonicalize_messages(messages).encode("utf-8")).hexdigest()


def get_conversation_tip_key(user_id: Any, model: str, tip_hash: str) -> str:
    return (
        f"gateway:conversation_tip:{user_id}:"
        f"{_binding_part((model or '').lower())}:{tip_hash}"
    )


def synthetic_tip_session_id(messages: Any) -> str:
    return f"tip-{hash_messages(messages)}"


async def resolve_session_id_from_tips(
    user_id: Any,
    model: str,
    messages: Any,
) -> Optional[str]:
    """Resolve sticky session from tip map.

    Empty messages → None (fill-first).
    Prefer parent tip hash(messages[:-1]) for multi-turn, then current tip for retries.
    """
    if not isinstance(messages, list) or not messages:
        return None

    if len(messages) >= 2:
        parent = await _load_tip(user_id, model, hash_messages(messages[:-1]))
        if parent and parent.get("session_id"):
            return str(parent["session_id"])

    current = await _load_tip(user_id, model, hash_messages(messages))
    if current and current.get("session_id"):
        return str(current["session_id"])
    return None


async def remember_tip(
    messages_for_tip: Any,
    user_id: Any,
    model: str,
    session_id: Optional[str],
    credential_id: Any,
) -> None:
    """Store tip hash → {session_id, credential_id} without persisting history."""
    if not session_id or not isinstance(messages_for_tip, list) or not messages_for_tip:
        return
    tip_hash = hash_messages(messages_for_tip)
    key = get_conversation_tip_key(user_id, model, tip_hash)
    payload = json.dumps(
        {
            "session_id": str(session_id),
            "credential_id": str(credential_id) if credential_id is not None else None,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    try:
        await redis_client.set(key, payload, ex=CONVERSATION_TIP_TTL_SECONDS)
    except Exception:
        logger.exception("Failed to remember conversation tip")


def extract_assistant_message(response: Any) -> Optional[dict]:
    """Normalize a non-stream completion into an OpenAI-style assistant message dict."""
    choices = _get_field(response, "choices") or []
    if not choices:
        return None
    message = _get_field(choices[0], "message")
    if message is None:
        return None
    plain = _to_plain(message)
    if not isinstance(plain, dict):
        return None
    out = dict(plain)
    out.setdefault("role", "assistant")
    return out


def new_stream_assistant_state() -> dict:
    return {
        "content_parts": [],
        "reasoning_parts": [],
        "tool_calls": {},  # index -> dict
        "images": [],
    }


def accumulate_stream_delta(state: dict, chunk: Any) -> None:
    """Fold one streaming chunk's delta into an assistant message accumulator."""
    choices = _get_field(chunk, "choices") or []
    if not choices:
        return
    delta = _get_field(choices[0], "delta")
    if delta is None:
        return

    content = _get_field(delta, "content")
    if content:
        state["content_parts"].append(str(content))

    reasoning = _get_field(delta, "reasoning_content")
    if reasoning:
        state["reasoning_parts"].append(str(reasoning))

    images = _get_field(delta, "images")
    if images:
        state["images"].extend(_to_plain(images) if isinstance(images, list) else [_to_plain(images)])

    tool_calls = _get_field(delta, "tool_calls") or []
    for tc in tool_calls:
        plain_tc = _to_plain(tc)
        if not isinstance(plain_tc, dict):
            continue
        idx = plain_tc.get("index")
        if idx is None:
            # Antigravity may emit full tool_call objects with stable ids.
            tc_id = plain_tc.get("id")
            if tc_id is not None:
                existing = next(
                    (v for v in state["tool_calls"].values() if v.get("id") == tc_id),
                    None,
                )
                if existing is None:
                    idx = len(state["tool_calls"])
                    state["tool_calls"][idx] = plain_tc
                else:
                    _merge_tool_call(existing, plain_tc)
                continue
            idx = len(state["tool_calls"])
        idx = int(idx)
        if idx not in state["tool_calls"]:
            state["tool_calls"][idx] = {
                "id": plain_tc.get("id"),
                "type": plain_tc.get("type") or "function",
                "function": {
                    "name": "",
                    "arguments": "",
                },
                "index": idx,
            }
        _merge_tool_call(state["tool_calls"][idx], plain_tc)


def build_assistant_message_from_stream(state: dict) -> dict:
    content = "".join(state.get("content_parts") or [])
    message: dict[str, Any] = {
        "role": "assistant",
        "content": content if content else None,
    }
    reasoning = "".join(state.get("reasoning_parts") or [])
    if reasoning:
        message["reasoning_content"] = reasoning
    images = state.get("images") or []
    if images:
        message["images"] = images
    tool_calls = state.get("tool_calls") or {}
    if tool_calls:
        ordered = [tool_calls[i] for i in sorted(tool_calls)]
        cleaned = []
        for tc in ordered:
            item = {k: v for k, v in tc.items() if k != "index"}
            cleaned.append(item)
        message["tool_calls"] = cleaned
    return message


def _merge_tool_call(target: dict, incoming: dict) -> None:
    if incoming.get("id"):
        target["id"] = incoming["id"]
    if incoming.get("type"):
        target["type"] = incoming["type"]
    fn = incoming.get("function")
    if isinstance(fn, dict):
        target_fn = target.setdefault("function", {"name": "", "arguments": ""})
        if fn.get("name"):
            target_fn["name"] = fn["name"]
        if fn.get("arguments"):
            target_fn["arguments"] = (target_fn.get("arguments") or "") + str(fn["arguments"])


async def _load_tip(user_id: Any, model: str, tip_hash: str) -> Optional[dict]:
    key = get_conversation_tip_key(user_id, model, tip_hash)
    try:
        raw = await redis_client.get(key)
    except Exception:
        logger.exception("Failed to load conversation tip")
        return None
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        data = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _get_field(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _to_plain(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(v) for v in value]
    if hasattr(value, "model_dump"):
        try:
            return _to_plain(value.model_dump())
        except Exception:
            pass
    if hasattr(value, "dict"):
        try:
            return _to_plain(value.dict())
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        return _to_plain({k: v for k, v in vars(value).items() if not k.startswith("_")})
    return str(value)
