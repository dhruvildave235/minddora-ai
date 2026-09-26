# """
# llm_client_service.py

# Provider-agnostic LLM client used exclusively by app.ai.generator to
# perform the final answer-generation call in the RAG pipeline. Isolating
# the actual HTTP call to the LLM provider in its own service (rather than
# inside app/ai/generator.py) keeps the AI engine decoupled from any single
# vendor's SDK/API shape, and makes swapping providers a one-file change.

# Provider selection and credentials are read from environment variables
# (documented in .env.example):
#     LLM_PROVIDER    -> "anthropic" | "openai" | "self_hosted"
#     LLM_API_KEY      -> API key for the selected provider
#     LLM_MODEL_NAME    -> Model identifier for the selected provider
#     LLM_API_BASE_URL  -> Override base URL (used for self_hosted / proxy setups)

# This module deliberately does NOT read Flask's app.config directly (to
# stay usable from non-request contexts such as background workers); it
# reads from os.environ via a small settings loader below.
# """

# import os
# import time
# from typing import List

# import requests

# _DEFAULT_TIMEOUT_SECONDS = 30
# _MAX_RETRIES = 2
# _RETRY_BACKOFF_SECONDS = 1.5


# class LLMClientError(Exception):
#     """
#     Raised for any failure calling the configured LLM provider (network
#     error, non-2xx response, malformed response body, missing
#     configuration). Caught by app.ai.generator and converted into a
#     user-facing GenerationError.
#     """

#     def __init__(self, message: str):
#         super().__init__(message)
#         self.message = message


# def _get_provider_settings() -> dict:
#     """
#     Reads LLM provider configuration from environment variables.

#     Returns:
#         A dict with keys "provider", "api_key", "model_name", "base_url".

#     Raises:
#         LLMClientError: If required configuration (provider or API key)
#             is missing, so misconfiguration fails fast with a clear
#             message rather than an obscure downstream error.
#     """
#     provider = os.environ.get("LLM_PROVIDER", "").strip().lower()
#     api_key = os.environ.get("LLM_API_KEY", "").strip()
#     model_name = os.environ.get("LLM_MODEL_NAME", "").strip()
#     base_url = os.environ.get("LLM_API_BASE_URL", "").strip()

#     if not provider:
#         raise LLMClientError("LLM_PROVIDER is not configured on the server.")
#     if not api_key:
#         raise LLMClientError("LLM_API_KEY is not configured on the server.")

#     return {"provider": provider, "api_key": api_key, "model_name": model_name, "base_url": base_url}


# def call_llm(system_prompt: str, messages: List[dict]) -> str:
#     """
#     Sends a chat-completion request to the configured LLM provider and
#     returns the generated text content.

#     Args:
#         system_prompt: The system instruction string (grounding/citation
#             rules), from app.ai.prompt_builder.
#         messages: List of {"role": "user"|"assistant", "content": str}
#             dicts representing conversation history plus the final,
#             context-augmented question.

#     Returns:
#         The generated answer text as a plain string.

#     Raises:
#         LLMClientError: If configuration is missing, the request fails
#             after retries, or the response cannot be parsed.
#     """
#     settings = _get_provider_settings()

#     dispatch = {
#         "anthropic": _call_anthropic,
#         "openai": _call_openai,
#         "self_hosted": _call_self_hosted,
#     }

#     handler = dispatch.get(settings["provider"])
#     if handler is None:
#         raise LLMClientError(f"Unsupported LLM_PROVIDER configured: {settings['provider']}")

#     last_error = None
#     for attempt in range(1, _MAX_RETRIES + 2):  # initial attempt + retries
#         try:
#             return handler(system_prompt, messages, settings)
#         except LLMClientError as exc:
#             last_error = exc
#             if attempt <= _MAX_RETRIES:
#                 time.sleep(_RETRY_BACKOFF_SECONDS * attempt)
#                 continue
#             raise last_error


# def _call_anthropic(system_prompt: str, messages: List[dict], settings: dict) -> str:
#     """
#     Calls the Anthropic Messages API.

