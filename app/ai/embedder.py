"""
embedder.py

Wraps the SentenceTransformer "all-MiniLM-L6-v2" model, providing a
single, lazily-initialized, process-wide instance (loaded once, reused
across every embedding call) since loading the model from disk/downloading
it is expensive and should not happen on every request.

Responsibilities:
    - Load and cache the embedding model.
    - Generate embeddings for document chunks (batch mode, used during
      ingestion by embedding_service.py).
    - Generate a single embedding for an incoming chat query (used by
      retriever.py at query time).

This module is intentionally framework-agnostic (no Flask imports) so it
can be reused by background workers/CLI scripts as well as request-time
code, and so app/ai/ as a whole remains extractable into a standalone
microservice later without modification.
"""

import threading
from typing import List

import numpy as np
from sentence_transformers import SentenceTransformer

_MODEL_LOCK = threading.Lock()
_model_instance: SentenceTransformer = None
_model_name_loaded: str = None


def _get_model(model_name: str = "all-MiniLM-L6-v2") -> SentenceTransformer:
    """
    Returns the process-wide singleton SentenceTransformer instance,
    loading it from disk/HuggingFace cache on first use. Thread-safe via
    a lock, since Flask's development/production servers may handle
    concurrent requests across multiple threads.

    Args:
        model_name: The SentenceTransformer model identifier to load.
            Defaults to "all-MiniLM-L6-v2" (also the default in
            app.config["EMBEDDING_MODEL_NAME"]).

    Returns:
        A loaded SentenceTransformer instance.
    """
    global _model_instance, _model_name_loaded

    if _model_instance is not None and _model_name_loaded == model_name:
        return _model_instance

    with _MODEL_LOCK:
        # Re-check inside the lock in case another thread loaded it while
        # this thread was waiting.
        if _model_instance is None or _model_name_loaded != model_name:
            _model_instance = SentenceTransformer(model_name)
            _model_name_loaded = model_name

    return _model_instance


class Embedder:
    """
    High-level interface for generating embeddings, used by both the
    ingestion pipeline (batch chunk embedding) and the RAG retrieval
    pipeline (single query embedding).
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        Args:
            model_name: The SentenceTransformer model identifier.
                Should be passed from app.config["EMBEDDING_MODEL_NAME"]
                by calling services, keeping this class free of any
                direct Flask config dependency.
        """
        self.model_name = model_name
        self._model = _get_model(model_name)
        self.embedding_dimension = self._model.get_sentence_embedding_dimension()

    def embed_texts(self, texts: List[str], batch_size: int = 32, show_progress: bool = False) -> np.ndarray:
        """
        Generates embeddings for a batch of texts (used during document
        ingestion to embed all of a document's chunks at once, which is
        significantly faster than embedding one chunk at a time).

        Args:
            texts: List of chunk text strings to embed.
            batch_size: Number of texts processed per forward pass.
            show_progress: Whether to display a progress bar (useful for
                large documents processed via a CLI/worker context).

        Returns:
            A NumPy array of shape (len(texts), embedding_dimension),
            L2-normalized so that cosine similarity reduces to a simple
            dot product during vector search.
        """
        if not texts:
            return np.empty((0, self.embedding_dimension), dtype=np.float32)

        embeddings = self._model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=show_progress,
            normalize_embeddings=True,  # Enables cosine similarity via dot product in FAISS/ChromaDB
            convert_to_numpy=True,
        )
        return embeddings.astype(np.float32)

    def embed_query(self, query_text: str) -> np.ndarray:
        """
        Generates a single embedding for an incoming user chat question,
        used by app/ai/retriever.py to perform the similarity search
        against stored chunk vectors.

        Args:
            query_text: The student's natural-language question.

        Returns:
            A 1-D NumPy array of shape (embedding_dimension,),
            L2-normalized.
        """
        embedding = self._model.encode(
            [query_text],
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return embedding[0].astype(np.float32)