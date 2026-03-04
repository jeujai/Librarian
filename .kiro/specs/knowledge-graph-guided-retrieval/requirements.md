# Requirements Document

## Introduction

This document specifies the requirements for the Knowledge Graph-Guided Retrieval feature, which implements an intelligent retrieval system that leverages the existing Neo4j knowledge graph (with 19,626+ concepts) to provide more precise and explainable document retrieval. This feature addresses the limitations of pure semantic search, particularly for queries involving named entities like "Chelsea" where embedding truncation and semantic dilution cause retrieval failures.

The system implements a multi-stage retrieval approach that uses direct chunk pointers from concept nodes (`source_chunks` field), graph traversal for relationship-based retrieval, and semantic re-ranking for relevance ordering.

## Glossary

- **KG_Retrieval_Service**: The main service component that orchestrates knowledge graph-guided retrieval operations
- **Chunk_Resolver**: Component responsible for resolving chunk IDs from concept nodes to actual chunk content via OpenSearch
- **Query_Decomposer**: Component that extracts entities, actions, and subjects from user queries using the knowledge graph
- **Reasoning_Path_Retriever**: Component that retrieves chunks along relationship paths in the knowledge graph
- **Semantic_Reranker**: Component that re-ranks candidate chunks using semantic similarity scores
- **Source_Chunks**: Array field on Neo4j Concept nodes containing direct pointers to chunk IDs in OpenSearch
- **Concept_Node**: A node in the Neo4j knowledge graph representing an extracted concept with metadata and source chunk references
- **Reasoning_Path**: A sequence of relationships connecting concepts in the knowledge graph
- **Fallback_Mode**: Operating mode when knowledge graph is unavailable, using pure semantic search

## Requirements

### Requirement 1: Direct Chunk Retrieval via Source Chunks

**User Story:** As a user, I want the system to retrieve document chunks directly using knowledge graph concept pointers, so that I can find relevant content even when semantic search fails due to embedding limitations.

#### Acceptance Criteria

1. WHEN a query contains a recognized concept THEN THE KG_Retrieval_Service SHALL retrieve the `source_chunks` array from the matching Concept_Node in Neo4j
2. WHEN source chunk IDs are retrieved THEN THE Chunk_Resolver SHALL fetch the actual chunk content from OpenSearch using `get_chunk_by_id()`
3. WHEN multiple concepts are recognized in a query THEN THE KG_Retrieval_Service SHALL aggregate source chunks from all matching concepts
4. WHEN a chunk ID from `source_chunks` does not exist in OpenSearch THEN THE Chunk_Resolver SHALL log a warning and continue with remaining chunks
5. THE KG_Retrieval_Service SHALL deduplicate chunks when the same chunk is referenced by multiple concepts

### Requirement 2: Graph-Guided Relationship Retrieval

**User Story:** As a user, I want the system to find related content by traversing knowledge graph relationships, so that I can discover relevant information connected to my query concepts.

#### Acceptance Criteria

1. WHEN a concept is identified in a query THEN THE Reasoning_Path_Retriever SHALL traverse relationships up to 2 hops to find related concepts
2. WHEN related concepts are found THEN THE Reasoning_Path_Retriever SHALL collect source chunks from those related concepts
3. WHEN traversing relationships THEN THE Reasoning_Path_Retriever SHALL prioritize RELATED_TO, IS_A, PART_OF, and CAUSES relationship types
4. THE Reasoning_Path_Retriever SHALL assign relevance scores to chunks based on relationship distance (closer = higher score)
5. WHEN a reasoning path connects query concepts THEN THE KG_Retrieval_Service SHALL include chunks from all concepts along the path

### Requirement 3: Two-Stage Retrieval Pipeline

**User Story:** As a user, I want the system to combine knowledge graph precision with semantic relevance, so that I get both accurate and well-ordered results.

#### Acceptance Criteria

