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

        // Track active conversation thread for delete-disable (Requirement 7.1)
        this._activeThreadId = null;

        // Listen for active thread changes from ChatApp
        document.addEventListener('active-thread-changed', (e) => {
            this._activeThreadId = e.detail.threadId;
            this._updateDeleteButtonStates();
        });

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
            // Update status badge in real-time for the affected document
            if (data.document_id) {
                this._updateDocumentStatus(data.document_id, data.status);
            }
            if (this.isVisible && (data.status === 'completed' || data.status === 'failed')) {
                // Full refresh when a document finishes processing
                this.requestDocumentList();
            }
        });

        // Handle related docs graph response
        this.wsManager.on('related_docs_graph', (data) => {
            this._handleRelatedDocsGraphResponse(data);
        });

        // Handle related docs graph error
        this.wsManager.on('related_docs_graph_error', (data) => {
            this._handleRelatedDocsGraphError(data);
        });

        // Handle on-demand document stats response
        this.wsManager.on('document_stats', (data) => {
            this._handleDocumentStatsResponse(data);
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
            // Don't close if interacting with the related docs popup
            const isInRelatedDocsPopup = this._relatedDocsPopup &&
                this._relatedDocsPopup.contains(e.target);

            if (isOutsidePanel && isNotTrigger && !isInRelatedDocsPopup) {
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

        // Check if we have a pending scroll target
        if (this._pendingScrollDocId) {
            const found = this.documents.some(d => d.document_id === this._pendingScrollDocId);
            if (found) {
                // Target is on this page — render first, then scroll after DOM update
                const targetId = this._pendingScrollDocId;
                this._pendingScrollDocId = null;
                // Let the render happen below, then scroll in the next frame
                setTimeout(() => this._scrollToDocument(targetId), 50);
            } else {
                // Target not on this page — try next page
                const totalPages = Math.ceil(this.totalCount / this.pageSize);
                if (this.currentPage < totalPages) {
                    this.currentPage++;
                    this.requestDocumentList();
                    return; // Don't render yet, keep searching
                } else {
                    // Exhausted all pages, give up
                    this._pendingScrollDocId = null;
                }
            }
        }

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

        const isConversation = doc.source_type === 'conversation';

        // Format file size
        const fileSize = this.formatFileSize(doc.file_size);

        // Format timestamp
        const timestamp = this.formatTimestamp(doc.upload_timestamp);

        // Get status badge
        const statusBadge = this.getStatusBadge(doc.status);

        const fmt = n => Number(n).toLocaleString();
        const statsHtml = this.buildStatsHtml(doc, fmt);

        // Icon: 💬 for conversation, 📄 for regular docs (Requirement 5.2)
        const icon = isConversation ? '💬' : '📄';

        // Title rendering: conversation docs get editable span + click-to-reopen,
        // regular docs get download link (Requirements 5.3, 6.1, 9.1)
        const displayTitle = this.escapeHtml(doc.title || doc.filename);
        let titleHtml;
        if (isConversation) {
            titleHtml = `<span class="document-title-text conversation-title-clickable" data-thread-id="${doc.thread_id}">${displayTitle}</span>`;
        } else {
            titleHtml = `<a href="/api/documents/${encodeURIComponent(doc.document_id)}/download?redirect=true" target="_blank" rel="noopener">${displayTitle}</a>`;
        }

        // Meta line: conversation docs skip file size (Requirement 5.3)
        let metaHtml;
        if (isConversation) {
            metaHtml = `
                <span class="document-item-date">${timestamp}</span>
                ${doc.chunk_count ? `<span class="document-item-separator">•</span><span class="document-item-chunks">${fmt(doc.chunk_count)} chunks</span>` : ''}
            `;
        } else {
            metaHtml = `
                <span class="document-item-size">${fileSize}</span>
                <span class="document-item-separator">•</span>
                <span class="document-item-date">${timestamp}</span>
                ${doc.chunk_count ? `<span class="document-item-separator">•</span><span class="document-item-chunks">${fmt(doc.chunk_count)} chunks</span>` : ''}
            `;
        }

        item.innerHTML = `
            <div class="document-item-main">
                <div class="document-item-icon">${icon}</div>
                <div class="document-item-info">
                    <div class="document-item-title" title="${displayTitle}">
                        ${titleHtml}
                    </div>
                    <div class="document-item-meta">
                        ${metaHtml}
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

        const relatedDocsBtn = `
                <button class="document-related-docs-btn"
                        data-document-id="${doc.document_id}"
                        aria-label="Show related documents graph">
                    📎 Related Docs
                </button>`;

        // Stats are loaded on-demand when the user clicks the toggle.
        return `
            <div class="document-stats" data-doc-id="${doc.document_id}">
                <button class="document-stats-toggle" aria-label="Toggle document stats">
                    <span class="stats-arrow">▸</span> Stats
                </button>
                ${relatedDocsBtn}
                <div class="document-stats-details" style="display:none;">
                    <div class="stats-loading" style="padding:6px 0;color:var(--vscode-descriptionForeground,#888);font-size:0.85em;">Loading stats…</div>
                </div>
            </div>
        `;
    }

    /**
     * Render stats rows from a document_stats response into a container.
     * Also injects the Related Docs button if concepts > 0.
     */
    _renderStatsContent(container, data) {
        const fmt = (n) => (n >= 1000 ? (n / 1000).toFixed(1) + 'k' : String(n));
        let rows = '';
        if (data.chunk_count) rows += `<div class="stat-row"><span class="stat-label">Chunks</span><span class="stat-value">${fmt(data.chunk_count)}</span></div>`;
        if (data.bridge_count) rows += `<div class="stat-row"><span class="stat-label">Bridges</span><span class="stat-value">${fmt(data.bridge_count)}</span></div>`;
        if (data.concept_count) rows += `<div class="stat-row"><span class="stat-label">Concepts</span><span class="stat-value">${fmt(data.concept_count)}</span></div>`;
        if (data.relationship_count) rows += `<div class="stat-row"><span class="stat-label">Relationships</span><span class="stat-value">${fmt(data.relationship_count)}</span></div>`;
        if (data.umls_linked_count) rows += `<div class="stat-row"><span class="stat-label">🏥 UMLS Linked</span><span class="stat-value">${fmt(data.umls_linked_count)}</span></div>`;
        if (data.umls_concept_count) rows += `<div class="stat-row"><span class="stat-label">🏥 UMLS Concepts</span><span class="stat-value">${fmt(data.umls_concept_count)}</span></div>`;

        if (data.relationship_breakdown && Object.keys(data.relationship_breakdown).length > 0) {
            const bySource = {};
            for (const [type, info] of Object.entries(data.relationship_breakdown)) {
                const count = typeof info === 'object' ? info.count : info;
                const source = typeof info === 'object' ? (info.source || 'Document') : 'Document';
                if (!bySource[source]) bySource[source] = { types: {}, total: 0 };
                bySource[source].types[type] = count;
                bySource[source].total += count;
            }

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
                const sorted = Object.entries(group.types).sort((a, b) => b[1] - a[1]);
                for (const [type, count] of sorted) {
                    const typeLabel = type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
                    rows += `<div class="stat-row stat-breakdown"><span class="stat-label">${this.escapeHtml(typeLabel)}</span><span class="stat-value">${fmt(count)}</span></div>`;
                }
            }

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

        container.innerHTML = rows || '<div class="stat-row"><span class="stat-label">No stats available</span></div>';
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
     * Update the status badge for a specific document in-place.
     * Called on real-time processing status WebSocket events.
     */
    _updateDocumentStatus(documentId, status) {
        if (!status) return;
        // Map processing statuses to badge status
        const badgeStatus = (status === 'running' || status === 'pending') ? 'processing' : status;
        const newBadgeHtml = this.getStatusBadge(badgeStatus);

        // Update in floating panel
        const item = this.panelElement?.querySelector(`[data-document-id="${documentId}"]`);
        if (item) {
            const badge = item.querySelector('.status-badge');
            if (badge) badge.outerHTML = newBadgeHtml;
        }

        // Update in inline list
        if (this.inlineContainer) {
            const inlineItem = this.inlineContainer.querySelector(`[data-document-id="${documentId}"]`);
            if (inlineItem) {
                const badge = inlineItem.querySelector('.status-badge');
                if (badge) badge.outerHTML = newBadgeHtml;
            }
        }

        // Update local documents array
        const doc = this.documents.find(d => d.document_id === documentId);
        if (doc) doc.status = badgeStatus;
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
        const isConversation = doc.source_type === 'conversation';

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

        // Delete button — disabled if this conversation is active (Requirements 7.1, 7.2, 7.3)
        const isActive = isConversation && this._activeThreadId && this._activeThreadId === doc.thread_id;
        const deleteTitle = isActive ? 'Cannot delete while conversation is active' : 'Delete document';
        buttons += `
            <button class="document-action-btn delete-btn${isActive ? ' delete-btn-disabled' : ''}" 
                    data-action="delete" 
                    data-document-id="${doc.document_id}"
                    ${isConversation ? `data-thread-id="${doc.thread_id}"` : ''}
                    aria-label="Delete ${this.escapeHtml(doc.title || doc.filename)}"
                    title="${deleteTitle}"
                    ${isActive ? 'disabled' : ''}>
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
        const isConversation = doc.source_type === 'conversation';

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

        // Conversation title click → reopen conversation (Requirement 6.1)
        if (isConversation) {
            const titleText = item.querySelector('.conversation-title-clickable');
            if (titleText) {
                titleText.addEventListener('click', (e) => {
                    e.stopPropagation();
                    e.preventDefault();
                    if (window.chatApp && typeof window.chatApp.reopenConversation === 'function') {
                        window.chatApp.reopenConversation(doc.thread_id);
                    }
                });

                // Double-click title → inline edit (Requirement 9.1)
                titleText.addEventListener('dblclick', (e) => {
                    e.stopPropagation();
                    e.preventDefault();
                    this._startTitleEdit(titleText, doc);
                });
            }
        }

        // Stats toggle handler — lazy-loads stats on first expand
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
                    // Request stats on first open
                    const statsDiv = item.querySelector('.document-stats');
                    if (!isOpen && statsDiv && !statsDiv.hasAttribute('data-stats-loaded')) {
                        statsDiv.setAttribute('data-stats-loaded', 'pending');
                        this.wsManager.send({
                            type: 'document_stats_request',
                            document_id: doc.document_id,
                        });
                    }
                }
            });
        }

        // Related Docs button handler
        const relatedDocsBtn = item.querySelector('.document-related-docs-btn');
        if (relatedDocsBtn) {
            relatedDocsBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                const displayTitle = doc.title || decodeURIComponent(doc.filename || doc.document_id);
                this._openRelatedDocsPopup(doc.document_id, displayTitle);
            });
        }
    }

    /**
     * Update delete button disabled states for all conversation documents.
     * Called when active-thread-changed event fires.
     * 
     * Requirements: 7.1, 7.2, 7.3, 7.4
     */
    _updateDeleteButtonStates() {
        // Update in floating panel
        const deleteBtns = this.panelElement.querySelectorAll('.delete-btn[data-thread-id]');
        deleteBtns.forEach(btn => {
            const threadId = btn.getAttribute('data-thread-id');
            const isActive = this._activeThreadId && threadId === this._activeThreadId;
            btn.disabled = isActive;
            btn.title = isActive ? 'Cannot delete while conversation is active' : 'Delete document';
            if (isActive) {
                btn.classList.add('delete-btn-disabled');
            } else {
                btn.classList.remove('delete-btn-disabled');
            }
        });

        // Update in inline panel
        if (this.inlineContainer) {
            const inlineDeleteBtns = this.inlineContainer.querySelectorAll('.inline-delete-btn[data-thread-id]');
            inlineDeleteBtns.forEach(btn => {
                const threadId = btn.getAttribute('data-thread-id');
                const isActive = this._activeThreadId && threadId === this._activeThreadId;
                btn.disabled = isActive;
                btn.title = isActive ? 'Cannot delete while conversation is active' : 'Delete document';
                if (isActive) {
                    btn.classList.add('delete-btn-disabled');
                } else {
                    btn.classList.remove('delete-btn-disabled');
                }
            });
        }
    }

    /**
     * Start inline title editing for a conversation document.
     * Click title text → switch to input element.
     * 
     * Requirements: 9.1, 9.2, 9.3, 9.4
     * 
     * @param {HTMLElement} titleElement - The title span element
     * @param {Object} doc - Document information
     */
    _startTitleEdit(titleElement, doc) {
        // Prevent double-editing
        if (titleElement.querySelector('.document-title-edit')) return;

        const originalTitle = titleElement.textContent;
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'document-title-edit';
        input.value = originalTitle;
        input.setAttribute('aria-label', 'Edit document title');

        // Replace text with input
        titleElement.textContent = '';
        titleElement.appendChild(input);
        input.focus();
        input.select();

        const finishEdit = (save) => {
            if (input._finished) return;
            input._finished = true;

            const newTitle = input.value.trim();

            if (!save || !newTitle) {
                // Revert: Escape pressed or empty title
                titleElement.textContent = originalTitle;
                if (!newTitle && save) {
                    // Show brief validation message for empty title
                    titleElement.textContent = originalTitle;
                    const msg = document.createElement('span');
                    msg.className = 'title-validation-msg';
                    msg.textContent = 'Title cannot be empty';
                    titleElement.parentElement.appendChild(msg);
                    setTimeout(() => msg.remove(), 2000);
                }
                return;
            }

            if (newTitle === originalTitle) {
                titleElement.textContent = originalTitle;
                return;
            }

            // Save via API
            this._saveTitleEdit(doc.thread_id, newTitle, titleElement, originalTitle);
        };

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                finishEdit(true);
            } else if (e.key === 'Escape') {
                e.preventDefault();
                finishEdit(false);
            }
        });

        input.addEventListener('blur', () => {
            finishEdit(true);
        });
    }

    /**
     * Save an edited title via PATCH API.
     * 
     * Requirements: 9.2
     * 
     * @param {string} threadId - Conversation thread ID
     * @param {string} newTitle - New title to save
     * @param {HTMLElement} titleElement - The title element to update
     * @param {string} originalTitle - Original title for revert on failure
     */
    async _saveTitleEdit(threadId, newTitle, titleElement, originalTitle) {
        // Optimistically update the DOM
        titleElement.textContent = newTitle;
        titleElement.parentElement.setAttribute('title', newTitle);

        try {
            const response = await fetch(`/api/conversations/${threadId}/title`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: newTitle })
            });

            if (!response.ok) {
                throw new Error(`Failed to update title: ${response.statusText}`);
            }
        } catch (err) {
            console.error('Title edit failed:', err);
            // Revert on failure
            titleElement.textContent = originalTitle;
            titleElement.parentElement.setAttribute('title', originalTitle);
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

        // Track thread_id for conversation documents so we can dispatch
        // the deletion event after the server confirms (Requirement 8.5)
        const doc = this.documents.find(d => d.document_id === documentId);
        if (doc && doc.source_type === 'conversation' && doc.thread_id) {
            this._pendingDeleteThreadIds = this._pendingDeleteThreadIds || {};
            this._pendingDeleteThreadIds[documentId] = doc.thread_id;
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
            // Dispatch event for conversation documents so ChatApp can clean up
            // UI handles to the source conversation (Requirement 8.5)
            const threadId = this._pendingDeleteThreadIds && this._pendingDeleteThreadIds[document_id];
            if (threadId) {
                document.dispatchEvent(new CustomEvent('conversation-document-deleted', {
                    detail: { documentId: document_id, threadId }
                }));
                delete this._pendingDeleteThreadIds[document_id];
            }

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

            // Remove from local documents array
            this.documents = this.documents.filter(d => d.document_id !== document_id);
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
                        <button class="pagination-btn inline-first-btn" disabled aria-label="First page">«</button>
                        <button class="pagination-btn inline-prev-btn" disabled aria-label="Previous page">‹</button>
                        <span class="inline-page-info"></span>
                        <button class="pagination-btn inline-next-btn" disabled aria-label="Next page">›</button>
                        <button class="pagination-btn inline-last-btn" disabled aria-label="Last page">»</button>
                    </div>
                </div>
            </div>
        `;

        // Inject top pagination into the Upload PDF row
        const uploadItem = this.inlineContainer.closest('.upload-dropdown')?.querySelector('.upload-dropdown-item[data-action="upload"]');
        if (uploadItem) {
            const topNav = document.createElement('div');
            topNav.className = 'inline-doc-top-pagination';
            topNav.style.display = 'none';
            topNav.innerHTML = `
                <button class="pagination-btn top-first-btn" disabled aria-label="First page">«</button>
                <button class="pagination-btn top-prev-btn" disabled aria-label="Previous page">‹</button>
                <span class="top-page-info"></span>
                <button class="pagination-btn top-next-btn" disabled aria-label="Next page">›</button>
                <button class="pagination-btn top-last-btn" disabled aria-label="Last page">»</button>
            `;
            uploadItem.appendChild(topNav);
            this._topPagination = topNav;
        }

        // Pagination handlers — wire up all nav buttons (top + bottom)
        this._wirePaginationBtn('.inline-first-btn', 'first');
        this._wirePaginationBtn('.inline-prev-btn', 'prev');
        this._wirePaginationBtn('.inline-next-btn', 'next');
        this._wirePaginationBtn('.inline-last-btn', 'last');
        if (this._topPagination) {
            this._wirePaginationBtn('.top-first-btn', 'first', this._topPagination);
            this._wirePaginationBtn('.top-prev-btn', 'prev', this._topPagination);
            this._wirePaginationBtn('.top-next-btn', 'next', this._topPagination);
            this._wirePaginationBtn('.top-last-btn', 'last', this._topPagination);
        }

        this.inlineMounted = true;
    }

    /**
     * Wire a pagination button to navigate pages.
     * @param {string} selector - CSS selector for the button
     * @param {string} action - 'first', 'prev', 'next', or 'last'
     * @param {HTMLElement} [root] - Root element to query from (defaults to inlineContainer)
     */
    _wirePaginationBtn(selector, action, root) {
        const el = (root || this.inlineContainer).querySelector(selector);
        if (!el) return;
        el.addEventListener('click', (e) => {
            e.stopPropagation();
            const totalPages = Math.ceil(this.totalCount / this.pageSize);
            if (action === 'first' && this.currentPage > 1) {
                this.currentPage = 1;
            } else if (action === 'prev' && this.currentPage > 1) {
                this.currentPage--;
            } else if (action === 'next' && this.currentPage < totalPages) {
                this.currentPage++;
            } else if (action === 'last' && this.currentPage < totalPages) {
                this.currentPage = totalPages;
            } else {
                return;
            }
            this.requestDocumentList();
        });
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

            const isConversation = doc.source_type === 'conversation';
            const title = this.escapeHtml(doc.title || doc.filename);
            const statusBadge = this.getStatusBadge(doc.status);
            const statsHtml = this.buildStatsHtml(doc, fmt);

            const retryBtn = doc.status === 'failed' ? `
                <button class="inline-doc-action-btn inline-retry-btn" data-document-id="${doc.document_id}" aria-label="Retry processing" title="Retry">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23,4 23,10 17,10"></polyline><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path></svg>
                </button>` : '';

            // Delete button — disabled for active conversations (Requirements 7.1, 7.2, 7.3)
            const isActive = isConversation && this._activeThreadId && this._activeThreadId === doc.thread_id;
            const deleteTitle = isActive ? 'Cannot delete while conversation is active' : 'Delete';
            const deleteDisabled = isActive ? 'disabled' : '';
            const deleteDisabledClass = isActive ? ' delete-btn-disabled' : '';

            // Title: conversation docs get clickable span, regular docs get download link
            let titleHtml;
            if (isConversation) {
                titleHtml = `<span class="inline-doc-title conversation-title-clickable" data-thread-id="${doc.thread_id}" title="${title}">💬 ${title}</span>`;
            } else {
                titleHtml = `<a class="inline-doc-title" href="/api/documents/${encodeURIComponent(doc.document_id)}/download?redirect=true" title="${title}" target="_blank" rel="noopener">${title}</a>`;
            }

            row.innerHTML = `
                <div class="inline-doc-row-main">
                    ${titleHtml}
                    ${statusBadge}
                    ${retryBtn}
                    <button class="inline-doc-action-btn inline-delete-btn${deleteDisabledClass}" data-document-id="${doc.document_id}" ${isConversation ? `data-thread-id="${doc.thread_id}"` : ''} aria-label="Delete document" title="${deleteTitle}" ${deleteDisabled}>
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3,6 5,6 21,6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                    </button>
                </div>
                ${statsHtml}
            `;

            // Wire up stats toggle — lazy-loads stats on first expand
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
                        const statsDiv = row.querySelector('.document-stats');
                        if (!isOpen && statsDiv && !statsDiv.hasAttribute('data-stats-loaded')) {
                            statsDiv.setAttribute('data-stats-loaded', 'pending');
                            this.wsManager.send({
                                type: 'document_stats_request',
                                document_id: doc.document_id,
                            });
                        }
                    }
                });
            }

            // Related Docs button handler
            const relatedDocsBtn = row.querySelector('.document-related-docs-btn');
            if (relatedDocsBtn) {
                relatedDocsBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    e.preventDefault();
                    const displayTitle = doc.title || decodeURIComponent(doc.filename || doc.document_id);
                    this._openRelatedDocsPopup(doc.document_id, displayTitle);
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

            // Wire up conversation title click → reopen (Requirement 6.1)
            if (isConversation) {
                const titleEl = row.querySelector('.conversation-title-clickable');
                if (titleEl) {
                    titleEl.addEventListener('click', (e) => {
                        e.stopPropagation();
                        e.preventDefault();
                        if (window.chatApp && typeof window.chatApp.reopenConversation === 'function') {
                            window.chatApp.reopenConversation(doc.thread_id);
                        }
                    });

                    // Double-click title → inline edit (Requirement 9.1)
                    titleEl.addEventListener('dblclick', (e) => {
                        e.stopPropagation();
                        e.preventDefault();
                        this._startTitleEdit(titleEl, doc);
                    });
                }
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
        const firstBtn = this.inlineContainer.querySelector('.inline-first-btn');
        const prevBtn = this.inlineContainer.querySelector('.inline-prev-btn');
        const nextBtn = this.inlineContainer.querySelector('.inline-next-btn');
        const lastBtn = this.inlineContainer.querySelector('.inline-last-btn');

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
            if (firstBtn) firstBtn.disabled = this.currentPage <= 1;
            if (prevBtn) prevBtn.disabled = this.currentPage <= 1;
            if (nextBtn) nextBtn.disabled = this.currentPage >= totalPages;
            if (lastBtn) lastBtn.disabled = this.currentPage >= totalPages;

            // Also update top pagination if present
            if (this._topPagination) {
                const topFirst = this._topPagination.querySelector('.top-first-btn');
                const topPrev = this._topPagination.querySelector('.top-prev-btn');
                const topNext = this._topPagination.querySelector('.top-next-btn');
                const topLast = this._topPagination.querySelector('.top-last-btn');
                const topPageInfo = this._topPagination.querySelector('.top-page-info');
                if (topFirst) topFirst.disabled = this.currentPage <= 1;
                if (topPrev) topPrev.disabled = this.currentPage <= 1;
                if (topNext) topNext.disabled = this.currentPage >= totalPages;
                if (topLast) topLast.disabled = this.currentPage >= totalPages;
                if (topPageInfo) topPageInfo.textContent = `${this.currentPage}/${totalPages}`;
                this._topPagination.style.display = totalPages > 1 ? 'flex' : 'none';
            }

            const pagination = this.inlineContainer.querySelector('.inline-doc-pagination');
            if (pagination) pagination.style.display = totalPages > 1 ? 'flex' : 'none';
        } else {
            footer.style.display = 'none';
            if (this._topPagination) this._topPagination.style.display = 'none';
        }
    }

    // =========================================================================
    // Related Docs Graph Popup
    // =========================================================================

    /**
     * Open the Related Docs Graph popup for a document.
     *
     * @param {string} documentId - Document ID
     * @param {string} title - Document title for display
     */
    _openRelatedDocsPopup(documentId, title) {
        // If popup is already open for this document, close it (toggle behavior)
        if (this._relatedDocsPopup && this._relatedDocsPopupDocId === documentId) {
            this._closeRelatedDocsPopup();
            return;
        }

        // Close any existing popup first (only one at a time)
        if (this._relatedDocsPopup) {
            // Preserve the current threshold slider value across re-fetches
            const slider = this._relatedDocsPopup.querySelector('.related-docs-threshold-slider');
            if (slider) {
                this._savedThreshold = parseFloat(slider.value);
            }
            this._closeRelatedDocsPopup();
        }

        this._relatedDocsPopupDocId = documentId;

        // Create popup container (no backdrop — keep document list visible)
        const popup = document.createElement('div');
        popup.className = 'related-docs-popup';

        popup.innerHTML = `
            <div class="related-docs-popup-header">
                <span class="related-docs-popup-title">Related Documents: ${this.escapeHtml(title)}</span>
                <button class="related-docs-popup-close" aria-label="Close related docs popup">✕</button>
            </div>
            <div class="related-docs-popup-controls">
                <label>Threshold: <input type="range" class="related-docs-threshold-slider"
                       min="0" max="1" step="0.01" value="${this._savedThreshold != null ? this._savedThreshold : 0.3}">
                <span class="related-docs-threshold-value">${this._savedThreshold != null ? Math.round(this._savedThreshold * 100) : 30}%</span></label>
            </div>
            <div class="related-docs-popup-body">
                <div class="related-docs-popup-loading">Loading...</div>
                <div class="related-docs-popup-message" style="display:none;"></div>
            </div>
        `;

        document.body.appendChild(popup);
        this._relatedDocsPopup = popup;

        // Close handlers
        const closeBtn = popup.querySelector('.related-docs-popup-close');
        closeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this._closeRelatedDocsPopup();
        });

        // Close on click outside the popup
        this._relatedDocsOutsideClickHandler = (e) => {
            if (this._relatedDocsPopup && !this._relatedDocsPopup.contains(e.target)) {
                this._closeRelatedDocsPopup();
            }
        };
        // Delay attaching so the current click doesn't immediately close it
        setTimeout(() => {
            document.addEventListener('click', this._relatedDocsOutsideClickHandler);
        }, 100);

        this._relatedDocsEscHandler = (e) => {
            if (e.key === 'Escape') this._closeRelatedDocsPopup();
        };
        document.addEventListener('keydown', this._relatedDocsEscHandler);

        // Check WebSocket connection before sending
        if (!this.wsManager || !this.wsManager.isConnected()) {
            this._showRelatedDocsMessage('Not connected to server.');
            return;
        }

        // Send request
        this.wsManager.send({
            type: 'related_docs_graph',
            document_id: documentId
        });
    }

    /**
     * Close the Related Docs Graph popup and clean up.
     */
    _closeRelatedDocsPopup() {
        this._relatedDocsClosing = true;
        if (this._relatedDocsPopup) {
            this._relatedDocsPopup.remove();
            this._relatedDocsPopup = null;
        }
        this._relatedDocsPopupDocId = null;

        if (this._relatedDocsEscHandler) {
            document.removeEventListener('keydown', this._relatedDocsEscHandler);
            this._relatedDocsEscHandler = null;
        }
        if (this._relatedDocsOutsideClickHandler) {
            document.removeEventListener('click', this._relatedDocsOutsideClickHandler);
            this._relatedDocsOutsideClickHandler = null;
        }
    }

    /**
     * Show a message in the popup body (hides loading indicator).
     *
     * @param {string} text - Message to display
     */
    _showRelatedDocsMessage(text) {
        if (!this._relatedDocsPopup) return;
        const loading = this._relatedDocsPopup.querySelector('.related-docs-popup-loading');
        const msg = this._relatedDocsPopup.querySelector('.related-docs-popup-message');
        if (loading) loading.style.display = 'none';
        if (msg) {
            msg.textContent = text;
            msg.style.display = 'block';
        }
    }

    /**
     * Lazily load D3.js v7 from CDN. Returns a cached Promise.
     *
     * @returns {Promise<object>} Resolves with the d3 global object
     */
    _loadD3() {
        if (window.d3) return Promise.resolve(window.d3);
        if (this._d3LoadPromise) return this._d3LoadPromise;
        this._d3LoadPromise = new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = 'https://d3js.org/d3.v7.min.js';
            script.onload = () => resolve(window.d3);
            script.onerror = () => {
                this._d3LoadPromise = null;
                reject(new Error('Failed to load D3.js'));
            };
            document.head.appendChild(script);
        });
        return this._d3LoadPromise;
    }

    /**
     * Handle a document_stats WebSocket response.
     * Finds the matching stats container and renders the stats content.
     */
    _handleDocumentStatsResponse(data) {
        const docId = data.document_id;
        if (!docId) return;

        // Find all stats containers for this document (floating panel + inline)
        const containers = document.querySelectorAll(
            `.document-stats[data-doc-id="${docId}"]`
        );
        containers.forEach((statsDiv) => {
            statsDiv.setAttribute('data-stats-loaded', 'done');
            const details = statsDiv.querySelector('.document-stats-details');
            if (details) {
                this._renderStatsContent(details, data);
            }
        });
    }

    /**
     * Handle a successful related_docs_graph WebSocket response.
     *
     * @param {Object} data - Response payload with nodes and edges
     */
    _handleRelatedDocsGraphResponse(data) {
        if (!this._relatedDocsPopup) return;
        // Ignore responses for a different document
        if (data.document_id !== this._relatedDocsPopupDocId) return;

        const loading = this._relatedDocsPopup.querySelector('.related-docs-popup-loading');
        if (loading) loading.style.display = 'none';

        if (!data.edges || data.edges.length === 0) {
            this._showRelatedDocsMessage('No related documents found.');
            return;
        }

        const body = this._relatedDocsPopup.querySelector('.related-docs-popup-body');
        if (!body) return;

        this._loadD3().then(() => {
            this._renderRelatedDocsGraph(body, data);
        }).catch(() => {
            this._showRelatedDocsMessage(
                'Could not load visualization library. Please check your internet connection.'
            );
        });
    }

    /**
     * Handle a related_docs_graph_error WebSocket response.
     *
     * @param {Object} data - Error payload with message
     */
    _handleRelatedDocsGraphError(data) {
        if (!this._relatedDocsPopup) return;
        if (data.document_id !== this._relatedDocsPopupDocId) return;
        this._showRelatedDocsMessage(data.message || 'An error occurred.');
    }

    /**
     * Truncate a label string to a maximum of 30 characters.
     * Appends "…" if truncated.
     *
     * @param {string} text - The text to truncate
     * @returns {string} Truncated text
     */
    _truncateLabel(text) {
        if (!text) return '';
        if (text.length <= 30) return text;
        return text.substring(0, 30) + '\u2026';
    }

    /**
     * Render a force-directed graph of related documents using D3.js.
     *
     * Requirements: 7.6, 7.7, 7.8, 7.9, 7.10, 7.11, 7.12, 7.13, 7.14
     *
     * @param {HTMLElement} container - The popup body element to render into
     * @param {Object} data - Response payload with nodes and edges
     */
    _renderRelatedDocsGraph(container, data) {
        const d3 = window.d3;
        if (!d3 || !container) return;

        // Clear container content (loading indicator, messages)
        container.innerHTML = '';

        const width = container.clientWidth || 600;
        const height = container.clientHeight || 400;

        const CENTER_COLOR = '#4CAF50';
        const SATELLITE_COLOR = '#2196F3';
        const NODE_RADIUS = 20;
        const LABEL_OFFSET = 25;

        // Deep-copy nodes and edges so we can mutate freely
        const nodes = data.nodes.map(n => ({
            ...n,
            label: this._truncateLabel(n.title),
            isCenter: !!n.is_origin
        }));
        const edges = data.edges.map(e => ({
            source: e.source,
            target: e.target,
            score: e.score,
            edge_count: e.edge_count
        }));

        // Track current center node id
        let centerNodeId = (nodes.find(n => n.isCenter) || nodes[0] || {}).document_id;

        // Create SVG
        const svg = d3.select(container)
            .append('svg')
            .attr('width', width)
            .attr('height', height)
            .attr('class', 'related-docs-graph-svg');

        // Edge lines
        const linkGroup = svg.append('g').attr('class', 'links');
        let linkElements = linkGroup.selectAll('line')
            .data(edges)
            .enter()
            .append('line')
            .attr('stroke', '#999')
            .attr('stroke-opacity', 0.6)
            .attr('stroke-width', 2);

        // Edge labels (score as percentage)
        const linkLabelGroup = svg.append('g').attr('class', 'link-labels');
        let linkLabelElements = linkLabelGroup.selectAll('text')
            .data(edges)
            .enter()
            .append('text')
            .attr('text-anchor', 'middle')
            .attr('font-size', '10px')
            .attr('fill', '#666')
            .attr('dy', -5)
            .text(d => Math.round(d.score * 100) + '%');

        // Node circles
        const nodeGroup = svg.append('g').attr('class', 'nodes');
        let nodeElements = nodeGroup.selectAll('circle')
            .data(nodes, d => d.document_id)
            .enter()
            .append('circle')
            .attr('r', NODE_RADIUS)
            .attr('fill', d => d.document_id === centerNodeId ? CENTER_COLOR : SATELLITE_COLOR)
            .attr('stroke', '#fff')
            .attr('stroke-width', 2)
            .style('cursor', 'pointer');

        // Node labels
        const nodeLabelGroup = svg.append('g').attr('class', 'node-labels');
        let nodeLabelElements = nodeLabelGroup.selectAll('text')
            .data(nodes, d => d.document_id)
            .enter()
            .append('text')
            .attr('text-anchor', 'middle')
            .attr('font-size', '11px')
            .attr('fill', '#333')
            .attr('dy', LABEL_OFFSET)
            .text(d => d.label);

        // Force simulation — use forceX/forceY instead of forceCenter so
        // unpinned nodes drift gently toward the middle without fighting
        // the pinned center node.
        // Link distance is inversely proportional to score:
        //   score 1.0 → 60px (very close), score 0.0 → 260px (far away)
        const MIN_LINK_DIST = 60;
        const MAX_LINK_DIST = 260;
        const simulation = d3.forceSimulation(nodes)
            .force('link', d3.forceLink(edges)
                .id(d => d.document_id)
                .distance(d => MAX_LINK_DIST - (d.score || 0) * (MAX_LINK_DIST - MIN_LINK_DIST)))
            .force('charge', d3.forceManyBody().strength(-400))
            .force('x', d3.forceX(width / 2).strength(0.15))
            .force('y', d3.forceY(height / 2).strength(0.15))
            .force('collide', d3.forceCollide(NODE_RADIUS + 10))
            .on('tick', ticked);

        // Pin the initial center node so it stays at the center
        const centerNode = nodes.find(n => n.document_id === centerNodeId);
        if (centerNode) {
            centerNode.fx = width / 2;
            centerNode.fy = height / 2;
        }

        function ticked() {
            linkElements
                .attr('x1', d => d.source.x)
                .attr('y1', d => d.source.y)
                .attr('x2', d => d.target.x)
                .attr('y2', d => d.target.y);

            linkLabelElements
                .attr('x', d => (d.source.x + d.target.x) / 2)
                .attr('y', d => (d.source.y + d.target.y) / 2);

            nodeElements
                .attr('cx', d => d.x)
                .attr('cy', d => d.y);

            nodeLabelElements
                .attr('x', d => d.x)
                .attr('y', d => d.y);
        }

        // Drag behavior with click detection
        let dragStartX = 0, dragStartY = 0, wasDragged = false;
        const DRAG_THRESHOLD = 4; // pixels — below this counts as a click

        const self = this;
        const drag = d3.drag()
            .on('start', (event, d) => {
                dragStartX = event.x;
                dragStartY = event.y;
                wasDragged = false;
                if (!event.active) simulation.alphaTarget(0.3).restart();
                d.fx = d.x;
                d.fy = d.y;
            })
            .on('drag', (event, d) => {
                const dx = event.x - dragStartX;
                const dy = event.y - dragStartY;
                if (Math.abs(dx) > DRAG_THRESHOLD || Math.abs(dy) > DRAG_THRESHOLD) {
                    wasDragged = true;
                }
                d.fx = event.x;
                d.fy = event.y;
            })
            .on('end', (event, d) => {
                // --- Center-node navigation on click (Req 7.10, 7.11) ---
                if (!wasDragged && d.document_id !== centerNodeId) {
                    // Re-fetch the entire graph with the clicked node as origin.
                    // The current satellites are related to the OLD center —
                    // the new center has its own set of relationships.

                    // Save the current threshold before the popup is destroyed
                    const currentSlider = self._relatedDocsPopup &&
                        self._relatedDocsPopup.querySelector('.related-docs-threshold-slider');
                    if (currentSlider) {
                        self._savedThreshold = parseFloat(currentSlider.value);
                    }

                    self._scrollToDocument(d.document_id);
                    self._openRelatedDocsPopup(d.document_id, d.title || d.label);
                } else if (wasDragged) {
                    // Drag end — release the node (unless it's the center)
                    if (!event.active) simulation.alphaTarget(0);
                    if (d.document_id !== centerNodeId) {
                        d.fx = null;
                        d.fy = null;
                    }
                } else {
                    // Clicked the center node — show inline KG Explorer
                    if (!event.active) simulation.alphaTarget(0);
                    self._showInlineKGExplorer(d.document_id, d.title || d.label);
                }
            });

        nodeElements.call(drag);

        // --- Threshold slider filtering (Req 7.12, 7.13, 7.14) ---
        const popup = this._relatedDocsPopup;
        if (popup) {
            const slider = popup.querySelector('.related-docs-threshold-slider');
            const valueDisplay = popup.querySelector('.related-docs-threshold-value');
            if (slider) {
                const applyThreshold = () => {
                    const threshold = parseFloat(slider.value);
                    if (valueDisplay) {
                        valueDisplay.textContent = Math.round(threshold * 100) + '%';
                    }

                    // Filter edges: hide those below threshold
                    linkElements.attr('display', d => d.score >= threshold ? null : 'none');
                    linkLabelElements.attr('display', d => d.score >= threshold ? null : 'none');

                    // Determine which satellite nodes have at least one visible edge
                    const visibleNodeIds = new Set();
                    visibleNodeIds.add(centerNodeId); // Center always visible
                    edges.forEach(e => {
                        if (e.score >= threshold) {
                            const srcId = typeof e.source === 'object' ? e.source.document_id : e.source;
                            const tgtId = typeof e.target === 'object' ? e.target.document_id : e.target;
                            visibleNodeIds.add(srcId);
                            visibleNodeIds.add(tgtId);
                        }
                    });

                    nodeElements.attr('display', d => visibleNodeIds.has(d.document_id) ? null : 'none');
                    nodeLabelElements.attr('display', d => visibleNodeIds.has(d.document_id) ? null : 'none');
                };

                slider.addEventListener('input', applyThreshold);
                // Apply initial threshold
                applyThreshold();
            }
        }
    }

    // =========================================================================
    // Inline KG Explorer (rendered inside Related Docs popup)
    // =========================================================================

    /**
     * Show the KG Explorer graph inline within the Related Docs popup,
     * replacing the Related Docs content. A back arrow restores the previous view.
     *
     * @param {string} documentId - Document ID to explore
     * @param {string} title - Document title for display
     */
    async _showInlineKGExplorer(documentId, title) {
        const popup = this._relatedDocsPopup;
        if (!popup) return;

        // Save current popup body HTML so we can restore on back
        const body = popup.querySelector('.related-docs-popup-body');
        const controls = popup.querySelector('.related-docs-popup-controls');
        const headerTitle = popup.querySelector('.related-docs-popup-title');
        if (!body) return;

        // Stash the current Related Docs state
        this._relatedDocsStashedBody = body.innerHTML;
        this._relatedDocsStashedControls = controls ? controls.style.display : '';
        this._relatedDocsStashedTitle = headerTitle ? headerTitle.textContent : '';

        // Hide threshold controls
        if (controls) controls.style.display = 'none';

        // Update header: add back button, change title
        if (headerTitle) headerTitle.textContent = `Knowledge Graph: ${this.escapeHtml(title)}`;

        // Add back button if not already present
        let backBtn = popup.querySelector('.related-docs-kg-back-btn');
        if (!backBtn) {
            backBtn = document.createElement('button');
            backBtn.className = 'related-docs-kg-back-btn';
            backBtn.setAttribute('aria-label', 'Back to Related Documents');
            backBtn.title = 'Back to Related Documents';
            backBtn.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                     stroke="currentColor" stroke-width="2">
                    <polyline points="15,18 9,12 15,6"></polyline>
                </svg>
            `;
            backBtn.addEventListener('click', (e) => { e.stopPropagation(); this._hideInlineKGExplorer(); });
            const header = popup.querySelector('.related-docs-popup-header');
            if (header) header.insertBefore(backBtn, header.firstChild);
        }
        backBtn.style.display = 'flex';

        // Show loading in body
        body.innerHTML = '<div class="related-docs-popup-loading">Loading knowledge graph…</div>';

        // Initialize KG Explorer state for this popup
        this._inlineKG = {
            documentId,
            focusNode: null,
            navigationHistory: [],
            simulation: null,
            svg: null,
            currentNodes: [],
            currentEdges: [],
            maxNodes: 50
        };

        // Fetch and render
        try {
            const data = await this._fetchKGNeighborhood(documentId, null);
            if (data.is_landing) {
                this._renderInlineKGLanding(body, data.nodes);
            } else {
                this._renderInlineKGGraph(body, data.nodes, data.edges, data.focus_concept);
            }
        } catch (err) {
            body.innerHTML = `<div class="related-docs-popup-message" style="display:block;">
                ${err.status === 503 ? 'Knowledge graph service unavailable' : 'Error loading graph data'}
            </div>`;
        }
    }

    /**
     * Restore the Related Docs view from the inline KG Explorer.
     */
    _hideInlineKGExplorer() {
        const popup = this._relatedDocsPopup;
        if (!popup) return;

        // Stop any running KG simulation
        if (this._inlineKG && this._inlineKG.simulation) {
            this._inlineKG.simulation.stop();
        }
        this._inlineKG = null;

        // Restore body
        const body = popup.querySelector('.related-docs-popup-body');
        if (body && this._relatedDocsStashedBody != null) {
            body.innerHTML = this._relatedDocsStashedBody;
        }

        // Restore controls
        const controls = popup.querySelector('.related-docs-popup-controls');
        if (controls) controls.style.display = this._relatedDocsStashedControls || '';

        // Restore title
        const headerTitle = popup.querySelector('.related-docs-popup-title');
        if (headerTitle && this._relatedDocsStashedTitle) {
            headerTitle.textContent = this._relatedDocsStashedTitle;
        }

        // Hide back button
        const backBtn = popup.querySelector('.related-docs-kg-back-btn');
        if (backBtn) backBtn.style.display = 'none';

        // Re-render the graph since we restored raw HTML (need to re-run D3)
        // Trigger a re-fetch of the related docs graph
        if (this._relatedDocsPopupDocId && this.wsManager && this.wsManager.isConnected()) {
            const loading = body.querySelector('.related-docs-popup-loading');
            if (loading) loading.style.display = 'block';
            const msg = body.querySelector('.related-docs-popup-message');
            if (msg) msg.style.display = 'none';
            this.wsManager.send({
                type: 'related_docs_graph',
                document_id: this._relatedDocsPopupDocId
            });
        }

        this._relatedDocsStashedBody = null;
        this._relatedDocsStashedControls = null;
        this._relatedDocsStashedTitle = null;
    }

    /**
     * Fetch KG neighborhood data via REST API.
     *
     * @param {string} sourceId - Document ID
     * @param {string|null} focusConcept - Concept to focus on, or null for landing
     * @returns {Promise<Object>} Neighborhood data
     */
    async _fetchKGNeighborhood(sourceId, focusConcept) {
        const maxNodes = (this._inlineKG && this._inlineKG.maxNodes) || 50;
        const params = new URLSearchParams({ max_nodes: String(maxNodes) });
        if (focusConcept) params.set('focus_concept', focusConcept);

        const resp = await fetch(
            `/api/knowledge-graph/${encodeURIComponent(sourceId)}/neighborhood?${params}`
        );
        if (!resp.ok) throw Object.assign(new Error(), { status: resp.status });
        return resp.json();
    }

    /**
     * Render KG landing view (top concepts list) inside the popup body.
     *
     * @param {HTMLElement} container - The popup body element
     * @param {Array} nodes - Top concept nodes
     */
    _renderInlineKGLanding(container, nodes) {
        container.innerHTML = '';

        if (!nodes || nodes.length === 0) {
            container.innerHTML = '<div class="related-docs-popup-message" style="display:block;">No concepts found for this source.</div>';
            return;
        }

        const list = document.createElement('div');
        list.className = 'kg-explorer-landing';
        list.style.margin = '0 auto';
        list.innerHTML = '<h3 class="kg-explorer-landing-title">Top concepts — click to explore</h3>';

        const ul = document.createElement('ul');
        ul.className = 'kg-explorer-landing-list';
        ul.setAttribute('role', 'list');

        const nodeColorFn = (sourceType) => {
            if (sourceType === 'external') return '#50C878';
            if (sourceType === 'conversation') return '#9b59b6';
            return '#4A90D9';
        };

        nodes.forEach(node => {
            const li = document.createElement('li');
            li.className = 'kg-explorer-landing-item';
            li.setAttribute('role', 'listitem');
            li.setAttribute('tabindex', '0');
            li.style.cursor = 'pointer';

            const color = nodeColorFn(node.source_type);
            li.innerHTML = `
                <span class="kg-landing-dot" style="background:${color}"></span>
                <span class="kg-landing-name">${this.escapeHtml(node.name)}</span>
                <span class="kg-landing-degree" title="Relationships">${node.degree}</span>
            `;

            li.addEventListener('click', (e) => {
                e.stopPropagation();
                this._navigateInlineKG(node.name);
            });
            li.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    this._navigateInlineKG(node.name);
                }
            });
            ul.appendChild(li);
        });

        list.appendChild(ul);
        container.appendChild(list);
    }

    /**
     * Navigate to a concept neighborhood within the inline KG Explorer.
     *
     * @param {string} conceptName - Concept to navigate to
     */
    async _navigateInlineKG(conceptName) {
        if (!this._inlineKG || !this._relatedDocsPopup) return;

        const body = this._relatedDocsPopup.querySelector('.related-docs-popup-body');
        if (!body) return;

        // Push current focus to history (null means "landing view")
        this._inlineKG.navigationHistory.push(this._inlineKG.focusNode || null);

        // Update focusNode BEFORE updating back button so state is correct
        this._inlineKG.focusNode = conceptName;
        this._updateInlineKGBackButton();

        body.innerHTML = '<div class="related-docs-popup-loading">Loading neighborhood…</div>';

        try {
            const data = await this._fetchKGNeighborhood(this._inlineKG.documentId, conceptName);
            if (!data.nodes || data.nodes.length === 0) {
                body.innerHTML = `<div class="related-docs-popup-message" style="display:block;">No neighborhood data found for "${this.escapeHtml(conceptName)}"</div>`;
                // Revert: pop history and restore focusNode
                if (this._inlineKG.navigationHistory.length > 0) {
                    this._inlineKG.focusNode = this._inlineKG.navigationHistory.pop();
                    this._updateInlineKGBackButton();
                }
                return;
            }
            this._renderInlineKGGraph(body, data.nodes, data.edges, conceptName);
        } catch {
            body.innerHTML = '<div class="related-docs-popup-message" style="display:block;">Error loading graph data</div>';
            if (this._inlineKG.navigationHistory.length > 0) {
                this._inlineKG.focusNode = this._inlineKG.navigationHistory.pop();
                this._updateInlineKGBackButton();
            }
        }
    }

    /**
     * Go back in the inline KG Explorer navigation history.
     */
    async _navigateInlineKGBack() {
        if (!this._inlineKG || !this._relatedDocsPopup) return;

        const body = this._relatedDocsPopup.querySelector('.related-docs-popup-body');
        if (!body) return;

        if (this._inlineKG.navigationHistory.length === 0) {
            // No history at all — back to Related Docs
            this._hideInlineKGExplorer();
            return;
        }

        const prev = this._inlineKG.navigationHistory.pop();

        if (prev === null) {
            // Previous state was landing view
            this._inlineKG.focusNode = null;
            this._updateInlineKGBackButton();
            body.innerHTML = '<div class="related-docs-popup-loading">Loading concepts…</div>';
            try {
                const data = await this._fetchKGNeighborhood(this._inlineKG.documentId, null);
                if (data.is_landing) {
                    this._renderInlineKGLanding(body, data.nodes);
                } else {
                    this._renderInlineKGGraph(body, data.nodes, data.edges, data.focus_concept);
                }
            } catch {
                body.innerHTML = '<div class="related-docs-popup-message" style="display:block;">Error loading graph data</div>';
            }
            return;
        }

        // Navigate to previous concept
        this._inlineKG.focusNode = prev;
        this._updateInlineKGBackButton();
        body.innerHTML = '<div class="related-docs-popup-loading">Loading neighborhood…</div>';

        try {
            const data = await this._fetchKGNeighborhood(this._inlineKG.documentId, prev);
            this._renderInlineKGGraph(body, data.nodes, data.edges, prev);
        } catch {
            body.innerHTML = '<div class="related-docs-popup-message" style="display:block;">Error loading graph data</div>';
        }
    }

    /**
     * Update the back button behavior based on KG navigation state.
     * When in KG mode with history, back navigates KG history.
     * When in KG mode with no history, back returns to Related Docs.
     */
    _updateInlineKGBackButton() {
        const popup = this._relatedDocsPopup;
        if (!popup) return;

        const backBtn = popup.querySelector('.related-docs-kg-back-btn');
        if (!backBtn) return;

        // Clone and replace to remove old listeners
        const newBtn = backBtn.cloneNode(true);
        backBtn.parentNode.replaceChild(newBtn, backBtn);

        if (this._inlineKG && this._inlineKG.navigationHistory.length > 0) {
            // Has history — back navigates to previous concept or landing
            newBtn.title = 'Back';
            newBtn.addEventListener('click', (e) => { e.stopPropagation(); this._navigateInlineKGBack(); });
        } else {
            // No history — back returns to Related Docs
            newBtn.title = 'Back to Related Documents';
            newBtn.addEventListener('click', (e) => { e.stopPropagation(); this._hideInlineKGExplorer(); });
        }
    }

    /**
     * Render the KG force-directed graph inside the popup body.
     *
     * @param {HTMLElement} container - The popup body element
     * @param {Array} nodes - Concept nodes
     * @param {Array} edges - Relationship edges
     * @param {string|null} focusConcept - The focused concept name
     */
    _renderInlineKGGraph(container, nodes, edges, focusConcept) {
        const d3 = window.d3;
        if (!d3 || !container || !this._inlineKG) return;

        this._inlineKG.focusNode = focusConcept;
        this._inlineKG.currentNodes = nodes;
        this._inlineKG.currentEdges = edges;

        container.innerHTML = '';

        // Use explicit pixel dimensions (fallback to sensible defaults)
        const width = container.clientWidth || 600;
        const height = container.clientHeight || 400;

        // Build SVG with explicit pixel dimensions (like Related Docs graph)
        const svg = d3.select(container)
            .append('svg')
            .attr('width', width)
            .attr('height', height)
            .attr('role', 'img')
            .attr('aria-label', 'Knowledge graph visualization');

        this._inlineKG.svg = svg;

        // Arrow marker
        svg.append('defs').append('marker')
            .attr('id', 'kg-inline-arrow')
            .attr('viewBox', '0 -5 10 10')
            .attr('refX', 28).attr('refY', 0)
            .attr('markerWidth', 6).attr('markerHeight', 6)
            .attr('orient', 'auto')
            .append('path').attr('d', 'M0,-5L10,0L0,5').attr('fill', '#94a3b8');

        const nodeColorFn = (sourceType) => {
            if (sourceType === 'external') return '#50C878';
            if (sourceType === 'conversation') return '#9b59b6';
            return '#4A90D9';
        };

        // Prepare data — deduplicate nodes by name, filter self-edges
        const nodeMap = new Map(nodes.map(n => [n.name, { ...n }]));
        const links = edges
            .filter(e => e.source !== e.target && nodeMap.has(e.source) && nodeMap.has(e.target))
            .map(e => ({
                source: e.source,
                target: e.target,
                relationship_type: e.relationship_type,
            }));
        const nodeData = Array.from(nodeMap.values());

        // Force simulation
        if (this._inlineKG.simulation) this._inlineKG.simulation.stop();

        this._inlineKG.simulation = d3.forceSimulation(nodeData)
            .force('link', d3.forceLink(links).id(d => d.name).distance(80).strength(0.5))
            .force('charge', d3.forceManyBody().strength(-200))
            .force('center', d3.forceCenter(width / 2, height / 2))
            .force('collide', d3.forceCollide(30));

        // Edge group
        const edgeG = svg.append('g').attr('class', 'kg-edges');
        const link = edgeG.selectAll('g').data(links).join('g').attr('class', 'kg-edge-group');
        link.append('line').attr('class', 'kg-edge').attr('marker-end', 'url(#kg-inline-arrow)');
        link.append('text').attr('class', 'kg-edge-label').text(d => d.relationship_type);

        // Node group
        const nodeG = svg.append('g').attr('class', 'kg-nodes');
        const node = nodeG.selectAll('g')
            .data(nodeData, d => d.name)
            .join('g')
            .attr('class', 'kg-node-group')
            .style('cursor', 'pointer');

        // Focus ring
        node.append('circle')
            .attr('class', 'kg-node-ring')
            .attr('r', 22).attr('fill', 'none')
            .attr('stroke', d => d.name === focusConcept ? '#f59e0b' : 'none')
            .attr('stroke-width', 3);

        // Node circle
        node.append('circle')
            .attr('class', 'kg-node-circle')
            .attr('r', 16)
            .attr('fill', d => nodeColorFn(d.source_type));

        // Node label
        node.append('text')
            .attr('class', 'kg-node-label')
            .attr('dy', -22)
            .text(d => d.name && d.name.length > 20 ? d.name.substring(0, 20) + '…' : (d.name || ''));

        // Source subtitle
        node.append('text')
            .attr('class', 'kg-node-subtitle')
            .attr('dy', 30)
            .text(d => {
                const t = d.source_title || d.source_document || '';
                return t.length > 18 ? t.substring(0, 18) + '…' : t;
            });

        // Tooltip container
        let tooltip = container.querySelector('.kg-node-tooltip');
        if (!tooltip) {
            tooltip = document.createElement('div');
            tooltip.className = 'kg-node-tooltip';
            tooltip.setAttribute('aria-hidden', 'true');
            container.style.position = 'relative';
            container.appendChild(tooltip);
        }

        const self = this;

        // Hover tooltip
        node.on('mouseover', function (_event, d) {
            const relCount = links.filter(
                e => (e.source.name || e.source) === d.name || (e.target.name || e.target) === d.name
            ).length;
            const sourceLabel = d.source_title || d.source_document || '';
            tooltip.innerHTML = `
                <div class="kg-tooltip-name">${self.escapeHtml(d.name)}</div>
                <div class="kg-tooltip-row"><span>Source:</span><span>${self.escapeHtml(sourceLabel)}</span></div>
                <div class="kg-tooltip-row"><span>Type:</span><span>${self.escapeHtml(d.source_type || '')}</span></div>
                <div class="kg-tooltip-row"><span>Degree:</span><span>${d.degree ?? relCount}</span></div>
            `;
            tooltip.classList.add('kg-tooltip-visible');
        }).on('mouseout', () => {
            tooltip.classList.remove('kg-tooltip-visible');
        });

        // Click: focus node shows detail, others navigate
        node.on('click', (event, d) => {
            event.stopPropagation();
            tooltip.classList.remove('kg-tooltip-visible');
            if (d.name === focusConcept) {
                // Could show detail — for now just no-op on focus node
            } else {
                self._navigateInlineKG(d.name);
            }
        });

        // Drag behavior
        const drag = d3.drag()
            .on('start', (event, d) => {
                if (!event.active) self._inlineKG.simulation.alphaTarget(0.3).restart();
                d.fx = d.x; d.fy = d.y;
                tooltip.classList.remove('kg-tooltip-visible');
            })
            .on('drag', (event, d) => {
                d.fx = event.x; d.fy = event.y;
                tooltip.classList.remove('kg-tooltip-visible');
            })
            .on('end', (event, d) => {
                if (!event.active) self._inlineKG.simulation.alphaTarget(0);
                d.fx = null; d.fy = null;
            });
        node.call(drag);

        // Tick
        this._inlineKG.simulation.on('tick', () => {
            link.select('line')
                .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
                .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
            link.select('text')
                .attr('x', d => (d.source.x + d.target.x) / 2)
                .attr('y', d => (d.source.y + d.target.y) / 2);
            node.attr('transform', d => `translate(${d.x},${d.y})`);
        });

        this._updateInlineKGBackButton();
    }

    /**
     * Scroll the document list panel to a specific document and highlight it.
     * If the document isn't on the current page, pages through the list to find it.
     *
     * Requirement: 7.11
     *
     * @param {string} documentId - The document ID to scroll to
     */
    _scrollToDocument(documentId) {
        // Clear any previous persistent highlight
        document.querySelectorAll('.document-highlight').forEach(el => {
            el.classList.remove('document-highlight');
        });

        // Try inline container first, then floating panel
        const containers = [this.inlineContainer, this.panelElement].filter(Boolean);
        for (const container of containers) {
            const target = container.querySelector(`[data-document-id="${documentId}"]`);
            if (target) {
                target.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                target.classList.add('document-highlight');
                return;
            }
        }

        // Document not on current page — start searching from page 1
        this._pendingScrollDocId = documentId;
        this.currentPage = 1;
        this.requestDocumentList();
    }
}

// Export for use in other modules
window.DocumentListPanel = DocumentListPanel;
