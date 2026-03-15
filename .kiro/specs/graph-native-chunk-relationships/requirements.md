# Requirements Document

## Introduction

Refactor the Neo4j knowledge graph schema to replace property-based storage of chunk references (`source_chunks` comma-delimited string and `source_document` property on Concept nodes) with graph-native `Chunk` nodes and `EXTRACTED_FROM` relationships. The current approach stores chunk IDs as a comma-separated string on each Concept node, which is fragile, unindexable, cannot represent multiple source documents cleanly, and will hit Neo4j property size limits at scale. The target model uses first-class `Chunk` nodes linked to Concepts via `EXTRACTED_FROM` relationships, making chunk provenance a traversable, indexable part of the graph.

## Glossary

- **Concept**: A Neo4j node with label `Concept` representing an extracted knowledge concept (entity, process, property, etc.)
- **Chunk**: A new Neo4j node with label `Chunk` representing a content chunk from a document or conversation thread, identified by `chunk_id` and associated with a `source_id`
- **EXTRACTED_FROM**: A new Neo4j relationship type connecting a Concept node to the Chunk node it was extracted from, replacing the `source_chunks` property
- **ConceptNode**: The Python dataclass in `models/knowledge_graph.py` representing a Concept in application code
- **KG_Builder**: The `KnowledgeGraphBuilder` class responsible for extracting concepts from content and persisting them to Neo4j
- **KG_Query_Engine**: The `KnowledgeGraphQueryEngine` class responsible for querying the knowledge graph for neighborhoods, landing views, and concept search
- **KG_Retrieval_Service**: The `KGRetrievalService` class that retrieves chunk IDs from concept `source_chunks` for RAG-guided retrieval
- **Enrichment_Service**: The service that batch-persists concepts to Neo4j during document processing enrichment
- **Celery_Service**: The async task service that orchestrates document processing including concept extraction and Neo4j persistence
- **Conversation_Knowledge_Service**: The service that converts conversation threads into knowledge graph concepts and persists them to Neo4j
- **Privacy_Service**: The service responsible for GDPR-compliant deletion of knowledge graph data when documents are removed
- **Composite_Score_Engine**: The service that computes cross-document relatedness scores using concept counts per document
- **Chat_Document_Handlers**: The API router that queries Neo4j for per-document concept and relationship counts for the document info panel
- **Source_ID**: The document ID or conversation thread ID that a chunk belongs to

## Requirements

### Requirement 1: Chunk Node Schema

**User Story:** As a system operator, I want chunks represented as first-class graph nodes, so that chunk provenance is traversable and indexable in Neo4j.

#### Acceptance Criteria

1. THE KG_Builder SHALL create `Chunk` nodes in Neo4j with properties `chunk_id` (unique string) and `source_id` (string referencing the document or thread ID)
2. WHEN a Chunk node is created, THE KG_Builder SHALL use MERGE on `chunk_id` to prevent duplicate Chunk nodes for the same chunk
3. THE KG_Builder SHALL create a Neo4j uniqueness constraint on `Chunk.chunk_id`
4. THE KG_Builder SHALL create a Neo4j index on `Chunk.source_id` for efficient per-document lookups

### Requirement 2: EXTRACTED_FROM Relationship Schema

**User Story:** As a system operator, I want concept-to-chunk provenance stored as graph relationships, so that I can traverse and query provenance without string parsing.

#### Acceptance Criteria

1. WHEN a Concept is extracted from a Chunk, THE KG_Builder SHALL create an `EXTRACTED_FROM` relationship from the Concept node to the Chunk node
2. THE KG_Builder SHALL use MERGE on the `(Concept)-[:EXTRACTED_FROM]->(Chunk)` pattern to prevent duplicate relationships for the same concept-chunk pair
3. THE KG_Builder SHALL store a `created_at` timestamp property on each EXTRACTED_FROM relationship

### Requirement 3: Remove Property-Based Chunk Storage

**User Story:** As a developer, I want the `source_chunks` and `source_document` properties removed from Concept nodes, so that there is a single source of truth for chunk provenance.

