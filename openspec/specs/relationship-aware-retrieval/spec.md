## Purpose

This feature adds relationship-aware retrieval to the KG-guided retrieval pipeline. Currently, when a user queries for a clinical scenario involving multiple concepts (e.g., "What is the diagnosis for fever, productive cough, and right lower lobe crackles?"), the system matches individual concepts in Neo4j and retrieves all chunks linked via EXTRACTED_FROM edges. This returns irrelevant chunks because it ignores the relationships between concepts already stored in the knowledge graph (e.g., `(pneumococcus)-[:CAUSES]->(pneumonia)`, `(pneumonia)-[:PRESENTS_WITH]->(fever)`).

The solution introduces an additive relationship-traversal layer that activates when the query decomposer detects multiple medical/scientific concepts. It uses inter-concept relationship paths to boost chunks that sit at the intersection of clinically connected concepts, improving precision without breaking existing general-purpose retrieval.


### Key Terms
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

### Requirement: Multi-Concept Query Detection

The system SHALL support: As a user querying with multiple medical concepts, I want the system to detect that my query involves interconnected concepts, so that it can activate relationship-aware retrieval for more precise results.

#### Scenario: WHEN the Query_Decomposer returns two or more distinct Conce

- **THEN** WHEN the Query_Decomposer returns two or more distinct Concept matches for a query, THE KG_Retrieval_Service SHALL classify the query as a Multi_Concept_Query.

#### Scenario: WHEN the Query_Decomposer returns fewer than two Concept mat

- **THEN** WHEN the Query_Decomposer returns fewer than two Concept matches, THE KG_Retrieval_Service SHALL use Fallback_Mode without relationship traversal.

#### Scenario: THE KG_Retrieval_Service SHALL determine Multi_Concept_Query

- **THEN** THE KG_Retrieval_Service SHALL determine Multi_Concept_Query status using only the existing Query_Decomposer output without requiring additional LLM calls or external service requests.

#### Scenario: WHEN a query is classified as a Multi_Concept_Query, THE KG_

- **THEN** WHEN a query is classified as a Multi_Concept_Query, THE KG_Retrieval_Service SHALL record the classification in the retrieval metadata returned with the KGRetrievalResult.

### Requirement: Relationship Path Traversal

The system SHALL support: As a user asking about connected medical concepts, I want the system to traverse relationships between my query concepts in the knowledge graph, so that it finds chunks where those concepts are discussed in a connected context.

#### Scenario: WHEN a Multi_Concept_Query is detected, THE Relationship_Tra

- **THEN** WHEN a Multi_Concept_Query is detected, THE Relationship_Traverser SHALL execute a Cypher query that finds paths between pairs of matched Concept nodes using Clinically_Relevant_Relationships.

#### Scenario: THE Relationship_Traverser SHALL limit path traversal to a m

- **THEN** THE Relationship_Traverser SHALL limit path traversal to a maximum of 2 hops (Hop_Limit) between any two query concepts.

#### Scenario: THE Relationship_Traverser SHALL collect chunk IDs linked vi

- **THEN** THE Relationship_Traverser SHALL collect chunk IDs linked via EXTRACTED_FROM edges to concepts found along the traversed Relationship_Paths.

#### Scenario: WHEN no Relationship_Paths exist between any pair of query c

- **THEN** WHEN no Relationship_Paths exist between any pair of query concepts, THE Relationship_Traverser SHALL return an empty result set and the KG_Retrieval_Service SHALL proceed with Fallback_Mode results only.

#### Scenario: THE Relationship_Traverser SHALL filter traversal to use onl

- **THEN** THE Relationship_Traverser SHALL filter traversal to use only Clinically_Relevant_Relationships (CAUSES, PRESENTS_WITH, TREATED_BY, TREATS, IS_A, PART_OF, Causes, IsA, PartOf, RelatedTo, and their equivalents from PRIORITY_RELATIONSHIP_TYPES).

### Requirement: Intersection Chunk Identification

The system SHALL support: As a user, I want chunks that discuss multiple connected query concepts to be prioritized, so that I get the most contextually relevant results rather than chunks that mention a single concept in an unrelated context.

