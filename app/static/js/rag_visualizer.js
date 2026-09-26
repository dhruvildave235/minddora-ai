/**
 * rag_visualizer.js
 *
 * Renders the real hybrid retrieval pipeline as a neuron-style network:
 * query words on the left, an abstract embedding-space middle layer,
 * and the document's real chunks on the right — with connection
 * brightness/thickness driven by each chunk's actual relevance score
 * from app.ai.retriever, run live via /api/admin/rag-viz/visualize.
 */

let canvas, ctx, width, height;
let queryWords = [];
let chunkResults = [];
let animProgress = 0;

document.addEventListener("DOMContentLoaded", () => {
    canvas = document.getElementById("rag-canvas");
    if (!canvas) return;

    ctx = canvas.getContext("2d");
    resizeCanvas();
    window.addEventListener("resize", resizeCanvas);

    document.getElementById("viz-run-btn").addEventListener("click", runVisualization);
    requestAnimationFrame(drawFrame);
});

function resizeCanvas() {
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * window.devicePixelRatio;
    canvas.height = rect.height * window.devicePixelRatio;
    ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
    width = rect.width;
    height = rect.height;
}

async function runVisualization() {
    const question = document.getElementById("viz-question-input").value.trim();
    const select = document.getElementById("viz-document-select");
    const documentId = select.value;
    const userId = select.options[select.selectedIndex].dataset.userId;

    if (!question) {
        showToast("Enter a question first.", "error");
        return;
    }

    const response = await apiRequest("/api/admin/rag-viz/visualize", {
        method: "POST",
        body: { question, document_id: parseInt(documentId), user_id: parseInt(userId) },
    });

    if (!response.success) return;

    queryWords = response.data.query_words;
    chunkResults = response.data.chunks;
    animProgress = 0;
}

function wordNodes() {
    const n = queryWords.length || 1;
    return queryWords.map((w, i) => ({
        label: w,
        x: width * 0.12,
        y: height * ((i + 1) / (n + 1)),
    }));
}

function embeddingNodes() {
    const count = 8;
    return Array.from({ length: count }, (_, i) => ({
        x: width * 0.5,
        y: height * ((i + 1) / (count + 1)),
    }));
}

function chunkNodes() {
    const n = chunkResults.length || 1;
    return chunkResults.map((c, i) => ({
        ...c,
        x: width * 0.88,
        y: height * ((i + 1) / (n + 1)),
    }));
}

function scoreColor(score) {
    if (score >= 0.5) return "#22c55e";
    if (score >= 0.25) return "#22d3ee";
    if (score >= 0.1) return "#3b82f6";
    return "rgba(148, 163, 184, 0.35)";
}

function drawFrame() {
    ctx.clearRect(0, 0, width, height);

    if (animProgress < 1) animProgress += 0.015;

    const words = wordNodes();
    const embed = embeddingNodes();
    const chunks = chunkNodes();

    // Query words -> embedding layer (all connected, dim)
    words.forEach(w => {
        embed.forEach(e => {
            ctx.beginPath();
            ctx.moveTo(w.x, w.y);
            ctx.lineTo(e.x, e.y);
            ctx.strokeStyle = "rgba(168, 85, 247, 0.12)";
            ctx.lineWidth = 1;
            ctx.stroke();
        });
    });

    // Embedding layer -> chunk nodes, weighted by real score
    embed.forEach(e => {
        chunks.forEach(c => {
            const alpha = Math.min(animProgress * 1.5, 1);
            ctx.beginPath();
            ctx.moveTo(e.x, e.y);
            ctx.lineTo(c.x, c.y);
            ctx.strokeStyle = scoreColor(c.score).startsWith("#")
                ? scoreColor(c.score) + Math.round(c.score * alpha * 200 + 20).toString(16).padStart(2, "0")
                : scoreColor(c.score);
            ctx.lineWidth = 0.5 + c.score * 3;
            ctx.stroke();
        });
    });

    // Word nodes
    words.forEach(w => {
        ctx.beginPath();
        ctx.arc(w.x, w.y, 8, 0, Math.PI * 2);
        ctx.fillStyle = "#a855f7";
        ctx.fill();
        ctx.font = "12px sans-serif";
        ctx.fillStyle = "#f1f5f9";
        ctx.textAlign = "right";
        ctx.fillText(w.label, w.x - 14, w.y + 4);
    });

    // Embedding nodes
    embed.forEach(e => {
        ctx.beginPath();
        ctx.arc(e.x, e.y, 6, 0, Math.PI * 2);
        ctx.fillStyle = "#1e293b";
        ctx.strokeStyle = "#22d3ee";
        ctx.lineWidth = 1.5;
        ctx.fill();
        ctx.stroke();
    });

    // Chunk nodes, sized/colored by real relevance score
    chunks.forEach(c => {
        const radius = 8 + c.score * 14;
        ctx.beginPath();
        ctx.arc(c.x, c.y, radius, 0, Math.PI * 2);
        ctx.fillStyle = scoreColor(c.score);
        ctx.fill();

        ctx.font = "11px sans-serif";
        ctx.fillStyle = "#f1f5f9";
        ctx.textAlign = "left";
        ctx.fillText(`p.${c.page_number || "?"} · ${(c.score * 100).toFixed(0)}%`, c.x + radius + 8, c.y + 4);
    });

    requestAnimationFrame(drawFrame);
}