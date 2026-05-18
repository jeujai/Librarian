# Implementation Plan: Conversation KG Quality

## Overview

Bring the conversation-to-knowledge-graph pipeline (`ConversationKnowledgeService`) to parity with the document pipeline (`KnowledgeGraphBuilder`) by adding embedding-based relationship extraction, ConceptNet validation, conversation structure preservation, and source citation extraction. Changes are confined to `ConversationKnowledgeService`, `ConversationManager._combine_message_group` / `convert_to_knowledge_chunks`, the KG Explorer router, and the DI provider.

## Tasks

- [x] 1. Enhance ConversationManager chunking to preserve conversation structure
  - [x] 1.1 Modify `_combine_message_group` in `src/multimodal_librarian/components/conversation/conversation_manager.py` to return both combined text and a segments list
    - Change the method to build a `segments` list of `{"role": "user"|"assistant", "content": "..."}` dicts alongside the existing combined text string
    - Each message maps to one segment with its role and raw content
    - The combined text output remains the same format for backward compatibility with embeddings and vector storage
    - _Requirements: 3.1, 3.2_

  - [x] 1.2 Update `convert_to_knowledge_chunks` in `src/multimodal_librarian/components/conversation/conversation_manager.py` to store segment metadata in `KnowledgeMetadata`
    - Call the updated `_combine_message_group` to get `(combined_text, segments)`
    - Store the segments list in `knowledge_metadata` via a new attribute or by extending the metadata dict (e.g., `knowledge_metadata.segments = segments` or storing in a custom field)
    - Ensure legacy chunks without segments still work (backward compatibility)
    - _Requirements: 3.1, 3.2, 6.5_

  - [ ]* 1.3 Write property test for chunk segment preservation
    - **Property 4: Chunk segments preserve message roles**
    - **Validates: Requirements 3.1, 3.2**

- [x] 2. Add ConceptNet validation gate to ConversationKnowledgeService
  - [x] 2.1 Extend `ConversationKnowledgeService.__init__` in `src/multimodal_librarian/services/conversation_knowledge_service.py` to accept an optional `conceptnet_validator` parameter
    - Add `conceptnet_validator: Optional[ConceptNetValidator] = None` parameter
    - Store as `self._conceptnet_validator`
    - No import-time connections — validator is injected via DI
    - _Requirements: 2.1, 6.4_

  - [x] 2.2 Add ConceptNet validation step to `_extract_and_store_concepts` in `src/multimodal_librarian/services/conversation_knowledge_service.py`
    - After extracting concepts with `extract_all_concepts_async`, validate them through `self._conceptnet_validator.validate_concepts` if the validator is available
    - Retain only validated concepts; collect ConceptNet-sourced relationships
    - If validator is unavailable or raises, log a warning and use raw concepts
    - _Requirements: 2.1, 2.2, 2.3, 6.3_

  - [ ]* 2.3 Write property test for ConceptNet validation gate
    - **Property 3: ConceptNet validation filters concepts before relationship extraction**
    - **Validates: Requirements 2.1, 2.2**

- [x] 3. Add embedding-based relationship extraction to ConversationKnowledgeService
  - [x] 3.1 Add embedding relationship extraction to `_extract_and_store_concepts` in `src/multimodal_librarian/services/conversation_knowledge_service.py`
    - After pattern-based extraction, call `self._relationship_extractor.extract_relationships_embedding_async(concepts, self._model_client)` to get SIMILAR_TO edges (cosine similarity > 0.6)
    - If the model server client is unavailable or the call fails, log a warning and skip embedding relationships
    - Combine pattern, embedding, and ConceptNet relationships
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 6.2_

  - [ ]* 3.2 Write property test for embedding similarity threshold
    - **Property 1: Embedding similarity threshold produces SIMILAR_TO edges**
    - **Validates: Requirements 1.2**

- [x] 4. Add deduplication, evidence tracking, and confidence scoring
  - [x] 4.1 Implement `_deduplicate_relationships` in `src/multimodal_librarian/services/conversation_knowledge_service.py`
    - Port the deduplication logic from `KnowledgeGraphBuilder._deduplicate_relationships`: one edge per unique (subject, predicate, object) triple, max confidence, merged evidence chunks
    - Apply deduplication to the combined relationship list before persisting
    - _Requirements: 5.2, 1.4, 2.4_

  - [x] 4.2 Add evidence chunk references and confidence scoring to `_extract_and_store_concepts`
    - Ensure all relationships have `evidence_chunks` populated with the chunk ID
    - Calculate overall confidence score as the arithmetic mean of all concept and relationship confidence scores
    - Log the confidence score for observability
    - _Requirements: 5.3, 5.4_

  - [ ]* 4.3 Write property test for relationship deduplication
    - **Property 2: Relationship deduplication preserves unique edges with max confidence**
    - **Validates: Requirements 1.4, 2.4, 5.2**

  - [ ]* 4.4 Write property test for evidence chunk references
    - **Property 8: All relationships have evidence chunk references**
    - **Validates: Requirements 5.3**

  - [ ]* 4.5 Write property test for confidence score calculation
    - **Property 9: Confidence score equals average of concept and relationship confidences**
    - **Validates: Requirements 5.4**

