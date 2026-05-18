# Implementation Plan: Concept-Aware Bridge Recovery

## Overview

Surgical modifications to `framework.py`, `bridge_generator.py`, and `config.py` to make the bridge generation pipeline concept-aware when boundary shifting cannot resolve concept bisections. All changes are backward-compatible. No new services or DI providers.

## Tasks

- [x] 1. Add configuration settings and UnresolvedBisection data class
  - [x] 1.1 Add `enable_concept_recovery_bridges` and `recovery_bridge_context_chars` fields to `Settings` in `src/multimodal_librarian/config.py`
    - Add `enable_concept_recovery_bridges: bool = Field(default=True, env="ENABLE_CONCEPT_RECOVERY_BRIDGES")`
    - Add `recovery_bridge_context_chars: int = Field(default=400, env="RECOVERY_BRIDGE_CONTEXT_CHARS")`
    - Both with descriptive docstrings
    - _Requirements: 6.1, 6.3_

  - [x] 1.2 Add `UnresolvedBisection` dataclass to `framework.py`
    - Fields: `concept_name: str`, `concept_confidence: float`, `boundary_index: int`, `chunk_before_id: str`, `chunk_after_id: str`
    - Place alongside existing `ProcessedChunk` and `ChunkChangeMapping` dataclasses
    - _Requirements: 1.1_

- [x] 2. Record unresolved bisections during boundary adjustment
  - [x] 2.1 Modify `_adjust_boundary_for_concept_contiguity` in `framework.py` to accept an optional `unresolved_bisections: Optional[List[UnresolvedBisection]] = None` parameter
    - When multiple spanning concepts exist and only the highest-confidence one is resolved, append `UnresolvedBisection` entries for all remaining spanning concepts
    - When the best concept cannot be resolved (both forward and backward shifts fail), append an `UnresolvedBisection` for the best concept too
    - When `unresolved_bisections` is `None`, skip all recording (backward compatibility)
    - When no concepts span the boundary, do not create any records
    - _Requirements: 1.1, 1.2, 1.4_

  - [x] 2.2 Modify `_perform_primary_chunking` in `framework.py` to pass an `unresolved_bisections` list to `_adjust_boundary_for_concept_contiguity` and accumulate results
    - Create a `Dict[int, List[UnresolvedBisection]]` keyed by chunk boundary index (index of chunk pair)
    - After each chunk is created and its ID is known, back-fill `chunk_before_id` and `chunk_after_id` on the bisection records
    - Return the bisections dict alongside the chunks list (modify return type to tuple or add as attribute)
    - _Requirements: 1.3_

  - [ ]* 2.3 Write property test for unresolved bisection recording (Property 1)
    - **Property 1: Unresolved bisections are recorded for all concepts not resolved by boundary shifting**
    - Use hypothesis to generate overlap zones with planted multi-word concepts at boundary positions, with varying max_chunk_size constraints
    - Verify the unresolved_bisections list contains entries for all concepts not resolved by the shift
    - Verify concept_name and concept_confidence are correct on each entry
    - **Validates: Requirements 1.1, 1.2, 1.4**

- [x] 3. Augment bridge prompts with bisected concepts
  - [x] 3.1 Add optional `bisected_concepts: Optional[List[str]] = None` field to `BridgeGenerationRequest` dataclass in `bridge_generator.py`
    - _Requirements: 2.4_

  - [x] 3.2 Modify `create_adaptive_prompt` in `bridge_generator.py` to accept optional `bisected_concepts` parameter and append concept-preservation instruction block when non-empty
    - When `bisected_concepts` is non-empty, append "CRITICAL" instruction block listing each concept verbatim
    - When `bisected_concepts` is None or empty, produce the standard prompt unchanged
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 3.3 Modify `generate_bridge` in `bridge_generator.py` to accept optional `bisected_concepts` parameter and thread it through to `BridgeGenerationRequest` and `create_adaptive_prompt`
    - _Requirements: 2.4_

  - [x] 3.4 Modify `_generate_single_bridge` in `bridge_generator.py` to pass `bisected_concepts` from the request to `create_adaptive_prompt`
    - _Requirements: 2.1_

  - [ ]* 3.5 Write property test for augmented bridge prompt (Property 2)
    - **Property 2: Augmented bridge prompt contains all bisected concepts verbatim**
    - Use hypothesis to generate lists of concept name strings
    - Verify each concept name appears as a substring in the returned prompt
    - Verify empty/None bisected_concepts produces a prompt without the "CRITICAL" keyword
    - **Validates: Requirements 2.1, 2.2, 2.3**

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Add concept-recovery bridge prompt and generation
  - [x] 5.1 Add `create_recovery_prompt` method to `SmartBridgeGenerator` in `bridge_generator.py`
    - Use `recovery_bridge_context_chars` from settings for context window size (default 400)
    - Use `_extract_chunk_end` and `_extract_chunk_start` with the wider context window
    - Include each bisected concept verbatim in the prompt with explicit preservation instructions
    - Handle chunks shorter than the context window by using full chunk text
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [ ]* 5.2 Write property test for recovery prompt (Property 5)
    - **Property 5: Recovery prompt uses wider context window and includes all target concepts**
    - Use hypothesis to generate chunk texts and bisected concept lists
    - Verify context excerpts are at least `recovery_bridge_context_chars` long (or full chunk if shorter)
    - Verify every bisected concept name appears verbatim in the prompt
    - **Validates: Requirements 4.1, 4.2, 4.4**

