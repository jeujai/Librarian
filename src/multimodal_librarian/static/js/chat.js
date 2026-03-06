/**
 * Main chat application controller
 */

class ChatApp {
    constructor() {
        this.wsManager = new WebSocketManager();
        this.currentThreadId = null;
        this.messageHistory = [];

        // Initialize CitationPopup singleton (Requirements: 1.2, 2.2)
        this.initializeCitationPopup();

        this.initializeElements();
        this.setupEventListeners();
        this.setupWebSocketHandlers();

        // Connect to WebSocket first, then initialize file handler
        // ChatUploadHandler needs wsManager to be available
        this.wsManager.connect();

        // Initialize ChatUploadHandler after WebSocket is set up
        // Requirements: 1.1, 1.2, 1.3
        this.initializeChatUploadHandler();
        this.setupFileHandlers();

        // Initialize DocumentListPanel (Requirements: 8.1, 8.2)
        this.initializeDocumentListPanel();

        // Initialize upload dropdown (Requirements: 8.1, 8.2)
        this.initializeUploadDropdown();

        // Focus on input
        this.messageInput.focus();
    }

    /**
     * Initialize ChatUploadHandler for chat-integrated document uploads.
     * Uses ChatUploadHandler if available, falls back to FileHandler.
     * 
     * Requirements: 1.1, 1.2, 1.3
     */
    initializeChatUploadHandler() {
        if (typeof ChatUploadHandler !== 'undefined') {
            this.fileHandler = new ChatUploadHandler(this.wsManager, this);
            console.log('ChatUploadHandler initialized for chat document uploads');
        } else {
            // Fallback to basic FileHandler if ChatUploadHandler not loaded
            this.fileHandler = new FileHandler();
            console.warn('ChatUploadHandler not available, using basic FileHandler');
        }
    }

    /**
     * Initialize DocumentListPanel for viewing and managing documents.
     * 
     * Requirements: 8.1, 8.2
     */
    initializeDocumentListPanel() {
        if (typeof DocumentListPanel !== 'undefined') {
            this.documentListPanel = new DocumentListPanel(this.wsManager);
            console.log('DocumentListPanel initialized');
        } else {
            this.documentListPanel = null;
            console.warn('DocumentListPanel not available');
        }
    }

    /**
     * Initialize upload dropdown with "Upload PDF" and "View Documents" options.
     * 
     * Requirements: 8.1, 8.2
     */
    initializeUploadDropdown() {
        // Create dropdown container
        this.uploadDropdown = document.createElement('div');
        this.uploadDropdown.className = 'upload-dropdown';
        this.uploadDropdown.id = 'uploadDropdown';
        this.uploadDropdown.style.display = 'none';
        this.uploadDropdown.setAttribute('role', 'menu');
        this.uploadDropdown.setAttribute('aria-label', 'Upload options');

        this.uploadDropdown.innerHTML = `
            <button class="upload-dropdown-item" data-action="upload" role="menuitem">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                    <polyline points="17,8 12,3 7,8"></polyline>
                    <line x1="12" y1="3" x2="12" y2="15"></line>
                </svg>
                <span>Upload PDF</span>
            </button>
            <div id="inlineDocumentListSlot" class="inline-document-list-slot"></div>
        `;

        // Insert dropdown after upload button
        if (this.uploadBtn && this.uploadBtn.parentNode) {
            this.uploadBtn.parentNode.insertBefore(this.uploadDropdown, this.uploadBtn.nextSibling);
        }

        // Mount DocumentListPanel inline into the dropdown slot
        if (this.documentListPanel) {
            const slot = this.uploadDropdown.querySelector('#inlineDocumentListSlot');
            if (slot) {
                this.documentListPanel.mountInline(slot);
            }
        }

        // Set up dropdown event listeners
        this.setupUploadDropdownListeners();
    }

