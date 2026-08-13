import asyncio
import json
import os
import sys
import uuid
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.error_classifier import (
    UpstreamErrorKind,
    classify_upstream_error_kind,
    should_invalidate_session_binding,
    should_mutate_credential_status,
)
from app.db.models import Base, Credential, User, VirtualKey
from app.db.session import AsyncSessionLocal, engine
from app.providers.antigravity import AntigravityProvider
from app.redis_client import redis_client


class OAuthResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {"access_token": "access-token", "expires_in": 3600}
        self.request = httpx.Request("POST", "https://oauth2.googleapis.com/token")

    @property
    def text(self):
        return json.dumps(self._payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("oauth failure", request=self.request, response=self)


class OAuthClient:
    def __init__(self, response, delay=0):
        self.response = response
        self.delay = delay
        self.calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, *args, **kwargs):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.response


class StreamResponse:
    status_code = 200
    request = httpx.Request("POST", "https://example.test")

    async def aiter_lines(self):
        if False:
            yield ""

    async def aread(self):
        return b""


class StreamContext:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, *args):
        return None


class ChatClient:
    def __init__(self, captured):
        self.captured = captured
        self.response = StreamResponse()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def stream(self, *args, **kwargs):
        self.captured.append(kwargs["json"])
        return StreamContext(self.response)


class TestProviderLifecycle(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        redis_client.use_fake = True
        await redis_client.flushdb()
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        async with AsyncSessionLocal() as db:
            user = User(email=f"oauth-{uuid.uuid4().hex}@example.test", role="user")
            db.add(user)
            await db.flush()
            self.credential = Credential(
                user_id=user.id,
                type="antigravity",
                name="oauth-account",
                provider="google",
                encrypted_secret="encrypted-secret",
                models=["gemini-3.5-flash-low"],
                status="active",
            )
            db.add(self.credential)
            await db.commit()
            self.credential_id = self.credential.id

    async def asyncTearDown(self):
        await redis_client.flushdb()

    async def test_quota_and_rate_limit_are_distinct(self):
        quota = Exception("HTTP 429 RESOURCE_EXHAUSTED: quota exceeded")
        rate = Exception("HTTP 429 Too Many Requests")
        self.assertEqual(classify_upstream_error_kind(quota), UpstreamErrorKind.QUOTA)
        self.assertEqual(classify_upstream_error_kind(rate), UpstreamErrorKind.RATE_LIMIT)

    async def test_antigravity_sends_full_history_stable_ids_and_no_explicit_cache_resource(self):
        captured = []
        provider = AntigravityProvider(self.credential)
        provider.get_access_token = AsyncMock(return_value="token")
        client = ChatClient(captured)
        messages = [
            {"role": "system", "content": "system one"},
            {"role": "system", "content": "system two"},
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "answer"},
            {"role": "user", "content": "follow-up"},
        ]
        with patch(
            "app.providers.antigravity.decrypt_secret",
            return_value=json.dumps({"refresh_token": "refresh", "project_id": "project"}),
        ), patch("app.providers.antigravity.httpx.AsyncClient", return_value=client):
            await provider.chat_completion(
                model="gemini-3.5-flash-low",
                messages=messages,
                session_id="stable-session",
            )
        wrapper = captured[0]
        request = wrapper["request"]
        self.assertEqual(wrapper.get("userAgent"), "antigravity")
        self.assertTrue(str(wrapper.get("requestId", "")).startswith("agent/"))
        self.assertNotIn("requestId", request)
        self.assertEqual(request["sessionId"], "stable-session")
        self.assertEqual([item["role"] for item in request["contents"]], ["user", "model", "user"])
        self.assertEqual(request["contents"][0]["parts"][0]["text"], "first")
        self.assertEqual(request["contents"][1]["parts"][0]["text"], "answer")
        self.assertEqual(request["contents"][2]["parts"][0]["text"], "follow-up")
        self.assertEqual(
            [part["text"] for part in request["systemInstruction"]["parts"]],
            ["system one", "system two"],
        )
        self.assertNotIn("cachedContents", request)

    async def test_oauth_refresh_is_single_flight(self):
        response = OAuthResponse()
        client = OAuthClient(response, delay=0.05)
        provider_a = AntigravityProvider(self.credential)
        provider_b = AntigravityProvider(self.credential)
        with patch("app.providers.antigravity.decrypt_secret", return_value=json.dumps({"refresh_token": "refresh"})), patch(
            "app.providers.antigravity.httpx.AsyncClient", return_value=client
        ):
            tokens = await asyncio.gather(provider_a.get_access_token(), provider_b.get_access_token())
        self.assertEqual(tokens, ["access-token", "access-token"])
        self.assertEqual(client.calls, 1)

    async def test_invalid_grant_requires_reauth(self):
        response = OAuthResponse(400, {"error": "invalid_grant"})
        provider = AntigravityProvider(self.credential)
        with patch("app.providers.antigravity.decrypt_secret", return_value=json.dumps({"refresh_token": "expired"})), patch(
            "app.providers.antigravity.httpx.AsyncClient", return_value=OAuthClient(response)
        ):
            with self.assertRaisesRegex(Exception, "invalid_grant"):
                await provider.get_access_token()
        async with AsyncSessionLocal() as db:
            refreshed = await db.get(Credential, self.credential_id)
            self.assertEqual(refreshed.status, "reauth_required")




