import json
from unittest.mock import AsyncMock, patch

import pytest

import app.agent.orchestrator as orchestrator
from app.agent.orchestrator import run_agent


class _Function:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class _ToolCall:
    def __init__(self, name, arguments, call_id):
        self.id = call_id
        self.function = _Function(name, arguments)


def _tool_call(name, arguments, call_id="call_1"):
    return _ToolCall(name, json.dumps(arguments), call_id)


def _completion(tool_calls=None, content=None):
    class _Message:
        def __init__(a):
            a.tool_calls = tool_calls
            a.content = content

    class _Choice:
        def __init__(a):
            a.message = _Message()

    class _Comp:
        def __init__(a):
            a.choices = [_Choice()]

    return _Comp()


async def _fake_create_first(*args, **kwargs):
    # 1ª chamada: devolve tool_calls
    return _completion(
        tool_calls=[
            _tool_call(
                "web_search_tool",
                {"query": "cidadania originaria angola"},
                call_id="call_1",
            )
        ]
    )


async def _fake_start_second(*args, **kwargs):
    # verifica que a 2ª chamada inclui o resultado da tool e devolve texto final
    msgs = kwargs.get("messages") or []
    assert any(m["role"] == "tool" for m in msgs), "resultado da tool não inserido"
    return _completion(content="R: cidadania originária.")


@pytest.mark.asyncio
@patch("app.agent.orchestrator.get_groq_client")
async def test_run_agent_invokes_tool_then_final_answer(mock_get_client, monkeypatch):
    mock_client = AsyncMock()
    side_effects = [_fake_create_first, _fake_start_second]
    calls = {"n": 0}

    async def _create(*args, **kwargs):
        n = calls["n"]
        calls["n"] += 1
        return (await side_effects[min(n, len(side_effects) - 1)](*args, **kwargs))

    mock_client.chat.completions.create = _create
    mock_get_client.return_value = mock_client

    monkeypatch.setitem(
        orchestrator.TOOL_REGISTRY,
        "web_search_tool",
        lambda query, max_results=5: [
            {"title": "T", "href": "https://lex.ao/cidadania", "snippet": "s"}
        ],
    )

    result = await run_agent("Qual a cidadania originária angolana?")

    assert result.answer == "R: cidadania originária."
    assert result.tool_calls and result.tool_calls[0]["tool"] == "web_search_tool"
    assert "https://lex.ao/cidadania" in result.source_urls


@pytest.mark.asyncio
@patch("app.agent.orchestrator.get_groq_client")
async def test_run_agent_fallback_without_reliable_source(mock_get_client):
    """Sem nenhuma fonte fiável recolhida, devolve a mensagem de fallback (anti-alucinação)."""
    mock_client = AsyncMock()

    async def _create(*args, **kwargs):
        return _completion(content="R: resposta sem tools.")

    mock_client.chat.completions.create = _create
    mock_get_client.return_value = mock_client

    result = await run_agent("Quem é o Presidente de Angola?")

    assert result.answer == orchestrator.FALLBACK_MESSAGE
    assert "jurista" in result.answer
    assert result.tool_calls == []


@pytest.mark.asyncio
@patch("app.agent.orchestrator.get_groq_client")
async def test_run_agent_max_iterations_without_source_returns_fallback(mock_get_client, monkeypatch):
    """Se o loop esgota as iterações sem fontes, nunca devolve resposta inventada."""
    mock_client = AsyncMock()

    async def _tool_call_loop(*args, **kwargs):
        return _completion(
            tool_calls=[_tool_call("fetch_html_tool", {"url": "https://x.ao/404"}, call_id="c1")]
        )

    async def _fail(*args, **kwargs):
        raise ValueError("not found")

    mock_client.chat.completions.create = _tool_call_loop
    mock_get_client.return_value = mock_client

    monkeypatch.setitem(orchestrator.TOOL_REGISTRY, "fetch_html_tool", _fail)
    monkeypatch.setattr(orchestrator, "MAX_ITERATIONS", 3)

    result = await run_agent("Questão sem fontes?")

    assert result.answer == orchestrator.FALLBACK_MESSAGE
    assert result.source_urls == []

def test_ground_windows_inclui_artigo_relevante_fora_do_inicio():
    from app.agent.orchestrator import _ground_windows

    texto = (
        "LEI TESTE\n" + "A" * 30000 + "\n"
        "Artigo 23.º (Arquivo)\n"
        "Os registos devem ser arquivados por 10 (dez) anos.\n"
    )
    out = _ground_windows(texto, "por quanto tempo arquivados os registos?", budget=5000)
    assert "Artigo 23.º" in out
    assert "10 (dez) anos" in out


def test_ground_windows_sem_keywords_devolve_inicio():
    from app.agent.orchestrator import _ground_windows

    texto = "LEI X\n" + "B" * 10000
    out = _ground_windows(texto, "o que é a lei?", budget=5000)
    assert out.startswith("LEI X")
    assert len(out) <= 5000


def test_ground_windows_respeita_orcamento():
    from app.agent.orchestrator import _ground_windows

    texto = "LEI Y\n" + ("Artigo 1.º texto " + "C" * 5000) * 30
    out = _ground_windows(texto, "artigo 1 texto", budget=4000)
    assert len(out) <= 4000
