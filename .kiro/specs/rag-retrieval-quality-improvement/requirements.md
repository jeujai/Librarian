# Requirements Document

## Introduction

This specification covers two targeted changes to improve RAG retrieval quality in the Multimodal Librarian system. First, the `ContextPreparer` context window is increased from 8,000 to 32,000 characters so that more relevant chunks reach the LLM. Second, the embedding model is swapped from `all-MiniLM-L6-v2` (384 dimensions) to `bge-base-en-v1.5` (768 dimensions) to produce higher-quality semantic scores across all embedding consumers: Milvus vector search, Neo4j concept semantic matching, SemanticReranker, and QueryDecomposer. The swap requires recreating vector indexes, updating all hardcoded dimension references, and re-uploading all content (no automated migration script — the operator will re-upload documents through the normal upload pipeline).

## Glossary

- **Context_Preparer**: The `ContextPreparer` class in `rag_service.py` that ranks, selects, and formats document chunks into a text context string sent to the LLM.
- **Max_Context_Length**: The character budget that `Context_Preparer` uses to gate how many chunks are included in the LLM prompt.
- **Model_Server**: The dedicated Docker container (`model-server`) that loads and serves the sentence-transformer embedding model via HTTP.
- **Embedding_Model**: The sentence-transformer model used by `Model_Server` to convert text into dense vector representations.
- **Embedding_Dimension**: The number of floating-point values in each embedding vector produced by the `Embedding_Model` (384 for `all-MiniLM-L6-v2`, 768 for `bge-base-en-v1.5`).
- **Milvus**: The vector database that stores chunk and bridge embeddings and performs approximate nearest-neighbor search.
- **Milvus_Collection**: A named table in Milvus with a fixed vector dimension schema; must be recreated when the dimension changes.
- **Neo4j**: The graph database storing the knowledge graph, including Concept nodes with embedding vectors.
- **Concept_Embedding_Index**: The Neo4j vector index (`concept_embedding_index`) on `Concept.embedding` used for semantic concept matching at query time.
- **Semantic_Reranker**: The `SemanticReranker` component that generates query embeddings via `Model_Server` and computes cosine similarity against chunk embeddings for reranking.
- **Query_Decomposer**: The `QueryDecomposer` component that generates query embeddings via `Model_Server` and searches the `Concept_Embedding_Index` for semantic concept matches.
- **Celery_Worker**: The async task worker that generates concept embeddings during document enrichment via `Model_Server`.
- **Milvus_Client**: The `MilvusClient` class that manages Milvus connections, collection creation, and vector operations.
- **Neo4j_Client**: The `Neo4jClient` class that manages Neo4j connections and index creation.
- **Config**: The application configuration layer (`config.py`, `local_config.py`, `aws_native_config.py`) that defines `embedding_dimension` and `embedding_model` defaults.

## Requirements

### Requirement 1: Increase Context Window

**User Story:** As a user querying the knowledge base, I want the system to include more relevant chunks in the LLM context, so that answers draw from a broader set of retrieved information and relevant chunks ranked beyond position 4 are not silently dropped.

#### Acceptance Criteria

1. THE Context_Preparer SHALL use a Max_Context_Length of 32,000 characters.
2. WHEN chunks are selected for context assembly, THE Context_Preparer SHALL include all ranked chunks whose cumulative formatted length (content plus formatting overhead) fits within the 32,000-character budget.
3. WHEN the cumulative length of ranked chunks exceeds 32,000 characters, THE Context_Preparer SHALL stop adding chunks and return only those that fit within the budget.

### Requirement 2: Update Embedding Model in Model Server

**User Story:** As a system operator, I want the Model_Server to serve `bge-base-en-v1.5` instead of `all-MiniLM-L6-v2`, so that all embedding consumers produce higher-quality semantic representations.

#### Acceptance Criteria

