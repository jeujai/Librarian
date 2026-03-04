/**
 * File handling utilities for drag-and-drop and file uploads
 */

class FileHandler {
    constructor() {
        this.maxFileSize = 100 * 1024 * 1024; // 100MB
        this.supportedTypes = {
            'application/pdf': 'PDF',
            'text/plain': 'TXT',
            'application/msword': 'DOC',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'DOCX',
            'image/jpeg': 'JPG',
            'image/png': 'PNG',
            'image/gif': 'GIF',
            'image/webp': 'WEBP',
            'application/json': 'JSON',
            'text/csv': 'CSV',
            'application/vnd.ms-excel': 'XLS',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'XLSX'
        };

        this.eventHandlers = new Map();
        this.setupDragAndDrop();
    }

    /**
     * Set up drag and drop functionality
     */
    setupDragAndDrop() {
        const dragOverlay = document.getElementById('dragOverlay');
        let dragCounter = 0;

        // Prevent default drag behaviors on document
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            document.addEventListener(eventName, this.preventDefaults, false);
        });

        // Handle drag enter
        document.addEventListener('dragenter', (e) => {
            dragCounter++;
            if (this.hasFiles(e)) {
                dragOverlay.style.display = 'flex';
                document.body.classList.add('dragging');
            }
        });

        // Handle drag leave
        document.addEventListener('dragleave', (e) => {
            dragCounter--;
            if (dragCounter === 0) {
                dragOverlay.style.display = 'none';
                document.body.classList.remove('dragging');
            }
        });

        // Handle drop
        document.addEventListener('drop', (e) => {
            dragCounter = 0;
            dragOverlay.style.display = 'none';
            document.body.classList.remove('dragging');

            if (this.hasFiles(e)) {
                this.handleFiles(e.dataTransfer.files);
            }
        });

        // Handle paste events
        document.addEventListener('paste', (e) => {
            this.handlePaste(e);
        });
    }

    /**
     * Prevent default drag behaviors
     */
    preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    /**
     * Check if drag event contains files
     */
    hasFiles(e) {
        return e.dataTransfer && e.dataTransfer.types && e.dataTransfer.types.includes('Files');
    }

    /**
     * Handle file selection from input or drag-and-drop
     */
    handleFiles(files) {
        const fileArray = Array.from(files);

        // Validate files
        const validFiles = [];
        const errors = [];

        fileArray.forEach(file => {
            const validation = this.validateFile(file);
            if (validation.valid) {
                validFiles.push(file);
            } else {
                errors.push(`${file.name}: ${validation.error}`);
            }
        });

        // Show errors if any
        if (errors.length > 0) {
            this.emit('error', {
                message: 'Some files could not be uploaded:',
                details: errors
            });
        }

        // Process valid files
        if (validFiles.length > 0) {
            this.uploadFiles(validFiles);
        }
    }

    /**
     * Handle paste events
     */
    handlePaste(e) {
        const items = e.clipboardData?.items;
        if (!items) return;

        const files = [];
        const textContent = [];

        // Process clipboard items
        for (let i = 0; i < items.length; i++) {
            const item = items[i];

            if (item.kind === 'file') {
                const file = item.getAsFile();
                if (file) {
                    files.push(file);
                }
            } else if (item.kind === 'string' && item.type === 'text/plain') {
                item.getAsString(text => {
                    if (text.trim()) {
                        textContent.push(text);
                    }
                });
            }
        }

        // Handle pasted files
        if (files.length > 0) {
            e.preventDefault();
            this.handleFiles(files);
        }

        // Handle pasted text (let it proceed normally for text input)
        if (textContent.length > 0 && files.length === 0) {
            // Let the default paste behavior handle text
            return;
        }
    }

    /**
     * Validate a file before upload
     */
    validateFile(file) {
        // Check file size
        if (file.size > this.maxFileSize) {
            return {
                valid: false,
                error: `File too large (${this.formatFileSize(file.size)}). Maximum size is ${this.formatFileSize(this.maxFileSize)}.`
            };
        }

        // Check if file type is supported (allow all types for now)
        // if (!this.supportedTypes[file.type] && !file.type.startsWith('text/')) {
        //     return {
        //         valid: false,
        //         error: `File type not supported (${file.type})`
        //     };
        // }

        return { valid: true };
    }

    /**
     * Upload files to server
     */
    async uploadFiles(files) {
        const uploadProgress = document.getElementById('uploadProgress');
        const progressFill = document.getElementById('progressFill');
        const progressText = document.getElementById('progressText');

        // Show progress indicator
        if (uploadProgress) uploadProgress.style.display = 'block';
        if (progressFill) progressFill.style.width = '0%';
        if (progressText) progressText.textContent = 'Preparing upload...';

        try {
            for (let i = 0; i < files.length; i++) {
                const file = files[i];

                if (progressText) {
                    progressText.textContent = `Uploading ${file.name}... (${i + 1}/${files.length})`;
                }

                await this.uploadSingleFile(file, (percent) => {
                    // Update progress for current file
                    const overallProgress = ((i + percent / 100) / files.length) * 100;
                    if (progressFill) progressFill.style.width = `${overallProgress}%`;
                });
            }

            // Upload complete
            if (progressText) progressText.textContent = 'Upload complete!';
            if (progressFill) progressFill.style.width = '100%';

            setTimeout(() => {
                if (uploadProgress) uploadProgress.style.display = 'none';
            }, 2000);

            this.emit('uploadComplete', { files });

        } catch (error) {
            console.error('Upload failed:', error);
            if (progressText) progressText.textContent = `Upload failed: ${error.message}`;
            if (progressFill) progressFill.style.width = '0%';

            setTimeout(() => {
                if (uploadProgress) uploadProgress.style.display = 'none';
            }, 3000);

            this.emit('error', {
                message: 'Upload failed',
                details: [error.message]
            });
        }
    }

    /**
     * Upload a single file with progress tracking
     */
    async uploadSingleFile(file, onProgress) {
        return new Promise((resolve, reject) => {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('title', file.name);

            const xhr = new XMLHttpRequest();

            // Track upload progress
            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable && onProgress) {
                    const percent = (e.loaded / e.total) * 100;
                    onProgress(percent);
                }
            });

            xhr.addEventListener('load', () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    try {
                        const response = JSON.parse(xhr.responseText);
                        resolve(response);
                    } catch (e) {
                        resolve({ success: true });
                    }
                } else {
                    let errorMessage = `Upload failed: ${xhr.statusText}`;
                    try {
                        const errorData = JSON.parse(xhr.responseText);
                        errorMessage = errorData.detail || errorData.message || errorMessage;
                    } catch (e) { }
                    reject(new Error(errorMessage));
                }
            });

            xhr.addEventListener('error', () => {
                reject(new Error('Network error during upload'));
            });

            xhr.addEventListener('abort', () => {
                reject(new Error('Upload cancelled'));
            });

            xhr.open('POST', '/api/documents/upload');
            xhr.send(formData);
        });
    }

    /**
     * Format file size for display
     */
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';

        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));

        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    /**
     * Get file type display name
     */
    getFileTypeDisplay(file) {
        return this.supportedTypes[file.type] || file.type || 'Unknown';
    }

    /**
     * Create file preview element
     */
    createFilePreview(file) {
        const fileDiv = document.createElement('div');
        fileDiv.className = 'message-file';

        const fileIcon = document.createElement('div');
        fileIcon.className = 'file-icon';
        fileIcon.textContent = this.getFileTypeDisplay(file).substring(0, 3);

        const fileInfo = document.createElement('div');
        fileInfo.className = 'file-info';

        const fileName = document.createElement('div');
        fileName.className = 'file-name';
        fileName.textContent = file.name;

        const fileSize = document.createElement('div');
        fileSize.className = 'file-size';
        fileSize.textContent = this.formatFileSize(file.size);

        fileInfo.appendChild(fileName);
        fileInfo.appendChild(fileSize);
        fileDiv.appendChild(fileIcon);
        fileDiv.appendChild(fileInfo);

        return fileDiv;
    }

    /**
     * Add event handler
     */
    on(event, handler) {
        if (!this.eventHandlers.has(event)) {
            this.eventHandlers.set(event, []);
        }
        this.eventHandlers.get(event).push(handler);
    }

    /**
     * Remove event handler
     */
    off(event, handler) {
        if (this.eventHandlers.has(event)) {
            const handlers = this.eventHandlers.get(event);
            const index = handlers.indexOf(handler);
            if (index > -1) {
                handlers.splice(index, 1);
            }
        }
    }

    /**
     * Emit event to handlers
     */
    emit(event, data) {
        if (this.eventHandlers.has(event)) {
            this.eventHandlers.get(event).forEach(handler => {
                try {
                    handler(data);
                } catch (error) {
                    console.error(`Error in file handler event ${event}:`, error);
                }
            });
        }
    }
}

// Export for use in other modules
window.FileHandler = FileHandler;