#### Scenario: WHEN relationship traversal returns chunk IDs, THE KG_Retrie

- **THEN** WHEN relationship traversal returns chunk IDs, THE KG_Retrieval_Service SHALL identify Intersection_Chunks as chunks reachable from two or more query concepts via Relationship_Paths.

#### Scenario: THE KG_Retrieval_Service SHALL track the number of distinct

- **THEN** THE KG_Retrieval_Service SHALL track the number of distinct query concepts that connect to each chunk via Relationship_Paths.

#### Scenario: WHEN a chunk is reachable from only one query concept via re

- **THEN** WHEN a chunk is reachable from only one query concept via relationship traversal, THE KG_Retrieval_Service SHALL treat the chunk as a standard related chunk without applying Relationship_Boost.

### Requirement: Relationship Boost Scoring

The system SHALL support: As a user, I want relationship-connected chunks to rank higher than incidentally matched chunks, so that the most clinically relevant documents appear first in my results.

#### Scenario: THE KG_Retrieval_Service SHALL apply a Relationship_Boost to

- **THEN** THE KG_Retrieval_Service SHALL apply a Relationship_Boost to the kg_relevance_score of each Intersection_Chunk before semantic re-ranking.

#### Scenario: THE Relationship_Boost SHALL be configurable via application

- **THEN** THE Relationship_Boost SHALL be configurable via application settings with a default value of 1.

#### Scenario: 

- **THEN** 

#### Scenario: THE KG_Retrieval_Service SHALL scale the Relationship_Boost

- **THEN** THE KG_Retrieval_Service SHALL scale the Relationship_Boost proportionally to the number of distinct query concepts connected to the chunk (e.g., a chunk connected to 3 query concepts receives a higher boost than one connected to 2).

#### Scenario: THE KG_Retrieval_Service SHALL cap the boosted kg_relevance_

- **THEN** THE KG_Retrieval_Service SHALL cap the boosted kg_relevance_score at 1.0 to maintain compatibility with the Semantic_Reranker geometric mean formula.

#### Scenario: WHEN the Relationship_Boost is set to 1.0, THE KG_Retrieval_

- **THEN** WHEN the Relationship_Boost is set to 1.0, THE KG_Retrieval_Service SHALL produce results identical to Fallback_Mode, effectively disabling relationship-aware scoring.

### Requirement: Preservation of Existing Retrieval

The system SHALL support: As a user making general-purpose queries unrelated to medical concepts, I want the system to continue returning accurate results using the existing retrieval path, so that relationship-aware retrieval does not degrade non-medical queries.

#### Scenario: WHEN a query is not classified as a Multi_Concept_Query, THE

- **THEN** WHEN a query is not classified as a Multi_Concept_Query, THE KG_Retrieval_Service SHALL execute the existing concept-to-chunk retrieval pipeline without modification.

#### Scenario: THE KG_Retrieval_Service SHALL preserve the existing EXTRACT

- **THEN** THE KG_Retrieval_Service SHALL preserve the existing EXTRACTED_FROM traversal, concept-coverage scoring, and semantic re-ranking pipeline as the Fallback_Mode.

#### Scenario: WHEN relationship traversal returns no Intersection_Chunks f

- **THEN** WHEN relationship traversal returns no Intersection_Chunks for a Multi_Concept_Query, THE KG_Retrieval_Service SHALL return results from Fallback_Mode without degradation.

#### Scenario: THE KG_Retrieval_Service SHALL not modify the Semantic_Reran

- **THEN** THE KG_Retrieval_Service SHALL not modify the Semantic_Reranker geometric mean formula (kg_score^0.7 × semantic_score^0.3) or its weight parameters.

### Requirement: Latency Constraints

The system SHALL support: As a user, I want relationship-aware retrieval to respond within acceptable time limits, so that the added precision does not come at the cost of noticeable delays.

#### Scenario: THE Relationship_Traverser SHALL enforce a configurable time

- **THEN** THE Relationship_Traverser SHALL enforce a configurable timeout on relationship traversal Cypher queries with a default of 3 seconds.

