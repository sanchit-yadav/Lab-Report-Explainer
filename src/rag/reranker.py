"""Cross-Encoder Re-Ranker using ms-marco-MiniLM-L-6-v2.

Refines initial bi-encoder vector similarity candidates by evaluating
full cross-attention across (query, candidate_document) pairs.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, List, Optional

from src.config import RerankerConfig, get_config

logger = logging.getLogger("reranker")


class CrossEncoderReranker:
    """Joint cross-attention re-ranking for clinical search candidates."""

    _model_cache: Dict[str, Any] = {}
    _lock = threading.Lock()

    def __init__(self, config: Optional[RerankerConfig] = None):
        self.config = config or get_config().rag.reranker
        self.enabled = self.config.enabled
        # Allow environment override to save memory / avoid CPU cross-attention bottlenecks on low-spec hosting
        if os.environ.get("DISABLE_CROSS_ENCODER", "").lower() in ("1", "true", "yes"):
            self.enabled = False
        self.model_name = self.config.model
        self.top_n = self.config.top_n
        self._model = None

    def _get_model(self):
        """Lazy load CrossEncoder with thread-safe singleton cache to conserve memory and speed."""
        if not self.enabled:
            return None
        if self.model_name in self._model_cache:
            return self._model_cache[self.model_name]

        with self._lock:
            if self.model_name in self._model_cache:
                return self._model_cache[self.model_name]
            try:
                from sentence_transformers import CrossEncoder

                # Try local cached files first for speed and offline stability
                try:
                    model = CrossEncoder(self.model_name, local_files_only=True)
                except Exception:
                    model = CrossEncoder(self.model_name)
                self._model_cache[self.model_name] = model
                self._model = model
            except Exception as e:
                logger.warning(f"Could not initialize CrossEncoder ({e}). Re-ranking will pass-through.")
                self.enabled = False
        return self._model_cache.get(self.model_name)

    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_n: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Re-rank candidate documents based on cross-encoder scoring.

        Args:
            query: Clinical query string.
            candidates: Retrieved candidate dictionaries from vector search.
            top_n: Number of final chunks to return (defaults to config top_n).

        Returns:
            Sorted list of top_n candidates with 'rerank_score' attached.
        """
        n = top_n or self.top_n
        if not candidates:
            return []

        if not self.enabled:
            return candidates[:n]

        model = self._get_model()
        if model is None:
            return candidates[:n]

        # Prepare sentence pairs for cross-encoder
        pairs = [[query, c.get("text", "")] for c in candidates]

        try:
            scores = model.predict(pairs)
            for idx, candidate in enumerate(candidates):
                candidate["rerank_score"] = float(scores[idx])

            # Sort descending by re-ranker score
            sorted_candidates = sorted(
                candidates,
                key=lambda x: x.get("rerank_score", 0.0),
                reverse=True,
            )
            return sorted_candidates[:n]
        except Exception as e:
            logger.warning(f"Error during cross-encoder re-ranking: {e}. Falling back to vector ranking.")
            return candidates[:n]

    def rerank_batch(
        self,
        batch_items: List[Tuple[str, List[Dict[str, Any]]]],
        top_n: Optional[int] = None,
    ) -> List[List[Dict[str, Any]]]:
        """Batched re-ranking for multiple queries in a single vectorized forward pass.

        Args:
            batch_items: List of (query_str, candidate_list) pairs.
            top_n: Maximum chunks to return per query.

        Returns:
            List of sorted candidate lists per query.
        """
        n = top_n or self.top_n
        if not batch_items:
            return []

        if not self.enabled:
            return [cands[:n] for _, cands in batch_items]

        model = self._get_model()
        if model is None:
            return [cands[:n] for _, cands in batch_items]

        all_pairs = []
        indices_map = []  # (item_idx, cand_idx)
        for item_idx, (query, cands) in enumerate(batch_items):
            for cand_idx, c in enumerate(cands):
                all_pairs.append([query, c.get("text", "")])
                indices_map.append((item_idx, cand_idx))

        if not all_pairs:
            return [cands[:n] for _, cands in batch_items]

        try:
            scores = model.predict(all_pairs, batch_size=32)
            for (item_idx, cand_idx), score in zip(indices_map, scores):
                batch_items[item_idx][1][cand_idx]["rerank_score"] = float(score)

            results = []
            for _, cands in batch_items:
                sorted_c = sorted(cands, key=lambda x: x.get("rerank_score", 0.0), reverse=True)
                results.append(sorted_c[:n])
            return results
        except Exception as e:
            logger.warning(f"Error during batched cross-encoder re-ranking: {e}. Falling back to unranked.")
            return [cands[:n] for _, cands in batch_items]
