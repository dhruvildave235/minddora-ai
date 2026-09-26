"""
chunking_service.py

Smart chunking layer of the RAG ingestion pipeline. Splits cleaned,
page-level text (from cleaning_service.py) into semantically coherent
chunks suitable for embedding, using a recursive, hierarchy-aware
splitting strategy with a sliding-window overlap between consecutive
chunks so context is not lost at chunk boundaries.

Splitting priority (most-preferred break point first):
    1. Paragraph breaks ("\n\n")
    2. Sentence breaks (". ", "! ", "? ")
    3. Line breaks ("\n")
    4. Word breaks (" ")
    5. Hard character cut (last resort, only for pathological single "words"
       longer than the chunk size, e.g. a long URL or unbroken string)

Output shape:
    [
        {
            "chunk_index": 0,
            "chunk_text": "...",
            "chunk_char_length": 512,
            "page_number": 3,
        },
        ...
    ]

Chunk size and overlap are read from Flask config (CHUNK_SIZE,
CHUNK_OVERLAP in app/config.py), expressed here in characters as an
approximation of tokens (roughly 4 characters per token for English
text), which keeps this module dependency-free from any tokenizer while
still producing appropriately-sized chunks for all-MiniLM-L6-v2's
256-token effective context window.
"""

from typing import List, Dict

# Approximate characters-per-token ratio used to convert the configured
# CHUNK_SIZE (in tokens) into a character-based splitting target, avoiding
# a hard dependency on a specific tokenizer at chunking time.
_CHARS_PER_TOKEN_ESTIMATE = 4

_SEPARATOR_HIERARCHY = ["\n\n", ". ", "! ", "? ", "\n", " "]


def chunk_document_pages(
    pages: List[Dict],
    chunk_size_tokens: int = 500,
    chunk_overlap_tokens: int = 75,
) -> List[Dict]:
    """
    Chunks every page's cleaned text and returns a single flat, globally
    ordered list of chunks across the whole document, each tagged with
    its originating page_number for citation purposes.

    Args:
        pages: Output of cleaning_service.clean_pages(), i.e.
            [{"page_number": int, "text": str}, ...]
        chunk_size_tokens: Target chunk size in tokens (approximate),
            sourced from app.config["CHUNK_SIZE"].
        chunk_overlap_tokens: Overlap between consecutive chunks in
            tokens (approximate), sourced from app.config["CHUNK_OVERLAP"].

    Returns:
        A flat list of chunk dicts:
            [{"chunk_index": int, "chunk_text": str,
              "chunk_char_length": int, "page_number": int}, ...]
    """
    chunk_size_chars = chunk_size_tokens * _CHARS_PER_TOKEN_ESTIMATE
    overlap_chars = chunk_overlap_tokens * _CHARS_PER_TOKEN_ESTIMATE

    all_chunks: List[Dict] = []
    global_index = 0

    for page in pages:
        page_text = page["text"]
        if not page_text or not page_text.strip():
            continue

        page_chunks = _recursive_split(page_text, chunk_size_chars, overlap_chars)

        for chunk_text in page_chunks:
            stripped = chunk_text.strip()
            if not stripped:
                continue
            all_chunks.append({
                "chunk_index": global_index,
                "chunk_text": stripped,
                "chunk_char_length": len(stripped),
                "page_number": page["page_number"],
            })
            global_index += 1

    return all_chunks


# ---------------------------------------------------------------------------
# Recursive Splitting Core
# ---------------------------------------------------------------------------
# def _recursive_split(text: str, chunk_size: int, overlap: int) -> List[str]:
#     """
#     Splits `text` into chunks of approximately `chunk_size` characters,
#     preferring to break at the highest-priority separator available
#     (paragraph > sentence > line > word), then applies a sliding-window
#     overlap between consecutive chunks.

#     Args:
#         text: The full page text to split.
#         chunk_size: Target maximum chunk length, in characters.
#         overlap: Number of trailing characters from the previous chunk to
#             prepend to the next chunk, preserving cross-boundary context.

#     Returns:
#         A list of chunk text strings (not yet stripped of edge whitespace
#         — callers should strip before persisting).
#     """
#     if len(text) <= chunk_size:
#         return [text]

#     segments = _split_by_hierarchy(text, chunk_size)
#     return _merge_segments_with_overlap(segments, chunk_size, overlap)


def _recursive_split(text: str, chunk_size: int, overlap: int) -> List[str]:
    """
    Splits `text` into chunks of approximately `chunk_size` characters,
    preferring to break at the highest-priority separator available
    (paragraph > sentence > line > word), then applies a sliding-window
    overlap between consecutive chunks.

    Implemented iteratively (not recursively) to guarantee it can never
    exceed Python's call-stack recursion limit, regardless of document
    size or structure — this matters especially for DOCX files, which
    are extracted as one large text blob rather than page-by-page.

    Args:
        text: The full page text to split.
        chunk_size: Target maximum chunk length, in characters.
        overlap: Number of trailing characters from the previous chunk to
            prepend to the next chunk, preserving cross-boundary context.

    Returns:
        A list of chunk text strings (not yet stripped of edge whitespace
        — callers should strip before persisting).
    """
    if len(text) <= chunk_size:
        return [text]

    segments = _split_by_hierarchy(text, chunk_size)
    return _merge_segments_with_overlap(segments, chunk_size, overlap)

