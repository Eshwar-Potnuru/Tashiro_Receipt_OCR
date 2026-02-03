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
 * 
 * Phase 5D-0: JWT Authentication
 * - All API calls include Authorization header with JWT token
 * 
 * Phase 5D-2: Multi-user Isolation
 * - AuthState as single source of truth
 * - Draft loading respects user ownership
 * - Logout functionality
 */

// ============================================================================
// Phase 5D-2: Auth State Management (Single Source of Truth)
// ============================================================================

/**
 * Global auth state - ONLY source of auth info for entire app
 * Populated on page load by decoding JWT from localStorage
 */
window.AuthState = {
    token: null,
    user_id: null,
    email: null,
    name: null,
    role: null,
    ready: false
};

// Debug flag (set window.DEBUG_DRAFTS = true or localStorage debug_drafts=1)
const DEBUG_DRAFTS = (window.DEBUG_DRAFTS === true) || (localStorage.getItem('debug_drafts') === '1');

/**
 * Bootstrap AuthState from localStorage token
 * Decodes JWT payload (base64 only, no signature verification)
 */
function bootstrapAuthState() {
    const token = localStorage.getItem('auth_token');
    
    if (!token) {
        window.AuthState.ready = true;
        return;
    }
    
    try {
        // JWT format: header.payload.signature
        const parts = token.split('.');
        if (parts.length !== 3) {
            console.warn('Invalid JWT format');
            window.AuthState.ready = true;
            return;
        }
        
        // Decode payload (base64url → base64 → JSON)
        const payload = parts[1];
        const base64 = payload.replace(/-/g, '+').replace(/_/g, '/');
        const jsonPayload = decodeURIComponent(atob(base64).split('').map(c => 
            '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)
        ).join(''));
        
        const decoded = JSON.parse(jsonPayload);
        
        // Populate AuthState from JWT claims
        window.AuthState.token = token;
        window.AuthState.user_id = decoded.sub || decoded.user_id || null;
        window.AuthState.email = decoded.email || null;
        window.AuthState.name = decoded.name || null;
        window.AuthState.role = decoded.role || null;
        window.AuthState.ready = true;
        
        if (DEBUG_DRAFTS) {
            console.log('✅ AuthState initialized:', {
                user_id: window.AuthState.user_id,
                email: window.AuthState.email,
                role: window.AuthState.role
            });
        }
    } catch (error) {
        console.error('Failed to decode JWT:', error);
        window.AuthState.ready = true;
    }
}

// Bootstrap on script load
bootstrapAuthState();

/**
 * Phase 5D-2.1: Refresh AuthState after login
 * Call this after successful login to update AuthState without reload
 */
window.refreshAuthState = function() {
    if (DEBUG_DRAFTS) {
        console.log('🔄 Refreshing AuthState...');
    }
    bootstrapAuthState();
    
    // Update user indicator if draft modal is open
    if (document.getElementById('draftModal').style.display === 'block') {
        displayCurrentUser();
    }
};

/**
 * Logout: Clear auth state and reload page
 */
function logout() {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('tashiro_user');
    window.AuthState = {
        token: null,
        user_id: null,
        email: null,
        name: null,
        role: null,
        ready: true
    };
    location.reload();
}

// Expose logout globally
window.logout = logout;

// ============================================================================
// Auth Helpers
// ============================================================================

// Auth helper for consistent JWT authentication (Phase 5D-0)
function getAuthHeaders() {
    const token = localStorage.getItem('auth_token');
    return token ? { 'Authorization': `Bearer ${token}` } : {};
}

/**
 * Phase 5D-1.2: Get preview source for draft (NO artifact path probing)
 * Returns null if no preview available (caller shows placeholder)
 */
function getDraftPreviewSrc(draft) {
    // 1) Prefer session cache if present
    if (window.previewByDraftId && draft.draft_id && window.previewByDraftId[draft.draft_id]) {
        return window.previewByDraftId[draft.draft_id];
    }
    // 2) Use backend image_data if present (base64)
    if (draft.image_data) {
        // Normalize: may already have data URI prefix or just base64
        if (draft.image_data.startsWith('data:image/')) return draft.image_data;
        return `data:image/jpeg;base64,${draft.image_data}`;
    }
    // 3) No preview available
    return null;
}

