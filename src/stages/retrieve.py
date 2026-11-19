"""Stage 4: Knowledge Retrieval & Reranking (retrieve).

Executes semantic similarity search on the MedlinePlus clinical vector store
in ChromaDB, followed by cross-encoder re-ranking for contextual precision.
"""

from __future__ import annotations

import time
from typing import Dict, List

from src.config import get_config
from src.rag.reranker import CrossEncoderReranker
from src.rag.retriever import ChromaRetriever
from src.stages.logger import get_stage_logger
from src.stages.schemas import RetrievedChunk, RetrieveInput, RetrieveOutput

logger = get_stage_logger("retrieve")


class RetrieveStage:
    """Independently callable stage retrieving and reranking evidence from clinical knowledge bases."""

    def __init__(self):
        self.config = get_config().rag
        self.retriever = ChromaRetriever(self.config)
        self.reranker = CrossEncoderReranker(self.config.reranker)

    def __call__(self, inp: RetrieveInput) -> RetrieveOutput:
        return self.retrieve(inp)

    def retrieve(self, inp: RetrieveInput) -> RetrieveOutput:
        t0 = time.perf_counter()
        chunks_by_query: Dict[str, List[RetrievedChunk]] = {}
        total_chunks = 0

        for query in inp.queries:
            # 1. Bi-encoder ChromaDB retrieval
            candidates = self.retriever.retrieve(query, top_k=inp.top_k)

            # 2. Cross-Encoder re-ranking
            reranked = self.reranker.rerank(query, candidates, top_n=inp.top_n)

            query_chunks: List[RetrievedChunk] = []
            for item in reranked:
                chunk = RetrievedChunk(
                    chunk_id=item.get("id", f"chunk_{total_chunks}"),
                    doc_id=item.get("metadata", {}).get("source_file", item.get("id", "doc")),
                    title=item.get("metadata", {}).get("title", query),
                    text=item.get("text", ""),
                    score=float(item.get("score", 0.0)),
                    source_url=item.get("metadata", {}).get("source_url") or item.get("source_url"),
                )
                query_chunks.append(chunk)
                total_chunks += 1

            chunks_by_query[query] = query_chunks

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "Knowledge retrieval complete",
            inp.request_id,
            {
                "query_count": len(inp.queries),
                "total_chunks_retrieved": total_chunks,
                "elapsed_ms": round(elapsed_ms, 2),
            },
        )

        return RetrieveOutput(
            request_id=inp.request_id,
            chunks_by_query=chunks_by_query,
            total_chunks=total_chunks,
        )


def retrieve(inp: RetrieveInput) -> RetrieveOutput:
    """Functional convenience entrypoint for Stage 4."""
    return RetrieveStage()(inp)
