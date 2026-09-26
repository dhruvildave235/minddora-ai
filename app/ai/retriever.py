
"""
retriever.py

Retrieval layer of Minddora AI's Enhanced Pure Retrieval pipeline
(no generative LLM). Given a student's natural-language question, this
module runs the following process to maximize accuracy while staying
lightweight enough to run on modest hardware and free-tier cloud
hosting:

    Stage 0 — Direct Field Extraction: for structured factual questions
        (CGPA, email, date, amount, etc.), attempt a direct regex-based
        extraction over the document text FIRST. If found, return
        immediately — bypasses all chunk-boundary/ranking issues
        entirely for this category of question. Works across any
        document type; falls through silently if no field matches.
    Stage 1 — Semantic Search: embed the query (all-MiniLM-L6-v2) and
        fetch the top candidates from the vector store (FAISS/ChromaDB)
        by cosine similarity.
    Stage 2 — Keyword Search (BM25): independently score the same
        candidate pool using BM25 keyword matching, which catches exact
        terms (names, dates, formulas, acronyms) that semantic
        embeddings sometimes miss.
    Stage 3 — Hybrid Merge + Cross-Encoder Rerank: merge semantic and
        BM25 candidates into a single pool, then rerank that pool with a
        cross-encoder (app.ai.reranker) for the most accurate final
        ordering, before deduplication and threshold filtering.

This module is intentionally decoupled from Flask request handling — it
takes plain arguments and returns plain Python objects, so it can be
called from chat_api.py, search_api.py, or a future background worker
identically.
"""

import re
import difflib
from typing import List, Optional

from rank_bm25 import BM25Okapi

from app.ai.embedder import Embedder
from app.ai.reranker import rerank
from app.ai.field_extractor import detect_field_intent, extract_field
from app.models.chunk import Chunk
from app.services import vector_store_service


class RetrievedChunk:
    """
    Lightweight container pairing a PostgreSQL Chunk row with its final
    relevance score, used throughout the retrieval/answer pipeline
    without repeatedly re-querying the database. `extracted_field` is
    set only when this result came from direct field extraction
    (Stage 0), signaling answer_builder.py to skip normal synthesis and
    return the exact extracted value instead.
    """

    def __init__(self, chunk: Chunk, relevance_score: float):
        self.chunk = chunk
        self.relevance_score = relevance_score
        self.extracted_field = None

    def __repr__(self) -> str:
        return f"<RetrievedChunk chunk_id={self.chunk.id} score={self.relevance_score:.3f}>"

def _trim_by_relevance_dropoff(results: List[RetrievedChunk], drop_ratio: float = 0.5) -> List[RetrievedChunk]:
    """
    Drops trailing chunks whose relevance score falls sharply below the
    top result, preventing marginally-related chunks (e.g. a table that
    happened to share a few keywords) from padding out the answer just
    because top_k hasn't been reached yet.

    Args:
        results: RetrievedChunk list, already ordered by descending score.
        drop_ratio: Minimum fraction of the top score a chunk must retain
            to stay included (e.g. 0.5 means a chunk scoring less than
            half the top result's score is dropped).

    Returns:
        A trimmed list, always keeping at least the top result.
    """
    if not results:
        return results

    top_score = results[0].relevance_score
    threshold = top_score * drop_ratio

    trimmed = [results[0]]
    for r in results[1:]:
        if r.relevance_score >= threshold:
            trimmed.append(r)

    return trimmed


