"""Thread-safe in-memory TTL cache, bounded by entry count or by estimated memory.

`cachetools.TTLCache` is not thread-safe, and the `if key in cache: return
cache[key]` idiom is a check-then-act race (the entry can expire between the
two calls and raise KeyError). `TTLStore` exposes atomic `get` / `set` guarded
by a lock instead.

Analytics results range from 1 KB to several MB, so a bound on the number of
entries says nothing about memory: caches holding such results are bounded in
megabytes (`max_mb`). The size of an entry is estimated from its pickled size;
measured on real results, the in-memory size of these dict/list/float payloads
is ~4-5x the pickle, hence RAM_PER_PICKLED_BYTE.
"""

import logging
import pickle
import threading
from collections.abc import Hashable
from typing import Any

from cachetools import TTLCache

log = logging.getLogger(__name__)

RAM_PER_PICKLED_BYTE = 5


def estimated_size(value: Any) -> int:
    return len(pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)) * RAM_PER_PICKLED_BYTE


class TTLStore:
    def __init__(self, ttl: float, maxsize: int | None = None, max_mb: float | None = None) -> None:
        if (maxsize is None) == (max_mb is None):
            raise ValueError("pass exactly one of maxsize (entries) or max_mb (estimated memory)")
        if max_mb is not None:
            self._cache: TTLCache = TTLCache(maxsize=int(max_mb * 1_000_000), ttl=ttl, getsizeof=estimated_size)
        else:
            self._cache = TTLCache(maxsize=maxsize, ttl=ttl)
        self._lock = threading.Lock()

    def get(self, key: Hashable, default: Any = None) -> Any:
        with self._lock:
            return self._cache.get(key, default)

    def set(self, key: Hashable, value: Any) -> None:
        with self._lock:
            try:
                self._cache[key] = value
            except ValueError:  # a single value larger than the whole budget: serve it, don't cache it
                log.info("result not cached: larger than the cache budget")

    @property
    def currsize(self) -> int:
        """Number of entries, or estimated bytes for a memory-bounded store."""
        with self._lock:
            return int(self._cache.currsize)

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
