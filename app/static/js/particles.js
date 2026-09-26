/**
 * particles.js
 *
 * Lightweight, dependency-free animated particle background rendered on
 * an HTML5 canvas for the Landing Page's futuristic HUD aesthetic.
 * Deliberately avoids heavier libraries (Three.js, particles.js CDN) to
 * keep the public marketing page fast-loading; a simple canvas-based
 * starfield/particle drift achieves the same visual effect at a fraction
 * of the payload size.
 */

document.addEventListener("DOMContentLoaded", () => {
    const container = document.getElementById("particle-background");
    if (!container) return;

    const canvas = document.createElement("canvas");
    container.appendChild(canvas);
    const ctx = canvas.getContext("2d");

    let particles = [];
    const PARTICLE_COUNT = 70;
    const PARTICLE_COLORS = ["#3b82f6", "#22d3ee", "#a855f7"];

    /**
     * Resizes the canvas to match the current viewport dimensions,
     * called on load and on window resize.
     */
    function resizeCanvas() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }

    /**
     * Initializes the particle array with randomized positions,
     * velocities, sizes, and colors.
     */
    function initParticles() {
        particles = Array.from({ length: PARTICLE_COUNT }, () => ({
            x: Math.random() * canvas.width,
            y: Math.random() * canvas.height,
            radius: Math.random() * 1.8 + 0.5,
            speedX: (Math.random() - 0.5) * 0.3,
            speedY: (Math.random() - 0.5) * 0.3,
            color: PARTICLE_COLORS[Math.floor(Math.random() * PARTICLE_COLORS.length)],
            opacity: Math.random() * 0.5 + 0.2,
        }));
    }

    /**
     * Renders one animation frame: clears the canvas, draws and moves
     * each particle, wrapping around screen edges, and schedules the
     * next frame via requestAnimationFrame.
     */
    function drawFrame() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        particles.forEach(particle => {
            particle.x += particle.speedX;
            particle.y += particle.speedY;

            if (particle.x < 0) particle.x = canvas.width;
            if (particle.x > canvas.width) particle.x = 0;
            if (particle.y < 0) particle.y = canvas.height;
            if (particle.y > canvas.height) particle.y = 0;

            ctx.beginPath();
            ctx.arc(particle.x, particle.y, particle.radius, 0, Math.PI * 2);
            ctx.fillStyle = particle.color;
            ctx.globalAlpha = particle.opacity;
            ctx.fill();
        });

        ctx.globalAlpha = 1;
        requestAnimationFrame(drawFrame);
    }

    // Respect the user's reduced-motion preference — render a single
    // static frame instead of a continuous animation loop.
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    resizeCanvas();
    initParticles();

    if (prefersReducedMotion) {
        drawStaticFrame();
    } else {
        drawFrame();
    }

    window.addEventListener("resize", () => {
        resizeCanvas();
        initParticles();
        if (prefersReducedMotion) drawStaticFrame();
    });

    /**
     * Renders a single static frame of particles (no animation loop),
     * used when the user has requested reduced motion.
     */
    function drawStaticFrame() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        particles.forEach(particle => {
            ctx.beginPath();
            ctx.arc(particle.x, particle.y, particle.radius, 0, Math.PI * 2);
            ctx.fillStyle = particle.color;
            ctx.globalAlpha = particle.opacity;
            ctx.fill();
        });
        ctx.globalAlpha = 1;
    }
});