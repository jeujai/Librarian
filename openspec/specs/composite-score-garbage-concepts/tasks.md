# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Garbage Concepts Pass Through Edge Discovery
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate garbage concepts are not filtered
  - **Scoped PBT Approach**: Use Hypothesis to generate concept names matching garbage patterns (PDF artifacts with `?`, `+`, `=`; hyphenation breaks like `"sec- tion"`; generic phrases like `"less than"`; table refs like `"Table 15.2"`; time expressions like `"10 years"`; stage labels like `"stage 2"`; citations like `"et al."`) and concept pairs where both have NULL concept_type
  - Write a property-based test that:
    - Constructs mock Neo4j query results containing garbage concept names and/or NULL concept_type pairs
    - Calls the post-query filtering logic from `_discover_cross_doc_edges`
    - Asserts that garbage pairs are EXCLUDED from the returned candidates list
  - Test the `_is_garbage_concept_name` static method (will not exist yet on unfixed code — test the filtering gap directly)
  - Test the concept_type gate: pairs where both concepts have NULL concept_type should be excluded
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (garbage concepts pass through unfiltered, confirming the bug exists)
  - Document counterexamples found (e.g., `"? Weight"` with NULL types appears in candidates, `"less than"` appears in candidates)
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Legitimate Domain Concepts Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Observe behavior on UNFIXED code for non-buggy inputs:
    - Observe: valid multi-token domain concepts (e.g., `"machine learning"` with concept_type `"TOPIC"`) pass through edge discovery
    - Observe: UMLS-typed concepts (e.g., `"Disease or Syndrome"`) pass through edge discovery
    - Observe: trusted NER-typed concepts (e.g., `"ORG"`, `"PERSON"`) pass through edge discovery
    - Observe: per-edge scoring formula produces identical results for qualifying edges
  - Write property-based tests using Hypothesis:
    - Generate random multi-token concept names (alphabetic words joined by spaces, no garbage patterns) with at least one `DOMAIN_CONCEPT_TYPES` type → verify they pass through filtering
    - Generate random `(concept_type_a, concept_type_b)` pairs where at least one is in `DOMAIN_CONCEPT_TYPES` → verify the type gate allows them
    - Generate random edge data for non-garbage concepts → verify `_compute_edge_score` produces identical results
  - Verify tests PASS on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [x] 3. Fix garbage concept filtering in `_discover_cross_doc_edges`

  - [x] 3.1 Add `_is_garbage_concept_name` static method and class constants
    - Add `GARBAGE_PHRASES` frozenset class constant containing known generic filler phrases: `"less than"`, `"more than"`, `"more than two"`, `"information about"`, `"such as"`, `"as well"`, `"due to"`, `"based on"`, `"according to"`, `"in order"`, `"at least"`, `"up to"`, `"each of"`, `"one of"`
    - Add `_GARBAGE_PATTERNS` class constant: list of pre-compiled regex patterns for PDF artifacts (`[?+=]` adjacent to word boundaries), hyphenation breaks (`\w+- \w+`), table/figure references (`^(table|figure|fig)\s+\d`), time expressions (`^\d+\s+(years?|days?|months?|weeks?|hours?|minutes?)$`), stage/phase labels (`^(stage|phase|step|grade|level|type)\s+\d`), citations (`\bet\s+al\.?$`)
    - Add `_is_garbage_concept_name(name: str) -> bool` static method that checks the name against `GARBAGE_PHRASES` (exact match, case-insensitive) and `_GARBAGE_PATTERNS` (regex match)
    - _Bug_Condition: isBugCondition(src_name, tgt_name, src_type, tgt_type) where isGarbageName(src_name) OR isGarbageName(tgt_name)_
    - _Expected_Behavior: When isGarbageName returns True for either concept name, the pair is excluded from candidates_
    - _Preservation: Legitimate domain concept names (no garbage patterns) return False from _is_garbage_concept_name_
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 3.2 Modify Cypher overlap query to return concept_type
    - Add `c1.concept_type AS src_type` and `c2.concept_type AS tgt_type` to the RETURN clause of the overlap query in `_discover_cross_doc_edges`
    - Also add `c1.name AS src_name` and `c2.name AS tgt_name` if not already present (verify they are returned)
    - _Bug_Condition: concept_type is not available for filtering in the current query results_
    - _Expected_Behavior: Query results include src_type and tgt_type fields for each candidate pair_
    - _Preservation: Query structure, Phase 2 cosine similarity, deduplication, and per-target-doc capping remain unchanged_
    - _Requirements: 2.5, 2.6_

  - [x] 3.3 Add post-query filtering in the deduplication/capping loop
    - In the loop inside `_discover_cross_doc_edges` that processes query results, after extracting record fields:
      1. Call `_is_garbage_concept_name(src_name)` and `_is_garbage_concept_name(tgt_name)` — skip candidate if either returns True
      2. Check concept types: if both `src_type` and `tgt_type` are NULL or not in `DOMAIN_CONCEPT_TYPES`, skip the candidate
    - _Bug_Condition: isBugCondition(src_name, tgt_name, src_type, tgt_type) where both type checks fail or either name is garbage_
    - _Expected_Behavior: Candidates matching the bug condition are excluded from the returned list_
    - _Preservation: Non-garbage candidates with at least one DOMAIN_CONCEPT_TYPES type pass through unchanged_
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 3.4 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Garbage Concepts Excluded from Edge Discovery
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior (garbage concepts excluded)
    - When this test passes, it confirms garbage concepts are now properly filtered
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 3.5 Verify preservation tests still pass
    - **Property 2: Preservation** - Legitimate Domain Concepts Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all tests still pass after fix (no regressions)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [x] 4. Checkpoint - Ensure all tests pass
  - Run full test suite to confirm no regressions
  - Verify bug condition exploration test passes (garbage concepts excluded)
  - Verify preservation tests pass (legitimate domain concepts unchanged)
  - Ensure all tests pass, ask the user if questions arise
