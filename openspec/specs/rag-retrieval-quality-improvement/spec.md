## Purpose

This specification covers two targeted changes to improve RAG retrieval quality in the Multimodal Librarian system. First, the `ContextPreparer` context window is increased from 8,000 to 32,000 characters so that more relevant chunks reach the LLM. Second, the embedding model is swapped from `all-MiniLM-L6-v2` (384 dimensions) to `bge-base-en-v1.5` (768 dimensions) to produce higher-quality semantic scores across all embedding consumers: Milvus vector search, Neo4j concept semantic matching, SemanticReranker, and QueryDecomposer. The swap requires recreating vector indexes, updating all hardcoded dimension references, and re-uploading all content (no automated migration script — the operator will re-upload documents through the normal upload pipeline).


### Key Terms
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

### Requirement: Increase Context Window

The system SHALL support: As a user querying the knowledge base, I want the system to include more relevant chunks in the LLM context, so that answers draw from a broader set of retrieved information and relevant chunks ranked beyond position 4 are not silently dropped.

#### Scenario: THE Context_Preparer SHALL use a Max_Context_Length of 32,00

- **THEN** THE Context_Preparer SHALL use a Max_Context_Length of 32,000 characters.

#### Scenario: WHEN chunks are selected for context assembly, THE Context_P

- **THEN** WHEN chunks are selected for context assembly, THE Context_Preparer SHALL include all ranked chunks whose cumulative formatted length (content plus formatting overhead) fits within the 32,000-character budget.

#### Scenario: WHEN the cumulative length of ranked chunks exceeds 32,000 c

- **THEN** WHEN the cumulative length of ranked chunks exceeds 32,000 characters, THE Context_Preparer SHALL stop adding chunks and return only those that fit within the budget.

### Requirement: Update Embedding Model in Model Server

The system SHALL support: As a system operator, I want the Model_Server to serve `bge-base-en-v1.5` instead of `all-MiniLM-L6-v2`, so that all embedding consumers produce higher-quality semantic representations.

#### Scenario: THE Model_Server SHALL load and serve the `bge-base-en-v1.5`

- **THEN** THE Model_Server SHALL load and serve the `bge-base-en-v1.5` embedding model.

#### Scenario: WHEN the Model_Server starts, THE Model_Server SHALL report

- **THEN** WHEN the Model_Server starts, THE Model_Server SHALL report an Embedding_Dimension of

#### Scenario: 

- **THEN** 

#### Scenario: THE Model_Server Docker container configuration SHALL specif

- **THEN** THE Model_Server Docker container configuration SHALL specify `bge-base-en-v1.5` as the `EMBEDDING_MODEL` environment variable.

#### Scenario: WHEN a client sends an embedding request, THE Model_Server S

- **THEN** WHEN a client sends an embedding request, THE Model_Server SHALL return vectors with 768 dimensions.

### Requirement: Update Application Configuration Defaults

The system SHALL support: As a developer, I want all configuration files to reflect the new embedding model and dimension, so that the system is internally consistent and new deployments use the correct defaults.

#### Scenario: THE Config SHALL define a default `embedding_dimension` of

- **THEN** THE Config SHALL define a default `embedding_dimension` of

#### Scenario: 

- **THEN** 

#### Scenario: THE Config SHALL define a default `embedding_model` of `bge-

- **THEN** THE Config SHALL define a default `embedding_model` of `bge-base-en-v1.5`.

#### Scenario: THE Config SHALL include `bge-base-en-v1.5` with dimension 7

- **THEN** THE Config SHALL include `bge-base-en-v1.5` with dimension 768 in the model-to-dimension mapping used for auto-detection.

#### Scenario: WHEN the `EMBEDDING_MODEL` environment variable is set to `b

- **THEN** WHEN the `EMBEDDING_MODEL` environment variable is set to `bge-base-en-v1.5`, THE Config SHALL resolve the Embedding_Dimension to 768.

### Requirement: Recreate Milvus Collection with New Dimensions

The system SHALL support: As a system operator, I want the Milvus collection to be recreated with 768-dimension schema, so that the new embeddings can be stored and searched correctly.

#### Scenario: THE Milvus_Client SHALL create collections with an Embedding

