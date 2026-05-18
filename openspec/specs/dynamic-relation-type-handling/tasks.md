# Implementation Plan: Dynamic Relation Type Handling

## Overview

Incrementally introduce a centralized relation type mapping layer, update the `RelationshipEdge` model with a `raw_relation_type` field, wire all consumers to the new mapper, and add a startup registry for Neo4j relation type discovery. Each step builds on the previous and is validated by tests.

## Tasks

- [x] 1. Add `raw_relation_type` field to RelationshipEdge and update serialization
  - [x] 1.1 Add `raw_relation_type: Optional[str] = None` field to `RelationshipEdge` in `src/multimodal_librarian/models/knowledge_graph.py`
    - Add the field after `relationship_type`, before `bidirectional`
    - Update `to_dict()` to include `'raw_relation_type': self.raw_relation_type`
    - Update `from_dict()` to read `raw_relation_type=data.get('raw_relation_type')`
    - _Requirements: 1.1, 1.2, 1.3, 6.1, 6.2_

  - [ ]* 1.2 Write property test for RelationshipEdge serialization round-trip
    - **Property 1: RelationshipEdge serialization round-trip**
    - Generate random RelationshipEdge instances with hypothesis, verify `from_dict(to_dict(edge))` preserves all fields including `raw_relation_type`
    - Also test that dicts missing `raw_relation_type` deserialize with `None`
    - **Validates: Requirements 1.2, 1.3, 6.1, 6.2**

- [x] 2. Implement RelationTypeMapper
  - [x] 2.1 Create `src/multimodal_librarian/components/knowledge_graph/relation_type_mapper.py`
    - Define `RelationTypeMapper` class with `_CAUSAL` and `_HIERARCHICAL` frozensets (lowercased)
    - Implement `classify(cls, raw_relation_type: str) -> RelationshipType` as a classmethod
    - Case-insensitive lookup: lowercase input, check `_CAUSAL`, then `_HIERARCHICAL`, default to `ASSOCIATIVE`
    - Implement `get_known_types(cls)` classmethod returning the full mapping dict
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [ ]* 2.2 Write property test for classification correctness
    - **Property 2: Classification correctness**
    - Use hypothesis to generate strings from known causal/hierarchical/associative sets and arbitrary strings
    - Verify classify returns correct RelationshipType based on set membership
    - **Validates: Requirements 2.2, 2.3, 2.4, 2.5**

  - [ ]* 2.3 Write property test for case-insensitive classification
    - **Property 3: Case-insensitive classification**
    - Use hypothesis to generate case permutations of known relation type strings
    - Verify classify returns the same result regardless of casing
    - **Validates: Requirements 2.6**

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Integrate mapper into ConceptNetValidator
  - [x] 4.1 Update `ConceptNetValidator.get_relationships_for_concepts()` in `src/multimodal_librarian/components/knowledge_graph/conceptnet_validator.py`
    - Import `RelationTypeMapper`
    - Replace `relationship_type=RelationshipType.ASSOCIATIVE` with `relationship_type=RelationTypeMapper.classify(rec["rel_type"])`
    - Add `raw_relation_type=rec["rel_type"]` to the RelationshipEdge constructor
    - _Requirements: 3.1, 3.2, 1.4_

  - [ ]* 4.2 Write property test for ConceptNetValidator edge creation
    - **Property 4: ConceptNetValidator edge creation correctness**
    - Mock Neo4j client to return records with random rel_type strings
    - Verify each resulting edge has `relationship_type == RelationTypeMapper.classify(rel_type)` and `raw_relation_type == rel_type`
    - **Validates: Requirements 1.4, 3.1, 3.2**

- [x] 5. Integrate mapper into KG Manager and KG Builder
  - [x] 5.1 Update `ExternalKnowledgeBootstrapper._map_conceptnet_relation_type()` in `src/multimodal_librarian/components/knowledge_graph/kg_manager.py`
    - Import `RelationTypeMapper`
    - Replace the local mapping dictionary with `return RelationTypeMapper.classify(predicate)`
    - _Requirements: 4.1_

  - [x] 5.2 Update `RelationshipExtractor._get_relationship_type()` in `src/multimodal_librarian/components/knowledge_graph/kg_builder.py`
    - Import `RelationTypeMapper`
    - Replace the local mapping dictionary with `return RelationTypeMapper.classify(predicate)`
    - _Requirements: 4.2_

  - [ ]* 5.3 Write property test for delegation equivalence
    - **Property 5: Delegation equivalence**
    - Generate random predicate strings with hypothesis
    - Verify `_map_conceptnet_relation_type(predicate)` and `_get_relationship_type(predicate)` both return `RelationTypeMapper.classify(predicate)`
    - **Validates: Requirements 4.1, 4.2**

- [x] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement RelationTypeRegistry with DI integration
  - [x] 7.1 Create `src/multimodal_librarian/components/knowledge_graph/relation_type_registry.py`
    - Implement `RelationTypeRegistry` class with `__init__(self, neo4j_client)`
    - Implement `async initialize()` that queries Neo4j for distinct `r.relation_type` values on `ConceptNetRelation` edges
    - Implement `async refresh()` that re-queries and updates the cached set
    - Implement `get_discovered_types() -> Set[str]` and `is_known_type(relation_type: str) -> bool`
    - Handle Neo4j failures gracefully: log warning, set empty set, do not raise
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.7_

  - [x] 7.2 Add DI provider for RelationTypeRegistry in `src/multimodal_librarian/api/dependencies/services.py`
    - Add `get_relation_type_registry()` and `get_relation_type_registry_optional()` dependency providers
    - Follow existing lazy-init singleton pattern with global cache variable
    - Call `initialize()` on first creation
    - _Requirements: 5.6_

  - [ ]* 7.3 Write property test for registry membership check
    - **Property 6: Registry membership check**
    - Generate random sets of relation type strings with hypothesis
    - Mock Neo4j to return those strings
    - Verify `is_known_type(t)` returns True for all strings in the set and False for strings not in the set
    - **Validates: Requirements 5.4**

  - [ ]* 7.4 Write unit tests for registry error handling
    - Test that when Neo4j client raises during `initialize()`, registry logs warning and has empty discovered set
    - Test that `refresh()` failure retains previously cached set
    - Test that `is_known_type()` returns False before `initialize()` is called
    - _Requirements: 5.5_

- [x] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- The `RelationTypeMapper` is a pure stateless utility — no DI needed, just import and use
- The `RelationTypeRegistry` follows the project's DI pattern (lazy init, singleton cache, graceful degradation)
- Property tests use `hypothesis` with `@settings(max_examples=100)`
