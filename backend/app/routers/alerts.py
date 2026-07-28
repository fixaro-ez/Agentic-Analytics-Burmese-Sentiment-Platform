from __future__ import annotations

from fastapi import APIRouter, Depends

from ..auth import AuthUser, get_current_user
from ..models.chat import AlertConfig, AlertItem

router = APIRouter()


@router.get("", response_model=list[AlertItem])
async def list_alerts(
    acknowledged: bool | None = None,
    user: AuthUser = Depends(get_current_user),
):
    """
    TODO(Member 2): Implement alert listing.

    Steps:
    1. Create an 'alerts' table in PostgreSQL:
       - alert_id SERIAL PRIMARY KEY
       - entity_id INT REFERENCES dim_entities(entity_id)
       - alert_type VARCHAR(50) -- e.g. 'sentiment_spike', 'negative_surge'
       - severity VARCHAR(20) -- 'low', 'medium', 'high', 'critical'
       - message TEXT
       - metadata JSONB
       - acknowledged BOOLEAN DEFAULT FALSE
       - created_at TIMESTAMPTZ DEFAULT NOW()

    2. Query alerts with optional filters (acknowledged, severity, date range).
    3. Return sorted by created_at DESC.
    """
    return []


@router.post("/config", response_model=AlertConfig)
async def update_alert_config(
    config: AlertConfig,
    user: AuthUser = Depends(get_current_user),
):
    """
    TODO(Member 2): Implement alert configuration.

    Steps:
    1. Store config in a 'alert_config' table or as environment variables.
    2. The alert monitoring service should read these thresholds.
    3. Config options:
       - negative_threshold: ratio above which to trigger alert
       - spike_window_hours: how many hours to look back
       - spike_zscore: z-score threshold for anomaly detection
    """
    return config


@router.post("/check")
async def run_alert_check(user: AuthUser = Depends(get_current_user)):
    """
    TODO(Member 2): Implement alert checking logic.

    This endpoint is called by the Supabase Edge Function on a schedule.

    Steps:
    1. Read alert config thresholds.
    2. Query recent sentiment data from PostgreSQL.
    3. Detect anomalies:
       - Negative sentiment ratio exceeding threshold
       - Z-score spike in negative reviews within the window
    4. Insert new alerts into the alerts table.
    5. Return list of newly created alerts.
    """
    return {
        "new_alerts": [],
        "message": "Alert checking not yet implemented. TODO(Member 2)",
    }
