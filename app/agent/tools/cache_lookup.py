"""Cache de documentos legais (tabela law_cache): consulta por termos e gravação."""

import re

import structlog
from sqlalchemy import func, select, text as sqltext
from sqlalchemy.dialects.postgresql import insert

from app.db.session import async_session_factory
from app.models import LawCache

logger = structlog.get_logger(__name__)

STOPWORDS = {
    "a", "o", "os", "as", "de", "do", "da", "dos", "das", "é", "que", "em",
    "para", "por", "com", "um", "uma", "uns", "umas", "se", "no", "na", "nos",
    "nas", "não", "qual", "ser", "sob", "ao", "aos", "pelo", "pela", "pelos",
    "pelas", "mais", "menos", "todos", "toda", "tem", "ter", "como", "ou",
    "dos", "das", "sobre", "entre", "são", "deve", "devem", "devem", "idade",
}

SEARCH_COLUMNS = func.to_tsvector(
    "portuguese",
    func.coalesce(LawCache.artigo, "")
    + " " + func.coalesce(LawCache.title, "")
    + " " + func.coalesce(LawCache.text, ""),
)


def _query_terms(query: str) -> list[str]:
    tokens = re.findall(r"[a-zA-ZÀ-ÿ]+", query.lower())
    return [t for t in tokens if len(t) > 2 and t not in STOPWORDS]


async def cache_lookup_tool(query: str, limit: int = 3) -> dict:
    """Consulta a cache por termos relacionados à pergunta, antes da busca web.

    Usa full-text search do PostgreSQL (dicionário de português, semântica OR
    entre termos) para lidar com inflexões e melhorar a recordação, ordenando
    por relevância (ts_rank). Devolve até `limit` artigos.
    """
    terms = _query_terms(query)
    if not terms:
        return {"found": 0, "results": []}

    tsquery = func.to_tsquery("portuguese", " | ".join(terms))
    stmt = select(
        LawCache.url,
        LawCache.title,
        LawCache.artigo,
        LawCache.text,
        LawCache.captured_at,
        func.ts_rank(SEARCH_COLUMNS, tsquery).label("rank"),
    ).where(SEARCH_COLUMNS.op("@@")(tsquery))
    stmt = stmt.order_by(sqltext("rank desc")).limit(limit)

    async with async_session_factory() as session:
        rows = (await session.execute(stmt)).all()

    top_rank = float(rows[0][5]) if rows else 1.0
    results = [
        {
            "url": r[0],
            "title": r[1],
            "artigo": r[2],
            "snippet": (r[3] or "")[:400],
            "captured_at": r[4].isoformat() if r[4] else None,
            "score": round(float(r[5]) / top_rank, 3) if top_rank else 0.0,
        }
        for r in rows
    ]

    logger.info("cache_lookup", query=query, found=len(results))
    return {"found": len(results), "results": results}


async def get_law_entry(url: str) -> dict | None:
    """Devolve o registo completo (com texto integral) de uma URL da cache."""
    async with async_session_factory() as session:
        entry = (
            await session.execute(select(LawCache).where(LawCache.url == url))
        ).scalar_one_or_none()
    if entry is None:
        return None
    return {
        "url": entry.url,
        "title": entry.title,
        "artigo": entry.artigo,
        "text": entry.text,
        "captured_at": entry.captured_at.isoformat() if entry.captured_at else None,
    }


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