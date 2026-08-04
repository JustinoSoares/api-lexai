"""Testes E2E da busca web real (DuckDuckGo), com lex.ao priorizado.

Requer rede. Correr com: RUN_E2E=1 pytest tests/e2e/.
"""

from app.agent.tools.web_search import web_search_tool


def _assert_lexao_primary(results: list[dict]) -> None:
    assert results, "a busca devolveu resultados vazios"
    assert any("lex.ao" in r["href"] for r in results), "lex.ao não surge na busca"
    assert "lex.ao" in results[0]["href"], "o primeiro resultado não é lex.ao"


def test_web_search_devolve_lexao_primeiro_para_lei_pagamentos():
    results = web_search_tool("Lei do Sistema de Pagamentos Angola", max_results=5)
    _assert_lexao_primary(results)


def test_web_search_devolve_lexao_primeiro_para_lei_consumidor():
    results = web_search_tool(
        "Lei de defesa do consumidor Angola garantia bens", max_results=5
    )
    _assert_lexao_primary(results)


def test_web_search_devolve_lexao_primeiro_para_lei_trabalho():
    results = web_search_tool(
        "Lei Geral do Trabalho Angola prescrição créditos", max_results=5
    )
    _assert_lexao_primary(results)


def test_web_search_honra_max_results_com_fonte_primaria():
    results = web_search_tool("Constituição Angola direito ao trabalho", max_results=3)
    assert len(results) <= 3
    assert "lex.ao" in results[0]["href"]