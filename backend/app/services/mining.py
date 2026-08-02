from __future__ import annotations

from collections import Counter, defaultdict
from math import dist
from typing import Any, Iterable

from ..database import get_pool

ALLOWED_CLUSTER_AXES = {
    "positive_ratio",
    "negative_ratio",
    "avg_confidence",
    "total_reviews",
}
MIN_RULE_TRANSACTIONS = 10
MAX_RULE_SAMPLES = 3


def _fact_filters(
    entity_ids: list[int] | None,
    days: int | None,
    alias: str = "r.",
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if entity_ids:
        params.append(entity_ids)
        clauses.append(f"{alias}entity_id = ANY(${len(params)}::int[])")
    if days is not None:
        params.append(days)
        clauses.append(
            f"{alias}feedback_timestamp >= "
            f"CURRENT_DATE - (${len(params)} * INTERVAL '1 day')"
        )
    return (" AND " + " AND ".join(clauses)) if clauses else "", params


def _stringify_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


async def get_association_rule_analysis(
    *,
    entity_ids: list[int] | None = None,
    days: int | None = None,
    min_support: float = 0.05,
    min_confidence: float = 0.2,
) -> dict[str, Any]:
    where, params = _fact_filters(entity_ids, days)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT r.feedback_id, r.entity_id, de.entity_name, "
            "  MAX(r.raw_text) AS raw_text, "
            "  MAX(r.feedback_timestamp) AS feedback_timestamp, "
            "  array_agg(DISTINCT r.aspect_category) AS aspects "
            "FROM fact_review_absa_results r "
            "LEFT JOIN dim_entities de ON de.entity_id = r.entity_id "
            "WHERE r.aspect_category IS NOT NULL "
            "  AND r.aspect_category <> 'no_aspect'"
            f"{where} "
            "GROUP BY r.feedback_id, r.entity_id, de.entity_name",
            *params,
        )

    transactions: list[dict[str, Any]] = []
    for row in rows:
        aspects = set(row["aspects"] or [])
        if not aspects:
            continue
        transactions.append(
            {
                "aspects": aspects,
                "sample": {
                    "feedback_id": str(row["feedback_id"]),
                    "entity_id": row["entity_id"],
                    "entity_name": row["entity_name"],
                    "review_text": row["raw_text"],
                    "created_at": _stringify_timestamp(row["feedback_timestamp"]),
                },
            }
        )

    total = len(transactions)
    multi_aspect = sum(1 for item in transactions if len(item["aspects"]) > 1)
    singles: Counter[str] = Counter()
    pairs: Counter[tuple[str, str]] = Counter()
    pair_samples: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for transaction in transactions:
        aspects = transaction["aspects"]
        singles.update(aspects)
        for antecedent in aspects:
            for consequent in aspects:
                if antecedent == consequent:
                    continue
                pair = (antecedent, consequent)
                pairs[pair] += 1
                if len(pair_samples[pair]) < MAX_RULE_SAMPLES:
                    pair_samples[pair].append(transaction["sample"])

    rules: list[dict[str, Any]] = []
    for (antecedent, consequent), count in pairs.items():
        support = count / total if total else 0
        confidence = count / singles[antecedent] if singles[antecedent] else 0
        consequent_support = singles[consequent] / total if total else 0
        lift = confidence / consequent_support if consequent_support else 0
        if support < min_support or confidence < min_confidence:
            continue
        rules.append(
            {
                "antecedent": [antecedent],
                "consequent": [consequent],
                "support": round(support, 4),
                "confidence": round(confidence, 4),
                "lift": round(lift, 4),
                "cooccurrence_count": count,
                "samples": pair_samples[(antecedent, consequent)],
            }
        )

    rules.sort(
        key=lambda rule: (
            -rule["lift"],
            -rule["confidence"],
            rule["antecedent"][0],
            rule["consequent"][0],
        )
    )
    return {
        "rules": rules[:50],
        "meta": {
            "total_transactions": total,
            "multi_aspect_transactions": multi_aspect,
            "minimum_transactions": MIN_RULE_TRANSACTIONS,
            "sufficient_data": total >= MIN_RULE_TRANSACTIONS,
            "min_support": min_support,
            "min_confidence": min_confidence,
            "filters": {"entity_ids": entity_ids or [], "days": days},
            "assumption": (
                "Support uses all filtered feedback transactions as its denominator. "
                "The 10-transaction threshold is a display warning only; matching "
                "rules are not suppressed."
            ),
        },
    }


