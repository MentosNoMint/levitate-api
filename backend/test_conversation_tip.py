import os
import sys
import uuid
from unittest import IsolatedAsyncioTestCase

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.api.routers.v1.chat import get_explicit_session_id, get_session_id
from app.core.constants import get_session_binding_key
from app.db.models import Base, Credential, User
from app.db.session import AsyncSessionLocal, engine
from app.redis_client import redis_client
from app.routing.conversation_tip import (
    accumulate_stream_delta,
    build_assistant_message_from_stream,
    extract_assistant_message,
    hash_messages,
    new_stream_assistant_state,
    remember_tip,
    resolve_session_id_from_tips,
    synthetic_tip_session_id,
)
from app.routing.selector import CredentialSelector


class TestConversationTip(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        redis_client.use_fake = True
        await redis_client.flushdb()
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        async with AsyncSessionLocal() as db:
            self.user = User(email=f"tip-{uuid.uuid4().hex}@example.test", role="user")
            db.add(self.user)
            await db.flush()
            self.cred = Credential(
                id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1"),
                user_id=self.user.id,
                name="tip-cred",
                type="antigravity",
                provider="google",
                status="active",
                priority=1,
                concurrency_limit=4,
                encrypted_secret="cipher",
                models=["gemini-3.5-flash-low"],
                model_quotas={"_group:gemini": 1.0, "_group:others": 1.0},
            )
            self.other = Credential(
                id=uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb2"),
                user_id=self.user.id,
                name="tip-other",
                type="antigravity",
                provider="google",
                status="active",
                priority=2,
                concurrency_limit=4,
                encrypted_secret="cipher",
                models=["gemini-3.5-flash-low"],
                model_quotas={"_group:gemini": 1.0, "_group:others": 1.0},
            )
            db.add_all([self.cred, self.other])
            await db.commit()

    async def asyncTearDown(self):
        await redis_client.flushdb()

    async def _release(self, credential, db, count=1):
        for _ in range(count):
            await CredentialSelector.release(str(credential.id), 0, db)

    def test_explicit_header_wins_over_messages(self):
        payload = {"messages": [{"role": "user", "content": "x"}], "session_id": "body-id"}
        self.assertEqual(get_explicit_session_id(payload, {"X-Session-ID": "header-id"}), "header-id")
        self.assertEqual(get_session_id(payload, {"X-Session-ID": "header-id"}), "header-id")
        self.assertEqual(get_session_id(payload, {}), "body-id")

    async def test_empty_messages_resolve_to_none(self):
        self.assertIsNone(await resolve_session_id_from_tips(self.user.id, "gemini-3.5-flash-low", []))
        self.assertIsNone(await resolve_session_id_from_tips(self.user.id, "gemini-3.5-flash-low", None))

    async def test_turn1_remember_then_turn2_parent_resolves_same_session(self):
        model = "gemini-3.5-flash-low"
        u1 = {"role": "user", "content": "hello"}
        a1 = {"role": "assistant", "content": "hi there"}
        u2 = {"role": "user", "content": "continue"}
        session = synthetic_tip_session_id([u1])

        # No tip yet → first turn creates synthetic id; parent of [U1] is empty.
        self.assertIsNone(await resolve_session_id_from_tips(self.user.id, model, [u1]))
        await remember_tip([u1], self.user.id, model, session, self.cred.id)
        await remember_tip([u1, a1], self.user.id, model, session, self.cred.id)

        # Retry of turn1 uses current tip.
        self.assertEqual(await resolve_session_id_from_tips(self.user.id, model, [u1]), session)
        # Turn2 uses parent tip hash([U1,A1]).
        resolved = await resolve_session_id_from_tips(self.user.id, model, [u1, a1, u2])
        self.assertEqual(resolved, session)

        await remember_tip([u1, a1, u2], self.user.id, model, session, self.cred.id)
        a2 = {"role": "assistant", "content": "sure"}
        await remember_tip([u1, a1, u2, a2], self.user.id, model, session, self.cred.id)
        self.assertEqual(
            await resolve_session_id_from_tips(self.user.id, model, [u1, a1, u2, a2, {"role": "user", "content": "more"}]),
            session,
        )

    async def test_edited_history_does_not_match(self):
        model = "gemini-3.5-flash-low"
        u1 = {"role": "user", "content": "hello"}
        a1 = {"role": "assistant", "content": "hi"}
        session = synthetic_tip_session_id([u1])
        await remember_tip([u1, a1], self.user.id, model, session, self.cred.id)

        edited = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "CHANGED"},
            {"role": "user", "content": "continue"},
        ]
        self.assertIsNone(await resolve_session_id_from_tips(self.user.id, model, edited))

    async def test_selector_sticky_with_synthetic_tip_session(self):
        model = "gemini-3.5-flash-low"
        messages = [{"role": "user", "content": "sticky please"}]
        session = synthetic_tip_session_id(messages)
        async with AsyncSessionLocal() as db:
            first, _ = await CredentialSelector.select_and_book(
                db, model, self.user.id, estimated_tokens=10, session_id=session
            )
            await self._release(first, db)
            second, _ = await CredentialSelector.select_and_book(
                db, model, self.user.id, estimated_tokens=10, session_id=session
            )
            self.assertEqual(first.id, second.id)
            self.assertEqual(
                await redis_client.get(get_session_binding_key("antigravity", self.user.id, session, model)),
                str(first.id),
            )
            await self._release(second, db)

    async def test_extract_and_stream_assistant_message_roundtrip(self):
        response = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "hello",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": "lookup", "arguments": "{\"q\":1}"},
                            }
                        ],
                    }
                }
            ]
        }
        extracted = extract_assistant_message(response)
        self.assertEqual(extracted["content"], "hello")
        self.assertEqual(extracted["tool_calls"][0]["function"]["name"], "lookup")

        state = new_stream_assistant_state()
        accumulate_stream_delta(
            state,
            {"choices": [{"delta": {"content": "hel"}}]},
        )
        accumulate_stream_delta(
            state,
            {"choices": [{"delta": {"content": "lo"}}]},
        )
        accumulate_stream_delta(
            state,
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {"name": "lookup", "arguments": ""},
                                }
                            ]
                        }
                    }
                ]
            },
        )
        accumulate_stream_delta(
            state,
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {"index": 0, "function": {"arguments": "{\"q\":1}"}}
                            ]
                        }
                    }
                ]
            },
        )
        built = build_assistant_message_from_stream(state)
        self.assertEqual(built["content"], "hello")
        self.assertEqual(built["tool_calls"][0]["function"]["arguments"], '{"q":1}')
        self.assertEqual(hash_messages([extracted]), hash_messages([built]))


if __name__ == "__main__":
    import unittest

    unittest.main()
