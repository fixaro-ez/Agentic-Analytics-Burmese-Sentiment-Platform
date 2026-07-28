from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..auth import AuthUser, get_current_user
from ..database import get_pool
from ..models.entities import CreateEntity, Entity, EntityListResponse
from ..services.entities import get_all_entities, get_entity_by_id

router = APIRouter()


@router.get("", response_model=EntityListResponse)
async def list_entities(user: AuthUser = Depends(get_current_user)):
    entities = await get_all_entities()
    return EntityListResponse(entities=entities, total=len(entities))


@router.get("/{entity_id}", response_model=Entity)
async def get_entity(entity_id: int, user: AuthUser = Depends(get_current_user)):
    entity = await get_entity_by_id(entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity


@router.post("", response_model=Entity, status_code=201)
async def create_entity(
    body: CreateEntity,
    user: AuthUser = Depends(get_current_user),
):
    import json

    pool = await get_pool()
    async with pool.acquire() as conn:
        metadata_json = json.dumps(body.platform_metadata) if body.platform_metadata else None
        row = await conn.fetchrow(
            "INSERT INTO dim_entities (entity_name, platform, platform_metadata) "
            "VALUES ($1, $2, $3::jsonb) "
            "ON CONFLICT (entity_name, platform) DO UPDATE SET "
            "  platform_metadata = COALESCE(EXCLUDED.platform_metadata, dim_entities.platform_metadata) "
            "RETURNING entity_id, entity_name, platform, platform_metadata",
            body.entity_name,
            body.platform,
            metadata_json,
        )

    return Entity(
        entity_id=row["entity_id"],
        entity_name=row["entity_name"],
        platform=row["platform"],
        platform_metadata=row["platform_metadata"],
    )
