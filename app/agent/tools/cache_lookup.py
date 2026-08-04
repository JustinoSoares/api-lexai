"""Cache de documentos legais (tabela law_cache): consulta por termos e gravação."""

import structlog
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert

from app.db.session import async_session_factory
from app.models import LawCache

logger = structlog.get_logger(__name__)


def _terms(query: str) -> list[str]:
    return [w.strip() for w in query.lower().split() if w.strip()][:8]


async def cache_lookup_tool(query: str, limit: int = 3) -> dict:
    """Consulta a cache por termos relacionados à pergunta, antes da busca web.

    Procura em título, artigo e texto. Devolve até `limit` resultados.
    """
    keywords = _terms(query)
    async with async_session_factory() as session:
        stmt = select(LawCache)
        if keywords:
            clauses = []
            for kw in keywords:
                pattern = f"%{kw}%"
                clauses.append(LawCache.title.ilike(pattern))
                clauses.append(LawCache.artigo.ilike(pattern))
                clauses.append(LawCache.text.ilike(pattern))
            stmt = stmt.where(or_(*clauses))
        else:
            return {"found": 0, "results": []}

        stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        entries = result.scalars().all()

    results = [
        {
            "url": e.url,
            "title": e.title,
            "artigo": e.artigo,
            "snippet": (e.text or "")[:300],
            "captured_at": e.captured_at.isoformat() if e.captured_at else None,
        }
        for e in entries
    ]

    logger.info("cache_lookup", query=query, found=len(results))
    return {"found": len(results), "results": results}


async def cache_store(url: str, title: str, text: str, artigo: str | None = None) -> dict:
    """Grava/atualiza um documento capturado na cache (upsert por URL).

    `captured_at` é definido pelo servidor (server_default now()).
    """
    stmt = insert(LawCache).values(
        url=url,
        title=title[:500],
        artigo=artigo[:255] if artigo else None,
        text=text,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[LawCache.url],
        set_={
            LawCache.title.name: stmt.excluded.title,
            LawCache.artigo.name: stmt.excluded.artigo,
            LawCache.text.name: stmt.excluded.text,
        },
    )

    async with async_session_factory() as session:
        await session.execute(stmt)
        await session.commit()

    logger.info("cache_store", url=url, title=title[:50])
    return {"stored": True, "url": url, "title": title}