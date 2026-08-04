"""Endpoint principal /chat: recebe a pergunta, aciona o agente e devolve a resposta."""

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agent.orchestrator import run_agent
from app.api.rate_limit import rate_limit
from app.db.session import get_db
from app.models import Conversation, Message
from app.schemas import ChatRequest, ChatResponse, extract_disclaimer

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["chat"])


def _history(conversation: Conversation) -> list[dict]:
    """Devolve as mensagens anteriores da conversa como histórico para o agente."""
    return [{"role": m.role, "content": m.content} for m in conversation.messages]


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Fazer uma pergunta ao agente",
    dependencies=[Depends(rate_limit)],
)
async def chat(payload: ChatRequest, db: AsyncSession = Depends(get_db)) -> ChatResponse:
    conversation: Conversation | None = None
    if payload.conversation_id is not None:
        conversation = (
            await db.execute(
                select(Conversation)
                .options(selectinload(Conversation.messages))
                .where(Conversation.id == payload.conversation_id)
            )
        ).scalar_one_or_none()
        if conversation is None:
            raise HTTPException(status_code=404, detail="conversa não encontrada")

    history = _history(conversation) if conversation else None
    result = await run_agent(payload.question, history=history)

    if conversation is None:
        conversation = Conversation(title=payload.question[:80])
        db.add(conversation)
        await db.flush()

    db.add(Message(conversation_id=conversation.id, role="user", content=payload.question))
    db.add(Message(conversation_id=conversation.id, role="assistant", content=result.answer))
    await db.commit()

    logger.info("chat_completed", conversation_id=conversation.id)

    return ChatResponse(
        conversation_id=conversation.id,
        question=payload.question,
        answer=result.answer,
        sources=result.source_urls,
        disclaimer=extract_disclaimer(result.answer),
    )