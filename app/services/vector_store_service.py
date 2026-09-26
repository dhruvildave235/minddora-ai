"""
vector_store_service.py

Dispatch layer between the rest of Minddora AI's services (embedding_service.py,
app.ai.retriever) and the actual vector database backend. Selects between
FAISS and ChromaDB at runtime based on app.config["VECTOR_DB_PROVIDER"]
("faiss" or "chromadb"), so the rest of the codebase never imports
FAISS/ChromaDB directly and can be switched between the two providers
with a single environment variable change — no code changes elsewhere.

Both backends are free and open-source:
    FAISS      -> app/ai/vector_index.py (FAISSVectorIndex wrapper)
    ChromaDB   -> _chromadb_client() helpers defined in this module
"""

import os
import threading
from typing import List, Optional

import numpy as np
from flask import current_app

from app.ai.vector_index import FAISSVectorIndex

_CHROMA_LOCK = threading.Lock()
_chroma_client_instance = None
_chroma_collection_instance = None


# ---------------------------------------------------------------------------
# Public Dispatch Functions
# ---------------------------------------------------------------------------
def add_vectors(vector_ids: List[str], embeddings: np.ndarray) -> None:
    """
    Adds a batch of chunk embeddings to the currently configured vector
    store provider.

    Args:
        vector_ids: List of string IDs (equal to Chunk.id as a string,
            per embedding_service.py's convention), parallel to
            `embeddings`' rows.
        embeddings: NumPy array of shape (n, embedding_dimension),
            L2-normalized, as produced by app.ai.embedder.Embedder.

    Raises:
        ValueError: If VECTOR_DB_PROVIDER is set to an unsupported value.
    """
    provider = _get_provider()

    if provider == "faiss":
        index = _get_faiss_index()
        int_ids = [int(vid) for vid in vector_ids]
        index.add_vectors(int_ids, embeddings)
    elif provider == "chromadb":
        _chromadb_add(vector_ids, embeddings)
    else:
        raise ValueError(f"Unsupported VECTOR_DB_PROVIDER: {provider}")


def search_vectors(query_embedding: np.ndarray, top_k: int, allowed_ids: Optional[set] = None) -> List[tuple]:
    """
    Performs a top-K similarity search against the currently configured
    vector store provider, scoped to allowed_ids if provided.

    Args:
        query_embedding: 1-D NumPy array of shape (embedding_dimension,).
        top_k: Number of nearest neighbors to retrieve.
        allowed_ids: Optional set of integer Chunk.id values to restrict
            results to (data-isolation scoping from app.ai.retriever).

    Returns:
        A list of (chunk_id, similarity_score) tuples, ordered by
        descending similarity.

    Raises:
        ValueError: If VECTOR_DB_PROVIDER is set to an unsupported value.
    """
    provider = _get_provider()

    if provider == "faiss":
        index = _get_faiss_index()
        return index.search(query_embedding, top_k, allowed_ids)
    elif provider == "chromadb":
        return _chromadb_search(query_embedding, top_k, allowed_ids)
    else:
        raise ValueError(f"Unsupported VECTOR_DB_PROVIDER: {provider}")


def remove_vectors(vector_ids: List[str]) -> None:
    """
    Removes vectors from the currently configured vector store provider,
    called when a student deletes a document (cascade-removes its
    chunks' vectors so they no longer surface in future searches).

    Args:
        vector_ids: List of string IDs (equal to Chunk.id as a string) to remove.

    Raises:
        ValueError: If VECTOR_DB_PROVIDER is set to an unsupported value.
    """
    if not vector_ids:
        return

    provider = _get_provider()

    if provider == "faiss":
        index = _get_faiss_index()
        int_ids = [int(vid) for vid in vector_ids]
        index.remove_vectors(int_ids)
    elif provider == "chromadb":
        _chromadb_remove(vector_ids)
    else:
        raise ValueError(f"Unsupported VECTOR_DB_PROVIDER: {provider}")


def get_total_vector_count() -> int:
    """
    Returns the total number of vectors currently stored, used by the
    Admin Panel's System Analytics page to display vector database size.

    Returns:
        Total vector count as an integer.
    """
    provider = _get_provider()

    if provider == "faiss":
        return _get_faiss_index().total_vectors
    elif provider == "chromadb":
        collection = _get_chromadb_collection()
        return collection.count()
    else:
        return 0