async def get_association_rule_results(
    *,
    entity_ids: list[int] | None = None,
    days: int | None = None,
    min_support: float = 0.05,
    min_confidence: float = 0.2,
) -> list[dict[str, Any]]:
    analysis = await get_association_rule_analysis(
        entity_ids=entity_ids,
        days=days,
        min_support=min_support,
        min_confidence=min_confidence,
    )
    return analysis["rules"]


def _normalize_points(
    rows: list[dict[str, Any]], x_axis: str, y_axis: str
) -> list[tuple[float, float]]:
    x_values = [float(row[x_axis]) for row in rows]
    y_values = [float(row[y_axis]) for row in rows]
    x_min, x_max = min(x_values), max(x_values)
    y_min, y_max = min(y_values), max(y_values)

    def scale(value: float, lower: float, upper: float) -> float:
        return 0.5 if upper == lower else (value - lower) / (upper - lower)

    return [
        (scale(x, x_min, x_max), scale(y, y_min, y_max))
        for x, y in zip(x_values, y_values, strict=True)
    ]


def _kmeans_assignments(
    points: list[tuple[float, float]], k: int, iterations: int = 50
) -> list[int]:
    ordered = sorted(range(len(points)), key=lambda index: (sum(points[index]), index))
    centroids = [
        points[ordered[round(i * (len(ordered) - 1) / max(k - 1, 1))]]
        for i in range(k)
    ]
    assignments = [0] * len(points)

    for _ in range(iterations):
        next_assignments = [
            min(
                range(k),
                key=lambda cluster_id: (
                    dist(point, centroids[cluster_id]),
                    cluster_id,
                ),
            )
            for point in points
        ]
        if next_assignments == assignments:
            break
        assignments = next_assignments
        next_centroids: list[tuple[float, float]] = []
        for cluster_id in range(k):
            members = [
                point
                for point, assignment in zip(points, assignments, strict=True)
                if assignment == cluster_id
            ]
            if not members:
                next_centroids.append(centroids[cluster_id])
            else:
                next_centroids.append(
                    (
                        sum(point[0] for point in members) / len(members),
                        sum(point[1] for point in members) / len(members),
                    )
                )
        centroids = next_centroids
    return assignments


def _cluster_centroid(
    cluster: Iterable[int], points: list[tuple[float, float]]
) -> tuple[float, float]:
    members = list(cluster)
    return (
        sum(points[index][0] for index in members) / len(members),
        sum(points[index][1] for index in members) / len(members),
    )


def _hierarchical_assignments(
    points: list[tuple[float, float]], k: int
) -> list[int]:
    clusters: list[list[int]] = [[index] for index in range(len(points))]
    while len(clusters) > k:
        pair = min(
            (
                (
                    dist(
                        _cluster_centroid(clusters[left], points),
                        _cluster_centroid(clusters[right], points),
                    ),
                    left,
                    right,
                )
                for left in range(len(clusters))
                for right in range(left + 1, len(clusters))
            ),
            key=lambda item: item,
        )
        _, left, right = pair
        clusters[left] = sorted([*clusters[left], *clusters[right]])
        del clusters[right]

    assignments = [0] * len(points)
    for cluster_id, members in enumerate(clusters):
        for index in members:
            assignments[index] = cluster_id
    return assignments