- [x] 6. Integrate concept-recovery logic into chunk_with_smart_bridges
  - [x] 6.1 Modify `chunk_with_smart_bridges` in `framework.py` to receive unresolved bisections from `_perform_primary_chunking` and pass bisected concepts to `batch_generate_bridges` for standard bridge augmentation
    - Thread `unresolved_bisections_by_boundary` from primary chunking through to bridge generation
    - For each boundary in `bridge_needed`, look up bisected concepts and pass them to the bridge generator
    - Modify `batch_generate_bridges` to accept optional `bisected_concepts_per_boundary` dict
    - _Requirements: 2.1, 3.1_

  - [x] 6.2 Add concept-recovery bridge generation step in `chunk_with_smart_bridges` after standard bridge generation
    - For each boundary with unresolved bisections: check if a standard bridge exists and covers all concepts (case-insensitive substring match)
    - If concepts are missing, generate a concept-recovery bridge using `generate_bridge` with the missing concepts
    - Set recovery bridge metadata: `is_recovery_bridge=True`, `target_bisected_concepts`, `adjacent_chunk_ids`
    - Append recovery bridges to the bridges list
    - Gate behind `enable_concept_recovery_bridges` setting
    - _Requirements: 3.1, 3.2, 3.4, 3.5, 5.3, 6.2_

  - [x] 6.3 Ensure concept-recovery bridges go through concept extraction (existing Step 6 in pipeline)
    - Verify the existing bridge concept extraction loop processes recovery bridges identically to standard bridges
    - Recovery bridges should get `extracted_concepts` and `adjacent_chunk_ids` in metadata
    - _Requirements: 5.1, 5.2_

  - [ ]* 6.4 Write property test for recovery bridge generation (Property 3)
    - **Property 3: Recovery bridges are generated for all uncovered bisections**
    - Use hypothesis to generate scenarios with unresolved bisections and standard bridge texts that may or may not contain the bisected concepts
    - Verify recovery bridges are generated when concepts are missing, and not generated when all concepts are covered
    - **Validates: Requirements 3.1, 3.2, 3.5**

  - [ ]* 6.5 Write property test for recovery bridge metadata (Property 4)
    - **Property 4: Recovery bridge metadata is complete**
    - Use hypothesis to generate recovery bridge scenarios
    - Verify metadata contains `is_recovery_bridge=True`, non-empty `target_bisected_concepts`, and `adjacent_chunk_ids` with exactly two IDs
    - **Validates: Requirements 3.4, 5.2**

  - [ ]* 6.6 Write property test for feature toggle (Property 6)
    - **Property 6: Feature toggle disables all recovery bridge generation**
    - Use hypothesis to generate inputs with unresolved bisections
    - With `enable_concept_recovery_bridges=False`, verify zero recovery bridges in output
    - With `enable_concept_recovery_bridges=True`, verify recovery bridges are present when expected
    - **Validates: Requirements 6.1, 6.2**

- [x] 7. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests use `hypothesis` with `max_examples=100`
- All changes are backward-compatible modifications to existing files
- No new services or DI providers are introduced
- All threshold values are empirical starting points for tuning via retrieval quality metrics feedback loop
- The `bisected_concepts` parameter is optional everywhere to preserve backward compatibility with existing callers
