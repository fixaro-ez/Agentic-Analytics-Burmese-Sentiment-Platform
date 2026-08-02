from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from app.models.brands import Brand, BrandEntity
from app.services import benchmark


class _Acquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _Pool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return _Acquire(self.connection)


class _QueueConnection:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    async def fetch(self, query, *args):
        self.calls.append((query, args))
        return self.results.pop(0)


def _brand(brand_id: int, fb_id: int, shop_ids: list[int]) -> Brand:
    return Brand(
        brand_id=brand_id,
        brand_name=f"Brand {brand_id}",
        facebook_entity=BrandEntity(
            entity_id=fb_id, entity_name=f"Page {brand_id}", platform="facebook"
        ),
        foodpanda_shops=[
            BrandEntity(
                entity_id=shop_id,
                entity_name=f"Shop {shop_id}",
                platform="foodpanda",
            )
            for shop_id in shop_ids
        ],
    )


class BenchmarkSelectionTests(unittest.TestCase):
    def test_benchmark_requires_exactly_two_different_brands(self):
        self.assertEqual(benchmark.validate_brand_selection(2, 9), (2, 9))
        with self.assertRaisesRegex(ValueError, "different"):
            benchmark.validate_brand_selection(2, 2)


class BenchmarkResponseTests(unittest.IsolatedAsyncioTestCase):
    async def test_minimum_guard_and_brand_branch_filter_propagation(self):
        brands = [_brand(1, 101, [201, 202]), _brand(2, 102, [203])]
        facebook_rows = [
            {"brand_id": 1, "post_count": 8, "weighted_engagement": 800.0},
            {"brand_id": 2, "post_count": 5, "weighted_engagement": 200.0},
        ]
        review_rows = [
            {
                "brand_id": 1,
                "review_count": 45,
                "observation_count": 45,
                "positive_count": 30,
                "negative_count": 10,
            },
            {
                "brand_id": 2,
                "review_count": 12,
                "observation_count": 12,
                "positive_count": 10,
                "negative_count": 1,
            },
        ]
        aspect_rows = [
            {
                "brand_id": 1,
                "aspect": "price_and_value",
                "observation_count": 20,
                "positive_count": 15,
                "negative_count": 3,
                "neutral_count": 2,
            },
            {
                "brand_id": 2,
                "aspect": "price_and_value",
                "observation_count": 8,
                "positive_count": 7,
                "negative_count": 0,
                "neutral_count": 1,
            },
        ]
        connection = _QueueConnection([facebook_rows, review_rows, aspect_rows])

        with (
            patch.object(benchmark, "list_brands", new=AsyncMock(return_value=brands)),
            patch.object(benchmark, "get_pool", return_value=_Pool(connection)),
        ):
            response = await benchmark.get_competitor_benchmark(
                1,
                2,
                brand_a_branch_ids=[202],
                brand_b_branch_ids=[203],
                days=90,
            )

        self.assertTrue(response.brands[0].eligible)
        self.assertFalse(response.brands[1].eligible)
        self.assertIsNone(response.brands[1].net_sentiment)
        self.assertEqual(response.meta.eligible_brand_count, 1)
        self.assertFalse(response.meta.sufficient_data)
        self.assertEqual(response.insights, [])
        self.assertEqual(response.brands[0].facebook_share, 0.8)
        self.assertEqual(response.brands[0].foodpanda_share, round(45 / 57, 4))
        self.assertEqual(
            connection.calls[0][1], ([1, 2], [101, 102], 90)
        )
        self.assertEqual(
            connection.calls[1][1], ([1, 2], [202, 203], 90)
        )
        self.assertEqual(
            response.meta.filters.brands[0].foodpanda_entity_ids, [202]
        )

    async def test_rejects_branch_not_mapped_to_brand(self):
        brands = [_brand(1, 101, [201]), _brand(2, 102, [202])]
        with (
            patch.object(benchmark, "list_brands", new=AsyncMock(return_value=brands)),
            self.assertRaisesRegex(ValueError, "not mapped"),
        ):
            await benchmark.get_competitor_benchmark(
                1, 2, brand_a_branch_ids=[999]
            )

