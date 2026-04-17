"""Rate limiting (sliding window) with Redis storage."""
from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque

from fastapi import HTTPException


class RateLimiter:
    def __init__(self, *, max_requests: int, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._fallback_windows: dict[str, deque[float]] = defaultdict(deque)

    def check(self, user_id: str, redis_client=None) -> dict:
        """
        Validate the current request for a user.
        Raises 429 when over limit.
        """
        return (
            self._check_with_redis(user_id, redis_client)
            if redis_client is not None
            else self._check_in_memory(user_id)
        )

    def _check_with_redis(self, user_id: str, redis_client) -> dict:
        now = time.time()
        window_start = now - self.window_seconds
        key = f"ratelimit:{user_id}"

        pipe = redis_client.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        pipe.expire(key, self.window_seconds + 10)
        _, count, _ = pipe.execute()

        if count >= self.max_requests:
            oldest = redis_client.zrange(key, 0, 0, withscores=True)
            retry_after = 1
            if oldest:
                retry_after = max(1, int(oldest[0][1] + self.window_seconds - now) + 1)
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Rate limit exceeded",
                    "limit": self.max_requests,
                    "window_seconds": self.window_seconds,
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        member = f"{now}:{uuid.uuid4().hex}"
        redis_client.zadd(key, {member: now})
        redis_client.expire(key, self.window_seconds + 10)
        return {
            "limit": self.max_requests,
            "remaining": self.max_requests - (count + 1),
            "window_seconds": self.window_seconds,
        }

    def _check_in_memory(self, user_id: str) -> dict:
        now = time.time()
        window = self._fallback_windows[user_id]
        while window and window[0] <= now - self.window_seconds:
            window.popleft()
        if len(window) >= self.max_requests:
            retry_after = max(1, int(window[0] + self.window_seconds - now) + 1)
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Rate limit exceeded",
                    "limit": self.max_requests,
                    "window_seconds": self.window_seconds,
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )
        window.append(now)
        return {
            "limit": self.max_requests,
            "remaining": self.max_requests - len(window),
            "window_seconds": self.window_seconds,
        }

