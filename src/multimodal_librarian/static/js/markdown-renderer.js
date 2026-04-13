/**
 * Lightweight Markdown Renderer
 *
 * Converts common markdown patterns to HTML for chat message display.
 * Handles: bold, italic, headers, unordered/ordered lists, code blocks,
 * inline code, and line breaks.
 *
 * Does NOT use innerHTML for untrusted input — all text content is escaped.
 */
const MarkdownRenderer = (() => {
    /**
     * Escape HTML special characters to prevent XSS.
     * @param {string} text
     * @returns {string}
     */
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.appendChild(document.createTextNode(text));
        return div.innerHTML;
    }

    /**
     * Apply inline markdown formatting (bold, italic, inline code).
     * Operates on already-escaped HTML strings.
     * @param {string} escaped - HTML-escaped text
     * @returns {string} HTML string with inline formatting
     */
    function applyInlineFormatting(escaped) {
        // Inline code: `code`
        escaped = escaped.replace(/`([^`]+)`/g, '<code>$1</code>');
        // Bold+italic: ***text*** or ___text___
        escaped = escaped.replace(/\*{3}(.+?)\*{3}/g, '<strong><em>$1</em></strong>');
        // Bold: **text**
        escaped = escaped.replace(/\*{2}(.+?)\*{2}/g, '<strong>$1</strong>');
        // Italic: *text* (but not inside words like file*name)
        escaped = escaped.replace(/(^|[\s(])\*([^\s*].*?[^\s*])\*([\s).,;:!?]|$)/g, '$1<em>$2</em>$3');
        return escaped;
    }

    /**
     * Render a markdown string to an HTML string.
     * @param {string} markdown - Raw markdown text
     * @returns {string} Safe HTML string
     */
    function render(markdown) {
        if (!markdown) return '';

        const lines = markdown.split('\n');
        const htmlParts = [];
        let inCodeBlock = false;
        let codeBlockContent = [];
        let inList = false;
        let listType = null; // 'ul' or 'ol'
        let inTable = false;
        let tableRows = [];

        function closeList() {
            if (inList) {
                htmlParts.push(listType === 'ol' ? '</ol>' : '</ul>');
                inList = false;
                listType = null;
            }
        }

        function closeTable() {
            if (inTable && tableRows.length > 0) {
                htmlParts.push(renderTable(tableRows));
                tableRows = [];
                inTable = false;
            }
        }

        function renderTable(rows) {
            // Filter out separator rows (|---|---|)
            const dataRows = rows.filter(r => !r.match(/^\|[\s\-:|]+\|$/));
            if (dataRows.length === 0) return '';

            let html = '<table class="status-table">';
            dataRows.forEach((row, idx) => {
                const cells = row.split('|').filter((_, i, arr) => i > 0 && i < arr.length - 1);
                if (idx === 0) {
                    html += '<thead><tr>';
                    cells.forEach(c => { html += '<th>' + applyInlineFormatting(escapeHtml(c.trim())) + '</th>'; });
                    html += '</tr></thead><tbody>';
                } else {
                    html += '<tr>';
                    cells.forEach(c => { html += '<td>' + applyInlineFormatting(escapeHtml(c.trim())) + '</td>'; });
                    html += '</tr>';
                }
            });
            html += '</tbody></table>';
            return html;
        }

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];

            // Code block fences
            if (line.trim().startsWith('```')) {
                if (inCodeBlock) {
                    htmlParts.push('<pre><code>' + escapeHtml(codeBlockContent.join('\n')) + '</code></pre>');
                    codeBlockContent = [];
                    inCodeBlock = false;
                } else {
                    closeList();
                    inCodeBlock = true;
                }
                continue;
            }

            if (inCodeBlock) {
                codeBlockContent.push(line);
                continue;
            }

            // Blank line — close list, close table, add spacing
            if (line.trim() === '') {
                closeList();
                closeTable();
                // Don't add empty paragraphs for consecutive blank lines
                continue;
            }

            // Headers: # H1, ## H2, ### H3
            const headerMatch = line.match(/^(#{1,4})\s+(.+)$/);
            if (headerMatch) {
                closeList();
                const level = headerMatch[1].length;
                // Chat messages use h4-h6 to avoid oversized headers
                const tag = 'h' + Math.min(level + 3, 6);
                htmlParts.push('<' + tag + '>' + applyInlineFormatting(escapeHtml(headerMatch[2])) + '</' + tag + '>');
                continue;
            }

            // Unordered list: - item, * item, • item
            const ulMatch = line.match(/^(\s*)[-*•]\s+(.+)$/);
            if (ulMatch) {
                if (!inList || listType !== 'ul') {
                    closeList();
                    htmlParts.push('<ul>');
                    inList = true;
                    listType = 'ul';
                }
                htmlParts.push('<li>' + applyInlineFormatting(escapeHtml(ulMatch[2])) + '</li>');
                continue;
            }

            // Ordered list: 1. item, 2. item
            const olMatch = line.match(/^(\s*)\d+[.)]\s+(.+)$/);
            if (olMatch) {
                if (!inList || listType !== 'ol') {
                    closeList();
                    htmlParts.push('<ol>');
                    inList = true;
                    listType = 'ol';
                }
                htmlParts.push('<li>' + applyInlineFormatting(escapeHtml(olMatch[2])) + '</li>');
                continue;
            }

            // Table rows: | col1 | col2 | or |---|---|
            if (line.trim().startsWith('|') && line.trim().endsWith('|')) {
                closeList();
                inTable = true;
                tableRows.push(line.trim());
                continue;
            }

            // Regular paragraph
            closeList();
            closeTable();
            htmlParts.push('<p>' + applyInlineFormatting(escapeHtml(line)) + '</p>');
        }

        // Close any open structures
        closeList();
        closeTable();
        if (inCodeBlock) {
            htmlParts.push('<pre><code>' + escapeHtml(codeBlockContent.join('\n')) + '</code></pre>');
        }

        return htmlParts.join('\n');
    }

    return { render, escapeHtml };
})();

if (typeof window !== 'undefined') {
    window.MarkdownRenderer = MarkdownRenderer;
}
