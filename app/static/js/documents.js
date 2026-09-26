/**
 * documents.js
 *
 * Client-side logic for the My Documents page: delete and retry
 * (reprocess) actions, plus client-side pagination refresh via
 * GET /api/documents when more than one page of results exists. The
 * initial page load is server-rendered (first 20 documents); this file
 * takes over for subsequent pages and post-action refreshes.
 */

let currentDocumentsListPage = 1;

document.addEventListener("DOMContentLoaded", () => {
    const paginationContainer = document.getElementById("documents-list-pagination");
    if (paginationContainer) {
        // Only wire up client-side pagination if the grid exists on this page.
        refreshDocumentsGridPagination();
    }
});

/**
 * Deletes a document after user confirmation, calling
 * DELETE /api/documents/<id> and removing the card from the DOM on success.
 *
 * @param {number} documentId - The Document.id to delete.
 */
async function deleteDocument(documentId) {
    if (!confirm("Delete this document? This will remove it and all its indexed content permanently.")) {
        return;
    }

    const response = await apiRequest(`/api/documents/${documentId}`, { method: "DELETE" });

    if (response.success) {
        showToast(response.message, "success");
        const card = document.querySelector(`[data-document-id="${documentId}"]`);
        if (card) card.remove();
    }
}

/**
 * Re-runs the ingestion pipeline for a document that previously failed
 * processing, calling POST /api/documents/<id>/reprocess and reloading
 * the page on success to reflect the updated status.
 *
 * @param {number} documentId - The Document.id to reprocess.
 */
async function reprocessDocument(documentId) {
    showToast("Reprocessing document, this may take a moment...", "info");

    const response = await apiRequest(`/api/documents/${documentId}/reprocess`, { method: "POST" });

    if (response.success) {
        showToast(response.message, "success");
        setTimeout(() => location.reload(), 1000);
    }
}

/**
 * Fetches the current page's pagination metadata (via a lightweight
 * initial call) to determine whether pagination controls are needed at
 * all, since the My Documents page server-renders only the first page.
 */
async function refreshDocumentsGridPagination() {
    const response = await apiRequest(`/api/documents?page=1&per_page=20`, { suppressErrorToast: true });
    if (!response.success) return;

    renderDocumentsPagination(response.data.pagination);
}

/**
 * Renders pagination buttons and wires them to reload the documents
 * grid via fetch when a different page is selected.
 *
 * @param {Object} pagination - The pagination metadata object returned
 *   by the paginated_response() envelope (page, total_pages, etc.).
 */
function renderDocumentsPagination(pagination) {
    const container = document.getElementById("documents-list-pagination");
    if (!container || pagination.total_pages <= 1) return;

    const buttons = [];
    for (let i = 1; i <= pagination.total_pages; i++) {
        buttons.push(`<button class="btn btn-ghost btn-sm ${i === currentDocumentsListPage ? "active" : ""}" data-page="${i}">${i}</button>`);
    }
    container.innerHTML = buttons.join("");

    container.querySelectorAll("[data-page]").forEach(btn => {
        btn.addEventListener("click", async () => {
            currentDocumentsListPage = parseInt(btn.dataset.page, 10);
            const response = await apiRequest(`/api/documents?page=${currentDocumentsListPage}&per_page=20`);
            if (response.success) {
                renderDocumentsGrid(response.data.items);
                renderDocumentsPagination(response.data.pagination);
            }
        });
    });
}

/**
 * Re-renders the documents grid with a new set of document items,
 * replacing the current DOM contents (used after a pagination change).
 *
 * @param {Array<Object>} documents - Array of serialized Document dicts.
 */
function renderDocumentsGrid(documents) {
    const grid = document.getElementById("documents-grid");
    if (!grid) return;

    const fileIcons = { pdf: "📕", docx: "📘", png: "🖼️", jpg: "🖼️", jpeg: "🖼️" };

    grid.innerHTML = documents.map(doc => `
        <div class="glass-card document-card" data-document-id="${doc.id}">
            <div class="document-card-icon">${fileIcons[doc.file_type] || "📄"}</div>
            <div class="document-card-title">${escapeHtml(doc.title || doc.original_filename)}</div>
            <div class="document-card-meta">
                ${(doc.file_size_bytes / 1048576).toFixed(2)} MB
                &middot; <span class="status-badge status-${doc.processing_status}">${doc.processing_status}</span>
            </div>
            <div class="document-card-actions">
                <a href="/document/${doc.id}" class="btn btn-ghost btn-sm">View</a>
                ${doc.processing_status === "ready" ? `<a href="/chat?document_id=${doc.id}" class="btn btn-ghost btn-sm">Chat</a>` : ""}
                ${doc.processing_status === "failed" ? `<button class="btn btn-ghost btn-sm" onclick="reprocessDocument(${doc.id})">Retry</button>` : ""}
                <button class="btn btn-ghost btn-sm" onclick="deleteDocument(${doc.id})">Delete</button>
            </div>
        </div>
    `).join("");
}