"""Orquestrador do agente: loop de tool-calling com o LLM (Groq)."""

import asyncio
import inspect
import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import structlog

from app.agent.llm import get_groq_client
from app.agent.system_prompt import get_system_prompt
from app.agent.tools.fetch_html import fetch_html_tool
from app.agent.tools.fetch_pdf import fetch_pdf_tool
from app.agent.tools.lexao import resolve_lexao_doc
from app.agent.tools.web_search import web_search_tool
from app.core.config import settings

logger = structlog.get_logger(__name__)

MAX_ITERATIONS = 4

FALLBACK_MESSAGE = (
    "Não consegui encontrar uma base legal suficientemente fiável e verificada para "
    "responder a esta questão com rigor, e é preferível não arriscar uma resposta "
    "incorrecta. Recomendo que consultes um jurista ou advogado inscrito na ordem "
    "dos advogados de Angola, para aconselhamento adequado ao teu caso concreto."
)

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "web_search_tool",
            "description": (
                "Pesquisa na web por legislação angolana e fontes jurídicas. "
                "Prioriza sempre o portal Lex.ao (https://lex.ao), a fonte principal, "
                "e domínios de referência (Diário da República, Assembleia Nacional). "
                "Usa antes de responder a qualquer pergunta sobre leis, para citar "
                "legislação verificada."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Consulta de pesquisa em português."},
                    "max_results": {"type": "integer", "description": "Nº máximo de resultados (padrão 5)."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_html_tool",
            "description": (
                "Descarrega uma página HTML e devolve o texto principal (sem menus/anúncios). "
                "Usa para ler o conteúdo de uma página encontrada na pesquisa."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL completa da página."},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_pdf_tool",
            "description": (
                "Descarrega um documento PDF (ex.: Boletim da República) e devolve o texto extraído. "
                "Usa quando a fonte é um PDF."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL completa do PDF."},
                },
                "required": ["url"],
            },
        },
    },
]

TOOL_REGISTRY: dict[str, Any] = {
    "web_search_tool": web_search_tool,
    "fetch_html_tool": fetch_html_tool,
    "fetch_pdf_tool": fetch_pdf_tool,
}


@dataclass
class AgentResult:
    answer: str
    tool_calls: list[dict] = field(default_factory=list)
    source_urls: list[str] = field(default_factory=list)


async def _execute_tool(name: str, arguments: dict) -> Any:
    fn = TOOL_REGISTRY[name]
    if inspect.iscoroutinefunction(fn):
        return await fn(**arguments)
    return fn(**arguments)


def _record_sources(source_urls: set[str], name: str, result: Any) -> None:
    """Regista URLs de fontes a partir do resultado das tools fetch/busca."""
    if name in {"fetch_html_tool", "fetch_pdf_tool"}:
        if isinstance(result, dict) and result.get("found"):
            source_urls.add(result["url"])
    elif name == "web_search_tool" and isinstance(result, list):
        for item in result[:3]:
            href = item.get("href")
            if href:
                source_urls.add(href)


def _has_reliable_source(source_urls: set[str]) -> bool:
    """Indica se o agente recolheu pelo menos uma fonte concreta e verificável."""
    return bool(source_urls)


MAX_GROUND_CHARS = 20000
PRIMARY_DOMAIN = "lex.ao"

_GROUND_STOPWORDS = {
    "a", "o", "os", "as", "de", "do", "da", "dos", "das", "é", "que", "em",
    "para", "por", "com", "um", "uma", "se", "no", "na", "nos", "nas", "não",
    "qual", "ser", "ao", "aos", "pelo", "pela", "pelos", "pelas", "mais",
    "menos", "tem", "ter", "como", "ou", "sobre", "entre", "são", "deve",
    "devem", "qual", "quanto", "prazo", "fazer", "feita", "deve", "exigir",
    "após", "pos", "antes", "ser", "está", "esta", "esse", "essa",
}

_ARTICLE_HEADER_RE = re.compile(r"(?im)^\s*artigo\s+\d{1,3}\s*[.º°]*[^.\n]*")


def _ground_keywords(query: str) -> list[str]:
    words = re.findall(r"[a-zA-ZÀ-ÿ]{4,}", query.lower())
    return [w for w in words if w not in _GROUND_STOPWORDS]


