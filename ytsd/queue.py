"""RQ queue accessor.

RQ stores its own data as bytes and must NOT use a decode_responses connection
(that is reserved for our human-readable status hash in store.py), so it gets a
dedicated raw connection here.
"""
from __future__ import annotations

from typing import Optional

import redis
from rq import Queue

from .config import settings

_raw: Optional[redis.Redis] = None


def get_redis_raw() -> redis.Redis:
    global _raw
    if _raw is None:
        _raw = redis.Redis.from_url(settings.redis_url)
    return _raw


def get_queue() -> Queue:
    return Queue(
        settings.queue_name,
        connection=get_redis_raw(),
        default_timeout=settings.job_timeout,
    )
