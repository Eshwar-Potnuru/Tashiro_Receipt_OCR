/**
 * Security utilities for XSS prevention.
 * Include this script before other scripts that use innerHTML.
 */

/**
 * Escape HTML entities to prevent XSS attacks.
 * Use this when inserting user-provided data into innerHTML.
 * 
 * @param {string} str - The string to escape
 * @returns {string} - The escaped string safe for innerHTML
 */
function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    if (typeof str !== 'string') str = String(str);
    
    const htmlEntities = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
        '/': '&#x2F;',
        '`': '&#x60;',
        '=': '&#x3D;'
    };
    
    return str.replace(/[&<>"'`=\/]/g, char => htmlEntities[char]);
}

/**
 * Safely set element text content (recommended over innerHTML for plain text).
 * 
 * @param {HTMLElement|string} element - Element or selector
 * @param {string} text - Text to set
 */
function safeSetText(element, text) {
    const el = typeof element === 'string' ? document.querySelector(element) : element;
    if (el) {
        el.textContent = text;
    }
}

/**
 * Create a safe HTML string from a template literal.
 * Automatically escapes interpolated values.
 * 
 * Usage:
 *   const html = safeHtml`<div class="item">${userInput}</div>`;
 * 
 * @param {TemplateStringsArray} strings - Template literal strings
 * @param {...any} values - Interpolated values (will be escaped)
 * @returns {string} - Safe HTML string
 */
function safeHtml(strings, ...values) {
    return strings.reduce((result, str, i) => {
        const value = values[i - 1];
        const escaped = value !== undefined ? escapeHtml(value) : '';
        return result + escaped + str;
    });
}

// Make functions globally available
window.escapeHtml = escapeHtml;
window.safeSetText = safeSetText;
window.safeHtml = safeHtml;
