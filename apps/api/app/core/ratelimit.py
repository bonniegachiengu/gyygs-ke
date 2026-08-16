"""Per-IP sliding-window rate limiting for POST /api/quote (ARCHITECTURE §5, §11).

Dependency-free: no Redis, no slowapi. Single-process, which is what v1 is; the
class is the seam where a shared backend drops in if this ever runs replicated.
"""

from __future__ import annotations

import threading
import time
from collections import deque

from fastapi import Request

_MINUTE = 60.0
_HOUR = 3600.0


class SlidingWindowLimiter:
    def __init__(self, per_min: int, per_hour: int, *, max_keys: int = 10_000) -> None:
        self.per_min = per_min
        self.per_hour = per_hour
        self.max_keys = max_keys
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int]:
        """(allowed, retry_after_seconds)."""
        now = time.monotonic()
        with self._lock:
            self._evict(now)
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] > _HOUR:
                hits.popleft()

            in_hour = len(hits)
            in_minute = sum(1 for t in hits if now - t <= _MINUTE)

            if in_minute >= self.per_min:
                oldest = next(t for t in hits if now - t <= _MINUTE)
                return False, max(1, int(_MINUTE - (now - oldest)) + 1)
            if in_hour >= self.per_hour:
                return False, max(1, int(_HOUR - (now - hits[0])) + 1)

            hits.append(now)
            return True, 0

    def _evict(self, now: float) -> None:
        """Bounded memory, no background task."""
        if len(self._hits) <= self.max_keys:
            return
        stale = [k for k, v in self._hits.items() if not v or now - v[-1] > _HOUR]
        for k in stale:
            del self._hits[k]
        if len(self._hits) > self.max_keys:
            for k in sorted(self._hits, key=lambda k: self._hits[k][-1])[
                : len(self._hits) - self.max_keys
            ]:
                del self._hits[k]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def client_ip(request: Request) -> str:
    """The real customer's IP.

    Order matters. Cloudflare sets CF-Connecting-IP; nginx forwards it plus
    X-Forwarded-For. Without this every request looks like the nginx container
    and one customer would rate-limit the whole of Nairobi.
    """
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        return cf.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
