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
// i18n: Draft module translations
// ============================================================================
const draftsI18n = {
    // Draft list table headers
    th_vendor:         { en: 'Vendor',  ja: '取引先' },
    th_amount:         { en: 'Amount',  ja: '金額' },
    th_date:           { en: 'Date',    ja: '日付' },
    th_status:         { en: 'Status',  ja: 'ステータス' },

    // Validation tooltips
    ready_to_send:     { en: 'Ready to send', ja: '送信可能' },
    incomplete_fields: { en: 'Incomplete - missing required fields', ja: '未完了 — 必須項目が不足' },

    // Empty states
    no_drafts:         { en: 'No{filter} receipt drafts found', ja: '{filter}レシート下書きはありません' },
    empty_hint_all:    { en: 'Drafts are created when you save OCR results without sending.', ja: 'OCR結果を送信せずに保存すると下書きが作成されます。' },
    empty_hint_filter: { en: 'No drafts match the {filter} filter.', ja: '{filter}フィルターに一致する下書きはありません。' },

    // Selection
    drafts_selected:   { en: '{count} draft(s) selected', ja: '{count}件選択中' },

    // Detail panel
    receipt_info:      { en: 'Receipt Information', ja: 'レシート情報' },
    vendor_name:       { en: 'Vendor Name', ja: '取引先名' },
    date:              { en: 'Date', ja: '日付' },
    total_amount:      { en: 'Total Amount', ja: '合計金額' },
    tax_10:            { en: 'Tax (10%)', ja: '税額（10%）' },
    tax_8:             { en: 'Tax (8%)', ja: '税額（8%）' },
    invoice_number:    { en: 'Invoice Number', ja: '請求書番号' },
    location_staff:    { en: 'Location & Staff', ja: '事業所 & 担当者' },
    business_location: { en: 'Business Location', ja: '事業所' },
    staff_member:      { en: 'Staff Member', ja: '担当者' },
    draft_metadata:    { en: '📋 Draft Metadata', ja: '📋 下書きメタデータ' },
    status:            { en: 'Status', ja: 'ステータス' },
    draft_id:          { en: 'Draft ID', ja: '下書きID' },
    created_at:        { en: 'Created At', ja: '作成日時' },
    last_updated:      { en: 'Last Updated', ja: '最終更新' },
    sent_at:           { en: 'Sent At', ja: '送信日時' },
    image_ref:         { en: 'Image Reference', ja: '画像参照' },

    // Sent status banner
    sent_to_excel:     { en: '✅ Sent to Excel', ja: '✅ Excel送信済み' },
    sent_success_msg:  { en: 'This receipt has been successfully sent to HQ', ja: 'このレシートはHQに正常に送信されました' },
    sent_at_label:     { en: 'Sent at:', ja: '送信日時:' },

    // Validation errors
    validation_errors: { en: 'Validation Errors', ja: '検証エラー' },
    cannot_send_yet:   { en: '⚠️ This draft cannot be sent yet', ja: '⚠️ この下書きはまだ送信できません' },
    fix_errors:        { en: 'Fix the errors below before sending to HQ', ja: 'HQに送信する前に以下のエラーを修正してください' },

    // Receipt image
    receipt_image:     { en: '📷 Receipt Image', ja: '📷 レシート画像' },
    no_preview:        { en: 'No preview available', ja: 'プレビューなし' },

    // Action buttons
    edit_draft:        { en: 'Edit Draft', ja: '下書き編集' },
    delete_btn:        { en: 'Delete', ja: '削除' },

    // Edit mode
    editing_draft:     { en: '✏️ Editing Draft', ja: '✏️ 下書き編集中' },
    edit_hint:         { en: 'Make changes and click Save to update the draft', ja: '変更してから保存ボタンをクリックしてください' },
    total_amount_yen:  { en: 'Total Amount (¥)', ja: '合計金額（¥）' },
    tax_10_yen:        { en: 'Tax 10% (¥)', ja: '税額10%（¥）' },
    tax_8_yen:         { en: 'Tax 8% (¥)', ja: '税額8%（¥）' },
    cancel:            { en: 'Cancel', ja: 'キャンセル' },
    save_changes:      { en: '💾 Save Changes', ja: '💾 変更を保存' },
    select_location:   { en: 'Select location...', ja: '事業所を選択...' },
    select_staff:      { en: 'Select staff...', ja: '担当者を選択...' },
    loading:           { en: 'Loading...', ja: '読込中...' },
    error_load_staff:  { en: 'Error loading staff', ja: '担当者の読込失敗' },

    // Save/delete messages
    draft_updated:     { en: '✅ Draft updated successfully!', ja: '✅ 下書きを更新しました！' },
    save_failed:       { en: '❌ Failed to save changes: ', ja: '❌ 保存に失敗: ' },
    delete_confirm:    { en: '⚠️ Delete draft "{name}"?\n\nThis action cannot be undone.', ja: '⚠️ 下書き「{name}」を削除しますか？\n\nこの操作は元に戻せません。' },
    draft_deleted:     { en: '✅ Draft deleted successfully', ja: '✅ 下書きを削除しました' },
    delete_failed:     { en: '❌ Failed to delete draft: ', ja: '❌ 削除に失敗: ' },
    select_to_view:    { en: 'Select a draft to view details', ja: '下書きを選択して詳細を表示' },

    // Send flow
    send_incomplete:   { en: '⚠️ Cannot send incomplete drafts!\n\nLocation and Staff are required fields.\n\nIncomplete drafts ({count}):\n{list}\n\nPlease edit these drafts to add Location and Staff before sending.', ja: '⚠️ 不完全な下書きは送信できません！\n\n事業所と担当者は必須項目です。\n\n不完全な下書き（{count}件）:\n{list}\n\n送信前に事業所と担当者を追加してください。' },
    missing_location:  { en: 'Location', ja: '事業所' },
    missing_staff:     { en: 'Staff', ja: '担当者' },
    send_confirm_one:  { en: 'Send this receipt to HQ? This action cannot be undone.', ja: 'このレシートをHQに送信しますか？この操作は元に戻せません。' },
    send_confirm_many: { en: 'Send {count} receipts to HQ? This action cannot be undone.', ja: '{count}件のレシートをHQに送信しますか？この操作は元に戻せません。' },
    sending:           { en: 'Sending...', ja: '送信中...' },
    send:              { en: 'Send', ja: '送信' },
    send_failed:       { en: 'Failed to send drafts. Please try again.', ja: '送信に失敗しました。再試行してください。' },
    precheck_failed:   { en: 'Failed to run duplicate precheck. Please try again.', ja: '重複チェックに失敗しました。再試行してください。' },

    // Send results
    send_completed:    { en: 'Send completed:', ja: '送信完了:' },
    sent_count:        { en: '✓ Sent: {count}', ja: '✓ 送信: {count}件' },
    failed_count:      { en: '✗ Failed: {count}', ja: '✗ 失敗: {count}件' },
    duplicate_warn:    { en: '⚠ Possible duplicate detected. Please verify (Invoice/Date/Total).', ja: '⚠ 重複の可能性があります。請求書番号/日付/合計を確認してください。' },
    reasons:           { en: 'Reasons: ', ja: '理由: ' },
    tax_warning:       { en: '⚠ Tax Warning: Please verify tax calculations.', ja: '⚠ 税額警告: 税額計算を確認してください。' },
    issue:             { en: 'Issue: ', ja: '問題: ' },

    // Duplicate precheck
    dup_detected:      { en: '⚠ Duplicate candidate(s) detected before send.', ja: '⚠ 送信前に重複候補が検出されました。' },
    dup_review:        { en: 'Please review and choose:', ja: '確認して選択してください:' },
    dup_ok:            { en: '- OK = Continue sending to Excel', ja: '- OK = Excelへ送信を続行' },
    dup_cancel:        { en: '- Cancel = Return to draft menu', ja: '- キャンセル = 下書きメニューに戻る' },
    dup_more:          { en: '...and {count} more receipt(s).', ja: '...他{count}件のレシート。' },
    dup_continue:      { en: 'Continue with send?', ja: '送信を続行しますか？' },

    // Auth / loading
    initializing:      { en: 'Initializing...', ja: '初期化中...' },
    not_logged_in:     { en: 'Not logged in', ja: '未ログイン' },
    please_login:      { en: 'Please log in to view drafts.', ja: 'ログインして下書きを表示してください。' },
    logged_in_as:      { en: 'Logged in as: {name} ({role})', ja: 'ログイン中: {name}（{role}）' },
    session_expired:   { en: 'Session expired', ja: 'セッション期限切れ' },
    please_login_again:{ en: 'Please log in again to view drafts.', ja: '再ログインして下書きを表示してください。' },
    loading_drafts:    { en: 'Loading drafts...', ja: '下書きを読込中...' },
    failed_load_drafts:{ en: 'Failed to load drafts', ja: '下書きの読込に失敗' },
    retry:             { en: 'Retry', ja: '再試行' },
    loading_details:   { en: 'Loading details...', ja: '詳細を読込中...' },
    failed_load_details:{ en: 'Failed to load details.', ja: '詳細の読込に失敗しました。' },
    staff_loc_mismatch:{ en: '❌ Staff/Location mismatch. Please reselect staff and location, then send again.', ja: '❌ 担当者/事業所の不一致。担当者と事業所を再選択して送信してください。' },
};