// State
let allDrafts = [];
let selectedDraftIds = new Set();
let currentDraftId = null;
let isSending = false; // Phase 4D.2: Track send operations
let isEditing = false; // Phase 4F.2: Track edit mode
let currentFilter = 'all'; // Phase 5D-0: Track current filter (all, DRAFT, SENT, ERROR)

// Phase 5D-1.2: Expose preview map globally for cross-file access
window.previewByDraftId = window.previewByDraftId || {};
let previewByDraftId = window.previewByDraftId;

/**
 * Open the draft modal and load drafts
 * Phase 5D-2: Wait for AuthState.ready before loading
 */
function openDraftModal() {
    document.getElementById('draftModal').style.display = 'block';
    
    // Phase 5D-2: Wait for AuthState to be ready
    if (!window.AuthState.ready) {
        const container = document.getElementById('draftListContainer');
        container.innerHTML = '<div style="text-align: center; padding: 40px 20px; color: #64748b;">Initializing...</div>';
        
        // Poll until ready (should be immediate, but defensive)
        const checkReady = setInterval(() => {
            if (window.AuthState.ready) {
                clearInterval(checkReady);
                initializeDraftModal();
            }
        }, 50);
        return;
    }
    
    initializeDraftModal();
}

/**
 * Initialize draft modal after AuthState is ready
 * Phase 5D-2: Check token, show user, load drafts
 */
function initializeDraftModal() {
    // Phase 5D-2.1: Refresh AuthState to get latest token (in case user just logged in)
    if (window.refreshAuthState) {
        window.refreshAuthState();
    }
    
    // Phase 5D-0: Set up filter event handlers
    setupFilterHandlers();
    
    // Phase 5D-2: Update user indicator from AuthState
    displayCurrentUser();
    
    // Phase 5D-2: Check for valid token
    if (!window.AuthState.token) {
        const container = document.getElementById('draftListContainer');
        container.innerHTML = `<div style="text-align: center; padding: 40px 20px; color: #dc3545;">
            <i class="fas fa-exclamation-triangle" style="font-size: 48px; opacity: 0.3; margin-bottom: 12px;"></i>
            <div style="font-size: 16px; margin-bottom: 8px;">Not logged in</div>
            <div style="font-size: 13px; color: #64748b;">Please log in to view drafts.</div>
        </div>`;
        return;
    }
    
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
    
    // Clear detail panel (with null check)
    const detailContainer = document.getElementById('draftDetailContainer');
    if (detailContainer) {
        detailContainer.innerHTML = 
            '<div style="text-align: center; padding: 40px 20px; color: #64748b;">Select a draft to view details</div>';
    }
    
    updateSelectionCount();
}

/**
 * Display current user indicator in draft menu
 * Phase 5D-2: Read from AuthState (single source of truth)
 */
function displayCurrentUser() {
    const userIndicator = document.getElementById('draftUserIndicator');
    if (!userIndicator) return;
    
    // Phase 5D-2: Use AuthState as single source of truth
    if (window.AuthState.token && window.AuthState.email) {
        const displayName = window.AuthState.name || window.AuthState.email;
        const role = window.AuthState.role || 'WORKER';
        userIndicator.textContent = `Logged in as: ${displayName} (${role})`;
        userIndicator.style.display = 'block';
        if (DEBUG_DRAFTS) {
            console.log('DEBUG: Draft user indicator set:', {
                user_id: window.AuthState.user_id,
                email: window.AuthState.email,
                role: window.AuthState.role
            });
        }
    } else {
        userIndicator.style.display = 'none';
    }
}

/**
 * Set up filter button event handlers
 */
function setupFilterHandlers() {
    // Phase 5D-1: Remove duplicate handlers by cloning buttons
    const filterButtons = ['filterAll', 'filterDraft', 'filterSent', 'filterError'];
    
    filterButtons.forEach(buttonId => {
        const button = document.getElementById(buttonId);
        if (button) {
            // Clone to remove existing listeners
            const newButton = button.cloneNode(true);
            button.parentNode.replaceChild(newButton, button);
            
            newButton.addEventListener('click', function() {
                const filter = this.getAttribute('data-filter');
                setActiveFilter(filter);
            });
        }
    });
}

