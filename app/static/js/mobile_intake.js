// Receipt OCR Mobile Interface
console.log("Loading mobile intake script...");

// Global state
const state = {
    stream: null,
    user: null,
    queueId: null,
    currentBlob: null,
    analysis: null,
    imageBase64: null,
};

// DOM Elements
let registrationModal, registrationForm, editProfileButton;
let userInitialsEl, sidebarUserNameEl, sidebarUserEmailEl, sidebarUserIdEl;
let openCameraButton, stopCameraButton, captureButton, fileInput, dropzone;
let cameraFeed, captureOverlay, cameraPlaceholder;
let analysisCanvas, analysisPlaceholder, analysisLoader;
let verificationForm, submitButton, resetButton, verificationStatus;
let historyList, historyEmpty, historyLimit, refreshHistoryButton;
let toastContainer;

// Initialize when DOM is ready
document.addEventListener("DOMContentLoaded", function() {
    console.log("DOM loaded, initializing...");
    initElements();
    bindEvents();
    loadUser();
    refreshHistory();
    console.log("Initialization complete!");
});

function initElements() {
    console.log("Initializing DOM elements...");
    
    registrationModal = document.getElementById("registrationModal");
    registrationForm = document.getElementById("registrationForm");
    editProfileButton = document.getElementById("editProfileButton");
    userInitialsEl = document.getElementById("userInitials");
    sidebarUserNameEl = document.getElementById("sidebarUserName");
    sidebarUserEmailEl = document.getElementById("sidebarUserEmail");
    sidebarUserIdEl = document.getElementById("sidebarUserId");

    openCameraButton = document.getElementById("openCameraButton");
    stopCameraButton = document.getElementById("stopCameraButton");
    captureButton = document.getElementById("captureButton");
    fileInput = document.getElementById("fileInput");
    dropzone = document.getElementById("dropzone");
    cameraFeed = document.getElementById("cameraFeed");
    captureOverlay = document.getElementById("captureOverlay");
    cameraPlaceholder = document.getElementById("cameraPlaceholder");

    analysisCanvas = document.getElementById("analysisCanvas");
    analysisPlaceholder = document.getElementById("analysisPlaceholder");
    analysisLoader = document.getElementById("analysisLoader");
    verificationForm = document.getElementById("verificationForm");
    submitButton = document.getElementById("submitButton");
    resetButton = document.getElementById("resetButton");
    verificationStatus = document.getElementById("verificationStatus");

    historyList = document.getElementById("historyList");
    historyEmpty = document.getElementById("historyEmpty");
    historyLimit = document.getElementById("historyLimit");
    refreshHistoryButton = document.getElementById("refreshHistoryButton");

    toastContainer = document.getElementById("toastContainer");
    
    console.log("DOM elements initialized");
}

function bindEvents() {
    console.log("Binding events...");
    
    if (openCameraButton) {
        openCameraButton.addEventListener("click", startCamera);
        console.log("Camera button bound");
    }
    
    if (stopCameraButton) {
        stopCameraButton.addEventListener("click", stopCamera);
    }
    
    if (captureButton) {
        captureButton.addEventListener("click", captureFrame);
    }
    
    if (fileInput) {
        fileInput.addEventListener("change", onFileInputChange);
        console.log("File input bound");
    }
    
    if (resetButton) {
        resetButton.addEventListener("click", resetWorkspace);
    }
    
    if (refreshHistoryButton) {
        refreshHistoryButton.addEventListener("click", refreshHistory);
    }
    
    if (historyLimit) {
        historyLimit.addEventListener("change", refreshHistory);
    }
    
    if (editProfileButton) {
        editProfileButton.addEventListener("click", function() {
            if (registrationModal) {
                registrationModal.classList.remove("hidden");
            }
        });
    }
    
    if (verificationForm) {
        verificationForm.addEventListener("submit", onSubmitReceipt);
    }
    
    if (registrationForm) {
        registrationForm.addEventListener("submit", onRegisterUser);
        console.log("Registration form bound");
    }

    // Drag and drop
    if (dropzone) {
        ["dragenter", "dragover"].forEach((eventName) => {
            dropzone.addEventListener(eventName, (event) => {
                event.preventDefault();
                dropzone.classList.add("dragover");
            });
        });
        ["dragleave", "drop"].forEach((eventName) => {
            dropzone.addEventListener(eventName, (event) => {
                event.preventDefault();
                dropzone.classList.remove("dragover");
            });
        });
        dropzone.addEventListener("drop", async (event) => {
            event.preventDefault();
            const file = event.dataTransfer?.files?.[0];
            if (file) {
                await handleFile(file);
            }
        });
        console.log("Dropzone bound");
    }

    window.addEventListener("beforeunload", stopCamera);
    console.log("Events bound successfully!");
}

