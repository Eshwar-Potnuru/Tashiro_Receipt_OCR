const verificationForm = document.getElementById("verificationForm");
const receiptThumbnail = document.getElementById("receiptThumbnail");
const retakeButton = document.getElementById("retakeButton");
const reuploadButton = document.getElementById("reuploadButton");

let queueId = null;
let queueData = null;

async function init() {
    const urlParams = new URLSearchParams(window.location.search);
    queueId = urlParams.get("queueId");
    
    if (!queueId) {
        alert("No queue ID provided");
        window.location.href = "/mobile";
        return;
    }

    // Load user info from localStorage
    const storedUser = localStorage.getItem("tashiro_user");
    if (storedUser) {
        try {
            const user = JSON.parse(storedUser);
            document.getElementById("userName").textContent = user.name || "—";
            document.getElementById("userEmail").textContent = user.email || "—";
            document.getElementById("userId").textContent = user.id || "—";
        } catch (e) {
            console.warn("Failed to parse user data", e);
        }
    }

    // Fetch queue item data
    try {
        const response = await fetch(`/api/v1/mobile/queue/${queueId}`);
        if (!response.ok) {
            throw new Error("Failed to fetch queue data");
        }
        
        queueData = await response.json();
        
        // Populate form with extracted data
        if (queueData.result_summary && queueData.result_summary.fields) {
            const fields = queueData.result_summary.fields;
            document.getElementById("vendor").value = fields.vendor || "";
            document.getElementById("date").value = fields.date || "";
            document.getElementById("subtotal").value = fields.subtotal || "";
            document.getElementById("tax").value = fields.tax || "";
            document.getElementById("total").value = fields.total || "";
            document.getElementById("currency").value = fields.currency || "JPY";
        }

        // Set category if available
        if (queueData.result_summary && queueData.result_summary.category) {
            document.getElementById("category").value = queueData.result_summary.category;
        }

        // Show receipt thumbnail
        if (queueData.stored_path) {
            receiptThumbnail.src = `/artifacts/${queueData.stored_path.replace(/\\/g, "/")}`;
        }
    } catch (error) {
        console.error("Failed to load queue data", error);
        alert("Failed to load receipt data");
    }
}

verificationForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const formData = new FormData(verificationForm);
    const correctedData = {
        queue_id: queueId,
        fields: {
            vendor: formData.get("vendor"),
            date: formData.get("date"),
            subtotal: formData.get("subtotal"),
            tax: formData.get("tax"),
            total: formData.get("total"),
            currency: formData.get("currency"),
        },
        category: formData.get("category"),
    };

    try {
        const response = await fetch("/api/v1/mobile/verify", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(correctedData),
        });

        if (!response.ok) {
            throw new Error("Submission failed");
        }

        const result = await response.json();
        
        // Redirect to success page
        window.location.href = `/success?queueId=${queueId}`;
    } catch (error) {
        console.error("Submission error", error);
        alert("Failed to submit. Please try again.");
    }
});

retakeButton.addEventListener("click", () => {
    window.location.href = "/mobile";
});

reuploadButton.addEventListener("click", () => {
    window.location.href = "/mobile";
});

init();
