## Purpose

This feature unifies the document upload experience by allowing users to upload PDF documents directly within the chat interface. When a user drags and drops a PDF into the chat prompt field or uses the upload button, the system automatically catalogs the document, processes it through the existing pipeline (PDF extraction → chunking → embedding → knowledge graph extraction), and provides real-time processing status feedback in the chat UI. Additionally, the RAG retrieval system is enhanced to prioritize local Librarian documents over any external sources.


### Key Terms
- **Chat_Upload_Handler**: The frontend component that intercepts file uploads in the chat interface and triggers document processing
- **Document_Processing_Pipeline**: The existing backend workflow that processes PDFs through extraction, chunking, embedding, and knowledge graph extraction
- **Processing_Status_Service**: The WebSocket-based service that sends real-time processing status updates to the chat UI
- **RAG_Service**: The Retrieval-Augmented Generation service that searches documents and generates AI responses
- **Source_Prioritization_Engine**: The component that ranks and prioritizes search results based on source type (Librarian documents first, web search second, LLM fallback third)
- **Librarian_Documents**: Documents that have been uploaded and processed by the Multimodal Librarian system
- **Web_Search_Results**: Optional external search results from web search integration
- **LLM_Fallback**: AI-generated responses when no relevant documents are found

## Requirements

### Requirement: Unified Chat Upload Interface

The system SHALL support: As a user, I want to upload PDF documents directly in the chat interface, so that I can seamlessly add documents to my knowledge base without switching to a separate panel.

#### Scenario: WHEN a user drags and drops a PDF file onto the chat message

- **THEN** WHEN a user drags and drops a PDF file onto the chat message input area, THE Chat_Upload_Handler SHALL accept the file and initiate document processing

#### Scenario: WHEN a user clicks the upload button in the chat interface a

- **THEN** WHEN a user clicks the upload button in the chat interface and selects a PDF file, THE Chat_Upload_Handler SHALL accept the file and initiate document processing

#### Scenario: WHEN a user pastes a PDF file into the chat input area, THE

- **THEN** WHEN a user pastes a PDF file into the chat input area, THE Chat_Upload_Handler SHALL accept the file and initiate document processing

#### Scenario: WHEN a non-PDF file is dropped or selected, THE Chat_Upload_

- **THEN** WHEN a non-PDF file is dropped or selected, THE Chat_Upload_Handler SHALL display an error message indicating only PDF files are supported for document cataloging

#### Scenario: WHEN a file exceeds the 100MB size limit, THE Chat_Upload_Ha

- **THEN** WHEN a file exceeds the 100MB size limit, THE Chat_Upload_Handler SHALL display an error message with the file size limit

#### Scenario: WHEN multiple PDF files are uploaded simultaneously, THE Cha

- **THEN** WHEN multiple PDF files are uploaded simultaneously, THE Chat_Upload_Handler SHALL queue them for sequential processing and display status for each

### Requirement: Automatic Document Cataloging

The system SHALL support: As a user, I want uploaded documents to be automatically cataloged and processed, so that I can immediately start asking questions about them.

#### Scenario: WHEN a PDF is uploaded via the chat interface, THE Document_

- **THEN** WHEN a PDF is uploaded via the chat interface, THE Document_Processing_Pipeline SHALL automatically extract text, images, and metadata from the PDF

#### Scenario: WHEN PDF extraction completes, THE Document_Processing_Pipel

- **THEN** WHEN PDF extraction completes, THE Document_Processing_Pipeline SHALL chunk the content using the adaptive chunking framework

#### Scenario: WHEN chunking completes, THE Document_Processing_Pipeline SH

- **THEN** WHEN chunking completes, THE Document_Processing_Pipeline SHALL generate embeddings and store them in the vector database

#### Scenario: WHEN embedding storage completes, THE Document_Processing_Pi

- **THEN** WHEN embedding storage completes, THE Document_Processing_Pipeline SHALL extract concepts and relationships for the knowledge graph

#### Scenario: WHEN a duplicate document is detected, THE Document_Processi

