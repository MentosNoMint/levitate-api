import os
import sys
import types
import unittest

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("REDIS_REQUIRED", "false")
os.environ.setdefault("ALLOW_MOCK_AUTH", "true")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_auth_run.db")

litellm = types.ModuleType("litellm")


async def _stub(*args, **kwargs):
    raise RuntimeError("litellm stub")


litellm.acompletion = _stub
litellm.aembedding = _stub
sys.modules["litellm"] = litellm

if __name__ == "__main__":
    result = unittest.main(module="test_auth", verbosity=2, exit=False)
    sys.exit(0 if result.result.wasSuccessful() else 1)
