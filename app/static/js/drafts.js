/**
 * Phase 4F: Enhanced Draft Management with Edit, Delete, and Visual Indicators
 * 
 * UI-only logic for managing receipt drafts.
 * Does NOT implement validation - trusts backend API responses only.
 * 
 * Phase 4F Features:
 * - Edit drafts directly in modal
 * - Visual validation status indicators
 * - Delete with confirmation
 * - Draft metadata display
 * - Duplicate prevention (backend)
 */

// State
let allDrafts = [];
let selectedDraftIds = new Set();
let currentDraftId = null;
let isSending = false; // Phase 4D.2: Track send operations
let isEditing = false; // Phase 4F.2: Track edit mode

/**
 * Open the draft modal and load drafts
 */
function openDraftModal() {
    document.getElementById('draftModal').style.display = 'block';
    loadDrafts();
}

/**
 * Close the draft modal and reset state
 */
function closeDraftModal() {
    // Phase 4D.2: Prevent close during send
    if (isSending) {
        return;
    }
    
    document.getElementById('draftModal').style.display = 'none';
    
    // Phase 4D.2: Clean state reset
    selectedDraftIds.clear();
    currentDraftId = null;
    
    // Clear detail panel
    document.getElementById('draftDetailContainer').innerHTML = 
        '<div style="text-align: center; padding: 40px 20px; color: #64748b;">Select a draft to view details</div>';
    
    updateSelectionCount();
}

/**
 * Load all drafts from backend API
 */
async function loadDrafts() {
    const container = document.getElementById('draftListContainer');
    
    try {
        container.innerHTML = '<div style="text-align: center; padding: 40px 20px; color: #64748b;">Loading drafts...</div>';
        
        const response = await fetch('/api/drafts');
        if (!response.ok) throw new Error('Failed to load drafts');
        
        const data = await response.json();
        // Backend returns array directly, not {drafts: [...]}
        allDrafts = Array.isArray(data) ? data : (data.drafts || []);
        
        // Sort by created_at desc (newest first)
        allDrafts.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
        
        renderDraftList();
    } catch (error) {
        console.error('Error loading drafts:', error);
        container.innerHTML = '<div style="text-align: center; padding: 40px 20px; color: #dc3545;">Failed to load drafts. Please try again.</div>';
    }
}

/**
 * Render draft list table
 */
