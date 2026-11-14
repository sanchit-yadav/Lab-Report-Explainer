"""Embedding management for RAG knowledge base.

Uses Gemini Embedding 2 (gemini-embedding-2, 768-dim) via the google-genai SDK,
with a deterministic local fallback for offline evaluation and testing.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
from typing import List, Optional

from src.config import EmbeddingsConfig, get_config

logger = logging.getLogger("embeddings")


def _extract_embedding_vector(res: Any) -> Optional[List[float]]:
    """Safely extract vector values from google-genai EmbedContentResponse."""
    if hasattr(res, "embeddings") and res.embeddings:
        first = res.embeddings[0]
        if hasattr(first, "values") and first.values is not None:
            return list(first.values)
    if hasattr(res, "embedding"):
        emb = res.embedding
        if hasattr(emb, "values") and emb.values is not None:
            return list(emb.values)
        if isinstance(emb, list):
            return list(emb)
    return None


class EmbeddingManager:
    """Produces 768-dimensional dense vectors for documents and queries."""

    def __init__(self, config: Optional[EmbeddingsConfig] = None):
        self.config = config or get_config().rag.embeddings
        self.dimensions = self.config.dimensions
        self.api_key = os.environ.get("GEMINI_API_KEY") or get_config().gemini_api_key

    def _fallback_embed(self, text: str) -> List[float]:
        """Deterministic semantic vector generation for offline testing.

        Produces a normalized 768-dim dense embedding derived from token n-grams
        and semantic hashing, ensuring fast, reproducible offline tests without API keys.
        """
        words = text.lower().split()
        vec = [0.0] * self.dimensions

        for i, word in enumerate(words):
            h = int(hashlib.sha256(word.encode("utf-8")).hexdigest(), 16)
            # Map into dimensions
            dim_idx = h % self.dimensions
            weight = 1.0 / (1.0 + math.log(i + 1))
            vec[dim_idx] += weight

            # Bigram influence
            if i > 0:
                bigram = f"{words[i-1]}_{word}"
                bh = int(hashlib.md5(bigram.encode("utf-8")).hexdigest(), 16)
                b_idx = bh % self.dimensions
                vec[b_idx] += weight * 0.75

        # Normalize to unit length (L2 norm)
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of reference documents."""
        if not texts:
            return []

        if self.api_key:
            try:
                from google import genai
                from google.genai import types

                client = genai.Client(api_key=self.api_key)
                embeddings: List[List[float]] = []

                for text in texts:
                    res = client.models.embed_content(
                        model=self.config.model,
                        contents=text,
                        config=types.EmbedContentConfig(
                            task_type=self.config.doc_task_type,
                            output_dimensionality=self.dimensions,
                        ),
                    )
                    # Extract values safely across google-genai versions
                    vec = _extract_embedding_vector(res)
                    if vec:
                        embeddings.append(vec)
                    else:
                        embeddings.append(self._fallback_embed(text))

                return embeddings
            except Exception as e:
                logger.warning(f"Gemini API embedding call failed ({e}); using offline fallback embedder.")

        return [self._fallback_embed(t) for t in texts]

    def embed_query(self, query: str) -> List[float]:
        """Embed a single patient/clinician search query."""
        if self.api_key:
            try:
                from google import genai
                from google.genai import types

                client = genai.Client(api_key=self.api_key)
                res = client.models.embed_content(
                    model=self.config.model,
                    contents=query,
                    config=types.EmbedContentConfig(
                        task_type=self.config.task_type,
                        output_dimensionality=self.dimensions,
                    ),
                )
                vec = _extract_embedding_vector(res)
                if vec:
                    return vec
            except Exception as e:
                logger.warning(f"Gemini API query embedding failed ({e}); using offline fallback embedder.")

        return self._fallback_embed(query)