def retrieve_relevant_chunks(
    query_text: str,
    user_id: int,
    document_id: Optional[int] = None,
    top_k: int = 5,
    candidate_pool_size: int = 20,
    similarity_threshold: float = 0.30,
    embedding_model_name: str = "all-MiniLM-L6-v2",
) -> List[RetrievedChunk]:
    """
    Runs the full retrieval pipeline for a single query: direct field
    extraction first, then hybrid semantic+BM25+rerank retrieval as a
    fallback for anything not covered by a structured field pattern.

    Args:
        query_text: The student's natural-language question.
        user_id: The requesting student's ID — every result is scoped to
            only this user's own chunks, guaranteeing no cross-user data
            leakage.
        document_id: Optional single-document scope, restricting results
            to chunks belonging to this document only.
        top_k: Maximum number of final chunks to return, sourced from
            app.config["TOP_K_RETRIEVAL"].
        candidate_pool_size: Number of candidates pulled by the fast
            semantic + BM25 stages BEFORE cross-encoder reranking narrows
            it down to top_k.
        similarity_threshold: Minimum cross-encoder relevance score
            (0.0-1.0) required for a chunk to be included in the final
            answer, sourced from app.config["SIMILARITY_THRESHOLD"].
        embedding_model_name: Model used to embed the query, sourced from
            app.config["EMBEDDING_MODEL_NAME"].

    Returns:
        A list of RetrievedChunk objects, ordered by descending final
        relevance score, deduplicated, and threshold-filtered. May be
        empty if no sufficiently relevant chunks are found.
    """
    if not query_text or not query_text.strip():
        return []

    all_chunks = _get_scoped_chunks(user_id, document_id)
    if not all_chunks:
        return []

    query_text = _correct_typos(query_text, all_chunks)

    # -----------------------------------------------------------------
    # Stage 0: Direct field extraction (structured factual lookups).
    # Works across any document type; falls through silently if no
    # field keyword matches the question, or no pattern match is found
    # in the document.
    # -----------------------------------------------------------------
    field_key = detect_field_intent(query_text)
    if field_key:
        extracted = extract_field(field_key, all_chunks)
        if extracted:
            direct_result = RetrievedChunk(chunk=extracted.chunk, relevance_score=0.98)
            direct_result.extracted_field = extracted
            return [direct_result]

    # -----------------------------------------------------------------
    # Stage 1: Semantic search via the vector store.
    # -----------------------------------------------------------------
    allowed_ids = {c.id for c in all_chunks}
    embedder = Embedder(model_name=embedding_model_name)
    query_embedding = embedder.embed_query(query_text)

    semantic_results = vector_store_service.search_vectors(
        query_embedding=query_embedding,
        top_k=candidate_pool_size,
        allowed_ids=allowed_ids,
    )
    semantic_ids = {chunk_id for chunk_id, _ in semantic_results}

    # -----------------------------------------------------------------
    # Stage 2: Keyword search via BM25 over the same scoped chunk pool.
    # -----------------------------------------------------------------
    # bm25_ids = _bm25_search(query_text, all_chunks, top_n=candidate_pool_size)
    bm25_results = _bm25_search(query_text, all_chunks, top_n=candidate_pool_size)
    bm25_ids = {cid for cid, _ in bm25_results}

    # -----------------------------------------------------------------
    # Stage 3: Merge candidate pools, then rerank with the cross-encoder.
    # -----------------------------------------------------------------
    # merged_ids = semantic_ids | bm25_ids
    # if not merged_ids:
    #     return []

    # chunks_by_id = {c.id: c for c in all_chunks if c.id in merged_ids}
    # rerank_candidates = [(cid, chunk.chunk_text, 0.0) for cid, chunk in chunks_by_id.items()]

    merged_ids = semantic_ids | bm25_ids
    if not merged_ids:
        return []

    rrf_scores = _reciprocal_rank_fusion(semantic_results, bm25_results)

    chunks_by_id = {c.id: c for c in all_chunks if c.id in merged_ids}
    # Order candidates by RRF score before reranking, so the cross-encoder
    # sees the strongest fused candidates first if it ever needs to truncate.
    ordered_ids = sorted(chunks_by_id.keys(), key=lambda cid: rrf_scores.get(cid, 0), reverse=True)
    rerank_candidates = [(cid, chunks_by_id[cid].chunk_text, 0.0) for cid in ordered_ids]

    reranked = rerank(query_text, rerank_candidates)
    boosted = _apply_keyword_boost(query_text, reranked, chunks_by_id, all_chunks)

    filtered = [(cid, score) for cid, _, score in boosted if score >= similarity_threshold]
    if not filtered:
        return []

    # resolved = [RetrievedChunk(chunk=chunks_by_id[cid], relevance_score=score) for cid, score in filtered]
    # deduplicated = _remove_near_duplicate_chunks(resolved)

    # return deduplicated[:top_k]
    resolved = [RetrievedChunk(chunk=chunks_by_id[cid], relevance_score=score) for cid, score in filtered]
    deduplicated = _remove_near_duplicate_chunks(resolved)
    trimmed = _trim_by_relevance_dropoff(deduplicated)

    return trimmed[:top_k]

