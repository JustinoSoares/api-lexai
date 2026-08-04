"""Rate limiting por IP/utilizador para o endpoint /chat.

Janela deslizante em memória (por processo). Protege o free tier da Groq e
evita abuso das tools de busca. Pode ser desligado via `RATE_LIMIT_ENABLED`.
"""

import time
from collections import defaultdict, deque

import structlog
from fastapi import HTTPException, Request

from app.core.config import settings

logger = structlog.get_logger(__name__)

_hits: dict[str, deque[float]] = defaultdict(deque)
_last_cleanup: float = time.monotonic()
_CLEANUP_EVERY = 60.0


def _client_key(request: Request) -> str:
    """Chave do cliente: header de utilizador (se presente) ou IP."""
    header = settings.rate_limit_user_header
    if header:
        user = request.headers.get(header)
        if user and user.strip():
            return f"user:{user.strip()}"
    ip = request.client.host if request.client else "unknown"
    return f"ip:{ip}"


def _prune_old(dq: deque[float], now: float) -> None:
    window = settings.rate_limit_window_seconds
    while dq and dq[0] <= now - window:
        dq.popleft()


def _cleanup(now: float) -> None:
    global _last_cleanup
    if now - _last_cleanup < _CLEANUP_EVERY:
        return
    _last_cleanup = now
    for key in [k for k, dq in _hits.items() if not dq]:
        _hits.pop(key, None)


async def rate_limit(request: Request) -> None:
    """Dependency: rejeita (429) se o cliente exceder o limite configurado."""
    if not settings.rate_limit_enabled:
        return

    now = time.monotonic()
    _cleanup(now)

    key = _client_key(request)
    dq = _hits[key]
    _prune_old(dq, now)

    max_requests = settings.rate_limit_max_requests
    if len(dq) >= max_requests:
        window = settings.rate_limit_window_seconds
        retry_after = max(1, int(dq[0] + window - now))
        logger.warning("rate_limit_exceeded", key=key, max_requests=max_requests)
        raise HTTPException(
            status_code=429,
            detail="Limite de requisições excedido. Tenta novamente dentro de instantes.",
            headers={"Retry-After": str(retry_after)},
        )

    dq.append(now)


def clear_rate_limits() -> None:
    """Limpa o estado do limiter (útil em testes)."""
    _hits.clear()