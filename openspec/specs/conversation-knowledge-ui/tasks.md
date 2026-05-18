# Implementation Plan: Conversation Knowledge UI

## Overview

Incremental implementation starting with backend API additions, then frontend toast and chat lifecycle, document list integration, and finally the KG Explorer. Backend tasks come first where the frontend depends on them. Property-based tests use Hypothesis (Python) and fast-check (JavaScript).

## Tasks

- [x] 1. Backend: Conversation history and title endpoints
  - [x] 1.1 Create `api/routers/conversations.py` with `GET /{thread_id}/history` and `PATCH /{thread_id}/title` endpoints
    - Define `ConversationHistoryResponse`, `ConversationMessageResponse`, `TitleUpdateRequest`, `TitleUpdateResponse` Pydantic models
    - `GET /history` loads messages from ConversationManager and returns them as a list
    - `PATCH /title` validates non-empty title (1–200 chars), persists via ConversationManager, returns updated title
    - Use `Depends(get_conversation_manager)` per DI conventions
    - Register router in `main.py`
    - _Requirements: 6.1, 9.2, 9.4_

  - [ ]* 1.2 Write property test for title edit round-trip (Property 9)
    - **Property 9: Title edit round-trip persistence**
    - **Validates: Requirements 9.2, 9.4**
    - Use Hypothesis to generate random valid titles (non-empty strings ≤200 chars). PATCH then GET, assert equality.
    - Generate empty/whitespace titles, assert rejection (400).

  - [ ]* 1.3 Write unit tests for conversation history and title endpoints
    - Test 404 when thread not found
    - Test successful history load with multiple messages
    - Test title update with valid and invalid inputs
    - _Requirements: 6.1, 9.2, 9.4_

- [x] 2. Backend: Modify convert endpoint to accept title parameter
  - [x] 2.1 Add optional `title` field to `ConvertToKnowledgeRequest` in `api/routers/conversation_knowledge.py`
    - Pass title through to `ConversationKnowledgeService.convert_conversation()`
    - Ensure idempotent update: re-converting the same thread_id updates the existing document in place
    - _Requirements: 3.1, 4.1, 4.2, 4.3_

  - [ ]* 2.2 Write property test for stable document identity (Property 4)
    - **Property 4: Stable document identity across re-conversions**
    - **Validates: Requirements 4.1, 4.2, 4.3**
    - Use Hypothesis to generate random thread_ids, convert N times (N=1..5). Assert document_id is constant across all conversions.

- [x] 3. Backend: KG query engine additions
  - [x] 3.1 Add `get_neighborhood()` method to `KGQueryEngine` in `components/knowledge_graph/kg_query_engine.py`
    - If `focus_concept` is None, return top 10 concepts by degree for the given source_id (landing view)
    - If `focus_concept` is provided, return ego graph (nodes + edges) around focus concept, capped at `max_nodes`
    - Include cross-source nodes connected by relationships
    - Return `GraphNode` and `GraphEdge` compatible dicts
    - _Requirements: 11.2, 11.4, 14.1, 15.1, 15.3_

  - [x] 3.2 Add `search_concepts_by_embedding()` method to `KGQueryEngine`
    - Accept query embedding vector, optional source_id filter, limit (default 10)
    - Compare against concept name embeddings in Neo4j
    - Return ranked list of matches with name, source_document, similarity_score, degree
    - _Requirements: 13.2, 15.2, 15.4, 15.5_

  - [ ]* 3.3 Write property test for landing view ordering (Property 11)
    - **Property 11: Landing view returns at most 10 concepts ordered by degree**
    - **Validates: Requirements 11.2**
    - Use Hypothesis to generate random concept sets with varying degrees. Assert top 10 by degree, descending order.

  - [ ]* 3.4 Write property test for max node cap (Property 12)
    - **Property 12: Neighborhood response respects max node cap**
    - **Validates: Requirements 11.4, 15.1**
    - Use Hypothesis to generate random graphs of varying sizes (1–200 nodes). Query with max_nodes=50. Assert response ≤ 50 nodes.

  - [ ]* 3.5 Write property test for search ranking (Property 15)
    - **Property 15: Search returns semantically ranked concepts**
    - **Validates: Requirements 13.2, 13.3, 15.4**
    - Use Hypothesis to generate random concept embeddings and query embeddings. Assert results ordered by descending similarity, count ≤ 10.

  - [ ]* 3.6 Write property test for search scope (Property 19)
    - **Property 19: Search API scope respects source_id parameter**
    - **Validates: Requirements 15.2, 15.5**
    - Generate random concepts across multiple sources. Search with and without source_id. Assert filtering correctness.