function getDraftsLanguage() {
    if (typeof window !== 'undefined' && typeof window.currentLanguage === 'string' && window.currentLanguage) {
        return window.currentLanguage;
    }

    const langSelectEl = document.getElementById('languageSelect');
    const selectLang = langSelectEl ? langSelectEl.value : null;
    if (selectLang) {
        return selectLang;
    }

    const appLang = localStorage.getItem('appLang');
    if (appLang) {
        return appLang;
    }

    try {
        const settings = JSON.parse(localStorage.getItem('tashiro_settings') || '{}');
        if (settings.language) {
            return settings.language;
        }
    } catch (e) {
        // ignore settings parse errors
    }

    return 'ja';
}

function dt(key, params) {
    const lang = getDraftsLanguage();
    let text = (draftsI18n[key] && draftsI18n[key][lang]) || key;
    if (params) {
        Object.keys(params).forEach(k => {
            text = text.replace(new RegExp('\\{' + k + '\\}', 'g'), params[k]);
        });
    }
    return text;
}

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
        container.innerHTML = '<div style="text-align: center; padding: 40px 20px; color: #64748b;">' + dt('initializing') + '</div>';
        
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
            <div style="font-size: 16px; margin-bottom: 8px;">${dt('not_logged_in')}</div>
            <div style="font-size: 13px; color: #64748b;">${dt('please_login')}</div>
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
            '<div style="text-align: center; padding: 40px 20px; color: #64748b;">' + dt('select_to_view') + '</div>';
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
        userIndicator.textContent = dt('logged_in_as', { name: displayName, role: role });
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
            <div style="font-size: 16px; margin-bottom: 8px;">${dt('session_expired')}</div>
            <div style="font-size: 13px; color: #64748b;">${dt('please_login_again')}</div>
        </div>`;
        return;
    }
    
    try {
        container.innerHTML = `<div style="text-align: center; padding: 40px 20px; color: #64748b;">${dt('loading_drafts')}</div>`;
        
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
                <div style="font-size: 16px; margin-bottom: 8px;">${dt('session_expired')}</div>
                <div style="font-size: 13px; color: #64748b;">${dt('please_login_again')}</div>
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
            <div style="font-size: 16px; margin-bottom: 8px;">${dt('failed_load_drafts')}</div>
            <div style="font-size: 13px; color: #64748b;">${errorMsg}</div>
            <button onclick="loadDrafts()" style="margin-top: 12px; padding: 8px 16px; background: #3b82f6; color: white; border: none; border-radius: 6px; cursor: pointer;">
                <i class="fas fa-sync-alt"></i> ${dt('retry')}
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
                    ${dt('no_drafts', {filter: filterName})}
                </div>
                <div style="font-size: 14px; line-height: 1.6;">
                    ${currentFilter === 'all' ? dt('empty_hint_all') : 
                      dt('empty_hint_filter', {filter: currentFilter.toLowerCase()})}
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
                    <th style="padding: 12px 8px; text-align: left; font-weight: 600; color: #64748b;">${dt('th_vendor')}</th>
                    <th style="padding: 12px 8px; text-align: right; font-weight: 600; color: #64748b;">${dt('th_amount')}</th>
                    <th style="padding: 12px 8px; text-align: center; font-weight: 600; color: #64748b;">${dt('th_date')}</th>
                    <th style="padding: 12px 8px; text-align: center; font-weight: 600; color: #64748b;">${dt('th_status')}</th>
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
                            <td style="padding: 12px 8px; text-align: center; font-size: 16px;" title="${isValid ? dt('ready_to_send') : dt('incomplete_fields')}">
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
        countEl.textContent = dt('drafts_selected', { count: count });
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
    container.innerHTML = '<div style="text-align: center; padding: 40px 20px; color: #64748b;">' + dt('loading_details') + '</div>';
    
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
        container.innerHTML = '<div style="text-align: center; padding: 40px 20px; color: #dc3545;">' + dt('failed_load_details') + '</div>';
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
                <i class="fas fa-edit"></i> ${dt('edit_draft')}
            </button>
            <button onclick="confirmDeleteDraft('${draft.draft_id}')" 
                    style="padding: 10px 20px; background: #dc3545; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 14px;">
                <i class="fas fa-trash"></i> ${dt('delete_btn')}
            </button>
        </div>
    ` : '';
    
    const detailsHtml = `
        ${actionButtons}
        
        <!-- Receipt Information -->
        <div style="margin-bottom: 24px;">
            <h4 style="font-size: 14px; font-weight: 600; color: #64748b; margin-bottom: 12px; text-transform: uppercase;">${dt('receipt_info')}</h4>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                ${renderField(dt('vendor_name'), r.vendor_name || 'N/A')}
                ${renderField(dt('date'), r.receipt_date || 'N/A')}
                ${renderField(dt('total_amount'), `¥${formatAmount(r.total_amount)}`)}
                ${renderField(dt('tax_10'), `¥${formatAmount(r.tax_10_amount || 0)}`)}
                ${renderField(dt('tax_8'), `¥${formatAmount(r.tax_8_amount || 0)}`)}
                ${renderField(dt('invoice_number'), r.invoice_number || 'N/A')}
            </div>
        </div>
        
        <!-- Location & Staff -->
        <div style="margin-bottom: 24px;">
            <h4 style="font-size: 14px; font-weight: 600; color: #64748b; margin-bottom: 12px; text-transform: uppercase;">${dt('location_staff')}</h4>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                ${renderField(dt('business_location'), r.business_location_id || 'N/A')}
                ${renderField(dt('staff_member'), staffDisplay)}
            </div>
        </div>
        
        <!-- Phase 4F.5: Draft Metadata -->
        <div style="margin-bottom: 24px;">
            <h4 style="font-size: 14px; font-weight: 600; color: #64748b; margin-bottom: 12px; text-transform: uppercase;">${dt('draft_metadata')}</h4>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                <div>
                    <div style="font-size: 12px; color: #64748b; margin-bottom: 4px;">${dt('status')}</div>
                    <span style="padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: 600; display: inline-block;
                                 background: ${draft.status === 'SENT' ? '#d1fae5' : '#fef3c7'}; 
                                 color: ${draft.status === 'SENT' ? '#065f46' : '#92400e'};">
                        ${draft.status}
                    </span>
                </div>
                ${renderField(dt('draft_id'), draft.draft_id.substring(0, 8) + '...')}
                ${renderField(dt('created_at'), formatDateTime(draft.created_at))}
                ${renderField(dt('last_updated'), formatDateTime(draft.updated_at))}
                ${draft.sent_at ? renderField(dt('sent_at'), formatDateTime(draft.sent_at)) : ''}
                ${draft.image_ref ? renderField(dt('image_ref'), draft.image_ref.substring(0, 12) + '...') : ''}
            </div>
        </div>
        
        <!-- Status Message for SENT drafts or Validation Errors for DRAFT -->
        ${draft.status === 'SENT' ? `
        <div style="margin-bottom: 24px;">
            <div style="background: #d1fae5; border-left: 4px solid #10b981; border-radius: 4px; padding: 16px; text-align: center;">
                <div style="font-weight: 600; color: #065f46; font-size: 16px; margin-bottom: 4px;">${dt('sent_to_excel')}</div>
                <div style="font-size: 13px; color: #047857;">${dt('sent_success_msg')}</div>
                ${draft.sent_at ? `<div style="font-size: 12px; color: #059669; margin-top: 8px;">${dt('sent_at_label')} ${formatDateTime(draft.sent_at)}</div>` : ''}
            </div>
        </div>
        ` : validationErrors.length > 0 ? `
        <div id="validationErrorsSection" style="margin-bottom: 24px;">
            <h4 style="font-size: 14px; font-weight: 600; color: #dc3545; margin-bottom: 8px; text-transform: uppercase;">${dt('validation_errors')}</h4>
            <div style="background: #fee; border-left: 4px solid #dc3545; border-radius: 4px; padding: 12px 16px; margin-bottom: 12px;">
                <div style="font-weight: 600; color: #991b1b; font-size: 13px;">${dt('cannot_send_yet')}</div>
                <div style="font-size: 12px; color: #7f1d1d; margin-top: 4px;">${dt('fix_errors')}</div>
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
                    <h4 style="font-size: 14px; font-weight: 600; color: #64748b; margin-bottom: 12px; text-transform: uppercase;">${dt('receipt_image')}</h4>
                    <div style="position: relative; background: #f8fafc; border-radius: 8px; padding: 12px; text-align: center;">
                        <img id="draftImage_${draft.draft_id}" 
                             src="${previewSrc}" 
                             style="width: 100%; max-width: 500px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.15); cursor: pointer;"
                             alt="${dt('receipt_image')}"
                             onclick="window.open(this.src, '_blank')">
                    </div>
                </div>`;
            } else {
                return `
                <div style="margin-bottom: 24px;">
                    <h4 style="font-size: 14px; font-weight: 600; color: #64748b; margin-bottom: 12px; text-transform: uppercase;">${dt('receipt_image')}</h4>
                    <div style="position: relative; background: #f8fafc; border-radius: 8px; padding: 40px; text-align: center;">
                        <i class="fas fa-image" style="font-size: 48px; opacity: 0.2; color: #94a3b8;"></i>
                        <div style="color: #64748b; font-size: 14px; margin-top: 12px;">${dt('no_preview')}</div>
                    </div>
                </div>`;
            }
        })()}
    `;
    
    container.innerHTML = detailsHtml;
    
    // Phase 4D.2: Auto-scroll to validation errors if they exist
    if (validationErrors.length > 0) {
        requestAnimationFrame(() => {
            const errorSection = document.getElementById('validationErrorsSection');
            if (!errorSection) return;

            const rect = errorSection.getBoundingClientRect();
            const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
            const isVisible = rect.top >= 0 && rect.bottom <= viewportHeight;
            if (!isVisible) {
                errorSection.scrollIntoView({ behavior: 'auto', block: 'start' });
            }
        });
    }
}