- **THEN** THE Milvus_Client SHALL create collections with an Embedding_Dimension of

#### Scenario: 

- **THEN** 

#### Scenario: WHEN the existing `knowledge_chunks` Milvus_Collection has a

- **THEN** WHEN the existing `knowledge_chunks` Milvus_Collection has a dimension mismatch with the configured Embedding_Dimension, THE system SHALL require the collection to be dropped and recreated.

#### Scenario: IF a vector with incorrect dimensions is inserted into a Mil

- **GIVEN** a vector with incorrect dimensions is inserted into a Milvus_Collection
- **THEN** IF a vector with incorrect dimensions is inserted into a Milvus_Collection, THEN THE Milvus_Client SHALL return a descriptive error.

#### Scenario: THE Milvus_Client SHALL update all hardcoded Embedding_Dimen

- **THEN** THE Milvus_Client SHALL update all hardcoded Embedding_Dimension references from 384 to 768.

### Requirement: Recreate Neo4j Concept Embedding Index

The system SHALL support: As a system operator, I want the Neo4j concept embedding index to use 768 dimensions, so that semantic concept matching at query time works with the new embedding vectors.

#### Scenario: THE Neo4j_Client `ensure_indexes` method SHALL create the `c

- **THEN** THE Neo4j_Client `ensure_indexes` method SHALL create the `concept_embedding_index` with an Embedding_Dimension of

#### Scenario: 

- **THEN** 

#### Scenario: WHEN the existing `concept_embedding_index` has a dimension

- **THEN** WHEN the existing `concept_embedding_index` has a dimension mismatch, THE system SHALL require the index to be dropped and recreated at 768 dimensions.

#### Scenario: WHEN `ensure_indexes` executes, THE Neo4j_Client SHALL use 7

- **THEN** WHEN `ensure_indexes` executes, THE Neo4j_Client SHALL use 768 as the dimension parameter in the `db.index.vector.createNodeIndex` call.

### Requirement: Update Hardcoded Dimension References

The system SHALL support: As a developer, I want all hardcoded 384-dimension references in the application code to be updated to 768, so that placeholder embeddings, health checks, and documentation are consistent with the new model.

#### Scenario: THE Celery_Worker SHALL set `_embedding_dimension` to 768 wh

- **THEN** THE Celery_Worker SHALL set `_embedding_dimension` to 768 when initializing vector clients for chunk and bridge embedding tasks.

#### Scenario: THE `rag_service.py` placeholder embeddings SHALL use `np.ze

- **THEN** THE `rag_service.py` placeholder embeddings SHALL use `np.zeros(768)` instead of `np.zeros(384)`.

#### Scenario: THE `kg_query_engine.py` placeholder embeddings SHALL use `n

- **THEN** THE `kg_query_engine.py` placeholder embeddings SHALL use `np.zeros(768)` instead of `np.zeros(384)`.

#### Scenario: THE `opensearch_client.py` default `embedding_dimension` SHA

- **THEN** THE `opensearch_client.py` default `embedding_dimension` SHALL be

#### Scenario: 

- **THEN** 

#### Scenario: THE health check endpoint SHALL use 768-dimension dummy vect

- **THEN** THE health check endpoint SHALL use 768-dimension dummy vectors for Milvus search validation.

#### Scenario: THE Docker Compose configuration SHALL specify `EMBEDDING_MO

- **THEN** THE Docker Compose configuration SHALL specify `EMBEDDING_MODEL=bge-base-en-v1.5` for the Model_Server, app, and Celery_Worker services.

### Requirement: Update Embedding Token Configuration

The system SHALL support: As a developer, I want the embedding token configuration to reflect the new model's capabilities, so that the chunking framework produces chunks optimally sized for `bge-base-en-v1.5`.

#### Scenario: THE Config `target_embedding_tokens` description SHALL refer

- **THEN** THE Config `target_embedding_tokens` description SHALL reference `bge-base-en-v1.5` instead of `all-MiniLM-L6-v2`.

#### Scenario: THE Config SHALL document that `bge-base-en-v1.5` supports u

- **THEN** THE Config SHALL document that `bge-base-en-v1.5` supports up to 512 tokens, matching the existing `max_embedding_tokens` default.
