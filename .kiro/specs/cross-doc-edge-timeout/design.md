# Cross-Document Edge Discovery Timeout Bugfix Design

## Overview

The `_discover_cross_doc_edges()` method in `CompositeScoreEngine` times out on every batch because its Cypher query performs an unbounded traversal: all source-document concepts × 13 relationship types × all target-document concepts, with `gds.similarity.cosine()` computed for every matched pair. With ~7,700 source concepts and thousands of target concepts per document, the combinatorial explosion exceeds the 120-second Neo4j transaction timeout on every batch of 3 target documents.

The fix replaces the single monolithic query with a two-phase approach: (1) a cheap structural discovery query that finds concept pairs connected by qualifying relationships without computing cosine similarity, and (2) a targeted similarity computation pass that only evaluates cosine for the capped candidate set. Additionally, the batch size is reduced from 3 target documents to 1 to further bound the traversal scope per transaction.

## Glossary

- **Bug_Condition (C)**: The query execution condition where the Cypher pattern match traverses all source concepts × all relationship types × all target concepts AND computes cosine similarity for every pair, causing the transaction to exceed 120 seconds
- **Property (P)**: Each single-target-doc discovery query completes within the Neo4j transaction timeout (120s) and returns discovered cross-document edges where they exist
- **Preservation**: The downstream scoring pipeline (edge scoring, aggregation, filtering, RELATED_DOCS persistence) must produce identical results for the same set of discovered edges
- **`_discover_cross_doc_edges()`**: The method in `composite_score_engine.py` that queries Neo4j for cross-document concept pairs involving a given document
- **`batch_query`**: The Cypher query string inside `_discover_cross_doc_edges()` that performs the pattern match and cosine computation
- **BATCH_SIZE**: Number of target documents processed per Cypher query (currently 3)
- **`edge_cap` / MAX_EDGES_PER_TARGET_DOC**: Maximum edges sampled per target document (200)
- **Two-phase discovery**: Approach where structural edge discovery (cheap) is separated from cosine similarity computation (expensive)

## Bug Details

### Bug Condition

The bug manifests when `_discover_cross_doc_edges()` executes its batch Cypher query against a source document with thousands of concepts and target documents that also have thousands of concepts. The single MATCH pattern `(ch1:Chunk)<-[:EXTRACTED_FROM]-(c1:Concept)-[r]-(c2:Concept)-[:EXTRACTED_FROM]->(ch2:Chunk)` creates a combinatorial explosion of intermediate rows, and computing `gds.similarity.cosine()` on 384-dimensional embedding vectors for every matched pair adds significant per-row cost. The combination exceeds the 120-second transaction timeout for every batch.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type {source_doc_id, target_doc_ids[], rel_types[], edge_cap}
  OUTPUT: boolean

  source_concept_count := countConceptsForDocument(input.source_doc_id)
  target_concept_counts := [countConceptsForDocument(t) FOR t IN input.target_doc_ids]

  // The traversal fan-out is the product of source concepts, relationship
  // types, and target concepts across all batched target docs
  traversal_rows := source_concept_count
                    * len(input.rel_types)
                    * SUM(target_concept_counts)

  // Each row also requires a 384-dim cosine similarity computation
  cosine_computations := traversal_rows

  RETURN traversal_rows > THRESHOLD_FOR_120S_TIMEOUT
         AND cosine_computations > 0
         AND len(input.target_doc_ids) >= 1
