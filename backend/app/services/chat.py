from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, AsyncIterator
from uuid import uuid4

from ..config import settings
from ..database import get_pool
from ..models.chat import (
    ChatAction,
    ChatChartSpec,
    ChatConversation,
    ChatHistoryMessage,
    ChatHistoryResponse,
    ChatQuery,
    ChatResponse,
)

logger = logging.getLogger(__name__)


class UnsafeSQL(ValueError):
    """Raised when a query is not provably read-only."""


class QueryScopeMismatch(ValueError):
    """Raised when generated SQL drops an explicit question scope."""


_DISALLOWED_SQL = {
    "ALTER",
    "ANALYZE",
    "CALL",
    "CLUSTER",
    "COMMENT",
    "COPY",
    "CREATE",
    "DEALLOCATE",
    "DELETE",
    "DISCARD",
    "DO",
    "DROP",
    "EXECUTE",
    "GRANT",
    "INSERT",
    "INTO",
    "LISTEN",
    "LOAD",
    "LOCK",
    "MERGE",
    "NOTIFY",
    "PREPARE",
    "REASSIGN",
    "REFRESH",
    "REINDEX",
    "RESET",
    "REVOKE",
    "SECURITY",
    "SET",
    "TRUNCATE",
    "UNLISTEN",
    "UPDATE",
    "VACUUM",
}
_DISALLOWED_FUNCTIONS = {
    "dblink",
    "lo_export",
    "lo_import",
    "pg_advisory_lock",
    "pg_read_binary_file",
    "pg_read_file",
    "pg_sleep",
    "pg_terminate_backend",
}
_CONVERSATIONS: dict[str, dict[str, ChatConversation]] = defaultdict(dict)
_MAX_CONVERSATIONS_PER_USER = 20
_MAX_MESSAGES_PER_CONVERSATION = 50
_GENAI_CLIENT: Any | None = None
_GENAI_CLIENT_CONFIG: tuple[str, int, int] | None = None
_QUERY_CACHE: dict[str, tuple[float, tuple[dict[str, Any], ...]]] = {}
_PLAN_CACHE: dict[
    tuple[str, str],
    tuple[float, tuple[str, str, ChatChartSpec | None]],
] = {}
_MAX_CACHED_QUERIES = 128
_MAX_CACHED_PLANS = 128
_LLM_UNAVAILABLE_UNTIL = 0.0
_LAST_LLM_ERROR: str | None = None

_ANALYTICS_SCHEMA = """\
Tables and columns:
- dim_entities(entity_id, entity_name, platform, platform_metadata)
- fact_review_absa_results(result_id, feedback_id, entity_id, feedback_timestamp,
  raw_text, aspect_category, sentiment_label, confidence_score)
- fact_social_posts(post_id, entity_id, post_timestamp, post_text, total_reactions,
  like_count, love_count, haha_count, sad_count, angry_count, care_count,
  wow_count, shares_count, comments_count, positivity_ratio, negativity_ratio)
- dim_brands(brand_id, brand_name, facebook_entity_id)
- bridge_brand_foodpanda_shops(brand_id, entity_id)
Views and columns:
- v_entity_sentiment_overview(entity_id, entity_name, platform, total_reviews,
  positive_count, negative_count, neutral_count, positive_ratio, negative_ratio, avg_confidence)
- v_aspect_breakdown(aspect_category, sentiment_label, count, avg_confidence)
- v_sentiment_daily_trends(feedback_date, entity_id, entity_name, platform,
  total_reviews, positive_count, negative_count, neutral_count, positive_ratio)
- v_facebook_engagement(entity_id, entity_name, total_posts, total_reactions,
  total_shares, total_comments, avg_positivity_ratio, avg_negativity_ratio)
- v_entity_aspect_summary(entity_id, entity_name, platform, aspect_category,
  sentiment_label, count)
"""