- [x] 4. Backend: KG API endpoints and DI wiring
  - [x] 4.1 Create `api/routers/knowledge_graph.py` with neighborhood and search endpoints
    - `GET /api/knowledge-graph/{source_id}/neighborhood` — accepts `focus_concept` (optional) and `max_nodes` (default 50, max 100)
    - `GET /api/knowledge-graph/search` — accepts `query` and optional `source_id`
    - Define `GraphNode`, `GraphEdge`, `NeighborhoodResponse`, `ConceptMatch`, `ConceptSearchResponse` Pydantic models
    - Use `Depends(get_kg_query_engine)` and `Depends(get_model_server_client)` per DI conventions
    - Graceful degradation: return 503 if graph_client is None
    - Register router in `main.py`
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5_

  - [x] 4.2 Add DI providers in `api/dependencies/services.py`
    - Add `get_kg_query_engine()` and `get_kg_query_engine_optional()` providers
    - Add `get_model_server_client()` provider for embedding queries
    - _Requirements: 15.1_

  - [ ]* 4.3 Write property test for neighborhood API response schema (Property 18)
    - **Property 18: Neighborhood API response schema**
    - **Validates: Requirements 15.1, 15.3**
    - Use Hypothesis to generate random neighborhood responses. Validate against Pydantic model. Assert all required fields present.

  - [ ]* 4.4 Write unit tests for KG API endpoints
    - Test neighborhood landing view (no focus_concept)
    - Test neighborhood with focus_concept
    - Test search with and without source_id
    - Test 503 when graph service unavailable
    - Test max_nodes capping
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5_

- [x] 5. Checkpoint — Backend complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Frontend: Toast notification system
  - [x] 6.1 Create `static/js/toast-notification.js` with `ToastNotification` class
    - `show({ id, message, type, autoDismissMs })` — creates toast DOM element in fixed-position container (top-right)
    - `update(id, { message, type, autoDismissMs })` — updates existing toast
    - `dismiss(id)` — removes toast
    - Types: `loading` (spinner), `success` (checkmark, auto-dismiss 5s), `error` (persist until dismissed)
    - Each toast has a close button for manual dismiss
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [x] 6.2 Add toast CSS styles to `static/css/chat.css`
    - `.toast-container` fixed top-right positioning
    - `.toast--loading`, `.toast--success`, `.toast--error` visual variants
    - Close button styling
    - Fade-in/fade-out transitions
    - _Requirements: 10.1, 10.2, 10.3_

  - [ ]* 6.3 Write property test for toast auto-dismiss timing (Property 10)
    - **Property 10: Toast auto-dismiss timing**
    - **Validates: Requirements 10.4**
    - Use fast-check to generate random toast types. Assert autoDismissMs=5000 for success, null for error.

