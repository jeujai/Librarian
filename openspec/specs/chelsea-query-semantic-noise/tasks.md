# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Semantic Noise Inflates Coverage Bonus for Generic Concepts
  - **CRITICAL**: This test MUST FAIL on unfixed code — failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior — it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate generic verb-derived concepts inflate coverage_bonus and outrank specific entity matches
  - **Scoped PBT Approach**: Scope the property to the concrete failing case: queries containing both a specific named entity (e.g., "Chelsea") and common observation verbs (e.g., "observe", "saw"), where generic verb-derived concepts outnumber specific concepts in the semantic match set
  - Create test file `tests/services/test_chelsea_semantic_noise_bug_condition.py`
  - Use Hypothesis with strategies generating:
    - Semantic match sets containing 1 specific entity concept (e.g., "Chelsea", sim≥0.84) and N generic verb-derived concepts (e.g., "we observe", "we saw", "scrutinized", sim 0.75-0.84) where N > 1
    - Chunk-concept-hit mappings where one chunk matches only the specific entity and another chunk matches multiple generic concepts
  - Test that `_aggregate_and_deduplicate()` on UNFIXED code assigns higher `kg_relevance_score` to chunks matching many generic concepts than to chunks matching the specific entity (confirming the bug via coverage_bonus disparity)
  - Assert the EXPECTED (fixed) behavior: chunks matching specific named-entity concepts SHALL score >= chunks matching only generic verb-derived concepts
  - Test that `_find_semantic_matches()` with `semantic_max_results=20` and `similarity_threshold=0.75` returns >5 generic verb-derived concepts for observation-verb queries (confirming permissive parameters)
  - Run test on UNFIXED code — expect FAILURE (this confirms the bug exists)
  - Document counterexamples found (e.g., "chunk matching 8 generic concepts scores 0.3+ higher than chunk matching 1 specific entity")
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Non-Noisy Query Behavior Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Create test file `tests/services/test_chelsea_semantic_noise_preservation.py`
  - Observe on UNFIXED code: queries with only specific named entities (no generic verb phrases) produce correctly ranked results
  - Observe on UNFIXED code: `_aggregate_and_deduplicate()` with only specific concept hits applies coverage_bonus correctly (e.g., 2 genuinely distinct concepts → `log2(2)*0.1 = 0.1` bonus)
  - Observe on UNFIXED code: lexical fallback works when `_model_server_client` is None
  - Observe on UNFIXED code: `has_kg_matches=False` when no concepts match
  - Observe on UNFIXED code: related chunks receive hop-distance-decayed scores capped at `_max_related_chunks`
  - Write property-based tests using Hypothesis:
    - **Named Entity Query Preservation**: For all queries containing only specific named entities (no observation verbs), `_find_semantic_matches()` returns the same results before and after fix
    - **Multi-Concept Coverage Preservation**: For all chunk-concept-hit sets where all matched concepts are genuinely distinct (not generic verb phrases), `_aggregate_and_deduplicate()` applies the same coverage_bonus formula `log2(num_concepts) * 0.1`
    - **Lexical Fallback Preservation**: When `_model_server_client` is None, lexical fallback behavior is unchanged
    - **Related Chunk Scoring Preservation**: Related chunks continue to receive `hop_distance_decay ** hop` scores, capped at `_max_related_chunks`
  - Verify all tests PASS on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 3. Fix for Chelsea query semantic noise — generic concepts inflate coverage_bonus

  - [x] 3.1 Implement specificity filtering and parameter tightening in `_find_semantic_matches()`
    - In `src/multimodal_librarian/components/kg_retrieval/query_decomposer.py`:
    - Reduce default `semantic_max_results` from 20 to 8 to limit raw semantic match count
    - Raise default `similarity_threshold` from 0.75 to 0.80 to filter low-confidence matches
    - Add a post-filter after vector search results that identifies and removes generic verb-derived concepts:
      - Check concept name overlap with the `ACTION_WORDS` set already defined in the module
      - Filter short generic phrases (e.g., "we observe", "we saw") where all words are common verbs/pronouns
      - Preserve concepts that contain proper nouns or specific entity names
    - Add similarity score gap detection: if there is a significant gap (e.g., >0.02) between the top match and a cluster of lower matches, truncate at the gap to naturally separate specific concepts from generic noise
    - _Bug_Condition: isBugCondition(query, semantic_matches) where generic verb-derived concepts outnumber specific concepts in the match set_
    - _Expected_Behavior: filtered set where generic concepts are removed, total count capped at ~5-8, specific named-entity concepts dominate_
    - _Preservation: Queries with only specific named entities must return identical results; lexical fallback unchanged_
    - _Requirements: 1.1, 1.4, 2.1, 2.4, 3.1, 3.3_

  - [x] 3.2 Implement weighted coverage bonus by concept specificity in `_aggregate_and_deduplicate()`
    - In `src/multimodal_librarian/services/kg_retrieval_service.py`:
    - Modify the coverage_bonus calculation in `_aggregate_and_deduplicate()` to weight each concept's contribution by specificity
    - Add an `is_generic_concept()` helper that identifies generic verb-derived concept names (using ACTION_WORDS overlap, short common-word phrases, etc.)
    - Change the formula from `num_concepts = len(distinct_names)` to `num_concepts = len(specific_names)` where `specific_names` excludes generic concepts
    - Fallback: if all concepts are generic (edge case), use the original `len(distinct_names)` to avoid zero-bonus
    - _Bug_Condition: coverage_bonus = log2(num_generic_concepts) * 0.1 inflates irrelevant chunk scores_
    - _Expected_Behavior: coverage_bonus only counts specific concepts, so chunks matching only generic concepts get reduced or zero bonus_
    - _Preservation: Chunks matching only genuinely distinct specific concepts receive the same coverage_bonus as before_
    - _Requirements: 1.2, 1.3, 2.2, 2.3, 3.2, 3.5_

  - [x] 3.3 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Semantic Noise Filtering Removes Generic Concepts
    - **IMPORTANT**: Re-run the SAME test from task 1 — do NOT write a new test
    - The test from task 1 encodes the expected behavior
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1: `pytest tests/services/test_chelsea_semantic_noise_bug_condition.py -v`
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 3.4 Verify preservation tests still pass
    - **Property 2: Preservation** - Non-Noisy Query Behavior Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - Run preservation property tests from step 2: `pytest tests/services/test_chelsea_semantic_noise_preservation.py -v`
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all tests still pass after fix (no regressions)

- [x] 4. Checkpoint - Ensure all tests pass
  - Run full test suite: `pytest tests/services/test_chelsea_semantic_noise_bug_condition.py tests/services/test_chelsea_semantic_noise_preservation.py -v`
  - Verify both bug condition and preservation tests pass
  - Run existing kg_retrieval_service tests to confirm no regressions: `pytest tests/services/test_kg_retrieval_service.py -v`
  - Ensure all tests pass, ask the user if questions arise.