    /**
     * Set up event listeners for upload dropdown.
     */
    setupUploadDropdownListeners() {
        // Upload option
        const uploadOption = this.uploadDropdown.querySelector('[data-action="upload"]');
        if (uploadOption) {
            uploadOption.addEventListener('click', (e) => {
                e.stopPropagation();
                this.hideUploadDropdown();
                this.fileInput.click();
            });
        }

        // Close dropdown when clicking outside
        document.addEventListener('click', (e) => {
            if (this.isUploadDropdownVisible &&
                !this.uploadDropdown.contains(e.target) &&
                !this.uploadBtn.contains(e.target)) {
                this.hideUploadDropdown();
            }
        });

        // Close dropdown on Escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.isUploadDropdownVisible) {
                this.hideUploadDropdown();
                this.uploadBtn.focus();
            }
        });
    }

    /**
     * Show upload dropdown.
     */
    showUploadDropdown() {
        if (!this.uploadDropdown) return;

        // Position dropdown relative to upload button
        const btnRect = this.uploadBtn.getBoundingClientRect();
        this.uploadDropdown.style.position = 'absolute';
        this.uploadDropdown.style.bottom = '100%';
        this.uploadDropdown.style.left = '0';
        this.uploadDropdown.style.marginBottom = '4px';

        this.uploadDropdown.style.display = 'block';
        this.isUploadDropdownVisible = true;

        // Refresh inline document list
        if (this.documentListPanel) {
            this.documentListPanel.refreshInline();
        }

        // Focus first item for accessibility
        const firstItem = this.uploadDropdown.querySelector('.upload-dropdown-item');
        if (firstItem) {
            firstItem.focus();
        }
    }

    /**
     * Hide upload dropdown.
     */
    hideUploadDropdown() {
        if (!this.uploadDropdown) return;
        this.uploadDropdown.style.display = 'none';
        this.isUploadDropdownVisible = false;
    }

    /**
     * Toggle upload dropdown visibility.
     */
    toggleUploadDropdown() {
        if (this.isUploadDropdownVisible) {
            this.hideUploadDropdown();
        } else {
            this.showUploadDropdown();
        }
    }

    /**
     * Show document list panel.
     * 
     * Requirements: 8.1, 8.2
     */
    showDocumentListPanel() {
        if (this.documentListPanel) {
            this.documentListPanel.show(this.uploadBtn);
        } else {
            this.addSystemMessage('Document list panel not available', 'error');
        }
    }

    /**
     * Initialize CitationPopup singleton and wire to CitationRenderer
     * Requirements: 1.2, 2.2
     */
    initializeCitationPopup() {
        // Create singleton CitationPopup instance
        if (typeof CitationPopup !== 'undefined') {
            this.citationPopup = new CitationPopup();

            // Wire CitationRenderer to use this popup instance
            if (typeof CitationRenderer !== 'undefined') {
                CitationRenderer.setCitationPopup(this.citationPopup);
            }

            // Also expose globally for other components
            window.citationPopup = this.citationPopup;
        } else {
            console.warn('CitationPopup class not available - citation popups will be disabled');
            this.citationPopup = null;
        }
    }

    /**
     * Initialize DOM elements
     */
    initializeElements() {
        this.chatMessages = document.getElementById('chatMessages');
        this.messageInput = document.getElementById('messageInput');
        this.chatForm = document.getElementById('chatForm');
        this.sendBtn = document.getElementById('sendBtn');
        this.uploadBtn = document.getElementById('uploadBtn');
        this.fileInput = document.getElementById('fileInput');
        this.processingIndicator = document.getElementById('processingIndicator');
        this.newChatBtn = document.getElementById('newChatBtn');
        this.exportBtn = document.getElementById('exportBtn');
        this.characterCount = document.getElementById('characterCount');
    }

    /**
     * Set up event listeners
     */
    setupEventListeners() {
        // Form submission
        this.chatForm.addEventListener('submit', (e) => {
            e.preventDefault();
            this.sendMessage();
        });

        // Input handling
        this.messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        this.messageInput.addEventListener('input', () => {
            this.autoResizeTextarea();
            this.updateSendButton();
            this.updateCharacterCount();
        });

        // Upload button - show dropdown (Requirements: 8.1, 8.2)
        this.uploadBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.toggleUploadDropdown();
        });

        // File input
        this.fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                this.fileHandler.handleFiles(e.target.files);
                e.target.value = ''; // Reset input
            }
        });

        // Header buttons
        this.newChatBtn.addEventListener('click', () => {
            this.clearChat();
        });

        this.exportBtn.addEventListener('click', () => {
            this.showExportOptions();
        });

        // Window events
        window.addEventListener('beforeunload', () => {
            this.wsManager.disconnect();
        });

        // Accessibility: Focus management
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.messageInput.focus();
            }

            // Alt + N for new chat
            if (e.altKey && e.key === 'n') {
                e.preventDefault();
                this.clearChat();
            }

            // Alt + E for export
            if (e.altKey && e.key === 'e') {
                e.preventDefault();
                this.showExportOptions();
            }

            // Alt + U for upload
            if (e.altKey && e.key === 'u') {
                e.preventDefault();
                this.fileInput.click();
            }
        });
    }

    /**
     * Set up WebSocket event handlers
     */
    setupWebSocketHandlers() {
        // Track streaming state
        this.streamingState = {
            isStreaming: false,
            currentMessageElement: null,
            currentContent: '',
            citations: []
        };

        this.wsManager.on('connected', () => {
            console.log('Chat connected to server');
            this.startNewConversation();
        });

        this.wsManager.on('disconnected', () => {
            console.log('Chat disconnected from server');
        });

        this.wsManager.on('message', (data) => {
            this.handleServerMessage(data);
        });

        this.wsManager.on('response', (data) => {
            this.handleChatResponse(data);
        });

        this.wsManager.on('error', (data) => {
            this.handleServerError(data);
        });

        this.wsManager.on('processing', (data) => {
            this.showProcessingIndicator(data.message || 'Processing...');
        });

        this.wsManager.on('processing_complete', () => {
            this.hideProcessingIndicator();
        });

        this.wsManager.on('export_ready', (data) => {
            this.handleExportReady(data);
        });

        // Streaming response handlers
        this.wsManager.on('streaming_start', (data) => {
            this.handleStreamingStart(data);
        });

        this.wsManager.on('response_chunk', (data) => {
            this.handleStreamingChunk(data);
        });

        this.wsManager.on('response_complete', (data) => {
            this.handleStreamingComplete(data);
        });

        this.wsManager.on('streaming_error', (data) => {
            this.handleStreamingError(data);
        });

        this.wsManager.on('timeout_notification', (data) => {
            this.handleTimeoutNotification(data);
        });

        // Document processing status handlers (Requirements: 3.5, 3.6, 4.1, 4.2, 4.3, 4.4, 4.5)
        this.wsManager.on('document_processing_status', (data) => {
            this.handleDocumentProcessingStatus(data);
        });

        this.wsManager.on('document_upload_started', (data) => {
            this.handleDocumentUploadStarted(data);
        });

        this.wsManager.on('document_upload_error', (data) => {
            this.handleDocumentUploadError(data);
        });
    }

    /**
     * Handle streaming start - create message element and store citations
     */
    handleStreamingStart(data) {
        console.log('Streaming started with citations:', data.citations?.length || 0);

        // Hide processing indicator
        this.hideProcessingIndicator();

        // Create a new message element for streaming content
        this.streamingState.isStreaming = true;
        this.streamingState.currentContent = '';
        this.streamingState.citations = data.citations || [];

        // Create message element
        const messageElement = this.createMessageElement('system', '');
        this.streamingState.currentMessageElement = messageElement;
        this.chatMessages.appendChild(messageElement);
        this.scrollToBottom();
    }

    /**
     * Handle streaming chunk - append content to current message
     * Uses CitationRenderer to make inline citations clickable
     * Requirements: 1.1, 1.2
     */
    handleStreamingChunk(data) {
        if (!this.streamingState.isStreaming || !this.streamingState.currentMessageElement) {
            return;
        }

        // Append content
        this.streamingState.currentContent += data.content || '';

        // Update message element
        const contentDiv = this.streamingState.currentMessageElement.querySelector('.message-content');
        if (contentDiv) {
            // Clear and re-render content
            contentDiv.innerHTML = '';
            const paragraphs = this.streamingState.currentContent.split('\n\n');
            paragraphs.forEach(paragraph => {
                if (paragraph.trim()) {
                    const p = document.createElement('p');

                    // Use CitationRenderer to render inline citations as clickable elements
                    if (typeof CitationRenderer !== 'undefined' && this.streamingState.citations.length > 0) {
                        const renderedContent = CitationRenderer.renderCitations(
                            paragraph.trim(),
                            this.streamingState.citations
                        );
                        p.appendChild(renderedContent);
                    } else {
                        // Fallback to plain text if CitationRenderer not available
                        p.textContent = paragraph.trim();
                    }

                    contentDiv.appendChild(p);
                }
            });
        }

        this.scrollToBottom();
    }

    /**
     * Handle streaming complete - finalize message and add citations
     * Re-renders content with CitationRenderer for final inline citations
     * Requirements: 1.1, 1.2
     */
    handleStreamingComplete(data) {
        console.log('Streaming complete:', data.metadata);

        this.streamingState.isStreaming = false;

        // Re-render final content with CitationRenderer for inline citations
        if (this.streamingState.currentMessageElement) {
            const contentDiv = this.streamingState.currentMessageElement.querySelector('.message-content');
            if (contentDiv && this.streamingState.currentContent) {
                contentDiv.innerHTML = '';
                const paragraphs = this.streamingState.currentContent.split('\n\n');
                paragraphs.forEach(paragraph => {
                    if (paragraph.trim()) {
                        const p = document.createElement('p');

                        // Use CitationRenderer to render inline citations as clickable elements
                        if (typeof CitationRenderer !== 'undefined' && this.streamingState.citations.length > 0) {
                            const renderedContent = CitationRenderer.renderCitations(
                                paragraph.trim(),
                                this.streamingState.citations
                            );
                            p.appendChild(renderedContent);
                        } else {
                            p.textContent = paragraph.trim();
                        }

                        contentDiv.appendChild(p);
                    }
                });
            }
        }

        // Add citations list if available
        if (this.streamingState.citations.length > 0 && this.streamingState.currentMessageElement) {
            this.addCitationsToElement(this.streamingState.currentMessageElement, this.streamingState.citations);
        }

        // Add to message history
        this.messageHistory.push({
            type: 'system',
            content: this.streamingState.currentContent,
            messageType: 'info',
            timestamp: new Date(),
            metadata: data.metadata,
            citations: this.streamingState.citations // Store citations for popup access
        });

        // Reset streaming state
        this.streamingState.currentMessageElement = null;
        this.streamingState.currentContent = '';
        this.streamingState.citations = [];

        this.scrollToBottom();
    }

    /**
     * Handle streaming error
     */
    handleStreamingError(data) {
        console.error('Streaming error:', data.error);

        this.streamingState.isStreaming = false;

        if (data.recoverable) {
            this.showProcessingIndicator('Recovering...');
        } else {
            this.addSystemMessage(`Error: ${data.error}`, 'error');
        }

        // Reset streaming state
        this.streamingState.currentMessageElement = null;
        this.streamingState.currentContent = '';
        this.streamingState.citations = [];
    }

    /**
     * Handle timeout notification
     */
    handleTimeoutNotification(data) {
        console.warn('Timeout notification:', data.message);
        this.addSystemMessage(data.message, 'warning');
    }

    /**
     * Handle document processing status updates from WebSocket.
     * Creates or updates processing status cards in the chat UI.
     * 
     * Requirements: 3.5, 3.6, 4.1, 4.2, 4.3, 4.4, 4.5
     * 
     * @param {Object} data - Processing status message data
     */
    handleDocumentProcessingStatus(data) {
        const { document_id, filename, status, progress_percentage, current_stage, error_message, summary, metadata } = data;

        console.log('Document processing status:', status, progress_percentage + '%', current_stage);

        // Delegate to ChatUploadHandler if available (it has the full implementation)
        if (this.fileHandler && this.fileHandler instanceof ChatUploadHandler) {
            this.fileHandler.showProcessingStatus(data);
            return;
        }

        // Fallback: Create/update status card directly in chat.js
        let statusCard = document.getElementById(`processing-status-${document_id}`);

        if (!statusCard) {
            statusCard = this.createProcessingStatusCard(document_id, filename);
        }

        this.updateProcessingStatusCard(statusCard, {
            status: status,
            progress: progress_percentage,
            stage: current_stage,
            error: error_message,
            summary: summary,
            metadata: metadata
        });
    }

    /**
     * Handle document upload started confirmation.
     * 
     * @param {Object} data - Upload started message data
     */
    handleDocumentUploadStarted(data) {
        console.log('Document upload started:', data.filename);

        // Delegate to ChatUploadHandler if available
        if (this.fileHandler && this.fileHandler instanceof ChatUploadHandler) {
            this.fileHandler.handleUploadStarted(data);
            return;
        }

        // Fallback: Create status card directly
        this.createProcessingStatusCard(data.document_id, data.filename);
    }

    /**
     * Handle document upload error.
     * 
     * @param {Object} data - Upload error message data
     */
    handleDocumentUploadError(data) {
        console.error('Document upload error:', data);

        // Delegate to ChatUploadHandler if available
        if (this.fileHandler && this.fileHandler instanceof ChatUploadHandler) {
            this.fileHandler.handleUploadError(data);
            return;
        }

        // Fallback: Show error message
        this.addSystemMessage(
            `Upload failed for ${data.filename}: ${data.error_message}`,
            'error'
        );
    }

    /**
     * Create a processing status card in the chat UI.
     * 
     * Requirements: 4.1, 4.2
     * 
     * @param {string} documentId - Document ID
     * @param {string} filename - Document filename
     * @returns {HTMLElement} The created status card element
     */
    createProcessingStatusCard(documentId, filename) {
        const card = document.createElement('div');
        card.className = 'processing-status-card status-processing';
        card.id = `processing-status-${documentId}`;
        card.setAttribute('data-document-id', documentId);
        card.setAttribute('role', 'status');
        card.setAttribute('aria-live', 'polite');
        card.setAttribute('aria-label', `Processing status for ${filename}`);

        card.innerHTML = `
            <div class="processing-status-header">
                <span class="processing-icon" aria-hidden="true">📄</span>
                <span class="processing-filename">${this.escapeHtml(filename)}</span>
            </div>
            <div class="processing-status-body">
                <div class="processing-stage">Queued for processing...</div>
                <div class="processing-progress-container">
                    <div class="processing-progress-bar" role="progressbar" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">
                        <div class="processing-progress-fill" style="width: 0%"></div>
                    </div>
                    <span class="processing-progress-text">0%</span>
                </div>
            </div>
        `;

        // Add to chat messages area
        if (this.chatMessages) {
            this.chatMessages.appendChild(card);
            this.scrollToBottom();
        }

        return card;
    }

    /**
     * Update a processing status card with new status.
     * 
     * Requirements: 4.3, 4.4, 4.5
     * 
     * @param {HTMLElement} card - Status card element
     * @param {Object} statusData - Status data to display
     */
    updateProcessingStatusCard(card, statusData) {
        const { status, progress, stage, error, summary, metadata } = statusData;

        const stageElement = card.querySelector('.processing-stage');
        const progressFill = card.querySelector('.processing-progress-fill');
        const progressText = card.querySelector('.processing-progress-text');
        const progressBar = card.querySelector('.processing-progress-bar');

        // Update stage text
        if (stageElement) {
            stageElement.textContent = this.getProcessingStageText(status, stage);
        }

        // Update progress bar
        if (progressFill) {
            progressFill.style.width = `${progress}%`;
        }

        if (progressText) {
            progressText.textContent = `${progress}%`;
        }

        // Update ARIA attributes for accessibility
        if (progressBar) {
            progressBar.setAttribute('aria-valuenow', progress);
        }

        // Update live stats from metadata
        this.updateProcessingLiveStats(card, metadata, status);

        // Update card styling based on status
        card.classList.remove('status-processing', 'status-completed', 'status-failed');

        if (status === 'completed') {
            card.classList.add('status-completed');
            this.showProcessingComplete(card, summary);
        } else if (status === 'failed') {
            card.classList.add('status-failed');
            this.showProcessingFailed(card, error, card.getAttribute('data-document-id'));
        } else {
            card.classList.add('status-processing');
        }

        this.scrollToBottom();
    }

    /**
     * Update live processing stats display on the status card.
     *
     * @param {HTMLElement} card - Status card element
     * @param {Object|null} metadata - Stage-specific stats from backend
     * @param {string} status - Current processing status
     */
    updateProcessingLiveStats(card, metadata, status) {
        let statsEl = card.querySelector('.processing-live-stats');

        if (status === 'completed' || status === 'failed') {
            if (statsEl) statsEl.remove();
            return;
        }

        if (!metadata || typeof metadata !== 'object') return;

        if (!statsEl) {
            statsEl = document.createElement('div');
            statsEl.className = 'processing-live-stats';
            statsEl.style.cssText = 'font-size:0.75rem;color:#64748b;margin-top:4px;line-height:1.5;font-variant-numeric:tabular-nums;';
            const stageEl = card.querySelector('.processing-stage');
            if (stageEl) {
                stageEl.parentNode.insertBefore(statsEl, stageEl.nextSibling);
            }
        }

        const fmt = n => Number(n).toLocaleString();
        const parts = [];
        if (metadata.pages_extracted) parts.push(`${fmt(metadata.pages_extracted)} pages`);
        if (metadata.pages) parts.push(`${fmt(metadata.pages)} pages`);
        if (metadata.images) parts.push(`${fmt(metadata.images)} images`);
        if (metadata.tables) parts.push(`${fmt(metadata.tables)} tables`);
        if (metadata.text_length) parts.push(`${fmt(Math.round(metadata.text_length / 1024))}KB text`);
        if (metadata.chunks_generated) parts.push(`${fmt(metadata.chunks_generated)} chunks`);
        // Incremental chunk storage progress
        if (metadata.chunks_stored_so_far && metadata.total_chunks) {
            parts.push(`chunk ${fmt(metadata.chunks_stored_so_far)}/${fmt(metadata.total_chunks)} stored`);
        } else if (metadata.chunks_stored) {
            parts.push(`${fmt(metadata.chunks_stored)} chunks stored`);
        }
        // Incremental embedding storage progress
        if (metadata.embeddings_stored_so_far && metadata.total_chunks) {
            parts.push(`embedding ${fmt(metadata.embeddings_stored_so_far)}/${fmt(metadata.total_chunks)}`);
        } else if (metadata.embeddings_stored) {
            parts.push(`${fmt(metadata.embeddings_stored)} embeddings`);
        }
        // Page progress
        if (metadata.current_page && metadata.total_pages) {
            parts.push(`page ${fmt(metadata.current_page)}/${fmt(metadata.total_pages)}`);
        }
        if (metadata.bridges_generated !== undefined) {
            if (metadata.total_bridges) {
                parts.push(`bridge ${fmt(metadata.bridges_generated)}/${fmt(metadata.total_bridges)}`);
            } else {
                parts.push(`${fmt(metadata.bridges_generated)} bridges`);
            }
        }
        if (metadata.concepts !== undefined) parts.push(`${fmt(metadata.concepts)} concepts`);
        if (metadata.relationships !== undefined) parts.push(`${fmt(metadata.relationships)} relationships`);
        if (metadata.kg_batch && metadata.kg_total_batches) {
            parts.push(`batch ${metadata.kg_batch}/${metadata.kg_total_batches}`);
        }

        statsEl.textContent = parts.length > 0 ? parts.join(' · ') : '';
    }

    /**
     * Get human-readable text for processing stage.
     * 
     * @param {string} status - Processing status
     * @param {string} stage - Current stage name
     * @returns {string} Human-readable stage text
     */
    getProcessingStageText(status, stage) {
        const stageMap = {
            'queued': 'Queued for processing...',
            'extracting': 'Extracting content from PDF...',
            'chunking': 'Processing document content...',
            'embedding': 'Generating embeddings...',
            'bridging': 'Generating bridges...',
            'kg_extraction': 'Building knowledge graph...',
            'finalizing': 'Finalizing...',
            'completed': 'Processing complete!',
            'failed': 'Processing failed'
        };

        return stageMap[status] || stage || 'Processing...';
    }

    /**
     * Show completion state on status card.
     * 
     * Requirement: 4.4
     * 
     * @param {HTMLElement} card - Status card element
     * @param {Object} summary - Processing summary
     */
    showProcessingComplete(card, summary) {
        const bodyElement = card.querySelector('.processing-status-body');
        if (!bodyElement) return;

        // Build summary text
        let summaryText = 'Document ready for querying';
        if (summary) {
            const parts = [];
            if (summary.page_count) parts.push(`${summary.page_count} pages`);
            if (summary.chunk_count) parts.push(`${summary.chunk_count} chunks`);
            if (summary.concept_count) parts.push(`${summary.concept_count} concepts`);
            if (parts.length > 0) {
                summaryText = parts.join(' • ');
            }
        }

        bodyElement.innerHTML = `
            <div class="processing-complete">
                <span class="complete-icon" aria-hidden="true">✓</span>
                <span class="complete-text">${summaryText}</span>
            </div>
        `;

        // Auto-remove after delay
        const documentId = card.getAttribute('data-document-id');
        setTimeout(() => {
            this.removeProcessingStatusCard(documentId);
        }, 5000);
    }

    /**
     * Show failure state on status card with retry option.
     * 
     * Requirement: 4.5
     * 
     * @param {HTMLElement} card - Status card element
     * @param {string} error - Error message
     * @param {string} documentId - Document ID for retry
     */
    showProcessingFailed(card, error, documentId) {
        const bodyElement = card.querySelector('.processing-status-body');
        if (!bodyElement) return;

        bodyElement.innerHTML = `
            <div class="processing-failed">
                <span class="failed-icon" aria-hidden="true">✗</span>
                <span class="failed-text">${this.escapeHtml(error || 'Processing failed')}</span>
            </div>
            <button class="retry-btn" data-document-id="${documentId}" aria-label="Retry processing">
                Retry
            </button>
        `;

        // Add retry button handler
        const retryBtn = bodyElement.querySelector('.retry-btn');
        if (retryBtn) {
            retryBtn.addEventListener('click', () => {
                this.retryDocumentProcessing(documentId);
            });
        }
    }

    /**
     * Retry document processing.
     * 
     * @param {string} documentId - Document ID to retry
     */
    retryDocumentProcessing(documentId) {
        if (!this.wsManager || !this.wsManager.isConnected()) {
            this.addSystemMessage('Cannot retry: Not connected to server', 'error');
            return;
        }

        // Send retry request via WebSocket
        this.wsManager.send({
            type: 'document_retry_request',
            document_id: documentId
        });

        // Reset status card to processing state
        const card = document.getElementById(`processing-status-${documentId}`);
        if (card) {
            card.classList.remove('status-failed');
            card.classList.add('status-processing');

            const bodyElement = card.querySelector('.processing-status-body');
            if (bodyElement) {
                bodyElement.innerHTML = `
                    <div class="processing-stage">Retrying...</div>
                    <div class="processing-progress-container">
                        <div class="processing-progress-bar" role="progressbar" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">
                            <div class="processing-progress-fill" style="width: 0%"></div>
                        </div>
                        <span class="processing-progress-text">0%</span>
                    </div>
                `;
            }
        }
    }

    /**
     * Remove a processing status card from the UI.
     * 
     * @param {string} documentId - Document ID
     */
    removeProcessingStatusCard(documentId) {
        const card = document.getElementById(`processing-status-${documentId}`);
        if (card && card.parentNode) {
            card.parentNode.removeChild(card);
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
     * Add citations to a specific message element
     * Makes source items clickable to show CitationPopup
     * Requirements: 2.1, 2.2, 2.3
     */
    addCitationsToElement(messageElement, citations) {
        if (!citations || citations.length === 0) return;

        const citationsDiv = document.createElement('div');
        citationsDiv.className = 'message-citations';

        const title = document.createElement('h4');
        title.textContent = 'Sources:';
        title.style.marginBottom = '0.5rem';
        title.style.fontSize = '0.875rem';
        title.style.color = '#64748b';
        citationsDiv.appendChild(title);

        citations.forEach((citation, index) => {
            const citationDiv = document.createElement('div');
            citationDiv.className = 'citation citation--clickable';

            // Store citation data on the element for popup access
            citationDiv.dataset.citationIndex = index;
            citationDiv._citationData = citation;

            // Make clickable with cursor pointer and hover state styling
            citationDiv.style.cursor = 'pointer';
            citationDiv.style.transition = 'background-color 0.2s ease, transform 0.1s ease';
            citationDiv.setAttribute('role', 'button');
            citationDiv.setAttribute('tabindex', '0');

            const docTitle = citation.document_title || citation.source_title || 'Unknown';
            citationDiv.setAttribute('aria-label', `View excerpt from Source ${index + 1}: ${docTitle}`);

            // Source number label
            const sourceNum = document.createElement('span');
            sourceNum.textContent = `${index + 1}.`;
            sourceNum.style.cssText = 'font-weight:600;margin-right:6px;color:#475569;min-width:1.2em;';

            const isWebSource = citation.url && citation.source_type === 'web_search';
            const icon = document.createElement('span');
            icon.textContent = isWebSource ? '🔗' : '📖';
            icon.setAttribute('aria-hidden', 'true');

            const text = document.createElement('span');
            const page = citation.page_number ? ` (Page ${citation.page_number})` : '';
            const score = citation.relevance_score ? ` - ${Math.round(citation.relevance_score * 100)}% relevant` : '';

            if (isWebSource) {
                const link = document.createElement('a');
                link.href = citation.url;
                link.target = '_blank';
                link.rel = 'noopener noreferrer';
                link.textContent = `${docTitle}${score}`;
                link.style.color = '#3b82f6';
                link.style.textDecoration = 'underline';
                link.addEventListener('click', (e) => e.stopPropagation());
                text.appendChild(link);
            } else {
                text.textContent = `${docTitle}${page}${score}`;
            }

            citationDiv.appendChild(sourceNum);
            citationDiv.appendChild(icon);

            // Add download button (to the left of the source text)
            if (!isWebSource && citation.document_id) {
                const downloadBtn = document.createElement('button');
                downloadBtn.innerHTML = '⬇';
                downloadBtn.title = `Download ${docTitle}`;
                downloadBtn.setAttribute('aria-label', `Download ${docTitle}`);
                downloadBtn.style.cssText = 'background:none;border:1px solid #cbd5e1;border-radius:4px;cursor:pointer;padding:1px 5px;margin-right:6px;font-size:0.75rem;color:#64748b;transition:all 0.2s ease;line-height:1;';
                downloadBtn.addEventListener('mouseenter', () => {
                    downloadBtn.style.backgroundColor = '#3b82f6';
                    downloadBtn.style.color = '#fff';
                    downloadBtn.style.borderColor = '#3b82f6';
                });
                downloadBtn.addEventListener('mouseleave', () => {
                    downloadBtn.style.backgroundColor = '';
                    downloadBtn.style.color = '#64748b';
                    downloadBtn.style.borderColor = '#cbd5e1';
                });
                downloadBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    window.open(`/api/documents/${citation.document_id}/download?redirect=true`, '_blank');
                });
                citationDiv.appendChild(downloadBtn);
            }

            citationDiv.appendChild(text);

            // Add hover state styling
            citationDiv.addEventListener('mouseenter', () => {
                citationDiv.style.backgroundColor = '#e2e8f0';
                citationDiv.style.transform = 'translateX(4px)';
            });

            citationDiv.addEventListener('mouseleave', () => {
                citationDiv.style.backgroundColor = '';
                citationDiv.style.transform = '';
            });

            // Add click handler to show CitationPopup
            citationDiv.addEventListener('click', (event) => {
                event.preventDefault();
                event.stopPropagation();
                this.showCitationPopup(citation, citationDiv);
            });

            // Add keyboard support (Enter and Space to activate)
            citationDiv.addEventListener('keydown', (event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    event.stopPropagation();
                    this.showCitationPopup(citation, citationDiv);
                }
            });

            citationsDiv.appendChild(citationDiv);
        });

        const contentDiv = messageElement.querySelector('.message-content');
        if (contentDiv) {
            contentDiv.appendChild(citationsDiv);
        }
    }

    /**
     * Show citation popup for a given citation
     * Uses the singleton CitationPopup instance initialized in constructor
     * @param {Object} citationData - Citation information
     * @param {HTMLElement} triggerElement - Element that triggered the popup
     * Requirements: 1.2, 2.2
     */
    showCitationPopup(citationData, triggerElement) {
        if (!this.citationPopup) {
            console.warn('CitationPopup not initialized');
            return;
        }

        this.citationPopup.show(citationData, triggerElement);
    }

    /**
     * Set up file handler event listeners.
     * Wires ChatUploadHandler events for chat-integrated uploads.
     * 
     * Requirements: 1.1, 1.2, 1.3
     */
    setupFileHandlers() {
        // Handle upload completion (for both ChatUploadHandler and FileHandler)
        this.fileHandler.on('uploadComplete', (data) => {
            this.addSystemMessage(`Successfully uploaded ${data.files.length} file(s)`);

            // Send notification to server about uploaded files
            this.wsManager.send({
                type: 'files_uploaded',
                thread_id: this.currentThreadId,
                files: data.files.map(f => ({
                    name: f.name,
                    size: f.size,
                    type: f.type
                }))
            });
        });

        // Handle upload errors
        this.fileHandler.on('error', (data) => {
            this.addSystemMessage(`Upload error: ${data.message}`, 'error');
            if (data.details && data.details.length > 0) {
                data.details.forEach(detail => {
                    this.addSystemMessage(detail, 'error');
                });
            }
        });

        // ChatUploadHandler-specific events
        if (this.fileHandler instanceof ChatUploadHandler) {
            // Handle processing completion
            this.fileHandler.on('processingComplete', (data) => {
                console.log('Document processing complete:', data);
                // Optionally show a success message
                // this.addSystemMessage(`Document "${data.filename}" is ready for querying`);
            });

            // Handle processing failure
            this.fileHandler.on('processingFailed', (data) => {
                console.log('Document processing failed:', data);
                // Error is already shown in the status card
            });

            // Handle upload errors from WebSocket
            this.fileHandler.on('uploadError', (data) => {
                console.log('Upload error:', data);
                // Error message is already shown by ChatUploadHandler
            });
        }
    }

    /**
     * Start a new conversation
     */
    startNewConversation() {
        this.wsManager.send({
            type: 'start_conversation'
        });
    }

    /**
     * Send a message
     */
    sendMessage() {
        const message = this.messageInput.value.trim();
        if (!message || !this.wsManager.isConnected()) {
            return;
        }

        // Add user message to chat
        this.addUserMessage(message);

        // Clear input
        this.messageInput.value = '';
        this.autoResizeTextarea();
        this.updateSendButton();

        // Send to server
        this.wsManager.send({
            type: 'chat_message',
            thread_id: this.currentThreadId,
            message: message,
            timestamp: new Date().toISOString()
        });

        // Show processing indicator
        this.showProcessingIndicator('Processing your message...');
    }

    /**
     * Handle server messages
     * 
     * NOTE: 'response', 'error', 'processing', and 'processing_complete' types
     * are handled by dedicated event handlers registered in setupWebSocketHandlers().
     * Do NOT handle them here to avoid duplicate processing.
     */
    handleServerMessage(data) {
        switch (data.type) {
            case 'conversation_started':
                this.currentThreadId = data.thread_id;
                console.log('Conversation started:', this.currentThreadId);
                break;

            // These types are handled by dedicated handlers in setupWebSocketHandlers()
            // to avoid duplicate message rendering
            case 'response':
            case 'error':
            case 'processing':
            case 'processing_complete':
                // Already handled by dedicated event handlers
                break;

            default:
                console.log('Unknown message type:', data.type);
        }
    }

    /**
     * Handle chat response from server
     */
    handleChatResponse(data) {
        this.hideProcessingIndicator();

        if (data.response) {
            this.addSystemMessage(data.response.text_content || data.response);

            // Handle multimedia content
            if (data.response.visualizations) {
                data.response.visualizations.forEach(viz => {
                    this.addVisualization(viz);
                });
            }

            // Handle citations
            if (data.response.knowledge_citations) {
                this.addCitations(data.response.knowledge_citations);
            }
        }
    }

    /**
     * Handle server errors
     */
    handleServerError(data) {
        this.hideProcessingIndicator();
        this.addSystemMessage(`Error: ${data.message || 'An error occurred'}`, 'error');
    }

    /**
     * Add user message to chat
     */
    addUserMessage(message) {
        const messageElement = this.createMessageElement('user', message);
        this.chatMessages.appendChild(messageElement);
        this.scrollToBottom();

        this.messageHistory.push({
            type: 'user',
            content: message,
            timestamp: new Date()
        });
    }

    /**
     * Add system message to chat
     */
    addSystemMessage(message, type = 'info') {
        const messageElement = this.createMessageElement('system', message, type);
        this.chatMessages.appendChild(messageElement);
        this.scrollToBottom();

        this.messageHistory.push({
            type: 'system',
            content: message,
            messageType: type,
            timestamp: new Date()
        });
    }

    /**
     * Create message element
     */
    createMessageElement(sender, content, messageType = 'info') {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender}-message`;

        // Message header
        const headerDiv = document.createElement('div');
        headerDiv.className = 'message-header';

        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.textContent = sender === 'user' ? 'U' : 'AI';
        avatar.setAttribute('aria-hidden', 'true');

        const timestamp = document.createElement('span');
        timestamp.className = 'message-timestamp';
        timestamp.textContent = new Date().toLocaleTimeString();

        headerDiv.appendChild(avatar);
        headerDiv.appendChild(timestamp);

        // Message content
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';

        if (messageType === 'error') {
            contentDiv.style.background = '#fef2f2';
            contentDiv.style.color = '#dc2626';
            contentDiv.style.borderColor = '#fecaca';
        }

        // Handle different content types
        if (typeof content === 'string') {
            // Convert line breaks to paragraphs
            const paragraphs = content.split('\n\n');
            paragraphs.forEach(paragraph => {
                if (paragraph.trim()) {
                    const p = document.createElement('p');
                    p.textContent = paragraph.trim();
                    contentDiv.appendChild(p);
                }
            });
        } else {
            contentDiv.appendChild(content);
        }

        messageDiv.appendChild(headerDiv);
        messageDiv.appendChild(contentDiv);

        return messageDiv;
    }

    /**
     * Add visualization to chat
     */
    addVisualization(visualization) {
        const mediaDiv = document.createElement('div');
        mediaDiv.className = 'message-media';

        if (visualization.type === 'image') {
            const img = document.createElement('img');
            img.className = 'message-image';
            img.src = visualization.url;
            img.alt = visualization.caption || 'Generated visualization';
            mediaDiv.appendChild(img);
        }

        // Add to last system message or create new one
        const lastMessage = this.chatMessages.lastElementChild;
        if (lastMessage && lastMessage.classList.contains('system-message')) {
            const content = lastMessage.querySelector('.message-content');
            content.appendChild(mediaDiv);
        } else {
            const messageElement = this.createMessageElement('system', mediaDiv);
            this.chatMessages.appendChild(messageElement);
        }

        this.scrollToBottom();
    }

    /**
     * Add citations to chat
     * Makes source items clickable to show CitationPopup
     * Requirements: 2.1, 2.2, 2.3
     */
    addCitations(citations) {
        if (!citations || citations.length === 0) return;

        const citationsDiv = document.createElement('div');
        citationsDiv.className = 'message-citations';

        const title = document.createElement('h4');
        title.textContent = 'Sources:';
        title.style.marginBottom = '0.5rem';
        title.style.fontSize = '0.875rem';
        title.style.color = '#64748b';
        citationsDiv.appendChild(title);

        citations.forEach((citation, index) => {
            const citationDiv = document.createElement('div');
            citationDiv.className = 'citation citation--clickable';

            // Store citation data on the element for popup access
            citationDiv.dataset.citationIndex = index;
            citationDiv._citationData = citation;

            // Make clickable with cursor pointer and hover state styling
            citationDiv.style.cursor = 'pointer';
            citationDiv.style.transition = 'background-color 0.2s ease, transform 0.1s ease';
            citationDiv.setAttribute('role', 'button');
            citationDiv.setAttribute('tabindex', '0');

            const docTitle = citation.document_title || citation.source_title || 'Unknown';
            citationDiv.setAttribute('aria-label', `View excerpt from Source ${index + 1}: ${docTitle}`);

            // Source number label
            const sourceNum = document.createElement('span');
            sourceNum.textContent = `${index + 1}.`;
            sourceNum.style.cssText = 'font-weight:600;margin-right:6px;color:#475569;min-width:1.2em;';

            const isWebSource = citation.url && citation.source_type === 'web_search';
            const icon = document.createElement('span');
            icon.textContent = isWebSource ? '🔗' : '📖';
            icon.setAttribute('aria-hidden', 'true');

            const text = document.createElement('span');
            const page = citation.page_number ? ` (Page ${citation.page_number})` : '';
            const score = citation.relevance_score ? ` - ${Math.round(citation.relevance_score * 100)}% relevant` : '';

            if (isWebSource) {
                const link = document.createElement('a');
                link.href = citation.url;
                link.target = '_blank';
                link.rel = 'noopener noreferrer';
                link.textContent = `${docTitle}${score}`;
                link.style.color = '#3b82f6';
                link.style.textDecoration = 'underline';
                link.addEventListener('click', (e) => e.stopPropagation());
                text.appendChild(link);
            } else {
                text.textContent = `${docTitle}${page}${score}`;
            }

            citationDiv.appendChild(sourceNum);
            citationDiv.appendChild(icon);

            // Add download button (to the left of the source text)
            if (!isWebSource && citation.document_id) {
                const downloadBtn = document.createElement('button');
                downloadBtn.innerHTML = '⬇';
                downloadBtn.title = `Download ${docTitle}`;
                downloadBtn.setAttribute('aria-label', `Download ${docTitle}`);
                downloadBtn.style.cssText = 'background:none;border:1px solid #cbd5e1;border-radius:4px;cursor:pointer;padding:1px 5px;margin-right:6px;font-size:0.75rem;color:#64748b;transition:all 0.2s ease;line-height:1;';
                downloadBtn.addEventListener('mouseenter', () => {
                    downloadBtn.style.backgroundColor = '#3b82f6';
                    downloadBtn.style.color = '#fff';
                    downloadBtn.style.borderColor = '#3b82f6';
                });
                downloadBtn.addEventListener('mouseleave', () => {
                    downloadBtn.style.backgroundColor = '';
                    downloadBtn.style.color = '#64748b';
                    downloadBtn.style.borderColor = '#cbd5e1';
                });
                downloadBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    window.open(`/api/documents/${citation.document_id}/download?redirect=true`, '_blank');
                });
                citationDiv.appendChild(downloadBtn);
            }

            citationDiv.appendChild(text);

            // Add hover state styling
            citationDiv.addEventListener('mouseenter', () => {
                citationDiv.style.backgroundColor = '#e2e8f0';
                citationDiv.style.transform = 'translateX(4px)';
            });

            citationDiv.addEventListener('mouseleave', () => {
                citationDiv.style.backgroundColor = '';
                citationDiv.style.transform = '';
            });

            // Add click handler to show CitationPopup
            citationDiv.addEventListener('click', (event) => {
                event.preventDefault();
                event.stopPropagation();
                this.showCitationPopup(citation, citationDiv);
            });

            // Add keyboard support (Enter and Space to activate)
            citationDiv.addEventListener('keydown', (event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    event.stopPropagation();
                    this.showCitationPopup(citation, citationDiv);
                }
            });

            citationsDiv.appendChild(citationDiv);
        });

        // Add to last system message
        const lastMessage = this.chatMessages.lastElementChild;
        if (lastMessage && lastMessage.classList.contains('system-message')) {
            const content = lastMessage.querySelector('.message-content');
            content.appendChild(citationsDiv);
        }

        this.scrollToBottom();
    }

    /**
     * Show processing indicator
     */
    showProcessingIndicator(message = 'Processing...') {
        const indicator = this.processingIndicator;
        const text = indicator.querySelector('span');
        if (text) {
            text.textContent = message;
        }
        indicator.style.display = 'flex';
    }

    /**
     * Hide processing indicator
     */
    hideProcessingIndicator() {
        this.processingIndicator.style.display = 'none';
    }

    /**
     * Auto-resize textarea
     */
    autoResizeTextarea() {
        const textarea = this.messageInput;
        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
    }

    /**
     * Update character count display
     */
    updateCharacterCount() {
        const length = this.messageInput.value.length;
        const maxLength = 4000;

        if (this.characterCount) {
            this.characterCount.textContent = `${length}/${maxLength}`;

            // Update styling based on length
            this.characterCount.className = 'character-count';
            if (length > maxLength * 0.9) {
                this.characterCount.classList.add('error');
            } else if (length > maxLength * 0.8) {
                this.characterCount.classList.add('warning');
            }
        }
    }

    /**
     * Show export options
     */
    showExportOptions() {
        if (this.messageHistory.length === 0) {
            this.addSystemMessage('No conversation to export', 'error');
            return;
        }

        // Create export options modal
        const modal = this.createExportModal();
        document.body.appendChild(modal);

        // Focus on first option
        const firstOption = modal.querySelector('button');
        if (firstOption) {
            firstOption.focus();
        }
    }

    /**
     * Create export modal
     */
    createExportModal() {
        const modal = document.createElement('div');
        modal.className = 'export-modal';
        modal.setAttribute('role', 'dialog');
        modal.setAttribute('aria-labelledby', 'export-title');
        modal.setAttribute('aria-modal', 'true');

        modal.innerHTML = `
            <div class="export-modal-backdrop"></div>
            <div class="export-modal-content">
                <div class="export-modal-header">
                    <h3 id="export-title">Export Conversation</h3>
                    <button class="export-close-btn" aria-label="Close export dialog">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <line x1="18" y1="6" x2="6" y2="18"></line>
                            <line x1="6" y1="6" x2="18" y2="18"></line>
                        </svg>
                    </button>
                </div>
                <div class="export-modal-body">
                    <p>Choose a format to export your conversation:</p>
                    <div class="export-options">
                        <button class="export-option" data-format="txt">
                            <span class="export-icon">📄</span>
                            <div>
                                <span class="export-label">Text (.txt)</span>
                                <span class="export-desc">Plain text format</span>
                            </div>
                        </button>
                        <button class="export-option" data-format="docx">
                            <span class="export-icon">📝</span>
                            <div>
                                <span class="export-label">Word (.docx)</span>
                                <span class="export-desc">Microsoft Word document</span>
                            </div>
                        </button>
                        <button class="export-option" data-format="pdf">
                            <span class="export-icon">📋</span>
                            <div>
                                <span class="export-label">PDF (.pdf)</span>
                                <span class="export-desc">Portable document format</span>
                            </div>
                        </button>
                        <button class="export-option" data-format="html">
                            <span class="export-icon">🌐</span>
                            <div>
                                <span class="export-label">HTML (.html)</span>
                                <span class="export-desc">Web page format</span>
                            </div>
                        </button>
                    </div>
                </div>
            </div>
        `;

        // Add event listeners
        const closeBtn = modal.querySelector('.export-close-btn');
        const backdrop = modal.querySelector('.export-modal-backdrop');
        const options = modal.querySelectorAll('.export-option');

        const closeModal = () => {
            document.body.removeChild(modal);
            this.messageInput.focus();
        };

        closeBtn.addEventListener('click', closeModal);
        backdrop.addEventListener('click', closeModal);

        options.forEach(option => {
            option.addEventListener('click', () => {
                const format = option.dataset.format;
                this.exportConversation(format);
                closeModal();
            });
        });

        // Handle escape key
        const handleKeydown = (e) => {
            if (e.key === 'Escape') {
                closeModal();
                document.removeEventListener('keydown', handleKeydown);
            }
        };
        document.addEventListener('keydown', handleKeydown);

        return modal;
    }

    /**
     * Export conversation via WebSocket
     */
    exportConversation(format) {
        if (this.messageHistory.length === 0) {
            this.addSystemMessage('No conversation to export');
            return;
        }

        if (!this.wsManager.isConnected()) {
            // Fallback: client-side text export
            this.exportClientSide(format);
            return;
        }

        this.wsManager.send({
            type: 'export_conversation',
            thread_id: this.currentThreadId,
            format: format
        });

        this.addSystemMessage(`Preparing ${format.toUpperCase()} export...`);
    }

    /**
     * Handle export ready response from server
     */
    handleExportReady(data) {
        if (!data.data) {
            this.addSystemMessage('Export failed: no data received');
            return;
        }

        const mimeTypes = {
            txt: 'text/plain',
            html: 'text/html',
            pdf: 'application/pdf',
            docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        };

        const byteChars = atob(data.data);
        const byteArray = new Uint8Array(byteChars.length);
        for (let i = 0; i < byteChars.length; i++) {
            byteArray[i] = byteChars.charCodeAt(i);
        }

        const blob = new Blob([byteArray], { type: mimeTypes[data.format] || 'application/octet-stream' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `conversation_${new Date().toISOString().slice(0, 10)}.${data.format}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        this.addSystemMessage(`${data.format.toUpperCase()} export downloaded`);
    }

    /**
     * Fallback client-side export when WebSocket unavailable
     */
    exportClientSide(format) {
        let content = 'Conversation Export\n\n';
        this.messageHistory.forEach(msg => {
            const sender = msg.role === 'user' ? 'You' : 'Assistant';
            content += `${sender}: ${msg.content}\n\n`;
        });

        const blob = new Blob([content], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `conversation_${new Date().toISOString().slice(0, 10)}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        this.addSystemMessage('Exported as text (server unavailable for other formats)');
    }

    /**
     * Scroll to bottom of chat
     */
    scrollToBottom() {
        requestAnimationFrame(() => {
            this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
        });
    }

    /**
     * Update send button state
     */
    updateSendButton() {
        const hasContent = this.messageInput.value.trim().length > 0;
        const isConnected = this.wsManager.isConnected();
        const withinLimit = this.messageInput.value.length <= 4000;

        this.sendBtn.disabled = !hasContent || !isConnected || !withinLimit;
        this.exportBtn.disabled = this.messageHistory.length === 0;
    }

    /**
     * Clear chat history
     */
    clearChat() {
        // Remove all messages except welcome message
        const messages = this.chatMessages.querySelectorAll('.message:not(.welcome-message .message)');
        messages.forEach(message => message.remove());

        this.messageHistory = [];
        this.currentThreadId = null;

        // Update button states
        this.updateSendButton();

        // Start new conversation
        if (this.wsManager.isConnected()) {
            this.startNewConversation();
        }

        // Show confirmation
        this.addSystemMessage('Started a new conversation');
    }
}

// Initialize chat app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.chatApp = new ChatApp();

    // Add keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        // Ctrl/Cmd + K to clear chat
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            window.chatApp.clearChat();
        }

        // Ctrl/Cmd + E to export
        if ((e.ctrlKey || e.metaKey) && e.key === 'e') {
            e.preventDefault();
            window.chatApp.showExportOptions();
        }

        // Ctrl/Cmd + U to upload
        if ((e.ctrlKey || e.metaKey) && e.key === 'u') {
            e.preventDefault();
            document.getElementById('fileInput').click();
        }
    });
});