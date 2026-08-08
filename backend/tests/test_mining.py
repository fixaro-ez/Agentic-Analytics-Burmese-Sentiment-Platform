from __future__ import annotations

import unittest
from unittest.mock import patch

from app.models.mining import AssociationRuleResponse, EntityClusterResponse
from app.routers.mining import _parse_entity_ids
from app.services import mining


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


class _Connection:
    def __init__(self, rows):
        self.rows = rows
        self.query = ""
        self.args = ()

    async def fetch(self, query, *args):
        self.query = query
        self.args = args
        return self.rows


class MiningFilterTests(unittest.IsolatedAsyncioTestCase):
    async def test_association_rules_apply_filters_and_include_samples(self):
        connection = _Connection(
            [
                {
                    "feedback_id": "review-1",
                    "entity_id": 7,
                    "entity_name": "Example",
                    "raw_text": "Late delivery and poor support",
                    "feedback_timestamp": "2026-07-31 10:00:00",
                    "aspects": ["fulfillment_and_speed", "staff_and_service"],
                },
                {
                    "feedback_id": "review-2",
                    "entity_id": 7,
                    "entity_name": "Example",
                    "raw_text": "Delivery was late",
                    "feedback_timestamp": "2026-07-30 10:00:00",
                    "aspects": ["fulfillment_and_speed"],
                },
            ]
        )
        with patch.object(mining, "get_pool", return_value=_Pool(connection)):
            result = await mining.get_association_rule_analysis(
                entity_ids=[7, 9],
                days=30,
                min_support=0.4,
                min_confidence=0.4,
            )

        self.assertIn("r.entity_id = ANY($1::int[])", connection.query)
        self.assertIn(
            "r.feedback_timestamp >= CURRENT_DATE - ($2 * INTERVAL '1 day')",
            connection.query,
        )
        self.assertEqual(connection.args, ([7, 9], 30))
        self.assertEqual(result["meta"]["total_transactions"], 2)
        self.assertFalse(result["meta"]["sufficient_data"])
        self.assertEqual(len(result["rules"]), 2)
        support_to_delivery = next(
            rule
            for rule in result["rules"]
            if rule["antecedent"] == ["staff_and_service"]
        )
        self.assertEqual(support_to_delivery["confidence"], 1.0)
        self.assertEqual(support_to_delivery["cooccurrence_count"], 1)
        self.assertEqual(
            support_to_delivery["samples"][0]["feedback_id"], "review-1"
        )
        validated = AssociationRuleResponse.model_validate(result)
        self.assertEqual(validated.rules[0].samples[0].entity_id, 7)

    async def test_thresholds_filter_rules(self):
        connection = _Connection(
            [
                {
                    "feedback_id": "review-1",
                    "entity_id": 1,
                    "entity_name": "Example",
                    "raw_text": "Two aspects",
                    "feedback_timestamp": None,
                    "aspects": ["price_and_value", "staff_and_service"],
                },
                {
                    "feedback_id": "review-2",
                    "entity_id": 1,
                    "entity_name": "Example",
                    "raw_text": "One aspect",
                    "feedback_timestamp": None,
                    "aspects": ["price_and_value"],
                },
            ]
        )
        with patch.object(mining, "get_pool", return_value=_Pool(connection)):
            result = await mining.get_association_rule_analysis(
                min_support=0.6,
                min_confidence=0.6,
            )

        self.assertEqual(result["rules"], [])
        self.assertEqual(result["meta"]["min_support"], 0.6)
        self.assertEqual(result["meta"]["min_confidence"], 0.6)

    async def test_cluster_filters_and_insufficient_data(self):
        connection = _Connection(
            [
                {
                    "entity_id": 1,
                    "entity_name": "A",
                    "platform": "foodpanda",
                    "total_reviews": 12,
                    "positive_ratio": 0.7,
                    "negative_ratio": 0.2,
                    "avg_confidence": 0.9,
                },
                {
                    "entity_id": 2,
                    "entity_name": "B",
                    "platform": "facebook",
                    "total_reviews": 8,
                    "positive_ratio": 0.3,
                    "negative_ratio": 0.6,
                    "avg_confidence": 0.8,
                },
            ]
        )
        with patch.object(mining, "get_pool", return_value=_Pool(connection)):
            result = await mining.get_cluster_analysis(
                entity_ids=[1, 2],
                days=14,
                algorithm="hierarchical",
                k=3,
                x_axis="avg_confidence",
                y_axis="total_reviews",
            )

        self.assertEqual(connection.args, ([1, 2], 14))
        self.assertEqual(result["clusters"], [])
        self.assertFalse(result["meta"]["sufficient_data"])
        self.assertEqual(result["meta"]["minimum_entities"], 3)
        self.assertEqual(result["meta"]["total_entities"], 2)
        validated = EntityClusterResponse.model_validate(result)
        self.assertFalse(validated.meta.sufficient_data)


class MiningAlgorithmTests(unittest.IsolatedAsyncioTestCase):
    def _rows(self):
        return [
            {
                "entity_id": 1,
                "entity_name": "A",
                "platform": "foodpanda",
                "total_reviews": 20,
                "positive_ratio": 0.85,
                "negative_ratio": 0.05,
                "avg_confidence": 0.92,
            },
            {
                "entity_id": 2,
                "entity_name": "B",
                "platform": "foodpanda",
                "total_reviews": 18,
                "positive_ratio": 0.75,
                "negative_ratio": 0.12,
                "avg_confidence": 0.88,
            },
            {
                "entity_id": 3,
                "entity_name": "C",
                "platform": "facebook",
                "total_reviews": 25,
                "positive_ratio": 0.25,
                "negative_ratio": 0.65,
                "avg_confidence": 0.8,
            },
            {
                "entity_id": 4,
                "entity_name": "D",
                "platform": "facebook",
                "total_reviews": 22,
                "positive_ratio": 0.15,
                "negative_ratio": 0.75,
                "avg_confidence": 0.78,
            },
        ]

    async def test_kmeans_returns_requested_cluster_shape(self):
        connection = _Connection(self._rows())
        with patch.object(mining, "get_pool", return_value=_Pool(connection)):
            result = await mining.get_cluster_analysis(k=2)

        self.assertTrue(result["meta"]["sufficient_data"])
        self.assertEqual(result["meta"]["actual_clusters"], 2)
        self.assertEqual(len(result["clusters"]), 2)
        members = [
            member
            for cluster in result["clusters"]
            for member in cluster["entities"]
        ]
        self.assertEqual(len(members), 4)
        self.assertTrue(all("x_value" in member for member in members))

    async def test_hierarchical_returns_requested_cluster_shape(self):
        connection = _Connection(self._rows())
        with patch.object(mining, "get_pool", return_value=_Pool(connection)):
            result = await mining.get_cluster_analysis(
                algorithm="hierarchical", k=2
            )

        self.assertEqual(result["meta"]["algorithm"], "hierarchical")
        self.assertEqual(result["meta"]["actual_clusters"], 2)

    def test_entity_id_parser_deduplicates(self):
        self.assertEqual(_parse_entity_ids("3,2,3"), [3, 2])


if __name__ == "__main__":
    unittest.main()
