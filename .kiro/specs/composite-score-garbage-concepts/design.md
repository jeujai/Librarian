# Composite Score Garbage Concepts Bugfix Design

## Overview

The `CompositeScoreEngine._discover_cross_doc_edges` method produces false positive cross-document relationships by matching on garbage concepts — PDF extraction artifacts, hyphenation breaks, generic filler phrases, table references, time expressions, stage/phase labels, and citations. These garbage concepts share identical `name_lower` values across documents and pass through the current filter (which only requires `name CONTAINS ' '`). Because they often have `NULL` concept_type and identical string content, they receive 1.0 cosine similarity, inflating document-pair scores. The fix adds a two-layer filter: (1) a regex-based garbage name filter applied in Python post-query, and (2) a concept_type gate requiring at least one concept in a matched pair to have a non-null type from `DOMAIN_CONCEPT_TYPES`.

## Glossary

- **Bug_Condition (C)**: A cross-document concept pair where at least one concept name matches a garbage pattern OR both concepts have NULL concept_type — these pairs should be excluded from edge discovery
- **Property (P)**: When the bug condition holds, the pair is excluded from the candidates list returned by `_discover_cross_doc_edges`
- **Preservation**: All existing behavior for legitimate domain concepts (valid multi-token names with at least one non-null concept_type) must remain unchanged
- **`_discover_cross_doc_edges`**: The method in `composite_score_engine.py` that runs the Cypher overlap query and returns candidate edge dicts
- **`_is_garbage_concept_name`**: New static method that returns True if a concept name matches any garbage pattern
- **`DOMAIN_CONCEPT_TYPES`**: Existing frozenset of concept types considered genuinely domain-specific (UMLS types, trusted NER types, TOPIC)

## Bug Details

### Bug Condition

The bug manifests when garbage concept names pass through the `_discover_cross_doc_edges` method's only filter (`c1.name CONTAINS ' '`). These garbage names are multi-token strings that originate from PDF extraction noise, not from genuine domain concepts. Additionally, concept pairs where both concepts have NULL `concept_type` are never filtered, allowing any string match to become a cross-document edge.

**Formal Specification:**
```
FUNCTION isBugCondition(src_name, tgt_name, src_concept_type, tgt_concept_type)
  INPUT: src_name: string, tgt_name: string, src_concept_type: string|null, tgt_concept_type: string|null
  OUTPUT: boolean

  // Layer 1: Garbage name patterns
  IF isGarbageName(src_name) OR isGarbageName(tgt_name) THEN
    RETURN TRUE
  END IF

  // Layer 2: Both concepts lack domain-specific type
  IF src_concept_type IS NULL AND tgt_concept_type IS NULL THEN
    RETURN TRUE
  END IF
  IF src_concept_type NOT IN DOMAIN_CONCEPT_TYPES
     AND tgt_concept_type NOT IN DOMAIN_CONCEPT_TYPES THEN
    RETURN TRUE
  END IF

  RETURN FALSE
END FUNCTION

FUNCTION isGarbageName(name)
  INPUT: name: string
  OUTPUT: boolean

  // PDF artifact characters adjacent to word boundaries
  IF name MATCHES /[?+=]/ adjacent to word boundaries THEN RETURN TRUE
  // Hyphenation breaks: "sec- tion", "includ- ing"
  IF name MATCHES /\w+- \w+/ THEN RETURN TRUE
  // Generic filler phrases
  IF name IN ["less than", "more than", "more than two", "information about",
               "such as", "as well", "due to", "based on", "according to",
               "in order", "at least", "up to", "each of", "one of"] THEN RETURN TRUE
  // Table/figure references: "Table 15.2", "Figure 3"
  IF name MATCHES /^(table|figure|fig)\s+\d/i THEN RETURN TRUE
  // Time expressions: "10 years", "30 days", "6 months"
  IF name MATCHES /^\d+\s+(years?|days?|months?|weeks?|hours?|minutes?)$/i THEN RETURN TRUE
  // Stage/phase labels: "stage 2", "phase 3"
  IF name MATCHES /^(stage|phase|step|grade|level|type)\s+\d/i THEN RETURN TRUE
  // Citations: "et al.", "et al"
  IF name MATCHES /\bet\s+al\.?$/i THEN RETURN TRUE

  RETURN FALSE
END FUNCTION
```