/**
 * Helper: Get staff name from ID by fetching from API
 */
async function getStaffName(location, staffId) {
    if (!location || String(location).startsWith('INVALID_')) {
        return null;
    }
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
            `• ${d.receipt.vendor_name || 'Unknown'} - Missing: ${!d.receipt.business_location_id ? dt('missing_location') : ''} ${!d.receipt.staff_id ? dt('missing_staff') : ''}`
        ).join('\n');
        
        alert(dt('send_incomplete', {count: invalidDrafts.length, list: invalidList}));
        return;
    }
    
    const draftIds = Array.from(selectedDraftIds);

    // Pre-send duplicate warning check (warning-only, no Excel write)
    let precheckResult = null;
    try {
        const precheckResponse = await fetch('/api/drafts/send/precheck', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...getAuthHeaders()
            },
            body: JSON.stringify({ draft_ids: draftIds })
        });

        if (!precheckResponse.ok) {
            const err = await precheckResponse.json().catch(() => ({}));
            const detail = err && err.detail ? err.detail : {};
            const message = (typeof detail === 'string' ? detail : detail.message) || 'Failed to run duplicate precheck';
            throw new Error(message);
        }

        precheckResult = await precheckResponse.json();
    } catch (error) {
        console.error('Duplicate precheck error:', error);
        alert(dt('precheck_failed'));
        return;
    }

    if (precheckResult && precheckResult.has_duplicates) {
        const warningMessage = buildDuplicatePrecheckMessage(precheckResult);
        const continueSend = confirm(warningMessage);
        if (!continueSend) {
            return;
        }
    }

    // Phase 4D.2: Send confirmation dialog
    const count = selectedDraftIds.size;
    const confirmMessage = count === 1 
        ? dt('send_confirm_one')
        : dt('send_confirm_many', {count});
    
    if (!confirm(confirmMessage)) {
        return; // User cancelled
    }
    
    const btn = document.getElementById('sendSelectedDraftsBtn');
    
    // Phase 4D.2: Set sending state and disable UI
    isSending = true;
    btn.disabled = true;
    btn.textContent = dt('sending');
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

        const duplicateWarningHeader = (response.headers.get('X-Duplicate-Warning') || 'false').toLowerCase() === 'true';
        const taxMismatchWarningHeader = (response.headers.get('X-Tax-Mismatch-Warning') || 'false').toLowerCase() === 'true';
        
        if (!response.ok) {
            let errorPayload = {};
            try {
                errorPayload = await response.json();
            } catch (e) {
                errorPayload = {};
            }

            const detail = errorPayload && errorPayload.detail ? errorPayload.detail : {};
            const errorCode = errorPayload.error_code || detail.error_code;

            if (errorCode === 'STAFF_LOCATION_MISMATCH') {
                alert(dt('staff_loc_mismatch'));
                return;
            }

            const detailMessage =
                (typeof detail === 'string' ? detail : detail.message) ||
                errorPayload.message ||
                'Send request failed';
            throw new Error(detailMessage);
        }
        
        const result = await response.json();
        
        // Show result summary
        showSendResults(result, duplicateWarningHeader, taxMismatchWarningHeader);
        
        // Refresh draft list
        selectedDraftIds.clear();
        await loadDrafts();
        
        // Clear detail panel if current draft was sent
        if (currentDraftId && draftIds.includes(currentDraftId)) {
            currentDraftId = null;
            const detailContainer = document.getElementById('draftDetailContainer');
            if (detailContainer) {
                detailContainer.innerHTML = 
                    `<div style="text-align: center; padding: 40px 20px; color: #64748b;">${dt('select_to_view')}</div>`;
            }
        }
        
    } catch (error) {
        console.error('Send error:', error);
        alert(dt('send_failed'));
    } finally {
        // Phase 4D.2: Re-enable UI
        isSending = false;
        btn.disabled = false;
        btn.textContent = dt('send');
        renderDraftList(); // Re-render to re-enable interactions
    }
}

