# Requirements Document

## Introduction

This feature closes the gap between conversation persistence and unified queryable knowledge. Today, `ConversationManager.convert_to_knowledge_chunks()` creates `KnowledgeChunk` objects in memory with `source_type=SourceType.CONVERSATION`, but those chunks are never embedded, never pushed to Milvus, never extracted into Neo4j, and never surfaced by the RAG pipeline. The product vision states "Treat books and conversations as equivalent knowledge sources" — this feature makes that real by wiring conversation chunks through the same embedding → vector store → knowledge graph → unified search pipeline that documents already use.

## Glossary

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

### Requirement 1: Conversation Knowledge Ingestion Pipeline

**User Story:** As a user, I want my completed conversations to be automatically processed into searchable knowledge, so that insights from past conversations are discoverable alongside document knowledge.

#### Acceptance Criteria

1. WHEN a conversation is marked for knowledge conversion, THE Conversation_Knowledge_Service SHALL invoke `ConversationManager.convert_to_knowledge_chunks()` to produce a list of Conversation_Chunks.
2. WHEN Conversation_Chunks are produced, THE Conversation_Knowledge_Service SHALL generate vector embeddings for each chunk using the Embedding_Model.
3. WHEN embeddings are generated, THE Conversation_Knowledge_Service SHALL insert the Conversation_Chunks with their embeddings into the Vector_Store.
4. WHEN Vector_Store insertion succeeds, THE Conversation_Knowledge_Service SHALL extract concepts and relationships from each Conversation_Chunk and store them in the Knowledge_Graph.
5. IF embedding generation fails for a Conversation_Chunk, THEN THE Conversation_Knowledge_Service SHALL raise an error and abort the pipeline for that conversation.
6. IF Vector_Store insertion fails, THEN THE Conversation_Knowledge_Service SHALL raise an error and abort the pipeline for that conversation.
7. IF Knowledge_Graph extraction fails, THEN THE Conversation_Knowledge_Service SHALL raise an error and abort the pipeline for that conversation.

### Requirement 2: Conversation Chunk Embedding Generation

**User Story:** As a system operator, I want conversation chunks to be embedded using the same model as document chunks, so that semantic similarity search works uniformly across all knowledge sources.

#### Acceptance Criteria

1. THE Conversation_Knowledge_Service SHALL use the same Embedding_Model instance used for document chunk embeddings.
2. WHEN generating embeddings for Conversation_Chunks, THE Conversation_Knowledge_Service SHALL produce embedding vectors of the same dimensionality as document chunk embeddings.
3. WHEN a Conversation_Chunk has associated multimedia metadata, THE Conversation_Knowledge_Service SHALL embed only the text content of the chunk.

### Requirement 3: Conversation Chunk Vector Storage

**User Story:** As a user, I want conversation-derived knowledge stored in the same vector database as document knowledge, so that a single semantic search query returns results from both sources.

#### Acceptance Criteria

1. THE Conversation_Knowledge_Service SHALL store Conversation_Chunks in the same Milvus collection used for document chunks.
2. WHEN storing a Conversation_Chunk, THE Conversation_Knowledge_Service SHALL persist the chunk ID, embedding vector, text content, source type as "conversation", source ID as the conversation thread ID, and knowledge metadata.
3. WHEN storing a Conversation_Chunk, THE Conversation_Knowledge_Service SHALL set the `source_type` metadata field to `SourceType.CONVERSATION` so that the chunk is identifiable as conversation-derived.
4. IF a Conversation_Chunk with the same ID already exists in the Vector_Store, THEN THE Conversation_Knowledge_Service SHALL overwrite the existing entry with the updated content and embedding (idempotent upsert).

### Requirement 4: Conversation Knowledge Graph Integration

**User Story:** As a user, I want concepts from my conversations extracted into the knowledge graph, so that concept-based queries can traverse both document and conversation knowledge.

#### Acceptance Criteria

1. WHEN Conversation_Chunks are stored in the Vector_Store, THE Conversation_Knowledge_Service SHALL extract concepts and relationships from each chunk using the same extraction logic used for document chunks.
2. WHEN creating Concept nodes in the Knowledge_Graph for conversation-derived concepts, THE Conversation_Knowledge_Service SHALL set the `source_document` property to the conversation thread ID.
3. THE Conversation_Knowledge_Service SHALL create relationships between conversation-derived concepts and existing document-derived concepts when semantic overlap is detected.

### Requirement 5: Unified Search Across Knowledge Sources

**User Story:** As a user, I want my search queries to return results from both documents and conversations ranked by relevance, so that I get the most relevant answer regardless of knowledge source.

#### Acceptance Criteria

1. WHEN the RAG_Pipeline performs semantic search, THE Vector_Store SHALL return matching chunks from both document and conversation sources without source-type filtering.
2. WHEN the RAG_Pipeline performs KG-guided retrieval, THE KnowledgeGraphQueryEngine SHALL traverse concepts originating from both document and conversation sources.
3. THE RAG_Pipeline SHALL rank conversation-derived chunks and document-derived chunks using the same similarity scoring and boosting logic.

### Requirement 6: Conversation-Aware Citation Tracking

**User Story:** As a user, I want responses that cite conversation sources to clearly indicate the conversation origin, so that I can distinguish between document-sourced and conversation-sourced information.

#### Acceptance Criteria

1. WHEN a response includes information from a Conversation_Chunk, THE CitationTracker SHALL create a KnowledgeCitation with `source_type=SourceType.CONVERSATION`.
2. WHEN formatting a conversation citation, THE CitationTracker SHALL include the conversation thread title and the timestamp range of the cited message group as the `location_reference`.
3. THE CitationTracker SHALL support filtering citations by `SourceType.CONVERSATION` via the existing `get_citations_by_source()` method.

### Requirement 7: Conversation Knowledge API Endpoint

**User Story:** As a developer, I want an API endpoint to trigger conversation knowledge ingestion, so that conversations can be programmatically converted to searchable knowledge.

#### Acceptance Criteria

1. THE API SHALL expose a POST endpoint at `/api/conversations/{thread_id}/convert-to-knowledge` that triggers the full ingestion pipeline for a given conversation.
2. WHEN the endpoint is called, THE API SHALL return a response containing the number of chunks created, the number of concepts extracted, and the conversation thread ID.
3. IF the specified conversation thread does not exist, THEN THE API SHALL return a 404 status code with a descriptive error message.
4. IF the ingestion pipeline fails at any stage, THEN THE API SHALL return a 500 status code with the failure stage and error details.
5. THE API endpoint SHALL use FastAPI dependency injection to obtain the Conversation_Knowledge_Service, Vector_Store, and Knowledge_Graph dependencies.

### Requirement 8: Duplicate Ingestion Prevention

**User Story:** As a system operator, I want the system to handle re-ingestion of already-converted conversations gracefully, so that duplicate knowledge entries do not accumulate.

#### Acceptance Criteria

1. WHEN a conversation that has already been ingested is submitted for conversion again, THE Conversation_Knowledge_Service SHALL remove existing Conversation_Chunks for that thread ID from the Vector_Store before inserting new chunks.
2. WHEN re-ingesting a conversation, THE Conversation_Knowledge_Service SHALL remove existing conversation-derived Concept nodes for that thread ID from the Knowledge_Graph before extracting new concepts.
3. WHEN the cleanup-then-reingest operation completes, THE Conversation_Knowledge_Service SHALL return the updated chunk and concept counts.