class FakeHTTPError(Exception):
    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code


class TestErrorClassification(IsolatedAsyncioTestCase):
    def test_client_400_is_client_not_quota(self):
        err = FakeHTTPError(400, "INVALID_ARGUMENT: bad schema for tool call")
        self.assertEqual(classify_upstream_error_kind(err), UpstreamErrorKind.CLIENT)

    def test_network_and_5xx_are_transient_not_exhausted(self):
        self.assertEqual(
            classify_upstream_error_kind(FakeHTTPError(503, "temporarily unavailable")),
            UpstreamErrorKind.TRANSIENT,
        )
        self.assertEqual(
            classify_upstream_error_kind(Exception("connection reset by peer")),
            UpstreamErrorKind.TRANSIENT,
        )
        self.assertEqual(
            classify_upstream_error_kind(
                Exception(
                    'HTTP 400: {"error":{"code":400,"message":"User location is not supported for the API use.","status":"FAILED_PRECONDITION"}}'
                )
            ),
            UpstreamErrorKind.TRANSIENT,
        )
        self.assertEqual(
            classify_upstream_error_kind(
                Exception("FAILED_PRECONDITION: not available in your country")
            ),
            UpstreamErrorKind.TRANSIENT,
        )

    def test_quota_vs_rate_limit_and_403_resource_exhausted(self):
        quota = FakeHTTPError(403, "RESOURCE_EXHAUSTED: quota exceeded for project")
        rate = FakeHTTPError(429, "Too Many Requests: rate limit per minute")
        self.assertEqual(classify_upstream_error_kind(quota), UpstreamErrorKind.QUOTA)
        self.assertEqual(classify_upstream_error_kind(rate), UpstreamErrorKind.RATE_LIMIT)

    def test_generic_429_resource_exhausted_is_rate_limit(self):
        cloud_code = FakeHTTPError(
            429,
            '{"error":{"code":429,"status":"RESOURCE_EXHAUSTED","message":"Resource has been exhausted (e.g. check quota)."}}',
        )
        bare = Exception("HTTP 429 RESOURCE_EXHAUSTED")
        self.assertEqual(classify_upstream_error_kind(cloud_code), UpstreamErrorKind.RATE_LIMIT)
        self.assertEqual(classify_upstream_error_kind(bare), UpstreamErrorKind.RATE_LIMIT)

    def test_explicit_quota_markers_remain_quota(self):
        self.assertEqual(
            classify_upstream_error_kind(Exception("HTTP 429 RESOURCE_EXHAUSTED: quota exceeded")),
            UpstreamErrorKind.QUOTA,
        )
        self.assertEqual(
            classify_upstream_error_kind(Exception("You exceeded your current quota")),
            UpstreamErrorKind.QUOTA,
        )
        self.assertEqual(
            classify_upstream_error_kind(Exception("quota_exceeded")),
            UpstreamErrorKind.QUOTA,
        )
        self.assertEqual(
            classify_upstream_error_kind(Exception("daily limit reached")),
            UpstreamErrorKind.QUOTA,
        )
        self.assertEqual(
            classify_upstream_error_kind(Exception("billing hard limit reached")),
            UpstreamErrorKind.QUOTA,
        )

    def test_invalid_grant_is_auth(self):
        self.assertEqual(
            classify_upstream_error_kind(Exception("invalid_grant: token revoked")),
            UpstreamErrorKind.AUTH,
        )

    def test_bare_not_exhausted_is_not_quota(self):
        # Regression: substring "exhausted" must not match "not exhausted".
        self.assertNotEqual(
            classify_upstream_error_kind(Exception("capacity is not exhausted yet")),
            UpstreamErrorKind.QUOTA,
        )


    def test_configuration_does_not_disable_account_via_classifier(self):
        # Request-path 400/schema must be CLIENT, never CONFIGURATION→disabled.
        err = FakeHTTPError(400, "bad request: invalid schema")
        self.assertEqual(classify_upstream_error_kind(err), UpstreamErrorKind.CLIENT)
        self.assertFalse(should_mutate_credential_status(UpstreamErrorKind.CONFIGURATION))
        self.assertFalse(should_invalidate_session_binding(UpstreamErrorKind.CLIENT))
        self.assertFalse(should_invalidate_session_binding(UpstreamErrorKind.UNKNOWN))
        self.assertFalse(should_invalidate_session_binding(UpstreamErrorKind.TRANSIENT))
        self.assertTrue(should_invalidate_session_binding(UpstreamErrorKind.QUOTA))

    def test_permission_403_without_quota_is_client(self):
        err = FakeHTTPError(403, "PERMISSION_DENIED: permission denied for model")
        self.assertEqual(classify_upstream_error_kind(err), UpstreamErrorKind.CLIENT)


