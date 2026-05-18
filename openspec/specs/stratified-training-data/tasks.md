# Implementation Plan: Stratified Training Data

## Overview

Thread a `semantic_types: Optional[List[str]]` parameter from the CLI through the API, Celery task config, `TrainingDataGenerator`, and into `RAGQAStrategy`, where it controls which UMLS semantic types are iterated during seed question generation. When provided, the budget is split evenly across the included types with remainder distributed to the first types in the list. When omitted, existing behavior (all 28 types) is preserved.

## Tasks

- [x] 1. Add `semantic_types` field to TrainingDataConfig
  - [x] 1.1 Add `semantic_types: Optional[List[str]] = None` field to the `TrainingDataConfig` dataclass in `src/multimodal_librarian/ml/models.py`
    - Import `Optional` and `List` from `typing` if not already imported
    - Place the field after the existing fields with default `None`
    - _Requirements: 1.1, 1.4, 6.1_

  - [ ]* 1.2 Write property test for TrainingDataConfig serialization round-trip
    - **Property 3: TrainingDataConfig serialization round-trip**
    - Use Hypothesis to generate random `TrainingDataConfig` instances with `semantic_types` as `None` or random subsets of `CLINICAL_SEMANTIC_TYPES`
    - Assert `TrainingDataConfig(**asdict(config))` produces an equivalent instance
    - **Validates: Requirements 6.1**

  - [ ]* 1.3 Write unit tests for TrainingDataConfig defaults
    - Test that `semantic_types` defaults to `None`
    - Test that the field accepts a list of strings
    - _Requirements: 1.1, 1.4_

- [x] 2. Modify RAGQAStrategy to accept and use `semantic_types`
  - [x] 2.1 Modify `generate_seed_questions` to accept `semantic_types: Optional[List[str]] = None`
    - Resolve active type list: `active_types = semantic_types if semantic_types else CLINICAL_SEMANTIC_TYPES`
    - Treat empty list `[]` the same as `None` (fall back to all types)
    - Compute per-type budgets for both UMLS and template sources
    - Pass `semantic_types` to `_generate_umls_concept_seeds` and `_generate_template_seeds`
    - Add logging of active inclusion list, per-type budget, and per-type seed counts using `collections.Counter`
    - _Requirements: 1.2, 1.3, 4.1, 4.2, 4.3, 4.4, 4.5, 7.1, 7.2_

  - [x] 2.2 Modify `_generate_umls_concept_seeds` to accept `semantic_types: Optional[List[str]] = None`
    - Use `active_types = semantic_types if semantic_types else CLINICAL_SEMANTIC_TYPES`
    - Compute `per_type_limit = max(budget // len(active_types), 5)`
    - Iterate over `active_types` instead of `CLINICAL_SEMANTIC_TYPES`
    - _Requirements: 4.3, 4.4_

  - [x] 2.3 Modify `_generate_template_seeds` to accept `semantic_types: Optional[List[str]] = None`
    - Forward `semantic_types` to `_fetch_concept_names_for_templates`
    - _Requirements: 5.1_

  - [x] 2.4 Modify `_fetch_concept_names_for_templates` to accept `semantic_types: Optional[List[str]] = None`
    - Use `active_types = semantic_types if semantic_types else CLINICAL_SEMANTIC_TYPES`
    - Compute `per_type = max(limit // len(active_types), 3)`
    - Shuffle and iterate over `active_types` instead of `CLINICAL_SEMANTIC_TYPES`
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 2.5 Modify `generate` method to accept `semantic_types: Optional[List[str]] = None` and forward to `generate_seed_questions`
    - Add `semantic_types` parameter after `target_count`
    - Pass `semantic_types=semantic_types` to `self.generate_seed_questions(seed_count, semantic_types=semantic_types)`
    - _Requirements: 6.3, 6.4_

  - [ ]* 2.6 Write property test for inclusion list restricts seed semantic types
    - **Property 1: Inclusion list restricts seed semantic types**
    - Use Hypothesis to generate random non-empty subsets of `CLINICAL_SEMANTIC_TYPES` and random `target_count` (10–500)
    - Mock Neo4j client to return deterministic concept records keyed by semantic type
    - Assert every `SeedQuestion.semantic_type` is a member of the provided subset
    - **Validates: Requirements 1.3, 4.3, 5.1, 6.4**

  - [ ]* 2.7 Write property test for stratified budget allocation sums to target
    - **Property 2: Stratified budget allocation sums to target**
    - Use Hypothesis to generate random `target_count` (1–10000) and random non-empty type lists (1–28 elements)
    - Assert per-type base = `target_count // len(types)`, remainder distributed to first types, total = `target_count`
    - **Validates: Requirements 4.1, 4.2, 4.4, 5.2**

  - [ ]* 2.8 Write unit tests for RAGQAStrategy semantic_types behavior
    - Test `None` uses all 28 `CLINICAL_SEMANTIC_TYPES`
    - Test empty list `[]` falls back to all types
    - Test logging includes per-type counts and active list
    - Test `generate` forwards `semantic_types` to `generate_seed_questions`
    - _Requirements: 1.2, 4.5, 7.1, 7.2_

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Modify TrainingDataGenerator to pass `semantic_types` to RAGQAStrategy
  - [x] 4.1 Update `_run_rag_strategy` in `src/multimodal_librarian/ml/training_data_generator.py`
    - Pass `semantic_types=config.semantic_types` to `strategy.generate()`
    - _Requirements: 6.2_

  - [ ]* 4.2 Write unit test for generator forwarding
    - Mock `RAGQAStrategy.generate` and verify it is called with `semantic_types` from config
    - _Requirements: 6.2_

- [x] 5. Modify CLI to pass `semantic_types` in API payload and skip Step 3a
  - [x] 5.1 Update `step_generate` in `scripts/run-training-pipeline.py`
    - When `semantic_types` is provided (non-None, non-empty), add `"semantic_types": semantic_types` to the API request payload
    - When `semantic_types` is provided, skip the Step 3a post-hoc filtering block entirely
    - When `semantic_types` is not provided, omit the field from the payload (existing behavior)
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [ ]* 5.2 Write unit tests for CLI payload and filtering behavior
    - Test payload contains `semantic_types` when provided
    - Test payload omits `semantic_types` when `None`
    - Test Step 3a is skipped when `semantic_types` is provided
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 6. Verify API router accepts `semantic_types` field
  - [x] 6.1 Confirm `TrainingDataRequest` in the API router accepts `semantic_types: Optional[List[str]] = None`
    - If not already present, add the field to the Pydantic request model
    - Ensure `config_dict` conditionally includes `semantic_types` when provided
    - _Requirements: 3.1, 3.2, 3.3_

  - [ ]* 6.2 Write unit tests for API request model
    - Test model validates with and without `semantic_types` field
    - Test `config_dict` includes `semantic_types` when provided
    - Test `config_dict` omits `semantic_types` when not provided
    - _Requirements: 3.1, 3.2, 3.3_

- [x] 7. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples, wiring, and edge cases
- The implementation language is Python (matching the existing codebase and design document)
- Hypothesis is already available in the project (`.hypothesis/` directory exists)
