"""
Redis client for caching insights data.
"""

import json
from typing import Optional

import redis

from logging_config import get_logger
from config import REDIS_URL

logger = get_logger(__name__, service="redis")

INSIGHTS_TTL = 86400  # 24 hours

_redis_client: Optional[redis.Redis] = None


def get_redis() -> Optional[redis.Redis]:
    """Get Redis connection, lazy-initialized."""
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
            _redis_client.ping()
            logger.info("Redis connected")
        except Exception as e:
            logger.warning(f"Redis not available: {e}")
            _redis_client = None
    return _redis_client


def get_insight(place_id: str, section: str) -> Optional[dict]:
    """Get a cached insight section. Returns None on miss or error."""
    r = get_redis()
    if not r:
        return None
    try:
        data = r.get(f"insights:{place_id}:{section}")
        if data:
            return json.loads(data)
    except Exception as e:
        logger.warning(f"Redis get error: {e}")
    return None


def set_insight(place_id: str, section: str, data: dict, ttl: int = INSIGHTS_TTL):
    """Cache an insight section."""
    r = get_redis()
    if not r:
        return
    try:
        r.setex(f"insights:{place_id}:{section}", ttl, json.dumps(data, default=str))
    except Exception as e:
        logger.warning(f"Redis set error: {e}")


def invalidate_insights(place_id: str):
    """Delete all cached insight sections for a place."""
    r = get_redis()
    if not r:
        return
    try:
        keys = r.keys(f"insights:{place_id}:*")
        if keys:
            r.delete(*keys)
            logger.info(f"Invalidated {len(keys)} insight cache keys for place {place_id}")
    except Exception as e:
        logger.warning(f"Redis invalidate error: {e}")
