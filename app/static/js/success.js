const startAgainButton = document.getElementById("startAgainButton");
const viewHistoryButton = document.getElementById("viewHistoryButton");

async function init() {
    const urlParams = new URLSearchParams(window.location.search);
    const queueId = urlParams.get("queueId");

    if (queueId) {
        document.getElementById("queueId").textContent = queueId;

        // Fetch submission data
        try {
            const response = await fetch(`/api/v1/mobile/queue/${queueId}`);
            if (response.ok) {
                const data = await response.json();
                
                if (data.result_summary && data.result_summary.fields) {
                    const fields = data.result_summary.fields;
                    document.getElementById("vendor").textContent = fields.vendor || "—";
                    document.getElementById("date").textContent = fields.date || "—";
                    document.getElementById("total").textContent = 
                        `${fields.currency || "JPY"} ${fields.total || "—"}`;
                }

                if (data.result_summary && data.result_summary.category) {
                    document.getElementById("category").textContent = data.result_summary.category;
                }

                // Show user info
                if (data.metadata && data.metadata.user) {
                    document.getElementById("userName").textContent = 
                        data.metadata.user.name || "—";
                }
            }
        } catch (error) {
            console.warn("Failed to load submission summary", error);
        }
    }

    // Load user from localStorage as fallback
    const storedUser = localStorage.getItem("tashiro_user");
    if (storedUser) {
        try {
            const user = JSON.parse(storedUser);
            if (document.getElementById("userName").textContent === "—") {
                document.getElementById("userName").textContent = user.name || "—";
            }
        } catch (e) {
            console.warn("Failed to parse user data", e);
        }
    }
}

startAgainButton.addEventListener("click", () => {
    window.location.href = "/mobile";
});

viewHistoryButton.addEventListener("click", () => {
    window.location.href = "/history";
});

init();
