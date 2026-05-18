# Implementation Plan: Composite Document Relationships

## Overview

Extend the cross-document relationship system to include ConceptNet-derived relationships in a composite scoring algorithm. A new `CompositeScoreEngine` computes per-edge scores (type weight, embedding similarity, CN weight) and aggregates them into document-pair scores stored as `RELATED_DOCS` edges in Neo4j. A WebSocket handler serves graph data to a frontend popup that renders an interactive D3.js force-directed graph with center-node navigation and threshold filtering.

## Tasks

- [x] 1. Add Pydantic models for WebSocket messages
  - [x] 1.1 Add RelatedDocsGraph models to `src/multimodal_librarian/api/models/chat_document_models.py`
    - Add `RelatedDocsGraphRequest` with `type` literal `"related_docs_graph"` and `document_id` string field
    - Add `RelatedDocsGraphNode` with `document_id`, `title`, `is_origin` (default false) fields
    - Add `RelatedDocsGraphEdge` with `source`, `target`, `score` (float, ge=0.0, le=1.0), `edge_count` (int, ge=0) fields
    - Add `RelatedDocsGraphResponse` with `type` literal, `document_id`, `nodes` list, `edges` list fields
    - Add `RelatedDocsGraphError` with `type` literal `"related_docs_graph_error"`, `document_id`, `message` fields
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [ ]* 1.2 Write property test for RelatedDocsGraphEdge schema validation (Property 20)
    - Test file: `tests/api/test_related_docs_graph_models.py`
    - **Property 20: RelatedDocsGraphEdge schema validation**
    - Generate valid combinations (score in [0.0, 1.0], edge_count >= 0) and verify construction succeeds; generate invalid combinations (score outside range, negative edge_count) and verify Pydantic raises ValidationError
    - **Validates: Requirements 8.3**

  - [ ]* 1.3 Write unit tests for Pydantic models
    - Test file: `tests/api/test_related_docs_graph_models.py`
    - Test all five models serialize/deserialize correctly
    - Test `RelatedDocsGraphResponse` round-trip with nodes and edges
    - Test literal type fields reject wrong values
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