### Examples

- `"? Weight"` matched across a medical doc and an ML doc → both have NULL concept_type → 1.0 cosine similarity → inflates pair score. **Expected**: excluded by PDF artifact pattern and NULL type gate.
- `"sec- tion"` matched across two documents → hyphenation break artifact. **Expected**: excluded by hyphenation pattern.
- `"less than"` matched across many documents → generic filler phrase. **Expected**: excluded by generic phrase list.
- `"Table 15.2"` matched across two documents → table reference. **Expected**: excluded by table reference pattern.
- `"10 years"` matched across two documents → time expression. **Expected**: excluded by time expression pattern.
- `"stage 2"` matched across two documents → stage label. **Expected**: excluded by stage/phase pattern.
- `"et al."` matched across two documents → citation fragment. **Expected**: excluded by citation pattern.
- `"machine learning"` with concept_type `"TOPIC"` → valid domain concept. **Expected**: kept (not garbage, has domain type).
- `"neural network"` with concept_type `NULL` paired with `"neural network"` with concept_type `"CODE_TERM"` → one has a type. **Expected**: kept (one concept has non-null type, name is not garbage).

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Valid multi-token domain concepts (e.g., "machine learning", "neural network", "clinical trial") with at least one non-null concept_type continue to be discovered as cross-document edges
- Concepts with UMLS semantic types (e.g., "Disease or Syndrome", "Organic Chemical") continue to be included regardless of token count
- Concepts with trusted NER types (e.g., ORG, PERSON) continue to be included
- The per-edge scoring formula (`type_weight × 0.4 + embedding_similarity × 0.45 + cn_weight × 0.15`) is applied identically to qualifying edges
- Document-pair aggregation thresholds (MIN_EDGE_SCORE, MIN_EMBEDDING_SIMILARITY, MIN_EDGES_FOR_PAIR) continue to filter and aggregate identically
- Conversation documents continue to be excluded from cross-document edge discovery
- The Cypher overlap query structure, Phase 2 cosine similarity computation, deduplication, and per-target-doc capping remain unchanged

**Scope:**
All inputs that do NOT involve garbage concept names and that have at least one concept with a non-null `DOMAIN_CONCEPT_TYPES` type should be completely unaffected by this fix. This includes:
- All existing legitimate cross-document edges between domain concepts
- Mouse/API interactions that trigger composite scoring
- The scoring formula, aggregation, and persistence logic
- Conversation document exclusion logic

## Hypothesized Root Cause

Based on the bug description, the most likely issues are:

1. **No Garbage Name Filtering**: The Cypher query's only name filter is `c1.name CONTAINS ' '` (multi-token check). This allows any multi-token string through, including PDF artifacts like `"? Weight"`, hyphenation breaks like `"sec- tion"`, generic phrases like `"less than"`, table references like `"Table 15.2"`, time expressions like `"10 years"`, stage labels like `"stage 2"`, and citations like `"et al."`.