- [x] 7. Frontend: Chat conversion lifecycle
  - [x] 7.1 Add `_generateDocumentTitle()` to `ChatApp` in `static/js/chat.js`
    - Format: `"Conversation: {first_user_message_truncated} ({Mon D, YYYY})"`
    - Truncate at 80 chars with ellipsis `…` if needed
    - Fallback to `"Conversation: (untitled) ({date})"` if no user messages
    - _Requirements: 3.1, 3.2, 3.3_

  - [x] 7.2 Add `_convertCurrentConversation()` to `ChatApp`
    - Fire-and-forget POST to `/api/conversations/{thread_id}/convert-to-knowledge` with generated title
    - Show loading toast, update to success/error on completion
    - _Requirements: 1.3, 1.4, 1.5, 10.1, 10.2, 10.3_

  - [x] 7.3 Modify `clearChat()` in `ChatApp` to trigger conversion before clearing
    - Guard: only convert if `messageHistory.length > 0` and `currentThreadId` exists
    - Call `_convertCurrentConversation()` then proceed with existing clear logic
    - Skip conversion if no messages
    - Add `activeThreadId` property, dispatch `active-thread-changed` event with null on clear
    - _Requirements: 1.1, 1.2, 1.6_

  - [x] 7.4 Modify WebSocket `disconnected` handler to trigger conversion
    - Guard: only convert if `messageHistory.length > 0` and `currentThreadId` exists
    - Log errors on failure (no toast since user may have navigated away)
    - _Requirements: 2.1, 2.2, 2.3_

  - [ ]* 7.5 Write property test for conversion trigger condition (Property 1)
    - **Property 1: Conversion triggered if and only if conversation has messages**
    - **Validates: Requirements 1.1, 1.6, 2.1, 2.2, 6.4, 6.5**
    - Use fast-check to generate random messageHistory arrays (empty and non-empty). Assert conversion called iff non-empty.

  - [ ]* 7.6 Write property test for title generation format (Property 3)
    - **Property 3: Title generation format**
    - **Validates: Requirements 3.1, 3.2, 3.3**
    - Use fast-check to generate random strings and dates. Verify `_generateDocumentTitle()` output matches expected format, truncation, and fallback.

- [x] 8. Frontend: Conversation reopening
  - [x] 8.1 Add `reopenConversation(threadId)` to `ChatApp`
    - If current chat has messages and different thread, convert current first
    - Fetch `GET /api/conversations/{threadId}/history`, render messages
    - Set `currentThreadId` and `activeThreadId` to reopened thread
    - Dispatch `active-thread-changed` event with the thread ID
    - Send `resume_conversation` message via WebSocket
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ]* 8.2 Write property test for reopened conversation state (Property 6)
    - **Property 6: Reopened conversation restores all messages and sets correct thread ID**
    - **Validates: Requirements 6.1, 6.2**
    - Use fast-check to generate random message arrays of varying lengths. Assert all messages rendered and currentThreadId set correctly.

- [x] 9. Frontend: Document list panel — conversation documents
  - [x] 9.1 Modify `createDocumentItem()` in `DocumentListPanel` to handle conversation documents
    - Detect `source_type === 'conversation'`, render with 💬 icon instead of 📄
    - Show title, creation date, chunk count
    - Wire click handler to call `chatApp.reopenConversation(doc.thread_id)`
    - _Requirements: 5.1, 5.2, 5.3, 6.1_

  - [x] 9.2 Add delete button state management for active conversations
    - Track `_activeThreadId` via `active-thread-changed` event listener
    - Disable delete button when `doc.thread_id === _activeThreadId`
    - Grey-out styling, tooltip "Cannot delete while conversation is active"
    - Re-enable when active thread changes
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [x] 9.3 Add inline title editing for conversation documents
    - Click title → switch to `<input>` element
    - Enter or blur → PATCH `/api/conversations/{thread_id}/title`, update DOM on success
    - Escape → revert to previous title
    - Empty title → revert and show validation message
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [x] 9.4 Add "View Concepts" button to document action buttons
    - Show button for any completed document with `concept_count > 0` (both PDF and conversation)
    - Wire click to open `KGExplorerPanel.open(doc.document_id)`
    - _Requirements: 11.1_

  - [ ]* 9.5 Write property test for icon rendering (Property 5)
    - **Property 5: Conversation document rendering contains required information**
    - **Validates: Requirements 5.2, 5.3**
    - Use fast-check to generate random doc objects with varying source_type. Assert correct icon (💬 vs 📄).

  - [ ]* 9.6 Write property test for delete button state (Property 7)
    - **Property 7: Delete button disabled if and only if conversation is active**
    - **Validates: Requirements 7.1, 7.4**
    - Use fast-check to generate random activeThreadId and document thread_id pairs. Assert disabled iff equal.

  - [ ]* 9.7 Write property test for View Concepts button presence (Property 20)
    - **Property 20: View Concepts button presence**
    - **Validates: Requirements 11.1**
    - Use fast-check to generate random doc objects with varying status and concept_count. Assert button shown iff completed and concept_count > 0.

