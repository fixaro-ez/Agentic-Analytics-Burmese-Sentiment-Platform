from __future__ import annotations

from fastapi import APIRouter, Depends

from ..auth import AuthUser, get_current_user
from ..models.chat import ChatQuery, ChatResponse
from ..services.chat import query_data

router = APIRouter()


@router.post("/query", response_model=ChatResponse)
async def chat_query(
    body: ChatQuery,
    user: AuthUser = Depends(get_current_user),
):
    return await query_data(body.question)


@router.get("/history")
async def chat_history(user: AuthUser = Depends(get_current_user)):
    return {"history": []}
