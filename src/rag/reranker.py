"""Cross-Encoder Re-Ranker using ms-marco-MiniLM-L-6-v2.

Refines initial bi-encoder vector similarity candidates by evaluating
full cross-attention across (query, candidate_document) pairs.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.config import RerankerConfig, get_config

logger = logging.getLogger("reranker")


class CrossEncoderReranker:
    """Joint cross-attention re-ranking for clinical search candidates."""

    def __init__(self, config: Optional[RerankerConfig] = None):
        self.config = config or get_config().rag.reranker
        self.enabled = self.config.enabled
        self.model_name = self.config.model
        self.top_n = self.config.top_n
        self._model = None

    def _get_model(self):
        """Lazy load CrossEncoder to conserve memory and initialization time."""
        if self._model is None and self.enabled:
            try:
                import os
                from sentence_transformers import CrossEncoder

                # Try local cached files first for speed and offline stability
                try:
                    self._model = CrossEncoder(self.model_name, local_files_only=True)
                except Exception:
                    self._model = CrossEncoder(self.model_name)
            except Exception as e:
                logger.warning(f"Could not initialize CrossEncoder ({e}). Re-ranking will pass-through.")
                self.enabled = False
        return self._model

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
