/**
 * Chat Upload Handler
 * 
 * Handles file uploads within the chat interface with WebSocket-based upload
 * and real-time processing status feedback.
 * 
 * Extends FileHandler with chat-specific behavior for PDF document uploads.
 * 
 * Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6
 */

class ChatUploadHandler extends FileHandler {
    /**
     * Initialize with WebSocket manager and chat app reference.
     * 
     * @param {WebSocketManager} wsManager - WebSocket manager for sending upload messages
     * @param {ChatApp} chatApp - Chat application instance for UI updates
     */
    constructor(wsManager, chatApp) {
        super();

        this.wsManager = wsManager;
        this.chatApp = chatApp;

        // Override supported types to PDF only for chat uploads
        this.supportedTypes = {
            'application/pdf': 'PDF'
        };

        // Upload queue for multi-file handling (Requirement 1.6)
        this.uploadQueue = [];
        this.isProcessingQueue = false;

        // Upload lock to prevent concurrent uploads
        this.isUploading = false;

        // Track active uploads for status updates
        this.activeUploads = new Map();

        // Processing status elements
        this.processingStatusCards = new Map();

        // Initialize duplicate checking and file queue components
        this._initDuplicateFilterComponents();

        // Set up WebSocket handlers for processing status
        this.setupProcessingStatusHandlers();
    }

    /**
     * Initialize DuplicateChecker, FileQueuePanel, and UploadedFilesPanel.
     * Creates container elements and wires callbacks.
     */
    _initDuplicateFilterComponents() {
        // DuplicateChecker
        if (typeof DuplicateChecker !== 'undefined') {
            this.duplicateChecker = new DuplicateChecker();
        } else {
            this.duplicateChecker = null;
        }

        // FileQueuePanel — create container and insert before the input area
        this.fileQueueContainer = document.createElement('div');
        this.fileQueueContainer.id = 'fileQueueContainer';
        this.fileQueueContainer.style.display = 'none';
        var inputContainer = document.querySelector('.chat-input-container');
        if (inputContainer && inputContainer.parentNode) {
            inputContainer.parentNode.insertBefore(this.fileQueueContainer, inputContainer);
        }

        if (typeof FileQueuePanel !== 'undefined') {
            this.fileQueuePanel = new FileQueuePanel(this.fileQueueContainer);
            var self = this;
            this.fileQueuePanel.onUploadNew = function (files) {
                self.uploadFiles(files, false);
            };
            this.fileQueuePanel.onForceUploadAll = function (files) {
                self.uploadFiles(files, true);
            };
            this.fileQueuePanel.onRemoveFile = function () {
                // no-op — panel handles removal internally
            };
        } else {
            this.fileQueuePanel = null;
        }

        // UploadedFilesPanel — container created but wired in by chat.js
        this.uploadedFilesPanelContainer = document.createElement('div');
        this.uploadedFilesPanelContainer.id = 'uploadedFilesPanelContainer';

        if (typeof UploadedFilesPanel !== 'undefined') {
            this.uploadedFilesPanel = new UploadedFilesPanel(this.uploadedFilesPanelContainer);
        } else {
            this.uploadedFilesPanel = null;
        }
    }

    /**
     * Set up WebSocket handlers for document processing status updates.
     */
    setupProcessingStatusHandlers() {
        if (!this.wsManager) return;

        // Handle upload started confirmation
        this.wsManager.on('document_upload_started', (data) => {
            this.handleUploadStarted(data);
        });

        // Handle processing status updates (Requirement 3.5)
        this.wsManager.on('document_processing_status', (data) => {
            this.showProcessingStatus(data);
        });

        // Handle retry started — immediately create a progress card so the
        // user sees feedback before the first processing status arrives
        this.wsManager.on('document_retry_started', (data) => {
            const { document_id, filename } = data;
            const card = this.createProcessingStatusCard(document_id, filename || 'Retrying...');
            if (card) {
                card.classList.remove('status-failed');
                card.classList.add('status-processing');
                const stageEl = card.querySelector('.processing-stage');
                if (stageEl) stageEl.textContent = 'Retrying...';
                const progressFill = card.querySelector('.processing-progress-fill');
                if (progressFill) progressFill.style.width = '0%';
                const progressText = card.querySelector('.processing-progress-text');
                if (progressText) progressText.textContent = '0%';
            }
        });

        // Note: document_upload_error is handled by chat.js which delegates
        // to this.handleUploadError() - no need to register here to avoid
        // duplicate error messages
    }


