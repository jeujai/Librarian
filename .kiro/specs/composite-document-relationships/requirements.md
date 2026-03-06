# Requirements Document

## Introduction

This feature extends the cross-document relationship system beyond identity-based `SAME_AS` links (which match concepts via shared YAGO Q-numbers) to include ConceptNet-derived relationships (IsA, PartOf, RelatedTo, etc.) for cross-document linkage. A two-stage composite scoring algorithm computes per-edge scores and aggregates them into document-pair scores. Pre-computed `RELATED_DOCS` edges are stored in Neo4j at ingestion time so that downstream consumers (visualization, search boosting) can retrieve document relatedness without runtime computation.

## Glossary

- **Composite_Score_Engine**: The new component that computes per-edge scores and document-pair aggregate scores for cross-document concept relationships.
- **EnrichmentService**: The existing service (`services/enrichment_service.py`) that orchestrates YAGO and ConceptNet enrichment and creates `SAME_AS` cross-document links.
- **Knowledge_Graph_Client**: The Neo4j graph database client accessed via `get_database_factory().get_graph_client()` that executes Cypher queries.
- **RELATED_DOCS_Edge**: A Neo4j relationship of type `RELATED_DOCS` between two Concept nodes from different documents, storing the composite score and its component metrics.
- **Edge_Score**: The per-edge score for a single cross-document concept pair, computed from relationship type weight, embedding similarity, and ConceptNet edge weight.
- **Document_Pair_Score**: The aggregate score for a pair of documents, computed from the average of all Edge_Scores and a neighborhood density factor.
- **Type_Weight**: A confidence weight assigned to each relationship type reflecting its semantic reliability for cross-document linkage (e.g., SAME_AS = 1.0, IsA = 0.65, PartOf = 0.60).
- **Embedding_Similarity**: The cosine similarity between the embedding vectors of two Concept nodes.
- **CN_Weight**: The normalized ConceptNet edge weight (the `weight` property stored on ConceptNet relationship edges in Neo4j).
- **Neighborhood_Density**: The fraction of the smaller document's concepts that participate in cross-document edges, capped at 1.0.
- **Document_List_Panel**: The existing frontend class (`static/js/document-list-panel.js`) that renders the list of uploaded documents with stats.
- **Related_Docs_Graph_Handler**: The backend async function in `chat_document_handlers.py` that handles `related_docs_graph` WebSocket messages by querying Neo4j for all `RELATED_DOCS` edges involving a document and returning a nodes-and-edges payload.
- **Related_Docs_Button**: A dedicated button placed to the right of the Stats toggle on each completed document item, used to open the Related_Docs_Graph_Popup.
- **Related_Docs_Graph_Popup**: A floating overlay appended to `document.body` that renders an interactive D3.js force-directed graph showing the origin document and all related documents as nodes, connected by edges labeled with composite scores.
- **Center_Node**: The document node currently positioned at the visual center of the graph, rendered with a distinct color. Initially the origin document; changes when the user clicks a Satellite_Node.
- **Satellite_Node**: A document node orbiting around the Center_Node in the force-directed graph, representing a related document. Clicking a Satellite_Node makes it the new Center_Node.
- **Threshold_Slider**: A range input control (0.0 to 1.0, step 0.01, default 0.5) within the Related_Docs_Graph_Popup that filters edges and nodes below the selected composite score threshold in real time.

## Requirements

### Requirement 1: Cross-Document Edge Discovery

**User Story:** As a system operator, I want the system to discover all cross-document concept pairs connected via ConceptNet relationships after enrichment, so that composite scores can be computed for every relevant edge.

#### Acceptance Criteria

