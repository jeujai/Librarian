/**
 * DuplicateChecker - Client-side duplicate filename detection for uploads.
 *
 * Fetches the current document list from the server, caches filenames,
 * and provides fast case-insensitive duplicate lookups. Degrades gracefully
 * when the API is unreachable.
 */
class DuplicateChecker {
    constructor() {
        /** @type {Set<string>} Lowercase filenames of uploaded documents */
        this.cachedFilenames = new Set();
        /** @type {Object[]} Full document objects from the API */
        this.documents = [];
        /** @type {boolean} Whether the document list has been successfully loaded */
        this.loaded = false;
        /** @type {boolean} Whether a fetch is currently in progress */
        this.loading = false;
    }

    /**
     * Fetch the document list from the server and populate the cache.
     * On failure, logs the error and allows uploads without duplicate checking.
     * @returns {Promise<void>}
     */
    async fetchUploadedFilenames() {
        if (this.loading) {
            return;
        }
        this.loading = true;

        try {
            const response = await fetch('/api/documents/?page_size=100');
            if (!response.ok) {
                throw new Error(`API returned status ${response.status}`);
            }

            const data = await response.json();
            const documents = data.documents || [];

            this.cachedFilenames.clear();
            this.documents = [];

            for (const doc of documents) {
                if (doc.filename) {
                    this.cachedFilenames.add(doc.filename.toLowerCase());
                }
                this.documents.push(doc);
            }

            this.loaded = true;
        } catch (error) {
            console.error('Failed to fetch uploaded filenames:', error);
            this.loaded = false;
        } finally {
            this.loading = false;
        }
    }

    /**
     * Check if a filename already exists on the server (case-insensitive).
     * Returns false when the cache hasn't been loaded, allowing uploads to proceed.
     * @param {string} filename
     * @returns {boolean}
     */
    isDuplicate(filename) {
        if (!this.loaded) {
            return false;
        }
        return this.cachedFilenames.has(filename.toLowerCase());
    }

    /**
     * Check multiple files against the cache and return annotated results.
     * @param {File[]} files
     * @returns {{file: File, isDuplicate: boolean}[]}
     */
    checkFiles(files) {
        const results = [];
        for (const file of files) {
            results.push({
                file: file,
                isDuplicate: this.isDuplicate(file.name)
            });
        }
        return results;
    }

    /**
     * Add a filename to the cache after a successful upload.
     * @param {string} filename
     * @param {Object} document - Document metadata from the server response
     */
    addUploadedDocument(filename, document) {
        if (filename) {
            this.cachedFilenames.add(filename.toLowerCase());
        }
        if (document) {
            this.documents.push(document);
        }
    }

    /**
     * Get the cached document objects (for the UploadedFilesPanel).
     * @returns {Object[]}
     */
    getDocuments() {
        return this.documents;
    }
}
