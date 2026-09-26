/**
 * database.js
 *
 * Client-side logic for the Admin Panel's Database browser: password
 * unlock gate, table list with row counts, and a generic data grid
 * that renders any table's columns dynamically, with a delete action
 * per row — all without writing SQL.
 */

let currentTable = null;
let currentPage = 1;

document.addEventListener("DOMContentLoaded", () => {
    const unlockBtn = document.getElementById("db-unlock-btn");
    if (!unlockBtn) return;

    unlockBtn.addEventListener("click", unlockDatabase);
    document.getElementById("db-unlock-password").addEventListener("keydown", (e) => {
        if (e.key === "Enter") unlockDatabase();
    });
    document.getElementById("db-back-btn").addEventListener("click", showTableList);
});

async function unlockDatabase() {
    const password = document.getElementById("db-unlock-password").value;
    if (!password) return;

    const response = await apiRequest("/api/admin/database/unlock", {
        method: "POST",
        body: { password },
        suppressErrorToast: true,
    });

    if (response.success) {
        document.getElementById("db-lock-screen").classList.add("hidden");
        showTableList();
    } else {
        showToast(response.error || "Incorrect password.", "error");
    }
}

async function showTableList() {
    document.getElementById("db-table-view").classList.add("hidden");
    document.getElementById("db-table-list").classList.remove("hidden");

    const response = await apiRequest("/api/admin/database/tables", { suppressErrorToast: true });

    if (!response.success) {
        if (response.error_code === "DB_LOCKED") {
            document.getElementById("db-table-list").classList.add("hidden");
            document.getElementById("db-lock-screen").classList.remove("hidden");
        }
        return;
    }

    const grid = document.getElementById("db-tables-grid");
    grid.innerHTML = response.data.tables.map(t => `
        <div class="glass-card stat-card" style="cursor:pointer;" onclick="openTable('${t.name}')">
            <div class="stat-value">${t.row_count}</div>
            <div class="stat-label">${t.name} · ${t.column_count} columns</div>
        </div>
    `).join("");
}

async function openTable(tableName, page = 1) {
    currentTable = tableName;
    currentPage = page;

    document.getElementById("db-table-list").classList.add("hidden");
    document.getElementById("db-table-view").classList.remove("hidden");
    document.getElementById("db-table-title").textContent = tableName;

    const response = await apiRequest(`/api/admin/database/tables/${tableName}?page=${page}&per_page=20`);
    if (!response.success) return;

    const { columns, items, pagination } = response.data;

    const headRow = document.getElementById("db-table-head");
    headRow.innerHTML = columns.map(c => `<th>${c}</th>`).join("") + "<th>Actions</th>";

    const body = document.getElementById("db-table-body");
    body.innerHTML = items.map(row => `
        <tr>
            ${columns.map(c => `<td>${formatCell(row[c])}</td>`).join("")}
            <td><button class="btn btn-ghost btn-sm" onclick="deleteRow('${tableName}', ${row.id})">Delete</button></td>
        </tr>
    `).join("");

    renderDbPagination(pagination);
}

function formatCell(value) {
    if (value === null || value === undefined) return "<span style='color:var(--color-text-muted)'>—</span>";
    const text = String(value);
    return escapeHtml(text.length > 60 ? text.slice(0, 60) + "…" : text);
}

async function deleteRow(tableName, rowId) {
    if (!confirm(`Delete row ${rowId} from ${tableName}? This cannot be undone.`)) return;

    const response = await apiRequest(`/api/admin/database/tables/${tableName}/${rowId}`, { method: "DELETE" });
    if (response.success) {
        showToast(response.message, "success");
        openTable(tableName, currentPage);
    }
}

function renderDbPagination(pagination) {
    const container = document.getElementById("db-pagination");
    if (pagination.total_pages <= 1) {
        container.innerHTML = "";
        return;
    }

    const buttons = [];
    for (let i = 1; i <= pagination.total_pages; i++) {
        buttons.push(`<button class="btn btn-ghost btn-sm ${i === pagination.page ? "active" : ""}" onclick="openTable('${currentTable}', ${i})">${i}</button>`);
    }
    container.innerHTML = buttons.join("");
}