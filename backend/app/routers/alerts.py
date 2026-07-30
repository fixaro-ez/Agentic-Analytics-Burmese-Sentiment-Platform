from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from ..auth import AuthUser, get_current_user
from ..models.chat import AlertConfig, AlertItem
from ..services.analytics import get_entity_sentiment_overviews

router = APIRouter()
_alert_config = AlertConfig()


async def _current_alerts() -> list[AlertItem]:
    items: list[AlertItem] = []
    now = datetime.now(timezone.utc).isoformat()
    for entity in await get_entity_sentiment_overviews():
        ratio = entity.negative_ratio or 0
        if ratio < _alert_config.negative_threshold:
            continue
        severity = "critical" if ratio >= 0.7 else "high" if ratio >= 0.5 else "medium"
        items.append(
            AlertItem(
                alert_id=entity.entity_id,
                entity_id=entity.entity_id,
                entity_name=entity.entity_name,
                alert_type="negative_sentiment_threshold",
                severity=severity,
                message=(
                    f"{entity.entity_name} has {ratio:.1%} negative sentiment, "
                    f"above the {_alert_config.negative_threshold:.1%} threshold."
                ),
                created_at=now,
            )
        )
    return items


@router.get("", response_model=list[AlertItem])
async def list_alerts(
    acknowledged: bool | None = None,
    user: AuthUser = Depends(get_current_user),
):
    items = await _current_alerts()
    if acknowledged is None:
        return items
    return [item for item in items if item.acknowledged is acknowledged]


@router.get("/config", response_model=AlertConfig)
async def get_alert_config(user: AuthUser = Depends(get_current_user)):
    return _alert_config


@router.post("/config", response_model=AlertConfig)
async def update_alert_config(
    config: AlertConfig,
    user: AuthUser = Depends(get_current_user),
):
    global _alert_config
    _alert_config = config
    return _alert_config


@router.post("/check")
async def run_alert_check(user: AuthUser = Depends(get_current_user)):
    alerts = await _current_alerts()
    return {"new_alerts": [item.model_dump() for item in alerts]}
