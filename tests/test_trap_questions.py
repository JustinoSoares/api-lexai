"""Testes anti-alucinação (LLM simulado, sem rede/Groq).

Cobrem o comportamento das "armadilhas": leis inexistentes e jurisdições
estrangeiras devem acionar o fallback "sem base legal suficiente"; questões
ambíguas dentro do domínio devem ancorar-se num diploma relevante.
"""

import json
from unittest.mock import patch

import pytest

import app.agent.orchestrator as orchestrator
from app.agent.orchestrator import run_agent, FALLBACK_MESSAGE


class _Function:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = json.dumps(arguments)


class _ToolCall:
    def __init__(self, name, arguments, call_id="call_1"):
        self.id = call_id
        self.function = _Function(name, arguments)


class _Message:
    def __init__(self, tool_calls=None, content=None):
        self.tool_calls = tool_calls
        self.content = content


class _Choice:
    def __init__(self, message):
        self.message = message


class _Completion:
    def __init__(self, message):
        self.choices = [_Choice(message)]


def _make_llm():
    """LLM simulado: 1.ª chamada pede busca web; seguintes devolvem texto."""
    calls = {"n": 0}

    async def create(**kwargs):
        n = calls["n"]
        calls["n"] += 1
        if n == 0:
            query = kwargs["messages"][-1]["content"]
            return _Completion(
                _Message(tool_calls=[_ToolCall("web_search_tool", {"query": query})])
            )
        return _Completion(_Message(content="resposta final"))

    class _Client:
        pass

    completions = type("_Completions", (), {})()
    completions.create = create
    chat = type("_Chat", (), {})()
    chat.completions = completions
    client = _Client()
    client.chat = chat
    return client


def _mock_tools(monkeypatch, search_results, fetch_text):
    monkeypatch.setitem(
        orchestrator.TOOL_REGISTRY,
        "web_search_tool",
        lambda query, max_results=5: search_results,
    )

    async def _fake_fetch(url):
        return fetch_text

    monkeypatch.setattr(orchestrator, "fetch_html_tool", _fake_fetch)


@pytest.mark.asyncio
@patch("app.agent.orchestrator.get_groq_client")
async def test_lei_inexistente_nao_ancora_diploma_irrelevante(mock_get_client, monkeypatch):
    """Busca devolve um diploma real (1999), mas o conteúdo não é relevante -> fallback."""
    mock_get_client.return_value = _make_llm()
    _mock_tools(
        monkeypatch,
        search_results=[{"title": "T", "href": "https://lex.ao/docs/assembleia-nacional/1999/lei-n-o-5-99/", "snippet": "s"}],
        fetch_text="Lei do Orçamento Geral do Estado para o ano de 1999.",
    )

    result = await run_agent(
        "O que estabelece a Lei n.º 99/99 sobre a tributação dos dinossauros em Angola?"
    )

    assert result.answer == FALLBACK_MESSAGE


@pytest.mark.asyncio
@patch("app.agent.orchestrator.get_groq_client")
async def test_jurisdicao_estrangeira_nao_ancora_direito_angolano(mock_get_client, monkeypatch):
    """Pergunta sobre o Japão não pode ser ancorada em diplomas angolanos -> fallback."""
    mock_get_client.return_value = _make_llm()
    _mock_tools(
        monkeypatch,
        search_results=[{"title": "T", "href": "https://lex.ao/docs/presidente-da-republica/2022/decreto-presidencial-n-o-18-22/", "snippet": "s"}],
        fetch_text="Decreto sobre a carta de condução em Angola.",
    )

    result = await run_agent("Qual é a idade mínima para conduzir no Japão?")

    assert result.answer == FALLBACK_MESSAGE
    assert not any(t["tool"].startswith("fetch_") for t in result.tool_calls)


@pytest.mark.asyncio
@patch("app.agent.orchestrator.get_groq_client")
async def test_pergunta_dentro_do_dominio_ancora_diploma_relevante(mock_get_client, monkeypatch):
    """Questão ambígua mas dentro do domínio ancora no diploma relevante -> sem fallback."""
    mock_get_client.return_value = _make_llm()
    _mock_tools(
        monkeypatch,
        search_results=[{"title": "T", "href": "https://lex.ao/docs/assembleia-nacional/2020/lei-n-o-40-20/", "snippet": "s"}],
        fetch_text="Lei do Sistema de Pagamentos — os registos das operações de pagamento.",
    )

    result = await run_agent("Fala-me sobre pagamentos em Angola.")

    assert result.answer == "resposta final"
    assert result.answer != FALLBACK_MESSAGE
    assert any("lex.ao" in url for url in result.source_urls)


@pytest.mark.asyncio
@patch("app.agent.orchestrator.get_groq_client")
async def test_premissa_falsa_e_ancorada_mas_nao_alucina(mock_get_client, monkeypatch):
    """Pergunta tendenciosa dentro do domínio ancora (não é fallback) para o LLM corrigir."""
    mock_get_client.return_value = _make_llm()
    _mock_tools(
        monkeypatch,
        search_results=[{"title": "T", "href": "https://lex.ao/docs/assembleia-nacional/2015/lei-n-o-7-15/", "snippet": "s"}],
        fetch_text="Lei Geral do Trabalho — o despedimento exige justa causa.",
    )

    result = await run_agent(
        "O empregador pode despedir sem justa causa bastando pagar indemnização?"
    )

    assert result.answer != FALLBACK_MESSAGE
    assert any("lex.ao" in url for url in result.source_urls)
