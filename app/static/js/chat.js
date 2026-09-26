/**
 * chat.js
 *
 * Client-side logic for the AI Chat page: sending messages via
 * POST /api/chat/message, rendering the conversation (Markdown-rendered
 * assistant responses via marked.js, sanitized server-side already by
 * app/utils/security.py's sanitize_html on any HTML-bearing content),
 * a typing indicator while waiting for the response, citation chips,
 * confidence badges, and a "copy response" action.
 */

let currentSessionId = null;
let currentDocumentId = null;

document.addEventListener("DOMContentLoaded", () => {
    const layout = document.querySelector(".chat-page-layout");
    if (!layout) return;

    currentSessionId = layout.dataset.sessionId ? parseInt(layout.dataset.sessionId, 10) : null;
    currentDocumentId = layout.dataset.documentId ? parseInt(layout.dataset.documentId, 10) : null;

    initChatInputForm();
    initAutoResizeTextarea();
    scrollChatToBottom();
});

// ---------------------------------------------------------------------------
// Chat Input Form
// ---------------------------------------------------------------------------
function initChatInputForm() {
    const form = document.getElementById("chat-input-form");
    if (!form) return;

    form.addEventListener("submit", async (event) => {
        event.preventDefault();

        const textarea = document.getElementById("chat-input-textarea");
        const question = textarea.value.trim();
        if (!question) return;

        appendMessageToChat("user", question);
        textarea.value = "";
        textarea.style.height = "auto";

        const typingIndicatorId = showTypingIndicator();

        const response = await apiRequest("/api/chat/message", {
            method: "POST",
            body: {
                question: question,
                session_id: currentSessionId,
                document_id: currentDocumentId,
            },
            suppressErrorToast: true,
        });

        removeTypingIndicator(typingIndicatorId);

        if (response.success) {
            currentSessionId = response.data.session.id;

            // Update the URL to reflect the (possibly newly created) session,
            // without a full page reload, so refreshing the page keeps context.
            window.history.replaceState({}, "", `/chat/${currentSessionId}`);

            appendMessageToChat("assistant", response.data.assistant_message.content, {
                confidence: response.data.assistant_message.confidence_score,
                citations: response.data.assistant_message.citations,
            });
        } else {
            appendMessageToChat("assistant", `⚠️ ${response.error}`, {});
        }

        scrollChatToBottom();
    });
}

/**
 * Auto-expands the chat input textarea as the student types multi-line
 * questions, up to the max-height cap defined in chat.css.
 */
function initAutoResizeTextarea() {
    const textarea = document.getElementById("chat-input-textarea");
    if (!textarea) return;

    textarea.addEventListener("input", () => {
        textarea.style.height = "auto";
        textarea.style.height = `${textarea.scrollHeight}px`;
    });

    textarea.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            document.getElementById("chat-input-form").requestSubmit();
        }
    });
}

// ---------------------------------------------------------------------------
// Message Rendering
// ---------------------------------------------------------------------------
/**
 * Appends a new message bubble to the chat messages container.
 *
 * @param {string} role - "user" or "assistant".
 * @param {string} content - The message text (Markdown, for assistant messages).
 * @param {Object} [meta] - Optional metadata for assistant messages.
 * @param {number} [meta.confidence] - Confidence score (0.0-1.0).
 * @param {Array<Object>} [meta.citations] - Citation objects.
 */
function appendMessageToChat(role, content, meta = {}) {
    const container = document.getElementById("chat-messages-container");

    // Remove the "ask a question to get started" empty state on the first message.
    const emptyState = container.querySelector(".empty-state-text");
    if (emptyState) emptyState.remove();

    const row = document.createElement("div");
    row.className = `chat-message-row role-${role}`;

    const renderedContent = role === "assistant" && typeof marked !== "undefined"
        ? marked.parse(content)
        : escapeHtml(content);

    let confidenceHtml = "";
    if (role === "assistant" && meta.confidence !== undefined && meta.confidence !== null) {
        const level = meta.confidence >= 0.7 ? "high" : meta.confidence >= 0.4 ? "medium" : "low";
        confidenceHtml = `<span class="chat-confidence-badge confidence-${level}">${Math.round(meta.confidence * 100)}% confidence</span>`;
    }

    let citationsHtml = "";
    if (role === "assistant" && meta.citations && meta.citations.length > 0) {
        citationsHtml = `<div class="chat-citations-list">${meta.citations.map(c =>
            `<span class="chat-citation-chip">Source ${c.source_number}${c.page_number ? ` · p.${c.page_number}` : ""}</span>`
        ).join("")}</div>`;
    }

    const actionsHtml = role === "assistant"
        ? `<div class="chat-message-actions"><button onclick="copyMessageContent(this)">📋 Copy</button></div>`
        : "";

    row.innerHTML = `
        <div class="chat-message-bubble">
            <div class="message-content">${renderedContent}</div>
            ${confidenceHtml}
            ${citationsHtml}
            ${actionsHtml}
        </div>
    `;

    container.appendChild(row);
}