- **THEN** WHEN a duplicate document is detected, THE Document_Processing_Pipeline SHALL notify the user and offer to skip or force re-upload

#### Scenario: IF document processing fails at any stage, THEN THE Document

- **GIVEN** document processing fails at any stage
- **THEN** IF document processing fails at any stage, THEN THE Document_Processing_Pipeline SHALL log the error, notify the user, and offer retry options

### Requirement: Real-Time Processing Status Feedback

The system SHALL support: As a user, I want to see the processing status of my uploaded documents in the chat, so that I know when they are ready for querying.

#### Scenario: WHEN document processing begins, THE Processing_Status_Servi

- **THEN** WHEN document processing begins, THE Processing_Status_Service SHALL send a WebSocket message with status "processing_started" and document metadata

#### Scenario: WHILE document processing is in progress, THE Processing_Sta

- **THEN** WHILE document processing is in progress, THE Processing_Status_Service SHALL send periodic progress updates with percentage completion and current stage

#### Scenario: WHEN document processing completes successfully, THE Process

- **THEN** WHEN document processing completes successfully, THE Processing_Status_Service SHALL send a "processing_complete" message with document summary

#### Scenario: IF document processing fails, THEN THE Processing_Status_Ser

- **GIVEN** document processing fails
- **THEN** IF document processing fails, THEN THE Processing_Status_Service SHALL send a "processing_failed" message with error details and retry option

#### Scenario: WHEN a progress update is received, THE Chat_UI SHALL displa

- **THEN** WHEN a progress update is received, THE Chat_UI SHALL display a progress indicator showing the current stage and percentage

#### Scenario: WHEN processing completes, THE Chat_UI SHALL display a succe

- **THEN** WHEN processing completes, THE Chat_UI SHALL display a success message with document title and chunk count

### Requirement: Chat UI Processing Indicator

The system SHALL support: As a user, I want visual feedback in the chat showing document processing progress, so that I can track the status without leaving the conversation.

#### Scenario: WHEN document upload begins, THE Chat_UI SHALL display an up

- **THEN** WHEN document upload begins, THE Chat_UI SHALL display an upload progress bar in the chat message area

#### Scenario: WHEN document processing begins, THE Chat_UI SHALL display a

- **THEN** WHEN document processing begins, THE Chat_UI SHALL display a processing status card showing document name and current stage

#### Scenario: WHILE processing is in progress, THE Chat_UI SHALL update th

- **THEN** WHILE processing is in progress, THE Chat_UI SHALL update the progress indicator with stage name and percentage

#### Scenario: WHEN processing completes, THE Chat_UI SHALL replace the pro

- **THEN** WHEN processing completes, THE Chat_UI SHALL replace the progress indicator with a success message containing document summary

#### Scenario: IF processing fails, THEN THE Chat_UI SHALL display an error

- **GIVEN** processing fails
- **THEN** IF processing fails, THEN THE Chat_UI SHALL display an error message with a retry button

#### Scenario: WHEN the user hovers over a processing status card, THE Chat

- **THEN** WHEN the user hovers over a processing status card, THE Chat_UI SHALL show detailed stage information

### Requirement: Source Prioritization in RAG Retrieval

The system SHALL support: As a user, I want my uploaded Librarian documents to be prioritized over external sources, so that I get answers from my curated knowledge base first.

#### Scenario: WHEN performing a search query, THE Source_Prioritization_En

- **THEN** WHEN performing a search query, THE Source_Prioritization_Engine SHALL search Librarian_Documents first

#### Scenario: WHEN Librarian_Documents return relevant results above the c

- **THEN** WHEN Librarian_Documents return relevant results above the confidence threshold, THE RAG_Service SHALL use those results without querying external sources

#### Scenario: WHEN Librarian_Documents return insufficient results, THE So

- **THEN** WHEN Librarian_Documents return insufficient results, THE Source_Prioritization_Engine SHALL optionally query Web_Search_Results as a secondary source

#### Scenario: WHEN both Librarian_Documents and Web_Search_Results return

