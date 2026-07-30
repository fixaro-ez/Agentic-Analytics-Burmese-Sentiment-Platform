from __future__ import annotations

import asyncpg
from supabase import Client, create_client

from .config import settings

_pool: asyncpg.Pool | None = None
_supabase: Client | None = None
_supabase_admin: Client | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            host=settings.PG_HOST,
            port=settings.PG_PORT,
            user=settings.PG_USER,
            password=settings.PG_PASSWORD,
            database=settings.PG_DBNAME,
            min_size=2,
            max_size=10,
            # Supabase's transaction-mode pooler (port 6543) does not support
            # prepared statements. Disabling asyncpg's statement cache is also
            # safe for direct and session-mode connections.
            statement_cache_size=0,
        )
    return _pool


def get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        _supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
    return _supabase


def get_supabase_admin() -> Client:
    global _supabase_admin
    if _supabase_admin is None:
        _supabase_admin = create_client(
            settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY
        )
    return _supabase_admin


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
