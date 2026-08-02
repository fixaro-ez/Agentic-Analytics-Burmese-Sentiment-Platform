from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChatQuery(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    conversation_id: str | None = Field(default=None, max_length=80)
    language: Literal["en", "my"] = "en"


class ChatChartSpec(BaseModel):
    type: Literal["bar", "line"]
    x_key: str
    y_keys: list[str]


class ChatAction(BaseModel):
    action: Literal["pin", "export_csv", "view_raw_reviews"]
    label: str


class ChatResponse(BaseModel):
    question: str
    sql: str | None = None
    results: list[dict] | None = None
    explanation: str | None = None
    error: str | None = None
    conversation_id: str | None = None
    message_id: str | None = None
    language: Literal["en", "my"] = "en"
    clarification_question: str | None = None
    chart: ChatChartSpec | None = None
    actions: list[ChatAction] = Field(default_factory=list)


class ChatHistoryMessage(BaseModel):
    message_id: str
    role: Literal["user", "assistant"]
    created_at: str
    question: str | None = None
    response: ChatResponse | None = None


class ChatConversation(BaseModel):
    conversation_id: str
    created_at: str
    updated_at: str
    messages: list[ChatHistoryMessage] = Field(default_factory=list)


class ChatHistoryResponse(BaseModel):
    history: list[ChatConversation] = Field(default_factory=list)
