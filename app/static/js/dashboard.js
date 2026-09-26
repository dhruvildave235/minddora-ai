/**
 * dashboard.js
 *
 * Client-side logic for the Dashboard area: Settings page's change-
 * password form submission, and AI Analytics page's activity chart
 * rendering. Uses the shared apiRequest() wrapper from main.js for the
 * change-password call against POST /api/auth/change-password.
 */

document.addEventListener("DOMContentLoaded", () => {
    initPasswordStrengthMeter();
    initChangePasswordForm();
    initAnalyticsChart();
});

// ---------------------------------------------------------------------------
// Change Password Form (Settings page)
// ---------------------------------------------------------------------------
function initChangePasswordForm() {
    const form = document.getElementById("change-password-form");
    if (!form) return;

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        clearFieldErrors(form);

        const currentPassword = document.getElementById("current_password").value;
        const newPassword = document.getElementById("new_password").value;
        const confirmNewPassword = document.getElementById("confirm_new_password").value;

        const response = await apiRequest("/api/auth/change-password", {
            method: "POST",
            body: {
                current_password: currentPassword,
                new_password: newPassword,
                confirm_password: confirmNewPassword,
            },
            suppressErrorToast: true,
        });

        if (response.success) {
            showToast(response.message, "success");
            form.reset();
            document.getElementById("password-strength-meter").style.setProperty("--strength-percent", "0%");
        } else {
            showToast(response.error, "error");
        }
    });
}

/**
 * Clears any previously displayed field-level error messages within a
 * given form element, used before re-submitting the change-password form.
 *
 * @param {HTMLFormElement} form - The form to clear errors within.
 */
function clearFieldErrors(form) {
    form.querySelectorAll(".field-error-message").forEach(el => {
        el.textContent = "";
        el.classList.add("hidden");
    });
}

// ---------------------------------------------------------------------------
// Password Strength Meter (reused pattern from auth.js, scoped locally
// here since the Settings page loads dashboard.js, not auth.js's
// DOMContentLoaded listener conflicts are avoided by using distinct IDs)
// ---------------------------------------------------------------------------
function initPasswordStrengthMeter() {
    const passwordInput = document.getElementById("new_password");
    const meterElement = document.getElementById("password-strength-meter");
    if (!passwordInput || !meterElement) return;

    passwordInput.addEventListener("input", () => {
        let score = 0;
        const password = passwordInput.value;

        if (password.length >= 8) score += 20;
        if (password.length >= 12) score += 10;
        if (/[a-z]/.test(password)) score += 15;
        if (/[A-Z]/.test(password)) score += 15;
        if (/\d/.test(password)) score += 15;
        if (/[!@#$%^&*(),.?":{}|<>]/.test(password)) score += 25;

        const percent = Math.min(score, 100);
        let color = "#ef4444";
        if (percent >= 40) color = "#f59e0b";
        if (percent >= 70) color = "#22d3ee";
        if (percent >= 90) color = "#22c55e";

        meterElement.style.setProperty("--strength-percent", `${percent}%`);
        meterElement.style.setProperty("--strength-color", color);
    });
}

// ---------------------------------------------------------------------------
// AI Analytics Chart
// ---------------------------------------------------------------------------
function initAnalyticsChart() {
    const container = document.getElementById("activity-chart");
    if (!container || typeof Chart === "undefined") return;

    const chartData = JSON.parse(container.dataset.chartData || "[]");
    const canvas = document.createElement("canvas");
    container.appendChild(canvas);

    new Chart(canvas, {
        type: "bar",
        data: {
            labels: chartData.map(point => point.date),
            datasets: [{
                data: chartData.map(point => point.count),
                backgroundColor: "rgba(168, 85, 247, 0.5)",
                borderRadius: 6,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { ticks: { color: "#94a3b8" }, grid: { display: false } },
                y: { ticks: { color: "#94a3b8" }, grid: { color: "rgba(255,255,255,0.05)" } },
            },
        },
    });

    // new Chart(canvas, {
    //     type: "bar",
    //     data: {
    //         labels: chartData.map(point => point.date),
    //         datasets: [{
    //             data: chartData.map(point => point.count),
    //             backgroundColor: "rgba(168, 85, 247, 0.5)",
    //             borderRadius: 6,
    //         }],
    //     },
    //     options: {
    //         plugins: { legend: { display: false } },
    //         scales: {
    //             x: { ticks: { color: "#94a3b8" }, grid: { display: false } },
    //             y: { ticks: { color: "#94a3b8" }, grid: { color: "rgba(255,255,255,0.05)" } },
    //         },
    //     },
    // });
}


// ---------------------------------------------------------------------------
// Edit Profile Form (Settings page)
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("edit-profile-form");
    if (!form) return;

    form.addEventListener("submit", async (event) => {
        event.preventDefault();

        const response = await apiRequest("/api/auth/update-profile", {
            method: "POST",
            body: {
                full_name: document.getElementById("profile-full-name").value.trim(),
                institution: document.getElementById("profile-institution").value.trim(),
                field_of_study: document.getElementById("profile-field-of-study").value.trim(),
            },
            suppressErrorToast: true,
        });

        if (response.success) {
            showToast(response.message, "success");
        } else {
            showToast(response.error, "error");
        }
    });
});

// ---------------------------------------------------------------------------
// AI Mode Settings (Settings page)
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
    const modeSelect = document.getElementById("settings-ai-mode-select");
    const geminiFields = document.getElementById("settings-gemini-fields");
    const saveBtn = document.getElementById("settings-save-ai-mode-btn");

    if (!modeSelect || !saveBtn) return;

    modeSelect.addEventListener("change", () => {
        geminiFields.classList.toggle("hidden", modeSelect.value !== "gemini");
    });

    saveBtn.addEventListener("click", async () => {
        const aiMode = modeSelect.value;
        const apiKey = document.getElementById("settings-gemini-key").value.trim();
        const modelName = document.getElementById("settings-gemini-model").value.trim();

        if (aiMode === "gemini" && !apiKey && !document.getElementById("settings-gemini-key").placeholder.includes("saved")) {
            showToast("Please enter your Gemini API key.", "error");
            return;
        }

        const response = await apiRequest("/api/auth/update-ai-settings", {
            method: "POST",
            body: { ai_mode: aiMode, gemini_api_key: apiKey, gemini_model_name: modelName },
        });

        if (response.success) {
            showToast("AI mode updated.", "success");
            sessionStorage.setItem("minddora_ai_mode_chosen", aiMode);
            document.getElementById("settings-gemini-key").value = "";
        }
    });
});