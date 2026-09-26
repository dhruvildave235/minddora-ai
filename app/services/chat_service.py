"""
chat_service.py

Business logic layer for the AI chat feature. Orchestrates a full chat
turn: create/resolve a ChatSession, pull recent conversation history for
continuity, run the retrieval pipeline (app.ai.retriever), synthesize an
extractive answer (app.ai.answer_builder — no generative LLM), and
persist both the user's question and the AI's answer as ChatMessage rows
in PostgreSQL.

Also provides session management (listing, renaming, bookmarking,
archiving, deleting) used by the History and Saved Conversations pages.
"""

from typing import List, Optional

from app.extensions import db
from app.models.chat import ChatSession, ChatMessage
from app.models.document import Document
from app.ai.retriever import retrieve_relevant_chunks
from app.ai.answer_builder import build_answer
# from app.utils.validators import is_non_empty_string, sanitize_plain_text
from app.utils.logger import log_to_db
from app.utils.validators import is_non_empty_string
from app.utils.security import sanitize_plain_text

from app.models.user import User

class ChatServiceError(Exception):
    """
    Raised for any expected failure in the chat flow (session not found,
    unauthorized access, invalid/empty question). Carries a machine-
    readable error_code for the API layer to map to the correct HTTP status.
    """

    def __init__(self, message: str, error_code: str = "CHAT_ERROR"):
        super().__init__(message)
        self.message = message
        self.error_code = error_code


# ---------------------------------------------------------------------------
# Core Chat Turn
# ---------------------------------------------------------------------------
def send_message(
    user_id: int,
    question: str,
    session_id: Optional[int] = None,
    document_id: Optional[int] = None,
    top_k: int = 5,
    similarity_threshold: float = 0.30,
    embedding_model_name: str = "all-MiniLM-L6-v2",
) -> dict:
    """
    Processes one full chat turn: resolves/creates the ChatSession,
    persists the user's question, runs retrieval + extractive answer
    synthesis, persists the AI's answer, and returns both messages plus
    session metadata for the frontend to render.

    Args:
        user_id: The authenticated student's ID.
        question: The student's natural-language question.
        session_id: Optional existing ChatSession.id to continue. If
            None, a new session is created (optionally scoped to
            document_id).
        document_id: Optional single-document scope for this session. If
            provided when creating a new session, the session is locked
            to searching only that document; ignored if session_id refers
            to an existing session (that session's own scope is used
            instead).
        top_k: Sourced from app.config["TOP_K_RETRIEVAL"].
        similarity_threshold: Sourced from app.config["SIMILARITY_THRESHOLD"].
        embedding_model_name: Sourced from app.config["EMBEDDING_MODEL_NAME"].

    Returns:
        A dict: {"session": ChatSession.to_dict(), "user_message": {...},
                 "assistant_message": {...}}

    Raises:
        ChatServiceError: If the question is empty, or the referenced
            session/document is not found or not owned by this user.
    """
    if not is_non_empty_string(question, max_length=2000):
        raise ChatServiceError("Please enter a question before sending.", "EMPTY_QUESTION")

    question = sanitize_plain_text(question)

    session = _resolve_session(user_id, session_id, document_id)

    user_message = ChatMessage(session_id=session.id, role="user", content=question)
    db.session.add(user_message)
    db.session.commit()

    conversation_history = _build_history_payload(session.id, exclude_message_id=user_message.id)

    # retrieved_chunks = retrieve_relevant_chunks(
    #     query_text=question,
    #     user_id=user_id,
    #     document_id=session.document_id,
    #     top_k=top_k,
    #     similarity_threshold=similarity_threshold,
    #     embedding_model_name=embedding_model_name,
    # )

    # answer_payload = build_answer(question=question, retrieved_chunks=retrieved_chunks)
    retrieved_chunks = retrieve_relevant_chunks(
        query_text=question,
        user_id=user_id,
        document_id=session.document_id,
        top_k=top_k,
        similarity_threshold=similarity_threshold,
        embedding_model_name=embedding_model_name,
    )

    user = User.query.get(user_id)
    answer_payload = None

    if user and user.ai_mode == "gemini" and user.gemini_api_key and retrieved_chunks:
        from app.services import gemini_service

        try:
            gemini_text = gemini_service.generate_answer(
                question=question,
                context_chunks=[r.chunk.chunk_text for r in retrieved_chunks],
                api_key=user.gemini_api_key,
                model_name=user.gemini_model_name or "gemini-2.0-flash",
            )
            citations = _build_citations_for_gemini(retrieved_chunks)
            answer_payload = {
                "answer_text": gemini_text,
                "citations": citations,
                "confidence_score": 0.9,
            }
        except gemini_service.GeminiError as exc:
            log_to_db(
                level="WARNING",
                category="chat",
                message=f"Gemini call failed for user {user.email}, falling back to local: {exc.message}",
                user_id=user_id,
            )

    if answer_payload is None:
        answer_payload = build_answer(question=question, retrieved_chunks=retrieved_chunks)

    

    assistant_message = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=answer_payload["answer_text"],
        citations=answer_payload["citations"],
        confidence_score=answer_payload["confidence_score"],
        retrieval_chunk_count=len(retrieved_chunks),
    )
    db.session.add(assistant_message)

    if session.title == "New Conversation":
        session.title = _generate_session_title(question)

    db.session.commit()

    log_to_db(
        level="INFO",
        category="chat",
        message=f"Chat turn processed for session {session.id}.",
        context={"retrieved_chunk_count": len(retrieved_chunks)},
        user_id=user_id,
    )

    return {
        "session": session.to_dict(),
        "user_message": user_message.to_dict(),
        "assistant_message": assistant_message.to_dict(),
    }

