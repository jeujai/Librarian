/**
 * Lightweight Markdown Renderer
 *
 * Converts common markdown patterns to HTML for chat message display.
 * Handles: bold, italic, headers, unordered/ordered lists, code blocks,
 * inline code, and line breaks.
 *
 * Does NOT use innerHTML for untrusted input — all text content is escaped.
 *
 * Version: 2025-06-10-v2 — multi-line list items, loose list support
 */
const MarkdownRenderer = (() => {
    console.log("[MarkdownRenderer] v2025-06-10-v3 loaded — nested list, loose list, multi-line support active");
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
        let currentListItem = []; // accumulated lines for the current <li>
        let inTable = false;
        let tableRows = [];
        let blankRun = 0; // consecutive blank lines (for loose list vs paragraph detection)

        function flushListItem() {
            if (currentListItem.length > 0) {
                const parts = currentListItem.map(line => applyInlineFormatting(escapeHtml(line)));
                htmlParts.push('<li>' + parts.join('<br>') + '</li>');
                currentListItem = [];
            }
        }

        function closeList() {
            if (inList) {
                flushListItem();
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

            // Blank line — close table, add spacing. Lists survive blank lines
            // because standard Markdown allows loose lists (blank lines between items).
            if (line.trim() === '') {
                closeTable();
                blankRun++;
                continue;
            }

            // Snapshot blank run for continuation-vs-paragraph decision,
            // then reset — every non-blank line ends a blank run.
            const blankLinesBefore = blankRun;
            blankRun = 0;

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
                    if (inList) {
                        // Inside a different list type — treat as continuation
                        // to avoid breaking the parent list (e.g., * bullets inside an ol)
                        currentListItem.push(line);
                        continue;
                    }
                    closeList();
                    htmlParts.push('<ul>');
                    inList = true;
                    listType = 'ul';
                }
                flushListItem();
                currentListItem = [ulMatch[2]];
                continue;
            }

            // Ordered list: 1. item, 2. item
            const olMatch = line.match(/^(\s*)\d+[.)]\s+(.+)$/);
            if (olMatch) {
                if (!inList || listType !== 'ol') {
                    if (inList) {
                        // Inside a different list type — treat as continuation
                        // to avoid breaking the parent list (e.g., numbered items inside a ul)
                        currentListItem.push(line);
                        continue;
                    }
                    closeList();
                    htmlParts.push('<ol>');
                    inList = true;
                    listType = 'ol';
                }
                flushListItem();
                currentListItem = [olMatch[2]];
                continue;
            }

            // Continuation line inside a list item (text after the numbered/bullet line)
            if (inList) {
                // Two or more blank lines before this line → standalone paragraph, close list
                if (blankLinesBefore >= 2) {
                    closeList();
                    htmlParts.push('<p>' + applyInlineFormatting(escapeHtml(line)) + '</p>');
                    continue;
                }
                // After a blank line, a non-indented line that starts a new
                // standalone paragraph pattern (bold header or non-continuation)
                // is NOT a list continuation. This handles LLM output where
                // closing paragraphs follow a numbered list with a single blank
                // line separator.
                if (blankLinesBefore >= 1 && line.trim() !== '') {
                    const isIndented = line[0] === ' ' || line[0] === '\t';
                    const isBoldHeader = /^\*\*[^*]+\*\*/.test(line.trim());
                    // Not indented → new paragraph per CommonMark spec.
                    // Bold header after a list → standalone paragraph (LLM pattern).
                    if (!isIndented || isBoldHeader) {
                        closeList();
                        htmlParts.push('<p>' + applyInlineFormatting(escapeHtml(line)) + '</p>');
                        continue;
                    }
                }
                currentListItem.push(line);
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
