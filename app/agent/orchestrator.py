"""Orquestrador do agente: loop de tool-calling com o LLM (Groq)."""

import asyncio
import inspect
import json
from dataclasses import dataclass, field
from typing import Any

import structlog

from app.agent.llm import get_groq_client
from app.agent.system_prompt import get_system_prompt
from app.agent.tools.cache_lookup import cache_lookup_tool
from app.agent.tools.fetch_html import fetch_html_tool
from app.agent.tools.fetch_pdf import fetch_pdf_tool
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
                "Pesquisa na web por legislação angolana e fontes jurídicas, "
                "priorizando domínios de referência (Diário da República, portais jurídicos). "
                "Usa antes de responder a perguntas sobre leis que desconheças."
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
    {
        "type": "function",
        "function": {
            "name": "cache_lookup_tool",
            "description": (
                "Consulta a cache local de documentos legais para uma URL já capturada. "
                "Usa primeiro, antes de fazer download, para evitar trabalho repetido."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL do documento."},
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
    "cache_lookup_tool": cache_lookup_tool,
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
    """Regista URLs de fontes a partir do resultado das tools fetch/cache/busca."""
    if name in {"fetch_html_tool", "fetch_pdf_tool", "cache_lookup_tool"}:
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


async def run_agent(question: str, history: list[dict] | None = None) -> AgentResult:
    """Executa o agente: chama o LLM, executa as tools pedidas e devolve a resposta final."""
    client = get_groq_client()
    system = {"role": "system", "content": get_system_prompt()}
    messages: list[dict] = [
        system,
        *((history or [])[-6:]),  # contexto recente limitado
        {"role": "user", "content": question},
    ]

    tool_calls_log: list[dict] = []
    source_urls: set[str] = set()

    for _ in range(MAX_ITERATIONS):
        completion = await client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
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
