import asyncio
import logging
import os
import threading

logger = logging.getLogger(__name__)


class FakeRedis:
    """Small in-process fallback implementing the Redis operations we use."""

    def __init__(self):
        self._data = {}
        self._expires = {}
        self._lock = threading.RLock()

    async def get(self, key):
        with self._lock:
            self._check_expiry(key)
            return self._data.get(key)

    async def set(self, key, value, ex=None, nx=False):
        with self._lock:
            self._check_expiry(key)
            if nx and key in self._data:
                return False
            self._data[key] = str(value)
            if ex:
                self._expires[key] = asyncio.get_event_loop().time() + ex
            else:
                self._expires.pop(key, None)
            return True

    async def delete(self, key):
        with self._lock:
            existed = key in self._data
            self._data.pop(key, None)
            self._expires.pop(key, None)
            return int(existed)

    async def compare_delete(self, key, expected):
        with self._lock:
            self._check_expiry(key)
            if self._data.get(key) != str(expected):
                return False
            self._data.pop(key, None)
            self._expires.pop(key, None)
            return True

    async def incrby(self, key, amount):
        with self._lock:
            self._check_expiry(key)
            value = int(self._data.get(key, 0)) + amount
            self._data[key] = str(value)
            return value

    async def decrby(self, key, amount):
        with self._lock:
            self._check_expiry(key)
            value = int(self._data.get(key, 0)) - amount
            self._data[key] = str(value)
            return value

    async def decrby_nonnegative(self, key, amount):
        with self._lock:
            self._check_expiry(key)
            value = max(0, int(self._data.get(key, 0)) - amount)
            self._data[key] = str(value)
            return value

    async def expire(self, key, seconds):
        with self._lock:
            self._check_expiry(key)
            if key not in self._data:
                return False
            self._expires[key] = asyncio.get_event_loop().time() + seconds
            return True

    async def ttl(self, key):
        with self._lock:
            self._check_expiry(key)
            if key not in self._data:
                return -2
            if key not in self._expires:
                return -1
            return max(0, int(self._expires[key] - asyncio.get_event_loop().time()))

    async def flushdb(self):
        with self._lock:
            self._data.clear()
            self._expires.clear()

    def _check_expiry(self, key):
        expiry = self._expires.get(key)
        if expiry is not None and asyncio.get_event_loop().time() > expiry:
            self._data.pop(key, None)
            self._expires.pop(key, None)


class RedisClientProxy:
    def __init__(self, url):
        self.url = url
        self.real_client = None
        self.fake_client = FakeRedis()
        self.use_fake = False
        # When REDIS_REQUIRED=true, Redis outages raise instead of silently
        # falling back to per-process FakeRedis (which bypasses every rate/quota
        # limit and corrupts usage counters in multi-process deployments).
        self.required = os.getenv("REDIS_REQUIRED", "false").strip().lower() in ("1", "true", "yes", "on")
        try:
            import redis.asyncio as aioredis
            self.real_client = aioredis.from_url(url, decode_responses=True)
        except Exception as e:
            if self.required:
                raise
            logger.error("Failed to initialize real Redis client: %s. Using FakeRedis.", e)
            self.use_fake = True

    def _fallback_or_raise(self, op: str, err: Exception):
        if self.required:
            raise err
        logger.warning("Transient Redis %s error: %s. Falling back to FakeRedis.", op, err)

    async def get(self, key):
        if not self.use_fake:
            try:
                return await self.real_client.get(key)
            except Exception as e:
                self._fallback_or_raise("GET", e)
        return await self.fake_client.get(key)

    async def set(self, key, value, ex=None, nx=False):
        if not self.use_fake:
            try:
                return await self.real_client.set(key, value, ex=ex, nx=nx)
            except Exception as e:
                self._fallback_or_raise("SET", e)
        return await self.fake_client.set(key, value, ex=ex, nx=nx)

    async def delete(self, key):
        if not self.use_fake:
            try:
                return await self.real_client.delete(key)
            except Exception as e:
                self._fallback_or_raise("DELETE", e)
        return await self.fake_client.delete(key)

    async def compare_delete(self, key, expected):
        """Delete a lock only if it is still owned by the caller."""
        if not self.use_fake:
            try:
                script = (
                    "if redis.call('get', KEYS[1]) == ARGV[1] "
                    "then return redis.call('del', KEYS[1]) else return 0 end"
                )
                return bool(await self.real_client.eval(script, 1, key, str(expected)))
            except Exception as e:
                self._fallback_or_raise("COMPARE_DELETE", e)
        return await self.fake_client.compare_delete(key, expected)

    async def incrby(self, key, amount):
        if not self.use_fake:
            try:
                return await self.real_client.incrby(key, amount)
            except Exception as e:
                self._fallback_or_raise("INCRBY", e)
        return await self.fake_client.incrby(key, amount)

    async def decrby(self, key, amount):
        if not self.use_fake:
            try:
                return await self.real_client.decrby(key, amount)
            except Exception as e:
                self._fallback_or_raise("DECRBY", e)
        return await self.fake_client.decrby(key, amount)

    async def decrby_nonnegative(self, key, amount):
        if not self.use_fake:
            try:
                script = (
                    "local v = tonumber(redis.call('get', KEYS[1]) or '0') "
                    "v = math.max(0, v - tonumber(ARGV[1])) "
                    "redis.call('set', KEYS[1], v) return v"
                )
                return int(await self.real_client.eval(script, 1, key, amount))
            except Exception as e:
                self._fallback_or_raise("DECRBY_NONNEGATIVE", e)
        return await self.fake_client.decrby_nonnegative(key, amount)

    async def expire(self, key, seconds):
        if not self.use_fake:
            try:
                return await self.real_client.expire(key, seconds)
            except Exception as e:
                self._fallback_or_raise("EXPIRE", e)
        return await self.fake_client.expire(key, seconds)

    async def ttl(self, key):
        if not self.use_fake:
            try:
                return await self.real_client.ttl(key)
            except Exception as e:
                self._fallback_or_raise("TTL", e)
        return await self.fake_client.ttl(key)

    async def flushdb(self):
        if not self.use_fake:
            try:
                return await self.real_client.flushdb()
            except Exception as e:
                self._fallback_or_raise("FLUSHDB", e)
        return await self.fake_client.flushdb()


REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = RedisClientProxy(REDIS_URL)
