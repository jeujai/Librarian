# Implementation Plan: Three-Layer Concurrent Scientific/Medical NER for Query Term Extraction

## Overview

This plan implements a three-layer concurrent NER extraction system. Layer 1 (Base) uses spaCy `en_core_web_sm` for general proper nouns (people, places, organizations, dates). Layer 2 (Scientific) uses scispaCy `en_core_sci_sm` for scientific and medical entity recognition (biology, chemistry, medicine). Layer 3 (Medical Precision) adds UMLS n-gram refinement via the existing `UMLSClient` for highest-precision medical terms. All three layers run concurrently via `asyncio.gather`, and results are merged with a priority hierarchy: UMLS > en_core_sci_sm > en_core_web_sm. The system is encapsulated in a new `NER_Extractor` class, injected into both `RelevanceDetector` and `QueryDecomposer` via the existing DI framework, with independent graceful degradation for each layer.

## Tasks

- [x] 1. Add scispaCy dependency and Docker installation
  - [x] 1.1 Add scispaCy to requirements-app.txt
    - Add `scispacy>=0.5.0,<0.6.0` to `requirements-app.txt` after the existing `spacy` entry
    - _Requirements: 1.2_
  - [x] 1.2 Install scispaCy and en_core_sci_sm in Dockerfile.app
    - Add `RUN pip install scispacy>=0.5.0,<0.6.0 && pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/en_core_sci_sm-0.5.4.tar.gz` after the existing `en_core_web_sm` download line in `Dockerfile.app`
    - Ensure the existing `en_core_web_sm` download line is preserved (needed for Layer 1)
    - _Requirements: 1.1, 1.3_

