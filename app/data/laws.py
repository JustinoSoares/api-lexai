"""Dados de referência curados (seed) das leis prioritárias e parser por artigo."""

import re
from dataclasses import dataclass

ARTICLE_HEADER_RE = re.compile(
    r"(?im)^\s*(?:artigo|ARTIGO)\s+(\d{1,3})\s*[.º°]*\s*(?:\(([^)]*)\))?\s*$"
)

TITLE_LINE_RE = re.compile(r"^\s*\(([^)]*)\)\s*$")


@dataclass
class LawSeed:
    slug: str
    title: str
    number: str
    url: str
    publication: str
    fetch_kind: str  # "html" | "pdf"


LAWS: list[LawSeed] = [
    LawSeed(
        slug="lei-geral-do-trabalho",
        title="Lei Geral do Trabalho",
        number="Lei n.º 7/15",
        url="https://lex.ao/docs/assembleia-nacional/2015/lei-n-o-7-15-de-15-de-junho/",
        publication="Diário da República Iª Série n.º 87, de 15 de Junho de 2015",
        fetch_kind="html",
    ),
    LawSeed(
        slug="lei-defesa-consumidor",
        title="Lei de Defesa do Consumidor",
        number="Lei n.º 15/03",
        url="https://www.africa-laws.org/Angola/Consumer%20Law/Law%20No.%201503%20of%20July%2022,%202003,%20on%20Consumer%20Protection%20(in%20Portuguese).pdf",
        publication="Diário da República Iª Série n.º 57, de 22 de Julho de 2003",
        fetch_kind="pdf",
    ),
    LawSeed(
        slug="lei-sistema-pagamentos",
        title="Lei do Sistema de Pagamentos",
        number="Lei n.º 40/20",
        url="https://lex.ao/docs/assembleia-nacional/2020/lei-n-o-40-20-de-16-de-dezembro/",
        publication="Diário da República Iª Série n.º 203, de 16 de Dezembro de 2020",
        fetch_kind="html",
    ),
]


@dataclass
class Article:
    number: int
    title: str
    text: str


def parse_articles(text: str) -> list[Article]:
    """Segmenta o texto integral de uma lei em artigos.

    Considera cabeçalhos `Artigo N.º` (ou `ARTIGO N.º`) no início de linha.
    O título/tema pode estar na mesma linha entre parênteses (lex.ao) ou na
    primeira linha do corpo entre parênteses (PDFs). Deduplica cabeçalhos
    repetidos consecutivos (quirk de algumas fontes), mantendo a última.
    """
    matches = list(ARTICLE_HEADER_RE.finditer(text))
    if not matches:
        return []

    articles: list[Article] = []
    for idx, m in enumerate(matches):
        number = int(m.group(1))
        title = (m.group(2) or "").strip()
        body_start = m.end()
        body_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()

        # título na primeira linha do corpo, entre parênteses (formato PDF)
        if not title and body:
            parts = body.split("\n", 1)
            tm = TITLE_LINE_RE.match(parts[0])
            if tm:
                title = tm.group(1).strip()
                body = parts[1].strip()

        articles.append(Article(number=number, title=title, text=body))

    # deduplica cabeçalhos repetidos consecutivos (mantém a última ocorrência)
    deduped: list[Article] = []
    for art in articles:
        if deduped and deduped[-1].number == art.number and deduped[-1].title == art.title:
            deduped[-1] = art
        else:
            deduped.append(art)
    return deduped