#     Args:
#         system_prompt: System instruction string, passed as the top-level
#             "system" field per Anthropic's API shape.
#         messages: Conversation messages (user/assistant turns only —
#             Anthropic does not accept a "system" role inside the messages
#             array).
#         settings: Provider settings dict from _get_provider_settings().

#     Returns:
#         The generated text content from the response.

#     Raises:
#         LLMClientError: On network failure or a non-2xx response.
#     """
#     base_url = settings["base_url"] or "https://api.anthropic.com/v1/messages"
#     model_name = settings["model_name"] or "claude-sonnet-4-6"

#     try:
#         response = requests.post(
#             base_url,
#             headers={
#                 "x-api-key": settings["api_key"],
#                 "anthropic-version": "2023-06-01",
#                 "content-type": "application/json",
#             },
#             json={
#                 "model": model_name,
#                 "max_tokens": 1500,
#                 "system": system_prompt,
#                 "messages": messages,
#             },
#             timeout=_DEFAULT_TIMEOUT_SECONDS,
#         )
#         response.raise_for_status()
#         data = response.json()
#         content_blocks = data.get("content", [])
#         text_parts = [block.get("text", "") for block in content_blocks if block.get("type") == "text"]
#         return "".join(text_parts)
#     except requests.exceptions.RequestException as exc:
#         raise LLMClientError(f"Anthropic API request failed: {exc}") from exc
#     except (KeyError, ValueError) as exc:
#         raise LLMClientError(f"Unexpected Anthropic API response format: {exc}") from exc


# def _call_openai(system_prompt: str, messages: List[dict], settings: dict) -> str:
#     """
#     Calls an OpenAI-compatible Chat Completions API (works for OpenAI
#     itself, or any self-hosted/proxy service exposing the same schema
#     when LLM_API_BASE_URL is overridden).

#     Args:
#         system_prompt: System instruction string, injected as the first
#             message with role "system" per OpenAI's API shape.
#         messages: Conversation messages (user/assistant turns).
#         settings: Provider settings dict from _get_provider_settings().

#     Returns:
#         The generated text content from the response.

#     Raises:
#         LLMClientError: On network failure or a non-2xx response.
#     """
#     base_url = settings["base_url"] or "https://api.openai.com/v1/chat/completions"
#     model_name = settings["model_name"] or "gpt-4o-mini"

#     full_messages = [{"role": "system", "content": system_prompt}] + messages

#     try:
#         response = requests.post(
#             base_url,
#             headers={
#                 "Authorization": f"Bearer {settings['api_key']}",
#                 "Content-Type": "application/json",
#             },
#             json={
#                 "model": model_name,
#                 "messages": full_messages,
#                 "max_tokens": 1500,
#                 "temperature": 0.3,
#             },
#             timeout=_DEFAULT_TIMEOUT_SECONDS,
#         )
#         response.raise_for_status()
#         data = response.json()
#         return data["choices"][0]["message"]["content"]
#     except requests.exceptions.RequestException as exc:
#         raise LLMClientError(f"OpenAI-compatible API request failed: {exc}") from exc
#     except (KeyError, IndexError, ValueError) as exc:
#         raise LLMClientError(f"Unexpected OpenAI-compatible API response format: {exc}") from exc


# def _call_self_hosted(system_prompt: str, messages: List[dict], settings: dict) -> str:
#     """
#     Calls a self-hosted inference endpoint that implements the same
#     OpenAI-compatible Chat Completions schema (e.g. vLLM, text-generation-
#     inference, LM Studio server). Reuses _call_openai's request/response
#     handling since the wire format is identical; only the base URL and
#     absence of a real API key differ.

#     Args:
#         system_prompt: System instruction string.
#         messages: Conversation messages.
#         settings: Provider settings dict — LLM_API_BASE_URL is required
#             for this provider since there is no public default endpoint.

#     Returns:
#         The generated text content from the response.

#     Raises:
#         LLMClientError: If LLM_API_BASE_URL is not set, or on request failure.
#     """
#     if not settings["base_url"]:
#         raise LLMClientError("LLM_API_BASE_URL must be set when LLM_PROVIDER=self_hosted.")

#     return _call_openai(system_prompt, messages, settings)