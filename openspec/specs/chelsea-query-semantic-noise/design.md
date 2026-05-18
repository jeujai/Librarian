# Chelsea Query Semantic Noise Bugfix Design

## Overview

The Chelsea query ("What did our team observe at Chelsea?") returns irrelevant results because two interacting defects amplify semantic noise. First, `_find_semantic_matches()` returns up to 20 concept matches with a permissive similarity threshold (0.75), allowing generic verb-derived concepts like "we observe" (sim=0.8369) and "we saw" (sim=0.8288) to flood the match set alongside the relevant "Chelsea" concept (sim=0.8454). Second, `_aggregate_and_deduplicate()` applies a `coverage_bonus = log2(num_concepts) * 0.1` that rewards chunks matching many concepts — so chunks from computer vision textbooks matching 8 generic observation concepts get a +0.3 bonus while the Chelsea-specific chunk matching only 1 concept gets +0.0.

The fix addresses both sides: (1) filter and cap semantic matches to remove generic/low-specificity concepts, and (2) make coverage scoring resilient to generic concept inflation by weighting the bonus based on concept specificity.

## Glossary

- **Bug_Condition (C)**: The condition where `_find_semantic_matches()` returns generic verb-derived concepts (e.g., "we observe", "we saw", "scrutinized") alongside specific named-entity concepts, AND `_aggregate_and_deduplicate()` amplifies those generic matches via coverage_bonus
- **Property (P)**: The desired behavior where semantic matches are filtered to a focused set of specific concepts, and coverage scoring does not allow generic concept count to outweigh named-entity relevance
- **Preservation**: Existing behavior for queries without generic verb noise, multi-concept coverage bonus for genuinely distinct concepts, lexical fallback, and related-chunk hop-distance decay must remain unchanged
- **`_find_semantic_matches()`**: Method in `src/multimodal_librarian/components/kg_retrieval/query_decomposer.py` that embeds the query and performs vector similarity search against Neo4j concept embeddings, returning up to `semantic_max_results` matches above `similarity_threshold`
- **`_aggregate_and_deduplicate()`**: Method in `src/multimodal_librarian/services/kg_retrieval_service.py` that scores and deduplicates chunks using concept-coverage scoring with `coverage_bonus = log2(num_matched_concepts) * 0.1`
- **Semantic Match**: A concept returned by vector similarity search with a `similarity_score` and `match_type="semantic"`
- **Generic Concept**: A concept whose name is a common verb phrase or observation word (e.g., "we observe", "we saw", "scrutinized") rather than a specific named entity or topic
- **Coverage Bonus**: The `log2(num_concepts) * 0.1` additive score boost applied to chunks matching multiple distinct concepts

## Bug Details

### Bug Condition

The bug manifests when a query contains both a specific named entity (e.g., "Chelsea") and common observation verbs (e.g., "observe", "saw", "found"). The `_find_semantic_matches()` method returns up to 20 matches with `similarity_threshold=0.75`, which is permissive enough to include many generic verb-derived concepts. These noisy concepts then fan out via EXTRACTED_FROM edges to hundreds of irrelevant chunks, and `_aggregate_and_deduplicate()` rewards those chunks with inflated coverage_bonus scores.

**Formal Specification:**
```
FUNCTION isBugCondition(query, semantic_matches, chunk_scores)
  INPUT: query of type str, semantic_matches of type List[Dict], chunk_scores of type Dict[str, float]
  OUTPUT: boolean

  generic_concepts := [m for m in semantic_matches
                       WHERE m.name matches common verb/observation patterns
                       AND m.match_type == "semantic"]
  specific_concepts := [m for m in semantic_matches
                        WHERE m.name contains proper nouns or specific entities]

  RETURN len(generic_concepts) > len(specific_concepts)
         AND any chunk scored via coverage_bonus from generic_concepts
             ranks above chunks scored via specific_concepts
END FUNCTION
```

### Examples

- Query "What did our team observe at Chelsea?" returns 20 semantic matches: "Chelsea" (sim=0.8454), "we observe" (sim=0.8369), "we saw" (sim=0.8288), "scrutinized" (sim=0.8246), plus 16 more generic concepts. A computer vision textbook chunk matching 8 of these generic concepts gets `coverage_bonus = log2(8) * 0.1 = 0.3`, while the GenLang book page 114 chunk matching only "Chelsea" gets `coverage_bonus = log2(1) * 0.1 = 0.0`. The irrelevant chunk ranks higher.
- Query "What did our team find about Venezuela?" would similarly return generic concepts like "we found", "discovered", "identified" alongside "Venezuela", inflating irrelevant chunks.
- Query "Tell me about Neo4j" (no generic verbs) works correctly because all semantic matches are specific to Neo4j — no generic verb noise to inflate coverage_bonus.
- Query "Compare Chelsea and Venezuela observations" should still benefit from coverage_bonus for chunks matching both "Chelsea" AND "Venezuela" (genuinely distinct concepts), but not from generic observation verbs.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Queries containing only specific named entities (e.g., "Tell me about Neo4j") must continue to return correctly ranked results with no change in semantic match quality
- Multi-concept queries where all matched concepts are genuinely distinct (e.g., "Chelsea" + "Venezuela") must continue to receive coverage_bonus for chunks at their intersection
- Lexical fallback when semantic matching is unavailable (no model server) must continue to work
- `has_kg_matches=False` signaling for queries with no matching concepts must continue to work
- Related chunks from relationship traversal must continue to receive hop-distance-decayed scores capped at `_max_related_chunks`
- The embedding cache in `_find_semantic_matches()` must continue to function for deterministic results