#### Acceptance Criteria

1. THE ConceptNode dataclass SHALL replace the `source_chunks: List[str]` field with a method that retrieves chunk IDs via graph traversal
2. THE ConceptNode dataclass SHALL remove the `source_document: Optional[str]` field, since source documents are derivable from `(Concept)-[:EXTRACTED_FROM]->(Chunk {source_id})` traversal
3. THE KG_Builder SHALL stop writing `source_chunks` and `source_document` properties to Concept nodes in all MERGE and SET Cypher queries
4. THE Celery_Service SHALL stop writing `source_chunks` and `source_document` properties in its batch concept MERGE queries
5. THE Conversation_Knowledge_Service SHALL stop writing `source_chunks` and `source_document` properties in its concept persistence queries
6. THE Enrichment_Service SHALL stop writing `source_chunks` and `source_document` properties in its batch concept MERGE queries

### Requirement 4: Document Processing Pipeline Update

**User Story:** As a developer, I want the document processing pipeline to create Chunk nodes and EXTRACTED_FROM relationships during concept extraction, so that new documents use the graph-native schema.

#### Acceptance Criteria

1. WHEN the Celery_Service processes a document, THE Celery_Service SHALL create Chunk nodes for each content chunk before persisting concepts
2. WHEN the Celery_Service persists concepts to Neo4j, THE Celery_Service SHALL create EXTRACTED_FROM relationships from each Concept to its source Chunk nodes instead of appending to a `source_chunks` string property
3. WHEN the Celery_Service encounters an existing Concept during MERGE, THE Celery_Service SHALL create additional EXTRACTED_FROM relationships to new Chunk nodes without affecting existing relationships

### Requirement 5: Conversation Knowledge Pipeline Update

**User Story:** As a developer, I want the conversation knowledge pipeline to use graph-native chunk relationships, so that conversation-sourced concepts follow the same schema as document-sourced concepts.

#### Acceptance Criteria

1. WHEN the Conversation_Knowledge_Service converts a conversation thread, THE Conversation_Knowledge_Service SHALL create Chunk nodes for each conversation chunk with `source_id` set to the thread ID
2. WHEN the Conversation_Knowledge_Service persists concepts, THE Conversation_Knowledge_Service SHALL create EXTRACTED_FROM relationships from Concepts to their source Chunk nodes
3. WHEN the Conversation_Knowledge_Service cleans up a conversation thread's knowledge, THE Conversation_Knowledge_Service SHALL delete EXTRACTED_FROM relationships and orphaned Chunk nodes for that thread

### Requirement 6: KG Retrieval Service Update

**User Story:** As a developer, I want the KG retrieval service to resolve chunk IDs via graph traversal instead of parsing comma-delimited strings, so that retrieval is reliable and performant.

#### Acceptance Criteria

1. WHEN the KG_Retrieval_Service retrieves direct chunks for a matched concept, THE KG_Retrieval_Service SHALL use a Cypher traversal `MATCH (c:Concept {concept_id: $id})-[:EXTRACTED_FROM]->(ch:Chunk) RETURN ch.chunk_id` instead of parsing a `source_chunks` string property
2. WHEN the KG_Retrieval_Service traverses relationships to find related chunks, THE KG_Retrieval_Service SHALL collect chunk IDs from related concepts via EXTRACTED_FROM traversal
3. THE KG_Retrieval_Service SHALL remove the `_parse_source_chunks` method and all comma-delimited string parsing logic
4. THE KG_Retrieval_Service SHALL update its cache to store chunk IDs resolved from graph traversal instead of parsed strings

### Requirement 7: Stats and Count Queries Update

**User Story:** As a user viewing document details, I want accurate concept and relationship counts per document, so that the document info panel shows correct statistics.

#### Acceptance Criteria

