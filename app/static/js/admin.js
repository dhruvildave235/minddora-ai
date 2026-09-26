// /**
//  * admin.js
//  *
//  * Client-side logic for the Admin Panel pages: User Management, Document
//  * Management, Feedback Management, System Logs, and System Analytics.
//  * Populates data tables and charts by calling the JSON endpoints in
//  * app/blueprints/api/admin_api.py via the shared apiRequest() wrapper
//  * from main.js, and wires up admin actions (suspend/reactivate/delete
//  * user, delete document, respond to feedback).
//  */

// document.addEventListener("DOMContentLoaded", () => {
//     initMobileSidebarToggle();

//     if (document.getElementById("users-table-body")) initUserManagementPage();
//     if (document.getElementById("documents-table-body")) initDocumentManagementPage();
//     if (document.getElementById("feedback-table-body")) initFeedbackManagementPage();
//     if (document.getElementById("logs-table-body")) initSystemLogsPage();
//     if (document.getElementById("signups-chart")) initDashboardCharts();
//     if (document.getElementById("system-signups-chart")) initSystemAnalyticsCharts();

//     initAutoRefresh();
// });

// /**
//  * Automatically re-fetches and re-renders the current admin page's data
//  * every 10 seconds, so status changes (user online/offline, document
//  * processing status, new feedback) appear without a manual page reload.
//  * Only polls pages that actually have live-changing data; static pages
//  * (analytics charts) are left as manual-refresh since they're less
//  * time-sensitive and re-rendering charts constantly is wasteful.
//  */
// // function initAutoRefresh() {
// //     const REFRESH_INTERVAL_MS = 10000;
// //     // const REFRESH_INTERVAL_MS = 30000;

// //     setInterval(() => {
// //         if (document.getElementById("users-table-body")) loadUsers();
// //         if (document.getElementById("documents-table-body")) loadDocuments();
// //         if (document.getElementById("feedback-table-body")) loadFeedback();
// //         if (document.getElementById("logs-table-body")) loadLogs();
// //     }, REFRESH_INTERVAL_MS);
// // }

// function initAutoRefresh() {
//     const REFRESH_INTERVAL_MS = 10000;
//      // const REFRESH_INTERVAL_MS = 30000;

//     setInterval(() => {
//         if (document.hidden) return; // Skip polling while this tab isn't active

//         if (document.getElementById("users-table-body")) loadUsers();
//         if (document.getElementById("documents-table-body")) loadDocuments();
//         if (document.getElementById("feedback-table-body")) loadFeedback();
//         if (document.getElementById("logs-table-body")) loadLogs();
//     }, REFRESH_INTERVAL_MS);
// }

// document.addEventListener("DOMContentLoaded", () => {
//     initMobileSidebarToggle();

//     if (document.getElementById("users-table-body")) initUserManagementPage();
//     if (document.getElementById("documents-table-body")) initDocumentManagementPage();
//     if (document.getElementById("feedback-table-body")) initFeedbackManagementPage();
//     if (document.getElementById("logs-table-body")) initSystemLogsPage();
//     if (document.getElementById("signups-chart")) initDashboardCharts();
//     if (document.getElementById("system-signups-chart")) initSystemAnalyticsCharts();
// });

// // ---------------------------------------------------------------------------
// // Mobile Sidebar Toggle
// // ---------------------------------------------------------------------------
// function initMobileSidebarToggle() {
//     const toggleButton = document.querySelector("[data-nav-toggle]");
//     const sidebar = document.getElementById("admin-sidebar");
//     if (!toggleButton || !sidebar) return;

//     toggleButton.addEventListener("click", () => {
//         sidebar.classList.toggle("mobile-open");
//     });
// }

// // ---------------------------------------------------------------------------
// // User Management Page
// // ---------------------------------------------------------------------------
// let currentUserPage = 1;

// function initUserManagementPage() {
//     loadUsers();

//     const searchInput = document.getElementById("user-search-input");
//     let debounceTimer;
//     searchInput.addEventListener("input", () => {
//         clearTimeout(debounceTimer);
//         debounceTimer = setTimeout(() => {
//             currentUserPage = 1;
//             loadUsers();
//         }, 400);
//     });
// }

