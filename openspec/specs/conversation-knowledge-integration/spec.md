## Purpose

This feature closes the gap between conversation persistence and unified queryable knowledge. Today, `ConversationManager.convert_to_knowledge_chunks()` creates `KnowledgeChunk` objects in memory with `source_type=SourceType.CONVERSATION`, but those chunks are never embedded, never pushed to Milvus, never extracted into Neo4j, and never surfaced by the RAG pipeline. The product vision states "Treat books and conversations as equivalent knowledge sources" — this feature makes that real by wiring conversation chunks through the same embedding → vector store → knowledge graph → unified search pipeline that documents already use.


### Key Terms
- **Conversation_Knowledge_Service**: The new service that orchestrates the full pipeline of converting a conversation into queryable knowledge (chunking → embedding → Milvus insertion → Neo4j concept extraction).
- **ConversationManager**: The existing component (`components/conversation/conversation_manager.py`) that manages conversation threads, message persistence, and in-memory chunk creation via `convert_to_knowledge_chunks()`.
- **Vector_Store**: The Milvus-backed vector database used for semantic search over embedded knowledge chunks.
- **Knowledge_Graph**: The Neo4j-backed graph database storing extracted concepts, relationships, and their connections to source documents/conversations.
- **KnowledgeGraphQueryEngine**: The existing class (`components/knowledge_graph/kg_query_engine.py`) that queries Neo4j for concept-based retrieval.
- **RAG_Pipeline**: The retrieval-augmented generation pipeline (`services/rag_service.py`) that combines vector search, KG retrieval, and LLM generation to answer user queries.
- **Embedding_Model**: The sentence-transformers model used to generate vector embeddings for text chunks.
- **KnowledgeChunk**: The core domain model (`models/core.py`) representing a unit of searchable knowledge with content, metadata, source type, and optional embedding.
- **CitationTracker**: The existing class (`components/query_processor/response_synthesizer.py`) that tracks and formats citations by source type in synthesized responses.
- **Conversation_Chunk**: A KnowledgeChunk with `source_type=SourceType.CONVERSATION`, derived from grouped conversation messages.

## Requirements

### Requirement: Conversation Knowledge Ingestion Pipeline

The system SHALL support: As a user, I want my completed conversations to be automatically processed into searchable knowledge, so that insights from past conversations are discoverable alongside document knowledge.

#### Scenario: WHEN a conversation is marked for knowledge conversion, THE

- **THEN** WHEN a conversation is marked for knowledge conversion, THE Conversation_Knowledge_Service SHALL invoke `ConversationManager.convert_to_knowledge_chunks()` to produce a list of Conversation_Chunks.

#### Scenario: WHEN Conversation_Chunks are produced, THE Conversation_Know

- **THEN** WHEN Conversation_Chunks are produced, THE Conversation_Knowledge_Service SHALL generate vector embeddings for each chunk using the Embedding_Model.

#### Scenario: WHEN embeddings are generated, THE Conversation_Knowledge_Se

- **THEN** WHEN embeddings are generated, THE Conversation_Knowledge_Service SHALL insert the Conversation_Chunks with their embeddings into the Vector_Store.

#### Scenario: WHEN Vector_Store insertion succeeds, THE Conversation_Knowl

- **THEN** WHEN Vector_Store insertion succeeds, THE Conversation_Knowledge_Service SHALL extract concepts and relationships from each Conversation_Chunk and store them in the Knowledge_Graph.

#### Scenario: IF embedding generation fails for a Conversation_Chunk, THEN

- **GIVEN** embedding generation fails for a Conversation_Chunk
- **THEN** IF embedding generation fails for a Conversation_Chunk, THEN THE Conversation_Knowledge_Service SHALL raise an error and abort the pipeline for that conversation.

#### Scenario: IF Vector_Store insertion fails, THEN THE Conversation_Knowl

- **GIVEN** Vector_Store insertion fails
- **THEN** IF Vector_Store insertion fails, THEN THE Conversation_Knowledge_Service SHALL raise an error and abort the pipeline for that conversation.

