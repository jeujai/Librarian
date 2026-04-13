/**
 * Unified Interface Controller
 * Manages the integrated chat and document management interface
 */

class UnifiedInterface {
    constructor() {
        this.currentView = 'chat';
        this.wsManager = new WebSocketManager();
        this.fileHandler = new FileHandler();
        this.currentThreadId = null;
        this.messageHistory = [];
        this.commandHistory = [];
        this.commandHistoryIndex = -1;
        this.commandDraft = '';
        this.documents = [];
        this.currentDocument = null;
        this.searchQuery = '';
        this.statusFilter = '';
        this.currentPage = 1;
        this.pageSize = 12;

        this.initializeElements();
        this.setupEventListeners();
        this.setupWebSocketHandlers();
        this.setupFileHandlers();
        this.initializeInterface();
    }

    /**
     * Initialize DOM elements
     */
    initializeElements() {
        // Navigation elements
        this.navItems = document.querySelectorAll('.nav-item[data-view]');
        this.viewContainers = document.querySelectorAll('.view-container');

        // Connection status
        this.statusIndicator = document.getElementById('statusIndicator');
        this.statusText = document.getElementById('statusText');

        // Chat elements
        this.chatMessages = document.getElementById('chatMessages');
        this.messageInput = document.getElementById('messageInput');
        this.chatForm = document.getElementById('chatForm');
        this.sendBtn = document.getElementById('sendBtn');
        this.processingIndicator = document.getElementById('processingIndicator');
        this.newChatBtn = document.getElementById('newChatBtn');
        this.exportBtn = document.getElementById('exportBtn');
        this.characterCount = document.getElementById('characterCount');
        this.uploadQuickBtn = document.getElementById('uploadQuickBtn');

        // Document elements
        this.documentSearchInput = document.getElementById('documentSearchInput');
        this.statusFilter = document.getElementById('statusFilter');
        this.gridViewBtn = document.getElementById('gridViewBtn');
        this.listViewBtn = document.getElementById('listViewBtn');
        this.documentList = document.getElementById('documentList');
        this.documentsLoading = document.getElementById('documentsLoading');
        this.documentsEmpty = document.getElementById('documentsEmpty');
        this.uploadDocumentBtn = document.getElementById('uploadDocumentBtn');
        this.refreshDocumentsBtn = document.getElementById('refreshDocumentsBtn');

        // Document stats
        this.totalDocuments = document.getElementById('totalDocuments');
        this.totalSize = document.getElementById('totalSize');
        this.processingCount = document.getElementById('processingCount');
        this.documentCount = document.getElementById('documentCount');

        // Search elements
        this.globalSearchInput = document.getElementById('globalSearchInput');
        this.globalSearchBtn = document.getElementById('globalSearchBtn');
        this.searchResults = document.getElementById('searchResults');

        // Modal elements
        this.uploadModal = document.getElementById('uploadModal');
        this.uploadModalClose = document.getElementById('uploadModalClose');
        this.uploadArea = document.getElementById('uploadArea');
        this.fileInput = document.getElementById('fileInput');
        this.uploadProgress = document.getElementById('uploadProgress');
        this.progressText = document.getElementById('progressText');
        this.progressPercent = document.getElementById('progressPercent');
        this.progressBar = document.getElementById('progressBar');

        this.documentModal = document.getElementById('documentModal');
        this.documentModalClose = document.getElementById('documentModalClose');
        this.documentModalTitle = document.getElementById('documentModalTitle');
        this.documentModalBody = document.getElementById('documentModalBody');
        this.chatAboutDocBtn = document.getElementById('chatAboutDocBtn');
        this.downloadDocBtn = document.getElementById('downloadDocBtn');
        this.deleteDocBtn = document.getElementById('deleteDocBtn');

        // Toast container
        this.toastContainer = document.getElementById('toastContainer');
    }

