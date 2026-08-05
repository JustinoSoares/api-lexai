"""Testes do endpoint POST /chat e dos esquemas de entrada/saída."""

import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.agent.orchestrator import AgentResult
import app.api.rate_limit as rate_limit_module
from app.core.config import settings
from app.db.session import get_db
from app.main import app


@pytest.fixture(autouse=True)
def _no_rate_limit():
    rate_limit_module.clear_rate_limits()
    settings.rate_limit_enabled = False
    yield
    settings.rate_limit_enabled = False


def _force_memory_limiter():
    """Força o caminho em memória (determinístico, independente do Redis)."""
    rate_limit_module._redis_failed_until = time.time() + 1000


class _FakeResult:
    def __init__(self, scalar=None):
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._scalar


class _FakeSession:
    def __init__(self, existing_conversation=None):
        self.existing = existing_conversation
        self.added = []
        self.committed = False

    async def execute(self, stmt):
        return _FakeResult(self.existing)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    async def commit(self):
        self.committed = True


def _client_with(fake_session, agent_result):
    app.dependency_overrides[get_db] = lambda: fake_session
    app.dependency_overrides["run_agent"] = lambda: agent_result
    return TestClient(app)


def test_chat_returns_structured_response(monkeypatch):
    fake = _FakeSession()
    result = AgentResult(
        answer="Resposta jurídica.",
        tool_calls=[],
        source_urls=["https://lex.ao/lei-n-o-7-15"],
    )
    async def fake_run(question, history=None):
        return result
    monkeypatch.setattr("app.api.routes.chat.run_agent", fake_run)
    app.dependency_overrides[get_db] = lambda: fake
    client = TestClient(app)
    try:
        resp = client.post(
            "/chat",
            json={"question": "Qual o prazo de prescrição dos créditos do trabalhador?"},
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert uuid.UUID(body["conversation_id"])
    assert body["answer"].startswith("Resposta jurídica")
    assert body["sources"] == ["https://lex.ao/lei-n-o-7-15"]
    # persistiu a pergunta do utilizador e a resposta do assistente
    roles = [getattr(m, "role", None) for m in fake.added]
    assert "user" in roles
    assert "assistant" in roles
    assert fake.committed


def test_chat_reuses_conversation_and_passes_history(monkeypatch):
    conv_id = uuid.uuid4()

    class _Conv:
        id = conv_id
        messages = [
            type("M", (), {"role": "user", "content": "Olá"})()
        ]

    fake = _FakeSession(existing_conversation=_Conv())
    seen = {}

    async def fake_run(question, history=None):
        seen["history"] = history
        return AgentResult(
            answer="Resposta com contexto.",
            tool_calls=[],
            source_urls=[],
        )

    monkeypatch.setattr("app.api.routes.chat.run_agent", fake_run)
    app.dependency_overrides[get_db] = lambda: fake
    client = TestClient(app)
    try:
        resp = client.post(
            "/chat",
            json={"question": "E quanto ao pagamento?", "conversation_id": str(conv_id)},
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["conversation_id"] == str(conv_id)
    assert seen["history"] == [{"role": "user", "content": "Olá"}]


def test_chat_unknown_conversation_returns_404(monkeypatch):
    fake = _FakeSession(existing_conversation=None)
    monkeypatch.setattr("app.api.routes.chat.run_agent", lambda question, history=None: None)
    app.dependency_overrides[get_db] = lambda: fake
    client = TestClient(app)
    try:
        resp = client.post(
            "/chat",
            json={"question": "Pergunta", "conversation_id": str(uuid.uuid4())},
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 404


def test_chat_validates_empty_question():
    client = TestClient(app)
    resp = client.post("/chat", json={"question": "   "})
    assert resp.status_code == 422


def test_chat_validates_question_length():
    client = TestClient(app)
    resp = client.post("/chat", json={"question": "a" * 2001})
    assert resp.status_code == 422


def _mock_run_agent():
    async def fake_run(question, history=None):
        return AgentResult(answer="ok", tool_calls=[], source_urls=[])
    return fake_run


def test_rate_limit_blocka_apos_maximo(monkeypatch):
    _force_memory_limiter()
    settings.rate_limit_enabled = True
    settings.rate_limit_max_requests = 2
    settings.rate_limit_window_seconds = 60
    monkeypatch.setattr("app.api.routes.chat.run_agent", _mock_run_agent())
    app.dependency_overrides[get_db] = lambda: _FakeSession()
    client = TestClient(app)
    try:
        assert client.post("/chat", json={"question": "q1"}).status_code == 200
        assert client.post("/chat", json={"question": "q2"}).status_code == 200
        r3 = client.post("/chat", json={"question": "q3"})
        assert r3.status_code == 429
        assert r3.headers.get("Retry-After")
    finally:
        app.dependency_overrides.clear()
        settings.rate_limit_enabled = False


def test_rate_limit_por_user_header(monkeypatch):
    _force_memory_limiter()
    settings.rate_limit_enabled = True
    settings.rate_limit_max_requests = 1
    settings.rate_limit_window_seconds = 60
    monkeypatch.setattr("app.api.routes.chat.run_agent", _mock_run_agent())
    app.dependency_overrides[get_db] = lambda: _FakeSession()
    client = TestClient(app)
    try:
        headers = {"X-User-Id": "alice"}
        assert client.post("/chat", json={"question": "q"}, headers=headers).status_code == 200
        assert client.post("/chat", json={"question": "q"}, headers=headers).status_code == 429
        assert (
            client.post("/chat", json={"question": "q"}, headers={"X-User-Id": "bob"}).status_code
            == 200
        )
    finally:
        app.dependency_overrides.clear()
        settings.rate_limit_enabled = False