// async function loadUsers() {
//     const searchTerm = document.getElementById("user-search-input").value.trim();
//     const params = new URLSearchParams({ page: currentUserPage, per_page: 20, search: searchTerm });

//     const response = await apiRequest(`/api/admin/users?${params.toString()}`);
//     if (!response.success) return;

//     const tbody = document.getElementById("users-table-body");
//     tbody.innerHTML = response.data.items.map(user => `
//         <tr>
//             <td>${escapeHtml(user.full_name)}</td>
//             <td>${escapeHtml(user.email)}</td>
//            <td>
//                 <span class="status-badge ${user.is_active ? "status-active" : "status-suspended"}">${user.is_active ? "Active" : "Suspended"}</span>
//                 <span class="status-badge ${user.is_online ? "status-active" : "status-suspended"}" style="margin-left: 4px;">${user.is_online ? "🟢 Online" : "⚪ Offline"}</span>
//             </td>
//              <td>${(user.storage_used_bytes / 1048576).toFixed(1)} MB</td>
//             <td>${new Date(user.created_at).toLocaleDateString()}</td>
//             <td>
//                 <button class="btn btn-ghost btn-sm" onclick="toggleUserStatus(${user.id}, ${user.is_active})">
//                     ${user.is_active ? "Suspend" : "Reactivate"}
//                 </button>
//                 <button class="btn btn-ghost btn-sm" onclick="deleteUser(${user.id})">Delete</button>
//             </td>
//         </tr>
//     `).join("");

//     renderPagination("users-pagination", response.data.pagination, (page) => {
//         currentUserPage = page;
//         loadUsers();
//     });
// }

// async function toggleUserStatus(userId, isCurrentlyActive) {
//     const endpoint = isCurrentlyActive ? `/api/admin/users/${userId}/suspend` : `/api/admin/users/${userId}/reactivate`;
//     const response = await apiRequest(endpoint, { method: "POST" });
//     if (response.success) {
//         showToast(response.message, "success");
//         loadUsers();
//     }
// }

// async function deleteUser(userId) {
//     if (!confirm("Permanently delete this user account and all their data? This cannot be undone.")) return;

//     const response = await apiRequest(`/api/admin/users/${userId}`, { method: "DELETE" });
//     if (response.success) {
//         showToast(response.message, "success");
//         loadUsers();
//     }
// }

// // ---------------------------------------------------------------------------
// // Document Management Page
// // ---------------------------------------------------------------------------
// let currentDocumentPage = 1;

// function initDocumentManagementPage() {
//     loadDocuments();
//     document.getElementById("document-status-filter").addEventListener("change", () => {
//         currentDocumentPage = 1;
//         loadDocuments();
//     });
// }

// async function loadDocuments() {
//     const statusFilter = document.getElementById("document-status-filter").value;
//     const params = new URLSearchParams({ page: currentDocumentPage, per_page: 20 });
//     if (statusFilter) params.set("status", statusFilter);

//     const response = await apiRequest(`/api/admin/documents?${params.toString()}`);
//     if (!response.success) return;

//     const tbody = document.getElementById("documents-table-body");
//     // tbody.innerHTML = response.data.items.map(doc => `
//     //     <tr>
//     //         <td>${escapeHtml(doc.original_filename)}</td>
//     //         <td>${doc.user_id}</td>
//     //         <td>${doc.file_type.toUpperCase()}</td>
//     tbody.innerHTML = response.data.items.map(doc => `
//         <tr>
//             <td>${escapeHtml(doc.original_filename)}</td>
//             <td>${escapeHtml(doc.owner_name)}<br><span style="font-size: 0.75rem; color: var(--color-text-muted);">${escapeHtml(doc.owner_email)}</span></td>
//             <td>${doc.file_type.toUpperCase()}</td>
//             <td>${(doc.file_size_bytes / 1048576).toFixed(2)} MB</td>
//             <td><span class="status-badge status-${doc.processing_status}">${doc.processing_status}</span></td>
//             <td>${new Date(doc.uploaded_at).toLocaleDateString()}</td>
//             <td><button class="btn btn-ghost btn-sm" onclick="deleteDocumentAsAdmin(${doc.id})">Delete</button></td>
//         </tr>
//     `).join("");

//     renderPagination("documents-pagination", response.data.pagination, (page) => {
//         currentDocumentPage = page;
//         loadDocuments();
//     });
// }