/**
 * Set active filter and update UI
 */
function setActiveFilter(filter) {
    currentFilter = filter;
    
    // Update button styles
    const buttons = document.querySelectorAll('.draft-filter-btn');
    buttons.forEach(btn => {
        const btnFilter = btn.getAttribute('data-filter');
        if (btnFilter === filter) {
            btn.style.background = '#3b82f6';
            btn.style.color = 'white';
        } else {
            btn.style.background = '#e2e8f0';
            btn.style.color = '#475569';
        }
    });
    
    // Re-render list with filter
    renderDraftList();
}

/**
 * Load all drafts from backend API
 */
async function loadDrafts() {
    const container = document.getElementById('draftListContainer');
    if (!container) {
        console.error('draftListContainer element not found');
        return;
    }
    
    if (DEBUG_DRAFTS) {
        console.log('DEBUG: loadDrafts called, AuthState:', window.AuthState);
    }

    // Phase 5D-1.2: Check token before making request
    const token = localStorage.getItem('auth_token');
    if (!token) {
        container.innerHTML = `<div style="text-align: center; padding: 40px 20px; color: #dc3545;">
            <i class="fas fa-exclamation-triangle" style="font-size: 48px; opacity: 0.3; margin-bottom: 12px;"></i>
            <div style="font-size: 16px; margin-bottom: 8px;">Session expired</div>
            <div style="font-size: 13px; color: #64748b;">Please log in again to view drafts.</div>
        </div>`;
        return;
    }
    
    try {
        container.innerHTML = '<div style="text-align: center; padding: 40px 20px; color: #64748b;">Loading drafts...</div>';
        
        // Phase 5D-3: Debug multi-user isolation
        if (DEBUG_DRAFTS) {
            console.log('DEBUG: loadDrafts AuthState:', {
                user_id: window.AuthState.user_id,
                email: window.AuthState.email,
                role: window.AuthState.role,
                token_present: !!window.AuthState.token
            });
        }
        
        // Phase 5D-0: Use JWT authentication
        const response = await fetch('/api/drafts', { 
            headers: getAuthHeaders(),
            cache: 'no-store'
        });
        
        // Phase 5D-1.2: Handle auth errors cleanly
        if (response.status === 401 || response.status === 403) {
            container.innerHTML = `<div style="text-align: center; padding: 40px 20px; color: #dc3545;">
                <i class="fas fa-exclamation-triangle" style="font-size: 48px; opacity: 0.3; margin-bottom: 12px;"></i>
                <div style="font-size: 16px; margin-bottom: 8px;">Session expired</div>
                <div style="font-size: 13px; color: #64748b;">Please log in again to view drafts.</div>
            </div>`;
            return;
        }
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: Failed to load drafts`);
        }
        
        // Check if response has content
        const text = await response.text();
        if (!text || text.trim() === '') {
            // Empty response - show empty state
            allDrafts = [];
            renderDraftList();
            return;
        }
        
        const data = JSON.parse(text);
        // Backend returns array directly, not {drafts: [...]}
        allDrafts = Array.isArray(data) ? data : (data.drafts || []);
        
        // Sort by created_at desc (newest first)
        allDrafts.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
        
        if (DEBUG_DRAFTS) {
            console.log(`DEBUG: Loaded ${allDrafts.length} drafts at ${new Date().toISOString()}`);
        }

        renderDraftList();
    } catch (error) {
        console.error('Error loading drafts:', error);
        const errorMsg = error.message || 'Unknown error';
        container.innerHTML = `<div style="text-align: center; padding: 40px 20px; color: #dc3545;">
            <div style="font-size: 16px; margin-bottom: 8px;">Failed to load drafts</div>
            <div style="font-size: 13px; color: #64748b;">${errorMsg}</div>
            <button onclick="loadDrafts()" style="margin-top: 12px; padding: 8px 16px; background: #3b82f6; color: white; border: none; border-radius: 6px; cursor: pointer;">
                <i class="fas fa-sync-alt"></i> Retry
            </button>
        </div>`;
    }
}

/**
 * Render draft list table
 */
function renderDraftList() {
    const container = document.getElementById('draftListContainer');
    
    // Phase 5D-1: Filter drafts based on backend truth (draft.status, last_send_error)
    let filteredDrafts = allDrafts;
    if (currentFilter !== 'all') {
        if (currentFilter === 'ERROR') {
            // Show drafts with send errors OR validation errors
            filteredDrafts = allDrafts.filter(draft => {
                const hasSendError = draft.last_send_error != null && draft.last_send_error !== '';
                const hasValidationError = draft.status === 'DRAFT' && draft.is_valid === false;
                return hasSendError || hasValidationError;
            });
        } else {
            // Filter by status (DRAFT or SENT)
            filteredDrafts = allDrafts.filter(draft => draft.status === currentFilter);
        }
    }
    
    if (filteredDrafts.length === 0) {
        // Phase 4D.2: Improved empty state messaging
        const filterName = currentFilter === 'all' ? '' : ` ${currentFilter.toLowerCase()}`;
        container.innerHTML = `
            <div style="text-align: center; padding: 40px 20px; color: #64748b;">
                <div style="font-size: 16px; font-weight: 500; color: #475569; margin-bottom: 8px;">
                    📋 No${filterName} receipt drafts found
                </div>
                <div style="font-size: 14px; line-height: 1.6;">
                    ${currentFilter === 'all' ? 'Drafts are created when you save OCR results without sending.' : 
                      `No drafts match the ${currentFilter.toLowerCase()} filter.`}
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
                ${filteredDrafts.map(draft => {
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
    const countEl = document.getElementById('draftSelectionCount');
    const sendBtn = document.getElementById('sendSelectedDraftsBtn');
    
    if (countEl) {
        countEl.textContent = `${count} draft${count !== 1 ? 's' : ''} selected`;
    }
    if (sendBtn) {
        const disabled = count === 0;
        sendBtn.disabled = disabled;
        sendBtn.style.opacity = disabled ? '0.5' : '1';
        sendBtn.style.cursor = disabled ? 'not-allowed' : 'pointer';
    }
}

/**
 * Load draft details (including validation)
 */
async function loadDraftDetails(draftId) {
    currentDraftId = draftId;
    renderDraftList(); // Re-render to highlight selected row
    
    const container = document.getElementById('draftDetailContainer');
    if (!container) {
        console.warn('draftDetailContainer not found, skipping detail display');
        return;
    }
    container.innerHTML = '<div style="text-align: center; padding: 40px 20px; color: #64748b;">Loading details...</div>';
    
    try {
        // Find draft in current list (includes validation status)
        const draft = allDrafts.find(d => d.draft_id === draftId);
        const previewAvailable = draft ? !!getDraftPreviewSrc(draft) : false;
        const needsFullDraft = !draft || (!previewAvailable && !draft.image_data);

        if (needsFullDraft) {
            // Fetch from API if not in list or missing image_data for preview
            const draftResponse = await fetch(`/api/drafts/${draftId}`, {
                headers: getAuthHeaders(),
                cache: 'no-store'
            });
            if (!draftResponse.ok) throw new Error('Failed to load draft');
            const draftData = await draftResponse.json();
            const mergedDraft = draft
                ? { ...draftData, is_valid: draft.is_valid, validation_errors: draft.validation_errors || [] }
                : draftData;
            renderDraftDetails(mergedDraft, mergedDraft.validation_errors || []);
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
    if (!container) {
        console.warn('draftDetailContainer not found, cannot render details');
        return;
    }
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
        ${(() => {
            // Phase 5D-1.2: Use getDraftPreviewSrc (NO artifact path probing)
            const previewSrc = getDraftPreviewSrc(draft);
            if (previewSrc) {
                return `
                <div style="margin-bottom: 24px;">
                    <h4 style="font-size: 14px; font-weight: 600; color: #64748b; margin-bottom: 12px; text-transform: uppercase;">📷 Receipt Image</h4>
                    <div style="position: relative; background: #f8fafc; border-radius: 8px; padding: 12px; text-align: center;">
                        <img id="draftImage_${draft.draft_id}" 
                             src="${previewSrc}" 
                             style="width: 100%; max-width: 500px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.15); cursor: pointer;"
                             alt="Receipt Image"
                             onclick="window.open(this.src, '_blank')">
                    </div>
                </div>`;
            } else {
                return `
                <div style="margin-bottom: 24px;">
                    <h4 style="font-size: 14px; font-weight: 600; color: #64748b; margin-bottom: 12px; text-transform: uppercase;">📷 Receipt Image</h4>
                    <div style="position: relative; background: #f8fafc; border-radius: 8px; padding: 40px; text-align: center;">
                        <i class="fas fa-image" style="font-size: 48px; opacity: 0.2; color: #94a3b8;"></i>
                        <div style="color: #64748b; font-size: 14px; margin-top: 12px;">No preview available</div>
                    </div>
                </div>`;
            }
        })()}
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
 * Helper: Get staff name from ID by fetching from API
 */
async function getStaffName(location, staffId) {
    try {
        const response = await fetch(`/api/staff?location=${encodeURIComponent(location)}`, {
            headers: getAuthHeaders()
        });
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
            headers: { 
                'Content-Type': 'application/json',
                ...getAuthHeaders()
            },
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
            const detailContainer = document.getElementById('draftDetailContainer');
            if (detailContainer) {
                detailContainer.innerHTML = 
                    '<div style="text-align: center; padding: 40px 20px; color: #64748b;">Select a draft to view details</div>';
            }
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
    if (!container) {
        console.warn('draftDetailContainer not found, cannot enter edit mode');
        return;
    }
    const r = draft.receipt;
    
    // Fetch locations and staff for dropdowns
    let locationsHtml = '<option value="">Select location...</option>';
    let staffHtml = '<option value="">Select staff...</option>';
    
    try {
        const locResponse = await fetch('/api/locations', {
            headers: getAuthHeaders()
        });
        if (locResponse.ok) {
            const locData = await locResponse.json();
            const locations = locData.locations || [];
            // API returns array of location names, not objects
            locationsHtml += locations.map(locName => 
                `<option value="${locName}" ${locName === r.business_location_id ? 'selected' : ''}>${locName}</option>`
            ).join('');
        }
        
        if (r.business_location_id) {
            const staffResponse = await fetch(`/api/staff?location=${encodeURIComponent(r.business_location_id)}`, {
                headers: getAuthHeaders()
            });
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
        const response = await fetch(`/api/staff?location=${encodeURIComponent(locationId)}`, {
            headers: getAuthHeaders()
        });
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
            headers: { 
                'Content-Type': 'application/json',
                ...getAuthHeaders()
            },
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
            method: 'DELETE',
            headers: getAuthHeaders()
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
    
    // Phase 5D-2: Refresh button
    const refreshBtn = document.getElementById('refreshDraftsBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            if (window.AuthState.ready && window.AuthState.token) {
                loadDrafts();
                if (DEBUG_DRAFTS) {
                    console.log(`DEBUG: Refresh clicked at ${new Date().toISOString()}`);
                }
            }
        });
    }
    
    // Send selected button
    const sendBtn = document.getElementById('sendSelectedDraftsBtn');
    if (sendBtn) {
        sendBtn.addEventListener('click', sendSelectedDrafts);
    }
    
    // Phase 5D-2: Select All checkbox
    const selectAllCheckbox = document.getElementById('selectAllDrafts');
    if (selectAllCheckbox) {
        selectAllCheckbox.addEventListener('change', function() {
            if (this.checked) {
                // Select all visible drafts
                allDrafts.forEach(draft => {
                    if (shouldShowDraft(draft)) {
                        selectedDraftIds.add(draft.draft_id);
                    }
                });
            } else {
                selectedDraftIds.clear();
            }
            renderDraftList();
            updateSelectionCount();
        });
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

/**
 * Helper: Check if draft should be shown based on current filter
 */
function shouldShowDraft(draft) {
    if (currentFilter === 'all') return true;
    if (currentFilter === 'ERROR') {
        const hasSendError = draft.last_send_error != null && draft.last_send_error !== '';
        const hasValidationError = draft.status === 'DRAFT' && draft.is_valid === false;
        return hasSendError || hasValidationError;
    }
    return draft.status === currentFilter;
}
