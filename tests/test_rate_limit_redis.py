"""Testes do rate limiting com Redis (janela deslizante partilhada).

Correm apenas se o Redis estiver acessível; caso contrário, são ignorados.
Cada teste usa um cliente Redis próprio (o module-level muda de event loop
entre testes com pytest-asyncio).
"""

import time
import uuid

import pytest
from redis.asyncio import Redis

from app.api.rate_limit import KEY_PREFIX, _redis_check
from app.core.config import settings


async def _fresh_client():
    client = Redis.from_url(settings.redis_url, decode_responses=True)
    if not await client.ping():
        await client.aclose()
        return None
    return client


@pytest.mark.asyncio
async def test_redis_check_blocka_apos_maximo():
    client = await _fresh_client()
    if client is None:
        pytest.skip("Redis indisponível; teste ignorado")

    key = f"test-{uuid.uuid4()}"
    window = 60
    allowed = 2
    outcomes = []
    try:
        for _ in range(3):
            blocked, retry = await _redis_check(key, time.time(), allowed, window, client=client)
            outcomes.append(blocked)
            if blocked:
                assert retry >= 1
    finally:
        await client.delete(f"{KEY_PREFIX}:{key}")
        await client.aclose()

    # 2 permitidas, a 3.ª bloqueada
    assert outcomes == [False, False, True]


@pytest.mark.asyncio
async def test_redis_check_respeita_janela():
    client = await _fresh_client()
    if client is None:
        pytest.skip("Redis indisponível; teste ignorado")

    key = f"test-{uuid.uuid4()}"
    window = 1
    try:
        assert await _redis_check(key, time.time(), 5, window, client=client) == (False, 0)
        assert await _redis_check(key, time.time(), 5, window, client=client) == (False, 0)
        import asyncio
        await asyncio.sleep(window + 0.1)
        assert await _redis_check(key, time.time(), 5, window, client=client) == (False, 0)
    finally:
        await client.delete(f"{KEY_PREFIX}:{key}")
        await client.aclose()