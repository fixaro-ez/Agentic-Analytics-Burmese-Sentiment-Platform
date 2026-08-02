from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class BrandEntity(BaseModel):
    entity_id: int
    entity_name: str
    platform: str


class Brand(BaseModel):
    brand_id: int
    brand_name: str
    facebook_entity: BrandEntity
    foodpanda_shops: list[BrandEntity]


class BrandListResponse(BaseModel):
    brands: list[Brand]
    total: int


class BrandWrite(BaseModel):
    brand_name: str = Field(min_length=1, max_length=255)
    facebook_entity_id: int = Field(gt=0)
    foodpanda_entity_ids: list[int] = Field(min_length=1)

    @field_validator("brand_name")
    @classmethod
    def normalize_brand_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Brand name is required.")
        return value

    @field_validator("foodpanda_entity_ids")
    @classmethod
    def unique_foodpanda_entities(cls, value: list[int]) -> list[int]:
        unique = list(dict.fromkeys(value))
        if any(entity_id <= 0 for entity_id in unique):
            raise ValueError("Foodpanda entity IDs must be positive integers.")
        return unique


class BrandCreate(BrandWrite):
    pass


class BrandUpdate(BrandWrite):
    pass
