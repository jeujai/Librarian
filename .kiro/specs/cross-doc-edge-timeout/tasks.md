# Implementation Plan: Cross-Document Edge Discovery Timeout

## Overview

Replace the single monolithic Cypher query in `_discover_cross_doc_edges()` with a two-phase approach: (1) structural discovery without cosine similarity, capped with LIMIT, processing 1 target doc at a time, and (2) targeted cosine similarity computation only for the capped candidate pairs. All changes are scoped to `_discover_cross_doc_edges()` in `composite_score_engine.py`.

## Tasks

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Monolithic Query Timeout on Large Document Pairs
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: Scope the property to the concrete failing case: a source document with thousands of concepts and a single target document with thousands of concepts, where the monolithic query combines traversal + cosine similarity in one pass
  - Write a property-based test (Hypothesis) that:
    - Mocks `execute_query` to simulate Neo4j behavior: raise `TransactionTimedOutClientConfiguration`-style exception when the query contains both the MATCH traversal pattern AND `gds.similarity.cosine` in a single query string, for concept counts above a threshold
    - For non-timeout queries (e.g., the `other_docs_query`), return realistic mock data
    - Calls `_discover_cross_doc_edges()` with a document_id that has high concept counts
    - Asserts that the method returns actual edges (non-empty list) rather than silently swallowing timeouts and returning zero edges
  - Bug Condition from design: `isBugCondition(input)` where `traversal_rows > THRESHOLD AND cosine_computations > 0` — the single query combines unbounded traversal with cosine computation
  - Expected Behavior: the method should complete within timeout and return discovered edges
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (the monolithic query triggers the timeout mock, all batches fail, zero edges returned — confirming the bug)
  - Document counterexamples found to understand root cause
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Return Schema and Edge Deduplication Behavior
  - **IMPORTANT**: Follow observation-first methodology
  - **IMPORTANT**: Write and run these tests BEFORE implementing the fix
  - Observe behavior on UNFIXED code for non-buggy inputs (small concept counts where the query completes):
    - Observe: `_discover_cross_doc_edges()` returns `List[dict]` where each dict has keys `src_id`, `src_doc`, `tgt_id`, `tgt_doc`, `rel_type`, `cn_weight`, `embedding_similarity`
    - Observe: duplicate edges (same `src_id`, `tgt_id`, `rel_type` triple) are deduplicated via the `seen` set
    - Observe: conversation documents are excluded from target_doc_ids
    - Observe: per-target-doc edge count is capped at MAX_EDGES_PER_TARGET_DOC (200)
  - Write property-based tests (Hypothesis) capturing observed behavior:
    - For all mock query results with valid edge data, every returned dict has exactly the 7 required keys with correct types (str for IDs, str for rel_type, float-compatible for cn_weight and embedding_similarity)
    - For all inputs with duplicate (src_id, tgt_id, rel_type) triples in query results, the output contains each triple at most once
    - For all inputs where conversation doc IDs are present, those IDs never appear as tgt_doc in results
    - `_compute_edge_score()` produces identical `EdgeScore` objects for the same edge dict inputs (downstream pipeline preservation)
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [x] 3. Implement two-phase discovery fix in `_discover_cross_doc_edges()`

  - [x] 3.1 Replace monolithic batch query with Phase 1 structural discovery query
    - In `_discover_cross_doc_edges()` in `src/multimodal_librarian/services/composite_score_engine.py`
    - Remove the existing `batch_query` that combines MATCH traversal with `gds.similarity.cosine()`
    - Add Phase 1 query: MATCH the same pattern `(ch1:Chunk {source_id: $doc_id})<-[:EXTRACTED_FROM]-(c1:Concept)-[r]-(c2:Concept)-[:EXTRACTED_FROM]->(ch2:Chunk {source_id: $tgt_doc})` with `WHERE type(r) IN $rel_types`
    - Return only scalar properties: `c1.concept_id AS src_id`, `c2.concept_id AS tgt_id`, `type(r) AS rel_type`, `r.weight AS cn_weight`
    - Add `LIMIT $edge_cap` after the MATCH/WHERE to allow Neo4j early termination instead of computing all matches before slicing
    - Process 1 target doc at a time (no UNWIND $tgt_docs) — change BATCH_SIZE from 3 to 1
    - _Bug_Condition: isBugCondition(input) where single query combines traversal + cosine for large concept counts_
    - _Expected_Behavior: Phase 1 completes within 120s by avoiding cosine computation and using LIMIT for early termination_
    - _Preservation: Same relationship types, same edge cap per target doc_
    - _Requirements: 2.1, 2.2, 2.4_

  - [x] 3.2 Add Phase 2 cosine similarity computation for candidate pairs
    - After Phase 1 collects candidate pairs, run a separate Cypher query to compute `gds.similarity.cosine()` only for those specific concept-pair IDs
    - Phase 2 query: `UNWIND $pairs AS pair MATCH (c1:Concept {concept_id: pair.src_id}) MATCH (c2:Concept {concept_id: pair.tgt_id})` then compute cosine similarity with the same CASE/WHEN null-check logic as the original query
    - Batch Phase 2 queries efficiently (e.g., 200 pairs per query, matching edge_cap)
    - Merge Phase 2 cosine results back into the candidate edge dicts
    - For pairs where cosine cannot be computed (missing embeddings), default to `embedding_similarity = 0.0`
    - _Bug_Condition: Original query computed cosine for every traversal match; Phase 2 computes only for capped candidates_
    - _Expected_Behavior: Cosine computation bounded to at most MAX_EDGES_PER_TARGET_DOC pairs per target doc_
    - _Preservation: Same cosine similarity values for the same concept pairs; same null-handling logic_
    - _Requirements: 2.4_

  - [x] 3.3 Add per-target-doc timing and logging
    - Log elapsed time for each target document's Phase 1 + Phase 2 discovery
    - Use `time.time()` around each target doc's processing loop iteration
    - Log at INFO level: target doc ID, edge count found, elapsed seconds
    - _Requirements: 2.1_

  - [x] 3.4 Preserve return schema and deduplication logic
    - Ensure the returned `List[dict]` has the same keys: `src_id`, `src_doc`, `tgt_id`, `tgt_doc`, `rel_type`, `cn_weight`, `embedding_similarity`
    - Keep the `seen` set deduplication on `(src_id, tgt_id, rel_type)` triples
    - Keep conversation document exclusion logic unchanged
    - Do NOT modify `_compute_edge_score()`, `_aggregate_document_pairs()`, or `_persist_related_docs()`
    - _Preservation: Return schema, deduplication, conversation exclusion, downstream pipeline all unchanged_
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [x] 3.5 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Monolithic Query Timeout on Large Document Pairs
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior (method returns edges, not zero)
    - With the two-phase approach, the mock timeout on monolithic queries is no longer triggered because the queries are split
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms the fix avoids the timeout condition)
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 3.6 Verify preservation tests still pass
    - **Property 2: Preservation** - Return Schema and Edge Deduplication Behavior
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions in schema, deduplication, conversation exclusion, or downstream scoring)
    - Confirm all tests still pass after fix (no regressions)

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- All code changes are scoped to `_discover_cross_doc_edges()` in `src/multimodal_librarian/services/composite_score_engine.py`
- The project uses pytest with Hypothesis for property-based testing
- Mock `execute_query` to simulate Neo4j behavior in tests (no live Neo4j required for unit/property tests)
- The downstream pipeline (`_compute_edge_score`, `_aggregate_document_pairs`, `_persist_related_docs`) must not be modified
