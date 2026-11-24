"""High-performance thread-safe RAG Query & Reranking Cache.

Eliminates redundant embedding generation and CrossEncoder inference bottlenecks
for standard clinical laboratory queries. Tracks cache hit/miss observability metrics.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("rag_cache")


class RAGCacheManager:
    """Thread-safe LRU cache for clinical vector retrieval and reranking results."""

    _instance: Optional[RAGCacheManager] = None
    _lock = threading.Lock()

    def __init__(self, maxsize: int = 1000, ttl_seconds: int = 86400):
        self.maxsize = maxsize
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, Tuple[float, Any]] = OrderedDict()
        self._access_lock = threading.Lock()

        # Observability metrics
        self.hits = 0
        self.misses = 0

    @classmethod
    def get_instance(cls, maxsize: int = 1000, ttl_seconds: int = 86400) -> RAGCacheManager:
        """Singleton accessor."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(maxsize=maxsize, ttl_seconds=ttl_seconds)
        return cls._instance

    def _make_key(self, query: str, top_k: int, top_n: int) -> str:
        """Create normalized deterministic cache key."""
        return f"{query.strip().lower()}:k={top_k}:n={top_n}"

    def get(self, query: str, top_k: int, top_n: int) -> Optional[Any]:
        """Retrieve cached reranked chunks if present and not expired."""
        key = self._make_key(query, top_k, top_n)
        with self._access_lock:
            if key in self._cache:
                timestamp, data = self._cache[key]
                if time.time() - timestamp < self.ttl_seconds:
                    self._cache.move_to_end(key)
                    self.hits += 1
                    return data
                else:
                    # Expired entry
                    del self._cache[key]
            self.misses += 1
            return None

    def put(self, query: str, top_k: int, top_n: int, data: Any) -> None:
        """Store retrieval results with eviction of oldest entries when full."""
        key = self._make_key(query, top_k, top_n)
        with self._access_lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = (time.time(), data)
            if len(self._cache) > self.maxsize:
                self._cache.popitem(last=False)

    def clear(self) -> None:
        """Reset the cache and metrics."""
        with self._access_lock:
            self._cache.clear()
            self.hits = 0
            self.misses = 0

    @property
    def hit_ratio(self) -> float:
        """Compute the instantaneous cache hit ratio."""
        total = self.hits + self.misses
        return (self.hits / total) if total > 0 else 0.0

    def get_stats(self) -> Dict[str, Any]:
        """Return structured telemetry for cache observability."""
        with self._access_lock:
            return {
                "size": len(self._cache),
                "maxsize": self.maxsize,
                "hits": self.hits,
                "misses": self.misses,
                "hit_ratio": round(self.hit_ratio, 4),
            }
