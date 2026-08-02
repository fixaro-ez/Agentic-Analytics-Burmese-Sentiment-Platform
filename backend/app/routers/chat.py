from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ..auth import AuthUser, get_current_user
from ..models.chat import ChatHistoryResponse, ChatQuery, ChatResponse
from ..services.chat import (
    answer_question,
    clear_history,
    get_history,
    stream_answer_events,
)

router = APIRouter()


@router.post("/query", response_model=ChatResponse)
async def chat_query(
    body: ChatQuery,
    user: AuthUser = Depends(get_current_user),
):
    return await answer_question(body, user.user_id)


@router.post("/stream")
async def chat_stream(
    body: ChatQuery,
    user: AuthUser = Depends(get_current_user),
):
    async def ndjson_stream():
        async for event in stream_answer_events(body, user.user_id):
            yield json.dumps(event, ensure_ascii=False) + "\n"

    return StreamingResponse(
        ndjson_stream(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/history", response_model=ChatHistoryResponse)
async def chat_history(
    conversation_id: str | None = None,
    user: AuthUser = Depends(get_current_user),
):
    return get_history(user.user_id, conversation_id)


@router.delete("/history", status_code=204)
async def delete_chat_history(
    conversation_id: str | None = None,
    user: AuthUser = Depends(get_current_user),
):
    clear_history(user.user_id, conversation_id)