- [x] 10. Frontend: Deletion semantics
  - [x] 10.1 Wire conversation document deletion in `DocumentListPanel`
    - On delete, call existing delete API which removes chunks from Milvus and concepts from Neo4j
    - Remove document from DOM immediately
    - Dispatch event so ChatApp removes UI handles to the source conversation
    - _Requirements: 8.1, 8.2, 8.4, 8.5_

  - [ ]* 10.2 Write property test for deletion semantics (Property 8)
    - **Property 8: Deletion removes search data but preserves conversation messages**
    - **Validates: Requirements 8.1, 8.2, 8.3**
    - Use Hypothesis to generate random conversation data, convert, delete. Assert Milvus empty, Neo4j empty, PostgreSQL messages preserved.

- [x] 11. Checkpoint — Chat lifecycle and document list complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Frontend: KG Explorer panel
  - [x] 12.1 Create `static/js/kg-explorer-panel.js` with `KGExplorerPanel` class
    - Panel DOM structure: header (back button, search input, close button), SVG viewport, detail sidebar
    - `open(sourceId)` — fetch landing view from `GET /api/knowledge-graph/{sourceId}/neighborhood`, render top 10 concept list
    - `navigateTo(conceptName)` — fetch ego graph, render D3 force-directed layout
    - `navigateBack()` — pop from navigation history stack, navigate to previous focus
    - `close()` — tear down D3 simulation, remove panel
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 12.1, 12.4_

  - [x] 12.2 Implement D3 force-directed graph rendering in `_renderGraph()`
    - Nodes as labeled circles, edges as labeled directed lines
    - Force configuration: link distance 80, many-body strength -200, center force, collide radius 30
    - Color coding: document-sourced `#4A90D9` (blue), conversation-sourced `#50C878` (green)
    - Focus node highlighted with ring
    - Source document name as subtitle on each node
    - _Requirements: 11.5, 11.6, 14.2, 14.3_

  - [x] 12.3 Implement neighborhood transition in `_transitionGraph()`
    - Retained nodes (in both old and new neighborhoods) stay in place
    - Exiting nodes fade out, entering nodes fade in
    - Click edge node → shift focus, fetch new neighborhood
    - Click focus node → show detail panel (concept name, source, chunks, relationship count)
    - _Requirements: 12.1, 12.2, 12.3, 12.5, 14.4_

  - [x] 12.4 Implement semantic search in KG Explorer
    - Search input field at top of panel
    - On submit, call `GET /api/knowledge-graph/search?query={text}&source_id={id}`
    - Show results as ranked dropdown list
    - Selecting a result navigates to that concept's neighborhood
    - "No matching concepts found" message when no results
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5_

  - [x] 12.5 Add KG Explorer CSS styles to `static/css/chat.css`
    - Panel overlay/sidebar layout
    - Node and edge styling, color coding
    - Landing view list styling
    - Search input and results dropdown
    - Detail panel sidebar
    - Transition animations (fade in/out)
    - _Requirements: 11.5, 11.6, 12.2, 12.3_

  - [ ]* 12.6 Write property test for navigation history (Property 13)
    - **Property 13: Navigation history stack preserves traversal order**
    - **Validates: Requirements 12.4**
    - Use fast-check to generate random sequences of navigateTo() calls. Assert history stack length = K-1 and correct order.

  - [ ]* 12.7 Write property test for neighborhood transition (Property 14)
    - **Property 14: Neighborhood transition retains shared nodes**
    - **Validates: Requirements 12.1, 12.2, 14.4**
    - Use fast-check to generate two consecutive node sets. Assert shared nodes retained, old-only removed, new-only added.

  - [ ] 12.8 Write property test for cross-source inclusion (Property 16)
    - **Property 16: Cross-source neighborhood inclusion**
    - **Validates: Requirements 14.1**
    - Use Hypothesis to generate focus concepts with cross-source relationships. Assert cross-source nodes included with correct source_type.

  - [ ]* 12.9 Write property test for node color coding (Property 17)
    - **Property 17: Node color coding by source type**
    - **Validates: Requirements 14.2, 14.3**
    - Use fast-check to generate random nodes with varying source_type. Assert correct color assignment and source subtitle display.

- [x] 13. Final checkpoint — All features integrated
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Backend tasks (1–4) are completed before frontend tasks that depend on them
- The DI pattern follows project conventions in `api/dependencies/services.py`