#### Scenario: IF Knowledge_Graph extraction fails, THEN THE Conversation_K

- **GIVEN** Knowledge_Graph extraction fails
- **THEN** IF Knowledge_Graph extraction fails, THEN THE Conversation_Knowledge_Service SHALL raise an error and abort the pipeline for that conversation.

### Requirement: Conversation Chunk Embedding Generation

The system SHALL support: As a system operator, I want conversation chunks to be embedded using the same model as document chunks, so that semantic similarity search works uniformly across all knowledge sources.

#### Scenario: THE Conversation_Knowledge_Service SHALL use the same Embedd

- **THEN** THE Conversation_Knowledge_Service SHALL use the same Embedding_Model instance used for document chunk embeddings.

#### Scenario: WHEN generating embeddings for Conversation_Chunks, THE Conv

- **THEN** WHEN generating embeddings for Conversation_Chunks, THE Conversation_Knowledge_Service SHALL produce embedding vectors of the same dimensionality as document chunk embeddings.

#### Scenario: WHEN a Conversation_Chunk has associated multimedia metadata

- **THEN** WHEN a Conversation_Chunk has associated multimedia metadata, THE Conversation_Knowledge_Service SHALL embed only the text content of the chunk.

### Requirement: Conversation Chunk Vector Storage

The system SHALL support: As a user, I want conversation-derived knowledge stored in the same vector database as document knowledge, so that a single semantic search query returns results from both sources.

#### Scenario: THE Conversation_Knowledge_Service SHALL store Conversation_

- **THEN** THE Conversation_Knowledge_Service SHALL store Conversation_Chunks in the same Milvus collection used for document chunks.

#### Scenario: WHEN storing a Conversation_Chunk, THE Conversation_Knowledg

- **THEN** WHEN storing a Conversation_Chunk, THE Conversation_Knowledge_Service SHALL persist the chunk ID, embedding vector, text content, source type as "conversation", source ID as the conversation thread ID, and knowledge metadata.

#### Scenario: WHEN storing a Conversation_Chunk, THE Conversation_Knowledg

- **THEN** WHEN storing a Conversation_Chunk, THE Conversation_Knowledge_Service SHALL set the `source_type` metadata field to `SourceType.CONVERSATION` so that the chunk is identifiable as conversation-derived.

#### Scenario: IF a Conversation_Chunk with the same ID already exists in t

- **GIVEN** a Conversation_Chunk with the same ID already exists in the Vector_Store
- **THEN** IF a Conversation_Chunk with the same ID already exists in the Vector_Store, THEN THE Conversation_Knowledge_Service SHALL overwrite the existing entry with the updated content and embedding (idempotent upsert).

### Requirement: Conversation Knowledge Graph Integration

The system SHALL support: As a user, I want concepts from my conversations extracted into the knowledge graph, so that concept-based queries can traverse both document and conversation knowledge.

#### Scenario: WHEN Conversation_Chunks are stored in the Vector_Store, THE

- **THEN** WHEN Conversation_Chunks are stored in the Vector_Store, THE Conversation_Knowledge_Service SHALL extract concepts and relationships from each chunk using the same extraction logic used for document chunks.

#### Scenario: WHEN creating Concept nodes in the Knowledge_Graph for conve

- **THEN** WHEN creating Concept nodes in the Knowledge_Graph for conversation-derived concepts, THE Conversation_Knowledge_Service SHALL set the `source_document` property to the conversation thread ID.

#### Scenario: THE Conversation_Knowledge_Service SHALL create relationship

- **THEN** THE Conversation_Knowledge_Service SHALL create relationships between conversation-derived concepts and existing document-derived concepts when semantic overlap is detected.

### Requirement: Unified Search Across Knowledge Sources

The system SHALL support: As a user, I want my search queries to return results from both documents and conversations ranked by relevance, so that I get the most relevant answer regardless of knowledge source.

#### Scenario: WHEN the RAG_Pipeline performs semantic search, THE Vector_S

