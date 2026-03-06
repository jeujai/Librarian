/**
 * UploadedFilesPanel - Displays already-uploaded documents near the upload controls.
 *
 * Shows filenames with processing status badges. Truncates to the first 10
 * entries with a "+N more" indicator when the list exceeds the threshold.
 * Provides updateDocuments() for bulk refresh and addDocument() for
 * incremental updates after a successful upload.
 */
class UploadedFilesPanel {
    /**
     * @param {HTMLElement} containerElement - DOM element to render the panel into
     */
    constructor(containerElement) {
        /** @type {HTMLElement} */
        this.container = containerElement;
        /** @type {Object[]} Document objects from the API */
        this.documents = [];
        /** @type {number} Maximum entries to display before truncating */
        this.maxVisible = 10;
    }

    /**
     * Replace the full document list and re-render.
     * @param {Object[]} documents - Array of document objects from the API
     */
    updateDocuments(documents) {
        this.documents = documents || [];
        this._render();
    }

    /**
     * Prepend a single document after a successful upload and re-render.
     * @param {Object} document - Document metadata from the server response
     */
    addDocument(document) {
        if (document) {
            this.documents.unshift(document);
        }
        this._render();
    }

    /**
     * Escape HTML special characters to prevent XSS.
     * @param {string} text
     * @returns {string}
     * @private
     */
    _escapeHtml(text) {
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(text));
        return div.innerHTML;
    }

    /**
     * Map a document status to a display label.
     * @param {string} status - One of "uploaded", "processing", "completed", "failed"
     * @returns {string}
     * @private
     */
    _statusLabel(status) {
        switch (status) {
            case 'completed': return 'Completed';
            case 'processing': return 'Processing';
            case 'failed': return 'Failed';
            case 'uploaded': return 'Processing';
            default: return 'Processing';
        }
    }

    /**
     * Map a document status to the CSS modifier class.
     * @param {string} status
     * @returns {string} CSS class suffix (e.g. "completed", "processing", "failed")
     * @private
     */
    _statusClass(status) {
        switch (status) {
            case 'completed': return 'completed';
            case 'processing': return 'processing';
            case 'failed': return 'failed';
            case 'uploaded': return 'processing';
            default: return 'processing';
        }
    }

    /**
     * Render the panel HTML with document entries, truncation indicator, or empty state.
     * @private
     */
    _render() {
        var total = this.documents.length;

        // Empty state
        if (total === 0) {
            this.container.innerHTML =
                '<div class="uploaded-files-panel">' +
                '<p class="uploaded-files-empty">No documents uploaded yet</p>' +
                '</div>';
            return;
        }

        // Build visible entries (up to maxVisible)
        var visibleCount = Math.min(total, this.maxVisible);
        var rowsHtml = '';
        for (var i = 0; i < visibleCount; i++) {
            var doc = this.documents[i];
            var filename = (doc.filename || 'Untitled');
            var statusCls = this._statusClass(doc.status);
            var statusLbl = this._statusLabel(doc.status);

            rowsHtml +=
                '<div class="uploaded-file-entry">' +
                '<span class="uploaded-file-name">' + this._escapeHtml(filename) + '</span>' +
                '<span class="status-badge ' + statusCls + '">' + statusLbl + '</span>' +
                '</div>';
        }

        // "+N more" indicator
        var moreHtml = '';
        if (total > this.maxVisible) {
            var remaining = total - this.maxVisible;
            moreHtml = '<div class="uploaded-files-more">+' + remaining + ' more</div>';
        }

        this.container.innerHTML =
            '<div class="uploaded-files-panel">' +
            rowsHtml +
            moreHtml +
            '</div>';
    }
}