- [x] 2. Implement NER_Extractor module with NERResult dataclass
  - [x] 2.1 Create `src/multimodal_librarian/components/kg_retrieval/ner_extractor.py` with NERResult dataclass and NER_Extractor class
    - Implement `NERResult` dataclass with `web_entities`, `sci_entities`, `umls_entities`, `key_terms` fields, plus `to_dict()` and `from_dict()` serialization methods
    - Implement `NER_Extractor.__init__()` accepting `spacy_web_nlp`, `spacy_sci_nlp`, optional `umls_client`, `umls_timeout_ms` (default 200), and `max_ngram_size` (default 5)
    - Define `FILTERED_LABELS` frozenset, `_AGE_PATTERN`, and `_NUMERIC_PATTERN` class attributes
    - _Requirements: 10.1, 10.2, 10.3, 10.4_
  - [x] 2.2 Implement shared spaCy extraction logic (`_run_spacy_extraction` method)
    - Run `nlp(query)` and extract named entities, filtering out `FILTERED_LABELS`, age descriptors, and numeric-only entities
    - Extract PROPN tokens (length > 2) and capitalized NOUN tokens (length > 2) from noun chunks
    - This method is shared by both Layer 1 and Layer 2
    - _Requirements: 2.3, 2.4, 3.3_
  - [x] 2.3 Implement Layer 1 extraction (`_extract_layer1_web` async method)
    - Call `_run_spacy_extraction(self.spacy_web_nlp, query)` for general proper noun extraction
    - Return empty list if `self.spacy_web_nlp` is None
    - Catch and log exceptions, return empty list on failure (Layer 2+3 continue)
    - _Requirements: 2.1, 2.2, 6.1_
  - [x] 2.4 Implement Layer 2 extraction (`_extract_layer2_sci` async method)
    - Call `_run_spacy_extraction(self.spacy_sci_nlp, query)` for scientific/medical entity extraction
    - Return empty list if `self.spacy_sci_nlp` is None
    - Catch and log exceptions, return empty list on failure (Layer 1+3 continue)
    - _Requirements: 3.1, 3.2, 6.2_
  - [x] 2.5 Implement n-gram generation (`_generate_ngrams` method)
    - Split query into words, generate all contiguous subsequences of 2 to `max_ngram_size` tokens
    - Strip trailing punctuation from each n-gram
    - _Requirements: 4.1_
  - [x] 2.6 Implement Layer 3 UMLS lookup (`_extract_layer3_umls` async method)
    - Generate candidate n-grams from query, batch-query `self.umls_client.batch_search_by_names(candidates)`
    - Wrap the UMLS call in `asyncio.wait_for()` with `self.umls_timeout_ms / 1000.0` timeout
    - Catch `asyncio.TimeoutError` and general exceptions, log warnings with elapsed time, return empty list on failure
    - Return empty list if `self.umls_client` is None
    - _Requirements: 4.2, 4.5, 6.3, 6.4, 6.6_
  - [x] 2.7 Implement three-way entity merge logic (`_merge_entities` method)
    - Accept web_entities, sci_entities, and umls_overrides as inputs
    - Step 1: Sort UMLS overrides by length descending; mark sci entities as subsumed when they are case-insensitive substrings of a longer UMLS term
    - Step 2: Remaining (non-subsumed) sci entities subsume shorter web entities when they are case-insensitive substrings
    - Step 3: UMLS terms also directly subsume web entities
    - Step 4: Return merged set: all UMLS overrides + non-subsumed sci entities + non-subsumed web entities
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_
  - [x] 2.8 Implement `extract_key_terms` async method
    - Run all three layers concurrently via `asyncio.gather(layer1, layer2, layer3)`
    - Pass results to `_merge_entities` for three-way merge
    - Return empty `NERResult` for empty/whitespace queries
    - Return `NERResult` with `web_entities`, `sci_entities`, `umls_entities`, and merged `key_terms`
    - _Requirements: 3.4, 4.6, 10.2_
  - [x] 2.9 Write property test: Filtered labels excluded from key_terms
    - **Property 1: Filtered labels are excluded from key_terms**
    - Use Hypothesis to generate random strings, mock spaCy doc with entities having filtered labels (CARDINAL, ORDINAL, etc.), age descriptors, and numeric-only patterns
    - Verify none of those entities appear in `key_terms` regardless of which layer (web or sci) produced them
    - **Validates: Requirements 2.3, 3.3**
  - [x] 2.10 Write property test: Proper nouns and capitalized nouns preserved
    - **Property 2: Proper nouns and capitalized nouns are preserved in key_terms**
    - Use Hypothesis to generate random capitalized words, construct mock spaCy doc with PROPN/NOUN tokens in noun chunks
    - Verify all qualifying tokens appear in `key_terms` (unless subsumed by a longer term from a higher-priority layer)
    - **Validates: Requirements 2.2, 2.4, 9.1, 9.3**
  - [x] 2.11 Write property test: N-gram generation completeness
    - **Property 3: N-gram generation produces all adjacent word combinations**
    - Use Hypothesis to generate random word lists (1–20 words), call `_generate_ngrams()`
    - Verify n-gram count equals sum of (N - k + 1) for k in range(2, min(6, N + 1))
    - **Validates: Requirements 4.1**
  - [x] 2.12 Write property test: Three-way merge correctness
    - **Property 4: Three-way merge correctness — priority hierarchy is respected**
    - Use Hypothesis to generate random entity lists for all three layers with substring relationships
    - Verify: (a) all UMLS terms in merged set, (b) non-subsumed sci entities preserved, (c) non-subsumed web entities preserved, (d) subsumed entities removed according to priority hierarchy
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**
  - [x] 2.13 Write property test: Well-formed NERResult
    - **Property 5: extract_key_terms returns a well-formed NERResult**
    - Use Hypothesis to generate random query strings, mock all three layers
    - Verify: (a) `web_entities` is list of str, (b) `sci_entities` is list of str, (c) `umls_entities` is list of str, (d) `key_terms` is set of str, (e) every element in `key_terms` is in `web_entities`, `sci_entities`, or `umls_entities`
    - **Validates: Requirements 10.2**
  - [x] 2.14 Write property test: NERResult serialization round-trip
    - **Property 6: NERResult serialization round-trip**
    - Use Hypothesis `builds()` strategy to generate random `NERResult` instances
    - Verify `NERResult.from_dict(result.to_dict())` produces identical fields
    - **Validates: Requirements 10.4**
  - [x] 2.15 Write property test: Independent layer degradation
    - **Property 7: Independent layer degradation preserves other layers' results**
    - Use Hypothesis to generate random queries, disable one layer at a time (set model to None)
    - Verify results from the other two layers still appear in `key_terms` (subject to merge hierarchy)
    - **Validates: Requirements 6.1, 6.2, 6.3**
  - [x] 2.16 Write unit tests for NER_Extractor
    - Test Layer 1 (web) failure: verify Layer 2+3 still produce results
    - Test Layer 2 (sci) failure: verify Layer 1+3 still produce results
    - Test UMLS unavailable (umls_client=None) returns Layer 1+2 only
    - Test UMLS timeout returns Layer 1+2 only (mock slow UMLS client)
    - Test all layers fail returns empty NERResult
    - Test degradation logging contains layer name, model name, error, remaining layers
    - Test empty/whitespace query returns empty NERResult
    - Test non-medical query with UMLS returning empty produces empty `umls_entities`
    - Test concurrent execution: verify all three layers run via asyncio.gather
    - Test merge: UMLS overrides sci, sci overrides web, non-overlapping preserved
    - Place tests in `tests/components/test_ner_extractor.py`
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 5.2, 5.3, 5.4, 9.2_

