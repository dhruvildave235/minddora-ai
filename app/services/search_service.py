"""
search_service.py

Business logic for the standalone "Search Notes" page — distinct from
chat_service.py in that it returns a ranked LIST of matching chunks/
documents for the student to browse (like a search engine results page),
rather than a single synthesized answer. Reuses the same hybrid
retrieval machinery (app.ai.retriever) as chat, but exposes additional
filtering (by document, subject, date range) and sorting options that
the Chat page doesn't need.

Supports three search modes, matching the "Search" feature spec:
    "semantic" -> pure embedding-based similarity search
    "keyword"  -> pure BM25 keyword search
    "hybrid"   -> both, merged and cross-encoder reranked (default,
                  same pipeline used by chat_service.py)
"""

from datetime import datetime
from typing import List, Optional

from rank_bm25 import BM25Okapi

from app.models.chunk import Chunk
from app.models.document import Document
from app.ai.embedder import Embedder
from app.ai.reranker import rerank
from app.services import vector_store_service


class SearchServiceError(Exception):
    """Raised for invalid search parameters (e.g. an unsupported search mode)."""

    def __init__(self, message: str, error_code: str = "SEARCH_ERROR"):
        super().__init__(message)
        self.message = message
        self.error_code = error_code


_VALID_MODES = {"semantic", "keyword", "hybrid"}


def search_notes(
    user_id: int,
    query_text: str,
    mode: str = "hybrid",
    document_id: Optional[int] = None,
    subject_filter: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    top_k: int = 15,
    embedding_model_name: str = "all-MiniLM-L6-v2",
) -> List[dict]:
    """
    Runs a search over the student's own notes and returns a ranked list
    of matching chunk results with document context, for the Search Notes
    page's results list.

    Args:
        user_id: The requesting student's ID — results are always scoped
            to only this user's own chunks.
        query_text: The search query string.
        mode: One of "semantic", "keyword", "hybrid" (default).
        document_id: Optional single-document filter.
        subject_filter: Optional exact-match Document.subject filter.
        date_from: Optional lower bound on Document.uploaded_at.
        date_to: Optional upper bound on Document.uploaded_at.
        top_k: Maximum number of results to return.
        embedding_model_name: Sourced from app.config["EMBEDDING_MODEL_NAME"].

    Returns:
        A list of result dicts, each shaped:
            {"chunk_id": int, "document_id": int, "document_title": str,
             "page_number": int, "excerpt": str, "score": float}

    Raises:
        SearchServiceError: If `mode` is not one of the supported values.
    """
    if mode not in _VALID_MODES:
        raise SearchServiceError(f"Invalid search mode: {mode}. Must be one of {_VALID_MODES}.", "INVALID_MODE")

    if not query_text or not query_text.strip():
        return []

    scoped_chunks = _get_filtered_chunks(user_id, document_id, subject_filter, date_from, date_to)
    if not scoped_chunks:
        return []

    if mode == "semantic":
        scored = _semantic_search(query_text, scoped_chunks, top_k, embedding_model_name)
    elif mode == "keyword":
        scored = _keyword_search(query_text, scoped_chunks, top_k)
    else:
        scored = _hybrid_search(query_text, scoped_chunks, top_k, embedding_model_name)

    return _format_results(scored)


def _get_filtered_chunks(
    user_id: int,
    document_id: Optional[int],
    subject_filter: Optional[str],
    date_from: Optional[datetime],
    date_to: Optional[datetime],
) -> List[Chunk]:
    """
    Queries PostgreSQL for the full scoped chunk pool matching the
    requested filters, joining to Document for subject/date filtering.

    Args:
        user_id: The requesting student's ID.
        document_id: Optional single-document filter.
        subject_filter: Optional exact-match Document.subject filter.
        date_from: Optional lower bound on Document.uploaded_at.
        date_to: Optional upper bound on Document.uploaded_at.

    Returns:
        A list of Chunk ORM objects matching all provided filters.
    """
    query = Chunk.query.join(Document, Chunk.document_id == Document.id).filter(
        Chunk.user_id == user_id,
        Document.is_deleted.is_(False),
    )

    if document_id is not None:
        query = query.filter(Chunk.document_id == document_id)
    if subject_filter:
        query = query.filter(Document.subject == subject_filter)
    if date_from is not None:
        query = query.filter(Document.uploaded_at >= date_from)
    if date_to is not None:
        query = query.filter(Document.uploaded_at <= date_to)

    return query.all()


