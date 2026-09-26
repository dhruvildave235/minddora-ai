"""
diagnose.py — One-shot diagnostic for the "no relevant chunks found" issue.
Run with: python diagnose.py
"""

from app import create_app
from app.extensions import db
from app.models.chunk import Chunk
from app.models.document import Document
from app.services import vector_store_service
from app.ai.embedder import Embedder
from app.ai.reranker import rerank

app = create_app()

with app.app_context():
    print("=" * 70)
    print("1. DOCUMENTS IN DATABASE")
    print("=" * 70)
    docs = Document.query.all()
    for d in docs:
        print(f"  id={d.id} title={d.title!r} status={d.processing_status} total_chunks={d.total_chunks}")

    print()
    print("=" * 70)
    print("2. CHUNKS IN DATABASE")
    print("=" * 70)
    chunks = Chunk.query.all()
    for c in chunks:
        print(f"  chunk_id={c.id} vector_id={c.vector_id!r} document_id={c.document_id} user_id={c.user_id} text={c.chunk_text[:60]!r}")

    print()
    print("=" * 70)
    print("3. VECTOR STORE TOTAL COUNT")
    print("=" * 70)
    total_vectors = vector_store_service.get_total_vector_count()
    print(f"  Total vectors stored: {total_vectors}")

    print()
    print("=" * 70)
    print("4. LIVE TEST SEARCH")
    print("=" * 70)
    query = "what is my cgpa"
    embedder = Embedder(model_name=app.config["EMBEDDING_MODEL_NAME"])
    query_embedding = embedder.embed_query(query)

    allowed_ids = {c.id for c in chunks}
    print(f"  allowed_ids being searched: {allowed_ids}")

    raw_results = vector_store_service.search_vectors(query_embedding, top_k=10, allowed_ids=allowed_ids)
    print(f"  Raw semantic search results (chunk_id, score): {raw_results}")

    if raw_results:
        chunks_by_id = {c.id: c for c in chunks}
        rerank_candidates = [(cid, chunks_by_id[cid].chunk_text, 0.0) for cid, _ in raw_results if cid in chunks_by_id]
        reranked = rerank(query, rerank_candidates)
        print(f"  Reranked results (chunk_id, text_snippet, score):")
        for cid, text, score in reranked:
            print(f"    id={cid} score={score:.4f} text={text[:50]!r}")
    else:
        print("  No raw results returned from vector store search — problem is at the vector store level.")

    print()
    print("=" * 70)
    print("DONE")
    print("=" * 70)