import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from unittest import IsolatedAsyncioTestCase

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.api.routers.v1.chat import _handle_credential_failure, get_session_id
from app.core.constants import get_session_binding_key
from app.core.error_classifier import UpstreamErrorKind
from app.db.models import Base, Credential, User, VirtualKey
from app.db.session import AsyncSessionLocal, engine
from app.redis_client import redis_client
from app.routing.selector import CredentialSelector


class TestSessionAffinity(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        redis_client.use_fake = True
        await redis_client.flushdb()
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        async with AsyncSessionLocal() as db:
            self.user = User(email=f"test-{uuid.uuid4().hex}@example.test", role="user")
            db.add(self.user)
            await db.flush()
            # Explicit non-sorted IDs make the test independent of UUID ordering.
            self.first = Credential(
                id=uuid.UUID("ffffffff-ffff-ffff-ffff-fffffffffff1"),
                user_id=self.user.id,
                type="antigravity",
                name="account-first",
                provider="google",
                encrypted_secret="secret",
                models=["gemini-3.5-flash-low"],
                priority=1,
                status="active",
            )
            self.second = Credential(
                id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                user_id=self.user.id,
                type="antigravity",
                name="account-second",
                provider="google",
                encrypted_secret="secret",
                models=["gemini-3.5-flash-low"],
                priority=2,
                status="active",
            )
            db.add_all([self.first, self.second])
            await db.commit()

    async def asyncTearDown(self):
        await redis_client.flushdb()

    async def _release(self, credential, db, count=1):
        for _ in range(count):
            await CredentialSelector.release(str(credential.id), 0, db)

    async def test_same_session_keeps_bound_non_first_account(self):
        model = "gemini-3.5-flash-low"
        session = "conversation-sticky"
        async with AsyncSessionLocal() as db:
            selected, _ = await CredentialSelector.select_and_book(
                db, model, self.user.id, estimated_tokens=10, session_id=session
            )
            self.assertEqual(selected.id, self.first.id)
            key = get_session_binding_key("antigravity", self.user.id, session, model)
            self.assertEqual(await redis_client.get(key), str(self.first.id))

            # Make the bound account no longer the fill-first account. A real
            # binding, rather than UUID order, must still win.
            first_row = await db.get(Credential, self.first.id)
            second_row = await db.get(Credential, self.second.id)
            first_row.priority = 99
            second_row.priority = 1
            await db.commit()
            selected_again, _ = await CredentialSelector.select_and_book(
                db, model, self.user.id, estimated_tokens=10, session_id=session
            )
            self.assertEqual(selected_again.id, self.first.id)
            await self._release(self.first, db, 2)

    async def test_different_sessions_fill_first_until_capacity(self):
        model = "gemini-3.5-flash-low"
        async with AsyncSessionLocal() as db:
            first, _ = await CredentialSelector.select_and_book(
                db, model, self.user.id, estimated_tokens=10, session_id="one"
            )
            second, _ = await CredentialSelector.select_and_book(
                db, model, self.user.id, estimated_tokens=10, session_id="two"
            )
            self.assertEqual(first.id, self.first.id)
            self.assertEqual(second.id, self.first.id)

            first_row = await db.get(Credential, self.first.id)
            first_row.concurrency_limit = 2
            await db.commit()
            third, _ = await CredentialSelector.select_and_book(
                db, model, self.user.id, estimated_tokens=10, session_id="three"
            )
            self.assertEqual(third.id, self.second.id)
            await self._release(self.first, db, 2)
            await self._release(self.second, db)

    async def test_concurrent_first_turns_converge_on_one_binding(self):
        model = "gemini-3.5-flash-low"
        session = "concurrent-first-turn"

        async def select_once():
            async with AsyncSessionLocal() as db:
                return await CredentialSelector.select_and_book(
                    db, model, self.user.id, estimated_tokens=10, session_id=session
                )

        results = await asyncio.gather(select_once(), select_once())
        self.assertEqual(results[0][0].id, results[1][0].id)
        key = get_session_binding_key("antigravity", self.user.id, session, model)
        self.assertEqual(await redis_client.get(key), str(results[0][0].id))
        async with AsyncSessionLocal() as db:
            await self._release(results[0][0], db, 2)

    async def test_hard_quota_invalidates_only_that_session(self):
        model = "gemini-3.5-flash-low"
        async with AsyncSessionLocal() as db:
            first_row = await db.get(Credential, self.first.id)
            first_row.concurrency_limit = 1
            await db.commit()
            first, _ = await CredentialSelector.select_and_book(
                db, model, self.user.id, estimated_tokens=10, session_id="affected"
            )
            other, _ = await CredentialSelector.select_and_book(
                db, model, self.user.id, estimated_tokens=10, session_id="unaffected"
            )
            self.assertEqual(first.id, self.first.id)
            self.assertEqual(other.id, self.second.id)
            await self._release(first, db)
            await CredentialSelector.invalidate_binding(
                db, self.user.id, "affected", model, provider="antigravity"
            )
            first_row = await db.get(Credential, self.first.id)
            first_row.status = "exhausted"
            first_row.model_quotas = {"_group:gemini": 0.0, "_group:others": 0.0}
            await db.commit()

            failover, _ = await CredentialSelector.select_and_book(
                db, model, self.user.id, estimated_tokens=10, session_id="affected"
            )
            still_bound, _ = await CredentialSelector.select_and_book(
                db, model, self.user.id, estimated_tokens=10, session_id="unaffected"
            )
            self.assertEqual(failover.id, self.second.id)
            self.assertEqual(still_bound.id, self.second.id)
            await self._release(failover, db)
            await self._release(still_bound, db)

    async def test_rate_limit_sets_cooldown_and_advances_only_affected_binding(self):
        model = "gemini-3.5-flash-low"
        session = "rate-limited"
        async with AsyncSessionLocal() as db:
            selected, _ = await CredentialSelector.select_and_book(
                db, model, self.user.id, estimated_tokens=10, session_id=session
            )
            await self._release(selected, db)
            key = VirtualKey(
                user_id=self.user.id,
                hashed_key=uuid.uuid4().hex,
                name="test-key",
                status="active",
            )
            db.add(key)
            await db.flush()
            await _handle_credential_failure(
                db, key, selected, session, model, UpstreamErrorKind.RATE_LIMIT
            )
            refreshed = await db.get(Credential, selected.id)
            self.assertEqual(refreshed.status, "cooldown")
            self.assertIsNone(
                await redis_client.get(get_session_binding_key("antigravity", self.user.id, session, model))
            )
            failover, _ = await CredentialSelector.select_and_book(
                db, model, self.user.id, estimated_tokens=10, session_id=session
            )
            self.assertEqual(failover.id, self.second.id)
            await self._release(failover, db)

    async def test_explicit_session_required_without_headers(self):
        # Silent first-user hashing is gone; tip sticky is a separate fallback.
        first_payload = {"messages": [{"role": "user", "content": "remember this"}]}
        second_payload = {
            "messages": [
                {"role": "user", "content": "remember this"},
                {"role": "assistant", "content": "ok"},
                {"role": "user", "content": "continue"},
            ]
        }
        self.assertIsNone(get_session_id(first_payload, {}))
        self.assertIsNone(get_session_id(second_payload, {}))

    async def test_header_and_body_identity_variants(self):
        payload = {"messages": [{"role": "user", "content": "x"}]}
        self.assertEqual(get_session_id(payload, {"X-Session-ID": "h1"}), "h1")
        self.assertEqual(get_session_id(payload, {"x-session-affinity": "h2"}), "h2")
        self.assertEqual(get_session_id(payload, {"X-Levitate-Session-ID": "h3"}), "h3")
        self.assertEqual(get_session_id({**payload, "sessionId": "body"}, {}), "body")
        self.assertEqual(get_session_id({"conversation": {"id": "conv"}}, {}), "conv")
        self.assertEqual(get_session_id({"prompt_cache_key": "cache"}, {}), "cache")

    async def test_cooldown_reactivates_but_reauth_and_unknown_exhausted_do_not(self):
        model = "gemini-3.5-flash-low"
        async with AsyncSessionLocal() as db:
            first_row = await db.get(Credential, self.first.id)
            second_row = await db.get(Credential, self.second.id)
            first_row.status = "cooldown"
            first_row.reset_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            second_row.status = "reauth_required"
            await db.commit()
            selected, _ = await CredentialSelector.select_and_book(
                db, model, self.user.id, estimated_tokens=10, session_id="cooldown"
            )
            self.assertEqual(selected.id, self.first.id)
            first_row = await db.get(Credential, self.first.id)
            self.assertEqual(first_row.status, "active")
            await self._release(self.first, db)

            first_row.status = "exhausted"
            first_row.model_quotas = {}
            second_row.status = "reauth_required"
            await db.commit()
            selected, _ = await CredentialSelector.select_and_book(
                db, model, self.user.id, estimated_tokens=10, session_id="no-healthy-account"
            )
            self.assertIsNone(selected)


    async def test_client_error_does_not_change_status(self):
        model = "gemini-3.5-flash-low"
        session = "client-error"
        async with AsyncSessionLocal() as db:
            selected, _ = await CredentialSelector.select_and_book(
                db, model, self.user.id, estimated_tokens=10, session_id=session
            )
            await self._release(selected, db)
            key = VirtualKey(
                user_id=self.user.id,
                hashed_key=uuid.uuid4().hex,
                name="client-key",
                status="active",
            )
            db.add(key)
            await db.flush()
            await _handle_credential_failure(
                db, key, selected, session, model, UpstreamErrorKind.CLIENT
            )
            refreshed = await db.get(Credential, selected.id)
            self.assertEqual(refreshed.status, "active")
            # Binding stays so sticky dialogue is not disrupted by bad client payloads.
            self.assertEqual(
                await redis_client.get(get_session_binding_key("antigravity", self.user.id, session, model)),
                str(selected.id),
            )

    async def test_network_error_cools_down_not_exhausted(self):
        model = "gemini-3.5-flash-low"
        session = "network-error"
        async with AsyncSessionLocal() as db:
            selected, _ = await CredentialSelector.select_and_book(
                db, model, self.user.id, estimated_tokens=10, session_id=session
            )
            await self._release(selected, db)
            key = VirtualKey(
                user_id=self.user.id,
                hashed_key=uuid.uuid4().hex,
                name="net-key",
                status="active",
            )
            db.add(key)
            await db.flush()
            await _handle_credential_failure(
                db, key, selected, session, model, UpstreamErrorKind.TRANSIENT
            )
            refreshed = await db.get(Credential, selected.id)
            self.assertEqual(refreshed.status, "cooldown")
            self.assertNotEqual(refreshed.status, "exhausted")
            # Transient blips must keep dialogue sticky binding.
            self.assertEqual(
                await redis_client.get(get_session_binding_key("antigravity", self.user.id, session, model)),
                str(selected.id),
            )

    async def test_unknown_error_does_not_change_status_or_binding(self):
        model = "gemini-3.5-flash-low"
        session = "unknown-error"
        async with AsyncSessionLocal() as db:
            selected, _ = await CredentialSelector.select_and_book(
                db, model, self.user.id, estimated_tokens=10, session_id=session
            )
            await self._release(selected, db)
            key = VirtualKey(
                user_id=self.user.id,
                hashed_key=uuid.uuid4().hex,
                name="unknown-key",
                status="active",
            )
            db.add(key)
            await db.flush()
            await _handle_credential_failure(
                db, key, selected, session, model, UpstreamErrorKind.UNKNOWN
            )
            refreshed = await db.get(Credential, selected.id)
            self.assertEqual(refreshed.status, "active")
            self.assertEqual(
                await redis_client.get(get_session_binding_key("antigravity", self.user.id, session, model)),
                str(selected.id),
            )

    async def test_release_never_underflows_concurrency(self):
        async with AsyncSessionLocal() as db:
            await CredentialSelector.release(str(self.first.id), 0, db)
            key = f"gateway:credential:{self.first.id}:concurrency"
            self.assertEqual(await redis_client.get(key), "0")


if __name__ == "__main__":
    import unittest

    unittest.main()
