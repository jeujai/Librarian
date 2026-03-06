# Requirements Document

## Introduction

This feature enhances the PDF upload experience in the Multimodal Librarian web UI by adding client-side duplicate detection, multi-file drag-and-drop with automatic filtering of already-uploaded files, and a visible list of uploaded documents near the upload controls. The goal is to prevent wasted uploads and give users clear visibility into what's already in the system before they attempt to upload.

## Glossary

- **Upload_UI**: The client-side JavaScript interface for uploading PDF documents, implemented in `chat.js`, `filehandler.js`, `chat-upload-handler.js`, and `unified_interface.js`
- **Document_List_API**: The `GET /api/documents/` endpoint that returns paginated document metadata including filenames, statuses, and IDs
- **Upload_API**: The `POST /api/documents/upload` endpoint that accepts multipart form data for PDF uploads
- **Duplicate_Indicator**: A visual UI element (badge, icon, or label) shown on a file entry to indicate that a file with the same filename already exists on the server
- **Drop_Zone**: A designated drag-and-drop area in the upload UI that accepts multiple files simultaneously
- **Uploaded_Files_Panel**: A UI panel displayed near the upload controls that shows the list of filenames already present on the server
- **File_Queue**: The list of files selected or dropped by the user, displayed before upload begins, allowing review and removal of individual entries

## Requirements

### Requirement 1: Fetch Uploaded Document Names on Upload Initiation

**User Story:** As a user, I want the upload UI to know which documents are already uploaded, so that I can be warned before uploading duplicates.

#### Acceptance Criteria

1. WHEN the user opens the upload interface, THE Upload_UI SHALL fetch the current document list from the Document_List_API
2. THE Upload_UI SHALL extract and cache the filenames from the Document_List_API response for use in duplicate comparison
3. IF the Document_List_API request fails, THEN THE Upload_UI SHALL allow uploads to proceed without duplicate checking and log the error to the browser console

### Requirement 2: Client-Side Duplicate Pre-Check on File Selection

**User Story:** As a user, I want to see a warning when I select a file that's already been uploaded, so that I can avoid uploading it again.

#### Acceptance Criteria

1. WHEN the user selects one or more files via the file picker, THE Upload_UI SHALL compare each selected filename against the cached list of uploaded filenames
2. WHEN a selected file matches an already-uploaded filename, THE Upload_UI SHALL display a Duplicate_Indicator on that file entry in the File_Queue
3. WHEN a selected file matches an already-uploaded filename, THE Upload_UI SHALL display a warning message that includes the matching filename
4. WHEN all selected files match already-uploaded filenames, THE Upload_UI SHALL disable the upload action and display a message indicating all files are duplicates
5. THE Upload_UI SHALL perform filename comparison in a case-insensitive manner

### Requirement 3: Multi-File Drag-and-Drop with Auto-Filtering

**User Story:** As a user, I want to drag and drop multiple PDF files and have already-uploaded ones automatically flagged, so that I can quickly upload only new files.

#### Acceptance Criteria

1. THE Drop_Zone SHALL accept multiple files dropped simultaneously
2. WHEN files are dropped onto the Drop_Zone, THE Upload_UI SHALL validate that each file is a PDF and is within the 100MB size limit
3. WHEN files are dropped onto the Drop_Zone, THE Upload_UI SHALL compare each dropped filename against the cached list of uploaded filenames
4. WHEN dropped files include duplicates, THE Upload_UI SHALL display the File_Queue with duplicate files visually marked using a Duplicate_Indicator
5. WHEN dropped files include duplicates, THE Upload_UI SHALL display a summary message stating the count of new files and the count of duplicate files
6. THE Upload_UI SHALL allow the user to remove individual files from the File_Queue before uploading
7. THE Drop_Zone SHALL provide visual feedback when files are dragged over the area (highlight or border change)

### Requirement 4: File Queue Review Before Upload

**User Story:** As a user, I want to review the list of files I'm about to upload and remove any I don't want, so that I have full control over what gets uploaded.

#### Acceptance Criteria

1. WHEN files are selected or dropped, THE Upload_UI SHALL display a File_Queue showing each file with its name, size, and duplicate status
2. THE Upload_UI SHALL provide a remove button on each file entry in the File_Queue
3. WHEN the user removes a file from the File_Queue, THE Upload_UI SHALL update the File_Queue display and the upload summary immediately
4. WHEN the File_Queue contains zero files, THE Upload_UI SHALL disable the upload action
5. THE Upload_UI SHALL provide an "Upload All New" action that uploads only files not marked as duplicates
6. THE Upload_UI SHALL provide a "Force Upload All" action that uploads all files in the File_Queue including duplicates (using the force_upload parameter)

### Requirement 5: Uploaded Files Panel Display

**User Story:** As a user, I want to see which files are already uploaded near the upload button, so that I know what's in the system without navigating elsewhere.

#### Acceptance Criteria

1. THE Uploaded_Files_Panel SHALL be displayed near the upload controls in the chat interface
2. WHEN the upload interface is opened, THE Uploaded_Files_Panel SHALL show the filenames of documents retrieved from the Document_List_API
3. THE Uploaded_Files_Panel SHALL display each filename with its processing status (completed, processing, failed)
4. WHEN the document list contains more than 10 entries, THE Uploaded_Files_Panel SHALL show the first 10 entries with a count of remaining documents
5. WHEN a new document is successfully uploaded, THE Uploaded_Files_Panel SHALL refresh to include the newly uploaded document
6. IF the Document_List_API returns zero documents, THEN THE Uploaded_Files_Panel SHALL display a message indicating no documents are uploaded

### Requirement 6: Upload Flow Integration

**User Story:** As a user, I want the duplicate filtering to work seamlessly with the existing upload mechanisms, so that my workflow is not disrupted.

#### Acceptance Criteria

1. THE Upload_UI SHALL integrate duplicate checking with both the file picker upload path and the drag-and-drop upload path
2. WHEN a file is uploaded successfully, THE Upload_UI SHALL update the cached filename list to include the newly uploaded filename
3. WHEN a file upload receives a 409 Conflict response from the Upload_API, THE Upload_UI SHALL display the server-provided duplicate information including the existing document title
4. THE Upload_UI SHALL support the existing WebSocket-based upload path in ChatUploadHandler with the same duplicate pre-check behavior
5. WHILE an upload is in progress, THE Upload_UI SHALL prevent additional uploads from being initiated
