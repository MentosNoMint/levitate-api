"""
Regression tests for the 2026-08-02 bugfix batch.
Runs without litellm / docker: stubs heavy deps, uses FakeRedis + sqlite.
"""
from __future__ import annotations

import os
import sys
import types
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, TestCase

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
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_fixes.db")
os.environ.pop("ENCRYPTION_KEY", None)

from app.core.error_classifier import classify_upstream_error
from app.core.constants import get_model_quota_group, get_credential_cooldown_key, get_vkey_tokens_key, get_vkey_rpm_key, map_model_name, build_antigravity_models_from_available, resolve_antigravity_upstream_model, DEFAULT_ANTIGRAVITY_MODELS
from app.redis_client import FakeRedis, RedisClientProxy, redis_client
from app.db.models import Base, Credential, User
from app.db.session import engine, AsyncSessionLocal
from app.routing.selector import CredentialSelector
from app.providers.byo_upstream import BYOUpstreamProvider
from app.services import usage_service, auth_service
from app.api.schemas.virtual_key import VirtualKeyCreate
from app.api.schemas.credential import CredentialCreate
from app.api.routers.v1.chat import ImageGenerationRequest
from pydantic import ValidationError
from fastapi import HTTPException


class TestErrorClassifier(TestCase):
    def test_bare_quota_is_hard_quota(self):
        is_rl, is_q = classify_upstream_error(Exception("You exceeded your current quota"))
        self.assertFalse(is_rl)
        self.assertTrue(is_q)

    def test_rate_limit_text(self):
        is_rl, is_q = classify_upstream_error(Exception("429 Too Many Requests / rate limit"))
        self.assertTrue(is_rl)
        self.assertFalse(is_q)

    def test_billing_is_quota(self):
        is_rl, is_q = classify_upstream_error(Exception("billing hard limit reached"))
        self.assertFalse(is_rl)
        self.assertTrue(is_q)

    def test_status_code_429(self):
        err = Exception("upstream failed")
        err.status_code = 429
        is_rl, is_q = classify_upstream_error(err)
        self.assertTrue(is_rl)
        self.assertFalse(is_q)


class TestModelGroups(TestCase):
    def test_gemini_group(self):
        self.assertEqual(get_model_quota_group("gemini-3.5-flash-low"), "gemini")
        self.assertEqual(get_model_quota_group("gemini-3.6-flash-high"), "gemini")

    def test_others_group(self):
        self.assertEqual(get_model_quota_group("claude-sonnet-4-6-thinking"), "others")
        self.assertEqual(get_model_quota_group("gpt-oss-120b-medium"), "others")


class TestDynamicAntigravityModels(TestCase):
    def test_map_model_keeps_gemini_36(self):
        self.assertEqual(map_model_name("gemini-3.6-flash-high"), "gemini-3.6-flash-high")
        self.assertEqual(map_model_name("gemini-3.6-flash"), "gemini-3.6-flash")

    def test_map_model_legacy_aliases(self):
        self.assertEqual(map_model_name("gemini-3.5-flash-medium"), "gemini-3.5-flash-medium")
        self.assertEqual(map_model_name("claude-sonnet-4-6-thinking"), "claude-sonnet-4-6-thinking")

    def test_resolve_upstream(self):
        self.assertEqual(resolve_antigravity_upstream_model("gemini-3.6-flash"), "gemini-3.6-flash-high")
        self.assertEqual(resolve_antigravity_upstream_model("gemini-3.5-flash-high"), "gemini-3-flash-agent")
        self.assertEqual(resolve_antigravity_upstream_model("brand-new-model-xyz"), "brand-new-model-xyz")

    def test_build_from_available_includes_new_and_aliases(self):
        available = {
            "gemini-3.6-flash-high",
            "gemini-3.5-flash-extra-low",
            "claude-sonnet-4-6",
        }
        built = build_antigravity_models_from_available(available)
        self.assertIn("gemini-3.6-flash-high", built)
        self.assertIn("gemini-3.5-flash-extra-low", built)
        self.assertIn("gemini-3.5-flash-medium", built)  # legacy alias -> extra-low
        self.assertIn("claude-sonnet-4-6", built)
        self.assertIn("claude-sonnet-4-6-thinking", built)
        self.assertNotIn("Gemini 3.6 Flash", built)  # display names excluded

    def test_build_empty_falls_back_default(self):
        self.assertEqual(build_antigravity_models_from_available([]), DEFAULT_ANTIGRAVITY_MODELS)


