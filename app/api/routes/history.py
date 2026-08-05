"""Rota de histórico: devolve as mensagens de uma conversa de forma paginada."""

from math import ceil
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models import Conversation, Message, Source
from app.schemas import ConversationHistoryResponse, MessageOut, PaginationMeta

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["chat"])

MAX_PER_PAGE = 100


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=ConversationHistoryResponse,
    summary="Histórico paginado de uma conversa",
)
async def conversation_history(
    conversation_id: UUID,
    page: int = Query(1, ge=1, description="Número da página (começa em 1)."),
    per_page: int = Query(20, ge=1, le=MAX_PER_PAGE, description="Itens por página."),
    db: AsyncSession = Depends(get_db),
) -> ConversationHistoryResponse:
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversa não encontrada")

    total = await db.scalar(
        select(func.count())
        .select_from(Message)
        .where(Message.conversation_id == conversation_id)
    )
    total = total or 0
    total_pages = ceil(total / per_page) if total else 0

    # página fora do intervalo -> ajusta para a última página existente
    if total_pages and page > total_pages:
        page = total_pages

    rows = await db.scalars(
        select(Message)
        .options(selectinload(Message.sources).selectinload(Source.law_cache))
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc(), Message.id)
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    messages = list(rows.all())

    data = [
        MessageOut(
            id=m.id,
            role=m.role,
            content=m.content,
            created_at=m.created_at,
            sources=[s.law_cache.url for s in m.sources if s.law_cache is not None],
        )
        for m in messages
    ]

    meta = PaginationMeta(
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
        next_page=page + 1 if page < total_pages else None,
        prev_page=page - 1 if page > 1 else None,
    )

    logger.info("conversation_history", conversation_id=str(conversation_id), page=page, total=total)

    return ConversationHistoryResponse(data=data, meta=meta)