// async function deleteDocumentAsAdmin(documentId) {
//     if (!confirm("Delete this document? This action cannot be undone.")) return;

//     const response = await apiRequest(`/api/admin/documents/${documentId}`, { method: "DELETE" });
//     if (response.success) {
//         showToast(response.message, "success");
//         loadDocuments();
//     }
// }

// // ---------------------------------------------------------------------------
// // Feedback Management Page
// // ---------------------------------------------------------------------------
// let currentFeedbackPage = 1;
// let activeFeedbackId = null;

// function initFeedbackManagementPage() {
//     loadFeedback();
//     document.getElementById("feedback-status-filter").addEventListener("change", () => { currentFeedbackPage = 1; loadFeedback(); });
//     document.getElementById("feedback-category-filter").addEventListener("change", () => { currentFeedbackPage = 1; loadFeedback(); });
//     document.getElementById("feedback-modal-cancel").addEventListener("click", closeFeedbackModal);
//     document.getElementById("feedback-modal-submit").addEventListener("click", submitFeedbackResponse);
// }

// async function loadFeedback() {
//     const status = document.getElementById("feedback-status-filter").value;
//     const category = document.getElementById("feedback-category-filter").value;
//     const params = new URLSearchParams({ page: currentFeedbackPage, per_page: 20 });
//     if (status) params.set("status", status);
//     if (category) params.set("category", category);

//     const response = await apiRequest(`/api/admin/feedback?${params.toString()}`);
//     if (!response.success) return;

//     const tbody = document.getElementById("feedback-table-body");
//     tbody.innerHTML = response.data.items.map(fb => `
//         <tr>
//             <td>${escapeHtml(fb.submitter_name)}<br><span style="font-size:0.75rem;color:var(--color-text-muted);">${escapeHtml(fb.submitter_email)}</span></td>
//             <td>${escapeHtml(fb.subject)}</td>
//             <td>${fb.category}</td>
//             <td><span class="status-badge status-${fb.status}">${fb.status}</span></td>
//             <td>${new Date(fb.created_at).toLocaleDateString()}</td>
//             <td><button class="btn btn-ghost btn-sm" onclick="openFeedbackModal(${fb.id}, '${escapeHtml(fb.subject)}', '${escapeHtml(fb.message)}')">Respond</button></td>
//         </tr>
//     `).join("");
//     // tbody.innerHTML = response.data.items.map(fb => `
//     //     <tr>
//     //         <td>${escapeHtml(fb.subject)}</td>
//     //         <td>${fb.category}</td>
//     //         <td><span class="status-badge status-${fb.status}">${fb.status}</span></td>
//     //         <td>${new Date(fb.created_at).toLocaleDateString()}</td>
//     //         <td><button class="btn btn-ghost btn-sm" onclick="openFeedbackModal(${fb.id}, '${escapeHtml(fb.subject)}', '${escapeHtml(fb.message)}')">Respond</button></td>
//     //     </tr>
//     // `).join("");

//     renderPagination("feedback-pagination", response.data.pagination, (page) => {
//         currentFeedbackPage = page;
//         loadFeedback();
//     });
// }

// function openFeedbackModal(feedbackId, subject, message) {
//     activeFeedbackId = feedbackId;
//     document.getElementById("feedback-modal-subject").textContent = subject;
//     document.getElementById("feedback-modal-message").textContent = message;
//     document.getElementById("feedback-modal").classList.remove("hidden");
// }

// function closeFeedbackModal() {
//     document.getElementById("feedback-modal").classList.add("hidden");
//     activeFeedbackId = null;
// }

// async function submitFeedbackResponse() {
//     const responseText = document.getElementById("feedback-response-input").value.trim();
//     const status = document.getElementById("feedback-status-select").value;

//     const response = await apiRequest(`/api/admin/feedback/${activeFeedbackId}/respond`, {
//         method: "POST",
//         body: { response: responseText, status },
//     });

//     if (response.success) {
//         showToast(response.message, "success");
//         closeFeedbackModal();
//         loadFeedback();
//     }
// }

// // ---------------------------------------------------------------------------
// // System Logs Page
// // ---------------------------------------------------------------------------
// let currentLogPage = 1;

