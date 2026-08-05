"""Cliente Redis assíncrono (rate limiting partilhado entre workers)."""

import structlog
from redis.asyncio import Redis

from app.core.config import settings

logger = structlog.get_logger(__name__)

redis_client: Redis = Redis.from_url(settings.redis_url, decode_responses=True)


async def redis_ping() -> bool:
    """Indica se o Redis responde (faz cache de curta duração para não o martelar)."""
    try:
        return bool(await redis_client.ping())
    except Exception as exc:  # noqa: BLE001 - falha de ligação ao Redis
        logger.warning("redis_unavailable", error=str(exc))
        return False


async def close_redis() -> None:
    await redis_client.aclose()