    /**
     * Handle files uploaded via chat interface.
     * Validates files and initiates upload via WebSocket.
     * 
     * @param {FileList} files - FileList from drag-drop, paste, or file input
     * 
     * Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6
     */
    async handleChatUpload(files) {
        const fileArray = Array.from(files);

        // Validate and filter files
        const validFiles = [];
        const errors = [];

        fileArray.forEach(file => {
            const validation = this.validateChatFile(file);
            if (validation.valid) {
                validFiles.push(file);
            } else {
                errors.push(`${file.name}: ${validation.error}`);
            }
        });

        // Show errors for invalid files (Requirement 1.4, 1.5)
        if (errors.length > 0) {
            errors.forEach(error => {
                this.chatApp.addSystemMessage(error, 'error');
            });
        }

        if (validFiles.length === 0) return;

        // If duplicate checker is available, run duplicate detection and show queue
        if (this.duplicateChecker && this.fileQueuePanel) {
            try {
                if (!this.duplicateChecker.loaded) {
                    await this.duplicateChecker.fetchUploadedFilenames();
                }
            } catch (e) {
                console.error('Failed to fetch uploaded filenames:', e);
            }

            const annotated = this.duplicateChecker.checkFiles(validFiles);
            this.fileQueuePanel.show(annotated);

            // Update uploaded files panel with current docs
            if (this.uploadedFilesPanel) {
                this.uploadedFilesPanel.updateDocuments(this.duplicateChecker.getDocuments());
            }
        } else {
            // Fallback: upload immediately without duplicate checking
            this.queueFilesForUpload(validFiles);
        }
    }

    /**
     * Validate a file for chat upload.
     * Only accepts PDF files under 100MB.
     * 
     * @param {File} file - File to validate
     * @returns {Object} Validation result with valid flag and error message
     * 
     * Requirements: 1.4, 1.5
     */
    validateChatFile(file) {
        // Check file type - PDF only (Requirement 1.4)
        const isPDF = file.type === 'application/pdf' ||
            file.name.toLowerCase().endsWith('.pdf');

        if (!isPDF) {
            return {
                valid: false,
                error: 'Only PDF files are supported for document cataloging'
            };
        }

        // Check file size - 100MB limit (Requirement 1.5)
        if (file.size > this.maxFileSize) {
            return {
                valid: false,
                error: `File exceeds 100MB limit. Please upload a smaller file.`
            };
        }

        // Check for empty file
        if (file.size === 0) {
            return {
                valid: false,
                error: 'File is empty'
            };
        }

        return { valid: true };
    }

    /**
     * Queue files for sequential upload processing.
     * 
     * @param {Array<File>} files - Array of validated files to upload
     * 
     * Requirement: 1.6
     */
    queueFilesForUpload(files) {
        // Add files to queue
        files.forEach(file => {
            this.uploadQueue.push(file);
        });

        // Start processing queue if not already processing
        if (!this.isProcessingQueue) {
            this.processUploadQueue();
        }
    }

    /**
     * Process the upload queue sequentially.
     * 
     * Requirement: 1.6
     */
    async processUploadQueue() {
        if (this.uploadQueue.length === 0) {
            this.isProcessingQueue = false;
            return;
        }

        this.isProcessingQueue = true;

        while (this.uploadQueue.length > 0) {
            const file = this.uploadQueue.shift();
            await this.uploadFileViaWebSocket(file);
        }

        this.isProcessingQueue = false;
    }


