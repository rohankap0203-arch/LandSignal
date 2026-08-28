"""Search / provider diagnostics (dev observability)."""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from typing import Any


class SearchDiagnostics:
    def __init__(self, maxlen: int = 40):
        self._lock = threading.Lock()
        self._events: deque[dict[str, Any]] = deque(maxlen=maxlen)

    def record(self, event: dict[str, Any]) -> str:
        eid = event.get("search_id") or str(uuid.uuid4())
        payload = {
            **event,
            "search_id": eid,
            "recorded_at": time.time(),
        }
        with self._lock:
            self._events.appendleft(payload)
        return eid

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._events)[:limit]

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


DIAGNOSTICS = SearchDiagnostics()
