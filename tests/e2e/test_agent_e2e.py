"""Testes E2E do agente completo (LLM real + busca web na Lex.ao).

Requer rede e uma chave Groq válida. Correr com: RUN_E2E=1 pytest tests/e2e/.
"""

import pytest

from app.core.config import settings
from app.agent.orchestrator import run_agent, FALLBACK_MESSAGE


@pytest.fixture(scope="module")
def _needs_groq():
    if not settings.groq_api_key:
        pytest.skip("GROQ_API_KEY não definida; E2E do agente ignorado")
    return True


@pytest.mark.asyncio
async def test_agente_pesquisa_web_e_cita_lexao_pagamentos(_needs_groq):
    result = await run_agent(
        "Por quanto tempo devem ser arquivados os registos das operações de pagamento?"
    )

    calls = {t["tool"] for t in result.tool_calls}
    assert "web_search_tool" in calls, "o agente não usou a busca web"

    assert result.answer and result.answer != FALLBACK_MESSAGE
    assert any("lex.ao" in url for url in result.source_urls), (
        f"a resposta não cita lex.ao: {result.source_urls}"
    )


@pytest.mark.asyncio
async def test_agente_nao_responde_de_memoria_cita_lexao_trabalho(_needs_groq):
    result = await run_agent(
        "Qual é o prazo de prescrição dos créditos do trabalhador após a cessação do contrato?"
    )

    calls = {t["tool"] for t in result.tool_calls}
    assert "web_search_tool" in calls

    assert result.answer and result.answer != FALLBACK_MESSAGE
    assert any("lex.ao" in url for url in result.source_urls)


@pytest.mark.asyncio
async def test_agente_devolve_resposta_fundamentada_com_fonte(_needs_groq):
    result = await run_agent(
        "Qual é a duração mínima da garantia dos bens móveis não consumíveis em Angola?"
    )
    assert result.answer and result.answer != FALLBACK_MESSAGE
    assert any("lex.ao" in url for url in result.source_urls), (
        f"não cita lex.ao: {result.source_urls}"
    )