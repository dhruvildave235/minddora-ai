"""
embedding_service.py

Orchestrates the embedding-generation stage of the RAG ingestion
pipeline. Sits between chunking_service.py (which produces raw chunk
dicts) and vector_store_service.py (which persists vectors into
FAISS/ChromaDB), and is responsible for:

    1. Persisting Chunk rows to PostgreSQL first (so each chunk has a
       stable Chunk.id to use as its vector_id/vector-store key).
    2. Batch-embedding all chunk texts via app.ai.embedder.Embedder.
    3. Handing the (vector_id, embedding) pairs off to
       vector_store_service.add_vectors() for persistence into the
       configured vector database.

Batch processing and a simple in-memory embedding cache (keyed by exact
chunk text) are used to avoid redundant model calls when a document
contains repeated boilerplate chunks (e.g. a recurring disclaimer
paragraph across many pages).
"""

from typing import List, Dict

from app.extensions import db
from app.models.chunk import Chunk
from app.ai.embedder import Embedder
from app.services import vector_store_service
from app.utils.logger import log_to_db

# Process-wide cache mapping exact chunk text -> embedding vector, to
# avoid re-embedding identical repeated chunks within or across documents
# during a single application run. Bounded in size to prevent unbounded
# memory growth on long-running server processes.
_EMBEDDING_CACHE: Dict[str, "np.ndarray"] = {}
_EMBEDDING_CACHE_MAX_SIZE = 5000


class EmbeddingError(Exception):
    """
    Raised when the embedding stage of ingestion fails (model load
    failure, vector store write failure). Caught by document_service.py
    to mark the Document's processing_status as "failed".
    """

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def embed_and_store_chunks(
    document_id: int,
    user_id: int,
    raw_chunks: List[Dict],
    embedding_model_name: str = "all-MiniLM-L6-v2",
    batch_size: int = 32,
) -> int:
    """
    Persists raw chunk dicts (from chunking_service.chunk_document_pages)
    as Chunk rows in PostgreSQL, generates their embeddings, and stores
    those embeddings in the configured vector database (FAISS/ChromaDB).

    Args:
        document_id: The PostgreSQL Document.id these chunks belong to.
        user_id: The owning student's User.id, denormalized onto each
            Chunk row for fast retrieval-scoping queries (avoids a JOIN
            through Document on every chat search).
        raw_chunks: Output of chunking_service.chunk_document_pages(),
            i.e. [{"chunk_index": int, "chunk_text": str,
                   "chunk_char_length": int, "page_number": int}, ...]
        embedding_model_name: Model identifier, sourced from
            app.config["EMBEDDING_MODEL_NAME"].
        batch_size: Number of chunks embedded per model forward pass.

    Returns:
        The total number of chunks successfully embedded and stored.

    Raises:
        EmbeddingError: If embedding generation or vector store writing fails.
    """
    if not raw_chunks:
        return 0

    try:
        # -----------------------------------------------------------------
        # Step 1: Persist Chunk rows first so each has a stable, real
        # Chunk.id to use as its vector_id in the vector store.
        # -----------------------------------------------------------------
        chunk_rows = []

        for index, raw_chunk in enumerate(raw_chunks):
            chunk_row = Chunk(
                document_id=document_id,
                user_id=user_id,
                chunk_index=raw_chunk["chunk_index"],
                chunk_text=raw_chunk["chunk_text"],
                chunk_char_length=raw_chunk["chunk_char_length"],
                page_number=raw_chunk.get("page_number"),
                embedding_model=embedding_model_name,
                vector_id=f"pending-{document_id}-{index}",
            )
            db.session.add(chunk_row)
            chunk_rows.append(chunk_row)

        db.session.flush()

        for chunk_row in chunk_rows:
            chunk_row.vector_id = str(chunk_row.id)

        db.session.commit()

        # -----------------------------------------------------------------
        # Step 2: Batch-embed all chunk texts (using cache where possible).
        # -----------------------------------------------------------------
        embeddings_by_chunk_id = _embed_chunks_with_cache(chunk_rows, embedding_model_name, batch_size)

        # -----------------------------------------------------------------
        # Step 3: Store embeddings in the configured vector database.
        # -----------------------------------------------------------------
        vector_ids = list(embeddings_by_chunk_id.keys())
        embeddings_matrix = _stack_embeddings(embeddings_by_chunk_id, vector_ids)

        vector_store_service.add_vectors(vector_ids=vector_ids, embeddings=embeddings_matrix)

        return len(vector_ids)

    except Exception as exc:  # noqa: BLE001 — normalize into EmbeddingError for the caller
        db.session.rollback()
        log_to_db(
            level="ERROR",
            category="rag_pipeline",
            message=f"Embedding stage failed for document_id={document_id}",
            context={"exception": str(exc)},
            user_id=user_id,
        )
        raise EmbeddingError(f"Failed to generate or store embeddings: {exc}") from exc


