"""Job status stored in a small Redis hash, shared by web and worker.

The RQ job id is reused as the public job id. Progress/stage/result live in
`ytsd:job:<id>` with a TTL matching retention, so state self-expires.
"""
from __future__ import annotations

from typing import Optional

import redis

from .config import settings

_pool: Optional[redis.Redis] = None


def get_redis() -> redis.Redis:
    global _pool
    if _pool is None:
        _pool = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return _pool


def _key(job_id: str) -> str:
    return f"ytsd:job:{job_id}"


def set_status(job_id: str, **fields) -> None:
    """Merge fields into the job hash and refresh its TTL."""
    conn = get_redis()
    mapping = {k: ("" if v is None else str(v)) for k, v in fields.items()}
    key = _key(job_id)
    conn.hset(key, mapping=mapping)
    conn.expire(key, int(settings.retention_seconds) + 300)


def get_status(job_id: str) -> Optional[dict]:
    data = get_redis().hgetall(_key(job_id))
    return data or None
