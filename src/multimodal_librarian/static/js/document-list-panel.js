/**
 * Document List Panel
 * 
 * Compact panel for viewing and managing documents within the chat interface.
 * Displayed as a dropdown from the upload button.
 * 
 * Requirements: 8.1, 8.2, 8.3, 8.4, 8.5
 */

class DocumentListPanel {
    /**
     * Initialize with WebSocket manager.
     * 
     * @param {WebSocketManager} wsManager - WebSocket manager for document operations
     */
    constructor(wsManager) {
        this.wsManager = wsManager;
        this.documents = [];
        this.isVisible = false;
        this.panelElement = null;
        this.currentPage = 1;
        this.pageSize = 10;
        this.totalCount = 0;

        // Create panel element
        this.createPanelElement();

        // Set up WebSocket handlers
        this.setupWebSocketHandlers();

        // Set up click outside handler
        this.setupClickOutsideHandler();

        // Set up keyboard handler
        this.setupKeyboardHandler();
    }

    /**
     * Create the panel DOM element.
     */
    createPanelElement() {
        this.panelElement = document.createElement('div');
        this.panelElement.className = 'document-list-panel';
        this.panelElement.id = 'documentListPanel';
        this.panelElement.setAttribute('role', 'dialog');
        this.panelElement.setAttribute('aria-labelledby', 'documentListTitle');
        this.panelElement.setAttribute('aria-modal', 'true');
        this.panelElement.style.display = 'none';

        this.panelElement.innerHTML = `
            <div class="document-list-header">
                <h3 id="documentListTitle">Your Documents</h3>
                <button class="document-list-close-btn" aria-label="Close document list">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="18" y1="6" x2="6" y2="18"></line>
                        <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
                </button>
            </div>
            <div class="document-list-body">
                <div class="document-list-loading" style="display: none;">
                    <div class="document-list-spinner"></div>
                    <span>Loading documents...</span>
                </div>
                <div class="document-list-empty" style="display: none;">
                    <span class="empty-icon">📄</span>
                    <p>No documents uploaded yet</p>
                    <p class="empty-hint">Upload a PDF to get started</p>
                </div>
                <div class="document-list-items"></div>
            </div>
            <div class="document-list-footer" style="display: none;">
                <span class="document-count"></span>
                <div class="document-list-pagination">
                    <button class="pagination-btn prev-btn" disabled aria-label="Previous page">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="15,18 9,12 15,6"></polyline>
                        </svg>
                    </button>
                    <span class="page-info"></span>
                    <button class="pagination-btn next-btn" disabled aria-label="Next page">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="9,18 15,12 9,6"></polyline>
                        </svg>
                    </button>
                </div>
            </div>
        `;

        // Add to document body
        document.body.appendChild(this.panelElement);

        // Set up internal event listeners
        this.setupInternalListeners();
    }