function renderDraftList() {
    const container = document.getElementById('draftListContainer');
    
    if (allDrafts.length === 0) {
        // Phase 4D.2: Improved empty state messaging
        container.innerHTML = `
            <div style="text-align: center; padding: 40px 20px; color: #64748b;">
                <div style="font-size: 16px; font-weight: 500; color: #475569; margin-bottom: 8px;">
                    📋 No receipt drafts found
                </div>
                <div style="font-size: 14px; line-height: 1.6;">
                    Drafts are created when you save OCR results without sending.
                </div>
            </div>
        `;
        return;
    }
    
    const table = `
        <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
            <thead>
                <tr style="background: #f8fafc; border-bottom: 2px solid #e2e8f0;">
                    <th style="padding: 12px 8px; text-align: left; font-weight: 600; color: #64748b; width: 40px;"></th>
                    <th style="padding: 12px 8px; text-align: left; font-weight: 600; color: #64748b; width: 30px;"></th>
                    <th style="padding: 12px 8px; text-align: left; font-weight: 600; color: #64748b;">Vendor</th>
                    <th style="padding: 12px 8px; text-align: right; font-weight: 600; color: #64748b;">Amount</th>
                    <th style="padding: 12px 8px; text-align: center; font-weight: 600; color: #64748b;">Date</th>
                    <th style="padding: 12px 8px; text-align: center; font-weight: 600; color: #64748b;">Status</th>
                </tr>
            </thead>
            <tbody>
                ${allDrafts.map(draft => {
                    const isSelected = selectedDraftIds.has(draft.draft_id);
                    const isSent = draft.status === 'SENT';
                    // Phase 4D.2: Disable interactions during send
                    const isDisabled = isSending || isSent;
                    const rowStyle = isDisabled ? 'opacity: 0.6;' : 'cursor: pointer;';
                    const bgColor = currentDraftId === draft.draft_id ? '#e0e7ff' : (draft.status === 'SENT' ? '#f1f5f9' : 'white');
                    
                    // Phase 4F.4: Visual validation indicator
                    const isValid = draft.is_valid !== undefined ? draft.is_valid : false;
                    const validationIcon = isSent ? '' : (isValid ? '✅' : '⚠️');
                    const validationColor = isValid ? '#10b981' : '#f59e0b';
                    
                    return `
                        <tr style="border-bottom: 1px solid #e2e8f0; ${rowStyle} background: ${bgColor};" 
                            onclick="${isSending ? '' : `loadDraftDetails('${draft.draft_id}')`}"
                            onmouseover="if('${draft.status}' === 'DRAFT' && !${isSending}) this.style.background='#f8fafc'"
                            onmouseout="this.style.background='${bgColor}'">
                            <td style="padding: 12px 8px;">
                                <input type="checkbox" 
                                       ${isDisabled ? 'disabled' : ''}
                                       ${isSelected ? 'checked' : ''}
                                       onclick="event.stopPropagation(); toggleDraftSelection('${draft.draft_id}')"
                                       style="cursor: ${isDisabled ? 'not-allowed' : 'pointer'};">
                            </td>
                            <td style="padding: 12px 8px; text-align: center; font-size: 16px;" title="${isValid ? 'Ready to send' : 'Incomplete - missing required fields'}">
                                <span style="color: ${validationColor};">${validationIcon}</span>
                            </td>
                            <td style="padding: 12px 8px; font-weight: 500; color: #1e293b;">
                                ${escapeHtml(draft.receipt.vendor_name || 'N/A')}
                            </td>
                            <td style="padding: 12px 8px; text-align: right; font-weight: 500; color: #1e293b;">
                                ¥${formatAmount(draft.receipt.total_amount)}
                            </td>
                            <td style="padding: 12px 8px; text-align: center; color: #64748b; font-size: 13px;">
                                ${formatDate(draft.receipt.receipt_date)}
                            </td>
                            <td style="padding: 12px 8px; text-align: center;">
                                <span style="padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: 600; 
                                             background: ${isSent ? '#d1fae5' : '#fef3c7'}; 
                                             color: ${isSent ? '#065f46' : '#92400e'};">
                                    ${draft.status}
                                </span>
                            </td>
                        </tr>
                    `;
                }).join('')}
            </tbody>
        </table>
    `;
    
    container.innerHTML = table;
    updateSelectionCount();
}

/**
 * Toggle draft selection (checkbox)
 */
function toggleDraftSelection(draftId) {
    const draft = allDrafts.find(d => d.draft_id === draftId);
    
    // Only allow selecting DRAFT status
    if (draft && draft.status === 'DRAFT') {
        if (selectedDraftIds.has(draftId)) {
            selectedDraftIds.delete(draftId);
        } else {
            selectedDraftIds.add(draftId);
        }
    }
    
    updateSelectionCount();
    renderDraftList(); // Re-render to update checkboxes
}

/**
 * Update selection count display
 */
function updateSelectionCount() {
    const count = selectedDraftIds.size;
    document.getElementById('draftSelectionCount').textContent = 
        `${count} draft${count !== 1 ? 's' : ''} selected`;
    document.getElementById('sendSelectedDraftsBtn').disabled = count === 0;
}

/**
 * Load draft details (including validation)
 */