def _semantic_search(query_text: str, chunks: List[Chunk], top_k: int, embedding_model_name: str) -> List[tuple]:
    """
    Pure embedding-based similarity search over the filtered chunk pool.

    Args:
        query_text: The search query string.
        chunks: The filtered scope of Chunk ORM objects to search within.
        top_k: Maximum number of results to return.
        embedding_model_name: Model used to embed the query.

    Returns:
        A list of (Chunk, score) tuples, ordered by descending similarity.
    """
    allowed_ids = {c.id for c in chunks}
    embedder = Embedder(model_name=embedding_model_name)
    query_embedding = embedder.embed_query(query_text)

    raw_results = vector_store_service.search_vectors(query_embedding, top_k=top_k, allowed_ids=allowed_ids)

    chunks_by_id = {c.id: c for c in chunks}
    return [(chunks_by_id[cid], score) for cid, score in raw_results if cid in chunks_by_id]


def _keyword_search(query_text: str, chunks: List[Chunk], top_k: int) -> List[tuple]:
    """
    Pure BM25 keyword search over the filtered chunk pool.

    Args:
        query_text: The search query string.
        chunks: The filtered scope of Chunk ORM objects to search within.
        top_k: Maximum number of results to return.

    Returns:
        A list of (Chunk, score) tuples, ordered by descending BM25 score.
    """
    tokenized_corpus = [c.chunk_text.lower().split() for c in chunks]
    bm25 = BM25Okapi(tokenized_corpus)

    tokenized_query = query_text.lower().split()
    scores = bm25.get_scores(tokenized_query)

    scored_chunks = [(chunk, score) for chunk, score in zip(chunks, scores) if score > 0]
    scored_chunks.sort(key=lambda pair: pair[1], reverse=True)

    return scored_chunks[:top_k]


def _hybrid_search(query_text: str, chunks: List[Chunk], top_k: int, embedding_model_name: str) -> List[tuple]:
    """
    Hybrid search: merges semantic and BM25 candidate pools, then
    reranks the merged pool with the cross-encoder for final ordering —
    the same accuracy-enhanced approach used by app.ai.retriever for chat.

    Args:
        query_text: The search query string.
        chunks: The filtered scope of Chunk ORM objects to search within.
        top_k: Maximum number of results to return.
        embedding_model_name: Model used to embed the query.

    Returns:
        A list of (Chunk, score) tuples, ordered by descending
        cross-encoder relevance score.
    """
    candidate_pool_size = max(top_k * 2, 20)

    semantic_results = _semantic_search(query_text, chunks, candidate_pool_size, embedding_model_name)
    keyword_results = _keyword_search(query_text, chunks, candidate_pool_size)

    merged_chunks_by_id = {}
    for chunk, _ in semantic_results + keyword_results:
        merged_chunks_by_id[chunk.id] = chunk

    if not merged_chunks_by_id:
        return []

    rerank_candidates = [(cid, chunk.chunk_text, 0.0) for cid, chunk in merged_chunks_by_id.items()]
    reranked = rerank(query_text, rerank_candidates)

    return [(merged_chunks_by_id[cid], score) for cid, _, score in reranked[:top_k]]


def _format_results(scored_chunks: List[tuple]) -> List[dict]:
    """
    Formats (Chunk, score) tuples into the result dict shape expected by
    the Search Notes page's frontend rendering.

    Args:
        scored_chunks: List of (Chunk, score) tuples.

    Returns:
        A list of formatted result dicts.
    """
    results = []
    for chunk, score in scored_chunks:
        excerpt = chunk.chunk_text[:300] + "..." if len(chunk.chunk_text) > 300 else chunk.chunk_text
        results.append({
            "chunk_id": chunk.id,
            "document_id": chunk.document_id,
            "document_title": chunk.document.title if chunk.document else None,
            "page_number": chunk.page_number,
            "excerpt": excerpt,
            "score": round(float(score), 4),
        })
    return results