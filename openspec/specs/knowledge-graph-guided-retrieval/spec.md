## Purpose

This document specifies the requirements for the Knowledge Graph-Guided Retrieval feature, which implements an intelligent retrieval system that leverages the existing Neo4j knowledge graph (with 19,626+ concepts) to provide more precise and explainable document retrieval. This feature addresses the limitations of pure semantic search, particularly for queries involving named entities like "Chelsea" where embedding truncation and semantic dilution cause retrieval failures.

The system implements a multi-stage retrieval approach that uses direct chunk pointers from concept nodes (`source_chunks` field), graph traversal for relationship-based retrieval, and semantic re-ranking for relevance ordering.


### Key Terms
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

### Requirement: Direct Chunk Retrieval via Source Chunks

The system SHALL support: As a user, I want the system to retrieve document chunks directly using knowledge graph concept pointers, so that I can find relevant content even when semantic search fails due to embedding limitations.

#### Scenario: WHEN a query contains a recognized concept THEN THE KG_Retri

- **WHEN** a query contains a recognized concept
- **THEN** THE KG_Retrieval_Service SHALL retrieve the `source_chunks` array from the matching Concept_Node in Neo4j

#### Scenario: WHEN source chunk IDs are retrieved THEN THE Chunk_Resolver

- **WHEN** source chunk IDs are retrieved
- **THEN** THE Chunk_Resolver SHALL fetch the actual chunk content from OpenSearch using `get_chunk_by_id()`

#### Scenario: WHEN multiple concepts are recognized in a query THEN THE KG

- **WHEN** multiple concepts are recognized in a query
- **THEN** THE KG_Retrieval_Service SHALL aggregate source chunks from all matching concepts

#### Scenario: WHEN a chunk ID from `source_chunks` does not exist in OpenS

- **WHEN** a chunk ID from `source_chunks` does not exist in OpenSearch
- **THEN** THE Chunk_Resolver SHALL log a warning and continue with remaining chunks

#### Scenario: THE KG_Retrieval_Service SHALL deduplicate chunks when the s

- **THEN** THE KG_Retrieval_Service SHALL deduplicate chunks when the same chunk is referenced by multiple concepts

### Requirement: Graph-Guided Relationship Retrieval

The system SHALL support: As a user, I want the system to find related content by traversing knowledge graph relationships, so that I can discover relevant information connected to my query concepts.

#### Scenario: WHEN a concept is identified in a query THEN THE Reasoning_P

- **WHEN** a concept is identified in a query
- **THEN** THE Reasoning_Path_Retriever SHALL traverse relationships up to 2 hops to find related concepts

#### Scenario: WHEN related concepts are found THEN THE Reasoning_Path_Retr

- **WHEN** related concepts are found
- **THEN** THE Reasoning_Path_Retriever SHALL collect source chunks from those related concepts

#### Scenario: WHEN traversing relationships THEN THE Reasoning_Path_Retrie

- **WHEN** traversing relationships
- **THEN** THE Reasoning_Path_Retriever SHALL prioritize RELATED_TO, IS_A, PART_OF, and CAUSES relationship types

#### Scenario: THE Reasoning_Path_Retriever SHALL assign relevance scores t

- **THEN** THE Reasoning_Path_Retriever SHALL assign relevance scores to chunks based on relationship distance (closer = higher score)

#### Scenario: WHEN a reasoning path connects query concepts THEN THE KG_Re

- **WHEN** a reasoning path connects query concepts
- **THEN** THE KG_Retrieval_Service SHALL include chunks from all concepts along the path

### Requirement: Two-Stage Retrieval Pipeline

The system SHALL support: As a user, I want the system to combine knowledge graph precision with semantic relevance, so that I get both accurate and well-ordered results.

#### Scenario: THE KG_Retrieval_Service SHALL implement a two-stage retriev

- **THEN** THE KG_Retrieval_Service SHALL implement a two-stage retrieval pipeline: Stage 1 (KG-based candidate retrieval) followed by Stage 2 (semantic re-ranking)

#### Scenario: WHEN Stage 1 completes THEN THE Semantic_Reranker SHALL re-r

- **WHEN** Stage 1 completes
- **THEN** THE Semantic_Reranker SHALL re-rank candidate chunks using cosine similarity to the query embedding

#### Scenario: WHEN Stage 1 returns fewer than 3 chunks THEN THE KG_Retriev

- **WHEN** Stage 1 returns fewer than 3 chunks
- **THEN** THE KG_Retrieval_Service SHALL augment results with semantic search results

#### Scenario: THE KG_Retrieval_Service SHALL return a maximum of 15 chunks

- **THEN** THE KG_Retrieval_Service SHALL return a maximum of 15 chunks after both stages complete

#### Scenario: WHEN returning results THEN THE KG_Retrieval_Service SHALL i

- **WHEN** returning results
- **THEN** THE KG_Retrieval_Service SHALL include retrieval metadata indicating which stage contributed each chunk

### Requirement: Query Decomposition

The system SHALL support: As a user, I want the system to understand the structure of my queries, so that it can identify the key entities and relationships I'm asking about.

#### Scenario: WHEN processing a query THEN THE Query_Decomposer SHALL extr

- **WHEN** processing a query
- **THEN** THE Query_Decomposer SHALL extract named entities by matching against Neo4j concept names

#### Scenario: WHEN a query contains action words (e.g., "observed", "found

- **WHEN** a query contains action words (e.g., "observed", "found", "discovered")
- **THEN** THE Query_Decomposer SHALL identify the action component