async function loadDraftDetails(draftId) {
    currentDraftId = draftId;
    renderDraftList(); // Re-render to highlight selected row
    
    const container = document.getElementById('draftDetailContainer');
    container.innerHTML = '<div style="text-align: center; padding: 40px 20px; color: #64748b;">Loading details...</div>';
    
    try {
        // Find draft in current list (includes validation status)
        const draft = allDrafts.find(d => d.draft_id === draftId);
        
        if (!draft) {
            // Fallback: fetch from API if not in list
            const draftResponse = await fetch(`/api/drafts/${draftId}`);
            if (!draftResponse.ok) throw new Error('Failed to load draft');
            const draftData = await draftResponse.json();
            renderDraftDetails(draftData, draftData.validation_errors || []);
        } else {
            // Use draft from list (already has validation status)
            renderDraftDetails(draft, draft.validation_errors || []);
        }
    } catch (error) {
        console.error('Error loading draft details:', error);
        container.innerHTML = '<div style="text-align: center; padding: 40px 20px; color: #dc3545;">Failed to load details.</div>';
    }
}

/**
 * Render draft details panel
 */
async function renderDraftDetails(draft, validationErrors) {
    const container = document.getElementById('draftDetailContainer');
    const r = draft.receipt;
    
    // Fetch staff name from ID
    let staffDisplay = r.staff_id || 'N/A';
    if (r.staff_id && r.business_location_id) {
        try {
            const staffName = await getStaffName(r.business_location_id, r.staff_id);
            staffDisplay = staffName ? `${staffName} (${r.staff_id})` : r.staff_id;
        } catch (error) {
            console.error('Failed to fetch staff name:', error);
        }
    }
    
    // Phase 4F.2: Edit and Delete buttons (only for DRAFT status)
    const actionButtons = draft.status === 'DRAFT' ? `
        <div style="margin-bottom: 24px; display: flex; gap: 12px; justify-content: flex-end;">
            <button onclick="enterEditMode('${draft.draft_id}')" 
                    style="padding: 10px 20px; background: var(--primary-blue, #3b82f6); color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 14px;">
                <i class="fas fa-edit"></i> Edit Draft
            </button>
            <button onclick="confirmDeleteDraft('${draft.draft_id}')" 
                    style="padding: 10px 20px; background: #dc3545; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 14px;">
                <i class="fas fa-trash"></i> Delete
            </button>
        </div>
    ` : '';
    
    const detailsHtml = `
        ${actionButtons}
        
        <!-- Receipt Information -->
        <div style="margin-bottom: 24px;">
            <h4 style="font-size: 14px; font-weight: 600; color: #64748b; margin-bottom: 12px; text-transform: uppercase;">Receipt Information</h4>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                ${renderField('Vendor Name', r.vendor_name || 'N/A')}
                ${renderField('Date', r.receipt_date || 'N/A')}
                ${renderField('Total Amount', `¥${formatAmount(r.total_amount)}`)}
                ${renderField('Tax (10%)', `¥${formatAmount(r.tax_10_amount || 0)}`)}
                ${renderField('Tax (8%)', `¥${formatAmount(r.tax_8_amount || 0)}`)}
                ${renderField('Invoice Number', r.invoice_number || 'N/A')}
            </div>
        </div>
        
        <!-- Location & Staff -->
        <div style="margin-bottom: 24px;">
            <h4 style="font-size: 14px; font-weight: 600; color: #64748b; margin-bottom: 12px; text-transform: uppercase;">Location & Staff</h4>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                ${renderField('Business Location', r.business_location_id || 'N/A')}
                ${renderField('Staff Member', staffDisplay)}
            </div>
        </div>
        
        <!-- Phase 4F.5: Draft Metadata -->
        <div style="margin-bottom: 24px;">
            <h4 style="font-size: 14px; font-weight: 600; color: #64748b; margin-bottom: 12px; text-transform: uppercase;">📋 Draft Metadata</h4>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                <div>
                    <div style="font-size: 12px; color: #64748b; margin-bottom: 4px;">Status</div>
                    <span style="padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: 600; display: inline-block;
                                 background: ${draft.status === 'SENT' ? '#d1fae5' : '#fef3c7'}; 
                                 color: ${draft.status === 'SENT' ? '#065f46' : '#92400e'};">
                        ${draft.status}
                    </span>
                </div>
                ${renderField('Draft ID', draft.draft_id.substring(0, 8) + '...')}
                ${renderField('Created At', formatDateTime(draft.created_at))}
                ${renderField('Last Updated', formatDateTime(draft.updated_at))}
                ${draft.sent_at ? renderField('Sent At', formatDateTime(draft.sent_at)) : ''}
                ${draft.image_ref ? renderField('Image Reference', draft.image_ref.substring(0, 12) + '...') : ''}
            </div>
        </div>
        
        <!-- Status Message for SENT drafts or Validation Errors for DRAFT -->
        ${draft.status === 'SENT' ? `
        <div style="margin-bottom: 24px;">
            <div style="background: #d1fae5; border-left: 4px solid #10b981; border-radius: 4px; padding: 16px; text-align: center;">
                <div style="font-weight: 600; color: #065f46; font-size: 16px; margin-bottom: 4px;">✅ Sent to Excel</div>
                <div style="font-size: 13px; color: #047857;">This receipt has been successfully sent to HQ</div>
                ${draft.sent_at ? `<div style="font-size: 12px; color: #059669; margin-top: 8px;">Sent at: ${formatDateTime(draft.sent_at)}</div>` : ''}
            </div>
        </div>
        ` : validationErrors.length > 0 ? `
        <div id="validationErrorsSection" style="margin-bottom: 24px;">
            <h4 style="font-size: 14px; font-weight: 600; color: #dc3545; margin-bottom: 8px; text-transform: uppercase;">Validation Errors</h4>
            <div style="background: #fee; border-left: 4px solid #dc3545; border-radius: 4px; padding: 12px 16px; margin-bottom: 12px;">
                <div style="font-weight: 600; color: #991b1b; font-size: 13px;">⚠️ This draft cannot be sent yet</div>
                <div style="font-size: 12px; color: #7f1d1d; margin-top: 4px;">Fix the errors below before sending to HQ</div>
            </div>
            <div style="background: #fef2f2; border: 1px solid #fecaca; border-radius: 6px; padding: 16px;">
                ${validationErrors.map(err => `
                    <div style="color: #991b1b; font-size: 14px; margin-bottom: 8px; display: flex; align-items: flex-start; gap: 8px;">
                        <span style="font-weight: bold;">⚠</span>
                        <span>${escapeHtml(err)}</span>
                    </div>
                `).join('')}
            </div>
        </div>
        ` : ''}
        
        <!-- Source Image -->
        ${draft.image_ref || draft.image_data ? `
        <div style="margin-bottom: 24px;">
            <h4 style="font-size: 14px; font-weight: 600; color: #64748b; margin-bottom: 12px; text-transform: uppercase;">📷 Receipt Image</h4>
            <div style="position: relative; background: #f8fafc; border-radius: 8px; padding: 12px; text-align: center;">
                ${draft.image_data ? `
                    <img id="draftImage_${draft.draft_id}" 
                         src="data:image/jpeg;base64,${draft.image_data}" 
                         style="width: 100%; max-width: 500px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.15); cursor: pointer;"
                         alt="Receipt Image"
                         onclick="window.open(this.src, '_blank')">
                ` : `
                    <img id="draftImage_${draft.draft_id}" 
                         src="/artifacts/ocr_results/${draft.image_ref}.${getImageFormat(draft)}" 
                         style="width: 100%; max-width: 500px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.15); cursor: pointer;"
                         alt="Receipt Image"
                         onclick="window.open(this.src, '_blank')"
                         onerror="tryAlternativeImageFormats(this, '${draft.image_ref}');">
                    <div id="imageError_${draft.draft_id}" style="display: none; color: #64748b; font-size: 13px; padding: 20px;">
                        <i class="fas fa-image" style="font-size: 32px; opacity: 0.3; margin-bottom: 8px;"></i><br>
                        Image not available<br>
                        <span style="font-size: 11px; color: #94a3b8;">(${draft.image_ref})</span>
                    </div>
                `}
            </div>
        </div>
        ` : ''}
    `;
    
    container.innerHTML = detailsHtml;
    
    // Phase 4D.2: Auto-scroll to validation errors if they exist
    if (validationErrors.length > 0) {
        setTimeout(() => {
            const errorSection = document.getElementById('validationErrorsSection');
            if (errorSection) {
                errorSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        }, 100);
    }
}

/**
 * Phase 4F Fix 1: Get image format from stored data (avoids 404s)
 */
function getImageFormat(draft) {
    // Check if format is stored in receipt diagnostics (from analysis)
    if (draft.receipt && draft.receipt.diagnostics && draft.receipt.diagnostics.image_format) {
        return draft.receipt.diagnostics.image_format;
    }
    // Fallback to jpg (will try alternatives if this fails)
    return 'jpg';
}

/**
 * Helper: Get staff name from ID by fetching from API
 */
async function getStaffName(location, staffId) {
    try {
        const response = await fetch(`/api/staff?location=${encodeURIComponent(location)}`);
        if (!response.ok) return null;
        
        const data = await response.json();
        const staffList = data.staff || [];
        const staff = staffList.find(s => s.id === staffId);
        return staff ? staff.name : null;
    } catch (error) {
        console.error('Error fetching staff:', error);
        return null;
    }
}

/**
 * Helper: Try alternative image formats if jpg fails
 */
function tryAlternativeImageFormats(img, imageRef) {
    const formats = ['png', 'jpeg', 'webp'];
    const currentSrc = img.src;
    
    // Check which format failed
    const lastFormat = currentSrc.split('.').pop();
    const currentIndex = formats.indexOf(lastFormat);
    
    if (currentIndex < formats.length - 1) {
        // Try next format
        const nextFormat = formats[currentIndex + 1];
        img.src = `/artifacts/ocr_results/${imageRef}.${nextFormat}`;
    } else {
        // All formats failed, show error message
        img.style.display = 'none';
        const errorDiv = document.getElementById(`imageError_${img.id.split('_')[1]}`);
        if (errorDiv) {
            errorDiv.style.display = 'block';
        }
    }
}

/**
 * Helper: Render a field row
 */
function renderField(label, value) {
    return `
        <div>
            <div style="font-size: 12px; color: #64748b; margin-bottom: 4px;">${label}</div>
            <div style="font-size: 14px; font-weight: 500; color: #1e293b;">${value}</div>
        </div>
    `;
}

/**
 * Send selected drafts via backend API
 */
async function sendSelectedDrafts() {
    if (selectedDraftIds.size === 0) return;
    
    // Phase 4F: Validate that selected drafts have location and staff
    const selectedDrafts = allDrafts.filter(d => selectedDraftIds.has(d.draft_id));
    const invalidDrafts = selectedDrafts.filter(d => 
        !d.receipt.business_location_id || !d.receipt.staff_id
    );
    
    if (invalidDrafts.length > 0) {
        const invalidList = invalidDrafts.map(d => 
            `• ${d.receipt.vendor_name || 'Unknown'} - Missing: ${!d.receipt.business_location_id ? 'Location' : ''} ${!d.receipt.staff_id ? 'Staff' : ''}`
        ).join('\n');
        
        alert(`⚠️ Cannot send incomplete drafts!\n\nLocation and Staff are required fields.\n\nIncomplete drafts (${invalidDrafts.length}):\n${invalidList}\n\nPlease edit these drafts to add Location and Staff before sending.`);
        return;
    }
    
    // Phase 4D.2: Send confirmation dialog
    const count = selectedDraftIds.size;
    const confirmMessage = count === 1 
        ? "Send this receipt to HQ? This action cannot be undone."
        : `Send ${count} receipts to HQ? This action cannot be undone.`;
    
    if (!confirm(confirmMessage)) {
        return; // User cancelled
    }
    
    const draftIds = Array.from(selectedDraftIds);
    const btn = document.getElementById('sendSelectedDraftsBtn');
    
    // Phase 4D.2: Set sending state and disable UI
    isSending = true;
    btn.disabled = true;
    btn.textContent = 'Sending...';
    renderDraftList(); // Re-render to disable checkboxes and row clicks
    
    try {
        const response = await fetch('/api/drafts/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ draft_ids: draftIds })
        });
        
        if (!response.ok) throw new Error('Send request failed');
        
        const result = await response.json();
        
        // Show result summary
        showSendResults(result);
        
        // Refresh draft list
        selectedDraftIds.clear();
        await loadDrafts();
        
        // Clear detail panel if current draft was sent
        if (currentDraftId && draftIds.includes(currentDraftId)) {
            currentDraftId = null;
            document.getElementById('draftDetailContainer').innerHTML = 
                '<div style="text-align: center; padding: 40px 20px; color: #64748b;">Select a draft to view details</div>';
        }
        
    } catch (error) {
        console.error('Send error:', error);
        alert('Failed to send drafts. Please try again.');
    } finally {
        // Phase 4D.2: Re-enable UI
        isSending = false;
        btn.disabled = false;
        btn.textContent = 'Send';
        renderDraftList(); // Re-render to re-enable interactions
    }
}