2. **No concept_type Gate**: The discovery pipeline never checks `concept_type`. Concepts with NULL type (which are typically extraction noise that didn't match any NER/UMLS/pattern tier in `ConceptNetValidator`) are treated identically to properly typed domain concepts. When both concepts in a pair have NULL type, there is no signal that either is a genuine domain concept.

3. **Identical String → 1.0 Cosine Similarity**: Garbage concepts that share the same `name_lower` across documents often have identical or near-identical embeddings (since they are the same string). This produces 1.0 cosine similarity, which combined with the SAME_AS type_weight of 1.0 yields a maximum edge score of `1.0 × 0.4 + 1.0 × 0.45 + 1.0 × 0.15 = 1.0`. Multiple such edges aggregate into a high document-pair score.

4. **Filtering Location**: The `_is_domain_concept` method exists on the class but is never called during `_discover_cross_doc_edges`. It was designed for a different filtering purpose and is not integrated into the edge discovery pipeline.

## Correctness Properties

Property 1: Bug Condition - Garbage Concepts Excluded from Edge Discovery

_For any_ cross-document concept pair where at least one concept name matches a garbage pattern (PDF artifacts, hyphenation breaks, generic phrases, table/figure references, time expressions, stage/phase labels, citations), the fixed `_discover_cross_doc_edges` method SHALL exclude that pair from the returned candidates list.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4**

Property 2: Bug Condition - NULL Type Pairs Excluded from Edge Discovery

_For any_ cross-document concept pair where both concepts have NULL concept_type (neither has a type in DOMAIN_CONCEPT_TYPES), the fixed `_discover_cross_doc_edges` method SHALL exclude that pair from the returned candidates list.

**Validates: Requirements 2.5, 2.6**

Property 3: Preservation - Legitimate Domain Concepts Unchanged

_For any_ cross-document concept pair where neither concept name matches a garbage pattern AND at least one concept has a non-null concept_type in DOMAIN_CONCEPT_TYPES, the fixed `_discover_cross_doc_edges` method SHALL produce the same result as the original method, preserving all existing legitimate cross-document edge discovery.

**Validates: Requirements 3.1, 3.2, 3.3**

Property 4: Preservation - Scoring and Aggregation Unchanged

_For any_ edge that passes the new garbage filter, the per-edge scoring formula, document-pair aggregation, thresholds (MIN_EDGE_SCORE, MIN_EMBEDDING_SIMILARITY, MIN_EDGES_FOR_PAIR), and RELATED_DOCS persistence SHALL produce identical results to the original code.

**Validates: Requirements 3.4, 3.5**

Property 5: Preservation - Conversation Document Exclusion Unchanged

_For any_ conversation document, the fixed code SHALL continue to exclude it from cross-document edge discovery, producing the same behavior as the original code.

**Validates: Requirements 3.6**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `src/multimodal_librarian/services/composite_score_engine.py`

**Class**: `CompositeScoreEngine`

**Specific Changes**:

1. **Add `_is_garbage_concept_name` static method**: A new method that takes a concept name string and returns True if it matches any garbage pattern. Uses compiled regex patterns for performance. Patterns cover:
   - PDF artifact characters (`?`, `+`, `=` adjacent to word boundaries)
   - Hyphenation breaks (`\w+- \w+`)
   - Generic filler phrases (exact match against a frozenset)
   - Table/figure references (`table/figure/fig \d`)
   - Time expressions (`\d+ years/days/months/...`)
   - Stage/phase labels (`stage/phase/step/... \d`)
   - Citations (`et al.?`)

2. **Add `GARBAGE_PHRASES` class constant**: A frozenset of known generic filler phrases that should be excluded (e.g., "less than", "more than", "information about", "such as", "as well", "due to", "based on").

3. **Add `_GARBAGE_PATTERNS` class constant**: A list of pre-compiled regex patterns for the non-exact-match garbage categories.

4. **Modify Cypher overlap query to return concept_type**: Add `c1.concept_type AS src_type` and `c2.concept_type AS tgt_type` to the RETURN clause of the overlap query so concept types are available for filtering in Python.

5. **Add filtering in the post-query loop**: In the deduplication/capping loop inside `_discover_cross_doc_edges`, after extracting `src_name`/`tgt_name` from the record, call `_is_garbage_concept_name` on both names and check concept types. Skip the candidate if the bug condition holds.

6. **No changes to scoring, aggregation, or persistence**: The `_compute_edge_score`, `_aggregate_document_pairs`, and `_persist_related_docs` methods remain untouched.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior. Since the bug is in a filtering gap (not a computation error), the primary testing surface is the `_is_garbage_concept_name` method and the post-query filtering logic in `_discover_cross_doc_edges`.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that construct mock Neo4j query results containing garbage concept names and NULL concept_types, pass them through the current `_discover_cross_doc_edges` post-processing logic, and assert that garbage pairs are NOT filtered. Run these tests on the UNFIXED code to observe that garbage concepts pass through.

**Test Cases**:
1. **PDF Artifact Test**: Mock query results with concept name `"? Weight"` and NULL types on both sides (will pass through on unfixed code)
2. **Hyphenation Break Test**: Mock query results with concept name `"sec- tion"` (will pass through on unfixed code)
3. **Generic Phrase Test**: Mock query results with concept name `"less than"` (will pass through on unfixed code)
4. **Table Reference Test**: Mock query results with concept name `"Table 15.2"` (will pass through on unfixed code)
5. **NULL Type Pair Test**: Mock query results with two concepts both having NULL concept_type and a valid-looking name (will pass through on unfixed code)

**Expected Counterexamples**:
- All garbage concept pairs pass through `_discover_cross_doc_edges` and appear in the candidates list
- Possible causes confirmed: no name pattern filtering, no concept_type gate

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior (exclusion from candidates).

**Pseudocode:**
```
FOR ALL (src_name, tgt_name, src_type, tgt_type) WHERE isBugCondition(src_name, tgt_name, src_type, tgt_type) DO
  result := _discover_cross_doc_edges_fixed(mock_graph_with(src_name, tgt_name, src_type, tgt_type))
  ASSERT (src_name, tgt_name) pair NOT IN result candidates
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL (src_name, tgt_name, src_type, tgt_type) WHERE NOT isBugCondition(src_name, tgt_name, src_type, tgt_type) DO
  ASSERT _discover_cross_doc_edges_original(input) = _discover_cross_doc_edges_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many random valid concept names and types to verify they still pass through
- It catches edge cases where the garbage regex might accidentally match legitimate names
- It provides strong guarantees that the filter is not over-aggressive

**Test Plan**: Observe behavior on UNFIXED code first for legitimate domain concepts, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Domain Concept Preservation**: Generate random multi-token domain concept names (no garbage patterns) with at least one DOMAIN_CONCEPT_TYPE, verify they pass through the filter
2. **UMLS Type Preservation**: Verify concepts with UMLS semantic types continue to be included
3. **NER Type Preservation**: Verify concepts with trusted NER types (ORG, PERSON) continue to be included
4. **Scoring Formula Preservation**: Verify edge scoring produces identical results for edges that pass the filter

### Unit Tests

- Test `_is_garbage_concept_name` with each garbage pattern category (PDF artifacts, hyphenation, generic phrases, table refs, time expressions, stage/phase, citations)
- Test `_is_garbage_concept_name` returns False for legitimate domain concept names
- Test the concept_type gate logic: both NULL → excluded, one non-null DOMAIN type → included
- Test edge cases: empty string, single character, very long names, unicode characters

### Property-Based Tests

- Generate random strings matching garbage patterns (using hypothesis strategies) and verify `_is_garbage_concept_name` returns True
- Generate random legitimate multi-token concept names (alphabetic words joined by spaces, no special characters) and verify `_is_garbage_concept_name` returns False
- Generate random (concept_type_a, concept_type_b) pairs and verify the type gate correctly identifies pairs where at least one is in DOMAIN_CONCEPT_TYPES
- Generate random edge data for non-garbage concepts and verify scoring/aggregation produces identical results to the original code

### Integration Tests

- Test full `compute_composite_scores()` flow with mock Neo4j returning a mix of garbage and legitimate concepts, verify only legitimate concepts produce RELATED_DOCS edges
- Test that document-pair scores decrease when garbage concepts are filtered out (compared to unfixed behavior)
- Test that the Cypher query correctly returns concept_type fields for filtering
