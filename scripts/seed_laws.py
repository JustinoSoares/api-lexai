"""Seed: extrai o texto integral das leis prioritárias e popula `law_cache`
com registos curados manualmente (source_type='seed').

Uso:
    python -m scripts.seed_laws            # extrai da web e popula
    python -m scripts.seed_laws --list     # só lista os artigos, sem gravar
"""

import argparse
import asyncio

import structlog

from app.agent.tools.fetch_html import fetch_html_tool
from app.agent.tools.fetch_pdf import fetch_pdf_tool
from app.data.laws import LAWS, LawSeed, parse_articles
from app.db.session import async_session_factory
from app.models import LawCache

logger = structlog.get_logger(__name__)


async def _fetch_text(law: LawSeed) -> str:
    if law.fetch_kind == "pdf":
        return await fetch_pdf_tool(law.url)
    return await fetch_html_tool(law.url)


def _article_fields(law: LawSeed, number: int, title: str, text: str) -> dict:
    artigo = f"Art. {number}º {title}".strip() if title else f"Art. {number}º"
    return {
        "url": f"{law.url}#art-{number}",
        "title": law.title,
        "artigo": artigo,
        "text": text,
        "source_type": "seed",
    }


async def seed_laws(list_only: bool = False) -> int:
    total = 0
    for law in LAWS:
        logger.info("seed_fetch", law=law.slug, url=law.url)
        text = await _fetch_text(law)
        articles = parse_articles(text)
        logger.info("seed_parsed", law=law.slug, articles=len(articles))

        rows = [_article_fields(law, a.number, a.title, a.text) for a in articles]

        if list_only:
            print(f"== {law.number} - {law.title} ({len(rows)} artigos) ==")
            for r in rows[:5]:
                print("  ", r["artigo"], "| texto:", (r["text"] or "")[:60])
            total += len(rows)
            continue

        async with async_session_factory() as session:
            # remove apenas os seed desta lei (idempotente)
            from sqlalchemy import delete

            await session.execute(
                delete(LawCache).where(
                    LawCache.url.startswith(law.url), LawCache.source_type == "seed"
                )
            )
            session.add_all(LawCache(**r) for r in rows)
            await session.commit()

        total += len(rows)
        logger.info("seed_stored", law=law.slug, stored=len(rows))

    return total


async def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true", help="só lista os artigos, sem gravar")
    args = parser.parse_args()
    total = await seed_laws(list_only=args.list)
    msg = "listados" if args.list else "gravados"
    print(f"Total de artigos {msg}: {total}")


if __name__ == "__main__":
    asyncio.run(_main())