1. WHEN the Chat_Document_Handlers queries concept count for a document, THE Chat_Document_Handlers SHALL use `MATCH (ch:Chunk {source_id: $doc_id})<-[:EXTRACTED_FROM]-(c:Concept) RETURN count(DISTINCT c)` instead of `MATCH (c:Concept {source_document: $doc_id}) RETURN count(c)`
2. WHEN the Chat_Document_Handlers queries relationship counts for a document, THE Chat_Document_Handlers SHALL use `MATCH (ch:Chunk {source_id: $doc_id})<-[:EXTRACTED_FROM]-(c:Concept)-[r]->() RETURN type(r), count(r)` instead of filtering by `c.source_document`
3. WHEN the Composite_Score_Engine queries concept counts per document, THE Composite_Score_Engine SHALL use Chunk-based traversal to count distinct concepts per source_id

### Requirement 8: KG Explorer Queries Update

**User Story:** As a user exploring the knowledge graph, I want the landing view and ego graph to work with the new schema, so that the KG explorer continues to show correct per-document concept neighborhoods.

#### Acceptance Criteria

1. WHEN the KG_Query_Engine returns the landing view for a source, THE KG_Query_Engine SHALL find concepts via `MATCH (ch:Chunk {source_id: $source_id})<-[:EXTRACTED_FROM]-(c:Concept)` instead of `MATCH (c:Concept {source_document: $source_id})`
2. WHEN the KG_Query_Engine returns the ego graph, THE KG_Query_Engine SHALL derive `source_document` for each node from its EXTRACTED_FROM relationships to Chunk nodes
3. WHEN the KG_Query_Engine searches concepts by embedding with a source_id filter, THE KG_Query_Engine SHALL filter via Chunk traversal instead of the `source_document` property

### Requirement 9: Document Deletion and Cleanup

**User Story:** As a system operator, I want document deletion to cleanly remove chunk nodes and EXTRACTED_FROM relationships, so that no orphaned graph data remains after a document is deleted.

#### Acceptance Criteria

1. WHEN the Privacy_Service deletes knowledge graph data for a source, THE Privacy_Service SHALL delete all EXTRACTED_FROM relationships pointing to Chunk nodes with the matching `source_id`
2. WHEN the Privacy_Service deletes knowledge graph data for a source, THE Privacy_Service SHALL delete all Chunk nodes with the matching `source_id`
3. WHEN the Privacy_Service deletes knowledge graph data for a source, THE Privacy_Service SHALL delete Concept nodes that have zero remaining EXTRACTED_FROM relationships after the source's chunks are removed (orphan cleanup)
4. IF a Concept node still has EXTRACTED_FROM relationships to Chunk nodes from other sources after deletion, THEN THE Privacy_Service SHALL retain that Concept node

### Requirement 10: Cross-Document Linking Compatibility

**User Story:** As a developer, I want cross-document SAME_AS linking to continue working with the new schema, so that concepts shared across documents remain discoverable.

#### Acceptance Criteria

1. WHEN the Knowledge_Graph_Service queries cross-document links via SAME_AS relationships, THE Knowledge_Graph_Service SHALL derive document IDs from EXTRACTED_FROM traversal to Chunk nodes instead of reading `source_document` properties
2. WHEN the Enrichment_Service creates SAME_AS relationships between concepts sharing a YAGO Q-number, THE Enrichment_Service SHALL identify cross-document matches by comparing Chunk `source_id` values instead of Concept `source_document` properties

### Requirement 11: In-Memory Model Compatibility

**User Story:** As a developer, I want the in-memory ConceptNode model to support both graph-native chunk references and backward-compatible serialization, so that non-Neo4j code paths continue to work during the transition.

#### Acceptance Criteria

1. THE ConceptNode dataclass SHALL retain a `source_chunks: List[str]` field for in-memory use during extraction pipelines (before Neo4j persistence)
2. THE ConceptNode `to_dict` method SHALL include `source_chunks` for serialization to non-Neo4j consumers
3. WHEN persisting to Neo4j, THE KG_Builder SHALL translate `ConceptNode.source_chunks` into EXTRACTED_FROM relationships and Chunk nodes instead of writing the list as a property
4. THE ConceptNode `add_source_chunk` method SHALL continue to work for in-memory accumulation during extraction