class TestSchemas(TestCase):
    def test_negative_rpm_rejected(self):
        with self.assertRaises(ValidationError):
            VirtualKeyCreate(name="x", rpm_limit=-1)

    def test_negative_quota_rejected(self):
        with self.assertRaises(ValidationError):
            CredentialCreate(
                type="byo_upstream",
                name="x",
                provider="openai",
                secret="sk-test",
                quota_total_tokens=-5,
            )

    def test_images_n_bounds(self):
        with self.assertRaises(ValidationError):
            ImageGenerationRequest(prompt="hi", n=0)
        with self.assertRaises(ValidationError):
            ImageGenerationRequest(prompt="hi", n=11)
        ok = ImageGenerationRequest(prompt="hi", n=2)
        self.assertEqual(ok.n, 2)


class TestByoPrefix(TestCase):
    def test_no_double_prefix(self):
        cred = types.SimpleNamespace(provider="openai", encrypted_secret="x", base_url=None)
        provider = BYOUpstreamProvider(cred)
        self.assertEqual(provider._prefixed_model("gpt-4o"), "openai/gpt-4o")
        self.assertEqual(provider._prefixed_model("openai/gpt-4o"), "openai/gpt-4o")


class TestAntigravityQuotaBlocked(TestCase):
    def test_per_model_overrides_group(self):
        cred = types.SimpleNamespace(
            type="antigravity",
            status="active",
            model_quotas={
                "_group:others": 0.0,
                "claude-sonnet-4-6-thinking": 0.5,
            }
        )
        self.assertTrue(CredentialSelector._model_quota_available(cred, "claude-sonnet-4-6-thinking"))
        self.assertFalse(CredentialSelector._model_quota_available(cred, "claude-opus-4-6-thinking"))

    def test_group_fallback_when_model_missing(self):
        cred = types.SimpleNamespace(type="antigravity", status="active", model_quotas={"_group:gemini": 0.0})
        self.assertFalse(CredentialSelector._model_quota_available(cred, "gemini-3.5-flash-low"))
        cred2 = types.SimpleNamespace(type="antigravity", status="active", model_quotas={"_group:gemini": 0.3})
        self.assertTrue(CredentialSelector._model_quota_available(cred2, "gemini-3.5-flash-low"))


class TestFakeRedisTTL(IsolatedAsyncioTestCase):
    async def test_ttl_and_expire(self):
        fake = FakeRedis()
        await fake.set("k", "1")
        self.assertEqual(await fake.ttl("k"), -1)
        await fake.expire("k", 60)
        ttl = await fake.ttl("k")
        self.assertGreater(ttl, 0)
        self.assertLessEqual(ttl, 60)
        self.assertEqual(await fake.ttl("missing"), -2)

    async def test_redis_required_raises(self):
        proxy = RedisClientProxy.__new__(RedisClientProxy)
        proxy.url = "redis://localhost:6379/0"
        proxy.fake_client = FakeRedis()
        proxy.use_fake = False
        proxy.required = True

        class Boom:
            async def get(self, key):
                raise ConnectionError("down")

        proxy.real_client = Boom()
        with self.assertRaises(ConnectionError):
            await proxy.get("x")


