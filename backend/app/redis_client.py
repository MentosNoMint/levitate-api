import os
import asyncio
import logging

logger = logging.getLogger(__name__)

class FakeRedis:
    def __init__(self):
        self._data = {}
        self._expires = {}

    async def get(self, key):
        self._check_expiry(key)
        return self._data.get(key)

    async def set(self, key, value, ex=None, nx=False):
        self._check_expiry(key)
        if nx and key in self._data:
            return False
        self._data[key] = str(value)
        if ex:
            self._expires[key] = asyncio.get_event_loop().time() + ex
        elif key in self._expires:
            del self._expires[key]
        return True

    async def delete(self, key):
        if key in self._data:
            del self._data[key]
        if key in self._expires:
            del self._expires[key]

    async def incrby(self, key, amount):
        self._check_expiry(key)
        val = int(self._data.get(key, 0)) + amount
        self._data[key] = str(val)
        return val

    async def decrby(self, key, amount):
        self._check_expiry(key)
        val = int(self._data.get(key, 0)) - amount
        self._data[key] = str(val)
        return val

    async def expire(self, key, seconds):
        if key in self._data:
            self._expires[key] = asyncio.get_event_loop().time() + seconds
            return True
        return False

    def _check_expiry(self, key):
        if key in self._expires:
            if asyncio.get_event_loop().time() > self._expires[key]:
                del self._data[key]
                del self._expires[key]

class RedisClientProxy:
    def __init__(self, url):
        self.url = url
        self.real_client = None
        self.fake_client = FakeRedis()
        self.use_fake = False
        try:
            import redis.asyncio as aioredis
            self.real_client = aioredis.from_url(url, decode_responses=True)
        except Exception as e:
            logger.error("Failed to initialize real Redis client: %s. Using FakeRedis.", e)
            self.use_fake = True

    async def get(self, key):
        if not self.use_fake:
            try:
                return await self.real_client.get(key)
            except Exception as e:
                logger.warning("Transient Redis GET error: %s. Falling back to FakeRedis.", e)
        return await self.fake_client.get(key)

    async def set(self, key, value, ex=None, nx=False):
        if not self.use_fake:
            try:
                return await self.real_client.set(key, value, ex=ex, nx=nx)
            except Exception as e:
                logger.warning("Transient Redis SET error: %s. Falling back to FakeRedis.", e)
        return await self.fake_client.set(key, value, ex=ex, nx=nx)

    async def delete(self, key):
        if not self.use_fake:
            try:
                return await self.real_client.delete(key)
            except Exception as e:
                logger.warning("Transient Redis DELETE error: %s. Falling back to FakeRedis.", e)
        return await self.fake_client.delete(key)

    async def incrby(self, key, amount):
        if not self.use_fake:
            try:
                return await self.real_client.incrby(key, amount)
            except Exception as e:
                logger.warning("Transient Redis INCRBY error: %s. Falling back to FakeRedis.", e)
        return await self.fake_client.incrby(key, amount)

    async def decrby(self, key, amount):
        if not self.use_fake:
            try:
                return await self.real_client.decrby(key, amount)
            except Exception as e:
                logger.warning("Transient Redis DECRBY error: %s. Falling back to FakeRedis.", e)
        return await self.fake_client.decrby(key, amount)

    async def expire(self, key, seconds):
        if not self.use_fake:
            try:
                return await self.real_client.expire(key, seconds)
            except Exception as e:
                logger.warning("Transient Redis EXPIRE error: %s. Falling back to FakeRedis.", e)
        return await self.fake_client.expire(key, seconds)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = RedisClientProxy(REDIS_URL)
