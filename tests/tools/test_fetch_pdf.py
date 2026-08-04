import httpx
import pytest

from app.agent.tools.fetch_pdf import fetch_pdf_tool
from tests.tools.conftest import FakeResponse, patch_async_client

PDF_BYTES = b"%PDF-1.4 fake pdf content for testing"


def _patch_fitz(monkeypatch, doc):
    """Substitui pymupdf.open por um objeto `doc` falso."""
    monkeypatch.setattr("app.agent.tools.fetch_pdf.pymupdf.open", lambda **kw: doc)


class FakePage:
    def __init__(self, text: str = "texto legal"):
        self._text = text

    def get_text(self) -> str:
        return self._text


class FakeDoc:
    def __init__(self, page_count: int = 1, pages=None):
        self.page_count = page_count
        self._pages = pages or [FakePage()] * page_count
        self.closed = False

    def __iter__(self):
        return iter(self._pages)

    def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_fetch_pdf_success(monkeypatch):
    patch_async_client(
        monkeypatch,
        "app.agent.tools.fetch_pdf",
        FakeResponse(content_type="application/pdf", chunks=PDF_BYTES),
    )
    _patch_fitz(
        monkeypatch,
        FakeDoc(
            pages=[
                FakePage(
                    "Constituicao da Republica de Angola. TITULO I - PRINCIPIOS FUNDAMENTAIS. "
                    "Artigo 1.º A Republica de Angola e um Estado democratico de direito."
                )
            ]
        ),
    )

    text = await fetch_pdf_tool("https://example.com/constituicao.pdf")

    assert "Constituicao" in text


@pytest.mark.asyncio
async def test_fetch_pdf_scanned_no_text(monkeypatch):
    patch_async_client(
        monkeypatch,
        "app.agent.tools.fetch_pdf",
        FakeResponse(content_type="application/pdf", chunks=PDF_BYTES),
    )
    _patch_fitz(monkeypatch, FakeDoc(pages=[FakePage("")]))

    with pytest.raises(ValueError, match="digitalizado"):
        await fetch_pdf_tool("https://example.com/digitalizado.pdf")


@pytest.mark.asyncio
async def test_fetch_pdf_corrupt(monkeypatch):
    patch_async_client(
        monkeypatch,
        "app.agent.tools.fetch_pdf",
        FakeResponse(content_type="application/pdf", chunks=b""),
    )

    def _raise(**kw):
        raise ValueError("Failed to open stream")

    monkeypatch.setattr("app.agent.tools.fetch_pdf.pymupdf.open", _raise)

    with pytest.raises(ValueError, match="corrompido"):
        await fetch_pdf_tool("https://example.com/corrupto.pdf")


@pytest.mark.asyncio
async def test_fetch_pdf_too_many_pages(monkeypatch):
    patch_async_client(
        monkeypatch,
        "app.agent.tools.fetch_pdf",
        FakeResponse(content_type="application/pdf", chunks=PDF_BYTES),
    )
    _patch_fitz(monkeypatch, FakeDoc(page_count=999))

    with pytest.raises(ValueError, match="demasiadas páginas"):
        await fetch_pdf_tool("https://example.com/grande.pdf")


@pytest.mark.asyncio
async def test_fetch_pdf_timeout(monkeypatch):
    async def _fail():
        raise httpx.TimeoutException("timed out")

    class _StreamCm:
        def __aenter__(self):
            return _fail()

        def __aexit__(self, *exc):
            return False

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def stream(self, method, url, **kw):
            return _StreamCm()

    monkeypatch.setattr(
        "app.agent.tools.fetch_pdf.httpx.AsyncClient", lambda *a, **k: Client()
    )

    with pytest.raises(httpx.TimeoutException):
        await fetch_pdf_tool("https://example.com/a.pdf")


@pytest.mark.asyncio
async def test_fetch_pdf_not_pdf_content_type(monkeypatch):
    patch_async_client(
        monkeypatch,
        "app.agent.tools.fetch_pdf",
        FakeResponse(content_type="text/html", chunks=b"<html></html>"),
    )

    with pytest.raises(ValueError, match="não devolve PDF"):
        await fetch_pdf_tool("https://example.com/nota")