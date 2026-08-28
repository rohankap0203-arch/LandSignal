"""ATTOM-compliant temporary response cache (TTL ≤ 24h) + circuit breaker."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from landsignal.services.property_providers import IntelligenceProviderState


# Hard ceiling under ATTOM trial / API retention terms
ATTOM_MAX_TTL_SECONDS = 24 * 60 * 60  # 86400


@dataclass
class CacheEntry:
    value: Any
    expires_at: float
    retrieved_at: float
    source: str = "ATTOM"
    persistence_policy: str = "TEMPORARY_LICENSED"


class AttomResponseCache:
    """In-process TTL cache. Never persists ATTOM payloads to durable DB."""

    def __init__(self, ttl_seconds: int = 82_800):
        self.ttl_seconds = max(60, min(int(ttl_seconds), ATTOM_MAX_TTL_SECONDS))
        self._lock = threading.Lock()
        self._store: dict[str, CacheEntry] = {}
        self.hits = 0
        self.misses = 0

    def _key(self, method: str, path: str, params: dict[str, Any] | None) -> str:
        blob = json.dumps({"m": method, "p": path, "q": params or {}}, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()

    def get(self, method: str, path: str, params: dict[str, Any] | None) -> Any | None:
        key = self._key(method, path, params)
        now = time.time()
        with self._lock:
            self._purge_locked(now)
            entry = self._store.get(key)
            if not entry:
                self.misses += 1
                return None
            if entry.expires_at <= now:
                self._store.pop(key, None)
                self.misses += 1
                return None
            self.hits += 1
            return entry.value

    def set(self, method: str, path: str, params: dict[str, Any] | None, value: Any) -> None:
        key = self._key(method, path, params)
        now = time.time()
        with self._lock:
            self._store[key] = CacheEntry(
                value=value,
                expires_at=now + self.ttl_seconds,
                retrieved_at=now,
            )

    def purge_expired(self) -> int:
        now = time.time()
        with self._lock:
            return self._purge_locked(now)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def _purge_locked(self, now: float) -> int:
        dead = [k for k, v in self._store.items() if v.expires_at <= now]
        for k in dead:
            self._store.pop(k, None)
        return len(dead)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "entries": len(self._store),
                "hits": self.hits,
                "misses": self.misses,
                "ttl_seconds": self.ttl_seconds,
                "hit_rate": (self.hits / (self.hits + self.misses)) if (self.hits + self.misses) else None,
            }


@dataclass
class CircuitBreaker:
    """Open circuit after repeated ATTOM failures to protect Show Matches."""

    failure_threshold: int = 5
    reset_seconds: float = 120.0
    failures: int = 0
    opened_at: float | None = None
    state: IntelligenceProviderState = IntelligenceProviderState.AVAILABLE
    last_error: str | None = None
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def allow_request(self) -> bool:
        with self._lock:
            if self.opened_at is None:
                return True
            if time.time() - self.opened_at >= self.reset_seconds:
                # half-open probe window
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            self.failures = 0
            self.opened_at = None
            self.state = IntelligenceProviderState.AVAILABLE
            self.last_error = None

    def record_failure(self, state: IntelligenceProviderState, error: str | None = None) -> None:
        with self._lock:
            self.failures += 1
            self.state = state
            self.last_error = (error or "")[:240] or None
            if self.failures >= self.failure_threshold:
                self.opened_at = time.time()
                if self.state == IntelligenceProviderState.AVAILABLE:
                    self.state = IntelligenceProviderState.UNAVAILABLE

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            open_now = self.opened_at is not None and (
                time.time() - self.opened_at < self.reset_seconds
            )
            return {
                "state": self.state.value,
                "failures": self.failures,
                "open": open_now,
                "last_error": self.last_error,
            }
