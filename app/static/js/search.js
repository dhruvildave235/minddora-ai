/**
 * search.js
 *
 * Client-side logic for the Search Notes page: mode toggle
 * (semantic/keyword/hybrid), filter controls (subject, date range), and
 * calling GET /api/search to render a ranked list of matching chunk
 * excerpts with document/page context.
 */

let currentSearchMode = "hybrid";

document.addEventListener("DOMContentLoaded", () => {
    initSearchModeToggle();
    initSearchSubmit();
});

/**
 * Wires up the search mode toggle buttons (Hybrid / Semantic / Keyword),
 * updating currentSearchMode and the active button's visual state.
 */
function initSearchModeToggle() {
    const buttons = document.querySelectorAll(".search-mode-btn");
    buttons.forEach(button => {
        button.addEventListener("click", () => {
            buttons.forEach(b => b.classList.remove("active"));
            button.classList.add("active");
            currentSearchMode = button.dataset.mode;
        });
    });
}

/**
 * Wires up the search input/button to trigger a search on click or
 * Enter key press, and executes the search against GET /api/search.
 */
function initSearchSubmit() {
    const input = document.getElementById("search-query-input");
    const submitBtn = document.getElementById("search-submit-btn");

    submitBtn.addEventListener("click", performSearch);
    input.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            event.preventDefault();
            performSearch();
        }
    });
}

/**
 * Executes a search request using the current query, mode, and filter
 * values, then renders the results list.
 */
async function performSearch() {
    const query = document.getElementById("search-query-input").value.trim();
    if (!query) {
        showToast("Please enter a search query.", "error");
        return;
    }

    const resultsContainer = document.getElementById("search-results-container");
    resultsContainer.innerHTML = `<div class="skeleton" style="height: 80px; margin-bottom: 12px;"></div>`.repeat(3);

    const params = new URLSearchParams({ q: query, mode: currentSearchMode, top_k: 15 });

    const subject = document.getElementById("search-subject-filter").value;
    const dateFrom = document.getElementById("search-date-from").value;
    const dateTo = document.getElementById("search-date-to").value;

    if (subject) params.set("subject", subject);
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo) params.set("date_to", dateTo);

    const response = await apiRequest(`/api/search?${params.toString()}`);

    if (response.success) {
        renderSearchResults(response.data.results);
    } else {
        resultsContainer.innerHTML = `<p class="empty-state-text">Something went wrong. Please try again.</p>`;
    }
}

/**
 * Renders the search results list, showing each matching chunk's
 * excerpt, source document title, page number, and relevance score.
 *
 * @param {Array<Object>} results - Array of result dicts from search_service.
 */
function renderSearchResults(results) {
    const container = document.getElementById("search-results-container");

    if (results.length === 0) {
        container.innerHTML = `<p class="empty-state-text">No matching results found. Try a different search term or mode.</p>`;
        return;
    }

    container.innerHTML = results.map(result => `
        <div class="glass-card search-result-card">
            <span class="search-result-score">Score: ${(result.score * 100).toFixed(0)}%</span>
            <h4>${escapeHtml(result.document_title || "Untitled Document")}${result.page_number ? ` — Page ${result.page_number}` : ""}</h4>
            <p class="mt-lg">${escapeHtml(result.excerpt)}</p>
            <a href="/document/${result.document_id}" class="auth-link-small">View document →</a>
        </div>
    `).join("");
}