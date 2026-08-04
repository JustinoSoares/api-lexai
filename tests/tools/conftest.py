import httpx


class FakeResponse:
    """Simula a resposta de `client.stream()`."""

    def __init__(
        self,
        status_code: int = 200,
        content_type: str = "text/html",
        chunks: bytes | list[bytes] = b"",
    ):
        self.headers = {"content-type": content_type}
        self._status_code = status_code
        self._chunks = chunks

    def raise_for_status(self) -> None:
        if self._status_code >= 400:
            request = httpx.Request("GET", "https://example.com")
            response = httpx.Response(self._status_code, request=request)
            raise httpx.HTTPStatusError(
                "erro HTTP", request=request, response=response
            )

    async def aiter_bytes(self):
        if isinstance(self._chunks, (bytes, bytearray)):
            yield bytes(self._chunks)
        else:
            for chunk in self._chunks:
                yield chunk


class _StreamCm:
    def __init__(self, response: FakeResponse):
        self._response = response

    async def __aenter__(self) -> FakeResponse:
        return self._response

    async def __aexit__(self, *exc) -> bool:
        return False


class FakeClient:
    """Simula `httpx.AsyncClient`, injetando uma resposta configurada."""

    def __init__(self, response: FakeResponse):
        self._response = response

    async def __aenter__(self) -> "FakeClient":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    def stream(self, method: str, url: str, **kwargs):
        return _StreamCm(self._response)


def patch_async_client(monkeypatch, module_dotted_path: str, response: FakeResponse):
    """Substitui `httpx.AsyncClient` num módulo pelo `FakeClient`."""
    monkeypatch.setattr(
        f"{module_dotted_path}.httpx.AsyncClient",
        lambda *a, **k: FakeClient(response),
    )