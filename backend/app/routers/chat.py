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
    """
    Chat with Data — ask questions about your sentiment data in natural language.
    Returns SQL query and results.

    TODO(Member 2): The service layer stub is in backend/app/services/chat.py.
    Implement LangChain Text-to-SQL agent there using GPT-4o.

    Security requirements:
    - Use a read-only PostgreSQL role (no INSERT/UPDATE/DELETE/DROP)
    - Add query timeout (30 seconds)
    - Limit results to 100 rows
    - Log all queries for audit
    """
    return await query_data(body.question)


@router.get("/history")
async def chat_history(user: AuthUser = Depends(get_current_user)):
    """
    TODO(Member 2): Implement chat history.

    Steps:
    1. Create a 'chat_history' table in PostgreSQL:
       - id SERIAL PRIMARY KEY
       - user_id UUID (from Supabase Auth)
       - question TEXT
       - sql_query TEXT
       - result_count INT
       - created_at TIMESTAMPTZ DEFAULT NOW()

    2. Store each query in the chat_query endpoint.
    3. Return the user's last 50 queries here.
    """
    return {
        "history": [],
        "message": "Chat history not yet implemented. TODO(Member 2)",
    }