1. WHEN YAGO enrichment and ConceptNet enrichment complete for a newly ingested document, THE EnrichmentService SHALL invoke the Composite_Score_Engine to discover cross-document concept pairs.
2. WHEN discovering cross-document edges, THE Composite_Score_Engine SHALL query the Knowledge_Graph_Client for all ConceptNet relationships (IsA, PartOf, RelatedTo, UsedFor, CapableOf, HasProperty, AtLocation, Causes, HasPrerequisite, MotivatedByGoal, Synonym, SimilarTo) where one concept belongs to the newly ingested document and the other concept belongs to a different document.
3. WHEN discovering cross-document edges, THE Composite_Score_Engine SHALL also include existing `SAME_AS` relationships in the edge set.
4. THE Composite_Score_Engine SHALL exclude concept pairs where both concepts belong to the same document.

### Requirement 2: Per-Edge Score Computation

**User Story:** As a system operator, I want each cross-document concept pair scored using relationship type confidence, embedding similarity, and ConceptNet weight, so that the composite score reflects multiple dimensions of relatedness.

#### Acceptance Criteria

1. FOR EACH cross-document concept pair, THE Composite_Score_Engine SHALL compute an Edge_Score using the formula: `edge_score = type_weight × 0.4 + embedding_similarity × 0.45 + cn_weight × 0.15`.
2. THE Composite_Score_Engine SHALL assign Type_Weight values based on relationship type: SAME_AS = 1.0, IsA = 0.65, PartOf = 0.60, UsedFor = 0.55, CapableOf = 0.55, HasProperty = 0.50, AtLocation = 0.50, Causes = 0.55, HasPrerequisite = 0.50, MotivatedByGoal = 0.45, Synonym = 0.80, SimilarTo = 0.70, RelatedTo = 0.40.
3. WHEN computing Embedding_Similarity, THE Composite_Score_Engine SHALL calculate the cosine similarity between the embedding vectors stored on the two Concept nodes.
4. IF either Concept node lacks an embedding vector, THEN THE Composite_Score_Engine SHALL use a default Embedding_Similarity of 0.0 for that edge.
5. WHEN computing CN_Weight, THE Composite_Score_Engine SHALL use the `weight` property from the ConceptNet relationship edge, normalized to the range [0.0, 1.0].
6. IF the relationship is a `SAME_AS` edge (which has no ConceptNet weight), THEN THE Composite_Score_Engine SHALL use a CN_Weight of 1.0.
7. THE Composite_Score_Engine SHALL clamp the final Edge_Score to the range [0.0, 1.0].

### Requirement 3: Document-Pair Score Aggregation

**User Story:** As a system operator, I want per-edge scores aggregated into a single document-pair score that accounts for both average edge quality and coverage density, so that document relatedness is expressed as a single comparable metric.

#### Acceptance Criteria

1. FOR EACH pair of documents connected by one or more cross-document edges, THE Composite_Score_Engine SHALL compute a Document_Pair_Score using the formula: `doc_score = avg_edge_score × 0.7 + neighborhood_density × 0.3`.
2. WHEN computing avg_edge_score, THE Composite_Score_Engine SHALL calculate the arithmetic mean of all Edge_Scores between the two documents.
3. WHEN computing Neighborhood_Density, THE Composite_Score_Engine SHALL use the formula: `min(cross_doc_edge_count / min_concepts_in_smaller_doc, 1.0)` where `cross_doc_edge_count` is the number of cross-document edges between the two documents and `min_concepts_in_smaller_doc` is the concept count of whichever document has fewer concepts.
4. THE Composite_Score_Engine SHALL clamp the final Document_Pair_Score to the range [0.0, 1.0].

### Requirement 4: RELATED_DOCS Edge Storage

**User Story:** As a system operator, I want all computed document-pair scores stored as `RELATED_DOCS` edges in Neo4j regardless of score value, so that downstream consumers can apply their own thresholds at display time.

#### Acceptance Criteria

