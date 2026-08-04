"""Testes unitários do catálogo Lex.ao (resolução de diploma por tópico)."""

from app.agent.tools.lexao import resolve_lexao_doc


def test_resolve_lei_pagamentos():
    r = resolve_lexao_doc("Por quanto tempo devem ser arquivados os registos das operações de pagamento?")
    assert r is not None and "40-20" in r["url"]


def test_resolve_lei_trabalho():
    r = resolve_lexao_doc("Qual é o prazo de prescrição dos créditos do trabalhador após a cessação?")
    assert r is not None and "lei-n-o-7-15" in r["url"]


def test_resolve_lei_consumidor():
    r = resolve_lexao_doc("Qual é a duração mínima da garantia dos bens móveis não consumíveis?")
    assert r is not None and "lei-n-o-15-03" in r["url"]


def test_resolve_sem_match_devolve_none():
    assert resolve_lexao_doc("Quem é o Presidente de Angola?") is None


def test_resolve_norm_de_accents():
    assert resolve_lexao_doc("prazo de prescrição") is not None