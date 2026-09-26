/**
 * upload.js
 *
 * Client-side logic for the Upload Notes page: drag-and-drop file
 * selection, client-side pre-validation, upload progress display via
 * XMLHttpRequest (needed for real upload progress events, unlike
 * fetch()), and polling the document's processing status until it
 * reaches "ready" or "failed".
 */

const ALLOWED_EXTENSIONS = ["pdf", "docx", "txt", "md", "png", "jpg", "jpeg"];
const MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024;

let selectedFile = null;

document.addEventListener("DOMContentLoaded", () => {
    const dropzone = document.getElementById("upload-dropzone");
    const fileInput = document.getElementById("upload-file-input");
    const submitBtn = document.getElementById("upload-submit-btn");

    if (!dropzone) return;

    dropzone.addEventListener("click", () => fileInput.click());

    dropzone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropzone.classList.add("dropzone-active");
    });

    dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dropzone-active"));

    dropzone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropzone.classList.remove("dropzone-active");
        if (e.dataTransfer.files.length > 0) {
            handleFileSelection(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener("change", () => {
        if (fileInput.files.length > 0) {
            handleFileSelection(fileInput.files[0]);
        }
    });

    submitBtn.addEventListener("click", handleUploadSubmit);
});

/**
 * Validates and stores the selected file client-side (extension, size),
 * updating the dropzone UI and enabling the submit button if valid.
 * This is a UX convenience only — the server re-validates everything in
 * app/utils/validators.py's validate_upload_file() regardless.
 *
 * @param {File} file - The selected/dropped File object.
 */
function handleFileSelection(file) {
    const extension = file.name.split(".").pop().toLowerCase();

    if (!ALLOWED_EXTENSIONS.includes(extension)) {
        showToast(`Unsupported file type. Allowed: ${ALLOWED_EXTENSIONS.join(", ")}`, "error");
        return;
    }

    if (file.size > MAX_FILE_SIZE_BYTES) {
        showToast("File exceeds the maximum allowed size of 25 MB.", "error");
        return;
    }

    selectedFile = file;

    const dropzone = document.getElementById("upload-dropzone");
    dropzone.querySelector("p").innerHTML = `<strong>Selected:</strong> ${escapeHtml(file.name)}`;

    document.getElementById("upload-submit-btn").disabled = false;
}

/**
 * Submits the selected file to POST /api/documents/upload via
 * XMLHttpRequest (rather than fetch()) specifically to capture real-time
 * upload progress events for the progress bar UI, then begins polling
 * the document's processing status once the upload completes.
 */
function handleUploadSubmit() {
    if (!selectedFile) return;

    const title = document.getElementById("upload-title-input").value.trim();
    const subject = document.getElementById("upload-subject-input").value.trim();

    const formData = new FormData();
    formData.append("file", selectedFile);
    if (title) formData.append("title", title);
    if (subject) formData.append("subject", subject);

    const progressContainer = document.getElementById("upload-progress-container");
    const progressBarFill = document.getElementById("upload-progress-bar-fill");
    const statusText = document.getElementById("upload-status-text");
    const submitBtn = document.getElementById("upload-submit-btn");

    progressContainer.classList.remove("hidden");
    submitBtn.disabled = true;
    statusText.textContent = "Uploading...";

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/documents/upload");
    xhr.setRequestHeader("X-CSRFToken", getCsrfToken());

    xhr.upload.addEventListener("progress", (event) => {
        if (event.lengthComputable) {
            const percent = Math.round((event.loaded / event.total) * 100);
            progressBarFill.style.width = `${percent}%`;
        }
    });

    xhr.addEventListener("load", () => {
        try {
            const response = JSON.parse(xhr.responseText);
            if (response.success) {
                statusText.textContent = "Processing your document...";
                pollDocumentStatus(response.data.document.id);
            } else {
                showToast(response.error, "error");
                resetUploadForm();
            }
        } catch (err) {
            showToast("Upload failed. Please try again.", "error");
            resetUploadForm();
        }
    });

    xhr.addEventListener("error", () => {
        showToast("Network error during upload. Please try again.", "error");
        resetUploadForm();
    });

    xhr.send(formData);
}

/**
 * Polls GET /api/documents/<id>/status every 2 seconds until the
 * document's processing_status reaches a terminal state ("ready" or
 * "failed"), updating the status text to reflect the current pipeline
 * stage (Extracting, Chunking, Embedding).
 *
 * @param {number} documentId - The newly created Document.id to poll.
 */
function pollDocumentStatus(documentId) {
    const statusText = document.getElementById("upload-status-text");
    const statusLabels = {
        queued: "Queued for processing...",
        extracting: "Extracting text...",
        chunking: "Splitting into chunks...",
        embedding: "Generating embeddings...",
        ready: "✓ Document ready!",
        failed: "✕ Processing failed.",
    };

    const intervalId = setInterval(async () => {
        const response = await apiRequest(`/api/documents/${documentId}/status`, { suppressErrorToast: true });

        if (!response.success) {
            clearInterval(intervalId);
            return;
        }

        const status = response.data.processing_status;
        statusText.textContent = statusLabels[status] || status;

        if (status === "ready") {
            clearInterval(intervalId);
            showToast("Document processed successfully!", "success");
            setTimeout(() => { window.location.href = "/my-documents"; }, 1200);
        } else if (status === "failed") {
            clearInterval(intervalId);
            showToast(response.data.processing_error || "Processing failed.", "error");
            resetUploadForm();
        }
    }, 2000);
}

/**
 * Resets the upload form UI back to its initial state, used after an
 * upload failure so the student can try again without reloading the page.
 */
function resetUploadForm() {
    selectedFile = null;
    document.getElementById("upload-submit-btn").disabled = true;
    document.getElementById("upload-progress-container").classList.add("hidden");
    document.getElementById("upload-progress-bar-fill").style.width = "0%";
    document.getElementById("upload-file-input").value = "";

    const dropzone = document.getElementById("upload-dropzone");
    dropzone.querySelector("p").innerHTML = "<strong>Drag & drop</strong> your file here, or click to browse";
}