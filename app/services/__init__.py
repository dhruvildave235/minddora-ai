"""
services/__init__.py

Marks app/services/ as a Python package containing Minddora AI's business
logic layer, kept independent of Flask routing concerns so it can be
called identically from HTML-form blueprints, JSON API blueprints, or a
future background task worker.

Modules in this package:
    auth_service.py         - Registration, login, password reset, email verification
    document_service.py     - Upload orchestration, ingestion pipeline, deletion
    extraction_service.py   - PDF/DOCX/TXT/OCR text extraction
    cleaning_service.py     - Text normalization/cleaning
    chunking_service.py     - Recursive + sliding-window chunking
    embedding_service.py    - Batch embedding generation + vector store writes
    vector_store_service.py - FAISS/ChromaDB dispatch wrapper
    chat_service.py         - Conversation orchestration (retrieval + extractive answer)
    search_service.py       - Semantic/keyword/hybrid search for the Search Notes page
    analytics_service.py    - Student and admin usage statistics aggregation

This file intentionally contains no logic — it exists only to make the
directory an importable package. Callers should import specific service
modules directly, e.g.:

    from app.services import auth_service
    from app.services import document_service
"""