    /**
     * Upload files with optional force-upload for duplicates.
     * Uses the upload lock to prevent concurrent uploads.
     *
     * @param {File[]} files - Files to upload
     * @param {boolean} forceUpload - If true, upload even if server detects duplicate
     */
    async uploadFiles(files, forceUpload) {
        if (this.isUploading) {
            this.chatApp.addSystemMessage('An upload is already in progress. Please wait.', 'error');
            return;
        }

        this.isUploading = true;

        try {
            for (const file of files) {
                await this.uploadFileViaWebSocket(file);

                // Update duplicate checker cache and uploaded files panel
                if (this.duplicateChecker) {
                    this.duplicateChecker.addUploadedDocument(file.name, {
                        filename: file.name,
                        title: file.name.replace(/\.pdf$/i, ''),
                        status: 'processing',
                        fileSize: file.size
                    });
                }
                if (this.uploadedFilesPanel) {
                    this.uploadedFilesPanel.addDocument({
                        filename: file.name,
                        title: file.name.replace(/\.pdf$/i, ''),
                        status: 'processing',
                        fileSize: file.size
                    });
                }
            }
        } catch (error) {
            console.error('Upload batch error:', error);
            this.chatApp.addSystemMessage(`Upload error: ${error.message}`, 'error');
        } finally {
            this.isUploading = false;
            // Hide the file queue panel after uploads complete
            if (this.fileQueuePanel) {
                this.fileQueuePanel.hide();
            }
        }
    }


    /**
     * Upload a single file via WebSocket.
     * Converts file to base64 and sends via WebSocket message.
     * 
     * @param {File} file - File to upload
     * @returns {Promise<void>}
     * 
     * Requirements: 1.1, 1.2, 1.3
     */
    async uploadFileViaWebSocket(file) {
        // Check WebSocket connection
        if (!this.wsManager || !this.wsManager.isConnected()) {
            this.chatApp.addSystemMessage(
                `Cannot upload ${file.name}: Not connected to server`,
                'error'
            );
            return;
        }

        // Show upload progress in chat
        this.showUploadProgress(file, 0);

        try {
            // Read file as base64
            const base64Data = await this.readFileAsBase64(file);

            // Update progress to show reading complete
            this.showUploadProgress(file, 50);

            // Create upload message matching ChatUploadMessage model
            const uploadMessage = {
                type: 'chat_document_upload',
                filename: file.name,
                file_size: file.size,
                content_type: file.type || 'application/pdf',
                file_data: base64Data,
                title: file.name.replace(/\.pdf$/i, ''),
                description: null
            };

            // Track this upload
            const uploadId = `${file.name}-${Date.now()}`;
            this.activeUploads.set(uploadId, {
                file: file,
                startTime: Date.now()
            });

            // Send via WebSocket
            const sent = this.wsManager.send(uploadMessage);

            if (sent) {
                this.showUploadProgress(file, 100);
                // Don't show system message here - wait for server response
                // to avoid showing message for duplicates
            } else {
                throw new Error('Failed to send upload message');
            }

        } catch (error) {
            console.error('Upload error:', error);
            this.chatApp.addSystemMessage(
                `Failed to upload ${file.name}: ${error.message}`,
                'error'
            );
            this.hideUploadProgress(file);
        }
    }

