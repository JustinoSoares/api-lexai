"""Esquemas Pydantic de entrada/saída da API."""

import uuid

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