#### Scenario: WHEN a query contains subject references (e.g., "our team",

- **WHEN** a query contains subject references (e.g., "our team", "the system")
- **THEN** THE Query_Decomposer SHALL identify the subject component

#### Scenario: THE Query_Decomposer SHALL return a structured decomposition

- **THEN** THE Query_Decomposer SHALL return a structured decomposition containing entities, actions, and subjects

#### Scenario: WHEN no concepts are recognized THEN THE Query_Decomposer SH

- **WHEN** no concepts are recognized
- **THEN** THE Query_Decomposer SHALL return an empty decomposition and signal fallback mode

### Requirement: Explanation Generation

The system SHALL support: As a user, I want to understand why certain chunks were retrieved, so that I can trust and verify the system's reasoning.

#### Scenario: WHEN chunks are retrieved via knowledge graph THEN THE KG_Re

- **WHEN** chunks are retrieved via knowledge graph
- **THEN** THE KG_Retrieval_Service SHALL generate an explanation describing the retrieval path

#### Scenario: WHEN a reasoning path is used THEN THE explanation SHALL inc

- **WHEN** a reasoning path is used
- **THEN** THE explanation SHALL include the concept names and relationship types traversed

#### Scenario: WHEN direct source chunks are used THEN THE explanation SHAL

- **WHEN** direct source chunks are used
- **THEN** THE explanation SHALL indicate which concept provided the chunk reference

#### Scenario: THE explanation SHALL be included in the RAG response metada

- **THEN** THE explanation SHALL be included in the RAG response metadata under the key `kg_retrieval_explanation`

#### Scenario: WHEN fallback to semantic search occurs THEN THE explanation

- **WHEN** fallback to semantic search occurs
- **THEN** THE explanation SHALL indicate that knowledge graph retrieval was not applicable

### Requirement: Graceful Degradation and Fallback

The system SHALL support: As a user, I want the system to continue working even when the knowledge graph is unavailable, so that I always get some response to my queries.

#### Scenario: WHEN Neo4j is unavailable THEN THE KG_Retrieval_Service SHAL

- **WHEN** Neo4j is unavailable
- **THEN** THE KG_Retrieval_Service SHALL fall back to pure semantic search via OpenSearch

#### Scenario: WHEN no concepts are recognized in a query THEN THE KG_Retri

- **WHEN** no concepts are recognized in a query
- **THEN** THE KG_Retrieval_Service SHALL fall back to pure semantic search

#### Scenario: WHEN knowledge graph retrieval returns zero chunks THEN THE

- **WHEN** knowledge graph retrieval returns zero chunks
- **THEN** THE KG_Retrieval_Service SHALL fall back to semantic search

#### Scenario: IF a timeout occurs during Neo4j queries THEN THE KG_Retriev

- **GIVEN** a timeout occurs during Neo4j queries
- **THEN** IF a timeout occurs during Neo4j queries THEN THE KG_Retrieval_Service SHALL return partial results and log the timeout

#### Scenario: THE KG_Retrieval_Service SHALL include a `fallback_used` fla

- **THEN** THE KG_Retrieval_Service SHALL include a `fallback_used` flag in the response metadata indicating whether fallback was triggered

### Requirement: Integration with RAGService

The system SHALL support: As a developer, I want the knowledge graph-guided retrieval to integrate seamlessly with the existing RAGService, so that I can use it without major code changes.

#### Scenario: THE KG_Retrieval_Service SHALL be injectable via FastAPI dep

- **THEN** THE KG_Retrieval_Service SHALL be injectable via FastAPI dependency injection following existing DI patterns

#### Scenario: WHEN RAGService is initialized THEN it SHALL accept an optio

- **WHEN** RAGService is initialized
- **THEN** it SHALL accept an optional KG_Retrieval_Service dependency

#### Scenario: THE KG_Retrieval_Service SHALL implement lazy initialization

- **THEN** THE KG_Retrieval_Service SHALL implement lazy initialization to avoid blocking application startup

#### Scenario: WHEN KG_Retrieval_Service is unavailable THEN RAGService SHA

- **WHEN** KG_Retrieval_Service is unavailable
- **THEN** RAGService SHALL continue functioning with existing semantic search

#### Scenario: THE KG_Retrieval_Service SHALL expose a health check method

- **THEN** THE KG_Retrieval_Service SHALL expose a health check method compatible with the existing health check system

### Requirement: Performance and Caching

The system SHALL support: As a user, I want the knowledge graph retrieval to be fast, so that my queries are answered without noticeable delay.

#### Scenario: THE KG_Retrieval_Service SHALL complete Stage 1 retrieval wi

- **THEN** THE KG_Retrieval_Service SHALL complete Stage 1 retrieval within 500ms for typical queries

#### Scenario: WHEN the same concept is queried multiple times THEN THE KG_

- **WHEN** the same concept is queried multiple times
- **THEN** THE KG_Retrieval_Service SHALL cache the source_chunks array for 5 minutes

#### Scenario: THE KG_Retrieval_Service SHALL use async operations for all

- **THEN** THE KG_Retrieval_Service SHALL use async operations for all Neo4j and OpenSearch calls to avoid blocking

#### Scenario: WHEN batch retrieving chunks THEN THE Chunk_Resolver SHALL u

- **WHEN** batch retrieving chunks
- **THEN** THE Chunk_Resolver SHALL use parallel requests to OpenSearch

#### Scenario: THE KG_Retrieval_Service SHALL log performance metrics inclu

- **THEN** THE KG_Retrieval_Service SHALL log performance metrics including retrieval time and cache hit rate
