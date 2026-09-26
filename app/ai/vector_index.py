"""
vector_index.py

FAISS-backed vector index wrapper — the default vector database provider
for Minddora AI (selectable via app.config["VECTOR_DB_PROVIDER"] = "faiss",
with ChromaDB as the alternate provider implemented separately in
app/ai/vector_store_chromadb.py-equivalent logic inside
app/services/vector_store_service.py, which dispatches between the two).

Design notes:
    - Uses a single global FAISS IndexIDMap wrapping an IndexFlatIP (inner
      product), since embeddings are L2-normalized at generation time
      (embedder.py), making inner product equivalent to cosine similarity.
    - IndexIDMap allows associating each vector with an arbitrary integer
      ID (Chunk.id from PostgreSQL) rather than relying on FAISS's default
      sequential internal indexing, so vectors can be looked up, added,
      and removed by their true database ID.
    - The index is persisted to disk (app.config["VECTOR_DB_PATH"]) as a
      single file per deployment and loaded into memory on first use,
      then kept resident for the lifetime of the process for fast search.
    - Deletion in FAISS's IndexIDMap is supported via remove_ids(), used
      when a student deletes a document (cascade-removes its chunks'
      vectors so they no longer surface in search results).
"""

import os
import threading

import faiss
import numpy as np

_INDEX_LOCK = threading.Lock()
_faiss_index_instance: faiss.IndexIDMap = None
_index_file_path_loaded: str = None


class FAISSVectorIndex:
    """
    High-level wrapper around a single FAISS IndexIDMap(IndexFlatIP),
    providing add / search / remove / persist operations keyed by
    PostgreSQL Chunk.id values.
    """

    def __init__(self, embedding_dimension: int, index_path: str):
        """
        Args:
            embedding_dimension: Dimensionality of the embeddings this
                index will store (384 for all-MiniLM-L6-v2), sourced from
                app.config["EMBEDDING_DIMENSION"].
            index_path: Directory path (app.config["VECTOR_DB_PATH"])
                where the FAISS index file is persisted as "faiss.index".
        """
        self.embedding_dimension = embedding_dimension
        self.index_path = index_path
        self.index_file = os.path.join(index_path, "faiss.index")
        self._index = self._load_or_create_index()

    # -----------------------------------------------------------------
    # Index Loading / Creation
    # -----------------------------------------------------------------
    def _load_or_create_index(self) -> faiss.IndexIDMap:
        """
        Loads the process-wide singleton FAISS index from disk if it
        already exists, otherwise creates a fresh empty index. Guarded by
        a lock since multiple request threads may attempt initialization
        concurrently on first access.

        Returns:
            The loaded or newly created faiss.IndexIDMap instance.
        """
        global _faiss_index_instance, _index_file_path_loaded

        if _faiss_index_instance is not None and _index_file_path_loaded == self.index_file:
            return _faiss_index_instance

        with _INDEX_LOCK:
            if _faiss_index_instance is None or _index_file_path_loaded != self.index_file:
                os.makedirs(self.index_path, exist_ok=True)

                if os.path.exists(self.index_file):
                    _faiss_index_instance = faiss.read_index(self.index_file)
                else:
                    base_index = faiss.IndexFlatIP(self.embedding_dimension)
                    _faiss_index_instance = faiss.IndexIDMap(base_index)

                _index_file_path_loaded = self.index_file

        return _faiss_index_instance

    def _persist(self) -> None:
        """
        Writes the current in-memory index state to disk. Called after
        every add/remove operation so the index survives process restarts
        without requiring a full re-embedding of every document.
        """
        os.makedirs(self.index_path, exist_ok=True)
        faiss.write_index(self._index, self.index_file)

    # -----------------------------------------------------------------
    # Add / Search / Remove
    # -----------------------------------------------------------------
    def add_vectors(self, vector_ids: list, embeddings: np.ndarray) -> None:
        """
        Adds one or more chunk embeddings to the index, keyed by their
        corresponding Chunk.id values so search results can be resolved
        straight back to PostgreSQL rows.

        Args:
            vector_ids: List of integer IDs (Chunk.id) parallel to
                `embeddings`' rows.
            embeddings: NumPy array of shape (n, embedding_dimension),
                L2-normalized, as produced by embedder.embed_texts().
        """
        if embeddings.shape[0] == 0:
            return

        ids_array = np.array(vector_ids, dtype=np.int64)
        with _INDEX_LOCK:
            self._index.add_with_ids(embeddings, ids_array)
            self._persist()

    def search(self, query_embedding: np.ndarray, top_k: int, allowed_ids: set = None) -> list:
        """
        Performs a top-K similarity search against the index.

        Args:
            query_embedding: 1-D NumPy array of shape (embedding_dimension,).
            top_k: Number of nearest neighbors to retrieve.
            allowed_ids: Optional set of Chunk.id values to restrict the
                search to (used to scope retrieval to a single user's own
                documents, or a single specific document). Since FAISS's
                IndexFlatIP does not natively support pre-filtering,
                results are over-fetched and then filtered post-search
                (see note in retriever.py on why this is acceptable at
                this product's scale).

        Returns:
            A list of (vector_id, similarity_score) tuples, ordered by
            descending similarity, filtered to allowed_ids if provided.
        """
        if self._index.ntotal == 0:
            return []

        # Over-fetch when filtering is required, since some top results
        # may belong to other users/documents and need to be discarded.
        search_k = top_k * 5 if allowed_ids is not None else top_k
        search_k = min(search_k, self._index.ntotal)

        query = query_embedding.reshape(1, -1)
        scores, ids = self._index.search(query, search_k)

        results = []
        for score, vector_id in zip(scores[0], ids[0]):
            if vector_id == -1:
                continue  # FAISS pads with -1 when fewer than search_k results exist
            if allowed_ids is not None and int(vector_id) not in allowed_ids:
                continue
            results.append((int(vector_id), float(score)))
            if len(results) >= top_k:
                break

        return results

    def remove_vectors(self, vector_ids: list) -> None:
        """
        Removes vectors from the index by their Chunk.id values. Called
        when a student deletes a document, ensuring its chunks can no
        longer be retrieved in future chat searches.

        Args:
            vector_ids: List of integer Chunk.id values to remove.
        """
        if not vector_ids:
            return

        ids_array = np.array(vector_ids, dtype=np.int64)
        with _INDEX_LOCK:
            self._index.remove_ids(ids_array)
            self._persist()

    @property
    def total_vectors(self) -> int:
        """Returns the total number of vectors currently stored in the index."""
        return self._index.ntotal