def _ground_windows(text: str, query: str, budget: int) -> str:
    """Selecciona do diploma o início e as secções de artigos relevantes.

    Mantém o orçamento de tokens (budget de chars) mas, em vez de apenas o
    começo do diploma, inclui também o artigo cujo cabeçalho acompanha termos
    da pergunta — o que antes ficava de fora e levava o LLM a adivinhar.
    """
    header = text[:1200]
    keywords = _ground_keywords(query)
    if not keywords:
        return text[:budget]

    headers = list(_ARTICLE_HEADER_RE.finditer(text))
    relevant: list[int] = []
    for kw in keywords:
        pos = text.lower().find(kw)
        if pos == -1:
            continue
        # cabeçalho de artigo imediatamente antes da ocorrência do termo
        prev = None
        for m in headers:
            if m.start() > pos:
                break
            prev = m
        if prev is not None and prev.start() not in relevant:
            relevant.append(prev.start())

    if not relevant:
        return text[:budget]

    per_section = max(1000, budget // max(1, len(relevant)))
    sections = []
    used = len(header) + 200
    for start in sorted(relevant):
        if used >= budget:
            break
        end = min(start + per_section, len(text))
        sections.append(text[start:end])
        used += end - start + 200

    return "\n\n---\n\n".join([header, *sections])[:budget]


def _source_rank(url: str) -> tuple[int, int]:
    """Prioridade de leitura de uma URL: páginas HTML de diplomas em lex.ao primeiro."""
    host = (urlparse(url).netloc or "").lower().removeprefix("www.")
    if host.endswith(PRIMARY_DOMAIN):
        if "/docs/" in url:
            if url.lower().endswith(".pdf"):
                return (2, 0)
            return (1, 0)
        return (3, 0)
    return (4, 0)


def _pick_primary_url(source_urls: set[str]) -> str | None:
    """Escolhe a URL da fonte primária (lex.ao) para leitura integral."""
    if not source_urls:
        return None
    return min(source_urls, key=_source_rank)


async def _ground_on_primary(
    source_urls: set[str],
    messages: list[dict],
    tool_calls_log: list[dict],
    primary_url: str | None = None,
    query: str = "",
) -> None:
    """Lê o diploma da fonte primária (Lex.ao) e injeta o texto no contexto.

    Usa `primary_url` (resolvida do catálogo Lex.ao) quando disponível, para
    garantir que se lê o diploma CORRECTO; senão cai para a primeira URL de
    Lex.ao devolvida pela pesquisa. Isto evita ler diplomas errados e ancorar
    a resposta em snippets. O texto é seleccionado por janelas em torno dos
    artigos relevantes à pergunta, dentro do orçamento de tokens.
    """
    url = primary_url or _pick_primary_url(source_urls)
    if not url:
        return
    fetch = fetch_pdf_tool if url.lower().endswith(".pdf") else fetch_html_tool
    try:
        text = await fetch(url)
    except Exception as exc:
        logger.warning("agent_ground_failed", url=url, error=str(exc))
        return
    if not isinstance(text, str) or not text.strip():
        return
    text = _ground_windows(text, query, MAX_GROUND_CHARS)
    source_urls.add(url)
    tc_id = f"ground_{len(tool_calls_log)}"
    messages.append(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tc_id,
                    "type": "function",
                    "function": {
                        "name": "fetch_pdf_tool" if url.lower().endswith(".pdf") else "fetch_html_tool",
                        "arguments": json.dumps({"url": url}),
                    },
                }
            ],
        }
    )
    messages.append({"role": "tool", "tool_call_id": tc_id, "content": text})
    tool_calls_log.append({"tool": "fetch_pdf_tool" if url.lower().endswith(".pdf") else "fetch_html_tool", "arguments": {"url": url}, "id": tc_id})
    logger.info("agent_grounded_source", url=url, chars=len(text))


async def run_agent(question: str, history: list[dict] | None = None) -> AgentResult:
    """Executa o agente: chama o LLM, executa as tools pedidas e devolve a resposta final."""
    client = get_groq_client()
    system = {"role": "system", "content": get_system_prompt()}

    tool_calls_log: list[dict] = []
    source_urls: set[str] = set()

    messages: list[dict] = [system]
    messages.extend((history or [])[-6:])
    messages.append({"role": "user", "content": question})

    for i in range(MAX_ITERATIONS):
        # Na primeira iteração força a busca web: o agente pesquisa sempre a
        # legislação em vez de responder de memória. Depois segue tool_choice auto.
        tool_choice = "auto"
        if i == 0:
            tool_choice = {"type": "function", "function": {"name": "web_search_tool"}}
        completion = await client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            tools=TOOLS,
            tool_choice=tool_choice,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )
        message = completion.choices[0].message

        if not message.tool_calls:
            answer = message.content or ""
            if not _has_reliable_source(source_urls):
                logger.info("agent_no_reliable_source", question=question)
                answer = FALLBACK_MESSAGE
            return AgentResult(
                answer=answer,
                tool_calls=tool_calls_log,
                source_urls=sorted(source_urls),
            )

        messages.append(
            {
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in message.tool_calls
                ],
            }
        )

        for tc in message.tool_calls:
            name = tc.function.name
            try:
                arguments = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}

            logger.info("agent_tool_call", tool=name, arguments=arguments)
            tool_calls_log.append({"tool": name, "arguments": arguments, "id": tc.id})

            try:
                result = await _execute_tool(name, arguments)
                _record_sources(source_urls, name, result)
                content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
            except Exception as exc:
                logger.warning("agent_tool_error", tool=name, error=str(exc))
                content = f"Erro ao executar '{name}': {exc}"

            messages.append(
                {"role": "tool", "tool_call_id": tc.id, "content": content}
            )

        # Após a busca garantida (iteração 0), lê o diploma da fonte primária
        # para ancorar a resposta no conteúdo real em vez de snippets. Usa o
        # catálogo Lex.ao para escolher o diploma correcto quando conhecido.
        if i == 0:
            resolved = resolve_lexao_doc(question)
            await _ground_on_primary(
                source_urls,
                messages,
                tool_calls_log,
                primary_url=resolved["url"] if resolved else None,
                query=question,
            )

    logger.warning("agent_max_iterations_reached", question=question)
    if not _has_reliable_source(source_urls):
        return AgentResult(
            answer=FALLBACK_MESSAGE,
            tool_calls=tool_calls_log,
            source_urls=sorted(source_urls),
        )

    # Esgotou as iterações mas há fontes; pede uma última síntese
    last_user = {"role": "user", "content": "Completa a tua resposta com base nas ferramentas já usadas."}
    completion = await client.chat.completions.create(
        model=settings.llm_model,
        messages=[*messages, last_user],
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )
    answer = completion.choices[0].message.content or ""
    if not answer:
        answer = FALLBACK_MESSAGE
    return AgentResult(
        answer=answer,
        tool_calls=tool_calls_log,
        source_urls=sorted(source_urls),
    )