    /**
     * Read file as base64 string.
     * 
     * @param {File} file - File to read
     * @returns {Promise<string>} Base64 encoded file content
     */
    readFileAsBase64(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();

            reader.onload = () => {
                // Remove data URL prefix to get pure base64
                const base64 = reader.result.split(',')[1];
                resolve(base64);
            };

            reader.onerror = () => {
                reject(new Error('Failed to read file'));
            };

            reader.readAsDataURL(file);
        });
    }

    /**
     * Display upload progress in chat UI.
     * 
     * @param {File} file - File being uploaded
     * @param {number} progress - Upload progress percentage (0-100)
     */
    showUploadProgress(file, progress) {
        // Use the existing upload progress elements if available
        const uploadProgress = document.getElementById('uploadProgress');
        const progressFill = document.getElementById('progressFill');
        const progressText = document.getElementById('progressText');

        if (uploadProgress && progressFill && progressText) {
            uploadProgress.style.display = 'block';
            progressFill.style.width = `${progress}%`;
            progressText.textContent = progress < 100
                ? `Uploading ${file.name}...`
                : `Upload complete: ${file.name}`;

            // Hide after completion
            if (progress >= 100) {
                setTimeout(() => {
                    uploadProgress.style.display = 'none';
                }, 2000);
            }
        }

        // Emit event for external handlers
        this.emit('uploadProgress', { file, progress });
    }

    /**
     * Hide upload progress indicator.
     * 
     * @param {File} file - File that was being uploaded
     */
    hideUploadProgress(file) {
        const uploadProgress = document.getElementById('uploadProgress');
        if (uploadProgress) {
            uploadProgress.style.display = 'none';
        }
    }


    /**
     * Handle upload started confirmation from server.
     * 
     * @param {Object} data - Upload started message data
     */
    handleUploadStarted(data) {
        console.log('Upload started:', data);

        // Create processing status card in chat
        this.createProcessingStatusCard(data.document_id, data.filename);
    }

    /**
     * Display document processing status in chat UI.
     * Updates the processing status card with current progress.
     * 
     * @param {Object} status - Processing status message from WebSocket
     * 
     * Requirements: 3.5, 3.6, 4.1, 4.2, 4.3, 4.4, 4.5
     */
    showProcessingStatus(status) {
        const { document_id, filename, status: processingStatus,
            progress_percentage, current_stage, error_message, summary, metadata } = status;

        // Get or create status card
        let statusCard = this.processingStatusCards.get(document_id);
        if (!statusCard) {
            statusCard = this.createProcessingStatusCard(document_id, filename);
        }

        // Update status card content
        this.updateProcessingStatusCard(statusCard, {
            status: processingStatus,
            progress: progress_percentage,
            stage: current_stage,
            error: error_message,
            summary: summary,
            metadata: metadata
        });

        // Handle completion states
        if (processingStatus === 'completed') {
            this.handleProcessingComplete(document_id, filename, summary);
        } else if (processingStatus === 'failed') {
            this.handleProcessingFailed(document_id, filename, error_message);
        }

        // Emit event for external handlers
        this.emit('processingStatus', status);
    }

    /**
     * Create a processing status card in the chat UI.
     * Returns existing card if one already exists for this document.
     * 
     * @param {string} documentId - Document ID
     * @param {string} filename - Document filename
     * @returns {HTMLElement} The created or existing status card element
     * 
     * Requirements: 4.1, 4.2
     */
    createProcessingStatusCard(documentId, filename) {
        // Check if card already exists to prevent duplicates
        const existingCard = this.processingStatusCards.get(documentId);
        if (existingCard) {
            return existingCard;
        }

        const card = document.createElement('div');
        card.className = 'processing-status-card';
        card.id = `processing-status-${documentId}`;
        card.setAttribute('data-document-id', documentId);

        card.innerHTML = `
            <div class="processing-status-header">
                <span class="processing-icon">📄</span>
                <span class="processing-filename">${this.escapeHtml(filename)}</span>
            </div>
            <div class="processing-status-body">
                <div class="processing-stage">Queued for processing...</div>
                <div class="processing-progress-container">
                    <div class="processing-progress-bar">
                        <div class="processing-progress-fill" style="width: 0%"></div>
                    </div>
                    <span class="processing-progress-text">0%</span>
                </div>
            </div>
        `;

        // Add to chat messages area
        const chatMessages = document.getElementById('chatMessages');
        if (chatMessages) {
            chatMessages.appendChild(card);
            this.scrollToBottom();
        }

        this.processingStatusCards.set(documentId, card);
        return card;
    }

    /**
     * Update a processing status card with new status.
     * 
     * @param {HTMLElement} card - Status card element
     * @param {Object} statusData - Status data to display
     * 
     * Requirements: 4.3, 4.4, 4.5
     */
    updateProcessingStatusCard(card, statusData) {
        const { status, progress, stage, error, summary, metadata } = statusData;

        const stageElement = card.querySelector('.processing-stage');
        const progressFill = card.querySelector('.processing-progress-fill');
        const progressText = card.querySelector('.processing-progress-text');

        // Monotonic progress — never go backwards (guards against
        // duplicate task deliveries or interleaved parallel updates)
        const prevProgress = parseInt(card.dataset.lastProgress || '0', 10);
        const effectiveProgress = (status === 'completed' || status === 'failed')
            ? progress
            : Math.max(progress, prevProgress);
        card.dataset.lastProgress = String(effectiveProgress);

        // Update stage text
        if (stageElement) {
            stageElement.textContent = this.getStageDisplayText(status, stage);
        }

        // Update progress bar
        if (progressFill) {
            progressFill.style.width = `${effectiveProgress}%`;
        }

        if (progressText) {
            progressText.textContent = `${effectiveProgress}%`;
        }

        // Update live stats from metadata
        this.updateLiveStats(card, metadata, status);

        // Update card styling based on status
        card.classList.remove('status-processing', 'status-completed', 'status-failed');

        if (status === 'completed') {
            card.classList.add('status-completed');
            this.showCompletionState(card, summary);
        } else if (status === 'failed') {
            card.classList.add('status-failed');
            this.showFailureState(card, error);
        } else {
            card.classList.add('status-processing');
        }
    }

    /**
     * Update live processing stats display on the status card.
     * Shows stage-relevant metrics like page count, chunks, bridges, concepts, etc.
     *
     * @param {HTMLElement} card - Status card element
     * @param {Object|null} metadata - Stage-specific stats from backend
     * @param {string} status - Current processing status
     */
    updateLiveStats(card, metadata, status) {
        let statsEl = card.querySelector('.processing-live-stats');

        // Remove stats on completion/failure (summary takes over)
        if (status === 'completed' || status === 'failed') {
            if (statsEl) statsEl.remove();
            return;
        }

        if (!metadata || typeof metadata !== 'object') return;

        // Create stats element if it doesn't exist
        if (!statsEl) {
            statsEl = document.createElement('div');
            statsEl.className = 'processing-live-stats';
            statsEl.style.cssText = 'font-size:0.75rem;color:#64748b;margin-top:4px;line-height:1.5;font-variant-numeric:tabular-nums;';
            const stageEl = card.querySelector('.processing-stage');
            if (stageEl) {
                stageEl.parentNode.insertBefore(statsEl, stageEl.nextSibling);
            }
        }

        // Build stats string based on what's available
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
            // Monotonic: never show a lower bridge count than previously seen
            const prevBridges = parseInt(card.dataset.lastBridges || '0', 10);
            const curBridges = Math.max(metadata.bridges_generated, prevBridges);
            card.dataset.lastBridges = String(curBridges);
            if (metadata.total_bridges) {
                parts.push(`bridge ${fmt(curBridges)}/${fmt(metadata.total_bridges)}`);
            } else {
                parts.push(`${fmt(curBridges)} bridges`);
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
     * Get display text for processing stage.
     * 
     * @param {string} status - Processing status
     * @param {string} stage - Current stage name
     * @returns {string} Human-readable stage text
     */
    getStageDisplayText(status, stage) {
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
     * @param {HTMLElement} card - Status card element
     * @param {Object} summary - Processing summary
     * 
     * Requirement: 4.4
     */
    showCompletionState(card, summary) {
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
                <span class="complete-icon">✓</span>
                <span class="complete-text">${summaryText}</span>
            </div>
        `;
    }

    /**
     * Show failure state on status card with retry option.
     * 
     * @param {HTMLElement} card - Status card element
     * @param {string} error - Error message
     * 
     * Requirement: 4.5
     */
    showFailureState(card, error) {
        const bodyElement = card.querySelector('.processing-status-body');
        if (!bodyElement) return;

        const documentId = card.getAttribute('data-document-id');

        bodyElement.innerHTML = `
            <div class="processing-failed">
                <span class="failed-icon">✗</span>
                <span class="failed-text">${this.escapeHtml(error || 'Processing failed')}</span>
            </div>
            <button class="retry-btn" data-document-id="${documentId}">
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
     * Handle processing completion.
     * 
     * @param {string} documentId - Document ID
     * @param {string} filename - Document filename
     * @param {Object} summary - Processing summary
     * 
     * Requirement: 3.6
     */
    handleProcessingComplete(documentId, filename, summary) {
        // Remove from active uploads
        this.activeUploads.forEach((value, key) => {
            if (value.file && value.file.name === filename) {
                this.activeUploads.delete(key);
            }
        });

        // Emit completion event
        this.emit('processingComplete', { documentId, filename, summary });

        // Auto-remove status card after delay
        setTimeout(() => {
            this.removeProcessingStatusCard(documentId);
        }, 5000);
    }

    /**
     * Handle processing failure.
     * 
     * @param {string} documentId - Document ID
     * @param {string} filename - Document filename
     * @param {string} error - Error message
     */
    handleProcessingFailed(documentId, filename, error) {
        // Emit failure event
        this.emit('processingFailed', { documentId, filename, error });
    }

    /**
     * Handle upload error from server.
     * 
     * @param {Object} data - Error message data
     */
    handleUploadError(data) {
        const { filename, error_message } = data;

        console.error('Upload error:', data);

        // Find any status card for this file and update it
        let foundCard = false;
        this.processingStatusCards.forEach((card, docId) => {
            const filenameElement = card.querySelector('.processing-filename');
            if (filenameElement && filenameElement.textContent === filename) {
                foundCard = true;
                // Update the card to show failure state
                this.showFailureState(card, error_message);
                card.classList.remove('status-processing');
                card.classList.add('status-failed');

                // Auto-remove after delay
                setTimeout(() => {
                    this.removeProcessingStatusCard(docId);
                }, 10000);
            }
        });

        // Always show system message for errors (status card may not exist
        // for early errors like duplicates)
        this.chatApp.addSystemMessage(
            `Upload failed for ${filename}: ${error_message}`,
            'error'
        );

        // If we found a card, remove it since we're showing the error message
        if (foundCard) {
            this.processingStatusCards.forEach((card, docId) => {
                const filenameElement = card.querySelector('.processing-filename');
                if (filenameElement && filenameElement.textContent === filename) {
                    // Remove immediately since error message is shown
                    this.removeProcessingStatusCard(docId);
                }
            });
        }

        // Also hide the upload progress bar
        this.hideUploadProgress({ name: filename });

        // Emit error event
        this.emit('uploadError', data);
    }

    /**
     * Retry document processing.
     * 
     * @param {string} documentId - Document ID to retry
     * 
     * Requirement: 8.4
     */
    retryDocumentProcessing(documentId) {
        if (!this.wsManager || !this.wsManager.isConnected()) {
            this.chatApp.addSystemMessage(
                'Cannot retry: Not connected to server',
                'error'
            );
            return;
        }

        // Send retry request
        this.wsManager.send({
            type: 'document_retry_request',
            document_id: documentId
        });

        // Reset status card to processing state
        const card = this.processingStatusCards.get(documentId);
        if (card) {
            card.classList.remove('status-failed');
            card.classList.add('status-processing');

            const bodyElement = card.querySelector('.processing-status-body');
            if (bodyElement) {
                bodyElement.innerHTML = `
                    <div class="processing-stage">Retrying...</div>
                    <div class="processing-progress-container">
                        <div class="processing-progress-bar">
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
        const card = this.processingStatusCards.get(documentId);
        if (card && card.parentNode) {
            card.parentNode.removeChild(card);
        }
        this.processingStatusCards.delete(documentId);
    }

    /**
     * Scroll chat to bottom.
     */
    scrollToBottom() {
        const chatMessages = document.getElementById('chatMessages');
        if (chatMessages) {
            requestAnimationFrame(() => {
                chatMessages.scrollTop = chatMessages.scrollHeight;
            });
        }
    }

    /**
     * Escape HTML to prevent XSS.
     * 
     * @param {string} text - Text to escape
     * @returns {string} Escaped text
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Override parent handleFiles to use chat-specific upload.
     * 
     * @param {FileList} files - Files to handle
     */
    handleFiles(files) {
        this.handleChatUpload(files);
    }

    /**
     * Override parent handlePaste to use chat-specific upload.
     * 
     * @param {ClipboardEvent} e - Paste event
     * 
     * Requirement: 1.3
     */
    handlePaste(e) {
        const items = e.clipboardData?.items;
        if (!items) return;

        const files = [];

        for (let i = 0; i < items.length; i++) {
            const item = items[i];
            if (item.kind === 'file') {
                const file = item.getAsFile();
                if (file) {
                    files.push(file);
                }
            }
        }

        // Handle pasted files through chat upload
        if (files.length > 0) {
            e.preventDefault();
            this.handleChatUpload(files);
        }
    }

    /**
     * Request document list from server.
     * 
     * Requirement: 8.2
     */
    requestDocumentList() {
        if (!this.wsManager || !this.wsManager.isConnected()) {
            console.warn('Cannot request document list: Not connected');
            return;
        }

        this.wsManager.send({
            type: 'document_list_request'
        });
    }

    /**
     * Request document deletion.
     * 
     * @param {string} documentId - Document ID to delete
     * 
     * Requirement: 8.3
     */
    requestDocumentDelete(documentId) {
        if (!this.wsManager || !this.wsManager.isConnected()) {
            this.chatApp.addSystemMessage(
                'Cannot delete: Not connected to server',
                'error'
            );
            return;
        }

        this.wsManager.send({
            type: 'document_delete_request',
            document_id: documentId
        });
    }
}

// Export for use in other modules
window.ChatUploadHandler = ChatUploadHandler;
