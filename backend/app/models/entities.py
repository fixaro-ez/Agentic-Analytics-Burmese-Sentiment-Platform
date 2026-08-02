from __future__ import annotations

from pydantic import BaseModel


class Entity(BaseModel):
    entity_id: int
    entity_name: str
    platform: str
    platform_metadata: dict | None = None


class CreateEntity(BaseModel):
    entity_name: str
    platform: str
    platform_metadata: dict | None = None


class EntityListResponse(BaseModel):
    entities: list[Entity]
    total: int