- **THEN** WHEN both Librarian_Documents and Web_Search_Results return insufficient results, THE RAG_Service SHALL fall back to LLM_Fallback

#### Scenario: WHEN displaying search results, THE RAG_Service SHALL clearl

- **THEN** WHEN displaying search results, THE RAG_Service SHALL clearly indicate the source type for each citation (Librarian, Web, or LLM)

#### Scenario: THE Source_Prioritization_Engine SHALL apply a boost factor

- **THEN** THE Source_Prioritization_Engine SHALL apply a boost factor to Librarian_Documents scores to ensure they rank higher than equivalent external results

### Requirement: WebSocket Message Protocol for Processing Status

The system SHALL support: As a developer, I want a well-defined WebSocket message protocol for processing status updates, so that the frontend can reliably display progress.

#### Scenario: THE Processing_Status_Service SHALL send messages with type

- **THEN** THE Processing_Status_Service SHALL send messages with type "document_processing_status" containing document_id, status, progress_percentage, and current_stage fields

#### Scenario: THE Processing_Status_Service SHALL define status values as:

- **THEN** THE Processing_Status_Service SHALL define status values as: "queued", "extracting", "chunking", "embedding", "kg_extraction", "completed", "failed"

#### Scenario: WHEN sending progress updates, THE Processing_Status_Service

- **THEN** WHEN sending progress updates, THE Processing_Status_Service SHALL include estimated_time_remaining when calculable

#### Scenario: THE Processing_Status_Service SHALL send messages only to th

- **THEN** THE Processing_Status_Service SHALL send messages only to the connection that initiated the upload

#### Scenario: IF the WebSocket connection is lost during processing, THEN

- **GIVEN** the WebSocket connection is lost during processing
- **THEN** IF the WebSocket connection is lost during processing, THEN THE Processing_Status_Service SHALL queue status updates and deliver them upon reconnection

### Requirement: Removal of Separate Document Library Panel

The system SHALL support: As a user, I want a streamlined interface where document upload is integrated into chat, so that I don't have to navigate between separate panels.

#### Scenario: WHEN the chat interface loads, THE Chat_UI SHALL NOT display

- **THEN** WHEN the chat interface loads, THE Chat_UI SHALL NOT display a separate "Documents" button in the header

#### Scenario: WHEN a document is uploaded via chat, THE Document_Processin

- **THEN** WHEN a document is uploaded via chat, THE Document_Processing_Pipeline SHALL store it using the existing document storage infrastructure

#### Scenario: THE Chat_UI SHALL provide document management capabilities (

- **THEN** THE Chat_UI SHALL provide document management capabilities (view uploaded documents, delete, retry failed) through chat commands or a minimal dropdown menu

#### Scenario: WHEN a user types a document management command (e.g., "/doc

- **THEN** WHEN a user types a document management command (e.g., "/documents", "/list"), THE Chat_UI SHALL display a list of uploaded documents with their status

### Requirement: Document Management in Chat

The system SHALL support: As a user, I want to manage my uploaded documents from within the chat interface, so that I can view, delete, or retry processing without leaving the conversation.

#### Scenario: WHEN a user clicks the upload button, THE Chat_UI SHALL disp

- **THEN** WHEN a user clicks the upload button, THE Chat_UI SHALL display a dropdown with options: "Upload PDF" and "View Documents"

#### Scenario: WHEN "View Documents" is selected, THE Chat_UI SHALL display

- **THEN** WHEN "View Documents" is selected, THE Chat_UI SHALL display a compact document list panel showing document name, status, and actions

#### Scenario: WHEN a user clicks delete on a document in the list, THE sys

- **THEN** WHEN a user clicks delete on a document in the list, THE system SHALL remove the document from storage and the knowledge base

#### Scenario: WHEN a user clicks retry on a failed document, THE Document_

- **THEN** WHEN a user clicks retry on a failed document, THE Document_Processing_Pipeline SHALL restart processing from the failed stage

#### Scenario: THE document list panel SHALL be dismissible by clicking out

- **THEN** THE document list panel SHALL be dismissible by clicking outside or pressing Escape