# ---------------------------------------------------------------------------
# Provider Selection
# ---------------------------------------------------------------------------
def _get_provider() -> str:
    """Reads the configured vector database provider from Flask app config."""
    return current_app.config.get("VECTOR_DB_PROVIDER", "faiss").lower()


# ---------------------------------------------------------------------------
# FAISS Backend
# ---------------------------------------------------------------------------
def _get_faiss_index() -> FAISSVectorIndex:
    """
    Builds (or reuses, via FAISSVectorIndex's own internal singleton
    caching) the FAISSVectorIndex instance using current Flask app config
    values for embedding dimension and storage path.

    Returns:
        A FAISSVectorIndex instance.
    """
    return FAISSVectorIndex(
        embedding_dimension=current_app.config["EMBEDDING_DIMENSION"],
        index_path=current_app.config["VECTOR_DB_PATH"],
    )


# ---------------------------------------------------------------------------
# ChromaDB Backend
# ---------------------------------------------------------------------------
def _get_chromadb_collection():
    """
    Returns the process-wide singleton ChromaDB persistent client and
    collection, creating them on first use. ChromaDB manages its own
    on-disk persistence directory (app.config["VECTOR_DB_PATH"]),
    analogous to FAISS's single index file but using ChromaDB's native
    storage format instead.

    Returns:
        A ChromaDB Collection object named "minddora_chunks".
    """
    global _chroma_client_instance, _chroma_collection_instance

    if _chroma_collection_instance is not None:
        return _chroma_collection_instance

    with _CHROMA_LOCK:
        if _chroma_collection_instance is None:
            import chromadb

            storage_path = current_app.config["VECTOR_DB_PATH"]
            os.makedirs(storage_path, exist_ok=True)

            _chroma_client_instance = chromadb.PersistentClient(path=storage_path)
            _chroma_collection_instance = _chroma_client_instance.get_or_create_collection(
                name="minddora_chunks",
                metadata={"hnsw:space": "cosine"},
            )

    return _chroma_collection_instance


def _chromadb_add(vector_ids: List[str], embeddings: np.ndarray) -> None:
    """
    Adds embeddings to the ChromaDB collection, keyed by their string
    vector IDs (equal to Chunk.id as a string).

    Args:
        vector_ids: List of string IDs parallel to `embeddings`' rows.
        embeddings: NumPy array of shape (n, embedding_dimension).
    """
    collection = _get_chromadb_collection()
    collection.add(
        ids=vector_ids,
        embeddings=embeddings.tolist(),
    )


def _chromadb_search(query_embedding: np.ndarray, top_k: int, allowed_ids: Optional[set]) -> List[tuple]:
    """
    Performs a similarity search against the ChromaDB collection. Since
    ChromaDB's `where` filtering operates on metadata rather than the ID
    list directly in this schema (IDs are stored as the primary key, not
    metadata), filtering to allowed_ids is applied post-search, mirroring
    the over-fetch-then-filter strategy used in FAISSVectorIndex.search().

    Args:
        query_embedding: 1-D NumPy array of shape (embedding_dimension,).
        top_k: Number of nearest neighbors to retrieve.
        allowed_ids: Optional set of integer Chunk.id values to restrict
            results to.

    Returns:
        A list of (chunk_id, similarity_score) tuples, ordered by
        descending similarity.
    """
    collection = _get_chromadb_collection()

    if collection.count() == 0:
        return []

    search_k = min(top_k * 5 if allowed_ids is not None else top_k, collection.count())

    results = collection.query(
        query_embeddings=[query_embedding.tolist()],
        n_results=search_k,
    )

    ids = results["ids"][0]
    distances = results["distances"][0]  # ChromaDB returns cosine DISTANCE (0 = identical)

    scored_results = []
    for vector_id_str, distance in zip(ids, distances):
        chunk_id = int(vector_id_str)
        if allowed_ids is not None and chunk_id not in allowed_ids:
            continue
        similarity_score = 1.0 - distance  # Convert distance back to a similarity score
        scored_results.append((chunk_id, similarity_score))
        if len(scored_results) >= top_k:
            break

    return scored_results


def _chromadb_remove(vector_ids: List[str]) -> None:
    """
    Removes vectors from the ChromaDB collection by their string IDs.

    Args:
        vector_ids: List of string IDs (equal to Chunk.id as a string) to remove.
    """
    collection = _get_chromadb_collection()
    collection.delete(ids=vector_ids)