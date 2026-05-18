# Implementation Plan: KG Concept Resolution Quality

## Overview

Surgical changes to three existing files to fix concept extraction gaps and reranking dilution. No new services or components. All changes are backward-compatible modifications.

## Tasks

- [x] 1. Add CODE_TERM patterns to ConceptExtractor
  - [x] 1.1 Add CODE_TERM regex patterns to `concept_patterns` dict in `ConceptExtractor.__init__`
    - Add 6 patterns: snake_case, camelCase, PascalCase, param assignment, function calls, dotted identifiers
    - Patterns go in a new `'CODE_TERM'` key in `self.concept_patterns`
    - No changes to `extract_concepts_ner()` method body — existing loop handles new category automatically
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

  - [ ]* 1.2 Write property tests for code term extraction
    - **Property 1: Code term extraction**
    - Use hypothesis to generate random snake_case, camelCase, PascalCase, param assignments, function calls, and dotted identifiers
    - Embed generated terms in filler text, run `extract_concepts_ner()`, verify concept with matching name and `CODE_TERM` type exists
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6**

  - [ ]* 1.3 Write property tests for backward compatibility
    - **Property 2: Existing pattern backward compatibility**
    - Use hypothesis to generate proper nouns, gerunds, and abstract nouns
    - Verify existing ENTITY, PROCESS, PROPERTY patterns still extract correctly after CODE_TERM addition
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4**

  - [ ]* 1.4 Write unit tests for specific code term examples
    - Test extraction of `allow_dangerous_code`, `getData()`, `os.path.join`, `allowed_dangerous_code=True`, `ConnectionManager`
    - Test edge cases: empty text, text with no code terms, very long identifiers
    - Test overlapping pattern matches (term matching both CODE_TERM and existing category)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.7_

- [x] 2. Checkpoint - Verify concept extraction
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Implement hop-distance-aware scoring and related chunk capping
  - [x] 3.1 Add `hop_distance_decay` and `max_related_chunks` parameters to `KGRetrievalService.__init__`
    - Add `hop_distance_decay: float = 0.5` parameter
    - Add `max_related_chunks: int = 50` parameter
    - Store as instance attributes `self._hop_distance_decay` and `self._max_related_chunks`
    - _Requirements: 2.2, 3.1_

  - [x] 3.2 Modify `_aggregate_and_deduplicate()` to apply hop-distance decay and cap related chunks
    - Update method signature to accept `source_mappings: Dict[str, ChunkSourceMapping]`
    - Set `kg_relevance_score = 1.0` for direct chunks
    - Sort related chunks by hop_distance ascending before adding
    - Apply `kg_relevance_score = self._hop_distance_decay ** hop_distance` for related chunks
    - Cap related chunks at `self._max_related_chunks`
    - Default to `hop_distance=1` if mapping not found for a chunk
    - _Requirements: 2.1, 2.2, 3.1, 3.2, 3.3_

  - [x] 3.3 Update `_stage1_kg_retrieval()` to pass `source_mappings` to `_aggregate_and_deduplicate()`
    - Pass the `source_mappings` dict that is already computed in `_stage1_kg_retrieval`
    - _Requirements: 2.1, 2.2_

  - [ ]* 3.4 Write property tests for hop-distance decay scoring
    - **Property 3: Hop-distance decay scoring**
    - Use hypothesis to generate random hop_distance (0-5) and decay_factor (0.1-1.0)
    - Verify `kg_relevance_score == decay_factor ** hop_distance` for each chunk
    - Verify direct chunks (hop_distance=0) always get score 1.0
    - **Validates: Requirements 2.1, 2.2**

  - [ ]* 3.5 Write property tests for related chunk capping
    - **Property 5: Related chunk capping with hop-distance priority**
    - Generate lists of related chunks with random hop distances and varying max_related_chunks
    - Verify output contains at most max_related_chunks related chunks
    - Verify retained chunks have the lowest hop_distance values
    - **Validates: Requirements 3.1, 3.2**

  - [ ]* 3.6 Write property tests for direct chunk guarantee
    - **Property 6: Direct chunks always included**
    - Generate random mixes of direct and related chunks
    - Verify all direct chunks appear in aggregated output regardless of max_related_chunks
    - **Validates: Requirements 3.3**

  - [ ]* 3.7 Write property test for hop-distance tiebreaking
    - **Property 4: Hop-distance tiebreaking in ranking**
    - Generate pairs of chunks with equal semantic scores but different hop distances
    - Run through `_calculate_final_score()` and verify the lower hop_distance chunk scores higher
    - **Validates: Requirements 2.3, 2.4**

  - [ ]* 3.8 Write unit tests for aggregation edge cases
    - Test empty direct chunks list, empty related chunks list, all chunks direct
    - Test max_related_chunks=0 (no related chunks included)
    - Test scoring: hop=0 → 1.0, hop=1 → 0.5, hop=2 → 0.25, hop=3 → 0.125
    - _Requirements: 2.1, 2.2, 3.1, 3.2, 3.3_

- [x] 4. Checkpoint - Verify scoring and capping
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Update ChunkSourceMapping relevance score
  - [x] 5.1 Update `get_relevance_score()` in ChunkSourceMapping to accept configurable decay factor
    - Change method signature to `get_relevance_score(self, decay_factor: float = 0.5)`
    - Change formula from `0.7 ** self.hop_distance` to `decay_factor ** self.hop_distance`
    - Clamp decay_factor to range (0.0, 1.0]
    - _Requirements: 5.3_

  - [ ]* 5.2 Write property test for ChunkSourceMapping serialization round-trip
    - **Property 7: ChunkSourceMapping serialization round-trip**
    - Use hypothesis to generate random ChunkSourceMapping instances (random hop_distance, concept IDs, retrieval sources)
    - Verify `from_dict(to_dict(mapping))` produces equivalent object
    - Verify `get_relevance_score()` returns same value before and after round-trip
    - **Validates: Requirements 5.1, 5.2**

  - [ ]* 5.3 Write unit tests for ChunkSourceMapping edge cases
    - Test get_relevance_score with decay_factor=0.5, 0.7, 1.0
    - Test hop_distance=0 always returns 1.0 regardless of decay_factor
    - Test serialization includes hop_distance field
    - _Requirements: 5.1, 5.2, 5.3_

- [x] 6. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests use hypothesis with minimum 100 iterations
- No new files are created for production code — all changes are to existing files
- Test files: `tests/components/test_concept_extractor_code_terms.py`, `tests/components/test_kg_aggregation_hop_scoring.py`, `tests/models/test_chunk_source_mapping_roundtrip.py`