#### Scenario: IF the relationship traversal Cypher query exceeds the confi

- **GIVEN** the relationship traversal Cypher query exceeds the configured timeout
- **THEN** IF the relationship traversal Cypher query exceeds the configured timeout, THEN THE KG_Retrieval_Service SHALL cancel the traversal and proceed with Fallback_Mode results only.

#### Scenario: THE Relationship_Traverser SHALL bound the number of relatio

- **THEN** THE Relationship_Traverser SHALL bound the number of relationship paths explored per concept pair to a configurable maximum with a default of 50 paths.

#### Scenario: THE KG_Retrieval_Service SHALL log the relationship traversa

- **THEN** THE KG_Retrieval_Service SHALL log the relationship traversal duration in the retrieval metadata for performance monitoring.

### Requirement: Configuration Management

The system SHALL support: As a system administrator, I want to configure relationship-aware retrieval parameters, so that I can tune the feature for different deployment environments and document corpora.

#### Scenario: THE KG_Retrieval_Service SHALL expose the following configur

- **THEN** THE KG_Retrieval_Service SHALL expose the following configurable parameters via application settings: Relationship_Boost default value, Hop_Limit, relationship traversal timeout, and maximum paths per concept pair.

#### Scenario: THE KG_Retrieval_Service SHALL use Pydantic Settings for all

- **THEN** THE KG_Retrieval_Service SHALL use Pydantic Settings for all relationship-aware retrieval configuration parameters, consistent with the existing configuration pattern.

#### Scenario: WHEN a configuration parameter is not explicitly set, THE KG

- **THEN** WHEN a configuration parameter is not explicitly set, THE KG_Retrieval_Service SHALL use the documented default values (Relationship_Boost: 1.5, Hop_Limit: 2, timeout: 3 seconds, max paths: 50).

### Requirement: Observability and Diagnostics

The system SHALL support: As a developer, I want visibility into how relationship-aware retrieval affects results, so that I can diagnose issues and tune the system.

#### Scenario: THE KG_Retrieval_Service SHALL include the following fields

- **THEN** THE KG_Retrieval_Service SHALL include the following fields in the KGRetrievalResult metadata: whether relationship-aware mode was activated, the number of Intersection_Chunks found, the number of Relationship_Paths traversed, and the relationship traversal duration in milliseconds.

#### Scenario: THE KG_Retrieval_Service SHALL log at DEBUG level the Relati

- **THEN** THE KG_Retrieval_Service SHALL log at DEBUG level the Relationship_Paths found between query concept pairs, including relationship types and intermediate concepts.

#### Scenario: IF relationship traversal fails with an exception, THEN THE

- **GIVEN** relationship traversal fails with an exception
- **THEN** IF relationship traversal fails with an exception, THEN THE KG_Retrieval_Service SHALL log the error at WARNING level and proceed with Fallback_Mode without raising the exception to the caller.

#### Scenario: THE KG_Retrieval_Service SHALL include the Relationship_Boos

- **THEN** THE KG_Retrieval_Service SHALL include the Relationship_Boost value applied to each Intersection_Chunk in the chunk's metadata for downstream inspection.

### Requirement: No Document Reprocessing

The system SHALL support: As a system operator, I want relationship-aware retrieval to work with the existing knowledge graph data, so that I do not need to reprocess documents or rebuild the graph.

#### Scenario: THE Relationship_Traverser SHALL use only relationship edges

- **THEN** THE Relationship_Traverser SHALL use only relationship edges and EXTRACTED_FROM edges that already exist in the Neo4j knowledge graph.

#### Scenario: THE Relationship_Traverser SHALL not create, modify, or dele

- **THEN** THE Relationship_Traverser SHALL not create, modify, or delete any nodes or edges in the Neo4j knowledge graph.

#### Scenario: THE KG_Retrieval_Service SHALL not require any schema change

- **THEN** THE KG_Retrieval_Service SHALL not require any schema changes, index additions, or data migrations to the Neo4j database for relationship-aware retrieval to function.
