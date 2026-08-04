"""Ferramenta de busca web usando ddgs (DuckDuckGo) com priorização de fontes jurídicas angolanas."""

import functools
import socket

import structlog
from ddgs import DDGS

from app.core.config import settings

logger = structlog.get_logger(__name__)

# Whitelist de domínios de fontes jurídicas angolanas de referência.
# A lógica corresponde ao domínio e aos seus subdomínios.
LEGAL_WHITELIST = {
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

    with DDGS() as ddgs:
        raw = list(ddgs.text(query, max_results=max_results * 3))

    results = [
        {
            "title": item.get("title", ""),
            "href": item.get("href", ""),
            "snippet": item.get("body", ""),
        }
        for item in raw
    ]

    whitelisted = [r for r in results if _is_whitelisted(r["href"])]
    other = [
        r for r in results if not _is_whitelisted(r["href"]) and _has_legal_signal(r["href"], r["snippet"])
    ]
    fallback = [r for r in results if r not in whitelisted and r not in other]

    ranked = whitelisted + other + fallback

    for r in ranked:
        logger.info("web_search_result", query=query, url=r["href"], whitelisted=_is_whitelisted(r["href"]))

    return ranked[:max_results]
