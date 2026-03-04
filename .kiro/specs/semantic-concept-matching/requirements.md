# Requirements Document

## Introduction

The current QueryDecomposer in the KG retrieval pipeline uses pure lexical matching (full-text index and CONTAINS queries) to find Concept nodes in Neo4j. This approach fails when user queries have no direct string overlap with stored concept names — for example, "What is allow_dangerous_code=True used for?" finds nothing because no concept name contains that exact token. With 19k+ concepts and 250k+ relationships, the knowledge graph is rich but underutilized due to brittle matching.

This feature adds semantic similarity matching to concept lookup. During document processing, embedding vectors are computed for each Concept node and stored in Neo4j. At query time, the user query is embedded and a vector similarity search finds the nearest concepts, which are then merged with existing lexical matches and fed into the KG retrieval pipeline. The knowledge graph will be rebuilt from scratch with embeddings included from the start.

## Glossary

- **Concept_Node**: A node in the Neo4j knowledge graph with label `Concept`, containing properties like `concept_id`, `name`, `type`, `confidence`, `source_document`, and `source_chunks`.
- **Embedding_Vector**: A 384-dimensional float array produced by the `all-MiniLM-L6-v2` model via the model server, representing the semantic meaning of a text.
- **Vector_Index**: A Neo4j vector index created via `db.index.vector.createNodeIndex` that enables approximate nearest-neighbor search on Embedding_Vectors stored as node properties.
- **QueryDecomposer**: The component responsible for decomposing user queries into entities, actions, and subjects by finding matching Concept_Nodes in Neo4j.
- **Model_Server_Client**: The async HTTP client that communicates with the model server at `http://model-server:8001` to generate Embedding_Vectors.
- **Similarity_Score**: A float between 0.0 and 1.0 representing cosine similarity between two Embedding_Vectors.
- **Similarity_Threshold**: A configurable minimum Similarity_Score (default 0.7) below which concept matches are discarded.
- **KG_Builder**: The component (`KnowledgeGraphBuilder` / `ConceptExtractor`) that extracts concepts from document chunks during processing.
- **Neo4j_Client**: The async client wrapper around the Neo4j Python driver that executes Cypher queries and manages connections.

## Requirements

### Requirement 1: Concept Embedding Storage

**User Story:** As a system operator, I want embedding vectors computed and stored on Concept_Nodes during document processing, so that semantic similarity search is available at query time.

#### Acceptance Criteria

1. WHEN the KG_Builder creates a new Concept_Node, THE KG_Builder SHALL compute an Embedding_Vector for the concept name using the Model_Server_Client and store it as a property named `embedding` on the Concept_Node.
2. WHEN the Model_Server_Client is unavailable during concept creation, THE KG_Builder SHALL create the Concept_Node without an `embedding` property and log a warning.
3. WHEN multiple Concept_Nodes are created in a single processing batch, THE KG_Builder SHALL batch embedding requests to the Model_Server_Client to minimize round trips.
4. THE Neo4j_Client SHALL create a Vector_Index named `concept_embedding_index` on the `Concept` label for the `embedding` property with 384 dimensions and cosine similarity during index initialization.

### Requirement 2: Semantic Concept Matching at Query Time

**User Story:** As a user, I want my queries to find relevant concepts even when my wording differs from concept names, so that I get useful knowledge graph results regardless of exact terminology.

#### Acceptance Criteria

1. WHEN a user query is received, THE QueryDecomposer SHALL embed the query using the Model_Server_Client and perform a vector similarity search against the Vector_Index to find semantically similar Concept_Nodes.
2. THE QueryDecomposer SHALL discard semantic matches with a Similarity_Score below the configured Similarity_Threshold.
3. WHEN both lexical and semantic matches are found, THE QueryDecomposer SHALL merge the results, removing duplicates by `concept_id`, and prefer the match with the higher score.
4. WHEN the Model_Server_Client is unavailable at query time, THE QueryDecomposer SHALL fall back to lexical-only matching and log a warning.
5. THE QueryDecomposer SHALL return semantic matches within the same `concept_matches` list in the QueryDecomposition, annotated with a `match_type` field indicating `"lexical"`, `"semantic"`, or `"both"`.

### Requirement 3: Configurable Matching Parameters

**User Story:** As a system operator, I want to tune semantic matching parameters, so that I can balance precision and recall for different deployment scenarios.

#### Acceptance Criteria

1. THE QueryDecomposer SHALL accept a configurable Similarity_Threshold with a default value of 0.7.
2. THE QueryDecomposer SHALL accept a configurable maximum number of semantic results with a default value of 10.
3. THE QueryDecomposer SHALL accept a configurable flag to enable or disable semantic matching, defaulting to enabled.
4. WHEN semantic matching is disabled, THE QueryDecomposer SHALL use only lexical matching without invoking the Model_Server_Client.

### Requirement 4: Integration with Existing KG Retrieval Pipeline

**User Story:** As a developer, I want semantic concept matches to flow through the existing KG retrieval pipeline without changes to downstream components, so that the integration is non-disruptive.

#### Acceptance Criteria

1. THE QueryDecomposer SHALL produce a QueryDecomposition object whose `concept_matches` list contains both lexical and semantic matches in a format compatible with the existing KGRetrievalService.
2. WHEN semantic matches are included, THE KGRetrievalService SHALL use them identically to lexical matches for chunk retrieval and relationship traversal.
3. THE QueryDecomposition serialization (to_dict / from_dict) SHALL preserve the `match_type` annotation through round-trip serialization.

### Requirement 5: Dependency Injection Compliance

**User Story:** As a developer, I want the semantic matching components to follow the project's dependency injection patterns, so that the system remains testable and follows established conventions.

#### Acceptance Criteria

1. THE QueryDecomposer SHALL receive the Model_Server_Client via dependency injection, not through module-level instantiation.
2. WHEN the Model_Server_Client dependency is not provided, THE QueryDecomposer SHALL operate in lexical-only mode without raising errors.