- [x] 2. Implement CompositeScoreEngine
  - [x] 2.1 Create `src/multimodal_librarian/services/composite_score_engine.py` with dataclasses and engine class
    - Define `EdgeScore`, `DocumentPairScore`, `CompositeScoreResult` dataclasses
    - Define `CompositeScoreEngine` class with `TYPE_WEIGHTS` dict and formula weight constants
    - Implement `__init__(self, kg_client)` storing the Neo4j client reference
    - _Requirements: 2.2_

  - [x] 2.2 Implement `_discover_cross_doc_edges()` method
    - Execute two Cypher queries (forward and reverse direction) to find all cross-document concept pairs connected via qualifying relationship types (SAME_AS, IsA, PartOf, RelatedTo, UsedFor, CapableOf, HasProperty, AtLocation, Causes, HasPrerequisite, MotivatedByGoal, Synonym, SimilarTo)
    - Filter out edges where `source_document == 'conceptnet'`
    - Deduplicate edges from both directions
    - Return list of edge dicts with concept IDs, document IDs, embeddings, relationship type, and CN weight
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 2.3 Implement `_compute_edge_score()` method
    - Compute cosine similarity between embedding vectors (default 0.0 if either is missing/zero)
    - Look up type_weight from `TYPE_WEIGHTS` dict (default 0.3 for unknown types)
    - Normalize cn_weight to [0.0, 1.0]; use 1.0 for SAME_AS edges, 0.0 if weight property is missing
    - Apply formula: `edge_score = clamp(type_weight × 0.4 + embedding_similarity × 0.45 + cn_weight × 0.15, 0.0, 1.0)`
    - Return `EdgeScore` dataclass
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [ ]* 2.4 Write property test for per-edge score formula (Property 3)
    - Test file: `tests/services/test_composite_score_engine.py`
    - **Property 3: Per-edge score formula correctness**
    - Generate random (relationship_type, embedding_similarity, cn_weight) tuples using hypothesis strategies; verify computed edge_score matches the formula exactly
    - **Validates: Requirements 2.1, 2.2, 2.4, 2.6**

  - [ ]* 2.5 Write property test for cosine similarity (Property 4)
    - Test file: `tests/services/test_composite_score_engine.py`
    - **Property 4: Cosine similarity correctness**
    - Generate random vector pairs; compare against numpy reference implementation; verify 0.0 when either vector is missing or zero
    - **Validates: Requirements 2.3, 2.4**

  - [ ]* 2.6 Write property test for CN weight normalization (Property 5)
    - Test file: `tests/services/test_composite_score_engine.py`
    - **Property 5: CN weight normalization**
    - Generate random float values; verify normalized result is clamped to [0.0, 1.0]
    - **Validates: Requirements 2.5**

  - [ ]* 2.7 Write property test for edge score output range (Property 6)
    - Test file: `tests/services/test_composite_score_engine.py`
    - **Property 6: Edge score output range**
    - Generate extreme inputs (type_weight in [0.0, 1.0], embedding_similarity in [-1.0, 1.0], cn_weight in [0.0, 1.0]); verify output always in [0.0, 1.0]
    - **Validates: Requirements 2.7**

  - [x] 2.8 Implement `_get_concept_counts()` and `_aggregate_document_pairs()` methods
    - `_get_concept_counts()`: query Neo4j for concept count per document using UNWIND + count
    - `_aggregate_document_pairs()`: group edge scores by (doc_id_a, doc_id_b) pair, compute avg_edge_score, compute neighborhood_density as `min(edge_count / min(concept_count_a, concept_count_b), 1.0)` (use 1 as denominator if concept count is 0), compute doc_score as `clamp(avg_edge_score × 0.7 + neighborhood_density × 0.3, 0.0, 1.0)`
    - Return list of `DocumentPairScore` dataclasses with ISO 8601 `computed_at` timestamp
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [ ]* 2.9 Write property test for document-pair score formula (Property 7)
    - Test file: `tests/services/test_composite_score_engine.py`
    - **Property 7: Document-pair score formula correctness**
    - Generate random lists of edge scores and concept counts; verify computed doc_score matches the formula and is in [0.0, 1.0]
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4**

  - [x] 2.10 Implement `_persist_related_docs()` method
    - Select representative concept per document from the edge set (concept with highest individual edge score)
    - Execute MERGE Cypher query with UNWIND for batch upsert of RELATED_DOCS edges
    - Store properties: score, edge_count, avg_edge_score, neighborhood_density, computed_at
    - Run upsert twice (once per direction) for bidirectional storage
    - Return count of edges created/updated
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 2.11 Implement `compute_composite_scores()` main entry point
    - Orchestrate: discover edges → compute per-edge scores → get concept counts → aggregate document pairs → persist RELATED_DOCS
    - Track timing for `duration_ms`
    - Return `CompositeScoreResult` with all metrics
    - Let all exceptions propagate (KG failure is fatal)
    - _Requirements: 1.1, 5.1, 5.3, 5.4_

  - [ ]* 2.12 Write property test for same-document exclusion (Property 2)
    - Test file: `tests/services/test_composite_score_engine.py`
    - **Property 2: Same-document exclusion**
    - Generate mock Neo4j results containing both intra-doc and cross-doc edges; verify only cross-doc edges are returned
    - **Validates: Requirements 1.4**

  - [ ]* 2.13 Write property test for edge discovery completeness (Property 1)
    - Test file: `tests/services/test_composite_score_engine.py`
    - **Property 1: Edge discovery completeness**
    - Generate random graph fixtures with known cross-doc edges across all qualifying relationship types; verify all are returned by discovery
    - **Validates: Requirements 1.2, 1.3**

  - [ ]* 2.14 Write unit tests for CompositeScoreEngine
    - Test file: `tests/services/test_composite_score_engine.py`
    - Test missing embeddings default to similarity 0.0
    - Test SAME_AS edges use cn_weight 1.0
    - Test zero concepts in a document (denominator uses 1)
    - Test empty graph returns zero-count result
    - Test single document in KG returns zero-count result
    - Test unknown relationship type uses default weight 0.3
    - _Requirements: 2.4, 2.6, 3.3_

