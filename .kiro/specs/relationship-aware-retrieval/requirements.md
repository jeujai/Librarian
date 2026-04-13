# Requirements Document

## Introduction

This feature adds relationship-aware retrieval to the KG-guided retrieval pipeline. Currently, when a user queries for a clinical scenario involving multiple concepts (e.g., "What is the diagnosis for fever, productive cough, and right lower lobe crackles?"), the system matches individual concepts in Neo4j and retrieves all chunks linked via EXTRACTED_FROM edges. This returns irrelevant chunks because it ignores the relationships between concepts already stored in the knowledge graph (e.g., `(pneumococcus)-[:CAUSES]->(pneumonia)`, `(pneumonia)-[:PRESENTS_WITH]->(fever)`).

The solution introduces an additive relationship-traversal layer that activates when the query decomposer detects multiple medical/scientific concepts. It uses inter-concept relationship paths to boost chunks that sit at the intersection of clinically connected concepts, improving precision without breaking existing general-purpose retrieval.

## Glossary

- **KG_Retrieval_Service**: The orchestration service (`kg_retrieval_service.py`) that coordinates the two-stage retrieval pipeline (KG-based candidate retrieval followed by semantic re-ranking).
- **Query_Decomposer**: The component (`query_decomposer.py`) that decomposes user queries into entities, actions, and subject references by matching against Neo4j concept names.
- **Semantic_Reranker**: The component (`semantic_reranker.py`) that re-ranks candidate chunks using a weighted geometric mean of KG relevance and semantic similarity scores.
- **Relationship_Traverser**: The new component responsible for executing bounded Cypher queries that traverse inter-concept relationships (CAUSES, PRESENTS_WITH, TREATED_BY, etc.) to find chunks at the intersection of connected query concepts.
- **Concept**: A named entity node in the Neo4j knowledge graph, linked to document chunks via EXTRACTED_FROM edges and to other concepts via typed relationship edges.
- **Relationship_Path**: A sequence of typed edges connecting two or more Concept nodes in Neo4j (e.g., `(fever)-[:PRESENTS_WITH]->(pneumonia)-[:CAUSED_BY]->(pneumococcus)`).
- **Intersection_Chunk**: A document chunk that is reachable from two or more query concepts via relationship traversal, indicating the chunk discusses those concepts in a connected clinical or scientific context.
- **Relationship_Boost**: A configurable score multiplier applied to Intersection_Chunks during aggregation, increasing their ranking relative to chunks matched by a single concept alone.
- **Multi_Concept_Query**: A query where the Query_Decomposer detects two or more distinct Concept matches that could be connected by domain-specific relationships.
- **Fallback_Mode**: The existing concept-to-chunk retrieval path that operates without relationship awareness, preserved as the default for single-concept queries and as a safety net when relationship traversal yields no results.
- **Hop_Limit**: The maximum number of relationship edges traversed between any two query concepts (bounded to 1-2 hops to control latency).
- **Clinically_Relevant_Relationships**: The subset of relationship types in Neo4j that carry domain-specific meaning for medical/scientific queries: CAUSES, PRESENTS_WITH, TREATED_BY, TREATS, IS_A, PART_OF, and their ConceptNet equivalents.

## Requirements

### Requirement 1: Multi-Concept Query Detection

**User Story:** As a user querying with multiple medical concepts, I want the system to detect that my query involves interconnected concepts, so that it can activate relationship-aware retrieval for more precise results.

#### Acceptance Criteria

1. WHEN the Query_Decomposer returns two or more distinct Concept matches for a query, THE KG_Retrieval_Service SHALL classify the query as a Multi_Concept_Query.
2. WHEN the Query_Decomposer returns fewer than two Concept matches, THE KG_Retrieval_Service SHALL use Fallback_Mode without relationship traversal.
3. THE KG_Retrieval_Service SHALL determine Multi_Concept_Query status using only the existing Query_Decomposer output without requiring additional LLM calls or external service requests.
4. WHEN a query is classified as a Multi_Concept_Query, THE KG_Retrieval_Service SHALL record the classification in the retrieval metadata returned with the KGRetrievalResult.

### Requirement 2: Relationship Path Traversal

**User Story:** As a user asking about connected medical concepts, I want the system to traverse relationships between my query concepts in the knowledge graph, so that it finds chunks where those concepts are discussed in a connected context.

#### Acceptance Criteria

1. WHEN a Multi_Concept_Query is detected, THE Relationship_Traverser SHALL execute a Cypher query that finds paths between pairs of matched Concept nodes using Clinically_Relevant_Relationships.
2. THE Relationship_Traverser SHALL limit path traversal to a maximum of 2 hops (Hop_Limit) between any two query concepts.
3. THE Relationship_Traverser SHALL collect chunk IDs linked via EXTRACTED_FROM edges to concepts found along the traversed Relationship_Paths.
4. WHEN no Relationship_Paths exist between any pair of query concepts, THE Relationship_Traverser SHALL return an empty result set and the KG_Retrieval_Service SHALL proceed with Fallback_Mode results only.
5. THE Relationship_Traverser SHALL filter traversal to use only Clinically_Relevant_Relationships (CAUSES, PRESENTS_WITH, TREATED_BY, TREATS, IS_A, PART_OF, Causes, IsA, PartOf, RelatedTo, and their equivalents from PRIORITY_RELATIONSHIP_TYPES).

### Requirement 3: Intersection Chunk Identification

**User Story:** As a user, I want chunks that discuss multiple connected query concepts to be prioritized, so that I get the most contextually relevant results rather than chunks that mention a single concept in an unrelated context.

#### Acceptance Criteria

