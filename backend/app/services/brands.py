from __future__ import annotations

from typing import Any

from ..database import get_pool
from ..models.brands import (
    Brand,
    BrandCreate,
    BrandEntity,
    BrandUpdate,
)

async def ensure_brand_schema() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dim_brands (
                brand_id SERIAL PRIMARY KEY,
                brand_name VARCHAR(255) NOT NULL UNIQUE,
                facebook_entity_id INT NOT NULL UNIQUE
                    REFERENCES dim_entities(entity_id),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS bridge_brand_foodpanda_shops (
                brand_id INT NOT NULL REFERENCES dim_brands(brand_id)
                    ON DELETE CASCADE,
                entity_id INT NOT NULL UNIQUE REFERENCES dim_entities(entity_id),
                PRIMARY KEY (brand_id, entity_id)
            );
            CREATE INDEX IF NOT EXISTS brand_foodpanda_brand_idx
                ON bridge_brand_foodpanda_shops (brand_id);
            """
        )


def _group_brand_rows(rows: list[Any]) -> list[Brand]:
    grouped: dict[int, dict[str, Any]] = {}
    for row in rows:
        brand_id = int(row["brand_id"])
        item = grouped.setdefault(
            brand_id,
            {
                "brand_id": brand_id,
                "brand_name": row["brand_name"],
                "facebook_entity": BrandEntity(
                    entity_id=int(row["facebook_entity_id"]),
                    entity_name=row["facebook_entity_name"],
                    platform=row["facebook_platform"],
                ),
                "foodpanda_shops": [],
            },
        )
        if row["foodpanda_entity_id"] is not None:
            item["foodpanda_shops"].append(
                BrandEntity(
                    entity_id=int(row["foodpanda_entity_id"]),
                    entity_name=row["foodpanda_entity_name"],
                    platform=row["foodpanda_platform"],
                )
            )
    return [Brand(**item) for item in grouped.values()]


async def list_brands() -> list[Brand]:
    await ensure_brand_schema()
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT b.brand_id, b.brand_name,
                   fb.entity_id AS facebook_entity_id,
                   fb.entity_name AS facebook_entity_name,
                   fb.platform AS facebook_platform,
                   fp.entity_id AS foodpanda_entity_id,
                   fp.entity_name AS foodpanda_entity_name,
                   fp.platform AS foodpanda_platform
            FROM dim_brands b
            JOIN dim_entities fb ON fb.entity_id = b.facebook_entity_id
            LEFT JOIN bridge_brand_foodpanda_shops bridge
                ON bridge.brand_id = b.brand_id
            LEFT JOIN dim_entities fp ON fp.entity_id = bridge.entity_id
            ORDER BY b.brand_name, fp.entity_name
            """
        )
    return _group_brand_rows(list(rows))


async def get_brand(brand_id: int) -> Brand | None:
    return next(
        (brand for brand in await list_brands() if brand.brand_id == brand_id),
        None,
    )


async def _validate_mapping(conn, facebook_id: int, shop_ids: list[int]) -> None:
    rows = await conn.fetch(
        "SELECT entity_id, platform FROM dim_entities WHERE entity_id = ANY($1::int[])",
        [facebook_id, *shop_ids],
    )
    platforms = {int(row["entity_id"]): str(row["platform"]).casefold() for row in rows}
    missing = [item for item in [facebook_id, *shop_ids] if item not in platforms]
    if missing:
        raise ValueError(f"Unknown entity IDs: {', '.join(map(str, missing))}.")
    if platforms[facebook_id] != "facebook":
        raise ValueError("The brand Facebook mapping must reference a Facebook entity.")
    invalid_shops = [
        entity_id for entity_id in shop_ids if platforms[entity_id] != "foodpanda"
    ]
    if invalid_shops:
        raise ValueError("Every branch mapping must reference a Foodpanda entity.")


async def create_brand(body: BrandCreate) -> Brand:
    await ensure_brand_schema()
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await _validate_mapping(
                    conn, body.facebook_entity_id, body.foodpanda_entity_ids
                )
                brand_id = await conn.fetchval(
                    """
                    INSERT INTO dim_brands (brand_name, facebook_entity_id)
                    VALUES ($1, $2)
                    RETURNING brand_id
                    """,
                    body.brand_name,
                    body.facebook_entity_id,
                )
                await conn.executemany(
                    """
                    INSERT INTO bridge_brand_foodpanda_shops (brand_id, entity_id)
                    VALUES ($1, $2)
                    """,
                    [(brand_id, entity_id) for entity_id in body.foodpanda_entity_ids],
                )
    except Exception as exc:
        if exc.__class__.__name__ == "UniqueViolationError":
            raise ValueError(
                "That brand name, Facebook page, or Foodpanda shop is already assigned."
            ) from exc
        raise
    brand = await get_brand(int(brand_id))
    if brand is None:
        raise RuntimeError("Brand mapping was created but could not be reloaded.")
    return brand


async def update_brand(brand_id: int, body: BrandUpdate) -> Brand:
    await ensure_brand_schema()
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                exists = await conn.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM dim_brands WHERE brand_id = $1)",
                    brand_id,
                )
                if not exists:
                    raise LookupError("Brand mapping not found.")
                await _validate_mapping(
                    conn, body.facebook_entity_id, body.foodpanda_entity_ids
                )
                await conn.execute(
                    """
                    UPDATE dim_brands
                    SET brand_name = $2, facebook_entity_id = $3, updated_at = NOW()
                    WHERE brand_id = $1
                    """,
                    brand_id,
                    body.brand_name,
                    body.facebook_entity_id,
                )
                await conn.execute(
                    "DELETE FROM bridge_brand_foodpanda_shops WHERE brand_id = $1",
                    brand_id,
                )
                await conn.executemany(
                    """
                    INSERT INTO bridge_brand_foodpanda_shops (brand_id, entity_id)
                    VALUES ($1, $2)
                    """,
                    [(brand_id, entity_id) for entity_id in body.foodpanda_entity_ids],
                )
    except Exception as exc:
        if exc.__class__.__name__ == "UniqueViolationError":
            raise ValueError(
                "That brand name, Facebook page, or Foodpanda shop is already assigned."
            ) from exc
        raise
    brand = await get_brand(brand_id)
    if brand is None:
        raise RuntimeError("Brand mapping was updated but could not be reloaded.")
    return brand


async def delete_brand(brand_id: int) -> bool:
    await ensure_brand_schema()
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM dim_brands WHERE brand_id = $1", brand_id
        )
    return result != "DELETE 0"