- [x] 3. Integrate CompositeScoreEngine into EnrichmentService
  - [x] 3.1 Add composite scoring step to `src/multimodal_librarian/services/enrichment_service.py`
    - After the batch ConceptNet persistence block in `enrich_concepts()`, add step 6: instantiate `CompositeScoreEngine` with `self.kg_service.client` and call `compute_composite_scores(document_id)`
    - Log result metrics (edges_discovered, document_pairs, duration_ms)
    - Let exceptions propagate to fail the enrichment pipeline
    - Only invoke if `self.kg_service` and `self.kg_service.client` are available
    - _Requirements: 5.1, 5.3_

  - [ ]* 3.2 Write unit tests for enrichment integration
    - Test file: `tests/services/test_enrichment_composite_integration.py`
    - Test `enrich_concepts()` calls `CompositeScoreEngine.compute_composite_scores()` after ConceptNet persistence
    - Test error propagation: when engine raises, enrichment pipeline fails
    - Test engine is not called when `kg_service` is None
    - _Requirements: 5.1, 5.3_

- [x] 4. Checkpoint - Ensure scoring engine and integration tests pass
  - Ensure all tests pass, ask the user if questions arise.
  - After editing Python files: `docker exec librarian-app-1 find /app -name "*.pyc" -delete` then `docker restart librarian-app-1 librarian-celery-worker-1`

- [x] 5. Implement Related Docs Graph backend handler and WebSocket routing
  - [x] 5.1 Add `handle_related_docs_graph()` to `src/multimodal_librarian/api/routers/chat_document_handlers.py`
    - Validate `document_id` is present and non-empty; return `related_docs_graph_error` if missing
    - Query Neo4j for all `RELATED_DOCS` edges where one endpoint concept has `source_document` matching the requested document_id
    - Build `nodes` list with origin node (`is_origin=True`) and all related document nodes
    - Build `edges` list with source, target, score, edge_count from Neo4j results
    - Look up document titles from PostgreSQL `multimodal_librarian.knowledge_sources` table; fall back to document_id as title if PostgreSQL is unavailable
    - Return valid response with only origin node and empty edges if no RELATED_DOCS found
    - Return `related_docs_graph_error` if Neo4j client is unavailable or query fails
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8_

  - [x] 5.2 Add WebSocket route dispatch in `src/multimodal_librarian/api/routers/chat.py`
    - Add `elif message_type == 'related_docs_graph'` branch calling `handle_related_docs_graph(message_data, connection_id, manager)`
    - Import the handler function
    - _Requirements: 6.1_

  - [ ]* 5.3 Write property test: Response contains exactly one origin node (Property 11)
    - Test file: `tests/api/test_related_docs_graph_handler.py`
    - **Property 11: Graph response contains exactly one origin node**
    - Generate random Neo4j result sets with varying numbers of related documents; assert exactly one node has `is_origin=True` and its `document_id` matches the requested document_id
    - **Validates: Requirements 6.3**

  - [ ]* 5.4 Write property test: Nodes and edges are structurally consistent (Property 12)
    - Test file: `tests/api/test_related_docs_graph_handler.py`
    - **Property 12: Graph response nodes and edges are structurally consistent**
    - Generate random result sets; assert every edge's `source` and `target` reference a `document_id` in the nodes list
    - **Validates: Requirements 6.2, 8.6**

  - [ ]* 5.5 Write unit tests for Related Docs Graph handler
    - Test file: `tests/api/test_related_docs_graph_handler.py`
    - Test handler returns `related_docs_graph_error` when Neo4j client is unavailable (Req 6.7)
    - Test handler returns `related_docs_graph_error` when `document_id` is empty (Req 6.8)
    - Test handler returns valid response with only origin node when no RELATED_DOCS exist (Req 6.6)
    - Test handler resolves document titles from PostgreSQL (Req 6.4)
    - Test handler degrades gracefully when PostgreSQL is unavailable — uses document_id as title (Req 6.5)
    - Test handler returns correct edge data (score, edge_count) from Neo4j results
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8_

- [ ] 6. Implement RELATED_DOCS persistence property tests
  - [ ]* 6.1 Write property test for persistence completeness and bidirectionality (Property 8)
    - Test file: `tests/services/test_composite_score_engine.py`
    - **Property 8: RELATED_DOCS persistence completeness and bidirectionality**
    - Mock Neo4j client; generate random document pair scores; verify both directions are written with all required properties (score, edge_count, avg_edge_score, neighborhood_density, computed_at)
    - **Validates: Requirements 4.2, 4.4**

  - [ ]* 6.2 Write property test for idempotent upsert (Property 9)
    - Test file: `tests/services/test_composite_score_engine.py`
    - **Property 9: Idempotent upsert**
    - Run `compute_composite_scores` twice on same mock graph state; verify RELATED_DOCS edge properties are identical after both runs
    - **Validates: Requirements 4.3**

  - [ ]* 6.3 Write property test for scoped recomputation (Property 10)
    - Test file: `tests/services/test_composite_score_engine.py`
    - **Property 10: Scoped recomputation**
    - Set up existing RELATED_DOCS edges between documents not involving the new document; run composite scoring for new document; verify pre-existing edges remain unchanged
    - **Validates: Requirements 5.4**

