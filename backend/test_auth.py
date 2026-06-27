import os
import sys
import asyncio

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from unittest import IsolatedAsyncioTestCase
from fastapi.testclient import TestClient
from app.main import app
from app.services import auth_service
from app.redis_client import redis_client
from app.db.session import engine
from app.db.models import Base

class TestFlexibleAuth(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Programmatically create database tables for sqlite test
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            
        self.client = TestClient(app)
        # Ensure auth configurations are set for test
        auth_service.AUTH_METHOD = "both"
        auth_service.ADMIN_TOKEN = "test-secret-token-12345"
        # Clear rate limits for testing IP
        await redis_client.delete("rate_limit:login:testclient")

    async def test_get_config(self):
        response = self.client.get("/admin/auth/config")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("auth_method", data)
        self.assertEqual(data["auth_method"], "both")

    async def test_token_login_success(self):
        response = self.client.post(
            "/admin/auth/token-login",
            json={"token": "test-secret-token-12345"}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("auth_token", data)

    async def test_token_login_invalid(self):
        response = self.client.post(
            "/admin/auth/token-login",
            json={"token": "wrong-token"}
        )
        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertEqual(data["detail"], "Invalid admin token.")

    async def test_token_login_rate_limiting(self):
        # We make 5 failed attempts
        for i in range(5):
            response = self.client.post(
                "/admin/auth/token-login",
                json={"token": "wrong-token"}
            )
            self.assertEqual(response.status_code, 401)

        # 6th attempt should be rate limited (429)
        response = self.client.post(
            "/admin/auth/token-login",
            json={"token": "wrong-token"}
        )
        self.assertEqual(response.status_code, 429)
        self.assertIn("Too many login attempts", response.json()["detail"])

if __name__ == "__main__":
    import unittest
    unittest.main()
