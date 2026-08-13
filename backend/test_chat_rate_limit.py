"""Router-level: RATE_LIMIT must surface as HTTP 429, not 500."""
from __future__ import annotations

import os
import sys
import types
import uuid
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

_litellm = types.ModuleType("litellm")


async def _stub_acompletion(*args, **kwargs):
    raise RuntimeError("litellm stub: acompletion should not be called in unit tests")


async def _stub_aembedding(*args, **kwargs):
    raise RuntimeError("litellm stub: aembedding should not be called in unit tests")


_litellm.acompletion = _stub_acompletion
_litellm.aembedding = _stub_aembedding
sys.modules.setdefault("litellm", _litellm)

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("REDIS_REQUIRED", "false")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_chat_rate_limit.db")
os.environ.pop("ENCRYPTION_KEY", None)

from fastapi import HTTPException
from starlette.requests import Request

from app.api.routers.v1 import chat as chat_mod
from app.api.routers.v1.chat import (
    RATE_LIMIT_RETRY_AFTER_SECONDS,
    _http_exception_from_upstream_failure,
)
from app.core.error_classifier import UpstreamErrorKind

CLOUD_CODE_429 = (
    "HTTP 429: {\n  \"error\": {\n    \"code\": 429,\n"
    "    \"message\": \"Resource has been exhausted (e.g. check quota).\",\n"
    "    \"status\": \"RESOURCE_EXHAUSTED\"\n  }\n}\n"
)


class TestChatRateLimitStatus(TestCase):
    def test_helper_maps_generic_resource_exhausted_to_429(self):
        exc = _http_exception_from_upstream_failure(
            Exception(CLOUD_CODE_429),
            UpstreamErrorKind.RATE_LIMIT,
            fallback_status=500,
        )
        self.assertEqual(exc.status_code, 429)
        self.assertEqual(
            exc.headers.get("Retry-After"),
            str(RATE_LIMIT_RETRY_AFTER_SECONDS),
        )
        self.assertIn("RESOURCE_EXHAUSTED", str(exc.detail))

    def test_helper_does_not_use_fallback_500_for_rate_limit(self):
        exc = _http_exception_from_upstream_failure(
            Exception(CLOUD_CODE_429),
            None,
            fallback_status=500,
        )
        self.assertEqual(exc.status_code, 429)


class TestChatCompletionsRateLimitRouter(IsolatedAsyncioTestCase):
    async def test_no_next_credential_after_rate_limit_returns_429(self):
        """Live bug: last_exception was a generic Exception, so chat.py emitted 500."""
        vkey = types.SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4())
        cred = types.SimpleNamespace(
            id=uuid.uuid4(),
            type="antigravity",
            base_url=None,
            encrypted_secret="enc",
        )
        calls = {"select": 0}

        async def fake_select(*args, **kwargs):
            calls["select"] += 1
            if calls["select"] == 1:
                return cred, "gemini-3.6-flash-high"
            return None, None

        async def boom(*args, **kwargs):
            raise Exception(CLOUD_CODE_429)

        provider = types.SimpleNamespace(chat_completion=boom)
        db = AsyncMock()
        request = Request(
            {
                "type": "http",
                "headers": [],
                "method": "POST",
                "path": "/v1/chat/completions",
            }
        )

        with patch.object(
            chat_mod.CredentialSelector, "select_and_book", side_effect=fake_select
        ), patch.object(
            chat_mod.CredentialSelector, "release", new_callable=AsyncMock
        ), patch.object(
            chat_mod, "decrypt_secret", return_value="secret"
        ), patch.object(
            chat_mod, "get_provider", return_value=provider
        ), patch.object(
            chat_mod.usage_service, "check_key_limits", new_callable=AsyncMock
        ), patch.object(
            chat_mod.usage_service, "log_usage_event", new_callable=AsyncMock
        ), patch.object(
            chat_mod, "_handle_credential_failure", new_callable=AsyncMock
        ), patch.object(
            chat_mod, "remember_tip", new_callable=AsyncMock
        ):
            with self.assertRaises(HTTPException) as ctx:
                await chat_mod.chat_completions(
                    request=request,
                    payload={
                        "messages": [{"role": "user", "content": "ping"}],
                        "model": "gemini-3.6-flash-high",
                        "session_id": "rate-limit-router-test",
                    },
                    authorization="Bearer test-key",
                    db=db,
                    vkey=vkey,
                )

        self.assertEqual(ctx.exception.status_code, 429)
        self.assertEqual(
            ctx.exception.headers.get("Retry-After"),
            str(RATE_LIMIT_RETRY_AFTER_SECONDS),
        )
        self.assertGreaterEqual(calls["select"], 2)


if __name__ == "__main__":
    import unittest

    unittest.main(verbosity=2)