- [x] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement segment-aware concept extraction and PROMPTED_BY edges
  - [x] 6.1 Implement `_extract_concepts_segment_aware` in `src/multimodal_librarian/services/conversation_knowledge_service.py`
    - Parse segment metadata from `chunk.knowledge_metadata`
    - If segments exist, extract concepts separately from user prompt segments and assistant response segments
    - Create PROMPTED_BY relationship edges linking each response concept back to each prompt concept within the same chunk
    - If no segment metadata (legacy chunk), fall back to full-content extraction
    - _Requirements: 3.3, 3.4_

  - [x] 6.2 Integrate `_extract_concepts_segment_aware` into `_extract_and_store_concepts`
    - Replace the single `extract_all_concepts_async(chunk.content)` call with `_extract_concepts_segment_aware(chunk)` which returns `(all_concepts, prompted_by_edges)`
    - Merge PROMPTED_BY edges into the combined relationship list before deduplication
    - _Requirements: 3.3, 3.4, 5.1_

  - [ ]* 6.3 Write property test for PROMPTED_BY edge creation
    - **Property 5: Segment-aware extraction produces PROMPTED_BY edges**
    - **Validates: Requirements 3.3, 3.4**

- [x] 7. Implement source citation extraction
  - [x] 7.1 Implement `_extract_source_citations` in `src/multimodal_librarian/services/conversation_knowledge_service.py`
    - Define `CITATION_PATTERNS` regex list as specified in the design (Source:, from "X", according to "X", cited in X, [Source: X], 📄 X)
    - For each matched citation in response text, create a `ConceptNode` with `CITED_SOURCE` concept type
    - Create `CITES` relationship edges from each response concept to the citation concept
    - _Requirements: 4.1, 4.2_

  - [x] 7.2 Implement `_match_citation_to_existing_source` in `src/multimodal_librarian/services/conversation_knowledge_service.py`
    - Query PostgreSQL `knowledge_sources` table to check if a citation name matches an existing source title
    - If matched, create a `DERIVED_FROM` relationship edge linking the citation concept to the existing source ID
    - If the DB lookup fails, log a warning and create a standalone citation concept (no DERIVED_FROM edge)
    - _Requirements: 4.3_

  - [x] 7.3 Integrate citation extraction into `_extract_and_store_concepts`
    - After segment-aware extraction, call `_extract_source_citations` for each response segment
    - Call `_match_citation_to_existing_source` for each citation
    - Merge citation concepts and relationships into the combined lists
    - _Requirements: 4.1, 4.2, 4.3_

  - [ ]* 7.4 Write property test for citation extraction
    - **Property 6: Citation extraction produces CITED_SOURCE concepts with CITES edges**
    - **Validates: Requirements 4.1, 4.2**

  - [ ]* 7.5 Write property test for citation-to-source matching
    - **Property 7: Citation-to-source matching produces DERIVED_FROM edges**
    - **Validates: Requirements 4.3**

- [x] 8. Update DI provider and KG Explorer
  - [x] 8.1 Update `get_conversation_knowledge_service` in `src/multimodal_librarian/api/dependencies/services.py`
    - Construct a `ConceptNetValidator` from the existing `graph_client` (matching how `KnowledgeGraphBuilder._get_conceptnet_validator()` works)
    - Pass it as the `conceptnet_validator` parameter to `ConversationKnowledgeService`
    - Wrap in try/except — if construction fails, pass `None` and log a warning
    - _Requirements: 6.3, 6.4_

  - [x] 8.2 Update KG Explorer `_infer_source_type` in `src/multimodal_librarian/api/routers/kg_explorer.py`
    - Extend `_infer_source_type` to recognize `CITED_SOURCE` concept types for color coding (e.g., return `"citation"` for cited source nodes)
    - Add optional `concept_type` field to `GraphNode` model
    - Pass concept type through from Neo4j node data to the response model
    - No new endpoints needed — existing traversal already handles new relationship types (PROMPTED_BY, CITES, DERIVED_FROM) via the generic `(focus)-[]-(neighbor)` Cypher pattern
    - _Requirements: 4.4_

- [x] 9. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. Write integration and smoke tests
  - [ ]* 10.1 Write property test for non-zero relationships with 2+ concepts
    - **Property 10: Chunks with 2+ concepts and model server produce non-zero relationships**
    - **Validates: Requirements 5.5**

  - [ ]* 10.2 Write unit tests for graceful degradation scenarios
    - Test model server unavailable → extraction still produces pattern + ConceptNet relationships
    - Test ConceptNet validator unavailable → raw concepts pass through
    - Test Neo4j unavailable → raises error
    - Test legacy chunk without segment metadata → falls back to full-content extraction
    - Test response with no citations → no CITED_SOURCE concepts
    - Test empty message group → no segments, no PROMPTED_BY edges
    - _Requirements: 1.3, 2.3, 6.1, 6.2, 6.3, 6.5_

  - [ ]* 10.3 Write integration test for full pipeline with mocked services
    - Test end-to-end: message group → chunking with segments → extraction with all three methods → deduplication → persist
    - Verify concept and relationship counts match expectations
    - Verify endpoint response model unchanged
    - _Requirements: 5.1, 5.5, 6.5_

- [ ] 11. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- All test files go in `tests/components/test_conversation_kg_quality.py` (property + unit) and `tests/integration/test_conversation_kg_pipeline.py` (integration)
- The implementation reuses existing extractors (`ConceptExtractor`, `RelationshipExtractor`, `ConceptNetValidator`) rather than duplicating logic
