from __future__ import annotations

import json

from ..database import get_pool
from ..models.entities import Entity


async def get_all_entities() -> list[Entity]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT entity_id, entity_name, platform, platform_metadata "
            "FROM dim_entities ORDER BY entity_name"
        )
    return [
        Entity(
            entity_id=r["entity_id"],
            entity_name=r["entity_name"],
            platform=r["platform"],
            platform_metadata=json.loads(r["platform_metadata"]) if r["platform_metadata"] else None,
        )
        for r in rows
    ]


async def get_entity_by_id(entity_id: int) -> Entity | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT entity_id, entity_name, platform, platform_metadata "
            "FROM dim_entities WHERE entity_id = $1",
            entity_id,
        )
    if row is None:
        return None
    return Entity(
        entity_id=row["entity_id"],
        entity_name=row["entity_name"],
        platform=row["platform"],
        platform_metadata=json.loads(row["platform_metadata"]) if row["platform_metadata"] else None,
    )