function buildDuplicatePrecheckMessage(precheckResult) {
    const byDraft = Array.isArray(precheckResult.by_draft) ? precheckResult.by_draft : [];
    const lines = [];
    lines.push(dt('dup_detected'));
    lines.push(dt('dup_review'));
    lines.push(dt('dup_ok'));
    lines.push(dt('dup_cancel'));
    lines.push('');

    byDraft.slice(0, 6).forEach((entry, index) => {
        const vendor = entry.vendor_name || 'Unknown vendor';
        const invoice = entry.invoice_number || 'N/A';
        const receiptDate = entry.receipt_date || 'N/A';
        lines.push(`${index + 1}) ${vendor} | Invoice: ${invoice} | Date: ${receiptDate}`);

        const matches = Array.isArray(entry.matches) ? entry.matches : [];
        matches.slice(0, 3).forEach(match => {
            const reason = match.reason || 'possible duplicate';
            const matchedInvoice = match.matched_invoice_number || 'N/A';
            const matchedVendor = match.matched_vendor_name || 'Unknown vendor';
            const matchedDate = match.matched_receipt_date || 'N/A';
            lines.push(`   • ${reason} -> ${matchedVendor} | Inv: ${matchedInvoice} | Date: ${matchedDate}`);
        });
        lines.push('');
    });

    if (byDraft.length > 6) {
        lines.push(dt('dup_more', {count: byDraft.length - 6}));
        lines.push('');
    }

    lines.push(dt('dup_continue'));
    return lines.join('\n');
}