**Scope:**
All inputs that do NOT involve generic verb-derived concepts dominating the semantic match set should be completely unaffected by this fix. This includes:
- Queries with only specific named entities
- Queries where semantic matching is unavailable
- Queries with no KG matches
- Related chunk scoring and capping logic

## Hypothesized Root Cause

Based on the bug description, the most likely issues are:

1. **Overly Permissive Semantic Match Parameters**: `_find_semantic_matches()` uses `semantic_max_results=20` and `similarity_threshold=0.75`. For queries containing common English verbs, many generic concepts in the knowledge graph (extracted from observation-heavy academic text) have embeddings close to the query embedding. The threshold is too low and the cap too high to filter them out.

2. **No Specificity Filtering on Semantic Results**: `_find_semantic_matches()` returns all results above the similarity threshold without any filtering for concept specificity. Generic verb phrases like "we observe" and "we saw" pass through with high similarity scores because the query literally contains those words.

3. **Coverage Bonus Treats All Concepts Equally**: `_aggregate_and_deduplicate()` computes `coverage_bonus = log2(num_concepts) * 0.1` using a raw count of distinct concept names. It does not distinguish between specific named-entity concepts and generic verb-derived concepts. A chunk matching 8 generic concepts gets the same bonus as one matching 8 genuinely distinct topic concepts.

4. **Multiplicative Noise Amplification**: The two defects interact multiplicatively. More noisy semantic matches → more EXTRACTED_FROM chunk fan-out → more chunks with high generic concept counts → higher coverage_bonus → irrelevant chunks outranking relevant ones. Fixing either side alone would reduce the problem, but fixing both eliminates it.

## Correctness Properties

Property 1: Bug Condition - Semantic Match Filtering Removes Generic Concepts

_For any_ query where the bug condition holds (isBugCondition returns true — i.e., generic verb-derived concepts outnumber specific concepts in the raw semantic match set), the fixed `_find_semantic_matches()` SHALL return a filtered set where generic verb-derived concepts are removed or deprioritized, and the total match count is capped at a reasonable limit (e.g., 5-8), ensuring specific named-entity concepts dominate the result set.

**Validates: Requirements 2.1, 2.4**

Property 2: Preservation - Non-Noisy Query Behavior Unchanged

_For any_ query where the bug condition does NOT hold (isBugCondition returns false — i.e., the query contains only specific named entities with no generic verb noise), the fixed `_find_semantic_matches()` and `_aggregate_and_deduplicate()` SHALL produce the same ranked results as the original functions, preserving all existing scoring, coverage_bonus, and chunk ordering behavior.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `src/multimodal_librarian/components/kg_retrieval/query_decomposer.py`

**Function**: `_find_semantic_matches()`

**Specific Changes**:
1. **Reduce Default `semantic_max_results`**: Lower from 20 to 8 (or a configurable value) to limit the raw number of semantic matches before any filtering. This reduces the surface area for generic concept noise.

2. **Raise Default `similarity_threshold`**: Increase from 0.75 to 0.80 (or a configurable value) to filter out lower-confidence matches that are more likely to be generic verb-derived concepts.

3. **Add Specificity Filter**: After retrieving semantic matches, apply a post-filter that identifies and removes generic verb-derived concepts. This can use a heuristic based on:
   - Concept name overlap with the `ACTION_WORDS` set (already defined in the module)
   - Concept name length (very short generic phrases like "we saw" are likely noise)
   - Concept type metadata (if available — ENTITY types are more specific than TOPIC types)

4. **Add Similarity Score Gap Detection**: If there is a significant gap between the top match's similarity score and lower matches, truncate at the gap. This naturally separates the "Chelsea" concept (sim=0.8454) from the cluster of generic concepts (sim=0.82-0.84).

**File**: `src/multimodal_librarian/services/kg_retrieval_service.py`

**Function**: `_aggregate_and_deduplicate()`

