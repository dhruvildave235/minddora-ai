

/**
 * auth.js
 *
 * Client-side logic for the Register and Login pages: live password
 * strength feedback on the Register form. The actual form submissions
 * use standard HTML POST (handled server-side by
 * app/blueprints/auth/routes.py + forms.py), NOT fetch() — this file
 * only enhances the UX on top of that server-rendered flow.
 *
 * (The JSON-based equivalents used by any future SPA-style auth flow
 * live in app/blueprints/api/auth_api.py and would be called via
 * apiRequest() from main.js if/when the UI is upgraded to submit via fetch.)
 */

document.addEventListener("DOMContentLoaded", () => {
    initPasswordStrengthMeter();
});

/**
 * Wires up a live password strength indicator on the Register page's
 * password field (if present on the current page), updating a CSS
 * custom property on #password-strength-meter to reflect strength.
 */
function initPasswordStrengthMeter() {
    const passwordInput = document.getElementById("password");
    const meterElement = document.getElementById("password-strength-meter");

    if (!passwordInput || !meterElement) return;

    passwordInput.addEventListener("input", () => {
        const { percent, color } = calculatePasswordStrength(passwordInput.value);
        meterElement.style.setProperty("--strength-percent", `${percent}%`);
        meterElement.style.setProperty("--strength-color", color);
    });
}

/**
 * Calculates an approximate password strength score based on the same
 * rules enforced server-side (app/utils/validators.py's
 * password_strength_errors), used purely for immediate visual feedback
 * — the server remains the source of truth for actual validation.
 *
 * @param {string} password - The current password field value.
 * @returns {{percent: number, color: string}} Strength meter fill
 *   percentage and color.
 */
function calculatePasswordStrength(password) {
    let score = 0;

    if (password.length >= 8) score += 20;
    if (password.length >= 12) score += 10;
    if (/[a-z]/.test(password)) score += 15;
    if (/[A-Z]/.test(password)) score += 15;
    if (/\d/.test(password)) score += 15;
    if (/[!@#$%^&*(),.?":{}|<>]/.test(password)) score += 25;

    const percent = Math.min(score, 100);

    let color = "#ef4444"; // red — weak
    if (percent >= 40) color = "#f59e0b"; // amber — fair
    if (percent >= 70) color = "#22d3ee"; // cyan — good
    if (percent >= 90) color = "#22c55e"; // green — strong

    return { percent, color };
}


// ---------------------------------------------------------------------------
// Password Show/Hide Toggle
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".password-toggle-btn").forEach(button => {
        button.addEventListener("click", () => {
            const targetInput = document.getElementById(button.dataset.target);
            if (!targetInput) return;

            const isHidden = targetInput.type === "password";
            targetInput.type = isHidden ? "text" : "password";
            button.textContent = isHidden ? "🙈" : "👁";
            button.classList.toggle("active", isHidden);
            button.setAttribute("aria-label", isHidden ? "Hide password" : "Show password");
        });
    });
});