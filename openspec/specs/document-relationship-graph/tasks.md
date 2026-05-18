# Implementation Plan: Document Relationship Graph

## Overview

Add an interactive force-directed graph visualization to the document list panel. Backend: new WebSocket handler queries Neo4j for cross-document `SAME_AS` relationships and returns a nodes-and-edges payload. Frontend: Graph button on completed documents opens a popup, lazily loads D3.js, and renders the force-directed graph with drag, tooltips, and zoom-to-fit.

## Tasks

- [ ] 1. Add WebSocket message models
  - [ ] 1.1 Add Pydantic models to `src/multimodal_librarian/api/models/chat_document_models.py`
    - Add `DocumentRelationshipGraphRequest` with `type` literal and `document_id` field
    - Add `GraphNode` with `document_id`, `title`, `is_origin` fields
    - Add `GraphEdge` with `source`, `target`, `shared_count`, `sample_concepts` (max 5) fields
    - Add `DocumentRelationshipGraphResponse` with `type`, `document_id`, `nodes`, `edges` fields
    - Add `DocumentRelationshipGraphError` with `type`, `document_id`, `message` fields
    - _Requirements: 3.2, 3.3, 3.5_

- [ ] 2. Implement backend handler and WebSocket routing
  - [ ] 2.1 Add `handle_document_relationship_graph()` in `src/multimodal_librarian/api/routers/chat_document_handlers.py`
    - Query Neo4j via `get_database_factory().get_graph_client()` using the Cypher query that traverses `SAME_AS` relationships up to 2 hops from the origin document's concepts
    - Aggregate results by target document: count shared concepts, collect up to 5 sample concept names per edge
    - Look up document titles from PostgreSQL `multimodal_librarian.knowledge_sources` table; fall back to document_id if PostgreSQL is unavailable
    - Build origin node with `is_origin=True`, related document nodes, and edges
    - Return `document_relationship_graph_error` if Neo4j client is unavailable, query fails, or `document_id` is empty
    - Return valid response with only origin node and empty edges if no relationships found
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ] 2.2 Add WebSocket route dispatch in `src/multimodal_librarian/api/routers/chat.py`
    - Add `elif message_type == 'document_relationship_graph'` branch calling `handle_document_relationship_graph(message_data, connection_id, manager)`
    - _Requirements: 3.1_

  - [ ]* 2.3 Write property test: Response contains exactly one origin node (Property 2)
    - Test file: `tests/components/test_document_relationship_graph_properties.py`
    - **Property 2: Response structure contains origin node with is_origin flag**
    - Generate random Neo4j result sets with varying numbers of related documents. Run aggregation logic. Assert exactly one node has `is_origin=True` matching the input `document_id`.
    - **Validates: Requirements 3.3**

  - [ ]* 2.4 Write property test: Sample concepts capped at 5 (Property 3)
    - Test file: `tests/components/test_document_relationship_graph_properties.py`
    - **Property 3: Sample concepts per edge are capped at 5**
    - Generate random Neo4j result sets with edges having 0–100 shared concepts. Assert every edge's `sample_concepts` has length ≤ 5.
    - **Validates: Requirements 3.5**

  - [ ]* 2.5 Write property test: No dangling edge references (Property 4)
    - Test file: `tests/components/test_document_relationship_graph_properties.py`
    - **Property 4: Response nodes and edges are structurally consistent**
    - Generate random Neo4j result sets. Assert every edge's `source` and `target` appear in the nodes list.
    - **Validates: Requirements 3.2**

  - [ ]* 2.6 Write unit tests for backend handler
    - Test file: `tests/components/test_document_relationship_graph.py`
    - Test handler returns error response when Neo4j client is unavailable (Req 3.4)
    - Test handler returns error response when `document_id` is empty
    - Test handler returns valid response with only origin node when no SAME_AS relationships exist
    - Test handler correctly queries with 2-hop SAME_AS traversal (Req 3.6)
    - Test handler looks up document titles from PostgreSQL
    - Test handler degrades gracefully when PostgreSQL is unavailable (uses document_id as title)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [ ] 3. Checkpoint - Ensure all backend tests pass
  - Ensure all tests pass, ask the user if questions arise.
  - After editing server-side Python files, clear `.pyc` cache and restart: `docker exec librarian-app-1 find /app -name "*.pyc" -delete` then `docker restart librarian-app-1 librarian-celery-worker-1`

