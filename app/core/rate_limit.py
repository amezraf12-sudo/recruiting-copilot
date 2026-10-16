"""In-memory rate limiting that protects the LLM budget of a public demo.

Two sliding windows: per client IP per hour, and a global cap per day. State lives in
process memory, so it resets on restart; fine for a single-instance demo, not for a
horizontally scaled deployment (use Redis there).
"""

import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request

from app import config

HOUR = 3600
DAY = 86400


class RateLimiter:
    def __init__(self, per_ip_per_hour: int, global_per_day: int, clock=time.monotonic):
        self.per_ip_per_hour = per_ip_per_hour
        self.global_per_day = global_per_day
        self.clock = clock
        self._by_ip: dict[str, deque[float]] = defaultdict(deque)
        self._global: deque[float] = deque()

    @staticmethod
    def _prune(window: deque[float], now: float, span: int) -> None:
        while window and now - window[0] >= span:
            window.popleft()

    def check(self, client_ip: str, cost: int = 1) -> None:
        """Record `cost` LLM calls, or raise 429 (recording nothing) if a limit would be exceeded."""
        now = self.clock()
        ip_window = self._by_ip[client_ip]
        self._prune(ip_window, now, HOUR)
        self._prune(self._global, now, DAY)
        if len(self._global) + cost > self.global_per_day:
            raise HTTPException(status_code=429, detail="Demo daily limit reached; try tomorrow.")
        if len(ip_window) + cost > self.per_ip_per_hour:
            raise HTTPException(status_code=429, detail="Too many requests; try again later.")
        ip_window.extend([now] * cost)
        self._global.extend([now] * cost)


_limiter = RateLimiter(config.RATE_LIMIT_PER_IP_PER_HOUR, config.RATE_LIMIT_GLOBAL_PER_DAY)


def get_limiter() -> RateLimiter:
    """Dependency so tests can swap in a fresh limiter."""
    return _limiter


def client_ip(request: Request) -> str:
    # Behind Render's proxy the real client is the first X-Forwarded-For entry.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(request: Request, limiter: RateLimiter = Depends(get_limiter)) -> None:
    """FastAPI dependency for routes that make one LLM call."""
    limiter.check(client_ip(request))