- [x] 7. Checkpoint - Ensure all backend tests pass
  - Ensure all tests pass, ask the user if questions arise.
  - After editing Python files: `docker exec librarian-app-1 find /app -name "*.pyc" -delete` then `docker restart librarian-app-1 librarian-celery-worker-1`

- [x] 8. Implement frontend Related Docs button and popup
  - [x] 8.1 Add Related Docs button to `src/multimodal_librarian/static/js/document-list-panel.js`
    - Modify `buildStatsHtml()` to render a `document-related-docs-btn` button with "📎 Related Docs" label to the right of the Stats toggle
    - Only render when `doc.status === 'completed'` and `doc.concept_count > 0`
    - Add click event listener that opens the Related Docs Graph popup
    - _Requirements: 7.1_

  - [x] 8.2 Implement Related Docs Graph popup DOM and lifecycle in `src/multimodal_librarian/static/js/document-list-panel.js`
    - Create popup DOM structure: backdrop, popup container, header with title ("Related Documents: {title}") and close button (✕), controls area with threshold slider, body with loading indicator and message area
    - Append popup to `document.body` to avoid overflow clipping
    - Implement close on: close button click, backdrop click, Escape key, Related Docs button re-click
    - Only one popup open at a time (opening new closes previous)
    - Show loading indicator while fetching data
    - Check WebSocket connection before sending; show "Not connected to server." if disconnected
    - Send `{type: "related_docs_graph", document_id}` via WebSocket
    - _Requirements: 7.2, 7.3, 7.4, 7.16, 7.17_

  - [x] 8.3 Implement D3.js lazy loading in `src/multimodal_librarian/static/js/document-list-panel.js`
    - Add `_loadD3()` method returning a cached Promise that loads D3.js v7 from CDN
    - Prevent duplicate script tags using cached promise pattern
    - Show error message "Could not load visualization library. Please check your internet connection." if CDN load fails
    - _Requirements: 7.5, 7.15_

  - [x] 8.4 Add WebSocket response handler for `related_docs_graph` and `related_docs_graph_error` messages
    - Wire incoming WebSocket messages to the popup: on success, call graph rendering; on error, show error message in popup body
    - _Requirements: 6.7, 7.2_