- [ ] 4. Implement Graph button and popup in frontend
  - [ ] 4.1 Add Graph button to `src/multimodal_librarian/static/js/document-list-panel.js`
    - Modify `buildStatsHtml()` to render a `document-graph-btn` button with "🔗 Graph" label adjacent to the Stats toggle
    - Only render when `doc.status === 'completed'` and `doc.concept_count > 0`
    - Add click event listener that opens the graph popup
    - _Requirements: 1.1, 1.2, 1.3_

  - [ ] 4.2 Implement Graph popup DOM and lifecycle in `src/multimodal_librarian/static/js/document-list-panel.js`
    - Create popup DOM structure: backdrop, popup container, header with title and close button (✕), body with loading indicator and message area
    - Append popup to `document.body` to avoid overflow clipping
    - Title bar shows "Document Relationships: {document_title}"
    - Implement close on: close button click, backdrop click, Escape key, Graph button re-click
    - Only one popup open at a time
    - Show loading indicator while fetching data; show descriptive message on error or empty data
    - Check WebSocket connection before sending; show "Not connected to server" if disconnected
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 6.4_

  - [ ] 4.3 Implement D3.js lazy loading in `src/multimodal_librarian/static/js/document-list-panel.js`
    - Add `_loadD3()` method returning a cached Promise that loads D3.js v7 from CDN
    - Show loading indicator while D3 loads; show error message if CDN load fails
    - _Requirements: 5.1, 5.2, 5.3_

  - [ ] 4.4 Implement force-directed graph rendering in `src/multimodal_librarian/static/js/document-list-panel.js`
    - Add `_renderGraph(container, data)` method using D3.js force simulation
    - Render document nodes as circles, origin node in distinct color
    - Render edges as lines with stroke-width proportional to `shared_count`
    - Add text labels truncated to 30 characters with ellipsis
    - Add tooltip on node hover (full title) and edge hover (concept names)
    - Add drag behavior via `d3.drag()`
    - Apply zoom-to-fit after simulation stabilizes
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_

  - [ ] 4.5 Add WebSocket response handler for `document_relationship_graph` and `document_relationship_graph_error` messages
    - Wire incoming WebSocket messages to the popup: on success, call `_renderGraph()`; on error, show error message in popup
    - _Requirements: 2.6, 2.7, 3.4_

- [ ] 5. Add Graph popup CSS styles
  - [ ] 5.1 Add popup styles to `src/multimodal_librarian/static/css/chat.css`
    - Style `.graph-popup-backdrop` with semi-transparent overlay
    - Style `.graph-popup` with min 500×400px, max 90vw × 80vh, matching panel color palette, font family, and border-radius
    - Style header, close button, loading indicator, message area, and SVG container
    - Style tooltip for node/edge hover
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [ ] 6. Checkpoint - Ensure frontend works end-to-end
  - Ensure all tests pass, ask the user if questions arise.
  - For static JS/HTML/CSS files, no Docker restart needed — just hard refresh the browser.

- [ ] 7. Frontend property and unit tests
  - [ ]* 7.1 Write property test: Graph button visibility (Property 1)
    - Test file: `tests/js/test_document_graph_properties.js`
    - **Property 1: Graph button visibility is determined by status and concept count**
    - Generate random document objects with varying `status` and `concept_count`. Assert Graph button presence matches `status === "completed" && concept_count > 0`.
    - **Validates: Requirements 1.1, 1.2**

  - [ ]* 7.2 Write property test: Title truncation (Property 5)
    - Test file: `tests/js/test_document_graph_properties.js`
    - **Property 5: Title truncation at 30 characters**
    - Generate random strings of length 0–200. Assert output ≤ 30 chars unchanged, > 30 chars truncated with "…", output never exceeds 31 characters.
    - **Validates: Requirements 4.2**

  - [ ]* 7.3 Write property test: Edge thickness monotonicity (Property 6)
    - Test file: `tests/js/test_document_graph_properties.js`
    - **Property 6: Edge thickness is monotonically proportional to shared count**
    - Generate pairs of edges with random `shared_count` values. Assert scaling function produces monotonically non-decreasing stroke-widths.
    - **Validates: Requirements 4.4**

  - [ ]* 7.4 Write property test: Popup title format (Property 7)
    - Test file: `tests/js/test_document_graph_properties.js`
    - **Property 7: Popup title format includes document title**
    - Generate random title strings. Assert popup title equals `"Document Relationships: " + title`.
    - **Validates: Requirements 6.4**

  - [ ]* 7.5 Write unit tests for frontend behavior
    - Test file: `tests/js/test_document_graph.js`
    - Test Graph button renders with "🔗 Graph" text (Req 1.3)
    - Test Graph button click opens popup (Req 2.1)
    - Test second click closes popup (Req 2.2)
    - Test backdrop click closes popup (Req 2.3)
    - Test Escape key closes popup (Req 2.4)
    - Test close button (✕) closes popup (Req 2.5)
    - Test error/empty data shows descriptive message (Req 2.7)
    - Test D3.js loaded lazily on first click (Req 5.1)
    - Test D3.js load failure shows error message (Req 5.2)
    - Test hover on node shows full title tooltip (Req 4.6)
    - Test hover on edge shows concept names tooltip (Req 4.5)
    - _Requirements: 1.3, 2.1, 2.2, 2.3, 2.4, 2.5, 2.7, 4.5, 4.6, 5.1, 5.2_

- [ ] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Backend uses Python 3.9+ with FastAPI and Pydantic 2.5+; frontend is vanilla JavaScript
- After editing Python files: `docker exec librarian-app-1 find /app -name "*.pyc" -delete` then `docker restart librarian-app-1 librarian-celery-worker-1`
- After editing static JS/CSS/HTML files: hard refresh the browser (no Docker restart needed)
- Property tests use Hypothesis (Python) and fast-check (JavaScript) with minimum 100 examples per property
- Docker container names use `librarian-` prefix
- PostgreSQL schema prefix: `multimodal_librarian.`
