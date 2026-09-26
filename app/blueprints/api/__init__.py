"""
blueprints/api/__init__.py

Marks app/blueprints/api/ as a Python package containing all JSON REST
API blueprints for Minddora AI:

    auth_api.py     -> auth_api_bp     (registered at /api/auth)
    document_api.py -> document_api_bp (registered at /api/documents)
    chat_api.py      -> chat_api_bp     (registered at /api/chat)
    search_api.py    -> search_api_bp   (registered at /api/search)
    admin_api.py      -> admin_api_bp    (registered at /api/admin)

Unlike app/blueprints/auth/__init__.py, this package does not re-export a
single Blueprint object, since each submodule defines and registers its
own independent Blueprint with its own url_prefix (applied in
app/__init__.py's create_app()). This file intentionally stays empty of
logic — it exists only to make the directory an importable package.
"""
# </parameter>