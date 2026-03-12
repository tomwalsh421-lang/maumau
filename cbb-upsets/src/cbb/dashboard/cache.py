"""Small TTL cache helpers for the local dashboard service layer."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass
class _CacheEntry(Generic[T]):
    fresh_until: float
    stale_until: float
    value: T


class TtlCache:
    """Thread-safe in-memory TTL cache for local dashboard payloads."""

    def __init__(self) -> None:
        self._entries: dict[str, _CacheEntry[object]] = {}
        self._lock = Lock()

    def clear(self) -> None:
        """Drop all stored cache entries."""
        with self._lock:
            self._entries.clear()

    def peek(self, key: str) -> object | None:
        """Return a cached value when it is still fresh."""
        now = monotonic()
        with self._lock:
            cached = self._entries.get(key)
            if cached is None:
                return None
            if cached.stale_until <= now:
                self._entries.pop(key, None)
                return None
            if cached.fresh_until <= now:
                return None
            return cached.value

    def peek_stale(self, key: str) -> object | None:
        """Return a cached value while it remains inside its stale window."""
        now = monotonic()
        with self._lock:
            cached = self._entries.get(key)
            if cached is None:
                return None
            if cached.stale_until <= now:
                self._entries.pop(key, None)
                return None
            return cached.value

    def set(
        self,
        key: str,
        *,
        ttl_seconds: int,
        stale_ttl_seconds: int = 0,
        value: T,
    ) -> T:
        """Store a value under an explicit TTL."""
        fresh_until = monotonic() + max(ttl_seconds, 0)
        stale_until = fresh_until + max(stale_ttl_seconds, 0)
        with self._lock:
            self._entries[key] = _CacheEntry(
                fresh_until=fresh_until,
                stale_until=stale_until,
                value=value,
            )
        return value

    def get_or_set(
        self,
        key: str,
        *,
        ttl_seconds: int,
        loader: Callable[[], T],
    ) -> T:
        """Return a cached value or compute and store it."""
        cached = self.peek(key)
        if cached is not None:
            return cached  # type: ignore[return-value]
        value = loader()
        return self.set(key, ttl_seconds=ttl_seconds, value=value)
