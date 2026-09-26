"""
rag_viz_api.py

Exposes the actual hybrid retrieval pipeline's per-chunk scores for the
Admin Panel's RAG Visualizer page, so students/admins can literally see
how a question gets matched against real document chunks — using the
same retriever.py used in real chat, not a simulated/fake demo.
"""

from flask import Blueprint, request

from app.ai.retriever import retrieve_relevant_chunks
from app.models.chunk import Chunk
from app.utils.responses import success_response, error_response
from app.utils.decorators import admin_required, json_required

rag_viz_api_bp = Blueprint("rag_viz_api", __name__)


@rag_viz_api_bp.route("/visualize", methods=["POST"])
@admin_required
@json_required
def api_visualize_retrieval():
    """
    POST /api/admin/rag-viz/visualize

    Request JSON body:
        { "question": "...", "document_id": 14, "user_id": 2 }

    Runs the real retrieval pipeline and returns every candidate chunk
    considered, with its actual relevance score, plus a short preview of
    its text — so the frontend can render exactly what the AI "saw" when
    answering this question.

    Success (200): { "success": true, "data": {"query_words": [...], "chunks": [...]} }
    """
    payload = request.get_json(silent=True) or {}
    question = payload.get("question", "").strip()
    document_id = payload.get("document_id")
    user_id = payload.get("user_id")

    if not question or not user_id:
        return error_response("Question and user_id are required.", status_code=400)

    results = retrieve_relevant_chunks(
        query_text=question,
        user_id=user_id,
        document_id=document_id,
        top_k=8,
        similarity_threshold=0.0,  # show everything considered, even low scorers, for visualization
    )

    query_words = [w.strip(".,!?") for w in question.split() if len(w) > 2]

    chunks_payload = []
    for r in results:
        chunks_payload.append({
            "chunk_id": r.chunk.id,
            "page_number": r.chunk.page_number,
            "excerpt": r.chunk.chunk_text[:120],
            "score": round(r.relevance_score, 4),
        })

    return success_response(data={"query_words": query_words, "chunks": chunks_payload})