1. THE Model_Server SHALL load and serve the `bge-base-en-v1.5` embedding model.
2. WHEN the Model_Server starts, THE Model_Server SHALL report an Embedding_Dimension of 768.
3. THE Model_Server Docker container configuration SHALL specify `bge-base-en-v1.5` as the `EMBEDDING_MODEL` environment variable.
4. WHEN a client sends an embedding request, THE Model_Server SHALL return vectors with 768 dimensions.

### Requirement 3: Update Application Configuration Defaults

**User Story:** As a developer, I want all configuration files to reflect the new embedding model and dimension, so that the system is internally consistent and new deployments use the correct defaults.

#### Acceptance Criteria

1. THE Config SHALL define a default `embedding_dimension` of 768.
2. THE Config SHALL define a default `embedding_model` of `bge-base-en-v1.5`.
3. THE Config SHALL include `bge-base-en-v1.5` with dimension 768 in the model-to-dimension mapping used for auto-detection.
4. WHEN the `EMBEDDING_MODEL` environment variable is set to `bge-base-en-v1.5`, THE Config SHALL resolve the Embedding_Dimension to 768.

### Requirement 4: Recreate Milvus Collection with New Dimensions

**User Story:** As a system operator, I want the Milvus collection to be recreated with 768-dimension schema, so that the new embeddings can be stored and searched correctly.

#### Acceptance Criteria

1. THE Milvus_Client SHALL create collections with an Embedding_Dimension of 768.
2. WHEN the existing `knowledge_chunks` Milvus_Collection has a dimension mismatch with the configured Embedding_Dimension, THE system SHALL require the collection to be dropped and recreated.
3. IF a vector with incorrect dimensions is inserted into a Milvus_Collection, THEN THE Milvus_Client SHALL return a descriptive error.
4. THE Milvus_Client SHALL update all hardcoded Embedding_Dimension references from 384 to 768.

### Requirement 5: Recreate Neo4j Concept Embedding Index

**User Story:** As a system operator, I want the Neo4j concept embedding index to use 768 dimensions, so that semantic concept matching at query time works with the new embedding vectors.

#### Acceptance Criteria

1. THE Neo4j_Client `ensure_indexes` method SHALL create the `concept_embedding_index` with an Embedding_Dimension of 768.
2. WHEN the existing `concept_embedding_index` has a dimension mismatch, THE system SHALL require the index to be dropped and recreated at 768 dimensions.
3. WHEN `ensure_indexes` executes, THE Neo4j_Client SHALL use 768 as the dimension parameter in the `db.index.vector.createNodeIndex` call.

### Requirement 6: Update Hardcoded Dimension References

**User Story:** As a developer, I want all hardcoded 384-dimension references in the application code to be updated to 768, so that placeholder embeddings, health checks, and documentation are consistent with the new model.

#### Acceptance Criteria

1. THE Celery_Worker SHALL set `_embedding_dimension` to 768 when initializing vector clients for chunk and bridge embedding tasks.
2. THE `rag_service.py` placeholder embeddings SHALL use `np.zeros(768)` instead of `np.zeros(384)`.
3. THE `kg_query_engine.py` placeholder embeddings SHALL use `np.zeros(768)` instead of `np.zeros(384)`.
4. THE `opensearch_client.py` default `embedding_dimension` SHALL be 768.
5. THE health check endpoint SHALL use 768-dimension dummy vectors for Milvus search validation.
6. THE Docker Compose configuration SHALL specify `EMBEDDING_MODEL=bge-base-en-v1.5` for the Model_Server, app, and Celery_Worker services.

### Requirement 7: Update Embedding Token Configuration

**User Story:** As a developer, I want the embedding token configuration to reflect the new model's capabilities, so that the chunking framework produces chunks optimally sized for `bge-base-en-v1.5`.

#### Acceptance Criteria

1. THE Config `target_embedding_tokens` description SHALL reference `bge-base-en-v1.5` instead of `all-MiniLM-L6-v2`.
2. THE Config SHALL document that `bge-base-en-v1.5` supports up to 512 tokens, matching the existing `max_embedding_tokens` default.
