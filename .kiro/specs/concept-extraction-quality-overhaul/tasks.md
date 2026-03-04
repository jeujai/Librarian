# Implementation Plan: Concept Extraction Quality Overhaul

## Overview

Replace the low-quality regex-based concept extraction with spaCy NER + curated regex patterns, add a local ConceptNet validation gate in Neo4j, and wire the new pipeline into the existing Celery processing chain. Tasks are ordered so each builds on the previous, with property tests close to the code they validate.

## Tasks

- [x] 1. Create ConceptNet import script and data model
  - [x] 1.1 Create `scripts/import_conceptnet.py` with `ConceptNetImporter` class
    - Implement `parse_conceptnet_uri()` to convert `/c/en/some_concept` to normalized lowercase name with spaces
    - Implement `import_assertions()` that reads the ConceptNet 5.7 CSV (gzipped), filters to `/c/en/` URIs, and batch-imports into Neo4j using `UNWIND` + `MERGE` Cypher queries with `:ConceptNetConcept` and `:ConceptNetRelation` labels
    - Implement `create_indexes()` for `:ConceptNetConcept(name)` and `:ConceptNetConcept(uri)`
    - Add `ImportStats` dataclass tracking concepts_imported, relationships_imported, duplicates_skipped, errors, duration_seconds
    - Add CLI entry point with `--neo4j-uri`, `--neo4j-user`, `--neo4j-password`, `--file-path`, `--batch-size` arguments
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [ ]* 1.2 Write property tests for ConceptNet parsing and normalization
    - **Property 1: ConceptNet CSV Parsing Round-Trip**
    - **Property 2: ConceptNet Name Normalization**
    - **Validates: Requirements 1.1, 1.4**

  - [ ]* 1.3 Write property test for import idempotence
    - **Property 3: Import Idempotence**
    - **Validates: Requirements 1.5**

- [x] 2. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Refactor ConceptExtractor to use spaCy NER and remove junk patterns
  - [x] 3.1 Remove ENTITY, PROCESS, and PROPERTY patterns from `ConceptExtractor.concept_patterns` in `kg_builder.py`
    - Delete the `ENTITY`, `PROCESS`, and `PROPERTY` keys and their pattern lists
    - Keep `CODE_TERM`, `MULTI_WORD`, and `ACRONYM` patterns unchanged
    - Rename `extract_concepts_ner()` to `extract_concepts_regex()` to reflect its new scope (regex-only)
    - Update all internal callers of `extract_concepts_ner()` to use `extract_concepts_regex()`
    - _Requirements: 2.2, 2.3_

  - [x] 3.2 Add async NER extraction method to `ConceptExtractor`
    - Add `extract_concepts_with_ner(self, text: str) -> List[ConceptNode]` that calls `ModelServerClient.get_entities([text])`
    - Convert each spaCy entity dict `{"text": ..., "label": ..., "start": ..., "end": ...}` into a `ConceptNode` with `concept_type` set to the spaCy label and `confidence` of 0.85
    - Handle model server unavailability by returning empty list and logging a warning
    - _Requirements: 2.1, 2.5, 2.4_

  - [x] 3.3 Add combined async extraction method `extract_all_concepts_async()`
    - Combine results from `extract_concepts_with_ner()` and `extract_concepts_regex()`
    - Deduplicate by normalized concept name, keeping the higher-confidence entry
    - If model server is unavailable, result is regex-only with a logged warning
    - _Requirements: 2.1, 2.3, 2.4, 2.6_

  - [ ]* 3.4 Write property tests for extraction pipeline
    - **Property 4: No Junk Concept Types Produced**
    - **Property 5: Curated Regex Patterns Retained**
    - **Property 6: NER Label Preserved as Concept Type**
    - **Validates: Requirements 2.2, 2.3, 2.5**

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement ConceptNet validation gate
  - [x] 5.1 Create `src/multimodal_librarian/components/knowledge_graph/conceptnet_validator.py`
    - Implement `ConceptNetValidator` class that takes a `Neo4jClient` instance
    - Implement `lookup_concept(name: str)` that runs a case-insensitive Cypher query: `MATCH (c:ConceptNetConcept) WHERE toLower(c.name) = toLower($name) RETURN c`
    - Implement `get_relationships_for_concepts(concept_names: List[str])` that batch-fetches ConceptNet relationships between known concepts
    - Implement `validate_concepts(candidates: List[ConceptNode]) -> ValidationResult` with the three-tier filtering logic:
      - Tier 1: concept exists in ConceptNet → keep + pull relationships
      - Tier 2: concept is NER entity type (ORG, PERSON, GPE, etc.) → keep as domain entity
      - Tier 3: concept is CODE_TERM, MULTI_WORD, or ACRONYM → keep
      - Otherwise → discard
    - Return `ValidationResult` with validated concepts, ConceptNet relationships, and counts
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [ ]* 5.2 Write property tests for validation gate
    - **Property 7: Validation Gate Filtering**
    - **Property 8: Real Relationships Replace RELATED_TO**
    - **Property 9: Case-Insensitive ConceptNet Lookup**
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

- [x] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Wire new pipeline into KnowledgeGraphBuilder and Celery
  - [x] 7.1 Update `KnowledgeGraphBuilder.process_knowledge_chunk_async()` in `kg_builder.py`
    - Replace call to `extract_concepts_from_content_async()` with `concept_extractor.extract_all_concepts_async()`
    - After extraction, instantiate `ConceptNetValidator` with the Neo4j client and call `validate_concepts()` on the candidates
    - Use validated concepts and ConceptNet relationships for persistence instead of co-occurrence RELATED_TO
    - Still run `RelationshipExtractor.extract_relationships_pattern()` for IS_A, PART_OF, CAUSES patterns (these are real semantic patterns, not co-occurrence)
    - Remove the co-occurrence relationship creation from `RelationshipExtractor.extract_relationships_llm()` (the sentence-level co-occurrence loop)
    - _Requirements: 4.1, 4.2, 4.4_

  - [x] 7.2 Update `_update_knowledge_graph()` in `celery_service.py`
    - Ensure the `KnowledgeGraphBuilder` instance used in the Celery task has access to the Neo4j client for ConceptNet validation
    - Add fallback handling: if Neo4j ConceptNet data is unavailable, skip validation and use raw extraction results with a warning
    - Verify model server fallback works in Celery context (model server client initialization already handles this)
    - _Requirements: 4.1, 4.2, 4.3, 4.5_

  - [ ]* 7.3 Write integration tests for the full pipeline
    - Test end-to-end: text input → NER + regex extraction → ConceptNet validation → persistence
    - Test model server unavailable fallback produces only MULTI_WORD/CODE_TERM/ACRONYM concepts
    - Test that persisted relationships use ConceptNet types instead of RELATED_TO
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties
- Unit tests validate specific examples and edge cases
- The ConceptNet import script (task 1.1) must be run once before the validation gate can function — this is a data prerequisite, not a code dependency
