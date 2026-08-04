"""Ferramenta de leitura de PDFs com pymupdf (comum no Boletim da República)."""

import structlog
import httpx
import pymupdf

from app.agent.tools.fetch_html import (
    DEFAULT_TIMEOUT,
    MAX_DOWNLOAD_BYTES,
    USER_AGENT,
)

logger = structlog.get_logger(__name__)

MAX_PAGES = 100  # evita processar documentos demasiado grandes
MIN_TEXT_CHARS = 40  # abaixo disto considera-se digitalizado/ilegível


async def fetch_pdf_tool(url: str) -> str:
    """Descarrega o PDF de `url` e devolve o texto extraído.

    Levanta `ValueError` para PDFs corrompidos, digitalizados (sem camada de
    texto) ou demasiado grandes, e `httpx.HTTPError` para falhas de rede.
    """
    async with httpx.AsyncClient(
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if "pdf" not in content_type and not url.lower().endswith(".pdf"):
                logger.info("not_pdf", url=url, content_type=content_type)
                raise ValueError(f"URL não devolve PDF (content-type: {content_type})")

            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > MAX_DOWNLOAD_BYTES:
                    raise ValueError(
                        f"PDF demasiado grande (> {MAX_DOWNLOAD_BYTES // (1024 * 1024)} MB)"
                    )
                chunks.append(chunk)

    data = b"".join(chunks)

    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        logger.warning("pdf_corrupt", url=url, error=str(exc))
        raise ValueError(f"PDF corrompido ou inválido: {exc}") from exc

    if doc.page_count > MAX_PAGES:
        doc.close()
        raise ValueError(f"PDF com demasiadas páginas ({doc.page_count} > {MAX_PAGES})")

    parts: list[str] = []
    for page in doc:
        parts.append(page.get_text())
    page_count = doc.page_count
    doc.close()

    text = "\n".join(parts).strip()

    if len(text) < MIN_TEXT_CHARS:
        raise ValueError(
            "PDF sem camada de texto extraível (possivelmente digitalizado/escaneado; OCR fora do MVP)"
        )

    logger.info("fetch_pdf_ok", url=url, bytes=size, chars=len(text), pages=page_count)
    return text
