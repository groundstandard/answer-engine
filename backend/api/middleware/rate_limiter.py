import time
from fastapi import HTTPException, Request, status
from backend.config.settings import settings


class RateLimiter:
    """Simple in-memory rate limiter (Redis-backed in production)."""

    def __init__(self):
        self._counts: dict[str, tuple[int, float]] = {}

    async def check(self, request: Request) -> None:
        key = request.client.host if request.client else "unknown"
        now = time.time()
        window = 60.0
        limit = settings.rate_limit_per_minute

        count, window_start = self._counts.get(key, (0, now))
        if now - window_start > window:
            count, window_start = 0, now

        if count >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Try again in 60 seconds.",
            )

        self._counts[key] = (count + 1, window_start)


rate_limiter = RateLimiter()
