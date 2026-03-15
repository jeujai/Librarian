# Requirements Document

## Introduction

The conversation-to-knowledge-graph pipeline (`ConversationKnowledgeService`) currently produces significantly lower quality results than the document processing pipeline (`KnowledgeGraphBuilder`). The document pipeline uses three relationship extraction methods (pattern-based, embedding-based, ConceptNet validation) while the conversation pipeline only uses pattern-based extraction — the weakest method that almost never matches conversational text. Additionally, conversations are flattened into timestamped text blocks, losing the prompt→response→source structure that would enable meaningful graph navigation. This feature brings the conversation KG pipeline to parity with the document pipeline and adds conversation-specific structure preservation.

## Glossary

- **Conversation_Pipeline**: The `ConversationKnowledgeService._extract_and_store_concepts` method that extracts concepts and relationships from conversation chunks and persists them to Neo4j.
- **Document_Pipeline**: The `KnowledgeGraphBuilder.process_knowledge_chunk_async` method that extracts concepts and relationships from document chunks using the full hybrid extraction approach (NER + regex concepts, ConceptNet validation, pattern + embedding + ConceptNet relationships).
- **Concept_Extractor**: The `ConceptExtractor` class that extracts concept nodes from text using NER and regex methods via `extract_all_concepts_async`.
- **Relationship_Extractor**: The `RelationshipExtractor` class that extracts relationship edges between concepts using pattern-based, embedding-based, and LLM-based methods.
- **ConceptNet_Validator**: The `ConceptNetValidator` class that validates extracted concepts against ConceptNet and produces additional ConceptNet-sourced relationships.
- **Embedding_Relationships**: Relationships extracted by computing cosine similarity between concept name embeddings via the model server, creating SIMILAR_TO edges above a 0.6 threshold.
- **Pattern_Relationships**: Relationships extracted by regex pattern matching (e.g., "X is a Y", "X causes Y") — effective for formal prose but rarely matches conversational text.
- **Knowledge_Chunk**: A `KnowledgeChunk` object representing a unit of content with metadata, source type, and content type.
- **Conversation_Structure**: The prompt→response→source hierarchy within a conversation turn: a user prompt, the AI response, and any source documents cited in that response.
- **Source_Citation**: A reference to a document or knowledge source that appears in an AI response, typically as a title, filename, or source ID.
- **Message_Group**: A list of consecutive messages grouped by `ConversationManager._group_messages_for_chunking` based on time gaps and topic boundaries.
- **KG_Explorer**: The API and query engine (`kg_explorer.py`, `kg_query_engine.py`) that allows users to search, browse, and navigate the knowledge graph.
- **Model_Server_Client**: The async client used to generate embeddings via the model server container, required for embedding-based relationship extraction.

## Requirements

### Requirement 1: Embedding-Based Relationship Extraction for Conversations

**User Story:** As a knowledge graph user, I want the conversation pipeline to extract embedding-based relationships between concepts, so that semantically related concepts from conversations are connected in the graph even when no explicit textual pattern links them.

#### Acceptance Criteria

1. WHEN the Conversation_Pipeline processes a Knowledge_Chunk, THE Conversation_Pipeline SHALL extract Embedding_Relationships by computing cosine similarity between concept name embeddings via the Model_Server_Client.
2. WHEN the cosine similarity between two concept embeddings exceeds 0.6, THE Conversation_Pipeline SHALL create a SIMILAR_TO relationship edge between those concepts.
3. IF the Model_Server_Client is unavailable, THEN THE Conversation_Pipeline SHALL skip Embedding_Relationships extraction and continue processing with Pattern_Relationships only.
4. THE Conversation_Pipeline SHALL combine Pattern_Relationships and Embedding_Relationships, deduplicate them, and persist all unique relationships to Neo4j.

### Requirement 2: ConceptNet Validation Gate for Conversations

**User Story:** As a knowledge graph user, I want conversation concepts to be validated through the ConceptNet gate, so that low-quality concepts are filtered out and ConceptNet-sourced relationships enrich the graph.

#### Acceptance Criteria

1. WHEN the Conversation_Pipeline extracts concepts from a Knowledge_Chunk, THE Conversation_Pipeline SHALL validate those concepts through the ConceptNet_Validator before relationship extraction.
2. WHEN the ConceptNet_Validator validates concepts, THE Conversation_Pipeline SHALL retain only validated concepts and collect ConceptNet-sourced relationships.
3. IF the ConceptNet_Validator is unavailable, THEN THE Conversation_Pipeline SHALL use the raw extracted concepts without validation and log a warning.
4. THE Conversation_Pipeline SHALL combine ConceptNet-sourced relationships with Pattern_Relationships and Embedding_Relationships before deduplication.