/**
 * Show send results in alert/notification
 */
function showSendResults(result, hasDuplicateWarning = false, hasTaxMismatchWarning = false) {
    const successCount = result.sent || 0;
    const failedCount = result.failed || 0;
    const duplicateMatches = (result.warnings && Array.isArray(result.warnings.duplicates))
        ? result.warnings.duplicates
        : [];
    const taxMismatchItems = (result.warnings && result.warnings.tax_mismatch && Array.isArray(result.warnings.tax_mismatch.items))
        ? result.warnings.tax_mismatch.items
        : [];
    
    let message = `${dt('send_completed')}\n`;
    message += `${dt('sent_count', {count: successCount})}\n`;
    message += `${dt('failed_count', {count: failedCount})}\n\n`;

    if (duplicateMatches.length > 0 || hasDuplicateWarning) {
        message += `${dt('duplicate_warn')}\n`;

        if (duplicateMatches.length > 0) {
            const reasons = [...new Set(
                duplicateMatches
                    .map(match => match.reason)
                    .filter(reason => typeof reason === 'string' && reason.trim().length > 0)
            )].slice(0, 2);

            if (reasons.length > 0) {
                message += `${dt('reasons')}${reasons.join('; ')}\n`;
            }
        }

        message += `\n`;
    }

    if (taxMismatchItems.length > 0 || hasTaxMismatchWarning) {
        message += `${dt('tax_warning')}\n`;

        if (taxMismatchItems.length > 0) {
            const firstMismatch = taxMismatchItems[0];
            
            // New format: detailed error messages
            if (firstMismatch.rule && firstMismatch.notes) {
                message += `${dt('issue')}${firstMismatch.notes}\n`;
                
                if (firstMismatch.total_yen && firstMismatch.total_tax_yen) {
                    message += `Total: ¥${firstMismatch.total_yen}, Taxes: ¥${firstMismatch.total_tax_yen}`;
                    if (firstMismatch.implied_subtotal_yen !== undefined) {
                        message += `, Subtotal: ¥${firstMismatch.implied_subtotal_yen}`;
                    }
                    message += `\n`;
                }
                
                if (firstMismatch.effective_tax_rate_pct !== undefined) {
                    message += `Effective tax rate: ${firstMismatch.effective_tax_rate_pct}% (expected: 7-11%)\n`;
                }
            }
            // Legacy format fallback (for old data)
            else if (
                typeof firstMismatch.total_yen === 'number' &&
                typeof firstMismatch.computed_yen === 'number' &&
                typeof firstMismatch.diff_yen === 'number'
            ) {
                message += `Tax check: total=${firstMismatch.total_yen}, computed=${firstMismatch.computed_yen}, diff=${firstMismatch.diff_yen}.\n`;
            }
        }

        message += `\n`;
    }
    
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
    let locationsHtml = `<option value="">${dt('select_location')}</option>`;
    let staffHtml = `<option value="">${dt('select_staff')}</option>`;
    
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
            <h4 style="font-size: 16px; font-weight: 600; color: #1e293b; margin-bottom: 8px;">${dt('editing_draft')}</h4>
            <p style="font-size: 13px; color: #64748b;">${dt('edit_hint')}</p>
        </div>
        
        <form id="editDraftForm" style="display: grid; gap: 16px;">
            <div>
                  <label for="edit_vendor" style="display: block; font-size: 13px; font-weight: 600; color: #475569; margin-bottom: 6px;">${dt('vendor_name')}</label>
                <input type="text" id="edit_vendor" value="${escapeHtml(r.vendor_name || '')}" 
                       style="width: 100%; padding: 10px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 14px;">
            </div>
            
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                <div>
                          <label for="edit_date" style="display: block; font-size: 13px; font-weight: 600; color: #475569; margin-bottom: 6px;">${dt('date')}</label>
                    <input type="date" id="edit_date" value="${r.receipt_date || ''}" 
                           style="width: 100%; padding: 10px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 14px;">
                </div>
                <div>
                          <label for="edit_total" style="display: block; font-size: 13px; font-weight: 600; color: #475569; margin-bottom: 6px;">${dt('total_amount_yen')}</label>
                    <input type="number" step="0.01" id="edit_total" value="${r.total_amount || 0}" 
                           style="width: 100%; padding: 10px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 14px;">
                </div>
            </div>
            
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                <div>
                          <label for="edit_tax10" style="display: block; font-size: 13px; font-weight: 600; color: #475569; margin-bottom: 6px;">${dt('tax_10_yen')}</label>
                    <input type="number" step="0.01" id="edit_tax10" value="${r.tax_10_amount || 0}" 
                           style="width: 100%; padding: 10px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 14px;">
                </div>
                <div>
                          <label for="edit_tax8" style="display: block; font-size: 13px; font-weight: 600; color: #475569; margin-bottom: 6px;">${dt('tax_8_yen')}</label>
                    <input type="number" step="0.01" id="edit_tax8" value="${r.tax_8_amount || 0}" 
                           style="width: 100%; padding: 10px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 14px;">
                </div>
            </div>
            
            <div>
                  <label for="edit_invoice" style="display: block; font-size: 13px; font-weight: 600; color: #475569; margin-bottom: 6px;">${dt('invoice_number')}</label>
                <input type="text" id="edit_invoice" value="${escapeHtml(r.invoice_number || '')}" 
                       style="width: 100%; padding: 10px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 14px;">
            </div>
            
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                <div>
                    <label for="edit_location" style="display: block; font-size: 13px; font-weight: 600; color: #475569; margin-bottom: 6px;">${dt('business_location')}</label>
                    <select id="edit_location" onchange="loadStaffForEdit(this.value)" 
                            style="width: 100%; padding: 10px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 14px;">
                        ${locationsHtml}
                    </select>
                </div>
                <div>
                    <label for="edit_staff" style="display: block; font-size: 13px; font-weight: 600; color: #475569; margin-bottom: 6px;">${dt('staff_member')}</label>
                    <select id="edit_staff" 
                            style="width: 100%; padding: 10px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 14px;">
                        ${staffHtml}
                    </select>
                </div>
            </div>
            
            <div style="display: flex; gap: 12px; justify-content: flex-end; margin-top: 12px;">
                <button type="button" onclick="cancelEdit('${draftId}')" 
                        style="padding: 10px 24px; background: white; color: #64748b; border: 1px solid #cbd5e1; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 14px;">
                    ${dt('cancel')}
                </button>
                <button type="button" onclick="saveDraftEdit('${draftId}')" 
                        style="padding: 10px 24px; background: var(--primary-blue, #3b82f6); color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 14px;">
                    ${dt('save_changes')}
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
    
    staffSelect.innerHTML = `<option value="">${dt('loading')}</option>`;
    
    try {
        const response = await fetch(`/api/staff?location=${encodeURIComponent(locationId)}`, {
            headers: getAuthHeaders()
        });
        if (!response.ok) throw new Error('Failed to load staff');
        
        const data = await response.json();
        const staffList = data.staff || [];
        
        staffSelect.innerHTML = `<option value="">${dt('select_staff')}</option>` +
            staffList.map(staff => `<option value="${staff.id}">${staff.name}</option>`).join('');
    } catch (error) {
        console.error('Error loading staff:', error);
        staffSelect.innerHTML = `<option value="">${dt('error_load_staff')}</option>`;
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
        
        alert(dt('draft_updated'));
    } catch (error) {
        console.error('Error saving draft:', error);
        alert(dt('save_failed') + error.message);
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
    
    if (!confirm(dt('delete_confirm', {name: vendorName}))) {
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
            `<div style="text-align: center; padding: 40px 20px; color: #64748b;">${dt('select_to_view')}</div>`;
        
        alert(dt('draft_deleted'));
    } catch (error) {
        console.error('Error deleting draft:', error);
        alert(dt('delete_failed') + error.message);
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

    window.addEventListener('app-language-changed', () => {
        const draftModal = document.getElementById('draftModal');
        if (draftModal && draftModal.style.display === 'block') {
            renderDraftList();
            updateSelectionCount();
            displayCurrentUser();
            if (currentDraftId) {
                loadDraftDetails(currentDraftId);
            }
        }
    });
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
