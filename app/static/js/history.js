const historyGrid = document.getElementById("historyGrid");
const historyEmpty = document.getElementById("historyEmpty");
const historyLimit = document.getElementById("historyLimit");
const refreshButton = document.getElementById("refreshButton");
const backButton = document.getElementById("backButton");
const historyCardTemplate = document.getElementById("historyCardTemplate");

backButton?.addEventListener("click", () => {
    window.location.href = "/mobile";
});

async function fetchHistory(limit) {
    const response = await fetch(`/api/v1/history?limit=${encodeURIComponent(limit)}`);
    if (!response.ok) {
        throw new Error("Failed to fetch history");
    }
    return response.json();
}

function formatCurrency(value) {
    if (value == null) return "—";
    try {
        return new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(value);
    } catch (error) {
        return Number(value).toFixed(2);
    }
}

function formatTimestamp(isoString) {
    if (!isoString) return "";
    try {
        const date = new Date(isoString);
        return date.toLocaleString();
    } catch (error) {
        return isoString;
    }
}

function renderHistory(entries) {
    historyGrid.innerHTML = "";
    if (!entries.length) {
        historyEmpty.classList.remove("hidden");
        return;
    }
    historyEmpty.classList.add("hidden");

    entries.forEach((entry) => {
        const node = historyCardTemplate.content.firstElementChild.cloneNode(true);
        node.querySelector(".vendor").textContent = entry.vendor || entry.source_filename || "Unknown";
        node.querySelector(".date").textContent = entry.date || "—";
        node.querySelector(".total").textContent = formatCurrency(entry.total);
        node.querySelector(".verified").textContent = entry.verified ? "Yes" : "No";
        node.querySelector(".primary-category").textContent = entry.primary_category || "—";
        node.querySelector(".issues").textContent = (entry.verification_issues || []).join("\n") || "";
        node.querySelector(".timestamp").textContent = formatTimestamp(entry.timestamp);

        const thumb = node.querySelector(".thumbnail img");
        const placeholder =
            "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='400' height='240' viewBox='0 0 400 240'%3E%3Cdefs%3E%3ClinearGradient id='g' x1='0' y1='0' x2='1' y2='1'%3E%3Cstop offset='0%25' stop-color='%23E5ECF6'/%3E%3Cstop offset='100%25' stop-color='%23CAD5E4'/%3E%3C/linearGradient%3E%3C/defs%3E%3Crect width='400' height='240' rx='20' fill='url(%23g)'/%3E%3Cpath d='M80 60h240v20H80zM80 110h160v16H80zM80 150h200v16H80zM80 190h120v16H80z' fill='%2390A4C2' opacity='0.6'/%3E%3C/svg%3E";
        thumb.src = entry.thumbnail_url || placeholder;
        thumb.alt = `Receipt thumbnail for ${entry.vendor || entry.source_filename || "receipt"}`;

        const excelLink = node.querySelector(".excel-link");
        if (entry.excel_url) {
            excelLink.href = entry.excel_url;
        } else {
            excelLink.classList.add("disabled");
            excelLink.removeAttribute("href");
            excelLink.textContent = "No Excel export";
        }

        // View More button
        const viewMoreBtn = node.querySelector(".view-more-btn");
        const expandedDetails = node.querySelector(".expanded-details");
        
        viewMoreBtn.addEventListener("click", () => {
            const isExpanded = !expandedDetails.classList.contains("hidden");
            expandedDetails.classList.toggle("hidden");
            viewMoreBtn.textContent = isExpanded ? "📄 View Details" : "🔼 Hide Details";
            
            if (!isExpanded && expandedDetails.querySelector(".detail-fields").children.length === 0) {
                // Populate expanded details
                const detailFields = expandedDetails.querySelector(".detail-fields");
                detailFields.innerHTML = `
                    <div><strong>Vendor:</strong><span>${entry.vendor || "—"}</span></div>
                    <div><strong>Date:</strong><span>${entry.date || "—"}</span></div>
                    <div><strong>Subtotal:</strong><span>${entry.subtotal || "—"}</span></div>
                    <div><strong>Tax:</strong><span>${entry.tax || "—"}</span></div>
                    <div><strong>Total:</strong><span>${formatCurrency(entry.total)}</span></div>
                    <div><strong>Currency:</strong><span>${entry.currency || "—"}</span></div>
                    <div><strong>Category:</strong><span>${entry.primary_category || "—"}</span></div>
                `;
                
                const userInfo = expandedDetails.querySelector(".user-info");
                if (entry.user) {
                    userInfo.innerHTML = `
                        <h4>Submitted By</h4>
                        <div><strong>Name:</strong><span>${entry.user.name || "—"}</span></div>
                        <div><strong>Email:</strong><span>${entry.user.email || "—"}</span></div>
                        <div><strong>ID:</strong><span>${entry.user.id || "—"}</span></div>
                    `;
                }
            }
        });

        historyGrid.appendChild(node);
    });
}

async function refreshHistory() {
    try {
        refreshButton.disabled = true;
        const limit = Number(historyLimit.value) || 50;
        const entries = await fetchHistory(limit);
        renderHistory(entries);
    } catch (error) {
        console.error(error);
        historyEmpty.textContent = "Unable to load history. Please try again.";
        historyEmpty.classList.remove("hidden");
    } finally {
        refreshButton.disabled = false;
    }
}

refreshButton.addEventListener("click", refreshHistory);
historyLimit.addEventListener("change", refreshHistory);

document.addEventListener("DOMContentLoaded", () => {
    refreshHistory();
});
