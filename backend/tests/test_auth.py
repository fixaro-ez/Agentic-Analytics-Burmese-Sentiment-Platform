from __future__ import annotations

import asyncio
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.auth import get_current_user
from app.config import settings


class _FakeAuth:
    def __init__(self, claims: dict, delay: float = 0):
        self.claims = claims
        self.delay = delay

    def get_claims(self, token: str):
        if self.delay:
            time.sleep(self.delay)
        return {"claims": self.claims}


class AuthVerificationTests(unittest.IsolatedAsyncioTestCase):
    def _claims(self, **overrides):
        claims = {
            "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
            "aud": "authenticated",
            "sub": "user-123",
            "email": "analyst@example.com",
            "role": "authenticated",
        }
        claims.update(overrides)
        return claims

    async def test_verified_claims_create_auth_user(self):
        client = SimpleNamespace(auth=_FakeAuth(self._claims()))
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="signed-token"
        )
        with patch("app.auth.get_supabase", return_value=client):
            user = await get_current_user(credentials)

        self.assertEqual(user.user_id, "user-123")
        self.assertEqual(user.email, "analyst@example.com")
        self.assertEqual(user.role, "authenticated")

    async def test_rejects_claims_from_another_project(self):
        client = SimpleNamespace(
            auth=_FakeAuth(self._claims(iss="https://other.supabase.co/auth/v1"))
        )
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="signed-token"
        )
        with (
            patch("app.auth.get_supabase", return_value=client),
            self.assertRaises(HTTPException) as raised,
        ):
            await get_current_user(credentials)

        self.assertEqual(raised.exception.status_code, 401)

    async def test_sync_verification_does_not_block_event_loop(self):
        client = SimpleNamespace(auth=_FakeAuth(self._claims(), delay=0.05))
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="signed-token"
        )
        with patch("app.auth.get_supabase", return_value=client):
            task = asyncio.create_task(get_current_user(credentials))
            started = time.perf_counter()
            await asyncio.sleep(0.01)
            elapsed = time.perf_counter() - started
            user = await task

        self.assertLess(elapsed, 0.04)
        self.assertEqual(user.user_id, "user-123")


if __name__ == "__main__":
    unittest.main()
