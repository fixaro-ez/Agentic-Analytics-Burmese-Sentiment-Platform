from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from ..database import get_pool


async def get_association_rule_results() -> list[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT feedback_id, array_agg(DISTINCT aspect_category) AS aspects "
            "FROM fact_review_absa_results "
            "WHERE aspect_category IS NOT NULL "
            "AND aspect_category <> 'no_aspect' "
            "GROUP BY feedback_id"
        )

    transactions = [set(row["aspects"]) for row in rows if row["aspects"]]
    total = len(transactions)
    if total == 0:
        return []

    singles: Counter[str] = Counter()
    pairs: Counter[tuple[str, str]] = Counter()
    for aspects in transactions:
        singles.update(aspects)
        for antecedent in aspects:
            for consequent in aspects:
                if antecedent != consequent:
                    pairs[(antecedent, consequent)] += 1

    rules: list[dict[str, Any]] = []
    for (antecedent, consequent), count in pairs.items():
        support = count / total
        confidence = count / singles[antecedent]
        consequent_support = singles[consequent] / total
        lift = confidence / consequent_support if consequent_support else 0
        if support >= 0.05 and confidence >= 0.2:
            rules.append(
                {
                    "antecedent": [antecedent],
                    "consequent": [consequent],
                    "support": round(support, 4),
                    "confidence": round(confidence, 4),
                    "lift": round(lift, 4),
                }
            )
    return sorted(rules, key=lambda rule: rule["lift"], reverse=True)[:50]


async def get_cluster_results() -> list[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT entity_id, entity_name, platform, total_reviews, "
            "positive_ratio, negative_ratio, avg_confidence "
            "FROM v_entity_sentiment_overview ORDER BY entity_name"
        )

    definitions = {
        0: "High performers",
        1: "Balanced",
        2: "Needs attention",
    }
    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        positive = float(row["positive_ratio"] or 0)
        negative = float(row["negative_ratio"] or 0)
        cluster_id = 0 if positive >= 0.65 else 2 if negative >= 0.5 else 1
        groups[cluster_id].append(
            {
                "entity_id": row["entity_id"],
                "entity_name": row["entity_name"],
                "platform": row["platform"],
                "total_reviews": row["total_reviews"] or 0,
                "positive_ratio": positive,
                "negative_ratio": negative,
                "avg_confidence": float(row["avg_confidence"] or 0),
            }
        )

    clusters: list[dict[str, Any]] = []
    for cluster_id, entities in sorted(groups.items()):
        clusters.append(
            {
                "cluster_id": cluster_id,
                "label": definitions[cluster_id],
                "entities": entities,
                "centroid": {
                    "positive_ratio": round(
                        sum(item["positive_ratio"] for item in entities) / len(entities),
                        4,
                    ),
                    "negative_ratio": round(
                        sum(item["negative_ratio"] for item in entities) / len(entities),
                        4,
                    ),
                    "avg_confidence": round(
                        sum(item["avg_confidence"] for item in entities) / len(entities),
                        4,
                    ),
                },
            }
        )
    return clusters