    /**
     * Set up internal event listeners for panel elements.
     */
    setupInternalListeners() {
        // Close button
        const closeBtn = this.panelElement.querySelector('.document-list-close-btn');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.hide());
        }

        // Pagination buttons
        const prevBtn = this.panelElement.querySelector('.prev-btn');
        const nextBtn = this.panelElement.querySelector('.next-btn');

        if (prevBtn) {
            prevBtn.addEventListener('click', () => {
                if (this.currentPage > 1) {
                    this.currentPage--;
                    this.requestDocumentList();
                }
            });
        }

        if (nextBtn) {
            nextBtn.addEventListener('click', () => {
                const totalPages = Math.ceil(this.totalCount / this.pageSize);
                if (this.currentPage < totalPages) {
                    this.currentPage++;
                    this.requestDocumentList();
                }
            });
        }
    }

    /**
     * Set up WebSocket handlers for document operations.
     */
    setupWebSocketHandlers() {
        if (!this.wsManager) return;

        // Handle document list response
        this.wsManager.on('document_list', (data) => {
            this.handleDocumentListResponse(data);
        });

        // Handle document deleted response
        this.wsManager.on('document_deleted', (data) => {
            this.handleDocumentDeleted(data);
        });

        // Handle document retry started
        this.wsManager.on('document_retry_started', (data) => {
            this.handleDocumentRetryStarted(data);
        });

        // Handle processing status updates to refresh list
        this.wsManager.on('document_processing_status', (data) => {
            if (this.isVisible && (data.status === 'completed' || data.status === 'failed')) {
                // Refresh list when a document finishes processing
                this.requestDocumentList();
            }
        });
    }

    /**
     * Set up click outside handler to close panel.
     */
    setupClickOutsideHandler() {
        document.addEventListener('click', (e) => {
            if (!this.isVisible) return;

            // Check if click is outside panel and not on the trigger button
            const isOutsidePanel = !this.panelElement.contains(e.target);
            const isNotTrigger = !e.target.closest('.upload-dropdown-btn') &&
                !e.target.closest('.upload-dropdown');

            if (isOutsidePanel && isNotTrigger) {
                this.hide();
            }
        });
    }

    /**
     * Set up keyboard handler for Escape key.
     * 
     * Requirement: 8.5
     */
    setupKeyboardHandler() {
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.isVisible) {
                this.hide();
            }
        });
    }

    /**
     * Show the document list panel.
     * 
     * @param {HTMLElement} anchorElement - Element to position panel relative to
     */
    show(anchorElement = null) {
        this.isVisible = true;
        this.panelElement.style.display = 'block';

        // Position panel relative to anchor element
        if (anchorElement) {
            this.positionPanel(anchorElement);
        }

        // Show loading state
        this.showLoading();

        // Request document list
        this.requestDocumentList();

        // Focus on close button for accessibility
        const closeBtn = this.panelElement.querySelector('.document-list-close-btn');
        if (closeBtn) {
            closeBtn.focus();
        }
    }

    /**
     * Hide the document list panel.
     */
    hide() {
        this.isVisible = false;
        this.panelElement.style.display = 'none';
    }

    /**
     * Toggle panel visibility.
     * 
     * @param {HTMLElement} anchorElement - Element to position panel relative to
     */
    toggle(anchorElement = null) {
        if (this.isVisible) {
            this.hide();
        } else {
            this.show(anchorElement);
        }
    }

    /**
     * Position the panel relative to an anchor element.
     * 
     * @param {HTMLElement} anchorElement - Element to position relative to
     */
    positionPanel(anchorElement) {
        const rect = anchorElement.getBoundingClientRect();
        const panelRect = this.panelElement.getBoundingClientRect();

        // Position above the anchor element
        let top = rect.top - panelRect.height - 8;
        let left = rect.left;

        // Ensure panel stays within viewport
        if (top < 10) {
            // Position below if not enough space above
            top = rect.bottom + 8;
        }

        if (left + panelRect.width > window.innerWidth - 10) {
            left = window.innerWidth - panelRect.width - 10;
        }

        if (left < 10) {
            left = 10;
        }

        this.panelElement.style.position = 'fixed';
        this.panelElement.style.top = `${top}px`;
        this.panelElement.style.left = `${left}px`;
    }

    /**
     * Request document list from server via WebSocket.
     */
    requestDocumentList() {
        if (!this.wsManager || !this.wsManager.isConnected()) {
            this.showError('Not connected to server');
            return;
        }

        this.wsManager.send({
            type: 'document_list_request',
            page: this.currentPage,
            page_size: this.pageSize
        });
    }

    /**
     * Handle document list response from server.
     * 
     * @param {Object} data - Document list response data
     */
    handleDocumentListResponse(data) {
        this.documents = data.documents || [];
        this.totalCount = data.total_count || 0;

        // Update inline list if mounted
        if (this.inlineMounted) {
            this.updateInlineList(this.documents);
        }

        // Update floating panel if visible
        if (this.isVisible) {
            this.hideLoading();
            this.updateDocumentList(this.documents);
            this.updatePagination();
        }
    }

    /**
     * Update the displayed document list.
     * 
     * @param {Array<Object>} documents - List of document information
     * 
     * Requirements: 8.1, 8.2
     */
    updateDocumentList(documents) {
        const listContainer = this.panelElement.querySelector('.document-list-items');
        const emptyState = this.panelElement.querySelector('.document-list-empty');

        if (!listContainer) return;

        // Clear existing items
        listContainer.innerHTML = '';

        // Show empty state if no documents
        if (!documents || documents.length === 0) {
            if (emptyState) {
                emptyState.style.display = 'flex';
            }
            return;
        }

        // Hide empty state
        if (emptyState) {
            emptyState.style.display = 'none';
        }

        // Render each document
        documents.forEach(doc => {
            const docElement = this.createDocumentItem(doc);
            listContainer.appendChild(docElement);
        });
    }

    /**
     * Create a document item element.
     * 
     * @param {Object} doc - Document information
     * @returns {HTMLElement} Document item element
     * 
     * Requirements: 8.2, 8.3, 8.4
     */
    createDocumentItem(doc) {
        const item = document.createElement('div');
        item.className = `document-item status-${doc.status}`;
        item.setAttribute('data-document-id', doc.document_id);

        // Format file size
        const fileSize = this.formatFileSize(doc.file_size);

        // Format timestamp
        const timestamp = this.formatTimestamp(doc.upload_timestamp);

        // Get status badge
        const statusBadge = this.getStatusBadge(doc.status);

        const fmt = n => Number(n).toLocaleString();
        const statsHtml = this.buildStatsHtml(doc, fmt);

        item.innerHTML = `
            <div class="document-item-main">
                <div class="document-item-icon">📄</div>
                <div class="document-item-info">
                    <div class="document-item-title" title="${this.escapeHtml(doc.title || doc.filename)}">
                        <a href="/api/documents/${encodeURIComponent(doc.document_id)}/download?redirect=true" target="_blank" rel="noopener">${this.escapeHtml(doc.title || doc.filename)}</a>
                    </div>
                    <div class="document-item-meta">
                        <span class="document-item-size">${fileSize}</span>
                        <span class="document-item-separator">•</span>
                        <span class="document-item-date">${timestamp}</span>
                        ${doc.chunk_count ? `<span class="document-item-separator">•</span><span class="document-item-chunks">${fmt(doc.chunk_count)} chunks</span>` : ''}
                    </div>
                </div>
                ${statusBadge}
            </div>
            <div class="document-item-actions">
                ${this.getActionButtons(doc)}
            </div>
            ${doc.error_message ? `<div class="document-item-error">${this.escapeHtml(doc.error_message)}</div>` : ''}
            ${statsHtml}
        `;

        // Set up action button handlers
        this.setupActionHandlers(item, doc);

        return item;
    }

    /**
     * Build expandable stats HTML for a completed document.
     *
     * @param {Object} doc - Document information
     * @param {Function} fmt - Number formatter
     * @returns {string} Stats HTML or empty string
     */
    buildStatsHtml(doc, fmt) {
        if (doc.status !== 'completed') return '';
        const hasStats = doc.bridge_count || doc.concept_count || doc.relationship_count;
        if (!hasStats) return '';

        let rows = '';
        if (doc.chunk_count) rows += `<div class="stat-row"><span class="stat-label">Chunks</span><span class="stat-value">${fmt(doc.chunk_count)}</span></div>`;
        if (doc.bridge_count) rows += `<div class="stat-row"><span class="stat-label">Bridges</span><span class="stat-value">${fmt(doc.bridge_count)}</span></div>`;
        if (doc.concept_count) rows += `<div class="stat-row"><span class="stat-label">Concepts</span><span class="stat-value">${fmt(doc.concept_count)}</span></div>`;
        if (doc.relationship_count) rows += `<div class="stat-row"><span class="stat-label">Relationships</span><span class="stat-value">${fmt(doc.relationship_count)}</span></div>`;

        // Breakdown by source then type
        if (doc.relationship_breakdown && Object.keys(doc.relationship_breakdown).length > 0) {
            // Group by source
            const bySource = {};
            for (const [type, info] of Object.entries(doc.relationship_breakdown)) {
                // Support both old format (int) and new format ({count, source})
                const count = typeof info === 'object' ? info.count : info;
                const source = typeof info === 'object' ? (info.source || 'Document') : 'Document';
                if (!bySource[source]) bySource[source] = { types: {}, total: 0 };
                bySource[source].types[type] = count;
                bySource[source].total += count;
            }

            // Render each source group
            const sourceOrder = ['Document', 'ConceptNet', 'YAGO', 'Cross-document'];
            const sourceLabels = {
                'Document': '📄 Document KG',
                'ConceptNet': '🌐 ConceptNet',
                'YAGO': '🏛️ YAGO',
                'Cross-document': '🔀 Cross-document'
            };

            for (const source of sourceOrder) {
                const group = bySource[source];
                if (!group) continue;
                const label = sourceLabels[source] || source;
                rows += `<div class="stat-row stat-source-header"><span class="stat-label">${label}</span><span class="stat-value">${fmt(group.total)}</span></div>`;
                // Sort types by count descending
                const sorted = Object.entries(group.types).sort((a, b) => b[1] - a[1]);
                for (const [type, count] of sorted) {
                    const typeLabel = type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
                    rows += `<div class="stat-row stat-breakdown"><span class="stat-label">${this.escapeHtml(typeLabel)}</span><span class="stat-value">${fmt(count)}</span></div>`;
                }
            }

            // Any sources not in sourceOrder
            for (const [source, group] of Object.entries(bySource)) {
                if (sourceOrder.includes(source)) continue;
                rows += `<div class="stat-row stat-source-header"><span class="stat-label">${this.escapeHtml(source)}</span><span class="stat-value">${fmt(group.total)}</span></div>`;
                const sorted = Object.entries(group.types).sort((a, b) => b[1] - a[1]);
                for (const [type, count] of sorted) {
                    const typeLabel = type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
                    rows += `<div class="stat-row stat-breakdown"><span class="stat-label">${this.escapeHtml(typeLabel)}</span><span class="stat-value">${fmt(count)}</span></div>`;
                }
            }
        }

        return `
            <div class="document-stats">
                <button class="document-stats-toggle" aria-label="Toggle document stats">
                    <span class="stats-arrow">▸</span> Stats
                </button>
                <div class="document-stats-details" style="display:none;">
                    ${rows}
                </div>
            </div>
        `;
    }

    /**
     * Get status badge HTML.
     * 
     * @param {string} status - Document status
     * @returns {string} Status badge HTML
     */
    getStatusBadge(status) {
        const badges = {
            'uploaded': '<span class="status-badge status-uploaded">Uploaded</span>',
            'processing': '<span class="status-badge status-processing"><span class="badge-spinner"></span>Processing</span>',
            'completed': '<span class="status-badge status-completed">Ready</span>',
            'failed': '<span class="status-badge status-failed">Failed</span>'
        };

        return badges[status] || badges['uploaded'];
    }

    /**
     * Get action buttons HTML based on document status.
     * 
     * @param {Object} doc - Document information
     * @returns {string} Action buttons HTML
     * 
     * Requirements: 8.3, 8.4
     */
    getActionButtons(doc) {
        let buttons = '';

        // Retry button for failed documents (Requirement 8.4)
        if (doc.status === 'failed') {
            buttons += `
                <button class="document-action-btn retry-btn" 
                        data-action="retry" 
                        data-document-id="${doc.document_id}"
                        aria-label="Retry processing ${this.escapeHtml(doc.title || doc.filename)}"
                        title="Retry processing">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="23,4 23,10 17,10"></polyline>
                        <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
                    </svg>
                </button>
            `;
        }

        // Delete button for all documents (Requirement 8.3)
        buttons += `
            <button class="document-action-btn delete-btn" 
                    data-action="delete" 
                    data-document-id="${doc.document_id}"
                    aria-label="Delete ${this.escapeHtml(doc.title || doc.filename)}"
                    title="Delete document">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="3,6 5,6 21,6"></polyline>
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                </svg>
            </button>
        `;

        return buttons;
    }

    /**
     * Set up action button handlers for a document item.
     * 
     * @param {HTMLElement} item - Document item element
     * @param {Object} doc - Document information
     */
    setupActionHandlers(item, doc) {
        // Delete button handler
        const deleteBtn = item.querySelector('.delete-btn');
        if (deleteBtn) {
            deleteBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.handleDelete(doc.document_id, doc.title || doc.filename);
            });
        }

        // Retry button handler
        const retryBtn = item.querySelector('.retry-btn');
        if (retryBtn) {
            retryBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.handleRetry(doc.document_id);
            });
        }

        // Stats toggle handler
        const statsToggle = item.querySelector('.document-stats-toggle');
        if (statsToggle) {
            statsToggle.addEventListener('click', (e) => {
                e.stopPropagation();
                const details = item.querySelector('.document-stats-details');
                const arrow = statsToggle.querySelector('.stats-arrow');
                if (details) {
                    const isOpen = details.style.display !== 'none';
                    details.style.display = isOpen ? 'none' : 'block';
                    if (arrow) arrow.textContent = isOpen ? '▸' : '▾';
                }
            });
        }
    }

    /**
     * Handle delete button click.
     * Shows confirmation before deleting.
     * 
     * @param {string} documentId - Document ID to delete
     * @param {string} documentName - Document name for confirmation
     * 
     * Requirement: 8.3
     */
    handleDelete(documentId, documentName) {
        // Show confirmation dialog
        const confirmed = confirm(`Are you sure you want to delete "${documentName}"?\n\nThis will remove the document from your knowledge base.`);

        if (!confirmed) return;

        if (!this.wsManager || !this.wsManager.isConnected()) {
            this.showError('Not connected to server');
            return;
        }

        // Show loading state on the item
        const item = this.panelElement.querySelector(`[data-document-id="${documentId}"]`);
        if (item) {
            item.classList.add('deleting');
        }

        // Send delete request
        this.wsManager.send({
            type: 'document_delete_request',
            document_id: documentId
        });
    }

    /**
     * Handle retry button click for failed documents.
     * 
     * @param {string} documentId - Document ID to retry
     * 
     * Requirement: 8.4
     */
    handleRetry(documentId) {
        if (!this.wsManager || !this.wsManager.isConnected()) {
            this.showError('Not connected to server');
            return;
        }

        // Show loading state on the item
        const item = this.panelElement.querySelector(`[data-document-id="${documentId}"]`);
        if (item) {
            item.classList.add('retrying');
            const statusBadge = item.querySelector('.status-badge');
            if (statusBadge) {
                statusBadge.outerHTML = '<span class="status-badge status-processing"><span class="badge-spinner"></span>Retrying</span>';
            }
        }

        // Send retry request
        this.wsManager.send({
            type: 'document_retry_request',
            document_id: documentId
        });
    }

    /**
     * Handle document deleted response.
     * 
     * @param {Object} data - Delete response data
     */
    handleDocumentDeleted(data) {
        const { document_id, success, message } = data;

        if (success) {
            // Remove item from floating panel
            const item = this.panelElement.querySelector(`[data-document-id="${document_id}"]`);
            if (item) {
                item.classList.add('deleted');
                setTimeout(() => {
                    item.remove();

                    // Update count
                    this.totalCount = Math.max(0, this.totalCount - 1);
                    this.updatePagination();

                    // Show empty state if no documents left
                    const listContainer = this.panelElement.querySelector('.document-list-items');
                    if (listContainer && listContainer.children.length === 0) {
                        const emptyState = this.panelElement.querySelector('.document-list-empty');
                        if (emptyState) {
                            emptyState.style.display = 'flex';
                        }
                    }
                }, 300);
            }

            // Remove item from inline list
            if (this.inlineContainer) {
                const inlineItem = this.inlineContainer.querySelector(`[data-document-id="${document_id}"]`);
                if (inlineItem) {
                    inlineItem.remove();
                    this.totalCount = Math.max(0, this.totalCount - 1);
                    this.updateInlinePagination();
                }
            }
        } else {
            this.showError(message || 'Failed to delete document');

            // Remove loading state
            const item = this.panelElement.querySelector(`[data-document-id="${document_id}"]`);
            if (item) {
                item.classList.remove('deleting');
            }
        }
    }

    /**
     * Handle document retry started response.
     * 
     * @param {Object} data - Retry response data
     */
    handleDocumentRetryStarted(data) {
        const { document_id } = data;

        // Update item status
        const item = this.panelElement.querySelector(`[data-document-id="${document_id}"]`);
        if (item) {
            item.classList.remove('retrying');
            item.classList.remove('status-failed');
            item.classList.add('status-processing');
        }
    }

    /**
     * Update pagination controls.
     */
    updatePagination() {
        const footer = this.panelElement.querySelector('.document-list-footer');
        const countSpan = this.panelElement.querySelector('.document-count');
        const pageInfo = this.panelElement.querySelector('.page-info');
        const prevBtn = this.panelElement.querySelector('.prev-btn');
        const nextBtn = this.panelElement.querySelector('.next-btn');

        if (!footer) return;

        const totalPages = Math.ceil(this.totalCount / this.pageSize);

        // Show/hide footer based on document count
        if (this.totalCount > 0) {
            footer.style.display = 'flex';

            if (countSpan) {
                countSpan.textContent = `${this.totalCount} document${this.totalCount !== 1 ? 's' : ''}`;
            }

            if (pageInfo && totalPages > 1) {
                pageInfo.textContent = `${this.currentPage} / ${totalPages}`;
                pageInfo.style.display = 'inline';
            } else if (pageInfo) {
                pageInfo.style.display = 'none';
            }

            // Update button states
            if (prevBtn) {
                prevBtn.disabled = this.currentPage <= 1;
            }
            if (nextBtn) {
                nextBtn.disabled = this.currentPage >= totalPages;
            }

            // Hide pagination if only one page
            const pagination = this.panelElement.querySelector('.document-list-pagination');
            if (pagination) {
                pagination.style.display = totalPages > 1 ? 'flex' : 'none';
            }
        } else {
            footer.style.display = 'none';
        }
    }

    /**
     * Show loading state.
     */
    showLoading() {
        const loading = this.panelElement.querySelector('.document-list-loading');
        const items = this.panelElement.querySelector('.document-list-items');
        const empty = this.panelElement.querySelector('.document-list-empty');

        if (loading) loading.style.display = 'flex';
        if (items) items.style.display = 'none';
        if (empty) empty.style.display = 'none';
    }

    /**
     * Hide loading state.
     */
    hideLoading() {
        const loading = this.panelElement.querySelector('.document-list-loading');
        const items = this.panelElement.querySelector('.document-list-items');

        if (loading) loading.style.display = 'none';
        if (items) items.style.display = 'block';
    }

    /**
     * Show error message.
     * 
     * @param {string} message - Error message to display
     */
    showError(message) {
        // Use chat app's system message if available
        if (window.chatApp && typeof window.chatApp.addSystemMessage === 'function') {
            window.chatApp.addSystemMessage(message, 'error');
        } else {
            console.error('Document List Panel Error:', message);
        }
    }

    /**
     * Format file size for display.
     * 
     * @param {number} bytes - File size in bytes
     * @returns {string} Formatted file size
     */
    formatFileSize(bytes) {
        if (!bytes || bytes === 0) return '0 B';

        const units = ['B', 'KB', 'MB', 'GB'];
        const k = 1024;
        const i = Math.floor(Math.log(bytes) / Math.log(k));

        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + units[i];
    }

    /**
     * Format timestamp for display.
     * 
     * @param {string} timestamp - ISO timestamp string
     * @returns {string} Formatted timestamp
     */
    formatTimestamp(timestamp) {
        if (!timestamp) return '';

        try {
            const date = new Date(timestamp);
            const now = new Date();
            const diffMs = now - date;
            const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

            if (diffDays === 0) {
                // Today - show time
                return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            } else if (diffDays === 1) {
                return 'Yesterday';
            } else if (diffDays < 7) {
                return `${diffDays} days ago`;
            } else {
                // Show date
                return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
            }
        } catch (e) {
            return '';
        }
    }

    /**
     * Escape HTML to prevent XSS.
     * 
     * @param {string} text - Text to escape
     * @returns {string} Escaped text
     */
    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Refresh the document list.
     */
    refresh() {
        if (this.isVisible) {
            this.showLoading();
            this.requestDocumentList();
        }
    }

    /**
     * Mount an inline compact document list into a container element.
     * This replaces the separate floating panel with an embedded list
     * inside the upload dropdown.
     *
     * @param {HTMLElement} container - DOM element to render into
     */
    mountInline(container) {
        this.inlineContainer = container;
        this.inlineContainer.innerHTML = `
            <div class="inline-doc-list">
                <div class="inline-doc-list-loading" style="display: none;">
                    <div class="document-list-spinner"></div>
                    <span>Loading...</span>
                </div>
                <div class="inline-doc-list-empty" style="display: none;">
                    <p class="uploaded-files-empty">No documents uploaded yet</p>
                </div>
                <div class="inline-doc-list-items"></div>
                <div class="inline-doc-list-footer" style="display: none;">
                    <span class="inline-doc-count"></span>
                    <div class="inline-doc-pagination">
                        <button class="pagination-btn inline-prev-btn" disabled aria-label="Previous page">‹</button>
                        <span class="inline-page-info"></span>
                        <button class="pagination-btn inline-next-btn" disabled aria-label="Next page">›</button>
                    </div>
                </div>
            </div>
        `;

        // Pagination handlers
        const prevBtn = this.inlineContainer.querySelector('.inline-prev-btn');
        const nextBtn = this.inlineContainer.querySelector('.inline-next-btn');
        if (prevBtn) {
            prevBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                if (this.currentPage > 1) {
                    this.currentPage--;
                    this.requestDocumentList();
                }
            });
        }
        if (nextBtn) {
            nextBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                const totalPages = Math.ceil(this.totalCount / this.pageSize);
                if (this.currentPage < totalPages) {
                    this.currentPage++;
                    this.requestDocumentList();
                }
            });
        }

        this.inlineMounted = true;
    }

    /**
     * Refresh the inline document list (called when dropdown opens).
     */
    refreshInline() {
        if (!this.inlineMounted || !this.inlineContainer) return;

        // Show loading
        const loading = this.inlineContainer.querySelector('.inline-doc-list-loading');
        const items = this.inlineContainer.querySelector('.inline-doc-list-items');
        const empty = this.inlineContainer.querySelector('.inline-doc-list-empty');
        if (loading) loading.style.display = 'flex';
        if (items) items.style.display = 'none';
        if (empty) empty.style.display = 'none';

        this.requestDocumentList();
    }

    /**
     * Update the inline document list with data.
     * Called from handleDocumentListResponse when inline mode is active.
     *
     * @param {Array<Object>} documents - Document list
     */
    updateInlineList(documents) {
        if (!this.inlineContainer) return;

        const loading = this.inlineContainer.querySelector('.inline-doc-list-loading');
        const itemsContainer = this.inlineContainer.querySelector('.inline-doc-list-items');
        const empty = this.inlineContainer.querySelector('.inline-doc-list-empty');

        if (loading) loading.style.display = 'none';
        if (itemsContainer) itemsContainer.style.display = 'block';

        if (!documents || documents.length === 0) {
            if (itemsContainer) itemsContainer.innerHTML = '';
            if (empty) empty.style.display = 'block';
            this.updateInlinePagination();
            return;
        }

        if (empty) empty.style.display = 'none';

        const fmt = n => Number(n).toLocaleString();
        itemsContainer.innerHTML = '';

        documents.forEach(doc => {
            const row = document.createElement('div');
            row.className = `inline-doc-row status-${doc.status}`;
            row.setAttribute('data-document-id', doc.document_id);

            const title = this.escapeHtml(doc.title || doc.filename);
            const statusBadge = this.getStatusBadge(doc.status);
            const statsHtml = this.buildStatsHtml(doc, fmt);

            const retryBtn = doc.status === 'failed' ? `
                <button class="inline-doc-action-btn inline-retry-btn" data-document-id="${doc.document_id}" aria-label="Retry processing" title="Retry">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23,4 23,10 17,10"></polyline><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path></svg>
                </button>` : '';

            row.innerHTML = `
                <div class="inline-doc-row-main">
                    <a class="inline-doc-title" href="/api/documents/${encodeURIComponent(doc.document_id)}/download?redirect=true" title="${title}" target="_blank" rel="noopener">${title}</a>
                    ${statusBadge}
                    ${retryBtn}
                    <button class="inline-doc-action-btn inline-delete-btn" data-document-id="${doc.document_id}" aria-label="Delete document" title="Delete">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3,6 5,6 21,6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                    </button>
                </div>
                ${statsHtml}
            `;

            // Wire up stats toggle
            const statsToggle = row.querySelector('.document-stats-toggle');
            if (statsToggle) {
                statsToggle.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const details = row.querySelector('.document-stats-details');
                    const arrow = statsToggle.querySelector('.stats-arrow');
                    if (details) {
                        const isOpen = details.style.display !== 'none';
                        details.style.display = isOpen ? 'none' : 'block';
                        if (arrow) arrow.textContent = isOpen ? '▸' : '▾';
                    }
                });
            }

            // Wire up delete button
            const deleteBtn = row.querySelector('.inline-delete-btn');
            if (deleteBtn) {
                deleteBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    e.preventDefault();
                    this.handleDelete(doc.document_id, doc.title || doc.filename);
                });
            }

            // Wire up retry button
            const retryBtnEl = row.querySelector('.inline-retry-btn');
            if (retryBtnEl) {
                retryBtnEl.addEventListener('click', (e) => {
                    e.stopPropagation();
                    e.preventDefault();
                    this.handleRetry(doc.document_id);
                });
            }

            itemsContainer.appendChild(row);
        });

        this.updateInlinePagination();
    }

    /**
     * Update inline pagination controls.
     */
    updateInlinePagination() {
        if (!this.inlineContainer) return;

        const footer = this.inlineContainer.querySelector('.inline-doc-list-footer');
        const countSpan = this.inlineContainer.querySelector('.inline-doc-count');
        const pageInfo = this.inlineContainer.querySelector('.inline-page-info');
        const prevBtn = this.inlineContainer.querySelector('.inline-prev-btn');
        const nextBtn = this.inlineContainer.querySelector('.inline-next-btn');

        if (!footer) return;

        const totalPages = Math.ceil(this.totalCount / this.pageSize);

        if (this.totalCount > 0) {
            footer.style.display = 'flex';
            if (countSpan) countSpan.textContent = `${this.totalCount} doc${this.totalCount !== 1 ? 's' : ''}`;
            if (pageInfo && totalPages > 1) {
                pageInfo.textContent = `${this.currentPage}/${totalPages}`;
                pageInfo.style.display = 'inline';
            } else if (pageInfo) {
                pageInfo.style.display = 'none';
            }
            if (prevBtn) prevBtn.disabled = this.currentPage <= 1;
            if (nextBtn) nextBtn.disabled = this.currentPage >= totalPages;

            const pagination = this.inlineContainer.querySelector('.inline-doc-pagination');
            if (pagination) pagination.style.display = totalPages > 1 ? 'flex' : 'none';
        } else {
            footer.style.display = 'none';
        }
    }
}

// Export for use in other modules
window.DocumentListPanel = DocumentListPanel;
