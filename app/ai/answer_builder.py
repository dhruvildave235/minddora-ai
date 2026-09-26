
import re
from typing import List

from app.ai.retriever import RetrievedChunk

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def build_answer(question: str, retrieved_chunks: List[RetrievedChunk]) -> dict:
    """
    Builds the final answer payload for a chat turn using extractive
    synthesis — no LLM call involved. Returns a direct field-extraction
    result immediately when available (see retriever.py Stage 0).

    Args:
        question: The student's natural-language question (used for
            sentence-level relevance highlighting within each chunk).
        retrieved_chunks: Ranked, deduplicated RetrievedChunk list from
            app.ai.retriever.retrieve_relevant_chunks().

    Returns:
        A dict with keys:
            "answer_text": str — Markdown-formatted extractive answer
            "citations": list[dict] — citation objects for ChatMessage.citations
            "confidence_score": float — 0.0 to 1.0
    """
    if not retrieved_chunks:
        return {
            "answer_text": (
                "I couldn't find this information in the uploaded document. "
                "Try rephrasing your question, or upload notes that cover this topic."
            ),
            "citations": [],
            "confidence_score": 0.0,
        }

    if len(retrieved_chunks) == 1 and getattr(retrieved_chunks[0], "extracted_field", None):
        return _build_field_extraction_answer(retrieved_chunks[0])

    answer_text = _format_extractive_answer(question, retrieved_chunks)
    citations = _build_citations(retrieved_chunks)
    confidence_score = _compute_confidence_score(retrieved_chunks)

    return {
        "answer_text": answer_text,
        "citations": citations,
        "confidence_score": confidence_score,
    }


def _build_field_extraction_answer(result: RetrievedChunk) -> dict:
    """
    Formats a direct field-extraction result (CGPA, email, date, amount,
    etc.) into the standard answer payload shape, with a high confidence
    score since the value was matched via exact pattern extraction rather
    than semantic similarity estimation.

    Args:
        result: The single RetrievedChunk carrying an extracted_field.

    Returns:
        The standard answer payload dict.
    """
    field = result.extracted_field
    chunk = result.chunk
    page_info = f" (Page {chunk.page_number})" if chunk.page_number else ""

    answer_text = f"**Your {field.label} is {field.value}.**\n\nSource: Document #{chunk.document_id}{page_info}"

    citation = chunk.to_citation()
    citation["source_number"] = 1

    return {
        "answer_text": answer_text,
        "citations": [citation],
        "confidence_score": 0.98,
    }


def _format_extractive_answer(question: str, retrieved_chunks: List[RetrievedChunk]) -> str:
    """
    Formats the retrieved chunks into a readable Markdown answer. For
    each source, extracts and highlights the most query-relevant
    sentence(s) within the chunk (via keyword overlap) so the student
    sees the sharpest, most on-topic excerpt first, followed by the
    surrounding context, rather than the raw chunk dumped as-is.

    Args:
        question: The student's question, used to identify the most
            relevant sentence(s) within each chunk via keyword overlap.
        retrieved_chunks: Ranked RetrievedChunk list.

    Returns:
        A Markdown-formatted answer string with numbered source sections.
    """
    if len(retrieved_chunks) == 1:
        intro = "Here's what I found in your notes:"
    else:
        intro = f"Here's what I found across {len(retrieved_chunks)} relevant sections of your notes:"

    sections = [intro, ""]

    for i, retrieved in enumerate(retrieved_chunks, start=1):
        chunk = retrieved.chunk
        page_info = f" (Page {chunk.page_number})" if chunk.page_number else ""
        highlighted = _highlight_relevant_sentences(question, chunk.chunk_text)

        sections.append(f"**Source {i}{page_info}:**")
        sections.append(highlighted)
        sections.append("")

    return "\n".join(sections).strip()