def _build_citations_for_gemini(retrieved_chunks) -> list:
    """Builds a citation list for a Gemini-generated answer, matching the shape used by the local answer_builder."""
    citations = []
    for i, r in enumerate(retrieved_chunks, start=1):
        citation = r.chunk.to_citation()
        citation["source_number"] = i
        citations.append(citation)
    return citations


def _resolve_session(user_id: int, session_id: Optional[int], document_id: Optional[int]) -> ChatSession:
    """
    Resolves the ChatSession for this chat turn — either loading an
    existing session (with an ownership check) or creating a new one,
    optionally scoped to a single document.

    Args:
        user_id: The authenticated student's ID.
        session_id: Optional existing ChatSession.id.
        document_id: Optional document scope for a newly created session.

    Returns:
        The resolved ChatSession instance.

    Raises:
        ChatServiceError: If session_id is provided but not found/owned
            by this user, or if document_id is provided but not found/
            owned by this user.
    """
    if session_id is not None:
        session = ChatSession.query.filter_by(id=session_id, user_id=user_id).first()
        if session is None:
            raise ChatServiceError("Chat session not found.", "SESSION_NOT_FOUND")
        return session

    if document_id is not None:
        document = Document.query.filter_by(id=document_id, user_id=user_id, is_deleted=False).first()
        if document is None:
            raise ChatServiceError("Document not found.", "DOCUMENT_NOT_FOUND")

    new_session = ChatSession(user_id=user_id, document_id=document_id, title="New Conversation")
    db.session.add(new_session)
    db.session.commit()
    return new_session