### Requirement 3: Conversation Structure Preservation in Chunking

**User Story:** As a knowledge graph user, I want the conversation chunking process to preserve the prompt→response→source structure, so that the knowledge graph reflects the conversational flow and enables navigation from questions to answers to cited sources.

#### Acceptance Criteria

1. WHEN the ConversationManager converts a Message_Group to a Knowledge_Chunk, THE ConversationManager SHALL produce separate content sections for user prompts and system responses within each chunk, preserving the role attribution.
2. WHEN a Knowledge_Chunk is created from a Message_Group, THE Knowledge_Chunk metadata SHALL include a structured field identifying which content segments are user prompts and which are system responses.
3. THE Conversation_Pipeline SHALL extract concepts separately from user prompt segments and system response segments within each Knowledge_Chunk.
4. WHEN concepts are extracted from both prompt and response segments of the same turn, THE Conversation_Pipeline SHALL create PROMPTED_BY relationship edges linking response concepts back to the prompt concepts that elicited them.

### Requirement 4: Source Citation Extraction and Graph Navigation

**User Story:** As a knowledge graph user, I want source documents cited in AI responses to appear as navigable concepts in the knowledge graph, so that I can trace from a conversation topic back to the original source material.

#### Acceptance Criteria

1. WHEN the Conversation_Pipeline processes a system response segment, THE Conversation_Pipeline SHALL extract Source_Citations from the response text using pattern matching for document titles, filenames, and source references.
2. WHEN a Source_Citation is extracted, THE Conversation_Pipeline SHALL create a concept node for the cited source with a CITED_SOURCE concept type and link it to the response concepts via a CITES relationship edge.
3. WHEN a Source_Citation matches an existing knowledge source in the system, THE Conversation_Pipeline SHALL link the citation concept to the existing source's concepts via a DERIVED_FROM relationship edge rather than creating a duplicate.
4. THE KG_Explorer SHALL support traversal of CITES and DERIVED_FROM relationship edges, enabling users to navigate from conversation concepts to cited source concepts.

### Requirement 5: Parity with Document Pipeline Extraction Quality

**User Story:** As a knowledge graph user, I want the conversation pipeline to use the same extraction methods as the document pipeline, so that conversation-sourced knowledge is equally rich and well-connected in the graph.

#### Acceptance Criteria

1. THE Conversation_Pipeline SHALL use the same three-stage relationship extraction as the Document_Pipeline: ConceptNet validation, Pattern_Relationships, and Embedding_Relationships.
2. THE Conversation_Pipeline SHALL deduplicate relationships using the same deduplication logic as the Document_Pipeline (`KnowledgeGraphBuilder._deduplicate_relationships`).
3. THE Conversation_Pipeline SHALL add evidence chunk references to all extracted relationships, matching the Document_Pipeline behavior.
4. THE Conversation_Pipeline SHALL calculate an overall confidence score for each chunk extraction by averaging concept and relationship confidence scores, matching the Document_Pipeline behavior.
5. WHEN the Conversation_Pipeline processes a Knowledge_Chunk with two or more concepts and a functioning Model_Server_Client, THE Conversation_Pipeline SHALL produce a non-zero count of relationships.

### Requirement 6: Backward Compatibility and Graceful Degradation

**User Story:** As a system operator, I want the enhanced conversation pipeline to degrade gracefully when optional services are unavailable, so that conversation conversion continues to work even in degraded environments.

#### Acceptance Criteria

1. IF the Neo4j client is unavailable, THEN THE Conversation_Pipeline SHALL raise an error for KG operations, matching the current fatal-failure behavior for Neo4j.
2. IF the Model_Server_Client is unavailable, THEN THE Conversation_Pipeline SHALL skip Embedding_Relationships extraction and proceed with Pattern_Relationships and ConceptNet relationships only.
3. IF the ConceptNet_Validator is unavailable, THEN THE Conversation_Pipeline SHALL skip concept validation and proceed with raw extracted concepts.
4. THE Conversation_Pipeline SHALL follow the dependency injection patterns defined in the project, obtaining the Model_Server_Client and ConceptNet_Validator through the existing DI infrastructure without import-time connections.
5. THE existing `POST /api/conversations/{thread_id}/convert-to-knowledge` endpoint response model and status codes SHALL remain unchanged.