- [x] 3. Checkpoint — Verify NER_Extractor module
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Wire NER_Extractor into Dependency Injection
  - [x] 4.1 Add `get_ner_extractor()` DI provider to `src/multimodal_librarian/api/dependencies/services.py`
    - Add module-level `_ner_extractor: Optional["NER_Extractor"] = None` cache variable
    - Implement `get_ner_extractor()` that independently loads `en_core_web_sm` (Layer 1) and `en_core_sci_sm` (Layer 2), each with fallback to None on failure; accepts optional `UMLSClient` via `Depends(get_umls_client_optional)` for Layer 3; creates and caches `NER_Extractor`
    - Log each model loading success/failure at appropriate levels
    - _Requirements: 7.1, 6.1, 6.2, 6.6_
  - [x] 4.2 Modify `get_relevance_detector()` to inject NER_Extractor
    - Add `ner_extractor: Optional["NER_Extractor"] = Depends(get_ner_extractor)` parameter
    - Use `ner_extractor.spacy_web_nlp` instead of loading `en_core_web_sm` directly
    - Pass `ner_extractor` as a new constructor parameter to `RelevanceDetector`
    - _Requirements: 7.1_
  - [x] 4.3 Modify `get_query_decomposer_optional()` to inject NER_Extractor
    - Add `ner_extractor: Optional["NER_Extractor"] = Depends(get_ner_extractor)` parameter
    - Pass `ner_extractor` to `QueryDecomposer` constructor as a new optional parameter
    - _Requirements: 8.1_
  - [x] 4.4 Add `_ner_extractor` to `clear_service_cache()` and `cleanup_services()` functions
    - Reset `_ner_extractor = None` in cache clearing
    - _Requirements: 7.1_

- [x] 5. Integrate NER_Extractor into RelevanceDetector
  - [x] 5.1 Add `ner_extractor` parameter to `RelevanceDetector.__init__()`
    - Add `ner_extractor: Optional[Any] = None` parameter and store as `self.ner_extractor`
    - _Requirements: 7.1_
  - [x] 5.2 Convert `filter_chunks_by_proper_nouns()` from sync to async and use NER_Extractor
    - Change method signature to `async def filter_chunks_by_proper_nouns(...)`
    - When `self.ner_extractor is not None`, call `await self.ner_extractor.extract_key_terms(query)` and use `ner_result.key_terms`
    - Keep existing inline spaCy extraction as fallback when `ner_extractor` is None
    - Update all callers of `filter_chunks_by_proper_nouns` to `await` the call
    - _Requirements: 7.2, 7.4_
  - [x] 5.3 Update `analyze_query_term_coverage()` to use NER_Extractor key_terms
    - If NER_Extractor is available, use its `key_terms` for proper noun coverage analysis
    - _Requirements: 7.3_

- [x] 6. Integrate NER_Extractor into QueryDecomposer
  - [x] 6.1 Add `ner_extractor` parameter to `QueryDecomposer.__init__()`
    - Add `ner_extractor: Optional[Any] = None` parameter and store as `self.ner_extractor`
    - _Requirements: 8.1_
  - [x] 6.2 Modify `_find_entity_matches()` to include multi-word NER entities
    - When `self.ner_extractor is not None`, call `await self.ner_extractor.extract_key_terms(query)`
    - Add multi-word entities (terms containing spaces) from `ner_result.key_terms` to `all_words` list for Neo4j concept matching
    - _Requirements: 8.2_

- [x] 7. Checkpoint — Verify integration wiring
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Write integration tests
  - [ ]* 8.1 Write integration tests in `tests/integration/test_ner_integration.py`
    - Test DI wiring: verify `get_ner_extractor()` loads both models independently and caches correctly
    - Test RelevanceDetector uses NER_Extractor: verify `filter_chunks_by_proper_nouns` uses `extract_key_terms` when `ner_extractor` is set
    - Test `analyze_query_term_coverage` uses NER_Extractor key_terms
    - Test QueryDecomposer includes multi-word NER entities in `_find_entity_matches`
    - Test UMLS `batch_search_by_names` is called with generated n-grams
    - Test concurrent execution: verify all three layers run in parallel
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 8.2, 4.2_

- [x] 9. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (Properties 1–7)
- Unit tests validate specific examples, edge cases, and graceful degradation scenarios
- The design uses Python throughout — all code examples use Python 3.9+ with async/await
- The project already uses Hypothesis for property-based testing (`.hypothesis/` directory present)
- The existing `en_core_web_sm` model is already installed in the Docker image and is now used for Layer 1 (Base)
- The `en_core_sci_sm` model is added for Layer 2 (Scientific) — both models load independently
- All three layers run concurrently via `asyncio.gather` — total latency ≈ max(layer1, layer2, layer3)
