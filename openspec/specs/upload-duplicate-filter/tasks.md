# Implementation Plan: Upload Duplicate Filter

## Overview

Add client-side duplicate detection and multi-file management to the upload UI. Three new JavaScript components (`DuplicateChecker`, `FileQueuePanel`, `UploadedFilesPanel`) are composed into the existing `ChatUploadHandler`. All changes are client-side vanilla JavaScript and CSS — no backend modifications.

## Tasks

- [x] 1. Create DuplicateChecker component
  - [x] 1.1 Create `src/multimodal_librarian/static/js/duplicate-checker.js` with the `DuplicateChecker` class
    - Implement `constructor()` initializing `cachedFilenames` (Set), `documents` (Array), `loaded`, `loading` flags
    - Implement `async fetchUploadedFilenames()` that calls `GET /api/documents/?page_size=100`, populates the Set with lowercase filenames, stores full document objects, sets `loaded = true`
    - On fetch failure: log error to console, set `loaded = false`, allow uploads to proceed without duplicate checking
    - Implement `isDuplicate(filename)` returning `true` if lowercase filename is in the Set
    - Implement `checkFiles(files)` returning array of `{file, isDuplicate}` objects
    - Implement `addUploadedDocument(filename, document)` to add a filename to the cache and document to the list
    - Implement `getDocuments()` returning cached document objects
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.5, 6.2_

  - [ ]* 1.2 Write property tests for DuplicateChecker
    - **Property 1: Cache population from API response** — for any document list, after fetch, cached set contains all lowercase filenames
    - **Property 2: Case-insensitive duplicate detection** — isDuplicate returns same result for any case variation of a filename
    - **Property 10: Cache update round-trip after upload** — after addUploadedDocument, isDuplicate returns true for that filename
    - **Validates: Requirements 1.1, 1.2, 2.1, 2.5, 3.3, 6.2**

  - [ ]* 1.3 Write unit tests for DuplicateChecker error handling
    - Test fetch failure graceful degradation (isDuplicate returns false for all files when fetch fails)
    - Test empty document list (cache is empty, no duplicates flagged)
    - _Requirements: 1.3_

- [x] 2. Create FileQueuePanel component
  - [x] 2.1 Create `src/multimodal_librarian/static/js/file-queue-panel.js` with the `FileQueuePanel` class
    - Implement `constructor(containerElement)` storing container ref, entries array, and callback slots (`onUploadNew`, `onForceUploadAll`, `onRemoveFile`)
    - Implement `show(fileEntries)` that accepts `[{file, isDuplicate}]`, assigns unique IDs, and calls `_render()`
    - Implement `removeEntry(entryId)` that removes entry by ID and re-renders
    - Implement `hide()` that clears entries and hides the container
    - Implement `getNewFileCount()` and `getDuplicateCount()` returning respective counts
    - Implement `_render()` that builds HTML: file rows with name, formatted size, duplicate indicator (amber badge) if duplicate, remove button per entry, summary line ("N new, M duplicates"), "Upload All New" button (disabled when all duplicates), "Force Upload All" button
    - Wire remove buttons to `removeEntry()`, upload buttons to callbacks
    - When queue becomes empty after removals, disable both upload buttons
    - _Requirements: 2.2, 2.3, 2.4, 3.4, 3.5, 3.6, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [ ]* 2.2 Write property tests for FileQueuePanel
    - **Property 3: File queue entry rendering completeness** — each entry renders filename, size, duplicate indicator iff duplicate, and remove button
    - **Property 4: Queue summary counts and upload button state** — summary shows correct new/duplicate counts; Upload All New disabled iff all duplicates
    - **Property 5: File removal preserves queue integrity** — removing entry yields queue of length N-1 without the removed file
    - **Property 6: Upload All New filters out duplicates** — upload list contains exactly non-duplicate files in original order
    - **Property 7: Force Upload All includes all files** — upload list contains all files regardless of duplicate status
    - **Validates: Requirements 2.2, 2.3, 2.4, 3.4, 3.5, 3.6, 4.1, 4.2, 4.3, 4.5, 4.6**

- [x] 3. Create UploadedFilesPanel component
  - [x] 3.1 Create `src/multimodal_librarian/static/js/uploaded-files-panel.js` with the `UploadedFilesPanel` class
    - Implement `constructor(containerElement)` storing container ref, documents array, `maxVisible = 10`
    - Implement `updateDocuments(documents)` that replaces the document list and calls `_render()`
    - Implement `addDocument(document)` that prepends a document and re-renders
    - Implement `_render()` that builds HTML: show first 10 filenames with status badges (completed/processing/failed), show "+N more" count if >10 documents, show "No documents uploaded yet" if empty
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.6_

  - [ ]* 3.2 Write property tests for UploadedFilesPanel
    - **Property 8: Uploaded files panel rendering** — each rendered entry contains filename and matching status indicator
    - **Property 9: Panel truncation at threshold** — for N > 10 documents, exactly 10 entries rendered with remaining count of N-10
    - **Validates: Requirements 5.2, 5.3, 5.4**