1. FOR EACH document pair with a computed Document_Pair_Score, THE Composite_Score_Engine SHALL create or update a `RELATED_DOCS` relationship in Neo4j between two representative Concept nodes (one from each document).
2. THE RELATED_DOCS_Edge SHALL store the following properties: `score` (Document_Pair_Score), `edge_count` (number of cross-document edges), `avg_edge_score`, `neighborhood_density`, and `computed_at` (ISO 8601 timestamp).
3. WHEN a `RELATED_DOCS` edge already exists between two documents, THE Composite_Score_Engine SHALL overwrite the existing edge properties with the newly computed values (idempotent upsert).
4. THE Composite_Score_Engine SHALL store `RELATED_DOCS` edges bidirectionally so that queries from either document discover the relationship.

### Requirement 5: Ingestion-Time Computation Trigger

**User Story:** As a system operator, I want composite scores computed automatically at ingestion time after enrichment completes, so that document relationships are available immediately without manual intervention or query-time overhead.

#### Acceptance Criteria

1. WHEN the EnrichmentService completes both YAGO enrichment and ConceptNet enrichment for a document, THE EnrichmentService SHALL invoke the Composite_Score_Engine to compute and store composite scores for the newly ingested document against all existing documents.
2. THE Composite_Score_Engine SHALL complete computation within 2 seconds for a document with up to 200 concepts and 10 existing documents in the knowledge graph.
3. IF the Composite_Score_Engine encounters an error during computation, THEN THE EnrichmentService SHALL raise the error and fail the enrichment pipeline for that document.
4. THE Composite_Score_Engine SHALL recompute `RELATED_DOCS` edges only for document pairs involving the newly ingested document, leaving existing edges between other document pairs unchanged.

### Requirement 6: Related Documents Graph Data Retrieval

**User Story:** As a user, I want to request the full graph of related documents for a given document via WebSocket, so that the frontend can render an interactive force-directed graph showing all RELATED_DOCS connections and their composite scores.

#### Acceptance Criteria

1. WHEN the frontend sends a WebSocket message of type `related_docs_graph` with a `document_id`, THE Related_Docs_Graph_Handler SHALL query the Knowledge_Graph_Client for all `RELATED_DOCS` edges where either endpoint concept belongs to the specified document.
2. THE Related_Docs_Graph_Handler SHALL return a response containing a `nodes` array of document nodes (each with `document_id`, `title`, and `is_origin` flag) and an `edges` array of relationship edges (each with `source` document_id, `target` document_id, `score`, and `edge_count`).
3. THE Related_Docs_Graph_Handler SHALL mark exactly one node with `is_origin` set to true, and that node's `document_id` SHALL equal the requested `document_id`.
4. THE Related_Docs_Graph_Handler SHALL resolve document titles from the PostgreSQL `knowledge_sources` table for all document IDs in the response.
5. IF PostgreSQL is unavailable for title lookup, THEN THE Related_Docs_Graph_Handler SHALL use the `document_id` string as a fallback title.
6. WHEN no `RELATED_DOCS` edges exist for the specified document, THE Related_Docs_Graph_Handler SHALL return a valid response containing only the origin node and an empty `edges` array.
7. IF the Knowledge_Graph_Client is unavailable or the query fails, THEN THE Related_Docs_Graph_Handler SHALL return an error response with type `related_docs_graph_error` containing the `document_id` and a descriptive error message.
8. IF the `document_id` field is empty or missing, THEN THE Related_Docs_Graph_Handler SHALL return a `related_docs_graph_error` response with a validation error message.

### Requirement 7: Interactive Related Documents Graph Popup

**User Story:** As a user, I want to click a "Related Documents" button on a completed document and see an interactive force-directed graph of all related documents with their composite scores, so that I can visually explore document relationships and navigate between them.

#### Acceptance Criteria

