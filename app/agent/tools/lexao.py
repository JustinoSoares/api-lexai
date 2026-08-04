"""Catálogo de diplomas angolanos no portal Lex.ao e resolução por tópico.

Este catálogo é independente do law_cache: guarda apenas o mapeamento
tópico -> URL do diploma na Lex.ao (a fonte primária da busca). Serve para
que o grounding leia o diploma CORRECTO em vez de depender do ranking do
motor de pesquisa, que mistura fontes portuguesas e devolve diplomas errados.
Quando a questão não corresponde a nenhum tópico, devolve None e a busca web
normal assume o controlo.
"""

import re

import structlog

logger = structlog.get_logger(__name__)

LEXAO_DOCUMENTS: list[dict] = [
    {
        "title": "Lei de Defesa do Consumidor",
        "law": "Lei n.º 15/03 de 22 de julho",
        "url": "https://lex.ao/docs/assembleia-nacional/2003/lei-n-o-15-03-de-22-de-julho/",
        "topics": [
            "consumidor", "defesa do consumidor", "protecção do consumidor",
            "proteção do consumidor", "garantia", "garantia dos bens",
            "bens móveis", "bens moveis", "não consumíveis", "nao consumiveis",
            "produtos", "serviços", "servicos", "qualidade dos produtos",
            "direito do consumidor", "leitura de consumo",
        ],
    },
    {
        "title": "Lei Geral do Trabalho",
        "law": "Lei n.º 7/15 de 15 de junho",
        "url": "https://lex.ao/docs/assembleia-nacional/2015/lei-n-o-7-15-de-15-de-junho/",
        "topics": [
            "trabalho", "trabalhador", "empregador", "contrato de trabalho",
            "relação de trabalho", "relacao de trabalho", "férias", "ferias",
            "salário", "salario", "remuneração", "remuneracao", "despedimento",
            "cessação", "cessacao", "prescrição", "prescricao", "créditos",
            "creditos", "indemnização", "indemnizacao", "subsídio", "subsidio",
            "horário", "horario", "sindicato",
        ],
    },
    {
        "title": "Lei do Sistema de Pagamentos",
        "law": "Lei n.º 40/20 de 16 de dezembro",
        "url": "https://lex.ao/docs/assembleia-nacional/2020/lei-n-o-40-20-de-16-de-dezembro/",
        "topics": [
            "pagamento", "pagamentos", "sistema de pagamentos",
            "instituição de pagamento", "instituicao de pagamento",
            "operações de pagamento", "operacoes de pagamento", "arquivo",
            "arquivados", "registos", "transferência", "transferencia",
            "meios de pagamento", "prestador de serviços de pagamento",
            "prestador de servicos de pagamento",
        ],
    },
]


def _terms(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-ZÀ-ÿ]+", text.lower()))


def resolve_lexao_doc(query: str, min_score: int = 1) -> dict | None:
    """Escolhe o diploma da Lex.ao mais relevante para a questão.

    Pontua cada diploma pela quantidade de tópicos (palavras ou frases) que
    aparecem na pergunta. Devolve o melhor diploma se atingir `min_score`,
    senão None (a busca web normal assume o controlo).
    """
    ql = query.lower()
    best: dict | None = None
    best_score = 0
    for doc in LEXAO_DOCUMENTS:
        score = 0
        for topic in doc["topics"]:
            if len(topic.split()) > 1:
                if topic in ql:
                    score += 2
            elif topic in _terms(ql):
                score += 1
        if score > best_score:
            best_score = score
            best = doc

    if best is None or best_score < min_score:
        if best is not None:
            logger.info("lexao_no_match", query=query, best_score=best_score)
        return None
    logger.info("lexao_resolved", query=query, url=best["url"], score=best_score)
    return best