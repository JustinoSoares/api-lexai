"""Rate limiting por IP/utilizador para o endpoint /chat.

Janela deslizante PARTILHADA entre workers via Redis (contador global).
Se o Redis estiver indisponível, cai para uma janela em memória (por
processo) para não bloquear o serviço. Pode ser desligado via
`RATE_LIMIT_ENABLED`.
"""

import random
import time
from collections import defaultdict, deque

import structlog
from fastapi import HTTPException, Request

from app.core.config import settings
from app.db.redis import redis_client

logger = structlog.get_logger(__name__)

KEY_PREFIX = "lexai:ratelimit"
_REDIS_FAILBACK_SECONDS = 5.0

_redis_failed_until: float = 0.0
_memory: dict[str, deque[float]] = defaultdict(deque)
_memory_cleanup: float = 0.0


def _client_key(request: Request) -> str:
    """Chave do cliente: header de utilizador (se presente) ou IP."""
    header = settings.rate_limit_user_header
    if header:
        user = request.headers.get(header)
        if user and user.strip():
            return f"user:{user.strip()}"
    ip = request.client.host if request.client else "unknown"
    return f"ip:{ip}"


def _memory_check(key: str, now: float, max_requests: int, window: int) -> tuple[bool, int]:
    """Verifica o limite em memória (fallback). Devolve (bloqueado, retry_after)."""
    global _memory_cleanup
    if now - _memory_cleanup > 60:
        _memory_cleanup = now
        for k in [k for k, dq in _memory.items() if not dq]:
            _memory.pop(k, None)

    dq = _memory[key]
    while dq and dq[0] <= now - window:
        dq.popleft()
    if len(dq) >= max_requests:
        retry = max(1, int(dq[0] + window - now))
        return True, retry
    dq.append(now)
    return False, 0


async def _redis_check(
    key: str,
    now: float,
    max_requests: int,
    window: int,
    client=None,
) -> tuple[bool, int]:
    """Verifica o limite no Redis (janela deslizante global). Devolve (bloqueado, retry_after).

    Levanta exceção se o Redis não estiver acessível. `client` permite injetar
    um cliente (ex.: em testes, onde o module-level muda de event loop).
    """
    client = client or redis_client
    rkey = f"{KEY_PREFIX}:{key}"
    member = f"{now:.6f}-{random.getrandbits(24)}"

    pipe = client.pipeline(transaction=True)
    pipe.zremrangebyscore(rkey, 0, now - window)
    pipe.zadd(rkey, {member: now})
    pipe.zcard(rkey)
    pipe.expire(rkey, window)
    results = await pipe.execute()

    count = results[2]
    if count > max_requests:
        oldest = await client.zrange(rkey, 0, 0, withscores=True)
        retry = window
        if oldest:
            retry = max(1, int(oldest[0][1] + window - now))
        return True, retry
    return False, 0


async def rate_limit(request: Request) -> None:
    """Dependency: rejeita (429) se o cliente exceder o limite configurado."""
    global _redis_failed_until
    if not settings.rate_limit_enabled:
        return

    now = time.time()
    key = _client_key(request)
    window = settings.rate_limit_window_seconds
    max_requests = settings.rate_limit_max_requests

    blocked, retry = False, 0
    if now < _redis_failed_until:
        blocked, retry = _memory_check(key, now, max_requests, window)
    else:
        try:
            blocked, retry = await _redis_check(key, now, max_requests, window)
        except Exception as exc:  # noqa: BLE001 - Redis indisponível
            _redis_failed_until = now + _REDIS_FAILBACK_SECONDS
            logger.warning("rate_limit_redis_fallback_memory", key=key, error=str(exc))
            blocked, retry = _memory_check(key, now, max_requests, window)

    if blocked:
        logger.warning("rate_limit_exceeded", key=key, max_requests=max_requests)
        raise HTTPException(
            status_code=429,
            detail="Limite de requisições excedido. Tenta novamente dentro de instantes.",
            headers={"Retry-After": str(retry)},
        )


def clear_rate_limits() -> None:
    """Limpa o estado em memória do limiter (útil em testes)."""
    _memory.clear()