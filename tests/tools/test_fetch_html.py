import httpx
import pytest

from app.agent.tools.fetch_html import fetch_html_tool
from tests.tools.conftest import FakeResponse, patch_async_client


def _html_body() -> bytes:
    return b"<html><body><p>Lei de Bases do Sistema de Educacao.</p></body></html>"


async def _raise_timeout(*args, **kwargs):
    raise httpx.TimeoutException("timed out", request=None)


class _StreamThatTimeout:
    def __init__(self, coro):
        self._coro = coro

    async def __aenter__(self):
        return await self._coro()

    async def __aexit__(self, *exc):
        return False


class _FailingClient:
    """httpx.AsyncClient cujo stream falha com timeout."""

    def __init__(self):
        self._response = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def stream(self, method, url, **kw):
        return _StreamThatTimeout(_raise_timeout)


@pytest.mark.asyncio
async def test_fetch_html_success(monkeypatch):
    patch_async_client(
        monkeypatch, "app.agent.tools.fetch_html", FakeResponse(chunks=_html_body())
    )
    monkeypatch.setattr(
        "app.agent.tools.fetch_html.trafilatura.extract",
        lambda html, **kw: "Lei de Bases do Sistema de Educacao.",
    )

    text = await fetch_html_tool("https://example.com/lei")

    assert "Lei de Bases" in text


@pytest.mark.asyncio
async def test_fetch_html_timeout(monkeypatch):
    monkeypatch.setattr(
        "app.agent.tools.fetch_html.httpx.AsyncClient", lambda *a, **k: _FailingClient()
    )
    with pytest.raises(httpx.TimeoutException):
        await fetch_html_tool("https://example.com/lei")


@pytest.mark.asyncio
async def test_fetch_html_invalid_url(monkeypatch):
    with pytest.raises(httpx.UnsupportedProtocol):
        await fetch_html_tool("example.com/lei")


@pytest.mark.asyncio
async def test_fetch_html_empty_response(monkeypatch):
    patch_async_client(
        monkeypatch, "app.agent.tools.fetch_html", FakeResponse(chunks=_html_body())
    )
    monkeypatch.setattr(
        "app.agent.tools.fetch_html.trafilatura.extract",
        lambda html, **kw: None,
    )

    with pytest.raises(ValueError, match="sem conteúdo relevante"):
        await fetch_html_tool("https://example.com/lei")


@pytest.mark.asyncio
async def test_fetch_html_http_error(monkeypatch):
    patch_async_client(
        monkeypatch,
        "app.agent.tools.fetch_html",
        FakeResponse(status_code=404, chunks=b""),
    )

    with pytest.raises(httpx.HTTPStatusError):
        await fetch_html_tool("https://example.com/nao-existe")


@pytest.mark.asyncio
async def test_fetch_html_not_html_content_type(monkeypatch):
    patch_async_client(
        monkeypatch,
        "app.agent.tools.fetch_html",
        FakeResponse(content_type="application/octet-stream", chunks=b"abc"),
    )

    with pytest.raises(ValueError, match="não devolve HTML"):
        await fetch_html_tool("https://example.com/ficheiro")