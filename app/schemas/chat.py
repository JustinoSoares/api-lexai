"""Esquemas Pydantic de entrada/saída da API."""

import re

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_DISCLAIMER = (
    "A resposta tem cariz informativo e não substitui aconselhamento jurídico "
    "profissional individualizado. É recomendável consultar um jurista ou advogado "
    "inscrito na Ordem dos Advogados de Angola."
)


class ChatRequest(BaseModel):
    """Pergunta enviada pelo utilizador ao agente."""

    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(..., min_length=1, max_length=2000, description="Pergunta jurídica.")
    conversation_id: int | None = Field(
        None, description="Identificador de conversa para manter contexto (opcional)."
    )


class ChatSource(BaseModel):
    """Fonte citada numa resposta."""

    url: str


class ChatResponse(BaseModel):
    """Resposta estruturada do agente."""

    conversation_id: int
    question: str
    answer: str
    sources: list[str] = Field(default_factory=list, description="URLs das fontes citadas.")
    disclaimer: str


def extract_disclaimer(answer: str) -> str:
    """Extrai a nota de disclaimer da 4.ª parte da resposta, se presente."""
    if not answer:
        return DEFAULT_DISCLAIMER
    match = re.search(
        r"4\.\s*\*?\*?\s*Disclaimer\s*\*?\*?\s*:?\s*",
        answer,
        re.IGNORECASE,
    )
    if match:
        content = answer[match.end():].strip()
        if content:
            return content
    return DEFAULT_DISCLAIMER