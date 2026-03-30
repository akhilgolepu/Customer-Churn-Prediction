import json
import time
from collections import defaultdict, deque

from core.settings import get_settings

try:
    import redis
except Exception:  # pragma: no cover
    redis = None


class CacheClient:
    def __init__(self) -> None:
        settings = get_settings()
        self._local_rate_hits: dict[str, deque[float]] = defaultdict(deque)
        self._local_kv: dict[str, tuple[float, str]] = {}
        self._redis = None

        if settings.redis_enabled and redis is not None:
            self._redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)

    @property
    def redis_client(self):
        return self._redis

    def incr_with_expiry(self, key: str, ttl_seconds: int) -> int:
        if self._redis:
            pipeline = self._redis.pipeline()
            pipeline.incr(key)
            pipeline.expire(key, ttl_seconds)
            value, _ = pipeline.execute()
            return int(value)

        now = time.time()
        queue = self._local_rate_hits[key]
        while queue and (now - queue[0]) > ttl_seconds:
            queue.popleft()
        queue.append(now)
        return len(queue)

    def set_json(self, key: str, value: dict, ttl_seconds: int) -> None:
        payload = json.dumps(value)
        if self._redis:
            self._redis.setex(key, ttl_seconds, payload)
            return
        self._local_kv[key] = (time.time() + ttl_seconds, payload)

    def get_json(self, key: str) -> dict | None:
        if self._redis:
            data = self._redis.get(key)
            return json.loads(data) if data else None

        item = self._local_kv.get(key)
        if not item:
            return None
        expires_at, payload = item
        if expires_at < time.time():
            self._local_kv.pop(key, None)
            return None
        return json.loads(payload)


cache_client = CacheClient()