def _split_by_hierarchy(text: str, chunk_size: int) -> List[str]:
    """
    Breaks text into small segments using the first separator in
    _SEPARATOR_HIERARCHY that successfully splits it into pieces no
    larger than chunk_size. Falls back progressively to finer-grained
    separators, and finally to a hard character cut if a single "word"
    (e.g. an unbroken URL) exceeds chunk_size on its own.

    Args:
        text: The text to split into raw segments (pre-merge).
        chunk_size: Target maximum segment length, in characters, used
            only to decide whether a hard cut is necessary as a last resort.

    Returns:
        A list of small text segments ready to be reassembled into
        appropriately-sized chunks by _merge_segments_with_overlap().
    """
    for separator in _SEPARATOR_HIERARCHY:
        if separator in text:
            raw_segments = text.split(separator)
            # Re-attach the separator to each segment (except the last)
            # so downstream merging preserves original formatting/punctuation.
            segments = [seg + separator for seg in raw_segments[:-1]] + [raw_segments[-1]]
            segments = [s for s in segments if s.strip()]
            if segments:
                return segments

    # Last resort: no separator found at all (e.g. one giant unbroken
    # string) — hard-cut into fixed-size pieces.
    return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]


# def _merge_segments_with_overlap(segments: List[str], chunk_size: int, overlap: int) -> List[str]:
#     """
#     Greedily merges small segments (from _split_by_hierarchy) into chunks
#     as close to chunk_size as possible without exceeding it, then applies
#     a sliding-window overlap by carrying the trailing `overlap` characters
#     of each finished chunk into the start of the next one.

#     Args:
#         segments: Small text segments to merge into properly-sized chunks.
#         chunk_size: Target maximum chunk length, in characters.
#         overlap: Number of trailing characters to carry into the next chunk.

#     Returns:
#         A list of finished chunk strings.
#     """
#     chunks: List[str] = []
#     current_chunk = ""

#     for segment in segments:
#         # If a single segment itself exceeds chunk_size (e.g. one very
#         # long sentence with no smaller separator), recursively split it
#         # further before merging.
#         if len(segment) > chunk_size:
#             if current_chunk:
#                 chunks.append(current_chunk)
#                 current_chunk = ""
#             sub_chunks = _recursive_split(segment, chunk_size, overlap)
#             chunks.extend(sub_chunks)
#             continue

#         if len(current_chunk) + len(segment) <= chunk_size:
#             current_chunk += segment
#         else:
#             if current_chunk:
#                 chunks.append(current_chunk)
#             # Start the new chunk with the overlap tail of the previous
#             # chunk (if any) plus the current segment, preserving context
#             # continuity across the boundary.
#             overlap_tail = current_chunk[-overlap:] if overlap > 0 and current_chunk else ""
#             current_chunk = overlap_tail + segment

#     if current_chunk:
#         chunks.append(current_chunk)

#     return chunks

def _merge_segments_with_overlap(segments: List[str], chunk_size: int, overlap: int) -> List[str]:
    """
    Greedily merges small segments (from _split_by_hierarchy) into chunks
    as close to chunk_size as possible without exceeding it, then applies
    a sliding-window overlap by carrying the trailing `overlap` characters
    of each finished chunk into the start of the next one.

    Any oversized segment (one that itself exceeds chunk_size — e.g. one
    very long sentence, or an entire DOCX table dumped into a single
    paragraph with no natural break points) is expanded further using an
    iterative work queue rather than a recursive function call, so this
    can never exceed Python's recursion limit no matter how large or
    unusually structured the input text is.

    Args:
        segments: Small text segments to merge into properly-sized chunks.
        chunk_size: Target maximum chunk length, in characters.
        overlap: Number of trailing characters to carry into the next chunk.

    Returns:
        A list of finished chunk strings.
    """
    chunks: List[str] = []
    current_chunk = ""

    queue: List[str] = list(segments)
    i = 0

    while i < len(queue):
        segment = queue[i]

        if len(segment) > chunk_size:
            expanded = _split_by_hierarchy(segment, chunk_size)

            # Safety net: if the hierarchy split couldn't shrink the
            # segment at all (e.g. one unbroken run of characters with no
            # separator whatsoever), force a hard character-level cut so
            # progress is guaranteed on every iteration.
            if len(expanded) == 1 and expanded[0] == segment:
                expanded = [segment[j:j + chunk_size] for j in range(0, len(segment), chunk_size)]

            queue[i:i + 1] = expanded
            continue  # Re-process this index now that it holds smaller pieces

        if len(current_chunk) + len(segment) <= chunk_size:
            current_chunk += segment
        else:
            if current_chunk:
                chunks.append(current_chunk)
            overlap_tail = current_chunk[-overlap:] if overlap > 0 and current_chunk else ""
            current_chunk = overlap_tail + segment

        i += 1

    if current_chunk:
        chunks.append(current_chunk)

    return chunks