class TestFailureStatusTransitions(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        redis_client.use_fake = True
        await redis_client.flushdb()
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        async with AsyncSessionLocal() as db:
            user = User(email=f"status-{uuid.uuid4().hex}@example.test", role="user")
            db.add(user)
            await db.flush()
            self.user_id = user.id
            self.credential = Credential(
                user_id=user.id,
                type="antigravity",
                name="status-account",
                provider="google",
                encrypted_secret="secret",
                models=["gemini-3.5-flash-low"],
                status="active",
                model_quotas={"_group:gemini": 0.5, "_group:others": 0.8},
            )
            db.add(self.credential)
            await db.flush()
            self.vkey = VirtualKey(
                user_id=user.id,
                hashed_key=uuid.uuid4().hex,
                name="vk",
                status="active",
            )
            db.add(self.vkey)
            await db.commit()
            self.credential_id = self.credential.id
            self.vkey_id = self.vkey.id

    async def asyncTearDown(self):
        await redis_client.flushdb()

    async def _cred(self, db):
        return await db.get(Credential, self.credential_id)

    async def test_client_400_does_not_change_status(self):
        from app.api.routers.v1.chat import _handle_credential_failure

        async with AsyncSessionLocal() as db:
            cred = await self._cred(db)
            vkey = await db.get(VirtualKey, self.vkey_id)
            await _handle_credential_failure(
                db, vkey, cred, "sess-client", "gemini-3.5-flash-low", UpstreamErrorKind.CLIENT
            )
            refreshed = await self._cred(db)
            self.assertEqual(refreshed.status, "active")
            self.assertEqual(refreshed.model_quotas["_group:gemini"], 0.5)

    async def test_transient_does_not_mark_exhausted(self):
        from app.api.routers.v1.chat import _handle_credential_failure

        async with AsyncSessionLocal() as db:
            cred = await self._cred(db)
            vkey = await db.get(VirtualKey, self.vkey_id)
            await _handle_credential_failure(
                db, vkey, cred, "sess-transient", "gemini-3.5-flash-low", UpstreamErrorKind.TRANSIENT
            )
            refreshed = await self._cred(db)
            self.assertEqual(refreshed.status, "cooldown")
            self.assertNotEqual(refreshed.status, "exhausted")
            self.assertIsNotNone(refreshed.reset_at)

    async def test_quota_marks_group_and_invalid_grant_reauth(self):
        from app.api.routers.v1.chat import _handle_credential_failure

        async with AsyncSessionLocal() as db:
            cred = await self._cred(db)
            vkey = await db.get(VirtualKey, self.vkey_id)
            await _handle_credential_failure(
                db, vkey, cred, "sess-quota", "gemini-3.5-flash-low", UpstreamErrorKind.QUOTA
            )
            refreshed = await self._cred(db)
            self.assertEqual(refreshed.model_quotas["_group:gemini"], 0.0)
            self.assertEqual(refreshed.status, "active")

            await _handle_credential_failure(
                db, vkey, refreshed, "sess-auth", "gemini-3.5-flash-low", UpstreamErrorKind.AUTH
            )
            refreshed = await self._cred(db)
            self.assertEqual(refreshed.status, "reauth_required")

    async def test_worker_does_not_revive_reauth_disabled_exhausted(self):
        from app.workers.worker import check_credential_health, periodic_health_checks

        async with AsyncSessionLocal() as db:
            cred = await self._cred(db)
            cred.status = "reauth_required"
            await db.commit()
            healthy = await check_credential_health(cred)
            self.assertFalse(healthy)
            cred = await self._cred(db)
            self.assertEqual(cred.status, "reauth_required")

            cred.status = "exhausted"
            cred.model_quotas = {"_group:gemini": 0.0, "_group:others": 0.0}
            await db.commit()
            healthy = await check_credential_health(cred)
            # Health probe may succeed for exhausted AG accounts, but worker must not
            # flip them back to active (antigravity branch skips mutation).
            async with AsyncSessionLocal() as db2:
                row = await db2.get(Credential, self.credential_id)
                self.assertEqual(row.status, "exhausted")


    async def test_list_credentials_derives_exhausted_display(self):
        from app.services.credential_service import list_credentials

        async with AsyncSessionLocal() as db:
            cred = await self._cred(db)
            cred.status = "active"
            cred.model_quotas = {"_group:gemini": 0.0, "_group:others": 0.0}
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(cred, "model_quotas")
            await db.commit()
            listed = await list_credentials(db, self.user_id)
            row = next(item for item in listed if item["id"] == self.credential_id)
            self.assertEqual(row["status"], "exhausted")

    async def test_flag_modified_keeps_model_quotas_visible(self):
        from app.api.routers.v1.chat import _mark_antigravity_group_exhausted
        from app.services.credential_service import list_credentials

        async with AsyncSessionLocal() as db:
            cred = await self._cred(db)
            await _mark_antigravity_group_exhausted(cred, "claude-sonnet-4-6-thinking")
            await db.commit()
            listed = await list_credentials(db, self.user_id)
            row = next(item for item in listed if item["id"] == self.credential_id)
            self.assertEqual(row["model_quotas"]["_group:others"], 0.0)
            self.assertEqual(row["status"], "active")


if __name__ == "__main__":
    import unittest

    unittest.main()
