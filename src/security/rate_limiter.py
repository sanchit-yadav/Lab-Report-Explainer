"""In-memory sliding window rate limiter for FastAPI microservices.

Protects sensitive endpoints (e.g. login, file uploads) against brute-force
and denial-of-service attempts without external dependencies.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import defaultdict
from typing import Dict, List

from fastapi import HTTPException, Request, status

logger = logging.getLogger("rate_limiter")


class SlidingWindowRateLimiter:
    """Thread-safe in-memory sliding window rate limiter."""

    def __init__(self, times: int = 10, seconds: int = 60, name: str = "default"):
        """
        Args:
            times: Maximum allowed requests within the time window.
            seconds: Window size in seconds.
            name: Limiter identifier for metrics/logs.
        """
        self.times = times
        self.seconds = seconds
        self.name = name
        self._history: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def _get_client_identifier(self, request: Request) -> str:
        """Derive client IP from X-Forwarded-For (proxy/load balancer) or direct client host."""
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # First IP in comma-separated chain is original client IP
            return forwarded.split(",")[0].strip()
        if request.client and request.client.host:
            return request.client.host
        return "127.0.0.1"

    def is_disabled(self) -> bool:
        """Check if rate limiting is globally disabled via environment toggle."""
        return os.environ.get("DISABLE_RATE_LIMITING", "").lower() in ("1", "true", "yes")

    def reset(self) -> None:
        """Reset all tracked request history (useful for unit tests)."""
        with self._lock:
            self._history.clear()

    def __call__(self, request: Request) -> None:
        """FastAPI dependency evaluation callable."""
        if self.is_disabled():
            return

        client_id = self._get_client_identifier(request)
        now = time.time()
        window_start = now - self.seconds

        with self._lock:
            # Purge timestamps outside the active window
            recent = [ts for ts in self._history[client_id] if ts > window_start]

            if len(recent) >= self.times:
                oldest = recent[0]
                retry_after = max(1, int(self.seconds - (now - oldest)))
                logger.warning(
                    f"Rate limit exceeded on '{self.name}' by client {client_id} "
                    f"({len(recent)}/{self.times} in {self.seconds}s). Retry-After: {retry_after}s"
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too Many Requests: Rate limit exceeded for {self.name}. Please retry in {retry_after} seconds.",
                    headers={"Retry-After": str(retry_after)},
                )

            recent.append(now)
            self._history[client_id] = recent
