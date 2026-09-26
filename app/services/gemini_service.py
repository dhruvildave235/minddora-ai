"""
gemini_service.py

Optional, user-provided-key integration with Google's Gemini API, used
only when a student explicitly opts into AI-powered answers instead of
the default local extractive retrieval. Each student supplies their own
free API key from Google AI Studio (ai.google.dev) — Minddora AI never
pays for or shares a key, keeping the app itself free to run.

If the call fails for any reason (bad key, rate limit, network issue),
callers should catch GeminiError and fall back to the local extractive
answer_builder — Gemini is always an enhancement, never a hard dependency.
"""

import requests

_TIMEOUT_SECONDS = 30


class GeminiError(Exception):
    """Raised when a Gemini API call fails for any reason."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def generate_answer(question: str, context_chunks: list, api_key: str, model_name: str) -> str:
    """
    Calls Gemini's generateContent endpoint with the student's question
    and their retrieved document chunks as grounding context, asking the
    model to answer using ONLY that context.

    Args:
        question: The student's natural-language question.
        context_chunks: List of chunk text strings retrieved from the
            student's own documents (from the existing retrieval pipeline).
        api_key: The student's own Gemini API key.
        model_name: The Gemini model to use, e.g. "gemini-2.0-flash".

    Returns:
        The generated answer text.

    Raises:
        GeminiError: If the request fails, the key is invalid, or the
            response is empty/malformed.
    """
    if not api_key:
        raise GeminiError("No Gemini API key configured.")

    context_block = "\n\n".join(f"[Source {i+1}]\n{chunk}" for i, chunk in enumerate(context_chunks))

    prompt = (
        "You are a study assistant. Answer the student's question using ONLY the "
        "context below, which comes from their own uploaded notes. If the context "
        "doesn't contain the answer, say so honestly rather than guessing. Cite "
        "which source number you used.\n\n"
        f"CONTEXT:\n{context_block}\n\n"
        f"QUESTION: {question}"
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"

    try:
        response = requests.post(
            url,
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()

        candidates = data.get("candidates", [])
        if not candidates:
            raise GeminiError("Gemini returned no candidates.")

        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts)

        if not text.strip():
            raise GeminiError("Gemini returned an empty response.")

        return text.strip()

    except requests.exceptions.HTTPError as exc:
        if response.status_code == 400:
            raise GeminiError("Invalid Gemini API key or request.") from exc
        elif response.status_code == 429:
            raise GeminiError("Gemini rate limit reached. Try again shortly.") from exc
        raise GeminiError(f"Gemini API error: {exc}") from exc
    except requests.exceptions.RequestException as exc:
        raise GeminiError(f"Could not reach Gemini API: {exc}") from exc