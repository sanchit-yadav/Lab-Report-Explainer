"""Retriever executing semantic search across indexed clinical documents in ChromaDB."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.api.models.Collection import Collection

from src.config import RAGConfig, get_config
from src.rag.embeddings import EmbeddingManager

logger = logging.getLogger("retriever")
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class ChromaRetriever:
    """Executes similarity search on ChromaDB for clinical test queries."""

    def __init__(self, config: Optional[RAGConfig] = None):
        self.config = config or get_config().rag
        self.embedder = EmbeddingManager(self.config.embeddings)
        persist_path = (PROJECT_ROOT / self.config.vector_store.persist_directory).resolve()
        persist_path.mkdir(parents=True, exist_ok=True)
        self.chroma_client = chromadb.PersistentClient(path=str(persist_path))
        self.collection_name = self.config.vector_store.collection_name
        self.collection: Collection = self.chroma_client.get_or_create_collection(
            name=self.collection_name
        )
        if self.collection.count() == 0:
            logger.info("ChromaDB collection is empty. Auto-indexing data/rag_sources...")
            try:
                from src.rag.indexer import DocumentIndexer
                indexer = DocumentIndexer(self.config)
                indexer.index_all()
                logger.info(f"Auto-indexed {self.collection.count()} clinical guidelines.")
            except Exception as e:
                logger.warning(f"Could not auto-populate ChromaDB: {e}")

        # Detect whether the persistent collection was indexed using dense neural or sparse fallback embeddings
        self._is_sparse_collection = False
        try:
            sample = self.collection.get(limit=1, include=["embeddings"])
            if (
                sample is not None
                and sample.get("embeddings") is not None
                and len(sample["embeddings"]) > 0
            ):
                first_emb = sample["embeddings"][0]
                zeros_count = sum(1 for x in first_emb if x == 0.0)
                if zeros_count > 200:
                    self._is_sparse_collection = True
                    logger.debug("Detected sparse fallback embeddings in ChromaDB; aligning query embedder.")
        except Exception as e:
            logger.debug(f"Could not inspect collection embedding density: {e}")

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve candidate document chunks for a query string.

        Args:
            query: The patient or analyte search string.
            top_k: Number of candidate chunks to retrieve (defaults to config).
            filter_metadata: Optional ChromaDB metadata filter dictionary.

        Returns:
            List of candidate dictionaries with id, text, metadata, and distance.
        """
        k = top_k or self.config.retrieval.top_k
        if not query.strip():
            return []

        # Embed query in aligned vector space
        if getattr(self, "_is_sparse_collection", False):
            query_embedding = self.embedder._fallback_embed(query)
        else:
            query_embedding = self.embedder.embed_query(query)

        # ChromaDB query
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=k,
            where=filter_metadata,
            include=["documents", "metadatas", "distances"],
        )

        candidates: List[Dict[str, Any]] = []
        if not results or not results.get("ids") or not results["ids"][0]:
            return candidates

        ids = results["ids"][0]
        documents = results["documents"][0] if results.get("documents") else []
        metadatas = results["metadatas"][0] if results.get("metadatas") else []
        distances = results["distances"][0] if results.get("distances") else []

        for idx, doc_id in enumerate(ids):
            doc_text = documents[idx] if idx < len(documents) else ""
            doc_meta = metadatas[idx] if idx < len(metadatas) else {}
            dist = distances[idx] if idx < len(distances) else 1.0

            # Convert distance to similarity score
            # For cosine distance: similarity = 1 - distance
            similarity = max(0.0, 1.0 - dist) if dist <= 1.0 else 1.0 / (1.0 + dist)

            candidates.append({
                "id": doc_id,
                "text": doc_text,
                "metadata": doc_meta,
                "distance": dist,
                "similarity": similarity,
            })

        return candidates