// function initSystemLogsPage() {
//     loadLogs();
//     document.getElementById("log-level-filter").addEventListener("change", () => { currentLogPage = 1; loadLogs(); });
//     document.getElementById("log-category-filter").addEventListener("change", () => { currentLogPage = 1; loadLogs(); });
// }

// async function loadLogs() {
//     const level = document.getElementById("log-level-filter").value;
//     const category = document.getElementById("log-category-filter").value;
//     const params = new URLSearchParams({ page: currentLogPage, per_page: 50 });
//     if (level) params.set("level", level);
//     if (category) params.set("category", category);

//     const response = await apiRequest(`/api/admin/logs?${params.toString()}`);
//     if (!response.success) return;

//     const tbody = document.getElementById("logs-table-body");
//     tbody.innerHTML = response.data.items.map(log => `
//         <tr>
//             <td><span class="status-badge status-${log.level === "ERROR" || log.level === "CRITICAL" ? "failed" : "active"}">${log.level}</span></td>
//             <td>${log.category}</td>
//             <td>${escapeHtml(log.message)}</td>
//             <td>${log.ip_address || "N/A"}</td>
//             <td>${new Date(log.created_at).toLocaleString()}</td>
//         </tr>
//     `).join("");

//     renderPagination("logs-pagination", response.data.pagination, (page) => {
//         currentLogPage = page;
//         loadLogs();
//     });
// }

// // ---------------------------------------------------------------------------
// // Charts (Dashboard + System Analytics)
// // ---------------------------------------------------------------------------
// function initDashboardCharts() {
//     renderLineChart("signups-chart");
//     renderLineChart("questions-chart");
// }

// function initSystemAnalyticsCharts() {
//     renderLineChart("system-signups-chart");
//     renderLineChart("system-questions-chart");

//     document.getElementById("analytics-days-filter").addEventListener("change", async (e) => {
//         const days = e.target.value;
//         const response = await apiRequest(`/api/admin/analytics?days=${days}`);
//         if (response.success) {
//             location.reload(); // Simplicity for MVP; a future iteration can update charts in-place
//         }
//     });
// }

// function renderLineChart(elementId) {
//     const container = document.getElementById(elementId);
//     if (!container) return;

//     const chartData = JSON.parse(container.dataset.chartData || "[]");
//     const canvas = document.createElement("canvas");
//     container.appendChild(canvas);

//     new Chart(canvas, {
//         type: "line",
//         data: {
//             labels: chartData.map(point => point.date),
//             datasets: [{
//                 data: chartData.map(point => point.count),
//                 borderColor: "#22d3ee",
//                 backgroundColor: "rgba(34, 211, 238, 0.1)",
//                 fill: true,
//                 tension: 0.35,
//             }],
//         },
//         options: {
//             plugins: { legend: { display: false } },
//             scales: {
//                 x: { ticks: { color: "#94a3b8" }, grid: { color: "rgba(255,255,255,0.05)" } },
//                 y: { ticks: { color: "#94a3b8" }, grid: { color: "rgba(255,255,255,0.05)" } },
//             },
//         },
//     });
// }

// // ---------------------------------------------------------------------------
// // Shared Pagination Renderer
// // ---------------------------------------------------------------------------
// function renderPagination(containerId, pagination, onPageClick) {
//     const container = document.getElementById(containerId);
//     if (!container) return;

//     const buttons = [];
//     for (let i = 1; i <= pagination.total_pages; i++) {
//         buttons.push(`<button class="btn btn-ghost btn-sm ${i === pagination.page ? "active" : ""}" data-page="${i}">${i}</button>`);
//     }
//     container.innerHTML = buttons.join("");

//     container.querySelectorAll("[data-page]").forEach(btn => {
//         btn.addEventListener("click", () => onPageClick(parseInt(btn.dataset.page, 10)));
//     });
// }


/**
 * admin.js
 *
 * Client-side logic for the Admin Panel pages: User Management, Document
 * Management, Feedback Management, System Logs, and System Analytics.
 * Populates data tables and charts by calling the JSON endpoints in
 * app/blueprints/api/admin_api.py via the shared apiRequest() wrapper
 * from main.js, and wires up admin actions (suspend/reactivate/delete
 * user, delete document, respond to feedback).
 */

