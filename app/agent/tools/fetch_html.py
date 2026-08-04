"""Ferramenta de leitura de páginas HTML: download com httpx e extração de texto com trafilatura."""

import structlog
import httpx
import trafilatura

from app.core.config import settings

logger = structlog.get_logger(__name__)

DEFAULT_TIMEOUT = 15.0
MAX_DOWNLOAD_BYTES = 2 * 1024 * 1024  # 2 MB
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


async def fetch_html_tool(url: str) -> str:
    """Descarrega `url` e devolve apenas o texto principal (sem menus/anúncios).

    Levanta `ValueError` para páginas sem conteúdo relevante e `httpx.HTTPError`
    para falhas de rede/HTTP.
    """
    async with httpx.AsyncClient(
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "html" not in content_type.lower():
                logger.info("not_html", url=url, content_type=content_type)
                raise ValueError(f"URL não devolve HTML (content-type: {content_type})")

            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > MAX_DOWNLOAD_BYTES:
                    raise ValueError(
                        f"Resposta demasiado grande (> {MAX_DOWNLOAD_BYTES // (1024 * 1024)} MB)"
                    )
                chunks.append(chunk)

    html = b"".join(chunks).decode("utf-8", errors="replace")

    text = trafilatura.extract(html, include_comments=False, include_tables=False)
    if not text or not text.strip():
        raise ValueError("Página sem conteúdo relevante para extrair")

    logger.info(
        "fetch_html_ok",
        url=url,
        bytes=size,
        chars=len(text),
    )
    return text.strip()
