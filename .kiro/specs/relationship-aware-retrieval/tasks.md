# Tasks: Relationship-Aware Retrieval

## Task 1: Add Configuration Settings

- [ ] 1.1 Add relationship-aware retrieval settings to the `Settings` class in `src/multimodal_librarian/config/config.py`
  - Add `relationship_boost: float = Field(default=1.5, description="Boost multiplier for intersection chunks")`
  - Add `relationship_hop_limit: int = Field(default=2, description="Maximum hops between concept pairs")`
  - Add `relationship_traversal_timeout: float = Field(default=3.0, description="Timeout in seconds for relationship traversal queries")`
  - Add `relationship_max_paths_per_pair: int = Field(default=50, description="Maximum paths explored per concept pair")`
  - Requirements: 7.1, 7.2, 7.3

## Task 2: Create TraversalResult Data Model

- [ ] 2.1 Add `TraversalResult` dataclass to `src/multimodal_librarian/models/kg_retrieval.py`
  - Fields: `chunk_concept_connections: Dict[str, Set[str]]`, `total_paths_found: int`, `traversal_duration_ms: int`, `completed: bool`
  - Property: `intersection_chunk_ids` returning chunk IDs reachable from >= 2 concepts
  - Method: `concept_count_for_chunk(chunk_id)` returning distinct concept count
  - Static method: `empty()` returning an empty/failed result
  - Requirements: 3.1, 3.2

## Task 3: Implement RelationshipTraverser Component

- [ ] 3.1 Create `src/multimodal_librarian/components/kg_retrieval/relationship_traverser.py` with `RelationshipTraverser` class
  - Constructor accepts `neo4j_client`, `hop_limit`, `timeout_seconds`, `max_paths_per_pair`
  - Define `CLINICALLY_RELEVANT_RELATIONSHIPS` class constant with the relationship types from the design (CAUSES, PRESENTS_WITH, TREATED_BY, TREATS, IS_A, PART_OF, and ConceptNet equivalents)
  - Requirements: 2.5, 9.1, 9.2
- [ ] 3.2 Implement `_build_pair_cypher()` method
  - Generate Cypher MATCH query using variable-length path `*1..hop_limit` with only `CLINICALLY_RELEVANT_RELATIONSHIPS`
  - Collect chunk IDs via `EXTRACTED_FROM` from all path nodes using UNWIND + OPTIONAL MATCH
  - Include `LIMIT $max_paths` clause
  - Return `(cypher_string, parameters)` tuple
  - Cypher must be read-only (no CREATE, MERGE, DELETE, SET, REMOVE)
  - Requirements: 2.1, 2.2, 2.3, 2.5, 6.3, 9.1, 9.2
- [ ] 3.3 Implement `traverse()` method
  - Generate C(n,2) concept pairs from `concept_matches`
  - Execute `_build_pair_cypher()` for each pair with `asyncio.wait_for` timeout
  - Aggregate results into `chunk_concept_connections` mapping (chunk_id → set of concept_ids from both ends of each pair)
  - Track total paths found and traversal duration
  - On timeout: log WARNING, return `TraversalResult.empty()`
  - On exception: log WARNING, return `TraversalResult.empty()`
  - Requirements: 2.1, 2.3, 2.4, 6.1, 6.2, 8.2, 8.3
- [ ] 3.4 Export `RelationshipTraverser` from `src/multimodal_librarian/components/kg_retrieval/__init__.py`
  - Add import and include in `__all__`

## Task 4: Implement Boost Application in KGRetrievalService

- [ ] 4.1 Add `_apply_relationship_boost()` private method to `KGRetrievalService`
  - Accept `chunks: List[RetrievedChunk]`, `traversal_result: TraversalResult`, `boost_factor: float`
  - For each chunk in `traversal_result.intersection_chunk_ids`, multiply `kg_relevance_score` by scaled boost: `boost_factor * (1 + 0.1 * (num_concepts - 2))`
  - Cap `kg_relevance_score` at 1.0
  - Set `chunk.metadata["relationship_boost_applied"]` and `chunk.metadata["connecting_concept_count"]`
  - Return modified chunk list
  - Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 8.4

