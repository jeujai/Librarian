/**
 * Document Manager JavaScript
 * Handles document upload, management, and user interactions
 */

class DocumentManager {
    constructor() {
        this.currentPage = 1;
        this.pageSize = 12;
        this.currentView = 'grid';
        this.searchQuery = '';
        this.statusFilter = '';
        this.sortBy = 'upload_timestamp';
        this.sortOrder = 'desc';
        this.uploadQueue = [];
        this.isUploading = false;

        this.init();
    }

    init() {
        this.setupEventListeners();
        this.loadDocuments();
        this.loadStatistics();

        // Auto-refresh every 30 seconds
        setInterval(() => {
            this.loadDocuments();
            this.loadStatistics();
        }, 30000);
    }

    setupEventListeners() {
        // Upload button
        document.getElementById('uploadBtn').addEventListener('click', () => {
            this.toggleUploadArea();
        });

        // File input and drag-drop
        const uploadZone = document.getElementById('uploadZone');
        const fileInput = document.getElementById('fileInput');

        uploadZone.addEventListener('click', () => {
            fileInput.click();
        });

        document.getElementById('browseFiles').addEventListener('click', (e) => {
            e.stopPropagation();
            fileInput.click();
        });

        fileInput.addEventListener('change', (e) => {
            this.handleFiles(e.target.files);
        });

        // Drag and drop
        uploadZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadZone.classList.add('dragover');
        });

        uploadZone.addEventListener('dragleave', (e) => {
            e.preventDefault();
            uploadZone.classList.remove('dragover');
        });

        uploadZone.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadZone.classList.remove('dragover');
            this.handleFiles(e.dataTransfer.files);
        });

        // Search and filters
        document.getElementById('searchInput').addEventListener('input', (e) => {
            this.searchQuery = e.target.value;
            this.debounceSearch();
        });

        document.getElementById('statusFilter').addEventListener('change', (e) => {
            this.statusFilter = e.target.value;
            this.currentPage = 1;
            this.loadDocuments();
        });

        document.getElementById('sortBy').addEventListener('change', (e) => {
            this.sortBy = e.target.value;
            this.currentPage = 1;
            this.loadDocuments();
        });

        document.getElementById('sortOrder').addEventListener('change', (e) => {
            this.sortOrder = e.target.value;
            this.currentPage = 1;
            this.loadDocuments();
        });

        // View toggle
        document.getElementById('gridView').addEventListener('click', () => {
            this.setView('grid');
        });

        document.getElementById('listView').addEventListener('click', () => {
            this.setView('list');
        });

        // Pagination
        document.getElementById('prevPage').addEventListener('click', () => {
            if (this.currentPage > 1) {
                this.currentPage--;
                this.loadDocuments();
            }
        });

        document.getElementById('nextPage').addEventListener('click', () => {
            this.currentPage++;
            this.loadDocuments();
        });

        // Modal
        document.getElementById('closeModal').addEventListener('click', () => {
            this.closeModal();
        });

        document.getElementById('documentModal').addEventListener('click', (e) => {
            if (e.target.id === 'documentModal') {
                this.closeModal();
            }
        });

        // Modal actions
        document.getElementById('downloadBtn').addEventListener('click', () => {
            this.downloadDocument();
        });

        document.getElementById('deleteBtn').addEventListener('click', () => {
            this.deleteDocument();
        });

        document.getElementById('retryBtn').addEventListener('click', () => {
            this.retryProcessing();
        });
    }

    debounceSearch() {
        clearTimeout(this.searchTimeout);
        this.searchTimeout = setTimeout(() => {
            this.currentPage = 1;
            this.loadDocuments();
        }, 500);
    }

    toggleUploadArea() {
        const uploadArea = document.getElementById('uploadArea');
        uploadArea.classList.toggle('hidden');
    }

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

    async uploadFiles(files) {
        if (this.isUploading) {
            this.showToast('warning', 'Upload already in progress');
            return;
        }

        this.isUploading = true;
        const progressContainer = document.getElementById('uploadProgress');
        const progressList = document.getElementById('progressList');

        progressContainer.classList.remove('hidden');
        progressList.innerHTML = '';

        for (let file of files) {
            const progressItem = this.createProgressItem(file.name);
            progressList.appendChild(progressItem);

            try {
                await this.uploadFile(file, progressItem);
            } catch (error) {
                console.error('Upload failed:', error);
                this.updateProgressItem(progressItem, 0, 'error', 'Upload failed');
            }
        }

        this.isUploading = false;

        // Hide upload area and refresh documents
        setTimeout(() => {
            progressContainer.classList.add('hidden');
            document.getElementById('uploadArea').classList.add('hidden');
            this.loadDocuments();
            this.loadStatistics();
        }, 2000);
    }

    createProgressItem(filename) {
        const item = document.createElement('div');
        item.className = 'progress-item';
        item.innerHTML = `
            <div class="progress-info">
                <i class="fas fa-file-pdf"></i>
                <span class="filename">${filename}</span>
            </div>
            <div class="progress-bar">
                <div class="progress-fill" style="width: 0%"></div>
            </div>
            <span class="progress-status">Uploading...</span>
        `;
        return item;
    }

    updateProgressItem(item, progress, status, message) {
        const progressFill = item.querySelector('.progress-fill');
        const progressStatus = item.querySelector('.progress-status');

        progressFill.style.width = `${progress}%`;
        progressStatus.textContent = message;
        progressStatus.className = `progress-status ${status}`;
    }

    async uploadFile(file, progressItem) {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('title', file.name.replace('.pdf', ''));
        formData.append('user_id', 'default_user');

        try {
            const response = await fetch('/api/documents/upload', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Upload failed');
            }

            const result = await response.json();
            this.updateProgressItem(progressItem, 100, 'success', 'Upload complete');
            this.showToast('success', `${file.name} uploaded successfully`);

            return result;
        } catch (error) {
            this.updateProgressItem(progressItem, 0, 'error', error.message);
            this.showToast('error', `Failed to upload ${file.name}: ${error.message}`);
            throw error;
        }
    }

    async loadDocuments() {
        const loadingState = document.getElementById('loadingState');
        const documentGrid = document.getElementById('documentGrid');
        const emptyState = document.getElementById('emptyState');

        loadingState.classList.remove('hidden');
        documentGrid.innerHTML = '';
        emptyState.classList.add('hidden');

        try {
            const params = new URLSearchParams({
                page: this.currentPage,
                page_size: this.pageSize,
                sort_by: this.sortBy,
                sort_order: this.sortOrder
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

            loadingState.classList.add('hidden');

            if (data.documents.length === 0) {
                emptyState.classList.remove('hidden');
            } else {
                this.renderDocuments(data.documents);
                this.updatePagination(data);
            }

        } catch (error) {
            console.error('Error loading documents:', error);
            loadingState.classList.add('hidden');
            this.showToast('error', 'Failed to load documents');
        }
    }

    renderDocuments(documents) {
        const documentGrid = document.getElementById('documentGrid');
        documentGrid.innerHTML = '';

        documents.forEach(doc => {
            const card = this.createDocumentCard(doc);
            documentGrid.appendChild(card);
        });
    }

    createDocumentCard(doc) {
        const card = document.createElement('div');
        card.className = 'document-card';
        card.addEventListener('click', () => this.showDocumentDetails(doc));

        const statusClass = `status-${doc.status}`;
        const statusIcon = this.getStatusIcon(doc.status);
        const fileSize = this.formatFileSize(doc.file_size);
        const uploadDate = new Date(doc.upload_timestamp).toLocaleDateString();

        card.innerHTML = `
            <div class="document-header">
                <i class="fas fa-file-pdf document-icon"></i>
                <div class="document-info">
                    <div class="document-title">${doc.title}</div>
                    <div class="document-filename">${doc.filename}</div>
                </div>
            </div>
            <div class="document-meta">
                <span><i class="fas fa-calendar"></i> ${uploadDate}</span>
                <span><i class="fas fa-hdd"></i> ${fileSize}</span>
                ${doc.page_count ? `<span><i class="fas fa-file-alt"></i> ${doc.page_count} pages</span>` : ''}
            </div>
            <div class="document-status ${statusClass}">
                <i class="fas ${statusIcon}"></i>
                ${doc.status.charAt(0).toUpperCase() + doc.status.slice(1)}
            </div>
        `;

        return card;
    }

    getStatusIcon(status) {
        const icons = {
            uploaded: 'fa-upload',
            processing: 'fa-spinner fa-spin',
            completed: 'fa-check-circle',
            failed: 'fa-exclamation-triangle'
        };
        return icons[status] || 'fa-question-circle';
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    updatePagination(data) {
        const pagination = document.getElementById('pagination');
        const prevBtn = document.getElementById('prevPage');
        const nextBtn = document.getElementById('nextPage');
        const pageInfo = document.getElementById('pageInfo');

        const totalPages = Math.ceil(data.total_count / this.pageSize);

        if (totalPages <= 1) {
            pagination.classList.add('hidden');
            return;
        }

        pagination.classList.remove('hidden');

        prevBtn.disabled = this.currentPage <= 1;
        nextBtn.disabled = this.currentPage >= totalPages;

        pageInfo.textContent = `Page ${this.currentPage} of ${totalPages}`;
    }

    setView(view) {
        this.currentView = view;
        const documentGrid = document.getElementById('documentGrid');
        const gridBtn = document.getElementById('gridView');
        const listBtn = document.getElementById('listView');

        if (view === 'grid') {
            documentGrid.classList.remove('list-view');
            gridBtn.classList.add('active');
            listBtn.classList.remove('active');
        } else {
            documentGrid.classList.add('list-view');
            listBtn.classList.add('active');
            gridBtn.classList.remove('active');
        }
    }

    async loadStatistics() {
        try {
            const response = await fetch('/api/documents/stats/summary');

            if (!response.ok) {
                throw new Error('Failed to load statistics');
            }

            const stats = await response.json();

            document.getElementById('totalDocs').textContent = stats.total_documents || 0;
            document.getElementById('totalSize').textContent = `${stats.total_size_mb || 0} MB`;
            document.getElementById('processingCount').textContent = stats.status_counts?.processing || 0;

        } catch (error) {
            console.error('Error loading statistics:', error);
        }
    }

    async showDocumentDetails(doc) {
        const modal = document.getElementById('documentModal');
        const modalTitle = document.getElementById('modalTitle');
        const modalBody = document.getElementById('modalBody');
        const retryBtn = document.getElementById('retryBtn');

        modalTitle.textContent = doc.title;

        // Show/hide retry button based on status
        if (doc.status === 'failed') {
            retryBtn.classList.remove('hidden');
        } else {
            retryBtn.classList.add('hidden');
        }

        // Store current document for modal actions
        this.currentDocument = doc;

        modalBody.innerHTML = `
            <div class="document-details">
                <div class="detail-row">
                    <strong>Filename:</strong> ${doc.filename}
                </div>
                <div class="detail-row">
                    <strong>File Size:</strong> ${this.formatFileSize(doc.file_size)}
                </div>
                <div class="detail-row">
                    <strong>Status:</strong> 
                    <span class="document-status ${`status-${doc.status}`}">
                        <i class="fas ${this.getStatusIcon(doc.status)}"></i>
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
                ${doc.chunk_count ? `
                <div class="detail-row">
                    <strong>Chunks:</strong> ${doc.chunk_count}
                </div>
                ` : ''}
                ${doc.processing_started_at ? `
                <div class="detail-row">
                    <strong>Processing Started:</strong> ${new Date(doc.processing_started_at).toLocaleString()}
                </div>
                ` : ''}
                ${doc.processing_completed_at ? `
                <div class="detail-row">
                    <strong>Processing Completed:</strong> ${new Date(doc.processing_completed_at).toLocaleString()}
                </div>
                ` : ''}
                ${doc.processing_error ? `
                <div class="detail-row">
                    <strong>Error:</strong> 
                    <span class="text-danger">${doc.processing_error}</span>
                </div>
                ` : ''}
                ${doc.description ? `
                <div class="detail-row">
                    <strong>Description:</strong> ${doc.description}
                </div>
                ` : ''}
            </div>
        `;

        modal.classList.remove('hidden');
    }

    closeModal() {
        document.getElementById('documentModal').classList.add('hidden');
        this.currentDocument = null;
    }

    async downloadDocument() {
        if (!this.currentDocument) return;

        try {
            const response = await fetch(`/api/documents/${this.currentDocument.id}/download`);

            if (!response.ok) {
                throw new Error('Download failed');
            }

            const data = await response.json();

            // Open download URL in new tab
            window.open(data.download_url, '_blank');

        } catch (error) {
            console.error('Download error:', error);
            this.showToast('error', 'Failed to download document');
        }
    }

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
            this.closeModal();
            this.loadDocuments();
            this.loadStatistics();

        } catch (error) {
            console.error('Delete error:', error);
            this.showToast('error', 'Failed to delete document');
        }
    }

    async retryProcessing() {
        if (!this.currentDocument) return;

        try {
            const response = await fetch(`/api/documents/${this.currentDocument.id}/retry`, {
                method: 'POST'
            });

            if (!response.ok) {
                throw new Error('Retry failed');
            }

            this.showToast('success', 'Processing retry initiated');
            this.closeModal();
            this.loadDocuments();

        } catch (error) {
            console.error('Retry error:', error);
            this.showToast('error', 'Failed to retry processing');
        }
    }

    showToast(type, message) {
        const container = document.getElementById('toastContainer');
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;

        const icon = {
            success: 'fa-check-circle',
            error: 'fa-exclamation-circle',
            warning: 'fa-exclamation-triangle',
            info: 'fa-info-circle'
        }[type] || 'fa-info-circle';

        toast.innerHTML = `
            <i class="fas ${icon}"></i>
            <span>${message}</span>
        `;

        container.appendChild(toast);

        // Auto-remove after 5 seconds
        setTimeout(() => {
            toast.remove();
        }, 5000);

        // Click to dismiss
        toast.addEventListener('click', () => {
            toast.remove();
        });
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new DocumentManager();
});