END FUNCTION
```

### Examples

- **Source doc with 7,700 concepts, 3 target docs with ~4,000 concepts each**: Traversal produces ~7,700 × 13 × 12,000 = ~1.2 billion candidate rows before filtering. Query times out at 120s. Zero edges returned.
- **Source doc with 7,700 concepts, 1 target doc with 7,700 concepts**: Traversal produces ~7,700 × 13 × 7,700 = ~770 million candidate rows. Still times out at 120s.
- **Source doc with 50 concepts, 3 target docs with 50 concepts each**: Traversal produces ~50 × 13 × 150 = ~97,500 rows. Completes in <1s. This case works correctly today.
- **Source doc with 3,000 concepts, 1 target doc with 3,000 concepts**: Traversal produces ~3,000 × 13 × 3,000 = ~117 million rows. Borderline — may or may not complete within 120s depending on how many pairs actually have connecting relationships (the 117M is the upper bound; actual matches are far fewer, but Neo4j must still evaluate the pattern).

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- The three-signal edge scoring formula (`type_weight × 0.4 + embedding_similarity × 0.45 + cn_weight × 0.15`) must continue to produce identical scores for the same edge inputs
- The aggregation pipeline (`MIN_EDGE_SCORE`, `MIN_EMBEDDING_SIMILARITY`, `MIN_EDGES_FOR_PAIR` filters, geometric-mean density) must remain unchanged
- RELATED_DOCS edges must continue to be upserted bidirectionally with representative concepts
- Conversation documents must continue to be excluded from both source and target roles
- The same 13 qualifying relationship types must be used
- Per-target-doc edge capping at MAX_EDGES_PER_TARGET_DOC (200) must still be enforced
- The `_compute_edge_score()`, `_aggregate_document_pairs()`, and `_persist_related_docs()` methods must not be modified

**Scope:**
All code outside of `_discover_cross_doc_edges()` should be completely unaffected by this fix. The method's return type (`List[dict]`) and the schema of each returned dict (`src_id`, `src_doc`, `tgt_id`, `tgt_doc`, `rel_type`, `cn_weight`, `embedding_similarity`) must remain identical so downstream consumers are unaware of the internal query restructuring.

## Hypothesized Root Cause

Based on the bug description and code analysis, the root cause is a combination of:

1. **Unbounded traversal fan-out in a single MATCH**: The pattern `(ch1:Chunk {source_id: $doc_id})<-[:EXTRACTED_FROM]-(c1:Concept)-[r]-(c2:Concept)-[:EXTRACTED_FROM]->(ch2:Chunk {source_id: tgt_doc})` requires Neo4j to evaluate all possible paths from every source concept through every qualifying relationship to every target concept. Even though many paths won't match (concepts aren't fully connected), the planner must still explore the search space. With 7,700 source concepts and 13 relationship types, the fan-out at the `c1-[r]-c2` step is enormous.

2. **Cosine similarity computed for every matched pair**: `gds.similarity.cosine()` on 384-dimensional float arrays is non-trivial per invocation. When multiplied by hundreds of thousands or millions of matched pairs, this adds seconds to minutes of pure computation time inside the transaction.

3. **Batching 3 target documents multiplies the problem**: The `UNWIND $tgt_docs` with 3 target docs triples the traversal scope within a single transaction, pushing an already-borderline query well past the timeout.

4. **No early termination or intermediate LIMIT**: The query computes ALL matching pairs before the `collect()[0..$edge_cap]` slice. The cap only applies after the full traversal completes, so it doesn't reduce the work done by the query engine.

## Correctness Properties

Property 1: Bug Condition - Single-Target Discovery Completes Within Timeout

_For any_ input where a source document has N concepts (N ≤ 10,000) and a single target document has M concepts (M ≤ 10,000), the fixed `_discover_cross_doc_edges` method SHALL complete the discovery query for that target document within the Neo4j transaction timeout (120 seconds) by using a two-phase approach that separates structural discovery from cosine similarity computation.

**Validates: Requirements 2.1, 2.2, 2.4**

Property 2: Preservation - Edge Schema and Downstream Pipeline Unchanged

_For any_ set of discovered cross-document edges, the fixed `_discover_cross_doc_edges` method SHALL return dicts with the same schema (`src_id`, `src_doc`, `tgt_id`, `tgt_doc`, `rel_type`, `cn_weight`, `embedding_similarity`) and the downstream scoring, aggregation, and persistence pipeline SHALL produce the same results as the original code would for the same edge set.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `src/multimodal_librarian/services/composite_score_engine.py`

**Method**: `_discover_cross_doc_edges()`

**Specific Changes**:

1. **Replace single monolithic query with two-phase approach**:
   - **Phase 1 — Structural Discovery**: A Cypher query that finds concept pairs connected by qualifying relationships between source and target documents, returning only scalar properties (`concept_id`, `rel_type`, `cn_weight`). No cosine similarity computation. Add a `LIMIT` clause to cap intermediate results per target doc before `collect()`.
   - **Phase 2 — Cosine Similarity**: A separate Cypher query that takes the discovered concept-pair IDs and computes `gds.similarity.cosine()` only for those specific pairs. This bounds the number of cosine computations to at most `MAX_EDGES_PER_TARGET_DOC` per target document.

2. **Reduce batch size from 3 to 1 target document per query**: Each Phase 1 query processes a single target document. This eliminates the `UNWIND $tgt_docs` multiplier and keeps the traversal scope to source_concepts × rel_types × single_target_concepts.

3. **Add LIMIT to Phase 1 discovery query**: Insert a `LIMIT` clause (e.g., `LIMIT $edge_cap`) after the MATCH/WHERE to allow Neo4j to stop traversal early once enough candidates are found, rather than computing all matches before slicing with `collect()[0..$edge_cap]`.

4. **Batch Phase 2 cosine queries efficiently**: Collect all candidate pairs from Phase 1 across multiple target docs, then compute cosine similarity in batches of concept-pair IDs (e.g., 200 pairs per query). This keeps each cosine query small and fast.

5. **Add per-target-doc timing and logging**: Log the elapsed time for each target document's discovery to help diagnose any remaining slow queries and to provide visibility into the distribution of query times.

6. **Preserve the return schema**: Ensure the returned `List[dict]` has the same keys (`src_id`, `src_doc`, `tgt_id`, `tgt_doc`, `rel_type`, `cn_weight`, `embedding_similarity`) so `_compute_edge_score()` and all downstream code works without modification.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that execute `_discover_cross_doc_edges()` against a Neo4j instance with realistic data volumes (thousands of concepts per document) and observe the timeout failures. Alternatively, mock the `execute_query` method to simulate timeout behavior based on query parameters.

**Test Cases**:
1. **Large Document Timeout Test**: Call `_discover_cross_doc_edges()` with a source document that has 5,000+ concepts and target documents with 3,000+ concepts. Observe that the batch query raises a timeout exception (will fail on unfixed code).
2. **Batch Size Amplification Test**: Compare execution time with BATCH_SIZE=1 vs BATCH_SIZE=3 for the same source/target pair. Observe that BATCH_SIZE=3 is disproportionately slower (will fail on unfixed code).
3. **Cosine Computation Cost Test**: Run the batch query with and without the `gds.similarity.cosine()` call to isolate the cost of cosine computation on large result sets (will fail on unfixed code).
4. **All-Batches-Fail Test**: Run the full discovery loop for a large document and verify that every batch times out, resulting in zero total edges (will fail on unfixed code).

**Expected Counterexamples**:
- Every batch of 3 target documents times out at 120s with zero results
- The timeout occurs in the MATCH traversal phase, not in the collect/return phase
- Possible causes: unbounded traversal fan-out, cosine computation on all pairs, batch size multiplier

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := _discover_cross_doc_edges_fixed(input.source_doc_id)
  ASSERT result completes within 120s per target document
  ASSERT result contains edges where cross-doc relationships exist
  ASSERT each edge has valid schema (src_id, src_doc, tgt_id, tgt_doc, rel_type, cn_weight, embedding_similarity)
  ASSERT len(edges_per_target_doc) <= MAX_EDGES_PER_TARGET_DOC
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT _discover_cross_doc_edges_original(input) = _discover_cross_doc_edges_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for small documents (where the query completes successfully), then write property-based tests capturing that behavior and verifying the fixed code produces equivalent results.

**Test Cases**:
1. **Small Document Preservation**: Run discovery for documents with <100 concepts on both unfixed and fixed code. Verify the same edges are returned (possibly in different order).
2. **Edge Schema Preservation**: Verify that every returned edge dict has exactly the keys `src_id`, `src_doc`, `tgt_id`, `tgt_doc`, `rel_type`, `cn_weight`, `embedding_similarity` with correct types.
3. **Edge Cap Preservation**: Verify that no more than MAX_EDGES_PER_TARGET_DOC edges are returned per target document.
4. **Conversation Exclusion Preservation**: Verify that conversation documents are still excluded from both source and target roles.
5. **Scoring Pipeline Preservation**: Feed the same edge dicts into `_compute_edge_score()` and verify identical `EdgeScore` objects are produced.

### Unit Tests

- Test Phase 1 structural discovery query returns concept pairs without cosine similarity
- Test Phase 2 cosine computation query returns correct similarity values for given concept-pair IDs
- Test that single-target-doc processing produces correct results
- Test edge deduplication via the `seen` set
- Test conversation document exclusion logic
- Test edge cap enforcement (≤200 per target doc)
- Test handling of missing embeddings (should produce `embedding_similarity = 0.0`)

### Property-Based Tests

- Generate random document configurations (varying concept counts, relationship densities) and verify the two-phase approach returns edges with valid schema
- Generate random edge dicts and verify `_compute_edge_score()` produces identical results (preservation of downstream pipeline)
- Generate random sets of EdgeScores and verify `_aggregate_document_pairs()` produces identical results (preservation of aggregation)

### Integration Tests

- Test full `compute_composite_scores()` flow with the fixed discovery method against a Neo4j instance with realistic data
- Test that RELATED_DOCS edges are actually created for documents that have cross-doc relationships
- Test that the total discovery time for a large document is reasonable (minutes, not 26+ minutes of timeouts)