def _reciprocal_rank_fusion(semantic_results: list, bm25_results: list, k: int = 60) -> dict:
    """
    Combines two independently-ranked result lists (semantic search and
    BM25) into a single fused score per chunk, using Reciprocal Rank
    Fusion — a chunk that ranks highly in BOTH lists scores much higher
    than one that only appears in one, which is a stronger accuracy
    signal than simple set membership.

    Args:
        semantic_results: List of (chunk_id, score) tuples from vector search, ranked.
        bm25_results: List of (chunk_id, score) tuples from BM25, ranked.
        k: RRF constant (60 is the standard default from the original
            RRF paper — Cormack, Clarke & Buettcher, SIGIR 2009).

    Returns:
        A dict mapping chunk_id -> fused RRF score.
    """
    fused = {}

    for rank, (cid, _) in enumerate(semantic_results, start=1):
        fused[cid] = fused.get(cid, 0) + 1 / (k + rank)

    for rank, (cid, _) in enumerate(bm25_results, start=1):
        fused[cid] = fused.get(cid, 0) + 1 / (k + rank)

    return fused


def _correct_typos(query_text: str, all_chunks: List[Chunk]) -> str:
    """
    Corrects likely typos in the student's query by fuzzy-matching each
    word against the vocabulary of words actually present in their
    scoped documents. Uses Python's built-in difflib (no extra
    dependency), so a query like "whta is my cgpa" is treated as
    "what is my cgpa" before keyword/BM25 matching runs.

    Args:
        query_text: The raw student-typed question.
        all_chunks: The scoped chunk pool, used to build the correction
            vocabulary from words that actually appear in their notes.

    Returns:
        A corrected version of the query string. Words with no close
        match (e.g. genuinely new terms) are left unchanged.
    """
    vocabulary = set()
    for chunk in all_chunks:
        vocabulary.update(w.lower().strip(".,!?;:\"'") for w in chunk.chunk_text.split())

    common_words = {"what", "when", "where", "who", "why", "how", "is", "are", "my", "the", "a", "an", "of", "in", "on"}
    vocabulary.update(common_words)

    corrected_words = []
    for word in query_text.split():
        clean_word = word.lower().strip(".,!?;:\"'")

        if not clean_word or clean_word in vocabulary or len(clean_word) <= 2:
            corrected_words.append(word)
            continue

        matches = difflib.get_close_matches(clean_word, vocabulary, n=1, cutoff=0.75)
        corrected_words.append(matches[0] if matches else word)

    return " ".join(corrected_words)


def _apply_keyword_boost(query_text: str, reranked: list, chunks_by_id: dict, all_chunks: List[Chunk]) -> list:
    """
    Boosts chunks containing an exact keyword from the question, and also
    pulls in the immediately adjacent chunk (by chunk_index, same document)
    when the keyword-matched chunk doesn't itself contain a number —
    common with PDF table rows where a label and its value get split
    across chunk boundaries.

    Args:
        query_text: The student's natural-language question.
        reranked: List of (chunk_id, chunk_text, score) tuples from rerank().
        chunks_by_id: Dict mapping chunk_id -> Chunk ORM object (candidate pool only).
        all_chunks: Full scoped chunk list (for looking up neighbors not in the candidate pool).

    Returns:
        A new list of (chunk_id, chunk_text, boosted_score) tuples, deduplicated
        and re-sorted by descending score.
    """
    significant_words = [w.lower().strip("?.,!") for w in query_text.split() if len(w) > 3]
    all_chunks_by_doc_and_index = {(c.document_id, c.chunk_index): c for c in all_chunks}
    all_chunks_by_id = {c.id: c for c in all_chunks}

    result_map = {}

    for cid, text, score in reranked:
        chunk_text_lower = text.lower()
        keyword_hit = any(word in chunk_text_lower for word in significant_words)
        boosted_score = score + 0.05 if keyword_hit else score
        existing_score = result_map.get(cid, (None, None, 0.0))[2]
        result_map[cid] = (cid, text, max(existing_score, boosted_score))
        # keyword_hit = any(word in chunk_text_lower for word in significant_words)
        # boosted_score = max(score, 0.15) if keyword_hit else score
        # existing_score = result_map.get(cid, (None, None, 0.0))[2]
        # result_map[cid] = (cid, text, max(existing_score, boosted_score))

        has_number_nearby = bool(re.search(r"\d", text))
        if keyword_hit and not has_number_nearby:
            chunk_obj = all_chunks_by_id.get(cid)
            if chunk_obj:
                neighbor = all_chunks_by_doc_and_index.get((chunk_obj.document_id, chunk_obj.chunk_index + 1))
                if neighbor:
                    neighbor_existing = result_map.get(neighbor.id, (None, None, 0.0))[2]
                    result_map[neighbor.id] = (neighbor.id, neighbor.chunk_text, max(neighbor_existing, 0.16))

    boosted = list(result_map.values())
    boosted.sort(key=lambda item: item[2], reverse=True)
    return boosted