_BUSINESS_CONTEXT = """\
Additional context:
- Aspect categories: product_quality, fulfillment_and_speed, price_and_value, staff_and_service, variety_and_availability
- Sentiment labels: Positive, Negative, Neutral
- Platforms: facebook, foodpanda
- Prefer views (v_*) for aggregate/overview questions. Use base tables for detailed drill-down queries (e.g., raw review text).
- Foreign keys: fact_review_absa_results.entity_id → dim_entities.entity_id; fact_social_posts.entity_id → dim_entities.entity_id; dim_brands.facebook_entity_id → dim_entities.entity_id; bridge_brand_foodpanda_shops.brand_id → dim_brands.brand_id; bridge_brand_foodpanda_shops.entity_id → dim_entities.entity_id.
- A branch means a Foodpanda shop mapped through bridge_brand_foodpanda_shops. For questions about branches of a named brand, join dim_brands → bridge_brand_foodpanda_shops → the entity/view and filter dim_brands.brand_name. Do not rank unrelated entities.
- Preserve every scope in the question, including brand, branch, entity, platform, aspect, sentiment, and date range. Never silently drop a requested filter.
- Use COUNT(DISTINCT (entity_id, feedback_id)) when counting distinct reviews from fact_review_absa_results."""


def _build_system_prompt() -> str:
    return (
        "You are a SQL analyst for a Burmese sentiment analytics dashboard.\n"
        "Given a natural-language question, write a single SELECT query against PostgreSQL.\n"
        "Rules: ONLY SELECT. No DML, no DDL. Use LIMIT 100 max.\n"
        "The SQL must answer the exact question and retain every named filter.\n"
        "Return ONLY the raw SQL — no markdown fences, no explanation, no commentary.\n\n"
        f"Database schema:\n{_ANALYTICS_SCHEMA}\n\n"
        f"{_BUSINESS_CONTEXT}"
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _serialize_rows(rows: list[Any]) -> list[dict[str, Any]]:
    return [
        {key: _json_value(value) for key, value in dict(row).items()}
        for row in rows
    ]


def _sql_structure(sql: str) -> str:
    """Remove comments and quoted values while retaining SQL structure."""
    output: list[str] = []
    index = 0
    length = len(sql)
    while index < length:
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < length else ""
        if char == "-" and next_char == "-":
            index += 2
            while index < length and sql[index] not in "\r\n":
                index += 1
            output.append(" ")
            continue
        if char == "/" and next_char == "*":
            end = sql.find("*/", index + 2)
            if end == -1:
                raise UnsafeSQL("Unterminated SQL comment")
            output.append(" ")
            index = end + 2
            continue
        if char in {"'", '"'}:
            quote = char
            output.append(" ")
            index += 1
            while index < length:
                if sql[index] == quote:
                    if index + 1 < length and sql[index + 1] == quote:
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            else:
                raise UnsafeSQL("Unterminated quoted SQL value")
            continue
        if char == "$":
            # Dollar-quoted values are unnecessary for analytics queries and
            # make lexical validation needlessly ambiguous.
            if re.match(r"\$[A-Za-z0-9_]*\$", sql[index:]):
                raise UnsafeSQL("Dollar-quoted SQL values are not allowed")
        output.append(char)
        index += 1
    return "".join(output)


def validate_readonly_sql(sql: str) -> str:
    """Validate a single SELECT/CTE statement before it reaches PostgreSQL."""
    if not sql or not sql.strip():
        raise UnsafeSQL("SQL query is empty")

    structure = _sql_structure(sql).strip()
    statements = [part.strip() for part in structure.split(";") if part.strip()]
    if len(statements) != 1:
        raise UnsafeSQL("Exactly one SQL statement is allowed")

    statement = statements[0]
    first_keyword = re.match(r"^[A-Za-z]+", statement)
    if not first_keyword or first_keyword.group(0).upper() not in {"SELECT", "WITH"}:
        raise UnsafeSQL("Only SELECT queries and read-only CTEs are allowed")

    tokens = {token.upper() for token in re.findall(r"\b[A-Za-z_]+\b", statement)}
    blocked = sorted(tokens.intersection(_DISALLOWED_SQL))
    if blocked:
        raise UnsafeSQL(f"Disallowed SQL keyword: {blocked[0]}")
    if re.search(
        r"\bFOR\s+(?:NO\s+KEY\s+)?(?:UPDATE|SHARE)\b",
        statement,
        flags=re.IGNORECASE,
    ):
        raise UnsafeSQL("Row-locking SELECT queries are not allowed")

    lowered = statement.lower()
    for function_name in _DISALLOWED_FUNCTIONS:
        if re.search(rf"\b{re.escape(function_name)}\s*\(", lowered):
            raise UnsafeSQL(f"Disallowed SQL function: {function_name}")

    return sql.strip().rstrip(";").strip()


def validate_question_scope(question: str, sql: str) -> None:
    """Reject plans that omit an explicitly requested brand-branch scope."""
    branch_brand = _branch_brand_filter(question)
    if not branch_brand:
        return

    lowered_sql = sql.lower()
    required_relations = {"dim_brands", "bridge_brand_foodpanda_shops"}
    if not required_relations.issubset(set(re.findall(r"\b[a-z_]+\b", lowered_sql))):
        raise QueryScopeMismatch(
            "Generated SQL did not preserve the requested brand branch filter"
        )
    if branch_brand.lower() not in lowered_sql:
        raise QueryScopeMismatch(
            "Generated SQL did not include the requested brand name"
        )


async def _execute_readonly(sql: str) -> list[dict[str, Any]]:
    safe_sql = validate_readonly_sql(sql)
    now = time.monotonic()
    cached = _QUERY_CACHE.get(safe_sql)
    if cached and cached[0] > now:
        return [dict(row) for row in cached[1]]

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction(readonly=True):
            rows = await conn.fetch(safe_sql, timeout=8)
    serialized = _serialize_rows(rows)
    if settings.CHAT_QUERY_CACHE_SECONDS > 0:
        if len(_QUERY_CACHE) >= _MAX_CACHED_QUERIES:
            oldest_key = min(_QUERY_CACHE, key=lambda key: _QUERY_CACHE[key][0])
            _QUERY_CACHE.pop(oldest_key, None)
        _QUERY_CACHE[safe_sql] = (
            now + settings.CHAT_QUERY_CACHE_SECONDS,
            tuple(dict(row) for row in serialized),
        )
    return serialized


def _translate(explanation: str, language: str) -> str:
    if language != "my":
        return explanation
    translations = {
        "Here are the most frequently detected aspect and sentiment pairs.": (
            "အများဆုံး တွေ့ရှိထားသော အကြောင်းအရာနှင့် စိတ်ခံစားမှု အတွဲများကို "
            "ဖော်ပြထားပါသည်။"
        ),
        "This is the daily sentiment trend for the last 30 days.": (
            "လွန်ခဲ့သော ရက် ၃၀ အတွင်း နေ့စဉ် စိတ်ခံစားမှု လမ်းကြောင်းဖြစ်ပါသည်။"
        ),
        "Entities are ranked by negative-review ratio, with review volume used as the tie-breaker.": (
            "အဖွဲ့အစည်းများကို အနုတ်လက္ခဏာ သုံးသပ်ချက်အချိုးအလိုက် စီထားပြီး "
            "အချိုးတူပါက သုံးသပ်ချက်အရေအတွက်ဖြင့် ဆုံးဖြတ်ထားပါသည်။"
        ),
        "Entities are ranked by positive-review ratio, with review volume used as the tie-breaker.": (
            "အဖွဲ့အစည်းများကို အပြုသဘော သုံးသပ်ချက်အချိုးအလိုက် စီထားပြီး "
            "အချိုးတူပါက သုံးသပ်ချက်အရေအတွက်ဖြင့် ဆုံးဖြတ်ထားပါသည်။"
        ),
        "Here is the current sentiment overview by entity.": (
            "အဖွဲ့အစည်းအလိုက် လက်ရှိ စိတ်ခံစားမှု အနှစ်ချုပ်ကို ဖော်ပြထားပါသည်။"
        ),
        "Here are the results for your query.": (
            "သင့်မေးခွန်းအတွက် ရလဒ်များကို ဖော်ပြထားပါသည်။"
        ),
    }
    return translations.get(explanation, explanation)


def _public_llm_error(exc: Exception) -> str:
    raw = str(exc)
    lowered = raw.lower()
    if isinstance(exc, QueryScopeMismatch):
        return (
            "The generated query did not preserve the requested brand or branch "
            "filter. Please try the question again."
        )
    if "location is not supported" in lowered:
        return (
            "Google could not serve the request from the current network region. "
            "Confirm that the US VPN is connected, then try again."
        )
    if "deadline" in lowered or isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        return "The planning request timed out. Please try again."
    if "429" in lowered or "resource_exhausted" in lowered:
        return "Google is rate-limiting requests. Please try again shortly."
    return "Google could not complete the planning request. Please try again."


def _clarification(normalized: str, has_history: bool, language: str) -> str | None:
    vague_phrases = {
        "show me more",
        "what about them",
        "compare them",
        "what about it",
        "tell me more",
        "more",
    }
    is_vague = normalized in vague_phrases or (
        len(normalized.split()) <= 3
        and any(word in normalized.split() for word in {"it", "them", "those", "more"})
    )
    if is_vague and not has_history:
        if language == "my":
            return (
                "ဘယ်အဖွဲ့အစည်း၊ အချိန်ကာလ သို့မဟုတ် စိတ်ခံစားမှုကို "
                "ဆန်းစစ်လိုပါသလဲ။"
            )
        return (
            "Which entity, date range, or sentiment should I analyze? "
            "For example: “Show negative trends for the last 30 days.”"
        )
    return None


def _sql_string_literal(value: str) -> str:
    """Quote a trusted route value without allowing it to change SQL structure."""
    return "'" + value.replace("'", "''") + "'"


def _branch_brand_filter(routing_text: str) -> str | None:
    """Extract the brand named in common branch-comparison questions."""
    if not re.search(r"\bbranch(?:es)?\b", routing_text):
        return None

    patterns = (
        r"\bbranch(?:es)?\s+(?:of|for)\s+(.+?)(?=\s+(?:has|have|with|by|in)\b|[?.]|$)",
        r"\b(?:which|what)\s+branch(?:es)?\s+(?:of|for)\s+(.+?)(?=\s+(?:has|have|with|by|in)\b|[?.]|$)",
        r"\b([a-z0-9][a-z0-9 &'’-]{0,50})\s+branch(?:es)?\b",
    )
    for pattern in patterns:
        match = re.search(pattern, routing_text, flags=re.IGNORECASE)
        if match:
            candidate = " ".join(match.group(1).split()).strip(" -")
            if candidate:
                return candidate[:60]
    return None


def _brand_label(value: str) -> str:
    return value.upper() if len(value) <= 4 else value.title()


def _keyword_route(
    routing_text: str, language: str
) -> tuple[str, str, ChatChartSpec | None] | None:
    branch_brand = _branch_brand_filter(routing_text)
    if "aspect" in routing_text:
        sql = (
            "SELECT aspect_category AS aspect, sentiment_label AS sentiment, "
            "count, avg_confidence FROM v_aspect_breakdown "
            "ORDER BY count DESC LIMIT 20"
        )
        explanation = (
            "Here are the most frequently detected aspect and sentiment pairs."
        )
        chart = ChatChartSpec(type="bar", x_key="aspect", y_keys=["count"])
    elif "trend" in routing_text or "over time" in routing_text:
        sql = (
            "SELECT feedback_date AS date, SUM(total_reviews)::int AS total_reviews, "
            "SUM(positive_count)::int AS positive_count, "
            "SUM(negative_count)::int AS negative_count, "
            "SUM(neutral_count)::int AS neutral_count "
            "FROM v_sentiment_daily_trends "
            "WHERE feedback_date >= CURRENT_DATE - INTERVAL '30 days' "
            "GROUP BY feedback_date ORDER BY feedback_date LIMIT 100"
        )
        explanation = "This is the daily sentiment trend for the last 30 days."
        chart = ChatChartSpec(
            type="line",
            x_key="date",
            y_keys=["positive_count", "negative_count", "neutral_count"],
        )
    elif "negative" in routing_text and (
        "most" in routing_text
        or "highest" in routing_text
        or "worst" in routing_text
    ):
        if branch_brand:
            brand_sql = _sql_string_literal(branch_brand)
            sql = (
                "SELECT overview.entity_id, overview.entity_name, overview.platform, "
                "overview.total_reviews, overview.negative_count, overview.negative_ratio "
                "FROM v_entity_sentiment_overview overview "
                "JOIN bridge_brand_foodpanda_shops bridge "
                "ON bridge.entity_id = overview.entity_id "
                "JOIN dim_brands brand ON brand.brand_id = bridge.brand_id "
                f"WHERE LOWER(brand.brand_name) = LOWER({brand_sql}) "
                "ORDER BY overview.negative_ratio DESC NULLS LAST, "
                "overview.total_reviews DESC LIMIT 10"
            )
            explanation = (
                f"{_brand_label(branch_brand)} branches are ranked by negative-review "
                "ratio, with review volume used as the tie-breaker."
            )
        else:
            sql = (
                "SELECT entity_id, entity_name, platform, total_reviews, negative_count, "
                "negative_ratio FROM v_entity_sentiment_overview "
                "ORDER BY negative_ratio DESC NULLS LAST, total_reviews DESC LIMIT 10"
            )
            explanation = (
                "Entities are ranked by negative-review ratio, with review volume "
                "used as the tie-breaker."
            )
        chart = ChatChartSpec(
            type="bar", x_key="entity_name", y_keys=["negative_ratio"]
        )
    elif "positive" in routing_text and (
        "most" in routing_text
        or "highest" in routing_text
        or "best" in routing_text
    ):
        if branch_brand:
            brand_sql = _sql_string_literal(branch_brand)
            sql = (
                "SELECT overview.entity_id, overview.entity_name, overview.platform, "
                "overview.total_reviews, overview.positive_count, overview.positive_ratio "
                "FROM v_entity_sentiment_overview overview "
                "JOIN bridge_brand_foodpanda_shops bridge "
                "ON bridge.entity_id = overview.entity_id "
                "JOIN dim_brands brand ON brand.brand_id = bridge.brand_id "
                f"WHERE LOWER(brand.brand_name) = LOWER({brand_sql}) "
                "ORDER BY overview.positive_ratio DESC NULLS LAST, "
                "overview.total_reviews DESC LIMIT 10"
            )
            explanation = (
                f"{_brand_label(branch_brand)} branches are ranked by positive-review "
                "ratio, with review volume used as the tie-breaker."
            )
        else:
            sql = (
                "SELECT entity_id, entity_name, platform, total_reviews, positive_count, "
                "positive_ratio FROM v_entity_sentiment_overview "
                "ORDER BY positive_ratio DESC NULLS LAST, total_reviews DESC LIMIT 10"
            )
            explanation = (
                "Entities are ranked by positive-review ratio, with review volume "
                "used as the tie-breaker."
            )
        chart = ChatChartSpec(
            type="bar", x_key="entity_name", y_keys=["positive_ratio"]
        )
    elif "schema" in routing_text or "database structure" in routing_text:
        sql = (
            "SELECT table_name, column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name IN "
            "('dim_entities', 'dim_brands', 'bridge_brand_foodpanda_shops', "
            "'fact_review_absa_results', 'fact_social_posts') "
            "ORDER BY table_name, ordinal_position LIMIT 100"
        )
        explanation = (
            "The data analyst receives a restricted schema map containing these "
            "analytics tables and columns."
        )
        chart = None
    elif re.search(r"\b(how many|count|total)\b", routing_text) and re.search(
        r"\breviews?\b", routing_text
    ):
        sql = (
            "SELECT COUNT(DISTINCT (entity_id, feedback_id))::int AS total_reviews "
            "FROM fact_review_absa_results"
        )
        explanation = "This is the total number of distinct reviews in the dataset."
        chart = None
    elif re.search(r"\b(how many|count|total)\b", routing_text) and re.search(
        r"\bentities\b|\bshops?\b", routing_text
    ):
        sql = "SELECT COUNT(*)::int AS total_entities FROM dim_entities"
        explanation = "This is the total number of entities in the dataset."
        chart = None
    elif re.search(r"\b(how many|count|total)\b", routing_text) and re.search(
        r"\bbrands?\b", routing_text
    ):
        sql = "SELECT COUNT(*)::int AS total_brands FROM dim_brands"
        explanation = "This is the total number of mapped brands in the dataset."
        chart = None
    elif "engagement" in routing_text or "reaction" in routing_text:
        sql = (
            "SELECT entity_id, entity_name, total_posts, total_reactions, "
            "total_shares, total_comments, avg_positivity_ratio, "
            "avg_negativity_ratio FROM v_facebook_engagement "
            "ORDER BY total_reactions DESC NULLS LAST LIMIT 20"
        )
        explanation = "Here is Facebook engagement ranked by total reactions."
        chart = ChatChartSpec(
            type="bar", x_key="entity_name", y_keys=["total_reactions"]
        )
    elif (
        "sentiment overview" in routing_text
        or "compare entities" in routing_text
        or "compare shops" in routing_text
        or "all entities" in routing_text
    ):
        sql = (
            "SELECT entity_id, entity_name, platform, total_reviews, "
            "positive_count, negative_count, neutral_count, positive_ratio, "
            "negative_ratio FROM v_entity_sentiment_overview "
            "ORDER BY total_reviews DESC LIMIT 20"
        )
        explanation = "Here is the current sentiment overview by entity."
        chart = ChatChartSpec(
            type="bar", x_key="entity_name", y_keys=["positive_ratio", "negative_ratio"]
        )
    else:
        return None

    return sql, _translate(explanation, language), chart


async def _llm_query_plan(
    question: str, language: str
) -> tuple[str, str, ChatChartSpec | None] | None:
    global _GENAI_CLIENT, _GENAI_CLIENT_CONFIG
    global _LAST_LLM_ERROR, _LLM_UNAVAILABLE_UNTIL

    if not settings.GOOGLE_API_KEY:
        return None
    now = time.monotonic()
    cache_key = (question, language)
    cached_plan = _PLAN_CACHE.get(cache_key)
    if cached_plan and cached_plan[0] > now:
        return cached_plan[1]
    if now < _LLM_UNAVAILABLE_UNTIL:
        return None

    try:
        from google import genai
        from google.genai import types

        timeout_ms = max(1, round(settings.GOOGLE_TIMEOUT_SECONDS * 1000))
        client_config = (
            settings.GOOGLE_API_KEY,
            timeout_ms,
            settings.GOOGLE_RETRY_ATTEMPTS,
        )
        if _GENAI_CLIENT is None or _GENAI_CLIENT_CONFIG != client_config:
            _GENAI_CLIENT = genai.Client(
                api_key=settings.GOOGLE_API_KEY,
                http_options=types.HttpOptions(
                    timeout=timeout_ms,
                    retry_options=types.HttpRetryOptions(
                        attempts=max(1, settings.GOOGLE_RETRY_ATTEMPTS)
                    ),
                ),
            )
            _GENAI_CLIENT_CONFIG = client_config

        request = _GENAI_CLIENT.aio.models.generate_content(
            model=settings.GOOGLE_MODEL,
            contents=question,
            config=types.GenerateContentConfig(
                system_instruction=_build_system_prompt(),
                max_output_tokens=256,
                thinking_config=types.ThinkingConfig(thinking_level="minimal"),
            ),
        )
        response = await asyncio.wait_for(
            request,
            timeout=settings.GOOGLE_TIMEOUT_SECONDS + 1,
        )

        sql = (response.text or "").strip()
        sql = re.sub(
            r"^```sql\s*|^```\s*|```$", "", sql, flags=re.MULTILINE
        ).strip()
        sql = validate_readonly_sql(sql)
        validate_question_scope(question, sql)
        _LAST_LLM_ERROR = None
        _LLM_UNAVAILABLE_UNTIL = 0.0
        plan = (
            sql,
            _translate("Here are the results for your query.", language),
            None,
        )
        if settings.CHAT_PLAN_CACHE_SECONDS > 0:
            if len(_PLAN_CACHE) >= _MAX_CACHED_PLANS:
                oldest_key = min(_PLAN_CACHE, key=lambda key: _PLAN_CACHE[key][0])
                _PLAN_CACHE.pop(oldest_key, None)
            _PLAN_CACHE[cache_key] = (
                now + settings.CHAT_PLAN_CACHE_SECONDS,
                plan,
            )
        return plan
    except Exception as exc:
        raw_error = str(exc) or type(exc).__name__
        _LAST_LLM_ERROR = _public_llm_error(exc)
        if "location is not supported" in raw_error.lower():
            _LLM_UNAVAILABLE_UNTIL = time.monotonic() + 15
        logger.warning("Gemini LLM query plan failed: %s", raw_error)
        return None


async def query_data(
    question: str,
    *,
    conversation_id: str | None = None,
    language: str = "en",
    history: list[ChatHistoryMessage] | None = None,
) -> ChatResponse:
    """Answer analytics questions with LLM-generated, validated read-only SQL."""
    history = history or []
    normalized = " ".join(question.lower().split())
    message_id = str(uuid4())

    clarification = _clarification(normalized, bool(history), language)
    if clarification:
        return ChatResponse(
            question=question,
            conversation_id=conversation_id,
            message_id=message_id,
            language=language,
            clarification_question=clarification,
            explanation=clarification,
        )

    routing_text = normalized
    if history and any(
        word in normalized.split() for word in {"it", "them", "those", "more"}
    ):
        previous_questions = [
            item.question for item in history if item.role == "user" and item.question
        ]
        if previous_questions:
            routing_text = f"{previous_questions[-1]} {normalized}"

    result = await _llm_query_plan(routing_text, language)
    if result is None and settings.CHAT_TEMPLATE_FALLBACK:
        result = _keyword_route(routing_text, language)

    if result is None:
        if settings.GOOGLE_API_KEY and _LAST_LLM_ERROR:
            error = f"The AI query planner is unavailable: {_LAST_LLM_ERROR}"
        else:
            error = (
                "I can answer questions about aspects, trends, sentiment rankings, "
                "and engagement. For other questions, configure GOOGLE_API_KEY in "
                "your .env file to enable AI-powered SQL generation."
            )
        return ChatResponse(
            question=question,
            conversation_id=conversation_id,
            message_id=message_id,
            language=language,
            error=error,
        )

    sql, explanation, chart = result
    results = await _execute_readonly(sql)
    actions = [
        ChatAction(action="pin", label="Pin to Dashboard"),
        ChatAction(action="export_csv", label="Export CSV"),
        ChatAction(action="view_raw_reviews", label="View Raw Reviews"),
    ]
    return ChatResponse(
        question=question,
        sql=sql,
        results=results,
        explanation=explanation,
        conversation_id=conversation_id,
        message_id=message_id,
        language=language,
        chart=chart,
        actions=actions,
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conversation(user_id: str, conversation_id: str | None) -> ChatConversation:
    user_conversations = _CONVERSATIONS[user_id]
    if conversation_id and conversation_id in user_conversations:
        return user_conversations[conversation_id]

    created_at = _now()
    new_conversation = ChatConversation(
        conversation_id=conversation_id or str(uuid4()),
        created_at=created_at,
        updated_at=created_at,
    )
    user_conversations[new_conversation.conversation_id] = new_conversation
    if len(user_conversations) > _MAX_CONVERSATIONS_PER_USER:
        oldest = min(user_conversations.values(), key=lambda item: item.updated_at)
        del user_conversations[oldest.conversation_id]
    return new_conversation


async def answer_question(body: ChatQuery, user_id: str) -> ChatResponse:
    conversation = _conversation(user_id, body.conversation_id)
    response = await query_data(
        body.question,
        conversation_id=conversation.conversation_id,
        language=body.language,
        history=conversation.messages,
    )
    created_at = _now()
    conversation.messages.extend(
        [
            ChatHistoryMessage(
                message_id=str(uuid4()),
                role="user",
                created_at=created_at,
                question=body.question,
            ),
            ChatHistoryMessage(
                message_id=response.message_id or str(uuid4()),
                role="assistant",
                created_at=created_at,
                response=response,
            ),
        ]
    )
    conversation.messages = conversation.messages[-_MAX_MESSAGES_PER_CONVERSATION:]
    conversation.updated_at = created_at
    return response


def get_history(user_id: str, conversation_id: str | None = None) -> ChatHistoryResponse:
    conversations = _CONVERSATIONS.get(user_id, {})
    if conversation_id:
        item = conversations.get(conversation_id)
        return ChatHistoryResponse(history=[item] if item else [])
    return ChatHistoryResponse(
        history=sorted(
            conversations.values(),
            key=lambda item: item.updated_at,
            reverse=True,
        )
    )


def clear_history(user_id: str, conversation_id: str | None = None) -> None:
    if conversation_id:
        _CONVERSATIONS.get(user_id, {}).pop(conversation_id, None)
    else:
        _CONVERSATIONS.pop(user_id, None)


async def stream_answer_events(
    body: ChatQuery, user_id: str
) -> AsyncIterator[dict[str, Any]]:
    """Yield bounded NDJSON events; errors remain machine-readable mid-stream."""
    conversation = _conversation(user_id, body.conversation_id)
    yield {
        "type": "meta",
        "conversation_id": conversation.conversation_id,
        "language": body.language,
    }
    yield {"type": "status", "message": "Generating read-only SQL from your question"}
    try:
        response = await answer_question(
            body.model_copy(update={"conversation_id": conversation.conversation_id}),
            user_id,
        )
        if response.error:
            yield {"type": "error", "error": response.error}
        elif response.clarification_question:
            yield {
                "type": "clarification",
                "question": response.clarification_question,
            }
        elif response.explanation:
            words = response.explanation.split()
            for index in range(0, len(words), 6):
                chunk = " ".join(words[index : index + 6])
                if index + 6 < len(words):
                    chunk += " "
                yield {"type": "explanation_delta", "delta": chunk}
                await asyncio.sleep(0)
        if not response.error:
            yield {"type": "response", "response": response.model_dump()}
        yield {"type": "done"}
    except Exception as exc:
        yield {
            "type": "error",
            "error": str(exc) or "Unable to answer the question",
        }
        yield {"type": "done"}