1. WHEN relationship traversal returns chunk IDs, THE KG_Retrieval_Service SHALL identify Intersection_Chunks as chunks reachable from two or more query concepts via Relationship_Paths.
2. THE KG_Retrieval_Service SHALL track the number of distinct query concepts that connect to each chunk via Relationship_Paths.
3. WHEN a chunk is reachable from only one query concept via relationship traversal, THE KG_Retrieval_Service SHALL treat the chunk as a standard related chunk without applying Relationship_Boost.

### Requirement 4: Relationship Boost Scoring

**User Story:** As a user, I want relationship-connected chunks to rank higher than incidentally matched chunks, so that the most clinically relevant documents appear first in my results.

#### Acceptance Criteria

1. THE KG_Retrieval_Service SHALL apply a Relationship_Boost to the kg_relevance_score of each Intersection_Chunk before semantic re-ranking.
2. THE Relationship_Boost SHALL be configurable via application settings with a default value of 1.5.
3. THE KG_Retrieval_Service SHALL scale the Relationship_Boost proportionally to the number of distinct query concepts connected to the chunk (e.g., a chunk connected to 3 query concepts receives a higher boost than one connected to 2).
4. THE KG_Retrieval_Service SHALL cap the boosted kg_relevance_score at 1.0 to maintain compatibility with the Semantic_Reranker geometric mean formula.
5. WHEN the Relationship_Boost is set to 1.0, THE KG_Retrieval_Service SHALL produce results identical to Fallback_Mode, effectively disabling relationship-aware scoring.

### Requirement 5: Preservation of Existing Retrieval

**User Story:** As a user making general-purpose queries unrelated to medical concepts, I want the system to continue returning accurate results using the existing retrieval path, so that relationship-aware retrieval does not degrade non-medical queries.

#### Acceptance Criteria

1. WHEN a query is not classified as a Multi_Concept_Query, THE KG_Retrieval_Service SHALL execute the existing concept-to-chunk retrieval pipeline without modification.
2. THE KG_Retrieval_Service SHALL preserve the existing EXTRACTED_FROM traversal, concept-coverage scoring, and semantic re-ranking pipeline as the Fallback_Mode.
3. WHEN relationship traversal returns no Intersection_Chunks for a Multi_Concept_Query, THE KG_Retrieval_Service SHALL return results from Fallback_Mode without degradation.
4. THE KG_Retrieval_Service SHALL not modify the Semantic_Reranker geometric mean formula (kg_score^0.7 × semantic_score^0.3) or its weight parameters.

### Requirement 6: Latency Constraints

**User Story:** As a user, I want relationship-aware retrieval to respond within acceptable time limits, so that the added precision does not come at the cost of noticeable delays.

#### Acceptance Criteria

1. THE Relationship_Traverser SHALL enforce a configurable timeout on relationship traversal Cypher queries with a default of 3 seconds.
2. IF the relationship traversal Cypher query exceeds the configured timeout, THEN THE KG_Retrieval_Service SHALL cancel the traversal and proceed with Fallback_Mode results only.
3. THE Relationship_Traverser SHALL bound the number of relationship paths explored per concept pair to a configurable maximum with a default of 50 paths.
4. THE KG_Retrieval_Service SHALL log the relationship traversal duration in the retrieval metadata for performance monitoring.

### Requirement 7: Configuration Management

**User Story:** As a system administrator, I want to configure relationship-aware retrieval parameters, so that I can tune the feature for different deployment environments and document corpora.

#### Acceptance Criteria

1. THE KG_Retrieval_Service SHALL expose the following configurable parameters via application settings: Relationship_Boost default value, Hop_Limit, relationship traversal timeout, and maximum paths per concept pair.
2. THE KG_Retrieval_Service SHALL use Pydantic Settings for all relationship-aware retrieval configuration parameters, consistent with the existing configuration pattern.
3. WHEN a configuration parameter is not explicitly set, THE KG_Retrieval_Service SHALL use the documented default values (Relationship_Boost: 1.5, Hop_Limit: 2, timeout: 3 seconds, max paths: 50).

### Requirement 8: Observability and Diagnostics

**User Story:** As a developer, I want visibility into how relationship-aware retrieval affects results, so that I can diagnose issues and tune the system.

#### Acceptance Criteria

1. THE KG_Retrieval_Service SHALL include the following fields in the KGRetrievalResult metadata: whether relationship-aware mode was activated, the number of Intersection_Chunks found, the number of Relationship_Paths traversed, and the relationship traversal duration in milliseconds.
2. THE KG_Retrieval_Service SHALL log at DEBUG level the Relationship_Paths found between query concept pairs, including relationship types and intermediate concepts.
3. IF relationship traversal fails with an exception, THEN THE KG_Retrieval_Service SHALL log the error at WARNING level and proceed with Fallback_Mode without raising the exception to the caller.
4. THE KG_Retrieval_Service SHALL include the Relationship_Boost value applied to each Intersection_Chunk in the chunk's metadata for downstream inspection.

### Requirement 9: No Document Reprocessing

**User Story:** As a system operator, I want relationship-aware retrieval to work with the existing knowledge graph data, so that I do not need to reprocess documents or rebuild the graph.

#### Acceptance Criteria

1. THE Relationship_Traverser SHALL use only relationship edges and EXTRACTED_FROM edges that already exist in the Neo4j knowledge graph.
2. THE Relationship_Traverser SHALL not create, modify, or delete any nodes or edges in the Neo4j knowledge graph.
3. THE KG_Retrieval_Service SHALL not require any schema changes, index additions, or data migrations to the Neo4j database for relationship-aware retrieval to function.
