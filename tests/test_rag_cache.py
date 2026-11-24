"""Tests for RAGCacheManager and retrieval optimization."""

import time

from src.rag.cache import RAGCacheManager
from src.stages.retrieve import RetrieveStage
from src.stages.schemas import RetrieveInput


def test_rag_cache_basic_put_get():
    """Verify basic put, get, hit count, and miss count."""
    cache = RAGCacheManager(maxsize=10, ttl_seconds=60)
    cache.clear()

    # Initial miss
    val = cache.get("glucose high", top_k=3, top_n=2)
    assert val is None
    assert cache.misses == 1
    assert cache.hits == 0

    # Store entry
    mock_data = [{"id": "chunk_1", "text": "Fasting glucose reference range"}]
    cache.put("glucose high", top_k=3, top_n=2, data=mock_data)

    # Cache hit
    val2 = cache.get("glucose high", top_k=3, top_n=2)
    assert val2 == mock_data
    assert cache.hits == 1
    assert cache.misses == 1
    assert cache.hit_ratio == 0.5


def test_rag_cache_ttl_expiration():
    """Verify TTL expiry evicts stale queries."""
    cache = RAGCacheManager(maxsize=10, ttl_seconds=1)
    cache.clear()

    cache.put("hemoglobin low", top_k=3, top_n=2, data=["chunk_hgb"])
    assert cache.get("hemoglobin low", top_k=3, top_n=2) == ["chunk_hgb"]

    # Sleep past TTL
    time.sleep(1.1)
    assert cache.get("hemoglobin low", top_k=3, top_n=2) is None


def test_rag_cache_lru_eviction():
    """Verify LRU capacity bounds and eviction."""
    cache = RAGCacheManager(maxsize=2, ttl_seconds=60)
    cache.clear()

    cache.put("q1", top_k=3, top_n=2, data="res1")
    cache.put("q2", top_k=3, top_n=2, data="res2")
    assert len(cache._cache) == 2

    # Access q1 to make it most recently used
    _ = cache.get("q1", top_k=3, top_n=2)

    # Adding q3 should evict q2 (least recently used)
    cache.put("q3", top_k=3, top_n=2, data="res3")
    assert len(cache._cache) == 2
    assert cache.get("q2", top_k=3, top_n=2) is None
    assert cache.get("q1", top_k=3, top_n=2) == "res1"
    assert cache.get("q3", top_k=3, top_n=2) == "res3"


def test_stage_retrieve_caching():
    """Verify RetrieveStage leverages cache on repeat queries."""
    stage = RetrieveStage()
    stage.cache.clear()

    inp = RetrieveInput(
        request_id="req-cache-test",
        queries=["fasting blood glucose high lab test meaning"],
        top_k=3,
        top_n=2,
    )

    # Run 1: Cache miss, ChromaDB retrieval + rerank
    t0 = time.perf_counter()
    res1 = stage(inp)
    dur1 = time.perf_counter() - t0
    assert res1.total_chunks > 0

    # Run 2: Cache hit
    t1 = time.perf_counter()
    res2 = stage(inp)
    dur2 = time.perf_counter() - t1

    assert res2.total_chunks == res1.total_chunks
    # Second run should be substantially faster due to caching
    assert dur2 < dur1 or dur2 < 0.05
    assert stage.cache.hits >= 1