def _get_scoped_chunks(user_id: int, document_id: Optional[int]) -> List[Chunk]:
    """
    Queries PostgreSQL for all Chunk rows the current search is permitted
    to retrieve from — scoped to the requesting user's own documents, and
    additionally to a single document if document_id is provided. This is
    the primary data-isolation guarantee of the retrieval layer, and also
    supplies the full text pool needed for BM25 and field extraction
    (both require the complete corpus, not just vector-store candidate IDs).

    Args:
        user_id: The requesting student's ID.
        document_id: Optional single-document scope.

    Returns:
        A list of Chunk ORM objects.
    """
    query = Chunk.query.filter_by(user_id=user_id)
    if document_id is not None:
        query = query.filter_by(document_id=document_id)
    return query.all()

def _bm25_search(query_text: str, chunks: List[Chunk], top_n: int) -> list:
    """
    Runs BM25 keyword-based ranking over the full scoped chunk pool and
    returns the top_n highest-scoring (chunk_id, score) tuples, ordered
    by descending score.
    """
    if not chunks:
        return []

    tokenized_corpus = [c.chunk_text.lower().split() for c in chunks]
    bm25 = BM25Okapi(tokenized_corpus)

    tokenized_query = query_text.lower().split()
    scores = bm25.get_scores(tokenized_query)

    scored_chunks = list(zip(chunks, scores))
    scored_chunks.sort(key=lambda pair: pair[1], reverse=True)

    return [(chunk.id, score) for chunk, score in scored_chunks[:top_n] if score > 0]


# def _bm25_search(query_text: str, chunks: List[Chunk], top_n: int) -> set:
#     """
#     Runs BM25 keyword-based ranking over the full scoped chunk pool and
#     returns the IDs of the top_n highest-scoring chunks. Catches exact
#     keyword/term matches (proper nouns, numbers, formulas, acronyms) that
#     the semantic embedding model can sometimes under-rank.

#     Args:
#         query_text: The student's natural-language question.
#         chunks: The full scoped list of Chunk ORM objects to search over.
#         top_n: Number of top BM25-ranked chunk IDs to return.

#     Returns:
#         A set of Chunk.id values.
#     """
#     if not chunks:
#         return set()

#     tokenized_corpus = [c.chunk_text.lower().split() for c in chunks]
#     bm25 = BM25Okapi(tokenized_corpus)

#     tokenized_query = query_text.lower().split()
#     scores = bm25.get_scores(tokenized_query)

#     scored_chunks = list(zip(chunks, scores))
#     scored_chunks.sort(key=lambda pair: pair[1], reverse=True)

#     return {chunk.id for chunk, score in scored_chunks[:top_n] if score > 0}


# def _remove_near_duplicate_chunks(results: List[RetrievedChunk], similarity_cutoff: float = 0.95) -> List[RetrievedChunk]:
def _remove_near_duplicate_chunks(results: List[RetrievedChunk], similarity_cutoff: float = 0.35) -> List[RetrievedChunk]:#0.6
    """
    Removes chunks whose text is near-identical to a higher-ranked chunk
    already selected (e.g. overlapping sliding-window chunks can
    occasionally both surface as top results). Uses a cheap word-overlap
    heuristic rather than a second model comparison.

    Args:
        results: RetrievedChunk list, already ordered by descending score.
        similarity_cutoff: Jaccard-style word-overlap ratio above which
            two chunks are considered duplicates.

    Returns:
        A filtered list with near-duplicate lower-ranked chunks removed.
    """
    deduplicated: List[RetrievedChunk] = []
    seen_word_sets = []

    for result in results:
        words = set(result.chunk.chunk_text.lower().split())
        is_duplicate = False

        for seen_words in seen_word_sets:
            if not words or not seen_words:
                continue
            overlap_ratio = len(words & seen_words) / len(words | seen_words)
            if overlap_ratio >= similarity_cutoff:
                is_duplicate = True
                break

        if not is_duplicate:
            deduplicated.append(result)
            seen_word_sets.append(words)

    return deduplicated