/**
 * Show send results in alert/notification
 */
function showSendResults(result) {
    const successCount = result.sent || 0;
    const failedCount = result.failed || 0;
    
    let message = `Send completed:\n`;
    message += `✓ Sent: ${successCount}\n`;
    message += `✗ Failed: ${failedCount}\n\n`;
    
    if (result.results && result.results.length > 0) {
        result.results.forEach(r => {
            if (!r.success && r.errors) {
                message += `\nDraft ${r.draft_id.slice(0, 8)}...\n`;
                r.errors.forEach(err => message += `  • ${err}\n`);
            }
        });
    }
    
    alert(message);
}

// ============================================================================
// Phase 4F: Edit and Delete Functions
// ============================================================================

/**
 * Phase 4F.2: Enter edit mode for a draft
 */
async function enterEditMode(draftId) {
    isEditing = true;
    const draft = allDrafts.find(d => d.draft_id === draftId);
    if (!draft) return;
    
    const container = document.getElementById('draftDetailContainer');
    const r = draft.receipt;
    
    // Fetch locations and staff for dropdowns
    let locationsHtml = '<option value="">Select location...</option>';
    let staffHtml = '<option value="">Select staff...</option>';
    
    try {
        const locResponse = await fetch('/api/locations');
        if (locResponse.ok) {
            const locData = await locResponse.json();
            const locations = locData.locations || [];
            // API returns array of location names, not objects
            locationsHtml += locations.map(locName => 
                `<option value="${locName}" ${locName === r.business_location_id ? 'selected' : ''}>${locName}</option>`
            ).join('');
        }
        
        if (r.business_location_id) {
            const staffResponse = await fetch(`/api/staff?location=${encodeURIComponent(r.business_location_id)}`);
            if (staffResponse.ok) {
                const staffData = await staffResponse.json();
                const staffList = staffData.staff || [];
                staffHtml += staffList.map(staff => 
                    `<option value="${staff.id}" ${staff.id === r.staff_id ? 'selected' : ''}>${staff.name}</option>`
                ).join('');
            }
        }
    } catch (error) {
        console.error('Failed to load dropdowns:', error);
    }
    
    container.innerHTML = `
        <div style="margin-bottom: 20px;">
            <h4 style="font-size: 16px; font-weight: 600; color: #1e293b; margin-bottom: 8px;">✏️ Editing Draft</h4>
            <p style="font-size: 13px; color: #64748b;">Make changes and click Save to update the draft</p>
        </div>
        
        <form id="editDraftForm" style="display: grid; gap: 16px;">
            <div>
                <label style="display: block; font-size: 13px; font-weight: 600; color: #475569; margin-bottom: 6px;">Vendor Name</label>
                <input type="text" id="edit_vendor" value="${escapeHtml(r.vendor_name || '')}" 
                       style="width: 100%; padding: 10px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 14px;">
            </div>
            
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                <div>
                    <label style="display: block; font-size: 13px; font-weight: 600; color: #475569; margin-bottom: 6px;">Date</label>
                    <input type="date" id="edit_date" value="${r.receipt_date || ''}" 
                           style="width: 100%; padding: 10px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 14px;">
                </div>
                <div>
                    <label style="display: block; font-size: 13px; font-weight: 600; color: #475569; margin-bottom: 6px;">Total Amount (¥)</label>
                    <input type="number" step="0.01" id="edit_total" value="${r.total_amount || 0}" 
                           style="width: 100%; padding: 10px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 14px;">
                </div>
            </div>
            
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                <div>
                    <label style="display: block; font-size: 13px; font-weight: 600; color: #475569; margin-bottom: 6px;">Tax 10% (¥)</label>
                    <input type="number" step="0.01" id="edit_tax10" value="${r.tax_10_amount || 0}" 
                           style="width: 100%; padding: 10px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 14px;">
                </div>
                <div>
                    <label style="display: block; font-size: 13px; font-weight: 600; color: #475569; margin-bottom: 6px;">Tax 8% (¥)</label>
                    <input type="number" step="0.01" id="edit_tax8" value="${r.tax_8_amount || 0}" 
                           style="width: 100%; padding: 10px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 14px;">
                </div>
            </div>
            
            <div>
                <label style="display: block; font-size: 13px; font-weight: 600; color: #475569; margin-bottom: 6px;">Invoice Number</label>
                <input type="text" id="edit_invoice" value="${escapeHtml(r.invoice_number || '')}" 
                       style="width: 100%; padding: 10px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 14px;">
            </div>
            
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                <div>
                    <label style="display: block; font-size: 13px; font-weight: 600; color: #475569; margin-bottom: 6px;">Business Location</label>
                    <select id="edit_location" onchange="loadStaffForEdit(this.value)" 
                            style="width: 100%; padding: 10px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 14px;">
                        ${locationsHtml}
                    </select>
                </div>
                <div>
                    <label style="display: block; font-size: 13px; font-weight: 600; color: #475569; margin-bottom: 6px;">Staff Member</label>
                    <select id="edit_staff" 
                            style="width: 100%; padding: 10px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 14px;">
                        ${staffHtml}
                    </select>
                </div>
            </div>
            
            <div style="display: flex; gap: 12px; justify-content: flex-end; margin-top: 12px;">
                <button type="button" onclick="cancelEdit('${draftId}')" 
                        style="padding: 10px 24px; background: white; color: #64748b; border: 1px solid #cbd5e1; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 14px;">
                    Cancel
                </button>
                <button type="button" onclick="saveDraftEdit('${draftId}')" 
                        style="padding: 10px 24px; background: var(--primary-blue, #3b82f6); color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 14px;">
                    💾 Save Changes
                </button>
            </div>
        </form>
    `;
}

