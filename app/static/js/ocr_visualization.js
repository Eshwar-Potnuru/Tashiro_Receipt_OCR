const receiptCanvas = document.getElementById("receiptCanvas");
const loadingOverlay = document.getElementById("loadingOverlay");
const extractedData = document.getElementById("extractedData");
const continueButton = document.getElementById("continueButton");
const retakeButton = document.getElementById("retakeButton");

const ctx = receiptCanvas.getContext("2d");

// Color mapping for field types (matching legend)
const FIELD_COLORS = {
    vendor: "rgba(255, 99, 71, 0.5)",
    date: "rgba(50, 205, 50, 0.5)",
    total: "rgba(30, 144, 255, 0.5)",
    tax: "rgba(255, 165, 0, 0.5)",
    subtotal: "rgba(138, 43, 226, 0.5)",
};

const FIELD_LABELS = {
    vendor: "Vendor/Store",
    date: "Date",
    total: "Total Amount",
    tax: "Tax Amount",
    subtotal: "Subtotal",
    currency: "Currency",
};

let ocrResult = null;

async function init() {
    const urlParams = new URLSearchParams(window.location.search);
    const queueId = urlParams.get("queueId");
    
    if (!queueId) {
        extractedData.innerHTML = '<p class="placeholder">No queue ID provided.</p>';
        return;
    }

    loadingOverlay.classList.remove("hidden");
    
    try {
        // Poll for processing completion
        const result = await pollForResult(queueId);
        ocrResult = result;
        
        // Load and draw receipt with annotations
        await drawAnnotatedReceipt(result);
        
        // Display extracted fields
        displayExtractedFields(result);
        
        continueButton.disabled = false;
    } catch (error) {
        console.error("Processing failed:", error);
        extractedData.innerHTML = '<p class="placeholder">Processing failed. Please try again.</p>';
    } finally {
        loadingOverlay.classList.add("hidden");
    }
}

async function pollForResult(queueId, maxAttempts = 30) {
    for (let i = 0; i < maxAttempts; i++) {
        const response = await fetch(`/api/v1/mobile/queue/${queueId}`);
        if (!response.ok) {
            throw new Error("Failed to fetch queue item");
        }
        
        const item = await response.json();
        
        if (item.status === "processed" && item.result_summary) {
            return item.result_summary;
        }
        
        if (item.status === "failed") {
            throw new Error("Processing failed");
        }
        
        await new Promise(resolve => setTimeout(resolve, 1000));
    }
    
    throw new Error("Processing timeout");
}

async function drawAnnotatedReceipt(result) {
    if (!result.annotated_image) {
        return;
    }
    
    const img = new Image();
    await new Promise((resolve, reject) => {
        img.onload = resolve;
        img.onerror = reject;
        img.src = result.annotated_image;
    });
    
    receiptCanvas.width = img.width;
    receiptCanvas.height = img.height;
    
    // Draw receipt image
    ctx.drawImage(img, 0, 0);
    
    // Draw bounding boxes for each field
    if (result.field_boxes) {
        drawFieldBoxes(result.field_boxes);
    }
}

function drawFieldBoxes(fieldBoxes) {
    ctx.lineWidth = 3;
    
    for (const [fieldName, box] of Object.entries(fieldBoxes)) {
        if (!box || box.length !== 4) continue;
        
        const color = FIELD_COLORS[fieldName] || "rgba(255, 255, 255, 0.3)";
        ctx.strokeStyle = color;
        ctx.fillStyle = color;
        
        const [x1, y1, x2, y2] = box;
        const width = x2 - x1;
        const height = y2 - y1;
        
        // Draw rectangle
        ctx.fillRect(x1, y1, width, height);
        ctx.strokeRect(x1, y1, width, height);
        
        // Draw label
        ctx.fillStyle = "white";
        ctx.font = "bold 14px Inter, sans-serif";
        ctx.fillText(fieldName.toUpperCase(), x1 + 4, y1 + 16);
    }
}

function displayExtractedFields(result) {
    const fields = result.fields || {};
    const html = [];
    
    for (const [key, value] of Object.entries(fields)) {
        if (!value) continue;
        
        const label = FIELD_LABELS[key] || key;
        const fieldClass = `${key}-field`;
        
        html.push(`
            <div class="field-item ${fieldClass}">
                <div class="field-label">${label}</div>
                <div class="field-value">${escapeHtml(String(value))}</div>
            </div>
        `);
    }
    
    if (html.length === 0) {
        extractedData.innerHTML = '<p class="placeholder">No fields extracted.</p>';
    } else {
        extractedData.innerHTML = html.join("");
    }
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

continueButton.addEventListener("click", () => {
    const urlParams = new URLSearchParams(window.location.search);
    const queueId = urlParams.get("queueId");
    window.location.href = `/verification?queueId=${queueId}`;
});

retakeButton.addEventListener("click", () => {
    window.location.href = "/mobile";
});

init();