def _embed_chunks_with_cache(chunk_rows: List[Chunk], embedding_model_name: str, batch_size: int) -> dict:
    """
    Generates embeddings for a list of Chunk rows, reusing cached
    embeddings for exact-duplicate chunk text where available and only
    calling the model for the remaining, uncached texts.

    Args:
        chunk_rows: Persisted Chunk ORM objects (already have .id set).
        embedding_model_name: Model identifier to use for embedding.
        batch_size: Batch size for the underlying model forward pass.

    Returns:
        A dict mapping vector_id (str, equal to Chunk.id) -> embedding
        (NumPy array).
    """
    import numpy as np  # local import to keep module import light for callers that don't need numpy directly

    embedder = Embedder(model_name=embedding_model_name)

    embeddings_by_chunk_id = {}
    texts_to_embed = []
    chunks_needing_embedding = []

    for chunk_row in chunk_rows:
        cached = _EMBEDDING_CACHE.get(chunk_row.chunk_text)
        if cached is not None:
            embeddings_by_chunk_id[chunk_row.vector_id] = cached
        else:
            texts_to_embed.append(chunk_row.chunk_text)
            chunks_needing_embedding.append(chunk_row)

    if texts_to_embed:
        new_embeddings = embedder.embed_texts(texts_to_embed, batch_size=batch_size)

        for chunk_row, embedding in zip(chunks_needing_embedding, new_embeddings):
            embeddings_by_chunk_id[chunk_row.vector_id] = embedding
            _cache_embedding(chunk_row.chunk_text, embedding)

    return embeddings_by_chunk_id


def _cache_embedding(chunk_text: str, embedding) -> None:
    """
    Stores a computed embedding in the process-wide cache, evicting the
    oldest entry (simple FIFO eviction via dict insertion order) once the
    cache reaches its maximum size, to bound memory usage on long-running
    server processes handling many document uploads over time.

    Args:
        chunk_text: The exact chunk text used as the cache key.
        embedding: The computed embedding vector for this text.
    """
    if len(_EMBEDDING_CACHE) >= _EMBEDDING_CACHE_MAX_SIZE:
        oldest_key = next(iter(_EMBEDDING_CACHE))
        del _EMBEDDING_CACHE[oldest_key]

    _EMBEDDING_CACHE[chunk_text] = embedding


def _stack_embeddings(embeddings_by_chunk_id: dict, vector_ids: List[str]):
    """
    Stacks individual embedding vectors (in the same order as vector_ids)
    into a single 2-D NumPy matrix suitable for a bulk add_vectors() call
    against the vector store.

    Args:
        embeddings_by_chunk_id: Dict mapping vector_id -> embedding vector.
        vector_ids: Ordered list of vector_id keys defining row order.

    Returns:
        A 2-D NumPy array of shape (len(vector_ids), embedding_dimension).
    """
    import numpy as np

    return np.stack([embeddings_by_chunk_id[vid] for vid in vector_ids])