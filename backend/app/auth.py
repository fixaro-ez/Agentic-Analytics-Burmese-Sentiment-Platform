from __future__ import annotations

import asyncio
import threading

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings
from .database import get_supabase

_bearer_scheme = HTTPBearer()
_claims_lock = threading.Lock()


class AuthUser:
    def __init__(self, user_id: str, email: str, role: str):
        self.user_id = user_id
        self.email = email
        self.role = role


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> AuthUser:
    token = credentials.credentials
    sb = get_supabase()

    def _verified_claims() -> dict:
        # supabase-py's auth client is synchronous. Keep its first JWKS fetch
        # off the event loop and serialize access to the shared client; after
        # that, ES256 verification uses the client's cached public key.
        with _claims_lock:
            response = sb.auth.get_claims(token)
        return response["claims"] if response is not None else {}

    try:
        claims = await asyncio.to_thread(_verified_claims)
        issuer = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1"
        audience = claims.get("aud")
        valid_audience = (
            audience == "authenticated"
            or isinstance(audience, list)
            and "authenticated" in audience
        )
        user_id = claims.get("sub")
        if claims.get("iss") != issuer or not valid_audience or not user_id:
            raise ValueError("Token claims do not match this Supabase project")

        return AuthUser(
            user_id=str(user_id),
            email=str(claims.get("email") or ""),
            role=str(claims.get("role") or "authenticated"),
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from None
