"""Thread-safe in-memory TTL cache.

`cachetools.TTLCache` is not thread-safe, and the `if key in cache: return
cache[key]` idiom is a check-then-act race (the entry can expire between the
two calls and raise KeyError). `TTLStore` exposes atomic `get` / `set` guarded
by a lock instead.
"""

import threading
from collections.abc import Hashable
from typing import Any

from cachetools import TTLCache


class TTLStore:
    def __init__(self, maxsize: int, ttl: float) -> None:
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)
        self._lock = threading.Lock()

    def get(self, key: Hashable, default: Any = None) -> Any:
        with self._lock:
            return self._cache.get(key, default)

    def set(self, key: Hashable, value: Any) -> None:
        with self._lock:
            self._cache[key] = value

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

