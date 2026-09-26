/**
 * main.js
 *
 * Global JavaScript utilities loaded on EVERY page via base.html:
 *   - Toast notification system (showToast), including auto-rendering
 *     of server-side Flask flash() messages injected into the DOM.
 *   - Mobile navigation menu toggle.
 *   - A small shared `apiRequest()` fetch wrapper used by every other
 *     page-specific JS file (auth.js, upload.js, chat.js, etc.) so every
 *     API call handles the standardized response envelope, CSRF token,
 *     and error toasts consistently in one place.
 */

// ---------------------------------------------------------------------------
// Toast Notification System
// ---------------------------------------------------------------------------
const TOAST_ICONS = {
    success: "✓",
    error: "✕",
    info: "ℹ",
    warning: "⚠",
};

/**
 * Displays a toast notification in the global toast container.
 *
 * @param {string} message - The message text to display.
 * @param {string} category - One of "success", "error", "info", "warning".
 * @param {number} durationMs - How long the toast stays visible before auto-dismissing.
 */
function showToast(message, category = "info", durationMs = 4500) {
    const container = document.getElementById("toast-container");
    if (!container) return;

    const toast = document.createElement("div");
    toast.className = `toast-item toast-${category}`;
    toast.innerHTML = `
        <span class="toast-icon">${TOAST_ICONS[category] || TOAST_ICONS.info}</span>
        <span class="toast-message">${escapeHtml(message)}</span>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transform = "translateX(40px)";
        setTimeout(() => toast.remove(), 300);
    }, durationMs);
}

/**
 * Escapes HTML special characters in a string before inserting it into
 * the DOM via innerHTML, preventing XSS from any dynamic message content
 * (e.g. API error messages that might echo back user input).
 *
 * @param {string} unsafeText - The raw text to escape.
 * @returns {string} HTML-escaped text safe for innerHTML insertion.
 */
function escapeHtml(unsafeText) {
    const div = document.createElement("div");
    div.textContent = unsafeText;
    return div.innerHTML;
}

/**
 * On page load, renders any server-side Flask flash() messages (injected
 * into a hidden #flash-messages element by base.html) as toasts, then
 * removes the element so they don't render twice on client-side navigation.
 */
document.addEventListener("DOMContentLoaded", () => {
    const flashElement = document.getElementById("flash-messages");
    if (flashElement) {
        try {
            const messages = JSON.parse(flashElement.dataset.flashMessages);
            messages.forEach(([category, message]) => {
                const normalizedCategory = category === "error" ? "error" : category;
                showToast(message, normalizedCategory);
            });
        } catch (err) {
            console.error("Failed to parse flash messages:", err);
        }
        flashElement.remove();
    }

    initMobileNavToggle();
});

// ---------------------------------------------------------------------------
// Mobile Navigation Toggle
// ---------------------------------------------------------------------------
/**
 * Wires up the hamburger menu button (if present on the page) to toggle
 * the .mobile-menu-open class on the nav links list, per the responsive
 * nav behavior defined in responsive.css.
 */
// function initMobileNavToggle() {
//     const toggleButton = document.querySelector("[data-nav-toggle]");
//     const navLinks = document.querySelector(".nav-links");

//     if (!toggleButton || !navLinks) return;

//     toggleButton.addEventListener("click", () => {
//         navLinks.classList.toggle("mobile-menu-open");
//     });
// }


function initMobileNavToggle() {
    const toggleButton = document.querySelector("[data-nav-toggle]");
    const collapsible = document.getElementById("nav-collapsible");

    if (!toggleButton || !collapsible) return;

    toggleButton.addEventListener("click", () => {
        collapsible.classList.toggle("mobile-menu-open");
        toggleButton.classList.toggle("open");
    });
}

// ---------------------------------------------------------------------------
// Shared API Request Wrapper
// ---------------------------------------------------------------------------
/**
 * Reads the CSRF token from the meta tag injected into the page head
 * (added per-template where forms/API calls need it), required by
 * Flask-WTF's CSRFProtect for any state-changing request.
 *
 * @returns {string} The CSRF token value, or an empty string if not present.
 */
function getCsrfToken() {
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    return metaTag ? metaTag.getAttribute("content") : "";
}

/**
 * Shared fetch() wrapper used by every page-specific JS module to call
 * Minddora AI's JSON API. Automatically attaches the CSRF token, parses
 * the standardized {success, data, error, error_code} response envelope,
 * and shows an error toast automatically on failure (unless suppressed).
 *
 * @param {string} url - The API endpoint URL (e.g. "/api/chat/message").
 * @param {Object} options - Fetch options.
 * @param {string} [options.method="GET"] - HTTP method.
 * @param {Object} [options.body] - Request body object (auto-JSON-stringified).
 * @param {boolean} [options.suppressErrorToast=false] - If true, skips the automatic error toast.
 * @returns {Promise<Object>} Resolves with the parsed response envelope
 *   (always has a `success` boolean field) or rejects on network failure.
 */
async function apiRequest(url, options = {}) {
    const { method = "GET", body = null, suppressErrorToast = false } = options;

    const fetchOptions = {
        method,
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCsrfToken(),
        },
    };

    if (body !== null) {
        fetchOptions.body = JSON.stringify(body);
    }

    try {
        const response = await fetch(url, fetchOptions);
        const data = await response.json();

        if (!data.success && !suppressErrorToast) {
            showToast(data.error || "Something went wrong. Please try again.", "error");
        }

        return data;
    } catch (networkError) {
        if (!suppressErrorToast) {
            showToast("Network error — please check your connection and try again.", "error");
        }
        return { success: false, error: "Network error", error_code: "NETWORK_ERROR" };
    }
}

// ---------------------------------------------------------------------------
// Feedback Submission Modal (available on every dashboard page)
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
    const openBtn = document.getElementById("open-feedback-modal-btn");
    const modal = document.getElementById("feedback-submit-modal");
    const cancelBtn = document.getElementById("feedback-submit-cancel");
    const sendBtn = document.getElementById("feedback-submit-send");

    if (!openBtn || !modal) return;

    openBtn.addEventListener("click", (e) => {
        e.preventDefault();
        modal.classList.remove("hidden");
    });

    cancelBtn.addEventListener("click", () => {
        modal.classList.add("hidden");
    });

    sendBtn.addEventListener("click", async () => {
        const category = document.getElementById("feedback-category-select").value;
        const subject = document.getElementById("feedback-subject-input").value.trim();
        const message = document.getElementById("feedback-message-input").value.trim();

        if (!subject || !message) {
            showToast("Please fill in both subject and message.", "error");
            return;
        }

        const response = await apiRequest("/api/feedback/submit", {
            method: "POST",
            body: { category, subject, message },
        });

        if (response.success) {
            showToast(response.message, "success");
            modal.classList.add("hidden");
            document.getElementById("feedback-subject-input").value = "";
            document.getElementById("feedback-message-input").value = "";
        }
    });
});