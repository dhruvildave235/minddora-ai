"""
field_extractor.py

Direct field extraction layer, used BEFORE the full hybrid retrieval
pipeline runs. For factual lookups (CGPA, email, phone, dates, amounts,
percentages, links, IDs), regex-based extraction over the raw document
text is far more reliable than embedding/rerank-based retrieval, since
these values are short, structured tokens that can be split across
chunk boundaries. When a field pattern is detected in the question and
a match is found in the document, this returns an exact, non-
hallucinated answer immediately — no LLM, no chunk ranking.

This works across ANY document type (resumes, invoices, contracts,
research papers, notes) since the patterns cover general categories of
structured facts, not just resume fields. If no pattern matches the
question, the caller falls through to the normal hybrid retrieval
pipeline — this module never blocks or breaks retrieval for documents
where no structured field applies.
"""

import re
from typing import List, Optional, Dict

from app.models.chunk import Chunk

# ---------------------------------------------------------------------------
# Field detection: field key -> (question keywords, extraction regex, label)
# General-purpose fields that apply across resumes, invoices, contracts,
# research papers, and notes — not limited to any one document type.
# ---------------------------------------------------------------------------
_FIELD_PATTERNS: Dict[str, Dict] = {
    "cgpa": {
        "keywords": ["cgpa", "gpa"],
        "pattern": re.compile(r"\b(\d{1,2}\.\d{1,2})\s*(?:cgpa|gpa)?\b", re.IGNORECASE),
        "label": "CGPA",
    },
    "percentage": {
        "keywords": ["percentage", "percent", "score"],
        "pattern": re.compile(r"\b(\d{1,3}(?:\.\d{1,2})?)\s*%"),
        "label": "Percentage",
    },
    "email": {
        "keywords": ["email", "e-mail", "mail"],
        "pattern": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
        "label": "Email",
    },
    "phone": {
        "keywords": ["phone", "mobile", "contact number", "call"],
        "pattern": re.compile(r"(?:\+\d{1,3}[-\s]?)?\d{10}\b"),
        "label": "Phone",
    },
    "linkedin": {
        "keywords": ["linkedin"],
        "pattern": re.compile(r"(?:linkedin\.com/in/[\w-]+|linkedin)", re.IGNORECASE),
        "label": "LinkedIn",
    },
    "github": {
        "keywords": ["github"],
        "pattern": re.compile(r"(?:github\.com/[\w-]+|github)", re.IGNORECASE),
        "label": "GitHub",
    },
    "website": {
        "keywords": ["website", "url", "link"],
        "pattern": re.compile(r"https?://[^\s,)]+|www\.[^\s,)]+"),
        "label": "Website/Link",
    },
    "date": {
        "keywords": ["date", "when", "deadline", "due date", "issued", "expiry", "expires"],
        "pattern": re.compile(
            r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"
            r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}|"
            r"\d{4}[/-]\d{1,2}[/-]\d{1,2})\b",
            re.IGNORECASE,
        ),
        "label": "Date",
    },
    "amount": {
        "keywords": ["amount", "price", "cost", "total", "fee", "salary", "payment", "bill", "invoice amount"],
        "pattern": re.compile(r"(?:₹|\$|Rs\.?|INR|USD)\s?[\d,]+(?:\.\d{1,2})?"),
        "label": "Amount",
    },
    "phone_ext": {
        "keywords": ["extension", "ext"],
        "pattern": re.compile(r"\bext\.?\s?\d{2,5}\b", re.IGNORECASE),
        "label": "Extension",
    },
    "id_number": {
        "keywords": ["id number", "reference number", "invoice number", "order number", "account number", "roll number", "enrollment number"],
        "pattern": re.compile(r"\b[A-Z0-9]{4,}[-/]?[A-Z0-9]{2,}\b"),
        "label": "ID/Reference Number",
    },
    "address": {
        "keywords": ["address", "located", "location"],
        "pattern": re.compile(r"\d{1,5}\s+[\w\s,.-]{5,60}(?:street|st|road|rd|avenue|ave|lane|ln|block|sector)[\w\s,.-]{0,40}", re.IGNORECASE),
        "label": "Address",
    },
    "duration": {
        "keywords": ["duration", "how long", "period", "term", "valid for"],
        "pattern": re.compile(r"\b\d{1,3}\s?(?:days?|weeks?|months?|years?|hrs?|hours?)\b", re.IGNORECASE),
        "label": "Duration",
    },
}


class ExtractedField:
    """Container for a directly-extracted factual answer."""

    def __init__(self, label: str, value: str, chunk: Chunk):
        self.label = label
        self.value = value
        self.chunk = chunk


def detect_field_intent(query_text: str) -> Optional[str]:
    """
    Checks whether the question is asking for a known structured field.
    Works across any document type — the field keywords are general
    categories (date, amount, email, etc.), not tied to resumes.

    Args:
        query_text: The student's natural-language question.

    Returns:
        The field key (e.g. "cgpa", "amount", "date") if detected, else None.
    """
    query_lower = query_text.lower()
    for field_key, config in _FIELD_PATTERNS.items():
        if any(kw in query_lower for kw in config["keywords"]):
            return field_key
    return None


def extract_field(field_key: str, chunks: List[Chunk]) -> Optional[ExtractedField]:
    """
    Runs the field's regex over all scoped chunks and returns the first
    match found, along with the chunk it came from (for citation).
    Prefers chunks that also mention the field's keyword (label + value
    together), falling back to any chunk containing just the pattern
    (value split from its label across a chunk boundary).

    Args:
        field_key: Key from _FIELD_PATTERNS (e.g. "cgpa", "amount").
        chunks: The scoped chunk pool to search over (already
            user/document filtered by the caller).

    Returns:
        An ExtractedField if a match is found anywhere in the scoped
        chunks, else None (caller falls through to hybrid retrieval).
    """
    config = _FIELD_PATTERNS.get(field_key)
    if not config:
        return None

    keyword_chunks = [c for c in chunks if any(kw in c.chunk_text.lower() for kw in config["keywords"])]
    other_chunks = [c for c in chunks if c not in keyword_chunks]
    search_order = keyword_chunks + other_chunks

    for chunk in search_order:
        match = config["pattern"].search(chunk.chunk_text)
        if match:
            return ExtractedField(label=config["label"], value=match.group(0).strip(), chunk=chunk)

    return None