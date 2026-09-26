"""
reranker.py

Cross-encoder reranking layer — the key accuracy booster for Minddora
AI's Enhanced Pure Retrieval pipeline. Unlike the bi-encoder embedding
model (all-MiniLM-L6-v2, in app/ai/embedder.py) which scores the query
and each chunk independently and compares vectors, a cross-encoder scores
the query and chunk TOGETHER in a single forward pass, producing a far
more accurate relevance score at the cost of being too slow to run
against every chunk in the database.

Design: retrieval is done in two stages —
    Stage 1 (cheap, broad): embedder.py + FAISS/ChromaDB fetch a wider
        candidate set (e.g. top 20) using fast bi-encoder similarity.
    Stage 2 (precise, narrow): THIS module re-scores only those ~20
        candidates with the cross-encoder and re-sorts them, so the final
        top-K returned to the student is meaningfully more accurate.

Model used: "cross-encoder/ms-marco-MiniLM-L-6-v2"
    - Free, open-source, ~80MB.
    - Trained specifically for query-passage relevance ranking (MS MARCO).
    - Runs comfortably on CPU in well under a second for ~20 candidates.
"""

import threading
from typing import List, Tuple

from sentence_transformers import CrossEncoder

_MODEL_LOCK = threading.Lock()
_reranker_instance: CrossEncoder = None
_model_name_loaded: str = None


def _get_reranker(model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> CrossEncoder:
    """
    Returns the process-wide singleton CrossEncoder instance, loading it
    from disk/Hugging Face cache on first use. Mirrors the lazy-loading
    pattern in app.ai.embedder to avoid reloading model weights on every
    request.

    Args:
        model_name: The CrossEncoder model identifier to load.

    Returns:
        A loaded CrossEncoder instance.
    """
    global _reranker_instance, _model_name_loaded

    if _reranker_instance is not None and _model_name_loaded == model_name:
        return _reranker_instance

    with _MODEL_LOCK:
        if _reranker_instance is None or _model_name_loaded != model_name:
            _reranker_instance = CrossEncoder(model_name, max_length=512)
            _model_name_loaded = model_name

    return _reranker_instance


def rerank(query: str, candidates: List[Tuple[int, str, float]]) -> List[Tuple[int, str, float]]:
    """
    Re-scores and re-sorts a candidate list of (chunk_id, chunk_text,
    original_similarity_score) tuples using the cross-encoder, replacing
    the original bi-encoder similarity score with a more accurate
    cross-encoder relevance score.

    Args:
        query: The student's natural-language question.
        candidates: A list of (chunk_id, chunk_text, original_score)
            tuples, typically the top ~20 results from the fast
            bi-encoder + vector-store search stage.

    Returns:
        The same candidates, re-scored (the third tuple element is now
        the cross-encoder relevance score, normalized to 0.0-1.0 via a
        sigmoid) and re-sorted by descending relevance.
    """
    if not candidates:
        return []

    reranker = _get_reranker()

    pairs = [(query, chunk_text) for _, chunk_text, _ in candidates]
    raw_scores = reranker.predict(pairs)

    normalized_scores = [_sigmoid(score) for score in raw_scores]

    rescored = [
        (chunk_id, chunk_text, normalized_score)
        for (chunk_id, chunk_text, _), normalized_score in zip(candidates, normalized_scores)
    ]

    rescored.sort(key=lambda item: item[2], reverse=True)
    return rescored


def _sigmoid(x: float) -> float:
    """
    Converts a raw cross-encoder logit score into a 0.0-1.0 probability-
    like value, since ms-marco-MiniLM-L-6-v2 outputs unbounded relevance
    logits rather than a pre-normalized score.

    Args:
        x: The raw model output score.

    Returns:
        A float between 0.0 and 1.0.
    """
    import math
    return 1.0 / (1.0 + math.exp(-x))