async def get_cluster_analysis(
    *,
    entity_ids: list[int] | None = None,
    days: int | None = None,
    algorithm: str = "kmeans",
    k: int = 3,
    x_axis: str = "positive_ratio",
    y_axis: str = "negative_ratio",
) -> dict[str, Any]:
    if x_axis not in ALLOWED_CLUSTER_AXES or y_axis not in ALLOWED_CLUSTER_AXES:
        raise ValueError("Unsupported cluster axis")
    if x_axis == y_axis:
        raise ValueError("Cluster axes must be different")
    if algorithm not in {"kmeans", "hierarchical"}:
        raise ValueError("Unsupported clustering algorithm")
    if not 2 <= k <= 6:
        raise ValueError("Cluster count must be between 2 and 6")

    where, params = _fact_filters(entity_ids, days)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT r.entity_id, de.entity_name, de.platform, "
            "  COUNT(DISTINCT r.feedback_id)::int AS total_reviews, "
            "  COALESCE(AVG((r.sentiment_label = 'Positive')::int), 0) "
            "    AS positive_ratio, "
            "  COALESCE(AVG((r.sentiment_label = 'Negative')::int), 0) "
            "    AS negative_ratio, "
            "  COALESCE(AVG(r.confidence_score), 0) AS avg_confidence "
            "FROM fact_review_absa_results r "
            "JOIN dim_entities de ON de.entity_id = r.entity_id "
            "WHERE r.aspect_category IS NOT NULL "
            "  AND r.aspect_category <> 'no_aspect'"
            f"{where} "
            "GROUP BY r.entity_id, de.entity_name, de.platform "
            "ORDER BY de.entity_name",
            *params,
        )

    entities = [
        {
            "entity_id": row["entity_id"],
            "entity_name": row["entity_name"],
            "platform": row["platform"],
            "total_reviews": int(row["total_reviews"] or 0),
            "positive_ratio": float(row["positive_ratio"] or 0),
            "negative_ratio": float(row["negative_ratio"] or 0),
            "avg_confidence": float(row["avg_confidence"] or 0),
        }
        for row in rows
    ]
    minimum_entities = max(3, k)
    sufficient_data = len(entities) >= minimum_entities
    base_meta = {
        "algorithm": algorithm,
        "requested_k": k,
        "actual_clusters": 0,
        "x_axis": x_axis,
        "y_axis": y_axis,
        "total_entities": len(entities),
        "minimum_entities": minimum_entities,
        "sufficient_data": sufficient_data,
        "filters": {"entity_ids": entity_ids or [], "days": days},
        "assumption": (
            "Clustering uses only the selected X/Y metrics after min-max "
            "normalization. At least max(k, 3) entities are required; entities "
            "with review data are not excluded by an undocumented review threshold."
        ),
    }
    if not sufficient_data:
        return {"clusters": [], "meta": base_meta}

    points = _normalize_points(entities, x_axis, y_axis)
    assignments = (
        _kmeans_assignments(points, k)
        if algorithm == "kmeans"
        else _hierarchical_assignments(points, k)
    )
    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for entity, assignment in zip(entities, assignments, strict=True):
        groups[assignment].append(entity)

    ordered_groups = sorted(
        groups.values(),
        key=lambda members: (
            sum(float(item[x_axis]) for item in members) / len(members),
            sum(float(item[y_axis]) for item in members) / len(members),
        ),
    )
    clusters: list[dict[str, Any]] = []
    for cluster_id, members in enumerate(ordered_groups):
        enriched_members = [
            {
                **member,
                "x_value": float(member[x_axis]),
                "y_value": float(member[y_axis]),
            }
            for member in members
        ]
        clusters.append(
            {
                "cluster_id": cluster_id,
                "label": f"Cluster {cluster_id + 1}",
                "entities": enriched_members,
                "centroid": {
                    "positive_ratio": round(
                        sum(item["positive_ratio"] for item in members) / len(members),
                        4,
                    ),
                    "negative_ratio": round(
                        sum(item["negative_ratio"] for item in members) / len(members),
                        4,
                    ),
                    "avg_confidence": round(
                        sum(item["avg_confidence"] for item in members) / len(members),
                        4,
                    ),
                    "total_reviews": round(
                        sum(item["total_reviews"] for item in members) / len(members),
                        2,
                    ),
                    "x_value": round(
                        sum(float(item[x_axis]) for item in members) / len(members),
                        4,
                    ),
                    "y_value": round(
                        sum(float(item[y_axis]) for item in members) / len(members),
                        4,
                    ),
                },
            }
        )

    base_meta["actual_clusters"] = len(clusters)
    return {"clusters": clusters, "meta": base_meta}


async def get_cluster_results(
    *,
    entity_ids: list[int] | None = None,
    days: int | None = None,
    algorithm: str = "kmeans",
    k: int = 3,
    x_axis: str = "positive_ratio",
    y_axis: str = "negative_ratio",
) -> list[dict[str, Any]]:
    analysis = await get_cluster_analysis(
        entity_ids=entity_ids,
        days=days,
        algorithm=algorithm,
        k=k,
        x_axis=x_axis,
        y_axis=y_axis,
    )
    return analysis["clusters"]