- [x] 9. Implement frontend force-directed graph rendering
  - [x] 9.1 Implement `_renderRelatedDocsGraph(container, data)` in `src/multimodal_librarian/static/js/document-list-panel.js`
    - Create SVG element sized to popup body
    - Create D3 force simulation with `forceLink`, `forceManyBody`, `forceCenter`
    - Render edges as `<line>` elements with `<text>` labels showing score as percentage (e.g., "72%")
    - Render nodes as `<circle>` elements — Center_Node in distinct color (#4CAF50), Satellite_Nodes in secondary color (#2196F3)
    - Add text labels truncated to 30 characters (append "…" if truncated)
    - Add drag behavior via `d3.drag()`
    - _Requirements: 7.6, 7.7, 7.8, 7.9_

  - [x] 9.2 Implement center-node navigation
    - On Satellite_Node click: transition clicked node to center position as new Center_Node, move previous Center_Node to satellite orbit
    - Update node colors to reflect new center/satellite roles
    - Scroll document list panel to the corresponding document item and apply a visual highlight CSS class
    - _Requirements: 7.10, 7.11_

  - [x] 9.3 Implement threshold slider filtering
    - Listen to Threshold_Slider `input` event (range 0.0–1.0, step 0.01, default 0.5)
    - Update threshold display value as percentage
    - Hide all edges with score < threshold
    - Hide all Satellite_Nodes that have no remaining visible edges
    - Always keep Center_Node visible regardless of threshold
    - _Requirements: 7.12, 7.13, 7.14_

- [x] 10. Add CSS styles for Related Docs popup and button
  - [x] 10.1 Add styles to `src/multimodal_librarian/static/css/chat.css`
    - Style `.related-docs-popup-backdrop` with semi-transparent overlay
    - Style `.related-docs-popup` with appropriate dimensions, matching panel color palette, font family, and border-radius
    - Style header, close button, controls area (threshold slider), loading indicator, message area, and SVG container
    - Style `.document-related-docs-btn` button consistent with existing Stats toggle
    - Style `.document-highlight` class for document list focus shift animation
    - _Requirements: 7.1, 7.2, 7.7, 7.12_

- [x] 11. Checkpoint - Ensure frontend works end-to-end
  - Ensure all tests pass, ask the user if questions arise.
  - For static JS/CSS/HTML files, no Docker restart needed — just hard refresh the browser.

- [ ] 12. Frontend property and unit tests (manual — no automated JS test framework)
  - [ ]* 12.1 Write property test: Edge label score percentage formatting (Property 13)
    - Test file: `tests/frontend/test_related_docs_graph_popup.js`
    - **Property 13: Edge label score percentage formatting**
    - Generate random score values in [0.0, 1.0]; verify label equals `Math.round(score × 100) + "%"`
    - **Validates: Requirements 7.8**

  - [ ]* 12.2 Write property test: Node label title truncation (Property 14)
    - Test file: `tests/frontend/test_related_docs_graph_popup.js`
    - **Property 14: Node label title truncation at 30 characters**
    - Generate random strings 0–200 chars; verify ≤30 unchanged, >30 truncated with "…", output never exceeds 31 characters
    - **Validates: Requirements 7.9**

  - [ ]* 12.3 Write property test: Center-node navigation preserves graph data (Property 15)
    - Test file: `tests/frontend/test_related_docs_graph_popup.js`
    - **Property 15: Center-node navigation preserves graph data**
    - Generate random graphs; simulate center-node switch; verify total node and edge counts unchanged
    - **Validates: Requirements 7.10**

  - [ ]* 12.4 Write property test: Threshold slider filtering correctness (Property 16)
    - Test file: `tests/frontend/test_related_docs_graph_popup.js`
    - **Property 16: Threshold slider filtering correctness**
    - Generate random edge sets and threshold values; verify visible edges have score >= T, visible Satellite_Nodes have at least one visible edge, Center_Node always visible
    - **Validates: Requirements 7.12, 7.13, 7.14**

  - [ ]* 12.5 Write property test: Document list focus shift (Property 17)
    - Test file: `tests/frontend/test_related_docs_graph_popup.js`
    - **Property 17: Document list focus shift targets correct document**
    - Generate random node clicks; verify scroll target matches clicked node's document_id
    - **Validates: Requirements 7.11**

  - [ ]* 12.6 Write property test: Related_Docs_Button visibility (Property 18)
    - Test file: `tests/frontend/test_related_docs_graph_popup.js`
    - **Property 18: Related_Docs_Button visibility is determined by status and concept count**
    - Generate random document objects; verify button presence iff `status === "completed"` and `concept_count > 0`
    - **Validates: Requirements 7.1**

  - [ ]* 12.7 Write property test: Popup title format (Property 19)
    - Test file: `tests/frontend/test_related_docs_graph_popup.js`
    - **Property 19: Popup title format includes document title**
    - Generate random title strings; verify popup title equals `"Related Documents: " + title`
    - **Validates: Requirements 7.17**

- [x] 13. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Backend uses Python 3.9+ with FastAPI and Pydantic 2.5+; frontend is vanilla JavaScript
- After editing Python files: `docker exec librarian-app-1 find /app -name "*.pyc" -delete` then `docker restart librarian-app-1 librarian-celery-worker-1`
- After editing static JS/CSS/HTML files: hard refresh the browser (no Docker restart needed)
- Property tests use `hypothesis` library with minimum 100 examples per property (`@settings(max_examples=100)`)
- Frontend property tests (task 12) are optional since there is no automated JS test framework in this project
- Docker container names use `librarian-` prefix
- PostgreSQL schema prefix: `multimodal_librarian.`
- The existing `document-relationship-graph` spec has a similar D3.js popup pattern that can be referenced for frontend implementation
- KG failure is fatal for the scoring engine (exceptions propagate); KG failure in the graph handler returns an error response gracefully