def _highlight_relevant_sentences(question: str, chunk_text: str, max_sentences: int = 2) -> str:#4
    """
    Selects and bolds the sentence(s) within a chunk that most closely
    match the question's keywords, then returns a trimmed excerpt (the
    best sentence plus limited surrounding context) rather than the
    entire chunk, keeping answers focused and scannable.

    Args:
        question: The student's question, tokenized for keyword overlap.
        chunk_text: The full text of the retrieved chunk.
        max_sentences: Maximum number of sentences to include in the
            returned excerpt.

    Returns:
        A Markdown string with the most relevant sentence bolded.
    """
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(chunk_text) if s.strip()]
    if not sentences:
        return chunk_text

    question_words = set(w.lower() for w in question.split() if len(w) > 2)

    scored_sentences = []
    for sentence in sentences:
        sentence_words = set(w.lower().strip(".,!?;:") for w in sentence.split())
        overlap = len(question_words & sentence_words)
        scored_sentences.append((sentence, overlap))

    best_sentence, best_score = max(scored_sentences, key=lambda pair: pair[1])
    best_index = sentences.index(best_sentence)

    start = max(0, best_index - 1)
    end = min(len(sentences), start + max_sentences)

    excerpt_sentences = []
    for idx in range(start, end):
        if idx == best_index and best_score > 0:
            excerpt_sentences.append(f"**{sentences[idx]}**")
        else:
            excerpt_sentences.append(sentences[idx])

    return " ".join(excerpt_sentences)


def _build_citations(retrieved_chunks: List[RetrievedChunk]) -> List[dict]:
    """
    Builds the citation payload stored on ChatMessage.citations and
    rendered in the Chat UI as clickable source references.

    Args:
        retrieved_chunks: The RetrievedChunk list used for this answer.

    Returns:
        A list of citation dicts, e.g.:
        [{"source_number": 1, "document_id": 12, "chunk_id": 88,
          "page_number": 4, "excerpt": "...", "relevance_score": 0.81}]
    """
    citations = []
    for i, retrieved in enumerate(retrieved_chunks, start=1):
        citation = retrieved.chunk.to_citation()
        citation["source_number"] = i
        citation["relevance_score"] = round(retrieved.relevance_score, 4)
        citations.append(citation)
    return citations


# def _compute_confidence_score(retrieved_chunks: List[RetrievedChunk]) -> float:
#     """
#     Derives an overall confidence score for the answer from the
#     cross-encoder relevance scores of the chunks used, displayed in the
#     Chat UI as a confidence indicator. Weighted toward the top result
#     while still factoring in the average across all used sources.

#     Args:
#         retrieved_chunks: The RetrievedChunk list used for this answer.

#     Returns:
#         A float between 0.0 and 1.0.
#     """
#     if not retrieved_chunks:
#         return 0.0

#     scores = [r.relevance_score for r in retrieved_chunks]
#     top_score = max(scores)
#     average_score = sum(scores) / len(scores)

#     weighted_score = (0.7 * top_score) + (0.3 * average_score)
#     return round(min(max(weighted_score, 0.0), 1.0), 4)

def _compute_confidence_score(retrieved_chunks: List[RetrievedChunk]) -> float:
    """
    ... (existing docstring)
    """
    scores = [r.relevance_score for r in retrieved_chunks]
    top_score = max(scores)
    average_score = sum(scores) / len(scores)

    weighted_score = (0.7 * top_score) + (0.3 * average_score)

    # Recalibration: cross-encoder scores after sigmoid rarely reach the
    # top of the 0-1 range even for strong matches, which makes raw
    # scores under-represent true answer quality. Stretch the practical
    # 0.05-0.6 working range up to a fuller, more intuitive 0-1 display
    # range, without changing which chunks get selected (this only
    # affects the displayed percentage, not retrieval decisions).
    calibrated = (weighted_score - 0.05) / (0.6 - 0.05)
    return round(min(max(calibrated, 0.0), 1.0), 4)