1. WHEN the Document_List_Panel renders a completed document item that has a concept_count greater than zero, THE Document_List_Panel SHALL display a Related_Docs_Button to the right of the Stats toggle button.
2. WHEN the user clicks the Related_Docs_Button, THE Document_List_Panel SHALL open a Related_Docs_Graph_Popup as a floating overlay appended to `document.body`.
3. WHEN the Related_Docs_Graph_Popup is open, THE Document_List_Panel SHALL close the popup when the user clicks the close button, clicks the backdrop, presses the Escape key, or clicks the Related_Docs_Button again.
4. THE Document_List_Panel SHALL allow only one Related_Docs_Graph_Popup open at a time; opening a new popup SHALL close any previously open popup.
5. WHEN the Related_Docs_Graph_Popup opens, THE Document_List_Panel SHALL lazily load D3.js from a CDN if not already loaded, using a cached Promise to prevent duplicate script tags.
6. WHEN graph data is received, THE Document_List_Panel SHALL render a force-directed graph using D3.js with document nodes as circles and RELATED_DOCS edges as lines.
7. THE Document_List_Panel SHALL render the origin document as a Center_Node with a distinct color, and all related documents as Satellite_Nodes with a different color.
8. THE Document_List_Panel SHALL display each edge label as the composite score formatted as a percentage (e.g., "72%").
9. THE Document_List_Panel SHALL display each node label as the document title truncated to a maximum of 30 characters, appending "…" if truncated.
10. WHEN the user clicks a Satellite_Node, THE Document_List_Panel SHALL reposition that node to the center of the graph as the new Center_Node, and move the previous Center_Node to a satellite orbit position.
11. WHEN the user clicks a Satellite_Node, THE Document_List_Panel SHALL scroll the document list panel to the corresponding document item and apply a visual highlight to that item.
12. THE Related_Docs_Graph_Popup SHALL contain a Threshold_Slider (range input from 0.0 to 1.0, step 0.01, default value 0.5) that filters edges and their connected nodes in real time.
13. WHEN the user adjusts the Threshold_Slider, THE Document_List_Panel SHALL hide all edges with a composite score below the threshold value and hide all Satellite_Nodes that have no remaining visible edges.
14. THE Related_Docs_Graph_Popup SHALL always keep the Center_Node visible regardless of the Threshold_Slider value.
15. WHEN D3.js fails to load from the CDN, THE Document_List_Panel SHALL display an error message in the popup body: "Could not load visualization library. Please check your internet connection."
16. WHEN the WebSocket is disconnected at the time the Related_Docs_Button is clicked, THE Document_List_Panel SHALL display an error message in the popup: "Not connected to server."
17. THE Related_Docs_Graph_Popup title bar SHALL display the text "Related Documents: " concatenated with the origin document title.

### Requirement 8: WebSocket Message Schema for Related Documents Graph

**User Story:** As a developer, I want well-defined Pydantic models and WebSocket message schemas for the related documents graph request and response, so that the frontend and backend communicate graph data consistently.

#### Acceptance Criteria

1. THE API models module SHALL define a `RelatedDocsGraphRequest` Pydantic model with fields: `type` (literal `"related_docs_graph"`) and `document_id` (string).
2. THE API models module SHALL define a `RelatedDocsGraphNode` Pydantic model with fields: `document_id` (string), `title` (string), and `is_origin` (boolean, default false).
3. THE API models module SHALL define a `RelatedDocsGraphEdge` Pydantic model with fields: `source` (string), `target` (string), `score` (float between 0.0 and 1.0), and `edge_count` (integer, non-negative).
4. THE API models module SHALL define a `RelatedDocsGraphResponse` Pydantic model with fields: `type` (literal `"related_docs_graph"`), `document_id` (string), `nodes` (list of `RelatedDocsGraphNode`), and `edges` (list of `RelatedDocsGraphEdge`).
5. THE API models module SHALL define a `RelatedDocsGraphError` Pydantic model with fields: `type` (literal `"related_docs_graph_error"`), `document_id` (string), and `message` (string).
6. FOR ALL valid `RelatedDocsGraphResponse` payloads, every `source` and `target` in the `edges` list SHALL reference a `document_id` that exists in the `nodes` list.