document.addEventListener("DOMContentLoaded", () => {
    initMobileSidebarToggle();

    if (document.getElementById("users-table-body")) initUserManagementPage();
    if (document.getElementById("documents-table-body")) initDocumentManagementPage();
    if (document.getElementById("feedback-table-body")) initFeedbackManagementPage();
    if (document.getElementById("logs-table-body")) initSystemLogsPage();
    if (document.getElementById("signups-chart")) initDashboardCharts();
    if (document.getElementById("system-signups-chart")) initSystemAnalyticsCharts();

    initAutoRefresh();
});

/**
 * Automatically re-fetches and re-renders the current admin page's data
 * every 30 seconds, so status changes (user online/offline, document
 * processing status, new feedback) appear without a manual page reload.
 * Skips polling entirely while the browser tab isn't visible, to avoid
 * wasted requests and rate-limit consumption.
 */
function initAutoRefresh() {
    const REFRESH_INTERVAL_MS = 30000;

    setInterval(() => {
        if (document.hidden) return;

        if (document.getElementById("users-table-body")) loadUsers();
        if (document.getElementById("documents-table-body")) loadDocuments();
        if (document.getElementById("feedback-table-body")) loadFeedback();
        if (document.getElementById("logs-table-body")) loadLogs();
    }, REFRESH_INTERVAL_MS);
}

// ---------------------------------------------------------------------------
// Mobile Sidebar Toggle
// ---------------------------------------------------------------------------
function initMobileSidebarToggle() {
    const toggleButton = document.querySelector("[data-nav-toggle]");
    const sidebar = document.getElementById("admin-sidebar");
    if (!toggleButton || !sidebar) return;

    toggleButton.addEventListener("click", () => {
        sidebar.classList.toggle("mobile-open");
    });
}

// ---------------------------------------------------------------------------
// User Management Page
// ---------------------------------------------------------------------------
let currentUserPage = 1;

function initUserManagementPage() {
    loadUsers();

    const searchInput = document.getElementById("user-search-input");
    let debounceTimer;
    searchInput.addEventListener("input", () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            currentUserPage = 1;
            loadUsers();
        }, 400);
    });
}

async function loadUsers() {
    const searchTerm = document.getElementById("user-search-input").value.trim();
    const params = new URLSearchParams({ page: currentUserPage, per_page: 20, search: searchTerm });

    const response = await apiRequest(`/api/admin/users?${params.toString()}`);
    if (!response.success) return;

    const tbody = document.getElementById("users-table-body");
    tbody.innerHTML = response.data.items.map(user => `
        <tr>
            <td>${escapeHtml(user.full_name)}</td>
            <td>${escapeHtml(user.email)}</td>
            <td>
                <span class="status-badge ${user.is_active ? "status-active" : "status-suspended"}">${user.is_active ? "Active" : "Suspended"}</span>
                <span class="status-badge ${user.is_online ? "status-active" : "status-suspended"}" style="margin-left: 4px;">${user.is_online ? "🟢 Online" : "⚪ Offline"}</span>
            </td>
            <td>${(user.storage_used_bytes / 1048576).toFixed(1)} MB</td>
            <td>${new Date(user.created_at).toLocaleDateString()}</td>
            <td>
                <button class="btn btn-ghost btn-sm" onclick="toggleUserStatus(${user.id}, ${user.is_active})">
                    ${user.is_active ? "Suspend" : "Reactivate"}
                </button>
                <button class="btn btn-ghost btn-sm" onclick="deleteUser(${user.id})">Delete</button>
            </td>
        </tr>
    `).join("");

    renderPagination("users-pagination", response.data.pagination, (page) => {
        currentUserPage = page;
        loadUsers();
    });
}

async function toggleUserStatus(userId, isCurrentlyActive) {
    const endpoint = isCurrentlyActive ? `/api/admin/users/${userId}/suspend` : `/api/admin/users/${userId}/reactivate`;
    const response = await apiRequest(endpoint, { method: "POST" });
    if (response.success) {
        showToast(response.message, "success");
        loadUsers();
    }
}

async function deleteUser(userId) {
    if (!confirm("Permanently delete this user account and all their data? This cannot be undone.")) return;

    const response = await apiRequest(`/api/admin/users/${userId}`, { method: "DELETE" });
    if (response.success) {
        showToast(response.message, "success");
        loadUsers();
    }
}