- [x] 4. Checkpoint - Ensure all component tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Add CSS styles for new components
  - [x] 5.1 Add styles to `src/multimodal_librarian/static/css/chat.css`
    - Add `.file-queue-panel` container styles
    - Add `.file-queue-entry` row styles with `.file-queue-entry.duplicate` amber/warning variant
    - Add `.duplicate-indicator` badge styles
    - Add `.file-queue-actions` button container styles
    - Add `.uploaded-files-panel` container styles
    - Add `.uploaded-file-entry` row styles
    - Add `.status-badge` styles with variants for completed, processing, failed
    - Add `.drop-zone-active` drag-over highlight styles
    - _Requirements: 2.2, 3.4, 3.7, 5.1, 5.3_

- [x] 6. Integrate components into ChatUploadHandler
  - [x] 6.1 Modify `src/multimodal_librarian/static/js/chat-upload-handler.js` to compose the new components
    - Import/reference `DuplicateChecker`, `FileQueuePanel`, `UploadedFilesPanel`
    - In constructor: instantiate `DuplicateChecker`, create container elements for `FileQueuePanel` and `UploadedFilesPanel`, instantiate both panels
    - Add `isUploading` lock flag to prevent concurrent uploads
    - _Requirements: 6.1, 6.5_

  - [x] 6.2 Modify `handleChatUpload(files)` to use duplicate checking and file queue
    - After file validation, call `duplicateChecker.fetchUploadedFilenames()` if not yet loaded
    - Call `duplicateChecker.checkFiles(validFiles)` to annotate files
    - Show `FileQueuePanel` with annotated entries instead of immediately uploading
    - Wire `onUploadNew` callback to upload only non-duplicate files
    - Wire `onForceUploadAll` callback to upload all files with `force_upload=true`
    - Wire `onRemoveFile` callback to `FileQueuePanel.removeEntry()`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.3, 3.4, 3.5, 3.6, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 6.1_

  - [x] 6.3 Implement `uploadFiles(files, forceUpload)` method
    - Set `isUploading = true` at start, `false` on completion/failure
    - Reject if `isUploading` is already true
    - For each file, call existing `uploadFileViaWebSocket(file)` or REST upload with `force_upload` parameter
    - On success: call `duplicateChecker.addUploadedDocument()` and refresh `UploadedFilesPanel`
    - On 409 Conflict: display server-provided duplicate info with existing document title
    - On other errors: show error, continue with remaining files
    - Hide `FileQueuePanel` after all uploads complete
    - _Requirements: 6.2, 6.3, 6.4, 6.5_

  - [ ]* 6.4 Write property test for upload lock
    - **Property 11: Upload lock prevents concurrent uploads** — when isUploading is true, new upload attempts are rejected
    - **Validates: Requirements 6.5**

  - [ ]* 6.5 Write property test for file validation
    - **Property 12: File validation rejects invalid files** — validateChatFile returns valid only for PDF files ≤100MB with size > 0
    - **Validates: Requirements 3.2**

- [x] 7. Wire UploadedFilesPanel into the upload UI
  - [x] 7.1 Add the UploadedFilesPanel container element to the chat HTML template
    - Add a container div near the upload controls in the appropriate template file (e.g., `src/multimodal_librarian/templates/` or inline in `chat.js`)
    - Trigger `duplicateChecker.fetchUploadedFilenames()` when the upload dropdown/interface is opened
    - Pass fetched documents to `uploadedFilesPanel.updateDocuments()`
    - After successful upload, call `uploadedFilesPanel.addDocument()` with the new document metadata
    - _Requirements: 5.1, 5.2, 5.5_

  - [ ]* 7.2 Write unit tests for upload integration
    - Test 409 Conflict response handling displays server duplicate info
    - Test successful upload updates both DuplicateChecker cache and UploadedFilesPanel
    - Test WebSocket upload path integrates with duplicate pre-check
    - _Requirements: 6.2, 6.3, 6.4_

- [x] 8. Add script tags and finalize wiring
  - [x] 8.1 Add `<script>` tags for the three new JS files in the HTML template
    - Add script references for `duplicate-checker.js`, `file-queue-panel.js`, `uploaded-files-panel.js` in the correct load order (before `chat-upload-handler.js`)
    - Verify all components initialize correctly on page load
    - _Requirements: 6.1_

- [x] 9. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests use fast-check library and validate correctness properties from the design document
- All changes are client-side JavaScript and CSS — no backend modifications needed
- The existing `force_upload` parameter on the upload API is already supported
