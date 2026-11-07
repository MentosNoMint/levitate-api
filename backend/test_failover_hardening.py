"""Failures that used to reach the client although a healthy answer was possible."""
import asyncio
import json
import os
import sys
import time
import types
import uuid
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

import httpx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["APP_ENV"] = "development"
os.environ.setdefault("REDIS_REQUIRED", "false")
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_failover_hardening.db"

from starlette.requests import Request

from app.api.routers.v1 import chat as chat_mod
from app.core.constants import get_credential_access_token_key, get_session_binding_key
from app.db.models import Base, Credential, User, VirtualKey
from app.db.session import AsyncSessionLocal, engine
from app.providers.antigravity import AntigravityProvider
from app.redis_client import redis_client
from app.services import usage_service

MODEL = "gemini-3.5-flash-low"


def _request():
    return Request({"type": "http", "headers": [], "method": "POST", "path": "/v1/chat/completions"})


def _answer(text="ok"):
    from litellm import ModelResponse

    return ModelResponse(
        choices=[{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
        model=MODEL,
    )


class _Base(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        redis_client.use_fake = True
        await redis_client.flushdb()
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        async with AsyncSessionLocal() as db:
            self.user = User(email=f"t-{uuid.uuid4().hex}@example.test", role="user")
            db.add(self.user)
            await db.flush()
            self.first = Credential(
                id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                user_id=self.user.id, type="antigravity", name="first", provider="google",
                encrypted_secret="secret", models=[MODEL], priority=1, status="active",
            )
            self.second = Credential(
                id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
                user_id=self.user.id, type="antigravity", name="second", provider="google",
                encrypted_secret="secret", models=[MODEL], priority=2, status="active",
            )
            self.vkey = VirtualKey(user_id=self.user.id, hashed_key=uuid.uuid4().hex, name="k", status="active")
            db.add_all([self.first, self.second, self.vkey])
            await db.commit()

    async def asyncTearDown(self):
        await redis_client.flushdb()

    async def _chat(self, provider_for, session_id="room-session"):
        with patch.object(chat_mod, "decrypt_secret", return_value="secret"), patch.object(
            chat_mod, "get_provider", side_effect=provider_for
        ), patch.object(chat_mod.usage_service, "check_key_limits", new_callable=AsyncMock):
            async with AsyncSessionLocal() as db:
                return await chat_mod.chat_completions(
                    request=_request(),
                    payload={"model": MODEL, "messages": [{"role": "user", "content": "hi"}], "session_id": session_id},
                    authorization="Bearer test-key",
                    db=db,
                    vkey=self.vkey,
                )


class TestRouterFailover(_Base):
    async def test_transient_failure_of_bound_account_moves_this_request_on(self):
        # The session is bound to `first` (prompt cache lives there). A Google
        # 503 on it must not surface: this one request goes to `second`.
        calls = []

        def provider_for(cred):
            async def chat_completion(**kwargs):
                calls.append(cred.name)
                if cred.name == "first":
                    raise Exception('HTTP 503: {"error":{"code":503,"status":"UNAVAILABLE"}}')
                return _answer()

            return types.SimpleNamespace(chat_completion=chat_completion)

        await redis_client.set(
            get_session_binding_key("antigravity", self.user.id, "room-session", MODEL), str(self.first.id)
        )
        response = await self._chat(provider_for)
        self.assertEqual(response.choices[0].message.content, "ok")
        self.assertEqual(calls, ["first", "second"])

    async def test_bookkeeping_failure_after_a_success_still_returns_the_answer(self):
        def provider_for(cred):
            return types.SimpleNamespace(chat_completion=AsyncMock(return_value=_answer("kept")))

        with patch.object(chat_mod.usage_service, "log_usage_event", side_effect=RuntimeError("db blip")):
            response = await self._chat(provider_for)
        self.assertEqual(response.choices[0].message.content, "kept")


class _Lines:
    def __init__(self, lines, status_code=200):
        self.status_code = status_code
        self.request = httpx.Request("POST", "https://example.test")
        self._lines = lines

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def aread(self):
        return b""


class _Ctx:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, *args):
        return None


class _Client:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def stream(self, *args, **kwargs):
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return _Ctx(response)


def _sse(obj):
    return "data: " + json.dumps(obj)


class TestProviderStream(_Base):
    async def _complete(self, responses):
        provider = AntigravityProvider(self.first)
        provider.get_access_token = AsyncMock(return_value="token")
        with patch(
            "app.providers.antigravity.decrypt_secret",
            return_value=json.dumps({"refresh_token": "r", "project_id": "p"}),
        ), patch("app.providers.antigravity.httpx.AsyncClient", return_value=_Client(responses)):
            return await provider.chat_completion(model=MODEL, messages=[{"role": "user", "content": "hi"}])

    async def test_complete_stream_is_an_answer(self):
        lines = [
            _sse({"response": {"candidates": [{"content": {"parts": [{"text": '{"a":'}]}}]}}),
            _sse({"response": {"candidates": [{"content": {"parts": [{"text": "1}"}]}, "finishReason": "STOP"}]}}),
        ]
        response = await self._complete([_Lines(lines)])
        self.assertEqual(response.choices[0].message.content, '{"a":1}')

    async def test_stream_cut_before_finish_reason_is_an_error_not_an_answer(self):
        # Regression: a stream closed mid-answer became finish_reason "stop"
        # with half a JSON object, and the client got an "invalid" answer.
        lines = [_sse({"response": {"candidates": [{"content": {"parts": [{"text": '{"a":'}]}}]}})]
        with self.assertRaisesRegex(Exception, "stream ended early"):
            await self._complete([_Lines(lines)])

    async def test_error_event_inside_the_stream_is_an_error(self):
        lines = [_sse({"error": {"code": 503, "message": "The service is currently unavailable.", "status": "UNAVAILABLE"}})]
        with self.assertRaisesRegex(Exception, "HTTP 503"):
            await self._complete([_Lines(lines)])


class TestTokenRefreshWait(_Base):
    async def test_waiter_refreshes_itself_when_the_holder_gave_up(self):
        # Regression: a request waiting on another one's token refresh waited
        # 95 s when that refresh failed, long after the caller had timed out.
        provider = AntigravityProvider(self.first)
        lock_key = f"lock:token_refresh:{self.first.id}"
        await redis_client.set(lock_key, "someone-else", ex=90)

        async def holder_gives_up():
            await asyncio.sleep(0.3)
            await redis_client.delete(lock_key)

        class _OAuth:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def post(self, *args, **kwargs):
                return types.SimpleNamespace(
                    status_code=200,
                    raise_for_status=lambda: None,
                    json=lambda: {"access_token": "fresh", "expires_in": 3600},
                )

        started = time.monotonic()
        with patch("app.providers.antigravity.decrypt_secret", return_value=json.dumps({"refresh_token": "r"})), patch(
            "app.providers.antigravity.httpx.AsyncClient", return_value=_OAuth()
        ):
            token, _ = await asyncio.gather(provider.get_access_token(), holder_gives_up())
        self.assertEqual(token, "fresh")
        self.assertLess(time.monotonic() - started, 5)
        self.assertEqual(await redis_client.get(get_credential_access_token_key(self.first.id)), "fresh")


class TestStreamErrorEvent(_Base):
    async def test_error_event_is_valid_json_even_with_quotes(self):
        async def gen():
            raise Exception('HTTP 403: {"error": {"message": "denied"}}')
            yield  # pragma: no cover

        events = []
        async for event in usage_service.stream_response_generator(
            types.SimpleNamespace(id=self.first.id, type="antigravity"),
            types.SimpleNamespace(usage=None, model_dump_json=lambda: "{}"),
            gen(),
            "secret",
            types.SimpleNamespace(id=None, user_id=self.user.id),
            MODEL,
            None,
            time.time(),
        ):
            events.append(event)
        error_event = [e for e in events if "error" in e][0]
        payload = json.loads(error_event[len("data: "):].strip())
        self.assertIn("denied", payload["error"])