/**
 * Phase 4F.2: Load staff dropdown when location changes in edit mode
 */
async function loadStaffForEdit(locationId) {
    const staffSelect = document.getElementById('edit_staff');
    if (!staffSelect) return;
    
    staffSelect.innerHTML = '<option value="">Loading...</option>';
    
    try {
        const response = await fetch(`/api/staff?location=${encodeURIComponent(locationId)}`);
        if (!response.ok) throw new Error('Failed to load staff');
        
        const data = await response.json();
        const staffList = data.staff || [];
        
        staffSelect.innerHTML = '<option value="">Select staff...</option>' +
            staffList.map(staff => `<option value="${staff.id}">${staff.name}</option>`).join('');
    } catch (error) {
        console.error('Error loading staff:', error);
        staffSelect.innerHTML = '<option value="">Error loading staff</option>';
    }
}

/**
 * Phase 4F.2: Save draft edits
 */
async function saveDraftEdit(draftId) {
    const updatedReceipt = {
        vendor_name: document.getElementById('edit_vendor').value || '',
        receipt_date: document.getElementById('edit_date').value || '',
        total_amount: parseFloat(document.getElementById('edit_total').value) || 0,
        tax_10_amount: parseFloat(document.getElementById('edit_tax10').value) || 0,
        tax_8_amount: parseFloat(document.getElementById('edit_tax8').value) || 0,
        invoice_number: document.getElementById('edit_invoice').value || '',
        business_location_id: document.getElementById('edit_location').value || null,
        staff_id: document.getElementById('edit_staff').value || null
    };
    
    try {
        const response = await fetch(`/api/drafts/${draftId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ receipt: updatedReceipt })
        });
        
        if (!response.ok) throw new Error('Failed to update draft');
        
        const updatedDraft = await response.json();
        
        // Refresh draft list
        await loadDrafts();
        
        // Show updated draft details
        isEditing = false;
        await loadDraftDetails(draftId);
        
        alert('✅ Draft updated successfully!');
    } catch (error) {
        console.error('Error saving draft:', error);
        alert('❌ Failed to save changes: ' + error.message);
    }
}

/**
 * Phase 4F.2: Cancel editing
 */
function cancelEdit(draftId) {
    isEditing = false;
    loadDraftDetails(draftId);
}

/**
 * Phase 4F.6: Confirm and delete draft
 */
async function confirmDeleteDraft(draftId) {
    const draft = allDrafts.find(d => d.draft_id === draftId);
    const vendorName = draft ? draft.receipt.vendor_name : 'this draft';
    
    if (!confirm(`⚠️ Delete draft "${vendorName}"?\n\nThis action cannot be undone.`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/drafts/${draftId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) throw new Error('Failed to delete draft');
        
        // Refresh draft list
        await loadDrafts();
        
        // Clear detail panel
        currentDraftId = null;
        document.getElementById('draftDetailContainer').innerHTML = 
            '<div style="text-align: center; padding: 40px 20px; color: #64748b;">Select a draft to view details</div>';
        
        alert('✅ Draft deleted successfully');
    } catch (error) {
        console.error('Error deleting draft:', error);
        alert('❌ Failed to delete draft: ' + error.message);
    }
}

// ============================================================================
// Utility Functions
// ============================================================================

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatAmount(amount) {
    return Number(amount || 0).toLocaleString('ja-JP');
}

function formatDate(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString('ja-JP', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
    });
}

function formatDateTime(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleString('ja-JP', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// ============================================================================
// Event Wiring
// ============================================================================

// Wait for DOM to be ready
document.addEventListener('DOMContentLoaded', function() {
    // Open drafts button
    const openBtn = document.getElementById('openDraftsBtn');
    if (openBtn) {
        openBtn.addEventListener('click', openDraftModal);
    }
    
    // Close modal button
    const closeBtn = document.getElementById('closeDraftModalBtn');
    if (closeBtn) {
        closeBtn.addEventListener('click', closeDraftModal);
    }
    
    // Send selected button
    const sendBtn = document.getElementById('sendSelectedDraftsBtn');
    if (sendBtn) {
        sendBtn.addEventListener('click', sendSelectedDrafts);
    }
    
    // Close modal on background click
    const modal = document.getElementById('draftModal');
    if (modal) {
        modal.addEventListener('click', function(e) {
            if (e.target.id === 'draftModal') {
                closeDraftModal();
            }
        });
    }
});
