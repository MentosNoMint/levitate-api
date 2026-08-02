import asyncio
from uuid import UUID
import httpx
import json
from app.main import app
from app.api.routers.v1.chat import verify_key
from app.db.models import VirtualKey

async def mock_verify_key():
    return VirtualKey(
        id=UUID("00000000-0000-0000-0000-000000000000"),
        user_id=UUID("261000a1-45fa-442f-baf1-1fe36a1bc896"),
        hashed_key="mocked",
        name="Mock Key",
        status="active"
    )

app.dependency_overrides[verify_key] = mock_verify_key

async def test_chat_with_reasoning():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        payload = {
            "model": "claude-opus-4-6-thinking",
            "messages": [{"role": "user", "content": "hello"}],
            "reasoning_effort": "high"
        }
        print("Testing chat completion with reasoning_effort...")
        headers = {"Authorization": "Bearer mocked"}
        resp = await client.post("/v1/chat/completions", json=payload, headers=headers)
        print(f"Status: {resp.status_code}")
        print("Response:", resp.text)

if __name__ == "__main__":
    asyncio.run(test_chat_with_reasoning())