class TestUsageServiceLimits(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        redis_client.use_fake = True
        redis_client.fake_client = FakeRedis()

    async def test_others_group_allows_claude(self):
        vkey = types.SimpleNamespace(
            id=uuid.uuid4(),
            allowed_model_groups=["others"],
            rpm_limit=None,
            monthly_token_limit=None,
        )
        await usage_service.check_key_limits(vkey, "claude-sonnet-4-6-thinking")

    async def test_others_group_rejects_gemini(self):
        vkey = types.SimpleNamespace(
            id=uuid.uuid4(),
            allowed_model_groups=["others"],
            rpm_limit=None,
            monthly_token_limit=None,
        )
        with self.assertRaises(HTTPException) as ctx:
            await usage_service.check_key_limits(vkey, "gemini-3.5-flash-low")
        self.assertEqual(ctx.exception.status_code, 403)

    async def test_monthly_tokens_get_ttl(self):
        vid = uuid.uuid4()
        await usage_service.incr_vkey_monthly_tokens(vid, 100)
        key = get_vkey_tokens_key(vid)
        used = await redis_client.get(key)
        self.assertEqual(int(used), 100)
        ttl = await redis_client.ttl(key)
        self.assertGreater(ttl, 0)

    async def test_rpm_ttl_self_heals(self):
        vkey = types.SimpleNamespace(
            id=uuid.uuid4(),
            allowed_model_groups=None,
            rpm_limit=10,
            monthly_token_limit=None,
        )
        await usage_service.check_key_limits(vkey, "gemini-3.5-flash-low")
        rpm_key = get_vkey_rpm_key(vkey.id)
        await redis_client.fake_client.set(rpm_key, await redis_client.get(rpm_key))
        self.assertEqual(await redis_client.ttl(rpm_key), -1)
        await usage_service.check_key_limits(vkey, "gemini-3.5-flash-low")
        self.assertGreater(await redis_client.ttl(rpm_key), 0)


class TestSelectorReleaseAndReset(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        redis_client.use_fake = True
        redis_client.fake_client = FakeRedis()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        self.user_id = uuid.uuid4()
        async with AsyncSessionLocal() as db:
            db.add(User(id=self.user_id, email="test@example.com", role="admin"))
            await db.commit()

    async def test_release_reseeds_from_db_when_redis_missing(self):
        cred_id = uuid.uuid4()
        async with AsyncSessionLocal() as db:
            db.add(
                Credential(
                    id=cred_id,
                    user_id=self.user_id,
                    type="byo_upstream",
                    name="byo2",
                    provider="openai",
                    encrypted_secret="enc",
                    models=["gpt-4o"],
                    quota_total_tokens=1_000_000,
                    quota_used_tokens=995_000,
                    status="active",
                )
            )
            await db.commit()

        async with AsyncSessionLocal() as db:
            await CredentialSelector.release(str(cred_id), 500, db)
            cred = await db.get(Credential, cred_id)
            self.assertEqual(cred.quota_used_tokens, 995_500)

    async def test_check_and_reset_quota_no_drift_and_revive(self):
        cred_id = uuid.uuid4()
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        async with AsyncSessionLocal() as db:
            cred = Credential(
                id=cred_id,
                user_id=self.user_id,
                type="byo_upstream",
                name="byo3",
                provider="openai",
                encrypted_secret="enc",
                models=["gpt-4o"],
                quota_total_tokens=1000,
                quota_used_tokens=1000,
                quota_window=3600,
                reset_at=past,
                status="exhausted",
            )
            db.add(cred)
            await db.commit()

        async with AsyncSessionLocal() as db:
            cred = await db.get(Credential, cred_id)
            await CredentialSelector.check_and_reset_quota(db, cred)
            await db.refresh(cred)
            self.assertEqual(cred.quota_used_tokens, 0)
            self.assertEqual(cred.status, "active")
            expected = past + timedelta(seconds=3600)
            while expected <= datetime.now(timezone.utc):
                expected += timedelta(seconds=3600)
            got = cred.reset_at
            if got.tzinfo is None:
                got = got.replace(tzinfo=timezone.utc)
            self.assertEqual(got.replace(microsecond=0), expected.replace(microsecond=0))

    async def test_embeddings_skip_antigravity(self):
        async with AsyncSessionLocal() as db:
            db.add(
                Credential(
                    id=uuid.uuid4(),
                    user_id=self.user_id,
                    type="antigravity",
                    name="ag",
                    provider="Gemini",
                    encrypted_secret="enc",
                    models=["gemini-3.5-flash-low", "claude-sonnet-4-6-thinking"],
                    status="active",
                )
            )
            await db.commit()

        async with AsyncSessionLocal() as db:
            creds, _ = await CredentialSelector.get_active_credentials(
                db, "text-embedding-3-small", self.user_id
            )
            self.assertEqual(creds, [])


class TestAuthRateLimit(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        redis_client.use_fake = True
        redis_client.fake_client = FakeRedis()
        auth_service.AUTH_METHOD = "both"
        auth_service.ADMIN_TOKEN = "good-token-12345678"
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def test_failed_attempts_counted_valid_not_blocked_early(self):
        async with AsyncSessionLocal() as db:
            for _ in range(4):
                with self.assertRaises(HTTPException) as ctx:
                    await auth_service.handle_token_login("bad", "1.2.3.4", db)
                self.assertEqual(ctx.exception.status_code, 401)

            token = await auth_service.handle_token_login("good-token-12345678", "1.2.3.4", db)
            self.assertTrue(token)

    async def test_fifth_failure_locks(self):
        async with AsyncSessionLocal() as db:
            for _ in range(5):
                with self.assertRaises(HTTPException):
                    await auth_service.handle_token_login("bad", "9.9.9.9", db)
            with self.assertRaises(HTTPException) as ctx:
                await auth_service.handle_token_login("good-token-12345678", "9.9.9.9", db)
            self.assertEqual(ctx.exception.status_code, 429)


class TestCooldownKey(TestCase):
    def test_cooldown_key_format(self):
        cid = uuid.uuid4()
        self.assertEqual(
            get_credential_cooldown_key(cid),
            f"gateway:credential:{cid}:cooldown",
        )


class TestWorkerCooldownLogic(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        redis_client.use_fake = True
        redis_client.fake_client = FakeRedis()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        self.user_id = uuid.uuid4()
        async with AsyncSessionLocal() as db:
            db.add(User(id=self.user_id, email="worker@example.com", role="admin"))
            await db.commit()

    async def test_cooldown_expiry_does_not_wipe_quota(self):
        from sqlalchemy import select

        cred_id = uuid.uuid4()
        async with AsyncSessionLocal() as db:
            db.add(
                Credential(
                    id=cred_id,
                    user_id=self.user_id,
                    type="byo_upstream",
                    name="byo-cd",
                    provider="openai",
                    encrypted_secret="enc",
                    models=["gpt-4o"],
                    quota_total_tokens=100_000,
                    quota_used_tokens=99_000,
                    quota_window=86400,
                    reset_at=datetime.now(timezone.utc) + timedelta(hours=12),
                    status="cooldown",
                )
            )
            await db.commit()

        async with AsyncSessionLocal() as db:
            now = datetime.now(timezone.utc)
            stmt = select(Credential).where(
                ((Credential.reset_at <= now) & (Credential.type != "antigravity"))
                | (Credential.status == "cooldown")
            )
            result = await db.execute(stmt)
            credentials = result.scalars().all()
            self.assertEqual(len(credentials), 1)
            cred = credentials[0]

            cooldown_key = get_credential_cooldown_key(cred.id)
            self.assertIsNone(await redis_client.get(cooldown_key))
            if cred.status == "cooldown":
                cred.status = "active"

            reset_at = cred.reset_at
            if reset_at.tzinfo is None:
                reset_at = reset_at.replace(tzinfo=timezone.utc)
            self.assertTrue(now < reset_at)
            await db.commit()
            await db.refresh(cred)
            self.assertEqual(cred.status, "active")
            self.assertEqual(cred.quota_used_tokens, 99_000)


if __name__ == "__main__":
    import unittest
    unittest.main(verbosity=2)
