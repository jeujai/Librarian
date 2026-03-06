/**
 * FileQueuePanel - Displays a reviewable file queue between selection and upload.
 *
 * Shows each file with its name, formatted size, and duplicate status.
 * Provides remove buttons per entry, summary counts, and upload action buttons.
 * Integrates with ChatUploadHandler via callbacks.
 */
class FileQueuePanel {
    /**
     * @param {HTMLElement} containerElement - DOM element to render the panel into
     */
    constructor(containerElement) {
        /** @type {HTMLElement} */
        this.container = containerElement;
        /** @type {{file: File, isDuplicate: boolean, id: string}[]} */
        this.entries = [];
        /** @type {Function|null} Callback when user clicks "Upload All New" */
        this.onUploadNew = null;
        /** @type {Function|null} Callback when user clicks "Force Upload All" */
        this.onForceUploadAll = null;
        /** @type {Function|null} Callback when user removes a file */
        this.onRemoveFile = null;
    }

    /**
     * Show the queue with file entries. Assigns unique IDs and renders.
     * @param {{file: File, isDuplicate: boolean}[]} fileEntries
     */
    show(fileEntries) {
        this.entries = fileEntries.map(function (entry, index) {
            return {
                file: entry.file,
                isDuplicate: entry.isDuplicate,
                id: 'fq-' + Date.now() + '-' + index
            };
        });
        this._render();
    }

    /**
     * Remove a file entry by its unique ID and re-render.
     * @param {string} entryId
     */
    removeEntry(entryId) {
        this.entries = this.entries.filter(function (entry) {
            return entry.id !== entryId;
        });
        this._render();
    }

    /**
     * Hide and clear the queue panel.
     */
    hide() {
        this.entries = [];
        this.container.style.display = 'none';
        this.container.innerHTML = '';
    }

    /**
     * Get count of new (non-duplicate) files in the queue.
     * @returns {number}
     */
    getNewFileCount() {
        return this.entries.filter(function (entry) {
            return !entry.isDuplicate;
        }).length;
    }

    /**
     * Get count of duplicate files in the queue.
     * @returns {number}
     */
    getDuplicateCount() {
        return this.entries.filter(function (entry) {
            return entry.isDuplicate;
        }).length;
    }

    /**
     * Format a byte count into a human-readable string (KB, MB, GB).
     * @param {number} bytes
     * @returns {string}
     */
    _formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        var units = ['B', 'KB', 'MB', 'GB'];
        var i = 0;
        var size = bytes;
        while (size >= 1024 && i < units.length - 1) {
            size /= 1024;
            i++;
        }
        return size.toFixed(i === 0 ? 0 : 1) + ' ' + units[i];
    }

    /**
     * Escape HTML special characters to prevent XSS.
     * @param {string} text
     * @returns {string}
     */
    _escapeHtml(text) {
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(text));
        return div.innerHTML;
    }

    /**
     * Render the panel HTML with file rows, summary, and action buttons.
     * @private
     */
    _render() {
        var self = this;
        var newCount = this.getNewFileCount();
        var dupCount = this.getDuplicateCount();
        var totalCount = this.entries.length;
        var isEmpty = totalCount === 0;

        // Build file rows
        var rowsHtml = '';
        for (var i = 0; i < this.entries.length; i++) {
            var entry = this.entries[i];
            var duplicateClass = entry.isDuplicate ? ' duplicate' : '';
            var duplicateBadge = entry.isDuplicate
                ? '<span class="duplicate-indicator">Duplicate</span>'
                : '';

            rowsHtml +=
                '<div class="file-queue-entry' + duplicateClass + '" data-entry-id="' + entry.id + '">' +
                '<div class="file-queue-entry-info">' +
                '<span class="file-queue-entry-name">' + this._escapeHtml(entry.file.name) + '</span>' +
                '<span class="file-queue-entry-size">' + this._formatFileSize(entry.file.size) + '</span>' +
                duplicateBadge +
                '</div>' +
                '<button class="file-queue-remove-btn" data-entry-id="' + entry.id + '" title="Remove file">&times;</button>' +
                '</div>';
        }

        // Summary line
        var summaryText = newCount + ' new, ' + dupCount + ' duplicate' + (dupCount !== 1 ? 's' : '');

        // Upload All New disabled when no new files or queue is empty
        var uploadNewDisabled = (newCount === 0 || isEmpty) ? ' disabled' : '';
        // Force Upload All disabled when queue is empty
        var forceUploadDisabled = isEmpty ? ' disabled' : '';

        var html =
            '<div class="file-queue-panel">' +
            '<div class="file-queue-entries">' + rowsHtml + '</div>' +
            '<div class="file-queue-summary">' + summaryText + '</div>' +
            '<div class="file-queue-actions">' +
            '<button class="file-queue-upload-new-btn"' + uploadNewDisabled + '>Upload All New</button>' +
            '<button class="file-queue-force-upload-btn"' + forceUploadDisabled + '>Force Upload All</button>' +
            '</div>' +
            '</div>';

        this.container.innerHTML = html;
        this.container.style.display = '';

        // Wire remove buttons
        var removeBtns = this.container.querySelectorAll('.file-queue-remove-btn');
        for (var j = 0; j < removeBtns.length; j++) {
            removeBtns[j].addEventListener('click', function (e) {
                var entryId = e.currentTarget.getAttribute('data-entry-id');
                self.removeEntry(entryId);
                if (self.onRemoveFile) {
                    self.onRemoveFile(entryId);
                }
            });
        }

        // Wire Upload All New button
        var uploadNewBtn = this.container.querySelector('.file-queue-upload-new-btn');
        if (uploadNewBtn) {
            uploadNewBtn.addEventListener('click', function () {
                if (self.onUploadNew) {
                    var newFiles = self.entries
                        .filter(function (entry) { return !entry.isDuplicate; })
                        .map(function (entry) { return entry.file; });
                    self.onUploadNew(newFiles);
                }
            });
        }

        // Wire Force Upload All button
        var forceUploadBtn = this.container.querySelector('.file-queue-force-upload-btn');
        if (forceUploadBtn) {
            forceUploadBtn.addEventListener('click', function () {
                if (self.onForceUploadAll) {
                    var allFiles = self.entries.map(function (entry) { return entry.file; });
                    self.onForceUploadAll(allFiles);
                }
            });
        }
    }
}
