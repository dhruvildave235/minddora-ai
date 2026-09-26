/**
 * history.js
 *
 * Client-side logic for the History and Saved Conversations pages:
 * bookmark toggling, session deletion (archiving), and client-side
 * pagination refresh via GET /api/chat/sessions. Both pages share the
 * same template (chat/history.html) and this same script, distinguished
 * by the `bookmarked_only` data attribute on #history-list.
 */

let currentHistoryPage = 1;

document.addEventListener("DOMContentLoaded", () => {
    const listContainer = document.getElementById("history-list");
    if (listContainer) {
        refreshHistoryPagination();
    }
});

/**
 * Toggles the bookmark status of a chat session, calling
 * POST /api/chat/sessions/<id>/bookmark. On the Saved Conversations
 * page, unbookmarking removes the card from the list entirely (since it
 * no longer belongs there); on the History page, it just updates the label.
 *
 * @param {number} sessionId - The ChatSession.id to toggle.
 * @param {HTMLElement} buttonElement - The clicked button, for in-place label updates.
 */
async function toggleSessionBookmark(sessionId, buttonElement) {
    const response = await apiRequest(`/api/chat/sessions/${sessionId}/bookmark`, { method: "POST" });
    if (!response.success) return;

    showToast(response.message, "success");

    const isBookmarkedOnlyView = document.getElementById("history-list").dataset.bookmarkedOnly === "true";

    if (isBookmarkedOnlyView && !response.data.session.is_bookmarked) {
        const card = document.querySelector(`[data-session-id="${sessionId}"]`);
        if (card) card.remove();
    } else {
        buttonElement.textContent = response.data.session.is_bookmarked ? "Unsave" : "Save";
        const icon = document.querySelector(`[data-session-id="${sessionId}"] .document-card-icon`);
        if (icon) icon.textContent = response.data.session.is_bookmarked ? "⭐" : "💬";
    }
}

/**
 * Archives (soft-deletes) a chat session after confirmation, calling
 * DELETE /api/chat/sessions/<id> and removing the card from the DOM.
 *
 * @param {number} sessionId - The ChatSession.id to delete.
 */
async function deleteSession(sessionId) {
    if (!confirm("Delete this conversation? This cannot be undone.")) return;

    const response = await apiRequest(`/api/chat/sessions/${sessionId}`, { method: "DELETE" });

    if (response.success) {
        showToast(response.message, "success");
        const card = document.querySelector(`[data-session-id="${sessionId}"]`);
        if (card) card.remove();
    }
}

/**
 * Fetches pagination metadata for the current view (History or Saved
 * Conversations) to render page navigation controls beneath the
 * server-rendered first page of results.
 */
async function refreshHistoryPagination() {
    const bookmarkedOnly = document.getElementById("history-list").dataset.bookmarkedOnly === "true";
    const params = new URLSearchParams({ page: 1, per_page: 20, bookmarked_only: bookmarkedOnly });

    const response = await apiRequest(`/api/chat/sessions?${params.toString()}`, { suppressErrorToast: true });
    if (!response.success) return;

    renderHistoryPagination(response.data.pagination, bookmarkedOnly);
}

/**
 * Renders pagination buttons and wires them to reload the history list
 * via fetch when a different page is selected.
 *
 * @param {Object} pagination - The pagination metadata object.
 * @param {boolean} bookmarkedOnly - Whether this is the Saved Conversations view.
 */
function renderHistoryPagination(pagination, bookmarkedOnly) {
    const container = document.getElementById("history-pagination");
    if (!container || pagination.total_pages <= 1) return;

    const buttons = [];
    for (let i = 1; i <= pagination.total_pages; i++) {
        buttons.push(`<button class="btn btn-ghost btn-sm ${i === currentHistoryPage ? "active" : ""}" data-page="${i}">${i}</button>`);
    }
    container.innerHTML = buttons.join("");

    container.querySelectorAll("[data-page]").forEach(btn => {
        btn.addEventListener("click", async () => {
            currentHistoryPage = parseInt(btn.dataset.page, 10);
            const params = new URLSearchParams({ page: currentHistoryPage, per_page: 20, bookmarked_only: bookmarkedOnly });
            const response = await apiRequest(`/api/chat/sessions?${params.toString()}`);
            if (response.success) {
                renderHistoryList(response.data.items, bookmarkedOnly);
                renderHistoryPagination(response.data.pagination, bookmarkedOnly);
            }
        });
    });
}

/**
 * Re-renders the history/saved-conversations list with a new set of
 * session items, replacing the current DOM contents.
 *
 * @param {Array<Object>} sessions - Array of serialized ChatSession dicts.
 * @param {boolean} bookmarkedOnly - Whether this is the Saved Conversations view.
 */
function renderHistoryList(sessions, bookmarkedOnly) {
    const container = document.getElementById("history-list");
    if (!container) return;

    if (sessions.length === 0) {
        container.innerHTML = `<p class="empty-state-text">No conversations found.</p>`;
        return;
    }

    container.innerHTML = sessions.map(session => `
        <div class="glass-card document-card" data-session-id="${session.id}">
            <div class="document-card-icon">${session.is_bookmarked ? "⭐" : "💬"}</div>
            <div class="document-card-title">${escapeHtml(session.title)}</div>
            <div class="document-card-meta">${session.message_count} messages &middot; ${new Date(session.updated_at).toLocaleDateString()}</div>
            <div class="document-card-actions">
                <a href="/chat/${session.id}" class="btn btn-ghost btn-sm">Open</a>
                <button class="btn btn-ghost btn-sm" onclick="toggleSessionBookmark(${session.id}, this)">${session.is_bookmarked ? "Unsave" : "Save"}</button>
                <button class="btn btn-ghost btn-sm" onclick="deleteSession(${session.id})">Delete</button>
            </div>
        </div>
    `).join("");
}