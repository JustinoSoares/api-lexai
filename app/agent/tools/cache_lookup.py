"""Ferramenta de consulta à cache de documentos legais (tabela law_cache)."""

import structlog
from sqlalchemy import select

from app.db.session import async_session_factory
from app.models import LawCache

logger = structlog.get_logger(__name__)


async def cache_lookup_tool(url: str) -> dict:
    """Procura na BD um documento legal já capturado para `url`.

    Devolve os dados em cache (title, artigo, text) ou `{"found": False}`.
    """
    async with async_session_factory() as session:
        result = await session.execute(select(LawCache).where(LawCache.url == url))
        entry = result.scalar_one_or_none()

    if entry is None:
        logger.info("cache_miss", url=url)
        return {"found": False, "url": url}

    logger.info("cache_hit", url=url, chars=len(entry.text or ""))
    return {
        "found": True,
        "url": entry.url,
        "title": entry.title,
        "artigo": entry.artigo,
        "text": entry.text,
        "captured_at": entry.captured_at.isoformat() if entry.captured_at else None,
    }