## Task 5: Integrate into _stage1_kg_retrieval Pipeline

- [ ] 5.1 Initialize `RelationshipTraverser` in `KGRetrievalService.__init__()` using config settings
  - Pass `neo4j_client`, `hop_limit`, `timeout_seconds`, `max_paths_per_pair` from Settings
  - Requirements: 7.1
- [ ] 5.2 Add multi-concept detection and traversal call in `_stage1_kg_retrieval()`
  - After `_aggregate_and_deduplicate()`, check `len(decomposition.concept_matches) >= 2`
  - If multi-concept: call `self._relationship_traverser.traverse(decomposition.concept_matches)`
  - Call `self._apply_relationship_boost(chunks, traversal_result)` with configured boost factor
  - If single-concept or traversal returns empty: skip boost (existing pipeline unchanged)
  - Requirements: 1.1, 1.2, 5.1, 5.2, 5.3
- [ ] 5.3 Add relationship-aware metadata to `KGRetrievalResult` in `retrieve()`
  - Add `relationship_aware_activated`, `intersection_chunks_found`, `relationship_paths_traversed`, `relationship_traversal_duration_ms` to result metadata
  - Log traversal duration for performance monitoring
  - Requirements: 1.4, 6.4, 8.1

## Task 6: Write Property-Based Tests

- [ ] 6.1 Create `tests/components/test_relationship_traverser.py` with property-based tests using Hypothesis
  - **Property 1 test**: Multi-concept classification threshold — generate random concept_matches lists of length 0..10, verify classification is True iff len >= 2
  - **Property 2 test**: Intersection chunk identification — generate random Dict[str, Set[str]] mappings, verify `intersection_chunk_ids` returns exactly chunks in >= 2 sets and `concept_count_for_chunk` is accurate
  - **Property 3 test**: Boost scaling and cap — generate random base scores in [0,1], boost factors in [1,3], concept counts in [2,5], verify boosted score is monotonically non-decreasing with concept count and always <= 1.0
  - **Property 4 test**: Boost identity — generate random chunk scores, apply boost=1.0, verify scores unchanged
  - **Property 5 test**: Cypher query structure — generate random concept ID pairs and hop limits 1..3, verify generated Cypher contains only allowed relationship types and correct path length constraint
  - **Property 7 test**: Read-only Cypher — generate random concept pairs, verify no write keywords in generated Cypher
  - **Property 10 test**: Path limit — generate random max_paths values, verify LIMIT clause matches
  - All tests: `@settings(max_examples=100)`, tagged with `# Feature: relationship-aware-retrieval, Property N: <title>`
  - Requirements: 1.1, 1.2, 2.1, 2.2, 2.5, 3.1, 3.2, 3.3, 4.1, 4.3, 4.4, 4.5, 6.3, 9.1, 9.2

## Task 7: Write Unit and Integration Tests

- [ ] 7.1 Add unit tests for `RelationshipTraverser` in `tests/components/test_relationship_traverser.py`
  - Test timeout handling: mock slow Neo4j, verify `TraversalResult.empty()` returned and WARNING logged
  - Test exception handling: mock Neo4j exception, verify fallback and WARNING logged
  - Test empty traversal: no paths found, verify empty result
  - Test single-concept query: verify traverser not invoked
  - Test configuration defaults: verify Settings defaults match documented values (1.5, 2, 3.0, 50)
  - Requirements: 2.4, 5.1, 5.3, 6.1, 6.2, 7.3, 8.3
- [ ] 7.2 Add integration test in `tests/integration/test_relationship_aware_retrieval.py`
  - Mock Neo4j with a small graph containing known concept paths and EXTRACTED_FROM edges
  - Run multi-concept query through `KGRetrievalService.retrieve()`
  - Verify intersection chunks have higher `kg_relevance_score` than single-concept chunks
  - Verify result metadata contains all relationship-aware fields
  - Verify single-concept query produces results identical to baseline (no traverser invocation)
  - Requirements: 1.4, 4.1, 5.1, 5.2, 5.4, 8.1
