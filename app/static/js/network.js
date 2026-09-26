/**
 * network.js
 *
 * Renders a live, animated node graph of Minddora AI's actual
 * architecture on a canvas: Browser -> Flask Gateway -> (Auth /
 * Document / Retrieval services) -> (PostgreSQL / Vector Store).
 * Polls /api/admin/live-activity every 2 seconds for new SystemLog
 * events and fires a glowing pulse traveling along the real path that
 * event took, color-coded by category, matching the app's neon theme.
 */

const COLORS = {
    auth: "#3b82f6",
    upload: "#22d3ee",
    chat: "#a855f7",
    rag_pipeline: "#a855f7",
    admin_action: "#f59e0b",
    security: "#ef4444",
    default: "#22d3ee",
};

// -----------------------------------------------------------------
// Node layout, mirroring the real system architecture.
// -----------------------------------------------------------------
const NODES = {
    browser:  { label: "Browser",       x: 0.50, y: 0.08, color: "#94a3b8" },
    gateway:  { label: "Flask Gateway", x: 0.50, y: 0.24, color: "#3b82f6" },
    auth:     { label: "Auth Service",  x: 0.18, y: 0.44, color: "#3b82f6" },
    document: { label: "Document Svc",  x: 0.50, y: 0.44, color: "#22d3ee" },
    retrieval:{ label: "Retrieval Eng", x: 0.82, y: 0.44, color: "#a855f7" },
    postgres: { label: "PostgreSQL",    x: 0.32, y: 0.80, color: "#3b82f6" },
    vectors:  { label: "Vector Store",  x: 0.68, y: 0.80, color: "#a855f7" },
};

const EDGES = [
    ["browser", "gateway"],
    ["gateway", "auth"],
    ["gateway", "document"],
    ["gateway", "retrieval"],
    ["auth", "postgres"],
    ["document", "postgres"],
    ["document", "vectors"],
    ["retrieval", "postgres"],
    ["retrieval", "vectors"],
];

// Maps a SystemLog category to the sequence of nodes an event of that
// type actually travels through in the real request lifecycle.
const CATEGORY_PATHS = {
    auth: ["browser", "gateway", "auth", "postgres"],
    upload: ["browser", "gateway", "document", "postgres"],
    rag_pipeline: ["browser", "gateway", "retrieval", "vectors"],
    chat: ["browser", "gateway", "retrieval", "postgres"],
    admin_action: ["browser", "gateway", "auth", "postgres"],
    security: ["browser", "gateway", "auth"],
    system: ["browser", "gateway"],
};

let canvas, ctx, width, height;
let pulses = [];
// let sinceId = 0;
let sinceId = null; // will be set to "latest so far" on first poll, so history never replays
let nodeGlow = {};

// document.addEventListener("DOMContentLoaded", () => {
//     canvas = document.getElementById("network-canvas");
//     if (!canvas) return;

//     ctx = canvas.getContext("2d");
//     resizeCanvas();
//     window.addEventListener("resize", resizeCanvas);

//     Object.keys(NODES).forEach(key => nodeGlow[key] = 0);

//     requestAnimationFrame(drawFrame);
//     pollActivity();
//     setInterval(pollActivity, 2000);
// });

document.addEventListener("DOMContentLoaded", () => {
    canvas = document.getElementById("network-canvas");
    if (!canvas) return;

    ctx = canvas.getContext("2d");
    resizeCanvas();
    window.addEventListener("resize", resizeCanvas);

    Object.keys(NODES).forEach(key => nodeGlow[key] = 0);

    requestAnimationFrame(drawFrame);
    pollActivity();
    setInterval(pollActivity, 2000);

    pollStatusBoard();
    setInterval(pollStatusBoard, 5000);
});

function appendTerminalLine(event) {
    const log = document.getElementById("terminal-log");
    if (!log) return;

    const now = new Date();
    const dateStr = now.toLocaleDateString(undefined, { day: "2-digit", month: "short" });
    const timeStr = now.toLocaleTimeString();
    const line = document.createElement("div");
    line.className = "terminal-line";
    line.innerHTML = `<span class="t-time">[${dateStr} ${timeStr}]</span> <span class="t-${event.category}">[${event.category}]</span> ${escapeHtml(event.message)}`;
    log.appendChild(line);

    while (log.children.length > 60) {
        log.removeChild(log.firstChild);
    }
    log.scrollTop = log.scrollHeight;
}

async function pollStatusBoard() {
    const response = await apiRequest("/api/admin/live-status-board", { suppressErrorToast: true });
    if (!response.success) return;

    const board = document.getElementById("status-board");
    if (!board) return;

    board.innerHTML = response.data.students.map(s => `
        <div class="status-card">
            <div class="status-card-header">
                <span class="status-card-name">${escapeHtml(s.full_name)}</span>
                <span>
                    <span class="status-dot" style="background:${s.is_online ? "#22c55e" : "#64748b"}"></span>
                    ${s.is_online ? "online" : "offline"}
                </span>
            </div>
            <div class="status-card-action">${escapeHtml(s.last_action)}</div>
        </div>
    `).join("");
}

