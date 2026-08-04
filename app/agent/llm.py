from functools import lru_cache

from groq import AsyncGroq

from app.core.config import settings


@lru_cache
def get_groq_client() -> AsyncGroq:
    if not settings.groq_api_key or settings.groq_api_key.startswith("coloque"):
        raise RuntimeError(
            "GROQ_API_KEY não configurada. Defina a variável no ficheiro .env"
        )
    return AsyncGroq(api_key=settings.groq_api_key)


async def chat(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    **kwargs,
) -> str:
    """Faz uma chamada simples ao modelo (sem tools)."""
    client = get_groq_client()
    completion = await client.chat.completions.create(
        model=model or settings.llm_model,
        messages=messages,
        temperature=temperature if temperature is not None else settings.llm_temperature,
        max_tokens=max_tokens or settings.llm_max_tokens,
        **kwargs,
    )
    return completion.choices[0].message.content or ""
