"""
cleaning_service.py

Text cleaning / normalization layer of the RAG ingestion pipeline. Takes
the raw page-level text produced by extraction_service.py and removes
noise that would otherwise degrade embedding quality and retrieval
accuracy: repeated headers/footers, page numbers, excessive whitespace,
broken mid-word line breaks (a common PDF extraction artifact), and
non-informative boilerplate.

Cleaning runs AFTER extraction and BEFORE chunking_service.py, operating
on the same page-level list structure:
    [{"page_number": int, "text": str}, ...] -> [{"page_number": int, "text": str}, ...]
"""

import re
from collections import Counter
from typing import List, Dict

# ---------------------------------------------------------------------------
# Regex patterns for common noise
# ---------------------------------------------------------------------------
_MULTI_WHITESPACE_RE = re.compile(r"[ \t]+")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
_HYPHEN_LINEBREAK_RE = re.compile(r"(\w)-\n(\w)")          # e.g. "under-\nstanding" -> "understanding"
_STANDALONE_PAGE_NUMBER_RE = re.compile(r"^\s*\d{1,4}\s*$")  # A line that is ONLY a number (likely a page number)
_URL_TRAILING_JUNK_RE = re.compile(r"\s+(?=https?://)")
_NON_PRINTABLE_RE = re.compile(r"[^\x09\x0A\x0D\x20-\x7E\u00A0-\uFFFF]")


def clean_pages(pages: List[Dict]) -> List[Dict]:
    """
    Runs the full cleaning pipeline over a list of extracted pages.

    Steps:
        1. Detect and strip repeated headers/footers that appear on
           nearly every page (common in textbooks/lecture slides).
        2. Per-page cleaning: fix hyphenated line-breaks, collapse
           whitespace, strip standalone page-number lines, remove
           non-printable characters.

    Args:
        pages: Output of extraction_service.extract_text(), i.e.
            [{"page_number": int, "text": str}, ...]

    Returns:
        A new list in the same shape, with cleaned text per page.
    """
    header_footer_lines = _detect_repeated_header_footer_lines(pages)

    cleaned_pages = []
    for page in pages:
        text = page["text"]
        text = _strip_repeated_lines(text, header_footer_lines)
        text = _fix_hyphenated_linebreaks(text)
        text = _strip_standalone_page_numbers(text)
        text = _remove_non_printable_characters(text)
        text = _normalize_whitespace(text)

        cleaned_pages.append({"page_number": page["page_number"], "text": text})

    return cleaned_pages


# ---------------------------------------------------------------------------
# Repeated Header/Footer Detection
# ---------------------------------------------------------------------------
def _detect_repeated_header_footer_lines(pages: List[Dict], min_page_count: int = 3) -> set:
    """
    Identifies lines that repeat identically across a large proportion of
    pages (e.g. a textbook running header "Chapter 4: Thermodynamics" or
    a footer "© 2024 University Press"). These are almost always
    non-informative boilerplate rather than content relevant to answering
    student questions, so they are removed before chunking.

    Args:
        pages: The list of page dicts to analyze.
        min_page_count: Minimum number of pages required before header/
            footer detection runs at all (not worth it for very short
            documents, where "repetition" could just be coincidental
            short content).

    Returns:
        A set of line strings (stripped) considered repeated header/footer noise.
    """
    if len(pages) < min_page_count:
        return set()

    line_counter = Counter()
    for page in pages:
        # Only consider the first 2 and last 2 lines of each page as
        # header/footer candidates, since content in the middle of a page
        # is very unlikely to be boilerplate.
        lines = [line.strip() for line in page["text"].splitlines() if line.strip()]
        candidate_lines = lines[:2] + lines[-2:]
        line_counter.update(set(candidate_lines))

    # A line appearing on 60%+ of pages is treated as repeated boilerplate.
    threshold = max(int(len(pages) * 0.6), 2)
    return {line for line, count in line_counter.items() if count >= threshold and len(line) < 150}


def _strip_repeated_lines(text: str, repeated_lines: set) -> str:
    """Removes lines that match the detected repeated header/footer set."""
    if not repeated_lines:
        return text
    lines = text.splitlines()
    filtered = [line for line in lines if line.strip() not in repeated_lines]
    return "\n".join(filtered)


# ---------------------------------------------------------------------------
# Per-Line / Per-Page Cleaning Steps
# ---------------------------------------------------------------------------
def _fix_hyphenated_linebreaks(text: str) -> str:
    """
    Rejoins words that were split across a line break with a trailing
    hyphen — a very common PDF text-extraction artifact (e.g.
    "under-\\nstanding" becomes "understanding").
    """
    return _HYPHEN_LINEBREAK_RE.sub(r"\1\2", text)


def _strip_standalone_page_numbers(text: str) -> str:
    """Removes lines that consist of nothing but a page number."""
    lines = text.splitlines()
    filtered = [line for line in lines if not _STANDALONE_PAGE_NUMBER_RE.match(line)]
    return "\n".join(filtered)


def _remove_non_printable_characters(text: str) -> str:
    """
    Strips control characters and other non-printable bytes that can
    occasionally survive PDF/OCR extraction and would otherwise corrupt
    downstream embedding tokenization.
    """
    return _NON_PRINTABLE_RE.sub("", text)


def _normalize_whitespace(text: str) -> str:
    """
    Collapses runs of spaces/tabs into a single space, collapses 3+
    consecutive newlines down to exactly 2 (preserving paragraph breaks
    without excessive blank space), and trims leading/trailing whitespace.
    """
    text = _MULTI_WHITESPACE_RE.sub(" ", text)
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)
    # Normalize whitespace at the start/end of each line individually.
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(lines)
    return text.strip()