function loadUser() {
        let stored = null;
        try {
            stored = localStorage.getItem("tashiro_user_v2");
        } catch (error) {
            console.warn("Local storage unavailable", error);
        }

        if (stored) {
            try {
                state.user = JSON.parse(stored);
                updateUserUI();
                registrationModal.classList.add("hidden");
                return;
            } catch (error) {
                console.warn("Failed to parse stored user", error);
            }
        }
        registrationModal.classList.remove("hidden");
    }

    async function onRegisterUser(event) {
        event.preventDefault();
        const name = document.getElementById("regName")?.value.trim();
        const email = document.getElementById("regEmail")?.value.trim();
        const id = document.getElementById("regId")?.value.trim() || null;

        if (!name || !email) {
            showToast("Please provide both name and email to continue.", "error");
            return;
        }

        const userData = {
            name,
            email,
            id,
            registered_at: new Date().toISOString(),
        };

        state.user = userData;
        try {
            localStorage.setItem("tashiro_user_v2", JSON.stringify(userData));
        } catch (error) {
            console.warn("Unable to persist user in local storage", error);
        }
        updateUserUI();

        try {
            await fetch("/api/v1/mobile/register", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(userData),
            });
        } catch (error) {
            console.warn("Failed to register user", error);
        }

        registrationModal.classList.add("hidden");
        showToast(`Welcome back, ${name}!`, "success");
    }

    function updateUserUI() {
        if (!state.user) {
            userInitialsEl.textContent = "--";
            sidebarUserNameEl.textContent = "Guest";
            sidebarUserEmailEl.textContent = "—";
            sidebarUserIdEl.textContent = "ID: —";
            return;
        }
        const initials = state.user.name
            .split(" ")
            .map((part) => part[0] || "")
            .join("")
            .slice(0, 2)
            .toUpperCase();
        userInitialsEl.textContent = initials || "--";
        sidebarUserNameEl.textContent = state.user.name;
        sidebarUserEmailEl.textContent = state.user.email;
        sidebarUserIdEl.textContent = state.user.id ? `ID: ${state.user.id}` : "ID: —";
    }

    async function startCamera() {
        if (!navigator.mediaDevices?.getUserMedia) {
            showToast("Camera not supported on this device.", "error");
            return;
        }
        try {
            state.stream = await navigator.mediaDevices.getUserMedia({
                video: {
                    facingMode: { ideal: "environment" },
                    width: { ideal: 1280 },
                    height: { ideal: 720 },
                },
                audio: false,
            });
            if (cameraFeed) {
                cameraFeed.srcObject = state.stream;
                cameraFeed.play?.();
            }
            if (cameraPlaceholder) {
                cameraPlaceholder.style.display = "none";
            }
            captureButton.disabled = false;
            showToast("Camera ready. Capture when receipt is in frame.", "success");
        } catch (error) {
            console.warn("Camera access failed", error);
            showToast("Unable to access camera. Check permissions.", "error");
        }
    }

    function stopCamera() {
        if (state.stream) {
            state.stream.getTracks().forEach((track) => track.stop());
            state.stream = null;
        }
        if (cameraFeed) {
            cameraFeed.srcObject = null;
        }
        if (cameraPlaceholder) {
            cameraPlaceholder.style.display = "flex";
        }
    }

    async function captureFrame() {
        if (!state.stream || !cameraFeed) {
            showToast("Start the camera before capturing.", "warning");
            return;
        }
        const trackSettings = state.stream.getVideoTracks()[0]?.getSettings() || {};
        const width = trackSettings.width || cameraFeed.videoWidth || 1280;
        const height = trackSettings.height || cameraFeed.videoHeight || 720;
        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext("2d");
        if (!ctx) {
            showToast("Capture failed. Try again.", "error");
            return;
        }
        ctx.drawImage(cameraFeed, 0, 0, width, height);
        await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.9)).then(async (blob) => {
            if (!blob) {
                showToast("Capture failed. Try again.", "error");
                return;
            }
            await analyzeBlob(blob, "camera-capture.jpg");
        });
        stopCamera();
    }

    async function onFileInputChange(event) {
        const file = event.target?.files?.[0];
        if (file) {
            await handleFile(file);
        }
        if (fileInput) {
            fileInput.value = "";
        }
    }

    async function handleFile(file) {
        const sanitized = await maybeCompress(file);
        await analyzeBlob(sanitized, sanitized.name || "receipt-upload.jpg");
    }

    async function maybeCompress(file) {
        const maxSizeBytes = 2.5 * 1024 * 1024;
        if (file.size <= maxSizeBytes) {
            return file;
        }
        const bitmap = await createImageBitmap(file);
        const canvas = document.createElement("canvas");
        const scale = Math.sqrt(maxSizeBytes / file.size);
        canvas.width = Math.round(bitmap.width * scale);
        canvas.height = Math.round(bitmap.height * scale);
        const ctx = canvas.getContext("2d");
        ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
        const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.85));
        if (!blob) {
            return file;
        }
        return new File([blob], file.name.replace(/\.[^.]+$/, ".jpg"), { type: "image/jpeg" });
    }

    async function analyzeBlob(file, filename) {
        if (!state.user) {
            registrationModal.classList.remove("hidden");
            showToast("Please confirm your profile before uploading.", "warning");
            return;
        }

        showLoader();
        submitButton.disabled = true;
        verificationStatus.textContent = "";

        const formData = new FormData();
        formData.append("file", file, filename);
        const metadata = {
            captured_at: new Date().toISOString(),
            source_filename: filename,
            user: state.user,
        };
        formData.append("metadata", JSON.stringify(metadata));

        try {
            const response = await fetch("/api/v1/mobile/analyze", {
                method: "POST",
                body: formData,
            });
            if (!response.ok) {
                throw new Error(`Analyze failed with status ${response.status}`);
            }
            const payload = await response.json();
            state.queueId = payload.queue_id;
            state.analysis = payload;
            state.currentBlob = file;
            renderAnalysis(payload);
            showToast("OCR analysis complete. Review the fields before submitting.", "success");
        } catch (error) {
            console.error("Analysis error", error);
            showToast("Failed to analyze receipt. Please try again.", "error");
            resetWorkspace(true);
        } finally {
            hideLoader();
        }
    }

    function renderAnalysis(payload) {
        if (!payload) {
            return;
        }
        const fieldValues = { ...(payload.fields || {}) };
        const sourceImage = fieldValues.source_image;
        delete fieldValues.source_image;

        populateVerificationForm(fieldValues);
        updateVerificationStatus(payload.fields_confidence, payload.verification);
        drawAnalysisImage(payload.annotated_image || sourceImage, payload.field_boxes);

        submitButton.disabled = !payload.queue_id;
    }

    function populateVerificationForm(fields) {
        const mapping = {
            vendor: document.getElementById("fieldVendor"),
            date: document.getElementById("fieldDate"),
            subtotal: document.getElementById("fieldSubtotal"),
            tax: document.getElementById("fieldTax"),
            total: document.getElementById("fieldTotal"),
            currency: document.getElementById("fieldCurrency"),
        };

        Object.entries(mapping).forEach(([key, input]) => {
            if (!input) {
                return;
            }
            const value = fields?.[key];
            input.value = value == null ? "" : value;
        });

        const categorySelect = document.getElementById("fieldCategory");
        if (categorySelect) {
            const category = state.analysis?.primary_category;
            categorySelect.value = category && [...categorySelect.options].some((option) => option.value === category)
                ? category
                : "";
        }
    }

    function drawAnalysisImage(base64Image, fieldBoxes) {
        if (!analysisCanvas) {
            return;
        }
        const ctx = analysisCanvas.getContext("2d");
        if (!ctx) {
            return;
        }
        if (!base64Image) {
            ctx.clearRect(0, 0, analysisCanvas.width, analysisCanvas.height);
            analysisPlaceholder?.classList.remove("hidden");
            return;
        }
        analysisPlaceholder?.classList.add("hidden");
        const image = new Image();
        image.onload = () => {
            analysisCanvas.width = image.width;
            analysisCanvas.height = image.height;
            ctx.clearRect(0, 0, image.width, image.height);
            ctx.drawImage(image, 0, 0, image.width, image.height);
            drawBoxes(ctx, fieldBoxes, image.width, image.height);
        };
        image.src = base64Image.startsWith("data:") ? base64Image : `data:image/png;base64,${base64Image}`;
    }

    function drawBoxes(ctx, boxes, width, height) {
        if (!boxes) {
            return;
        }
        const colors = {
            vendor: "#38bdf8",
            date: "#a855f7",
            currency: "#f97316",
            subtotal: "#14b8a6",
            tax: "#facc15",
            total: "#f87171",
        };
        ctx.lineWidth = Math.max(2, Math.min(width, height) * 0.0035);
        Object.entries(boxes).forEach(([field, points]) => {
            if (!Array.isArray(points) || points.length !== 4) {
                return;
            }
            const color = colors[field] || "#38bdf8";
            ctx.strokeStyle = color;
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.moveTo(points[0][0], points[0][1]);
            for (let i = 1; i < points.length; i += 1) {
                ctx.lineTo(points[i][0], points[i][1]);
            }
            ctx.closePath();
            ctx.stroke();
            const labelX = points[0][0];
            const labelY = Math.max(points[0][1] - 6, 12);
            ctx.font = `${Math.max(12, width * 0.017)}px Inter`;
            ctx.fillText(field.toUpperCase(), labelX + 4, labelY);
        });
    }

    function updateVerificationStatus(confidence = {}, verification = {}) {
        if (!verificationStatus) {
            return;
        }
        const issues = verification?.issues || [];
        const verified = Boolean(verification?.verified);
        const confidenceValues = Object.values(confidence).filter((value) => typeof value === "number");
        const averageConfidence = confidenceValues.length
            ? Math.round((confidenceValues.reduce((sum, value) => sum + value, 0) / confidenceValues.length) * 100)
            : null;

        let message = "";
        if (verified && !issues.length) {
                    message = "All key fields validated.";
        } else if (issues.length) {
            message = `Check highlighted fields: ${issues.join(", ")}`;
        } else {
            message = "Review OCR output and confirm totals before submitting.";
        }

        if (averageConfidence !== null) {
            message += ` — Average confidence ${averageConfidence}%`;
        }

        verificationStatus.textContent = message;
        verificationStatus.classList.remove("success", "error");
        verificationStatus.classList.add(issues.length ? "error" : "success");
    }

    async function onSubmitReceipt(event) {
        event.preventDefault();
        if (!state.queueId) {
            showToast("Analyze a receipt before submitting.", "warning");
            return;
        }
        submitButton.disabled = true;

        const formData = new FormData(verificationForm);
        const fields = {
            vendor: formData.get("vendor")?.toString().trim() || null,
            date: formData.get("date")?.toString().trim() || null,
            subtotal: formData.get("subtotal")?.toString().trim() || null,
            tax: formData.get("tax")?.toString().trim() || null,
            total: formData.get("total")?.toString().trim() || null,
            currency: formData.get("currency")?.toString().trim() || null,
        };
        const category = formData.get("category")?.toString() || null;
        const payload = {
            queue_id: state.queueId,
            fields,
            category,
            verification: state.analysis?.verification,
        };

        try {
            const response = await fetch("/api/v1/mobile/submit", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            if (!response.ok) {
                throw new Error(`Submit failed with status ${response.status}`);
            }
            const result = await response.json();
            showToast("Receipt submitted successfully.", "success");
            resetWorkspace();
            await refreshHistory();
            return result;
        } catch (error) {
            console.error("Submit error", error);
            showToast("Submission failed. Please try again.", "error");
        } finally {
            submitButton.disabled = false;
        }
    }

    function resetWorkspace(keepUser = false) {
        analysisPlaceholder?.classList.remove("hidden");
        if (analysisCanvas) {
            const ctx = analysisCanvas.getContext("2d");
            ctx?.clearRect(0, 0, analysisCanvas.width, analysisCanvas.height);
        }
        verificationForm?.reset();
        verificationStatus.textContent = "";
        submitButton.disabled = true;
        state.queueId = null;
        state.analysis = null;
        state.currentBlob = null;
        state.imageBase64 = null;
        if (!keepUser) {
            stopCamera();
        }
    }

    async function refreshHistory() {
        try {
            const limit = Number(historyLimit?.value || 50);
            const response = await fetch(`/api/v1/history?limit=${limit}`);
            if (!response.ok) {
                throw new Error(`History fetch failed with status ${response.status}`);
            }
            const entries = await response.json();
            renderHistory(entries);
        } catch (error) {
            console.error("History error", error);
        }
    }

    function renderHistory(entries) {
        if (!historyList || !historyEmpty) {
            return;
        }
        historyList.innerHTML = "";
        if (!entries?.length) {
            historyEmpty.style.display = "block";
            return;
        }
        historyEmpty.style.display = "none";

        entries.forEach((entry) => {
            const item = document.createElement("article");
            item.className = "history-item";

            const thumbWrapper = document.createElement("div");
            thumbWrapper.className = "history-thumb";
            if (entry.thumbnail_url) {
                const img = document.createElement("img");
                img.alt = entry.source_filename || "Receipt thumbnail";
                img.src = entry.thumbnail_url;
                thumbWrapper.appendChild(img);
            } else {
                const placeholder = document.createElement("div");
                placeholder.style.display = "flex";
                placeholder.style.alignItems = "center";
                placeholder.style.justifyContent = "center";
                placeholder.style.height = "100%";
                placeholder.style.fontSize = "12px";
                placeholder.style.color = "rgba(148, 163, 184, 0.8)";
                placeholder.textContent = "No preview";
                thumbWrapper.appendChild(placeholder);
            }

            const meta = document.createElement("div");
            meta.className = "history-meta";

            const title = document.createElement("h4");
            title.textContent = entry.vendor || entry.source_filename || "Untitled receipt";
            meta.appendChild(title);

            const date = document.createElement("p");
            const submitted = entry.timestamp ? new Date(entry.timestamp) : null;
            date.textContent = submitted ? submitted.toLocaleString() : "Submission time unknown";
            meta.appendChild(date);

            const total = document.createElement("p");
                    const totalValue = entry.fields?.total ?? entry.total;
                    const currency = entry.fields?.currency || "";
                    const numericTotal = typeof totalValue === "number" ? totalValue : parseFloat(totalValue);
                    if (Number.isFinite(numericTotal)) {
                        const formatted = numericTotal.toFixed(2);
                        total.textContent = currency ? `Total: ${currency} ${formatted}` : `Total: ${formatted}`;
                    } else if (totalValue) {
                        total.textContent = `Total: ${totalValue}`;
                    } else {
                        total.textContent = "Total unavailable";
                    }
            meta.appendChild(total);

            const category = document.createElement("span");
            category.className = "tag";
            const categoryName = entry.primary_category || entry.fields?.primary_category;
            if (entry.verified) {
                category.classList.add("success");
            } else {
                category.classList.add("neutral");
            }
            category.textContent = categoryName ? categoryName : entry.verified ? "Verified" : "Pending";
            meta.appendChild(category);

            const actions = document.createElement("div");
            actions.className = "history-actions-row";
            if (entry.excel_url) {
                const downloadLink = document.createElement("a");
                downloadLink.href = entry.excel_url;
                downloadLink.textContent = "Download Excel";
                downloadLink.target = "_blank";
                actions.appendChild(downloadLink);
            }
            if (entry.thumbnail_url) {
                const viewLink = document.createElement("a");
                viewLink.href = entry.thumbnail_url;
                viewLink.textContent = "View Receipt";
                viewLink.target = "_blank";
                actions.appendChild(viewLink);
            }

            meta.appendChild(actions);

            item.appendChild(thumbWrapper);
            item.appendChild(meta);

            historyList.appendChild(item);
        });
    }

    function showLoader() {
        analysisLoader?.classList.remove("hidden");
    }

    function hideLoader() {
        analysisLoader?.classList.add("hidden");
    }

        function showToast(message, type = "info") {
        if (!toastContainer) {
            return;
        }
        const toast = document.createElement("div");
        toast.className = `toast ${type}`;
        toast.textContent = message;
        toastContainer.appendChild(toast);
            requestAnimationFrame(() => {
                toast.classList.add("visible");
            });
            setTimeout(() => {
                toast.classList.remove("visible");
                toast.addEventListener(
                    "transitionend",
                    () => toast.remove(),
                    { once: true }
                );
            }, 4000);
    }

console.log("Mobile intake script loaded successfully!");
