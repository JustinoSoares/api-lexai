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
from app.models import Conversation


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


class _FakeHistorySession:
    def __init__(self, conversation, messages, total=None):
        self._conv = conversation
        self._messages = messages
        self._total = total if total is not None else len(messages)

    async def get(self, model, pk):
        return self._conv

    async def scalar(self, stmt):
        return self._total

    async def scalars(self, stmt):
        class _R:
            def all(self):
                return self._rows
        r = _R()
        r._rows = self._messages
        return r


def _fake_message(id_, role, content, created_at, sources=()):
    class _Law:
        def __init__(self, url):
            self.url = url

    class _Src:
        def __init__(self, url):
            self.law_cache = _Law(url)

    msg = type("M", (), {})()
    msg.id = id_
    msg.role = role
    msg.content = content
    msg.created_at = created_at
    msg.sources = [_Src(u) for u in sources]
    return msg


def test_conversation_history_paginated():
    conv_id = uuid.uuid4()
    msgs = [
        _fake_message(uuid.uuid4(), "user", "q1", "2024-01-01T00:00:00+00:00", ["https://lex.ao/x"]),
        _fake_message(uuid.uuid4(), "assistant", "a1", "2024-01-01T00:00:01+00:00"),
        _fake_message(uuid.uuid4(), "user", "q2", "2024-01-01T00:00:02+00:00"),
    ]
    fake = _FakeHistorySession(Conversation(id=conv_id, title="T"), msgs, total=3)
    app.dependency_overrides[get_db] = lambda: fake
    client = TestClient(app)
    try:
        resp = client.get(f"/conversations/{conv_id}/messages?page=1&per_page=2")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == 3
    assert body["data"][0]["role"] == "user"
    assert body["data"][0]["sources"] == ["https://lex.ao/x"]
    assert body["meta"] == {
        "page": 1,
        "per_page": 2,
        "total": 3,
        "total_pages": 2,
        "has_next": True,
        "has_prev": False,
        "next_page": 2,
        "prev_page": None,
    }


def test_conversation_history_unknown_returns_404():
    fake = _FakeHistorySession(None, [])
    app.dependency_overrides[get_db] = lambda: fake
    client = TestClient(app)
    try:
        resp = client.get(f"/conversations/{uuid.uuid4()}/messages")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 404


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