- **THEN** WHEN the RAG_Pipeline performs semantic search, THE Vector_Store SHALL return matching chunks from both document and conversation sources without source-type filtering.

#### Scenario: WHEN the RAG_Pipeline performs KG-guided retrieval, THE Know

- **THEN** WHEN the RAG_Pipeline performs KG-guided retrieval, THE KnowledgeGraphQueryEngine SHALL traverse concepts originating from both document and conversation sources.

#### Scenario: THE RAG_Pipeline SHALL rank conversation-derived chunks and

- **THEN** THE RAG_Pipeline SHALL rank conversation-derived chunks and document-derived chunks using the same similarity scoring and boosting logic.

### Requirement: Conversation-Aware Citation Tracking

The system SHALL support: As a user, I want responses that cite conversation sources to clearly indicate the conversation origin, so that I can distinguish between document-sourced and conversation-sourced information.

#### Scenario: WHEN a response includes information from a Conversation_Chu

- **THEN** WHEN a response includes information from a Conversation_Chunk, THE CitationTracker SHALL create a KnowledgeCitation with `source_type=SourceType.CONVERSATION`.

#### Scenario: WHEN formatting a conversation citation, THE CitationTracker

- **THEN** WHEN formatting a conversation citation, THE CitationTracker SHALL include the conversation thread title and the timestamp range of the cited message group as the `location_reference`.

#### Scenario: THE CitationTracker SHALL support filtering citations by `So

- **THEN** THE CitationTracker SHALL support filtering citations by `SourceType.CONVERSATION` via the existing `get_citations_by_source()` method.

### Requirement: Conversation Knowledge API Endpoint

The system SHALL support: As a developer, I want an API endpoint to trigger conversation knowledge ingestion, so that conversations can be programmatically converted to searchable knowledge.

#### Scenario: THE API SHALL expose a POST endpoint at `/api/conversations/

- **THEN** THE API SHALL expose a POST endpoint at `/api/conversations/{thread_id}/convert-to-knowledge` that triggers the full ingestion pipeline for a given conversation.

#### Scenario: WHEN the endpoint is called, THE API SHALL return a response

- **THEN** WHEN the endpoint is called, THE API SHALL return a response containing the number of chunks created, the number of concepts extracted, and the conversation thread ID.

#### Scenario: IF the specified conversation thread does not exist, THEN TH

- **GIVEN** the specified conversation thread does not exist
- **THEN** IF the specified conversation thread does not exist, THEN THE API SHALL return a 404 status code with a descriptive error message.

#### Scenario: IF the ingestion pipeline fails at any stage, THEN THE API S

- **GIVEN** the ingestion pipeline fails at any stage
- **THEN** IF the ingestion pipeline fails at any stage, THEN THE API SHALL return a 500 status code with the failure stage and error details.

#### Scenario: THE API endpoint SHALL use FastAPI dependency injection to o

- **THEN** THE API endpoint SHALL use FastAPI dependency injection to obtain the Conversation_Knowledge_Service, Vector_Store, and Knowledge_Graph dependencies.

### Requirement: Duplicate Ingestion Prevention

The system SHALL support: As a system operator, I want the system to handle re-ingestion of already-converted conversations gracefully, so that duplicate knowledge entries do not accumulate.

#### Scenario: WHEN a conversation that has already been ingested is submit

- **THEN** WHEN a conversation that has already been ingested is submitted for conversion again, THE Conversation_Knowledge_Service SHALL remove existing Conversation_Chunks for that thread ID from the Vector_Store before inserting new chunks.

#### Scenario: WHEN re-ingesting a conversation, THE Conversation_Knowledge

- **THEN** WHEN re-ingesting a conversation, THE Conversation_Knowledge_Service SHALL remove existing conversation-derived Concept nodes for that thread ID from the Knowledge_Graph before extracting new concepts.

#### Scenario: WHEN the cleanup-then-reingest operation completes, THE Conv

- **THEN** WHEN the cleanup-then-reingest operation completes, THE Conversation_Knowledge_Service SHALL return the updated chunk and concept counts.