/**
 * Copies the text content of an assistant message bubble to the
 * clipboard, triggered by the "Copy" action button.
 *
 * @param {HTMLElement} buttonElement - The clicked copy button, used to
 *   locate its parent message bubble's content.
 */
function copyMessageContent(buttonElement) {
    const bubble = buttonElement.closest(".chat-message-bubble");
    const content = bubble.querySelector(".message-content").innerText;

    navigator.clipboard.writeText(content).then(() => {
        showToast("Copied to clipboard.", "success");
    });
}

// ---------------------------------------------------------------------------
// Typing Indicator
// ---------------------------------------------------------------------------
/**
 * Displays a typing indicator bubble while waiting for the AI's response.
 *
 * @returns {string} A unique DOM id for the indicator, used to remove it later.
 */
function showTypingIndicator() {
    const container = document.getElementById("chat-messages-container");
    const indicatorId = `typing-${Date.now()}`;

    const row = document.createElement("div");
    row.className = "chat-message-row role-assistant";
    row.id = indicatorId;
    row.innerHTML = `
        <div class="chat-message-bubble">
            <div class="typing-indicator"><span></span><span></span><span></span></div>
        </div>
    `;

    container.appendChild(row);
    scrollChatToBottom();

    return indicatorId;
}

/**
 * Removes a previously shown typing indicator by its DOM id.
 *
 * @param {string} indicatorId - The id returned by showTypingIndicator().
 */
function removeTypingIndicator(indicatorId) {
    const el = document.getElementById(indicatorId);
    if (el) el.remove();
}

// ---------------------------------------------------------------------------
// Scroll Helper
// ---------------------------------------------------------------------------
function scrollChatToBottom() {
    const container = document.getElementById("chat-messages-container");
    if (container) container.scrollTop = container.scrollHeight;
}

// ---------------------------------------------------------------------------
// AI Mode Selection Modal
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", async () => {
    const modal = document.getElementById("ai-mode-modal");
    if (!modal) return;

    // Only ask once per browser session per visit to the chat page.
    if (sessionStorage.getItem("minddora_ai_mode_chosen")) return;

    const meResponse = await apiRequest("/api/auth/me", { suppressErrorToast: true });
    const user = meResponse.success ? meResponse.data.user : null;

    modal.classList.remove("hidden");

    document.getElementById("mode-local-btn").addEventListener("click", async () => {
        await apiRequest("/api/auth/update-ai-settings", { method: "POST", body: { ai_mode: "local" } });
        sessionStorage.setItem("minddora_ai_mode_chosen", "local");
        modal.classList.add("hidden");
    });

    document.getElementById("mode-gemini-btn").addEventListener("click", () => {
        if (user && user.has_gemini_key) {
            // Already has a key saved — just switch mode, no need to re-enter it.
            apiRequest("/api/auth/update-ai-settings", { method: "POST", body: { ai_mode: "gemini" } });
            sessionStorage.setItem("minddora_ai_mode_chosen", "gemini");
            modal.classList.add("hidden");
        } else {
            document.getElementById("gemini-key-form").classList.remove("hidden");
        }
    });

    document.getElementById("gemini-save-btn").addEventListener("click", async () => {
        const apiKey = document.getElementById("gemini-api-key-input").value.trim();
        const modelName = document.getElementById("gemini-model-input").value.trim();

        if (!apiKey) {
            showToast("Please enter your Gemini API key.", "error");
            return;
        }

        const response = await apiRequest("/api/auth/update-ai-settings", {
            method: "POST",
            body: { ai_mode: "gemini", gemini_api_key: apiKey, gemini_model_name: modelName },
        });

        if (response.success) {
            showToast("AI mode enabled.", "success");
            sessionStorage.setItem("minddora_ai_mode_chosen", "gemini");
            modal.classList.add("hidden");
        }
    });
});