"""Unit tests for RAG pipeline components."""

import pytest
from src.rag.embeddings import EmbeddingManager
from src.rag.indexer import DocumentIndexer
from src.rag.reranker import CrossEncoderReranker
from src.rag.retriever import ChromaRetriever


@pytest.fixture
def embedder():
    return EmbeddingManager()


@pytest.fixture
def retriever():
    return ChromaRetriever()


@pytest.fixture
def reranker():
    return CrossEncoderReranker()


def test_embedding_dimensions(embedder):
    """Verify embeddings produce unit-normalized vectors matching configured dimensions."""
    vec = embedder.embed_query("Hemoglobin test reference range")
    assert len(vec) == 768
    # Norm should be approximately 1.0
    norm = sum(x * x for x in vec) ** 0.5
    assert abs(norm - 1.0) < 1e-3


def test_indexer_loads_documents():
    """Verify document indexer discovers curated clinical documents."""
    indexer = DocumentIndexer()
    docs = indexer.load_documents()
    assert len(docs) >= 30
    assert any(d["id"] == "hemoglobin" for d in docs)
    assert any("platelet" in d["id"] for d in docs)


def test_retriever_returns_results(retriever):
    """Verify ChromaRetriever returns candidate chunks with metadata."""
    results = retriever.retrieve("What causes elevated WBC white blood cell count?", top_k=5)
    assert len(results) > 0
    top_doc = results[0]
    assert "id" in top_doc
    assert "text" in top_doc
    assert "metadata" in top_doc
    assert "source_url" in top_doc["metadata"]


def test_reranker_reorders_candidates(reranker):
    """Verify CrossEncoderReranker ranks the most relevant chunk first."""
    query = "What does high creatinine mean for kidney function?"
    mock_candidates = [
        {"id": "lipid_panel", "text": "Cholesterol and triglycerides are lipids stored in fat cells."},
        {"id": "serum_creatinine", "text": "Creatinine is a waste product filtered by the kidneys. High creatinine indicates kidney dysfunction."},
        {"id": "hemoglobin", "text": "Hemoglobin is an iron-rich protein in red blood cells that carries oxygen."},
    ]
    reranked = reranker.rerank(query, mock_candidates, top_n=3)
    assert len(reranked) == 3
    assert reranked[0]["id"] == "serum_creatinine"
    assert reranked[0]["rerank_score"] > reranked[1]["rerank_score"]


def test_extract_embedding_vector():
    """Verify safe extraction of embedding vectors from google-genai response objects."""
    from src.rag.embeddings import _extract_embedding_vector

    # Modern google-genai format: res.embeddings[0].values
    class MockContentEmbedding:
        def __init__(self, values):
            self.values = values

    class MockEmbedResponsePlural:
        def __init__(self, values):
            self.embeddings = [MockContentEmbedding(values)]

    mock_resp = MockEmbedResponsePlural([0.1, 0.2, 0.3])
    vec = _extract_embedding_vector(mock_resp)
    assert vec == [0.1, 0.2, 0.3]

    # Legacy format: res.embedding.values
    class MockEmbedResponseSingular:
        def __init__(self, values):
            self.embedding = MockContentEmbedding(values)

    mock_resp_sing = MockEmbedResponseSingular([0.4, 0.5])
    assert _extract_embedding_vector(mock_resp_sing) == [0.4, 0.5]