    /**
     * Set up event listeners
     */
    setupEventListeners() {
        // Navigation
        this.navItems.forEach(item => {
            item.addEventListener('click', () => {
                const view = item.dataset.view;
                this.switchView(view);
            });
        });

        // Chat form submission
        this.chatForm.addEventListener('submit', (e) => {
            e.preventDefault();
            this.sendMessage();
        });

        // Message input handling
        this.messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                this.sendMessage();
            }
            // Command history: Ctrl+Up to go back, Ctrl+Down to go forward
            if (e.key === 'ArrowUp' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                if (this.commandHistory.length === 0) return;
                if (this.commandHistoryIndex === -1) {
                    this.commandDraft = this.messageInput.value;
                    this.commandHistoryIndex = this.commandHistory.length - 1;
                } else if (this.commandHistoryIndex > 0) {
                    this.commandHistoryIndex--;
                }
                this.messageInput.value = this.commandHistory[this.commandHistoryIndex];
                this.autoResizeTextarea();
                this.updateCharacterCount();
            }
            if (e.key === 'ArrowDown' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                if (this.commandHistoryIndex === -1) return;
                if (this.commandHistoryIndex < this.commandHistory.length - 1) {
                    this.commandHistoryIndex++;
                    this.messageInput.value = this.commandHistory[this.commandHistoryIndex];
                } else {
                    this.commandHistoryIndex = -1;
                    this.messageInput.value = this.commandDraft;
                }
                this.autoResizeTextarea();
                this.updateCharacterCount();
            }
        });

        this.messageInput.addEventListener('input', () => {
            this.autoResizeTextarea();
            this.updateSendButton();
            this.updateCharacterCount();
        });

        // Chat buttons
        this.newChatBtn.addEventListener('click', () => {
            this.clearChat();
        });

        this.exportBtn.addEventListener('click', () => {
            this.showExportOptions();
        });

        this.uploadQuickBtn.addEventListener('click', () => {
            this.showUploadModal();
        });

        // Document search and filters
        this.documentSearchInput.addEventListener('input', (e) => {
            this.searchQuery = e.target.value;
            this.debounceDocumentSearch();
        });

        this.statusFilter.addEventListener('change', (e) => {
            this.statusFilter = e.target.value;
            this.currentPage = 1;
            this.loadDocuments();
        });

        // View toggle
        this.gridViewBtn.addEventListener('click', () => {
            this.setDocumentView('grid');
        });

        this.listViewBtn.addEventListener('click', () => {
            this.setDocumentView('list');
        });

        // Document actions
        this.uploadDocumentBtn.addEventListener('click', () => {
            this.showUploadModal();
        });

        this.refreshDocumentsBtn.addEventListener('click', () => {
            this.loadDocuments();
            this.loadDocumentStats();
        });

        // Global search
        this.globalSearchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                this.performGlobalSearch();
            }
        });

        this.globalSearchBtn.addEventListener('click', () => {
            this.performGlobalSearch();
        });

        // Upload modal
        this.uploadModalClose.addEventListener('click', () => {
            this.hideUploadModal();
        });

        this.uploadModal.addEventListener('click', (e) => {
            if (e.target === this.uploadModal) {
                this.hideUploadModal();
            }
        });

        // Upload area
        this.uploadArea.addEventListener('click', () => {
            this.fileInput.click();
        });

        this.fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                this.handleFiles(e.target.files);
                e.target.value = '';
            }
        });

        // Drag and drop
        this.uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            this.uploadArea.classList.add('dragover');
        });

        this.uploadArea.addEventListener('dragleave', (e) => {
            e.preventDefault();
            this.uploadArea.classList.remove('dragover');
        });

        this.uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            this.uploadArea.classList.remove('dragover');
            this.handleFiles(e.dataTransfer.files);
        });

        // Document modal
        this.documentModalClose.addEventListener('click', () => {
            this.hideDocumentModal();
        });

        this.documentModal.addEventListener('click', (e) => {
            if (e.target === this.documentModal) {
                this.hideDocumentModal();
            }
        });

        this.chatAboutDocBtn.addEventListener('click', () => {
            this.chatAboutDocument();
        });

        this.downloadDocBtn.addEventListener('click', () => {
            this.downloadDocument();
        });

        this.deleteDocBtn.addEventListener('click', () => {
            this.deleteDocument();
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            // Escape to close modals
            if (e.key === 'Escape') {
                this.hideUploadModal();
                this.hideDocumentModal();
            }

            // Ctrl/Cmd + K for new chat
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                this.clearChat();
            }

            // Ctrl/Cmd + U for upload
            if ((e.ctrlKey || e.metaKey) && e.key === 'u') {
                e.preventDefault();
                this.showUploadModal();
            }

            // Number keys for navigation
            if (e.key >= '1' && e.key <= '3' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                const views = ['chat', 'documents', 'search'];
                const index = parseInt(e.key) - 1;
                if (views[index]) {
                    this.switchView(views[index]);
                }
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
            console.log('Connected to server');
            this.updateConnectionStatus('connected');
            // On reconnect, resume existing thread instead of creating a new one
            if (this.currentThreadId) {
                console.log('Resuming conversation:', this.currentThreadId);
                this.wsManager.send({
                    type: 'resume_conversation',
                    thread_id: this.currentThreadId
                });
            } else {
                this.startNewConversation();
            }
        });

        this.wsManager.on('disconnected', () => {
            console.log('Disconnected from server');
            this.updateConnectionStatus('disconnected');
        });

        this.wsManager.on('message', (data) => {
            this.handleServerMessage(data);
        });

        this.wsManager.on('error', (data) => {
            this.handleServerError(data);
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
                    p.textContent = paragraph.trim();
                    contentDiv.appendChild(p);
                }
            });
        }

        this.scrollToBottom();
    }

    /**
     * Handle streaming complete - finalize message and add citations
     */
    handleStreamingComplete(data) {
        console.log('Streaming complete:', data.metadata);

        this.streamingState.isStreaming = false;

        // Add citations if available
        if (this.streamingState.citations.length > 0 && this.streamingState.currentMessageElement) {
            this.addCitationsToElement(this.streamingState.currentMessageElement, this.streamingState.citations);
        }

        // Add to message history
        this.messageHistory.push({
            type: 'system',
            content: this.streamingState.currentContent,
            messageType: 'info',
            timestamp: new Date(),
            metadata: data.metadata
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
        this.showToast('warning', data.message);
    }

    /**
     * Add citations to a specific message element
     */
    addCitationsToElement(messageElement, citations) {
        if (!citations || citations.length === 0) return;

        const citationsDiv = document.createElement('div');
        citationsDiv.className = 'message-citations';

        const toggle = document.createElement('button');
        toggle.className = 'citations-toggle';
        toggle.setAttribute('aria-expanded', 'false');
        toggle.innerHTML = '<span class="citations-arrow">▶</span> Sources:';
        citationsDiv.appendChild(toggle);

        const citationsList = document.createElement('div');
        citationsList.className = 'citations-list';

        toggle.addEventListener('click', () => {
            const expanded = toggle.getAttribute('aria-expanded') === 'true';
            toggle.setAttribute('aria-expanded', String(!expanded));
            citationsList.classList.toggle('expanded');
        });

        citations.forEach((citation, index) => {
            const citationDiv = document.createElement('div');
            citationDiv.className = 'citation';
            citationDiv.setAttribute('aria-label', `Source ${index + 1}: ${citation.document_title || citation.source_title || 'Unknown'}`);

            const sourceNum = document.createElement('span');
            sourceNum.textContent = `${index + 1}.`;
            sourceNum.style.cssText = 'font-weight:600;margin-right:6px;color:#475569;min-width:1.2em;';

            const isWebSource = citation.url && citation.source_type === 'web_search';
            const icon = document.createElement('span');
            icon.textContent = isWebSource ? '🔗' : '📖';
            icon.setAttribute('aria-hidden', 'true');

            const text = document.createElement('span');
            const docTitle = citation.document_title || citation.source_title || 'Unknown';
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
            citationsList.appendChild(citationDiv);
        });

        citationsDiv.appendChild(citationsList);

        const contentDiv = messageElement.querySelector('.message-content');
        if (contentDiv) {
            contentDiv.appendChild(citationsDiv);
        }
    }

    /**
     * Set up file handler event listeners
     */
    setupFileHandlers() {
        this.fileHandler.on('uploadComplete', (data) => {
            this.showToast('success', `Successfully uploaded ${data.files.length} file(s)`);
            this.hideUploadModal();
            this.loadDocuments();
            this.loadDocumentStats();
        });

        this.fileHandler.on('error', (data) => {
            this.showToast('error', `Upload error: ${data.message}`);
        });

        this.fileHandler.on('progress', (data) => {
            this.updateUploadProgress(data.progress, data.message);
        });
    }

    /**
     * Initialize the interface
     */
    initializeInterface() {
        // Connect to WebSocket
        this.wsManager.connect();

        // Load initial data
        this.loadDocuments();
        this.loadDocumentStats();

        // Focus on message input
        this.messageInput.focus();

        // Set up auto-refresh
        setInterval(() => {
            if (this.currentView === 'documents') {
                this.loadDocuments();
                this.loadDocumentStats();
            }
        }, 30000);
    }

    /**
     * Switch between views
     */
    switchView(view) {
        if (this.currentView === view) return;

        // Update navigation
        this.navItems.forEach(item => {
            item.classList.toggle('active', item.dataset.view === view);
        });

        // Update view containers
        this.viewContainers.forEach(container => {
            container.classList.toggle('active', container.id === `${view}View`);
        });

        this.currentView = view;

        // Load data for the new view
        if (view === 'documents') {
            this.loadDocuments();
            this.loadDocumentStats();
        } else if (view === 'chat') {
            this.messageInput.focus();
        }
    }

    /**
     * Update connection status
     */
    updateConnectionStatus(status) {
        this.statusIndicator.className = `status-indicator ${status}`;

        const statusMessages = {
            connected: 'Connected',
            disconnected: 'Disconnected',
            connecting: 'Connecting...'
        };

        this.statusText.textContent = statusMessages[status] || 'Unknown';
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

        // Add to command history buffer
        if (this.commandHistory.length === 0 || this.commandHistory[this.commandHistory.length - 1] !== message) {
            this.commandHistory.push(message);
        }
        this.commandHistoryIndex = -1;
        this.commandDraft = '';

        // Add user message to chat
        this.addUserMessage(message);

        // Clear input
        this.messageInput.value = '';
        this.autoResizeTextarea();
        this.updateSendButton();
        this.updateCharacterCount();

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
     */
    handleServerMessage(data) {
        switch (data.type) {
            case 'conversation_started':
                this.currentThreadId = data.thread_id;
                console.log('Conversation started:', this.currentThreadId);
                break;

            case 'conversation_resumed':
                this.currentThreadId = data.thread_id;
                console.log('Conversation resumed:', this.currentThreadId);
                break;

            case 'response':
                this.handleChatResponse(data);
                break;

            case 'error':
                this.handleServerError(data);
                break;

            case 'processing':
                this.showProcessingIndicator(data.message);
                break;

            case 'processing_complete':
                this.hideProcessingIndicator();
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

            // Handle citations
            if (data.response.citations && data.response.citations.length > 0) {
                this.addCitations(data.response.citations);
            }

            // Handle confidence score
            if (data.response.confidence_score !== undefined) {
                this.addConfidenceInfo(data.response.confidence_score);
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
     * Add citations to the last message
     */
    addCitations(citations) {
        if (!citations || citations.length === 0) return;

        const citationsDiv = document.createElement('div');
        citationsDiv.className = 'message-citations';

        const toggle = document.createElement('button');
        toggle.className = 'citations-toggle';
        toggle.setAttribute('aria-expanded', 'false');
        toggle.innerHTML = '<span class="citations-arrow">▶</span> Sources:';
        citationsDiv.appendChild(toggle);

        const citationsList = document.createElement('div');
        citationsList.className = 'citations-list';

        toggle.addEventListener('click', () => {
            const expanded = toggle.getAttribute('aria-expanded') === 'true';
            toggle.setAttribute('aria-expanded', String(!expanded));
            citationsList.classList.toggle('expanded');
        });

        citations.forEach((citation, index) => {
            const citationDiv = document.createElement('div');
            citationDiv.className = 'citation';
            citationDiv.setAttribute('aria-label', `Source ${index + 1}: ${citation.document_title || citation.source || 'Unknown'}`);

            const sourceNum = document.createElement('span');
            sourceNum.textContent = `${index + 1}.`;
            sourceNum.style.cssText = 'font-weight:600;margin-right:6px;color:#475569;min-width:1.2em;';

            const isWebSource = citation.url && citation.source_type === 'web_search';
            const icon = document.createElement('span');
            icon.textContent = isWebSource ? '🔗' : '📄';
            icon.setAttribute('aria-hidden', 'true');

            const text = document.createElement('span');
            if (isWebSource) {
                const link = document.createElement('a');
                link.href = citation.url;
                link.target = '_blank';
                link.rel = 'noopener noreferrer';
                link.textContent = citation.document_title || citation.source || 'Unknown';
                link.style.color = '#3b82f6';
                link.style.textDecoration = 'underline';
                text.appendChild(link);
            } else {
                text.textContent = `${citation.document_title || citation.source} (Page ${citation.page || 'N/A'})`;
            }

            citationDiv.appendChild(sourceNum);
            citationDiv.appendChild(icon);

            // Add download button (to the left of the source text)
            const docTitleForDownload = citation.document_title || citation.source || 'Unknown';
            if (!isWebSource && citation.document_id) {
                const downloadBtn = document.createElement('button');
                downloadBtn.innerHTML = '⬇';
                downloadBtn.title = `Download ${docTitleForDownload}`;
                downloadBtn.setAttribute('aria-label', `Download ${docTitleForDownload}`);
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
            citationsList.appendChild(citationDiv);
        });

        citationsDiv.appendChild(citationsList);

        // Add to last system message
        const lastMessage = this.chatMessages.lastElementChild;
        if (lastMessage && lastMessage.classList.contains('system-message')) {
            const content = lastMessage.querySelector('.message-content');
            content.appendChild(citationsDiv);
        }

        this.scrollToBottom();
    }

    /**
     * Add confidence information
     */
    addConfidenceInfo(confidence) {
        if (confidence === undefined) return;

        const confidenceDiv = document.createElement('div');
        confidenceDiv.className = 'confidence-info';
        confidenceDiv.style.marginTop = '0.5rem';
        confidenceDiv.style.fontSize = '0.75rem';
        confidenceDiv.style.color = '#64748b';
        confidenceDiv.textContent = `Confidence: ${Math.round(confidence * 100)}%`;

        // Add to last system message
        const lastMessage = this.chatMessages.lastElementChild;
        if (lastMessage && lastMessage.classList.contains('system-message')) {
            const content = lastMessage.querySelector('.message-content');
            content.appendChild(confidenceDiv);
        }
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
     * Update send button state
     */
    updateSendButton() {
        const hasContent = this.messageInput.value.trim().length > 0;
        const isConnected = this.wsManager.isConnected();
        const withinLimit = this.messageInput.value.length <= 4000;

        this.sendBtn.disabled = !hasContent || !isConnected || !withinLimit;
    }

    /**
     * Generate a document title from the current conversation.
     * @returns {string}
     */
    _generateDocumentTitle() {
        const firstUserMsg = this.messageHistory.find(m => m.type === 'user');
        const date = new Date().toLocaleDateString('en-US', {
            month: 'short', day: 'numeric', year: 'numeric'
        });
        if (!firstUserMsg) return `Conversation: (untitled) (${date})`;

        let content = firstUserMsg.content;
        if (content.length > 80) content = content.substring(0, 80) + '\u2026';
        return `Conversation: ${content} (${date})`;
    }

    /**
     * Fire-and-forget POST to convert current conversation to knowledge.
     * Mirrors chat.js _convertCurrentConversation().
     */
    async _convertCurrentConversation() {
        const threadId = this.currentThreadId;
        const title = this._generateDocumentTitle();

        try {
            const response = await fetch(
                `/api/conversations/${threadId}/convert-to-knowledge`,
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ title })
                }
            );
            if (!response.ok) throw new Error(await response.text());
        } catch (err) {
            console.error('Conversation conversion failed:', err);
        }
    }

    /**
     * Clear chat history
     */
    clearChat() {
        // Convert current conversation if it has messages (fire-and-forget)
        if (this.messageHistory.length > 0 && this.currentThreadId) {
            this._convertCurrentConversation().catch(err => {
                console.error('Conversion on clear failed:', err);
            });
        }

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

    /**
     * Show export options
     */
    showExportOptions() {
        if (this.messageHistory.length === 0) {
            this.showToast('error', 'No conversation to export');
            return;
        }

        // For now, just export as text
        this.exportConversation('txt');
    }

    /**
     * Export conversation
     */
    exportConversation(format = 'txt') {
        if (this.messageHistory.length === 0) {
            this.showToast('error', 'No conversation to export');
            return;
        }

        this.wsManager.send({
            type: 'export_conversation',
            thread_id: this.currentThreadId,
            format: format
        });

        this.showToast('info', `Preparing ${format.toUpperCase()} export...`);
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
     * Load documents
     */
    async loadDocuments() {
        this.documentsLoading.style.display = 'flex';
        this.documentList.innerHTML = '';
        this.documentsEmpty.style.display = 'none';

        try {
            const params = new URLSearchParams({
                page: this.currentPage,
                page_size: this.pageSize
            });

            if (this.searchQuery) {
                params.append('query', this.searchQuery);
            }

            if (this.statusFilter) {
                params.append('status_filter', this.statusFilter);
            }

            const response = await fetch(`/api/documents/?${params}`);

            if (!response.ok) {
                throw new Error('Failed to load documents');
            }

            const data = await response.json();
            this.documents = data.documents || [];

            this.documentsLoading.style.display = 'none';

            if (this.documents.length === 0) {
                this.documentsEmpty.style.display = 'flex';
            } else {
                this.renderDocuments(this.documents);
            }

        } catch (error) {
            console.error('Error loading documents:', error);
            this.documentsLoading.style.display = 'none';
            this.showToast('error', 'Failed to load documents');
        }
    }

    /**
     * Render documents
     */
    renderDocuments(documents) {
        this.documentList.innerHTML = '';

        documents.forEach(doc => {
            const card = this.createDocumentCard(doc);
            this.documentList.appendChild(card);
        });
    }

    /**
     * Create document card
     */
    createDocumentCard(doc) {
        const card = document.createElement('div');
        card.className = 'document-card';
        card.addEventListener('click', () => this.showDocumentDetails(doc));

        const statusClass = `status-${doc.status}`;
        const fileSize = this.formatFileSize(doc.file_size);
        const uploadDate = new Date(doc.upload_timestamp).toLocaleDateString();

        card.innerHTML = `
            <div class="document-header">
                <svg class="document-icon" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                    <polyline points="14,2 14,8 20,8"></polyline>
                </svg>
                <div class="document-info">
                    <div class="document-title">${doc.title}</div>
                    <div class="document-filename">${doc.filename}</div>
                </div>
            </div>
            <div class="document-meta">
                <span>📅 ${uploadDate}</span>
                <span>💾 ${fileSize}</span>
                ${doc.page_count ? `<span>📄 ${doc.page_count} pages</span>` : ''}
            </div>
            <div class="document-status ${statusClass}">
                ${doc.status.charAt(0).toUpperCase() + doc.status.slice(1)}
            </div>
        `;

        return card;
    }

    /**
     * Load document statistics
     */
    async loadDocumentStats() {
        try {
            const response = await fetch('/api/documents/stats/summary');

            if (!response.ok) {
                throw new Error('Failed to load statistics');
            }

            const stats = await response.json();

            this.totalDocuments.textContent = stats.total_documents || 0;
            this.totalSize.textContent = `${stats.total_size_mb || 0} MB`;
            this.processingCount.textContent = stats.status_counts?.processing || 0;
            this.documentCount.textContent = stats.total_documents || 0;

        } catch (error) {
            console.error('Error loading statistics:', error);
        }
    }

    /**
     * Debounce document search
     */
    debounceDocumentSearch() {
        clearTimeout(this.searchTimeout);
        this.searchTimeout = setTimeout(() => {
            this.currentPage = 1;
            this.loadDocuments();
        }, 500);
    }

    /**
     * Set document view mode
     */
    setDocumentView(view) {
        this.gridViewBtn.classList.toggle('active', view === 'grid');
        this.listViewBtn.classList.toggle('active', view === 'list');
        this.documentList.classList.toggle('list-view', view === 'list');
    }

    /**
     * Show upload modal
     */
    showUploadModal() {
        this.uploadModal.style.display = 'flex';
        this.uploadProgress.style.display = 'none';
    }

    /**
     * Hide upload modal
     */
    hideUploadModal() {
        this.uploadModal.style.display = 'none';
        this.uploadProgress.style.display = 'none';
    }

    /**
     * Handle file uploads
     */
    handleFiles(files) {
        const validFiles = [];

        for (let file of files) {
            if (file.type !== 'application/pdf') {
                this.showToast('error', `${file.name} is not a PDF file`);
                continue;
            }

            if (file.size > 10 * 1024 * 1024 * 1024) {
                this.showToast('error', `${file.name} exceeds 10GB limit`);
                continue;
            }

            validFiles.push(file);
        }

        if (validFiles.length > 0) {
            this.uploadFiles(validFiles);
        }
    }

    /**
     * Upload files
     */
    async uploadFiles(files) {
        this.uploadProgress.style.display = 'block';

        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            const progress = ((i + 1) / files.length) * 100;

            this.updateUploadProgress(progress, `Uploading ${file.name}...`);

            try {
                await this.uploadFile(file);
            } catch (error) {
                console.error('Upload failed:', error);
                this.showToast('error', `Failed to upload ${file.name}`);
            }
        }

        this.updateUploadProgress(100, 'Upload complete!');

        setTimeout(() => {
            this.hideUploadModal();
            this.loadDocuments();
            this.loadDocumentStats();
        }, 1000);
    }

    /**
     * Upload single file
     */
    async uploadFile(file) {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('title', file.name.replace('.pdf', ''));
        formData.append('user_id', 'default_user');

        const response = await fetch('/api/documents/upload', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Upload failed');
        }

        return await response.json();
    }

    /**
     * Update upload progress
     */
    updateUploadProgress(progress, message) {
        this.progressText.textContent = message;
        this.progressPercent.textContent = `${Math.round(progress)}%`;
        this.progressBar.style.width = `${progress}%`;
    }

    /**
     * Show document details
     */
    showDocumentDetails(doc) {
        this.currentDocument = doc;
        this.documentModalTitle.textContent = doc.title;

        this.documentModalBody.innerHTML = `
            <div class="document-details">
                <div class="detail-row">
                    <strong>Filename:</strong> ${doc.filename}
                </div>
                <div class="detail-row">
                    <strong>File Size:</strong> ${this.formatFileSize(doc.file_size)}
                </div>
                <div class="detail-row">
                    <strong>Status:</strong> 
                    <span class="document-status status-${doc.status}">
                        ${doc.status.charAt(0).toUpperCase() + doc.status.slice(1)}
                    </span>
                </div>
                <div class="detail-row">
                    <strong>Upload Date:</strong> ${new Date(doc.upload_timestamp).toLocaleString()}
                </div>
                ${doc.page_count ? `
                <div class="detail-row">
                    <strong>Pages:</strong> ${doc.page_count}
                </div>
                ` : ''}
                ${doc.processing_error ? `
                <div class="detail-row">
                    <strong>Error:</strong> 
                    <span style="color: var(--error-color);">${doc.processing_error}</span>
                </div>
                ` : ''}
            </div>
        `;

        this.documentModal.style.display = 'flex';
    }

    /**
     * Hide document modal
     */
    hideDocumentModal() {
        this.documentModal.style.display = 'none';
        this.currentDocument = null;
    }

    /**
     * Chat about document
     */
    chatAboutDocument() {
        if (!this.currentDocument) return;

        this.hideDocumentModal();
        this.switchView('chat');

        // Pre-fill message input with document reference
        const message = `Tell me about the document "${this.currentDocument.title}"`;
        this.messageInput.value = message;
        this.messageInput.focus();
        this.updateSendButton();
        this.updateCharacterCount();
    }

    /**
     * Download document
     */
    async downloadDocument() {
        if (!this.currentDocument) return;

        try {
            const response = await fetch(`/api/documents/${this.currentDocument.id}/download`);

            if (!response.ok) {
                throw new Error('Download failed');
            }

            const data = await response.json();
            window.open(data.download_url, '_blank');

        } catch (error) {
            console.error('Download error:', error);
            this.showToast('error', 'Failed to download document');
        }
    }

    /**
     * Delete document
     */
    async deleteDocument() {
        if (!this.currentDocument) return;

        if (!confirm(`Are you sure you want to delete "${this.currentDocument.title}"? This action cannot be undone.`)) {
            return;
        }

        try {
            const response = await fetch(`/api/documents/${this.currentDocument.id}`, {
                method: 'DELETE'
            });

            if (!response.ok) {
                throw new Error('Delete failed');
            }

            this.showToast('success', 'Document deleted successfully');
            this.hideDocumentModal();
            this.loadDocuments();
            this.loadDocumentStats();

        } catch (error) {
            console.error('Delete error:', error);
            this.showToast('error', 'Failed to delete document');
        }
    }

    /**
     * Perform global search
     */
    async performGlobalSearch() {
        const query = this.globalSearchInput.value.trim();
        if (!query) return;

        this.searchResults.innerHTML = '<div class="loading-state"><div class="spinner large"></div><p>Searching...</p></div>';

        try {
            const response = await fetch('/api/search/global', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ query })
            });

            if (!response.ok) {
                throw new Error('Search failed');
            }

            const results = await response.json();
            this.renderSearchResults(results);

        } catch (error) {
            console.error('Search error:', error);
            this.searchResults.innerHTML = '<div class="empty-state"><p>Search failed. Please try again.</p></div>';
        }
    }

    /**
     * Render search results
     */
    renderSearchResults(results) {
        if (!results || results.length === 0) {
            this.searchResults.innerHTML = '<div class="empty-state"><p>No results found.</p></div>';
            return;
        }

        const resultsHtml = results.map(result => `
            <div class="search-result">
                <h3>${result.title}</h3>
                <p>${result.snippet}</p>
                <div class="result-meta">
                    <span>Score: ${Math.round(result.score * 100)}%</span>
                    <span>Source: ${result.source}</span>
                </div>
            </div>
        `).join('');

        this.searchResults.innerHTML = resultsHtml;
    }

    /**
     * Format file size
     */
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';

        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));

        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    /**
     * Show toast notification
     */
    showToast(type, message) {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;

        const icons = {
            success: '✅',
            error: '❌',
            warning: '⚠️',
            info: 'ℹ️'
        };

        toast.innerHTML = `
            <span>${icons[type] || 'ℹ️'}</span>
            <span>${message}</span>
        `;

        this.toastContainer.appendChild(toast);

        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 5000);

        // Click to dismiss
        toast.addEventListener('click', () => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        });
    }
}

// Initialize unified interface when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.unifiedInterface = new UnifiedInterface();
});