// ---------------------------------------------------------------------------
// Document Management Page
// ---------------------------------------------------------------------------
let currentDocumentPage = 1;

function initDocumentManagementPage() {
    loadDocuments();
    document.getElementById("document-status-filter").addEventListener("change", () => {
        currentDocumentPage = 1;
        loadDocuments();
    });
}

async function loadDocuments() {
    const statusFilter = document.getElementById("document-status-filter").value;
    const params = new URLSearchParams({ page: currentDocumentPage, per_page: 20 });
    if (statusFilter) params.set("status", statusFilter);

    const response = await apiRequest(`/api/admin/documents?${params.toString()}`);
    if (!response.success) return;

    const tbody = document.getElementById("documents-table-body");
    tbody.innerHTML = response.data.items.map(doc => `
        <tr>
            <td>${escapeHtml(doc.original_filename)}</td>
            <td>${escapeHtml(doc.owner_name)}<br><span style="font-size: 0.75rem; color: var(--color-text-muted);">${escapeHtml(doc.owner_email)}</span></td>
            <td>${doc.file_type.toUpperCase()}</td>
            <td>${(doc.file_size_bytes / 1048576).toFixed(2)} MB</td>
            <td><span class="status-badge status-${doc.processing_status}">${doc.processing_status}</span></td>
            <td>${new Date(doc.uploaded_at).toLocaleDateString()}</td>
            <td><button class="btn btn-ghost btn-sm" onclick="deleteDocumentAsAdmin(${doc.id})">Delete</button></td>
        </tr>
    `).join("");

    renderPagination("documents-pagination", response.data.pagination, (page) => {
        currentDocumentPage = page;
        loadDocuments();
    });
}

async function deleteDocumentAsAdmin(documentId) {
    if (!confirm("Delete this document? This action cannot be undone.")) return;

    const response = await apiRequest(`/api/admin/documents/${documentId}`, { method: "DELETE" });
    if (response.success) {
        showToast(response.message, "success");
        loadDocuments();
    }
}

// ---------------------------------------------------------------------------
// Feedback Management Page
// ---------------------------------------------------------------------------
let currentFeedbackPage = 1;
let activeFeedbackId = null;

function initFeedbackManagementPage() {
    loadFeedback();
    document.getElementById("feedback-status-filter").addEventListener("change", () => { currentFeedbackPage = 1; loadFeedback(); });
    document.getElementById("feedback-category-filter").addEventListener("change", () => { currentFeedbackPage = 1; loadFeedback(); });
    document.getElementById("feedback-modal-cancel").addEventListener("click", closeFeedbackModal);
    document.getElementById("feedback-modal-submit").addEventListener("click", submitFeedbackResponse);
}

async function loadFeedback() {
    const status = document.getElementById("feedback-status-filter").value;
    const category = document.getElementById("feedback-category-filter").value;
    const params = new URLSearchParams({ page: currentFeedbackPage, per_page: 20 });
    if (status) params.set("status", status);
    if (category) params.set("category", category);

    const response = await apiRequest(`/api/admin/feedback?${params.toString()}`);
    if (!response.success) return;

    const tbody = document.getElementById("feedback-table-body");
    tbody.innerHTML = response.data.items.map(fb => `
        <tr>
            <td>${escapeHtml(fb.submitter_name)}<br><span style="font-size:0.75rem;color:var(--color-text-muted);">${escapeHtml(fb.submitter_email)}</span></td>
            <td>${escapeHtml(fb.subject)}</td>
            <td>${fb.category}</td>
            <td><span class="status-badge status-${fb.status}">${fb.status}</span></td>
            <td>${new Date(fb.created_at).toLocaleDateString()}</td>
            <td><button class="btn btn-ghost btn-sm" onclick="openFeedbackModal(${fb.id}, '${escapeHtml(fb.subject)}', '${escapeHtml(fb.message)}')">Respond</button></td>
        </tr>
    `).join("");

    renderPagination("feedback-pagination", response.data.pagination, (page) => {
        currentFeedbackPage = page;
        loadFeedback();
    });
}

function openFeedbackModal(feedbackId, subject, message) {
    activeFeedbackId = feedbackId;
    document.getElementById("feedback-modal-subject").textContent = subject;
    document.getElementById("feedback-modal-message").textContent = message;
    document.getElementById("feedback-modal").classList.remove("hidden");
}