function resizeCanvas() {
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * window.devicePixelRatio;
    canvas.height = rect.height * window.devicePixelRatio;
    ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
    width = rect.width;
    height = rect.height;
}

function nodePos(key) {
    const n = NODES[key];
    return { x: n.x * width, y: n.y * height };
}

// -----------------------------------------------------------------
// Polling real activity from the backend
// -----------------------------------------------------------------
async function pollActivity() {
    try {
        const isFirstPoll = sinceId === null;
        const response = await apiRequest(`/api/admin/live-activity?since_id=${sinceId ?? 0}`, { suppressErrorToast: true });
        if (!response.success) return;

        sinceId = response.data.latest_id;

        // On the very first poll after loading the page, just silently
        // catch up to "now" without replaying every historical event —
        // only events from THIS point forward get animated/logged.
        if (isFirstPoll) return;

        response.data.events.forEach(event => {
            const path = CATEGORY_PATHS[event.category] || CATEGORY_PATHS.system;
            const color = COLORS[event.category] || COLORS.default;
            spawnPulse(path, color);
            appendTerminalLine(event);
        });

        // response.data.events.forEach(event => {
        //     const path = CATEGORY_PATHS[event.category] || CATEGORY_PATHS.system;
        //     const color = COLORS[event.category] || COLORS.default;
        //     spawnPulse(path, color);
        // });

        const statusEl = document.getElementById("network-status");
        if (response.data.events.length > 0 && statusEl) {
            statusEl.textContent = `🟢 Live — last event: ${response.data.events[response.data.events.length - 1].category}`;
            setTimeout(() => { statusEl.textContent = "🔵 Watching for activity…"; }, 2500);
        }
    } catch (e) {
        // Silent — polling errors shouldn't spam the console every 2s
    }
}

// -----------------------------------------------------------------
// Pulse animation: a bright dot traveling node-to-node along a path
// -----------------------------------------------------------------
function spawnPulse(path, color) {
    for (let i = 0; i < path.length - 1; i++) {
        pulses.push({
            from: path[i],
            to: path[i + 1],
            color,
            progress: -i * 0.35,
            speed: 0.02,
        });
    }
}

function drawFrame() {
    ctx.clearRect(0, 0, width, height);

    // Static edges
    EDGES.forEach(([a, b]) => {
        const p1 = nodePos(a);
        const p2 = nodePos(b);
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.strokeStyle = "rgba(148, 163, 184, 0.15)";
        ctx.lineWidth = 1.5;
        ctx.stroke();
    });

    // Decay node glow
    Object.keys(nodeGlow).forEach(k => nodeGlow[k] = Math.max(0, nodeGlow[k] - 0.02));

    // Pulses
    pulses = pulses.filter(pulse => pulse.progress < 1.15);
    pulses.forEach(pulse => {
        pulse.progress += pulse.speed;
        if (pulse.progress < 0 || pulse.progress > 1) return;

        const p1 = nodePos(pulse.from);
        const p2 = nodePos(pulse.to);
        const x = p1.x + (p2.x - p1.x) * pulse.progress;
        const y = p1.y + (p2.y - p1.y) * pulse.progress;

        if (pulse.progress > 0.92) {
            nodeGlow[pulse.to] = 1;
        }

        const gradient = ctx.createRadialGradient(x, y, 0, x, y, 8);
        gradient.addColorStop(0, pulse.color);
        gradient.addColorStop(1, "transparent");
        ctx.beginPath();
        ctx.arc(x, y, 8, 0, Math.PI * 2);
        ctx.fillStyle = gradient;
        ctx.fill();

        ctx.beginPath();
        ctx.arc(x, y, 3, 0, Math.PI * 2);
        ctx.fillStyle = pulse.color;
        ctx.fill();
    });

    // Nodes
    Object.entries(NODES).forEach(([key, node]) => {
        const { x, y } = nodePos(key);
        const glow = nodeGlow[key] || 0;

        const radius = 22 + glow * 8;
        const gradient = ctx.createRadialGradient(x, y, 0, x, y, radius * 1.8);
        gradient.addColorStop(0, `rgba(59, 130, 246, ${0.25 + glow * 0.4})`);
        gradient.addColorStop(1, "transparent");
        ctx.beginPath();
        ctx.arc(x, y, radius * 1.8, 0, Math.PI * 2);
        ctx.fillStyle = gradient;
        ctx.fill();

        ctx.beginPath();
        ctx.arc(x, y, 16, 0, Math.PI * 2);
        ctx.fillStyle = "#10121c";
        ctx.fill();
        ctx.lineWidth = 2;
        ctx.strokeStyle = node.color;
        ctx.stroke();

        ctx.font = "600 12px sans-serif";
        ctx.fillStyle = "#f1f5f9";
        ctx.textAlign = "center";
        ctx.fillText(node.label, x, y + 32);
    });

    requestAnimationFrame(drawFrame);
}