**Specific Changes**:
5. **Weight Coverage Bonus by Concept Specificity**: Instead of treating all concepts equally in the coverage_bonus calculation, weight each concept's contribution by a specificity factor. Concepts with `match_type="semantic"` and names matching generic verb patterns should contribute less (or zero) to the coverage count. This prevents generic concept accumulation from inflating scores.

   Proposed formula change:
   ```
   # Before: num_concepts = len(distinct_names)
   # After:  num_concepts = count of distinct names that pass specificity filter
   specific_names = {name for name in distinct_names if not is_generic_concept(name)}
   num_concepts = len(specific_names) if specific_names else len(distinct_names)
   ```

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that construct realistic semantic match sets (with generic verb concepts and specific entity concepts) and pass them through `_aggregate_and_deduplicate()` to observe the scoring behavior. Run these tests on the UNFIXED code to observe that generic concept accumulation inflates coverage_bonus.

**Test Cases**:
1. **Generic Concept Inflation Test**: Create chunk_concept_hits where one chunk matches 8 generic concepts ("we observe", "we saw", etc.) and another matches 1 specific concept ("Chelsea"). Assert that the generic chunk scores higher on unfixed code (will fail on unfixed code — i.e., the bug is confirmed).
2. **Semantic Match Count Test**: Mock `_find_semantic_matches()` with a query containing observation verbs and assert it returns >10 matches including generic concepts (will confirm the noise on unfixed code).
3. **Coverage Bonus Disparity Test**: Compute coverage_bonus for varying numbers of generic vs specific concepts and assert the disparity (will fail on unfixed code).
4. **End-to-End Ranking Test**: With mocked Neo4j data, run the Chelsea query and assert that irrelevant chunks rank above Chelsea-specific chunks (will fail on unfixed code).

**Expected Counterexamples**:
- Chunks matching 8 generic observation concepts score 0.3+ higher than chunks matching 1 specific entity concept
- Possible causes: no specificity filtering in `_find_semantic_matches()`, equal weighting in coverage_bonus calculation

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL (query, semantic_matches) WHERE isBugCondition(query, semantic_matches) DO
  filtered_matches := _find_semantic_matches_fixed(query)
  ASSERT len(filtered_matches) <= semantic_max_results_cap
  ASSERT count_generic(filtered_matches) < count_specific(filtered_matches)

  chunk_scores := _aggregate_and_deduplicate_fixed(chunks, filtered_matches)
  ASSERT chunk_with_specific_entity.score >= chunk_with_only_generic_concepts.score
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL (query, semantic_matches) WHERE NOT isBugCondition(query, semantic_matches) DO
  ASSERT _find_semantic_matches_original(query) == _find_semantic_matches_fixed(query)
  ASSERT _aggregate_and_deduplicate_original(chunks) == _aggregate_and_deduplicate_fixed(chunks)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for queries without generic verb noise, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Named Entity Query Preservation**: Observe that queries like "Tell me about Neo4j" produce correct results on unfixed code, then verify the fix does not change those results
2. **Multi-Concept Coverage Preservation**: Observe that chunks matching multiple genuinely distinct concepts (no generic verbs) receive correct coverage_bonus on unfixed code, then verify the fix preserves this
3. **Lexical Fallback Preservation**: Observe that when semantic matching is unavailable, lexical fallback works on unfixed code, then verify the fix does not affect this path
4. **Related Chunk Scoring Preservation**: Observe that related chunks receive hop-distance-decayed scores on unfixed code, then verify the fix does not change this

### Unit Tests

- Test `_find_semantic_matches()` with queries containing observation verbs — assert filtered result count and absence of generic concepts
- Test `_find_semantic_matches()` with entity-only queries — assert results unchanged
- Test `_aggregate_and_deduplicate()` with mixed generic/specific concept hits — assert specific entity chunks score higher
- Test `_aggregate_and_deduplicate()` with only specific concept hits — assert coverage_bonus still applies correctly
- Test edge cases: empty semantic matches, single match, all matches generic, all matches specific

### Property-Based Tests

- Generate random queries with varying mixes of named entities and observation verbs, run through `_find_semantic_matches()`, and assert the filtered result count is bounded and generic concepts are deprioritized
- Generate random chunk_concept_hits with varying numbers of generic vs specific concepts, run through `_aggregate_and_deduplicate()`, and assert that chunks with specific entity matches always score >= chunks with only generic matches
- Generate random queries with only specific named entities (no verbs), run through both original and fixed functions, and assert identical output (preservation)

### Integration Tests

- Test the full Chelsea query end-to-end with mocked Neo4j and model server, asserting GenLang book page 114 content ranks in top results
- Test a multi-concept query ("Compare Chelsea and Venezuela") end-to-end, asserting coverage_bonus correctly rewards intersection chunks
- Test fallback behavior when semantic matching is unavailable, asserting lexical fallback produces reasonable results