function closeFeedbackModal() {
    document.getElementById("feedback-modal").classList.add("hidden");
    activeFeedbackId = null;
}

async function submitFeedbackResponse() {
    const responseText = document.getElementById("feedback-response-input").value.trim();
    const status = document.getElementById("feedback-status-select").value;

    const response = await apiRequest(`/api/admin/feedback/${activeFeedbackId}/respond`, {
        method: "POST",
        body: { response: responseText, status },
    });

    if (response.success) {
        showToast(response.message, "success");
        closeFeedbackModal();
        loadFeedback();
    }
}

// ---------------------------------------------------------------------------
// System Logs Page
// ---------------------------------------------------------------------------
let currentLogPage = 1;

function initSystemLogsPage() {
    loadLogs();
    document.getElementById("log-level-filter").addEventListener("change", () => { currentLogPage = 1; loadLogs(); });
    document.getElementById("log-category-filter").addEventListener("change", () => { currentLogPage = 1; loadLogs(); });
}

async function loadLogs() {
    const level = document.getElementById("log-level-filter").value;
    const category = document.getElementById("log-category-filter").value;
    const params = new URLSearchParams({ page: currentLogPage, per_page: 50 });
    if (level) params.set("level", level);
    if (category) params.set("category", category);

    const response = await apiRequest(`/api/admin/logs?${params.toString()}`);
    if (!response.success) return;

    const tbody = document.getElementById("logs-table-body");
    tbody.innerHTML = response.data.items.map(log => `
        <tr>
            <td><span class="status-badge status-${log.level === "ERROR" || log.level === "CRITICAL" ? "failed" : "active"}">${log.level}</span></td>
            <td>${log.category}</td>
            <td>${escapeHtml(log.message)}</td>
            <td>${log.ip_address || "N/A"}</td>
            <td>${new Date(log.created_at).toLocaleString()}</td>
        </tr>
    `).join("");

    renderPagination("logs-pagination", response.data.pagination, (page) => {
        currentLogPage = page;
        loadLogs();
    });
}

// ---------------------------------------------------------------------------
// Charts (Dashboard + System Analytics)
// ---------------------------------------------------------------------------
function initDashboardCharts() {
    renderLineChart("signups-chart");
    renderLineChart("questions-chart");
}

function initSystemAnalyticsCharts() {
    renderLineChart("system-signups-chart");
    renderLineChart("system-questions-chart");

    // document.getElementById("analytics-days-filter").addEventListener("change", async (e) => {
    //     const days = e.target.value;
    //     const response = await apiRequest(`/api/admin/analytics?days=${days}`);
    //     if (response.success) {
    //         location.reload();
    //     }
    // });

    document.getElementById("analytics-days-filter").addEventListener("change", (e) => {
        const days = e.target.value;
        window.location.href = `/admin/analytics?days=${days}`;
    });
}

function renderLineChart(elementId) {
    const container = document.getElementById(elementId);
    if (!container) return;

    const chartData = JSON.parse(container.dataset.chartData || "[]");
    const canvas = document.createElement("canvas");
    container.appendChild(canvas);

    new Chart(canvas, {
        type: "line",
        data: {
            labels: chartData.map(point => point.date),
            datasets: [{
                data: chartData.map(point => point.count),
                borderColor: "#22d3ee",
                backgroundColor: "rgba(34, 211, 238, 0.1)",
                fill: true,
                tension: 0.35,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { ticks: { color: "#94a3b8" }, grid: { color: "rgba(255,255,255,0.05)" } },
                y: { ticks: { color: "#94a3b8" }, grid: { color: "rgba(255,255,255,0.05)" } },
            },
        },
    });
}

// ---------------------------------------------------------------------------
// Shared Pagination Renderer
// ---------------------------------------------------------------------------
function renderPagination(containerId, pagination, onPageClick) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const buttons = [];
    for (let i = 1; i <= pagination.total_pages; i++) {
        buttons.push(`<button class="btn btn-ghost btn-sm ${i === pagination.page ? "active" : ""}" data-page="${i}">${i}</button>`);
    }
    container.innerHTML = buttons.join("");

    container.querySelectorAll("[data-page]").forEach(btn => {
        btn.addEventListener("click", () => onPageClick(parseInt(btn.dataset.page, 10)));
    });
}