def _build_history_payload(session_id: int, exclude_message_id: int, max_messages: int = 10) -> List[dict]:
    """
    Builds a lightweight role/content history list from the most recent
    ChatMessage rows in this session (excluding the just-inserted user
    message, since it's passed separately), used only for conversational
    context awareness — in this extractive (no-LLM) pipeline, history is
    not fed into a prompt, but is retained here for the future generative
    upgrade path noted in the Future Features roadmap.

    Args:
        session_id: The ChatSession.id to pull history from.
        exclude_message_id: The just-inserted user ChatMessage.id to
            exclude from the returned history.
        max_messages: Maximum number of prior messages to include.

    Returns:
        A list of {"role": ..., "content": ...} dicts, oldest-to-newest.
    """
    messages = (
        ChatMessage.query.filter(ChatMessage.session_id == session_id, ChatMessage.id != exclude_message_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(max_messages)
        .all()
    )
    messages.reverse()
    return [{"role": m.role, "content": m.content} for m in messages]


def _generate_session_title(question: str, max_length: int = 60) -> str:
    """
    Derives a short, human-readable session title from the student's
    first question in a new conversation, so the History/Saved
    Conversations pages show meaningful titles instead of "New
    Conversation" for every entry.

    Args:
        question: The first question asked in this session.
        max_length: Maximum character length for the derived title.

    Returns:
        A trimmed title string, ellipsized if truncated.
    """
    cleaned = question.strip()
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[:max_length].rsplit(" ", 1)[0] + "..."


# ---------------------------------------------------------------------------
# Session Management
# ---------------------------------------------------------------------------
def get_user_sessions(user_id: int, page: int = 1, per_page: int = 20, bookmarked_only: bool = False) -> tuple:
    """
    Retrieves a paginated list of a student's chat sessions for the
    History page (or Saved Conversations page, when bookmarked_only=True).

    Args:
        user_id: The requesting student's ID.
        page: 1-indexed page number.
        per_page: Number of sessions per page.
        bookmarked_only: If True, restricts results to sessions with
            is_bookmarked=True.

    Returns:
        A tuple of (sessions: List[ChatSession], total_count: int).
    """
    query = ChatSession.query.filter_by(user_id=user_id, is_archived=False)
    if bookmarked_only:
        query = query.filter_by(is_bookmarked=True)

    query = query.order_by(ChatSession.updated_at.desc())

    total_count = query.count()
    sessions = query.offset((page - 1) * per_page).limit(per_page).all()

    return sessions, total_count


def get_session_with_messages(session_id: int, user_id: int) -> ChatSession:
    """
    Retrieves a single chat session with its full message history,
    enforcing ownership.

    Args:
        session_id: The ChatSession.id to retrieve.
        user_id: The requesting student's ID.

    Returns:
        The ChatSession instance (messages accessible via session.messages).

    Raises:
        ChatServiceError: If not found or not owned by this user.
    """
    session = ChatSession.query.filter_by(id=session_id, user_id=user_id).first()
    if session is None:
        raise ChatServiceError("Chat session not found.", "SESSION_NOT_FOUND")
    return session


def rename_session(session_id: int, user_id: int, new_title: str) -> ChatSession:
    """
    Renames a chat session, e.g. from the History page's inline edit action.

    Args:
        session_id: The ChatSession.id to rename.
        user_id: The requesting student's ID (ownership enforcement).
        new_title: The new title text.

    Returns:
        The updated ChatSession instance.

    Raises:
        ChatServiceError: If not found/owned, or the new title is invalid.
    """
    if not is_non_empty_string(new_title, max_length=255):
        raise ChatServiceError("Title cannot be empty.", "INVALID_TITLE")

    session = get_session_with_messages(session_id, user_id)
    session.title = sanitize_plain_text(new_title)
    db.session.commit()
    return session


def toggle_bookmark(session_id: int, user_id: int) -> ChatSession:
    """
    Toggles the is_bookmarked flag on a chat session, used by the
    bookmark/star icon on the History and Chat pages.

    Args:
        session_id: The ChatSession.id to toggle.
        user_id: The requesting student's ID (ownership enforcement).

    Returns:
        The updated ChatSession instance.

    Raises:
        ChatServiceError: If not found or not owned by this user.
    """
    session = get_session_with_messages(session_id, user_id)
    session.is_bookmarked = not session.is_bookmarked
    db.session.commit()
    return session


def archive_session(session_id: int, user_id: int) -> None:
    """
    Archives (soft-hides) a chat session from the default History list,
    used by a "Delete conversation" action in the UI without permanently
    destroying the data.

    Args:
        session_id: The ChatSession.id to archive.
        user_id: The requesting student's ID (ownership enforcement).

    Raises:
        ChatServiceError: If not found or not owned by this user.
    """
    session = get_session_with_messages(session_id, user_id)
    session.is_archived = True
    db.session.commit()