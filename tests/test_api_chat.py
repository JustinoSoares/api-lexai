"""Testes do endpoint POST /chat e dos esquemas de entrada/saída."""

from fastapi.testclient import TestClient

from app.agent.orchestrator import AgentResult
from app.db.session import get_db
from app.main import app
from app.schemas import extract_disclaimer
from app.schemas.chat import DEFAULT_DISCLAIMER


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
                obj.id = 1

    async def commit(self):
        self.committed = True


def _client_with(fake_session, agent_result):
    app.dependency_overrides[get_db] = lambda: fake_session
    app.dependency_overrides["run_agent"] = lambda: agent_result
    return TestClient(app)


def test_chat_returns_structured_response(monkeypatch):
    fake = _FakeSession()
    result = AgentResult(
        answer="Resposta jurídica.\n\n4. **Disclaimer**: nota.",
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
    assert body["conversation_id"] == 1
    assert body["answer"].startswith("Resposta jurídica")
    assert body["sources"] == ["https://lex.ao/lei-n-o-7-15"]
    assert body["disclaimer"] == "nota."
    # persistiu a pergunta do utilizador e a resposta do assistente
    roles = [getattr(m, "role", None) for m in fake.added]
    assert "user" in roles
    assert "assistant" in roles
    assert fake.committed


def test_chat_reuses_conversation_and_passes_history(monkeypatch):
    class _Conv:
        id = 7
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
            json={"question": "E quanto ao pagamento?", "conversation_id": 7},
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["conversation_id"] == 7
    assert seen["history"] == [{"role": "user", "content": "Olá"}]


def test_chat_unknown_conversation_returns_404(monkeypatch):
    fake = _FakeSession(existing_conversation=None)
    monkeypatch.setattr("app.api.routes.chat.run_agent", lambda question, history=None: None)
    app.dependency_overrides[get_db] = lambda: fake
    client = TestClient(app)
    try:
        resp = client.post("/chat", json={"question": "Pergunta", "conversation_id": 999})
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


def test_extract_disclaimer():
    assert extract_disclaimer("x\n\n4. **Disclaimer**: nota informativa.") == "nota informativa."
    assert extract_disclaimer("apenas resposta") == DEFAULT_DISCLAIMER
    assert extract_disclaimer("") == DEFAULT_DISCLAIMER