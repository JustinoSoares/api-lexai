"""Ferramenta de busca web usando ddgs (DuckDuckGo) com priorização de fontes jurídicas angolanas."""

import functools
import socket

import structlog
from ddgs import DDGS

from app.core.config import settings

logger = structlog.get_logger(__name__)

# Whitelist de domínios de fontes jurídicas angolanas de referência.
# A lógica corresponde ao domínio e aos seus subdomínios.
# `lex.ao` é a fonte primária e é além disso priorizada à frente das restantes.
LEGAL_WHITELIST = {
    "lex.ao",                      # Lex.ao — fonte primária de legislação angolana
    "diariodarepublica.ao",        # Diário da República (Boletim Oficial / publicação de leis)
    "governo.gov.ao",              # Governo de Angola
    "parlamento.ao",               # Assembleia Nacional (produção legislativa)
    "minjusdh.gov.ao",             # Ministério da Justiça e dos Direitos Humanos
    "tribunalsupremo.ao",          # Tribunal Supremo
    "legis-palop.org",             # Legis-PALOP (legislação dos PALOP)
    "lexlink.eu",                  # Portal jurídico de referência
    "vlex.com",                    # vLex Angola / iberlei
    "consultorjuridico.com",       # Portal jurídico de referência
    "angola-forum.com",            # Portal de legislação angolana
}# Termos que reforçam a relevância de um resultado mesmo fora da whitelist.
LEGAL_KEYWORDS = (
    "lei", "decreto", "diploma", "constituição", "código civil",
    "código penal", "regulamento", "boletim oficial", "diário da república",
    "assembleia nacional", "ministério da justiça", "legislação",
)


def _is_whitelisted(url: str) -> bool:
    from urllib.parse import urlparse

    host = (urlparse(url).netloc or "").lower().removeprefix("www.")
    for domain in _validated_whitelist():
        if host == domain or host.endswith(f".{domain}"):
            return True
    return False


def _has_legal_signal(url: str, snippet: str) -> bool:
    text = f"{url} {snippet}".lower()
    return any(kw in text for kw in LEGAL_KEYWORDS)


@functools.lru_cache(maxsize=1)
def _validated_whitelist() -> set[str]:
    """Devolve apenas os domínios da whitelist que existem (resolvem em DNS).

    Domínios inexistentes são ignorados, como se não estivessem na lista.
    """
    valid: set[str] = set()
    for domain in LEGAL_WHITELIST:
        try:
            socket.getaddrinfo(domain, None)
        except socket.gaierror:
            logger.warning("domain_not_resolved", domain=domain)
            continue
        valid.add(domain)
        logger.info("domain_validated", domain=domain)
    return valid


def web_search_tool(query: str, max_results: int = 5) -> list[dict]:
    """Pesquisa na web e devolve resultados priorizados.

    Resultados de domínios na whitelist jurídica angolana vêm primeiro;
    os restantes só completam até `max_results`. Cada item tem:
    title, href (URL) e snippet (body).
    """
    if not settings.web_search_enabled:
        logger.warning("web_search_disabled")
        return []

    results = list(_ddgs_search(query, max_results * 3))

    # Pesquisa dirigida à fonte primária (lex.ao) para garantir que surge,
    # e coloca-a sempre à frente dos restantes resultados.
    lexao = list(_ddgs_search(f"site:lex.ao {query}", max_results * 2))
    fresh = results + [r for r in lexao if r["href"] not in {x["href"] for x in results}]
    fresh = _dedupe(fresh)

    whitelisted = [r for r in fresh if _is_whitelisted(r["href"])]
    other = [
        r for r in fresh if not _is_whitelisted(r["href"]) and _has_legal_signal(r["href"], r["snippet"])
    ]
    fallback = [r for r in fresh if r not in whitelisted and r not in other]

    primary = [r for r in whitelisted if "lex.ao" in r["href"]]
    whitelisted = [r for r in whitelisted if r not in primary]

    ranked = primary + whitelisted + other + fallback

    for r in ranked:
        logger.info("web_search_result", query=query, url=r["href"], whitelisted=_is_whitelisted(r["href"]))

    return ranked[:max_results]


def _ddgs_search(query: str, max_results: int) -> list[dict]:
    with DDGS() as ddgs:
        raw = list(ddgs.text(query, max_results=max_results))
    return [
        {
            "title": item.get("title", ""),
            "href": item.get("href", ""),
            "snippet": item.get("body", ""),
        }
        for item in raw
    ]


def _dedupe(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for item in items:
        if item["href"] in seen:
            continue
        seen.add(item["href"])
        out.append(item)
    return out