1. THE KG_Retrieval_Service SHALL implement a two-stage retrieval pipeline: Stage 1 (KG-based candidate retrieval) followed by Stage 2 (semantic re-ranking)
2. WHEN Stage 1 completes THEN THE Semantic_Reranker SHALL re-rank candidate chunks using cosine similarity to the query embedding
3. WHEN Stage 1 returns fewer than 3 chunks THEN THE KG_Retrieval_Service SHALL augment results with semantic search results
4. THE KG_Retrieval_Service SHALL return a maximum of 15 chunks after both stages complete
5. WHEN returning results THEN THE KG_Retrieval_Service SHALL include retrieval metadata indicating which stage contributed each chunk

### Requirement 4: Query Decomposition

**User Story:** As a user, I want the system to understand the structure of my queries, so that it can identify the key entities and relationships I'm asking about.

#### Acceptance Criteria

1. WHEN processing a query THEN THE Query_Decomposer SHALL extract named entities by matching against Neo4j concept names
2. WHEN a query contains action words (e.g., "observed", "found", "discovered") THEN THE Query_Decomposer SHALL identify the action component
3. WHEN a query contains subject references (e.g., "our team", "the system") THEN THE Query_Decomposer SHALL identify the subject component
4. THE Query_Decomposer SHALL return a structured decomposition containing entities, actions, and subjects
5. WHEN no concepts are recognized THEN THE Query_Decomposer SHALL return an empty decomposition and signal fallback mode

### Requirement 5: Explanation Generation

**User Story:** As a user, I want to understand why certain chunks were retrieved, so that I can trust and verify the system's reasoning.

#### Acceptance Criteria

1. WHEN chunks are retrieved via knowledge graph THEN THE KG_Retrieval_Service SHALL generate an explanation describing the retrieval path
2. WHEN a reasoning path is used THEN THE explanation SHALL include the concept names and relationship types traversed
3. WHEN direct source chunks are used THEN THE explanation SHALL indicate which concept provided the chunk reference
4. THE explanation SHALL be included in the RAG response metadata under the key `kg_retrieval_explanation`
5. WHEN fallback to semantic search occurs THEN THE explanation SHALL indicate that knowledge graph retrieval was not applicable

### Requirement 6: Graceful Degradation and Fallback

**User Story:** As a user, I want the system to continue working even when the knowledge graph is unavailable, so that I always get some response to my queries.

#### Acceptance Criteria

1. WHEN Neo4j is unavailable THEN THE KG_Retrieval_Service SHALL fall back to pure semantic search via OpenSearch
2. WHEN no concepts are recognized in a query THEN THE KG_Retrieval_Service SHALL fall back to pure semantic search
3. WHEN knowledge graph retrieval returns zero chunks THEN THE KG_Retrieval_Service SHALL fall back to semantic search
4. IF a timeout occurs during Neo4j queries THEN THE KG_Retrieval_Service SHALL return partial results and log the timeout
5. THE KG_Retrieval_Service SHALL include a `fallback_used` flag in the response metadata indicating whether fallback was triggered

### Requirement 7: Integration with RAGService

**User Story:** As a developer, I want the knowledge graph-guided retrieval to integrate seamlessly with the existing RAGService, so that I can use it without major code changes.

#### Acceptance Criteria

1. THE KG_Retrieval_Service SHALL be injectable via FastAPI dependency injection following existing DI patterns
2. WHEN RAGService is initialized THEN it SHALL accept an optional KG_Retrieval_Service dependency
3. THE KG_Retrieval_Service SHALL implement lazy initialization to avoid blocking application startup
4. WHEN KG_Retrieval_Service is unavailable THEN RAGService SHALL continue functioning with existing semantic search
5. THE KG_Retrieval_Service SHALL expose a health check method compatible with the existing health check system

### Requirement 8: Performance and Caching

**User Story:** As a user, I want the knowledge graph retrieval to be fast, so that my queries are answered without noticeable delay.

#### Acceptance Criteria

1. THE KG_Retrieval_Service SHALL complete Stage 1 retrieval within 500ms for typical queries
2. WHEN the same concept is queried multiple times THEN THE KG_Retrieval_Service SHALL cache the source_chunks array for 5 minutes
3. THE KG_Retrieval_Service SHALL use async operations for all Neo4j and OpenSearch calls to avoid blocking
4. WHEN batch retrieving chunks THEN THE Chunk_Resolver SHALL use parallel requests to OpenSearch
5. THE KG_Retrieval_Service SHALL log performance metrics including retrieval time and cache hit rate
