"""Esquemas Pydantic de entrada/saída da API."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    """Pergunta enviada pelo utilizador ao agente."""

    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(..., min_length=1, max_length=2000, description="Pergunta jurídica.")
    conversation_id: uuid.UUID | None = Field(
        None, description="Identificador UUID da conversa para manter contexto (opcional)."
    )


class ChatSource(BaseModel):
    """Fonte citada numa resposta."""

    url: str


class ChatResponse(BaseModel):
    """Resposta estruturada do agente."""

    conversation_id: uuid.UUID
    question: str
    answer: str
    sources: list[str] = Field(default_factory=list, description="URLs das fontes citadas.")


class MessageOut(BaseModel):
    """Mensagem de uma conversa."""

    id: uuid.UUID
    role: str
    content: str
    created_at: datetime
    sources: list[str] = Field(default_factory=list, description="URLs das fontes citadas.")


class PaginationMeta(BaseModel):
    """Metadados da paginação."""

    page: int
    per_page: int
    total: int
    total_pages: int
    has_next: bool
    has_prev: bool
    next_page: int | None = None
    prev_page: int | None = None


class ConversationHistoryResponse(BaseModel):
    """Histórico paginado de uma conversa."""

    data: list[MessageOut]
    meta: PaginationMeta