# Implementation Plan: Chunking-KG Optimization

## Overview

Surgical modifications to four existing components and one service to optimize the chunking-KG pipeline for recall, accuracy, and precision. All changes are backward-compatible. Implementation proceeds from configuration through core logic to metrics, with property tests validating each step.

## Tasks

- [x] 1. Add embedding-aware chunk size configuration and logic
  - [x] 1.1 Add `target_embedding_tokens`, `max_embedding_tokens`, `min_embedding_tokens`, and all concept extraction threshold fields to `Settings` in `src/multimodal_librarian/config.py`
    - Add embedding fields: `target_embedding_tokens=256`, `max_embedding_tokens=512`, `min_embedding_tokens=64`
    - Add concept extraction fields: `pmi_threshold=5.0`, `multi_word_seed_confidence=0.85`, `multi_word_pmi_confidence=0.65`, `acronym_confidence=0.6`, `frequency_boost_increment=0.02`, `frequency_boost_cap=0.1`
    - Add bisection field: `overlap_window=20`
    - All with `env=` overrides and descriptive docstrings including rationale
    - _Requirements: 1.1, 1.5, 9.1_

  - [x] 1.2 Modify `_generate_chunking_requirements` in `content_analyzer.py` to use `target_embedding_tokens` from settings as the base chunk size, replacing the hardcoded `base_chunk_size = 400`
    - Read `target_embedding_tokens`, `max_embedding_tokens`, `min_embedding_tokens` from `get_settings()`
    - Replace `max(150, min(preferred_size, 300))` with `max(min_tokens, min(preferred_size, max_tokens))`
    - _Requirements: 1.2, 1.3, 1.4_

  - [ ]* 1.3 Write property test for chunk size bounds (Property 1)
    - **Property 1: Chunk size is bounded by embedding model limits**
    - Use hypothesis to generate random content types, complexity scores, and conceptual densities
    - Verify `preferred_chunk_size` is always within `[min_embedding_tokens, max_embedding_tokens]`
    - **Validates: Requirements 1.2, 1.3, 1.4**

- [x] 2. Expand concept extraction with multi-word phrases (seed + PMI) and acronyms
  - [x] 2.1 Add `MULTI_WORD` seed list and `ACRONYM` pattern categories to `ConceptExtractor.concept_patterns` in `kg_builder.py`
    - Add multi-word seed list regex patterns for known domain terminology
    - Add acronym regex pattern `r'\b[A-Z]{2,6}\b'`
    - Add acronym stopword filter set
    - _Requirements: 2.1, 2.2, 2.4, 2.5_

  - [x] 2.2 Implement `_extract_collocations_pmi` method on `ConceptExtractor`
    - Compute word frequencies and bigram frequencies from chunk text
    - Calculate PMI for each bigram: `log2(P(x,y) / (P(x) * P(y)))`
    - Extract bigrams exceeding `pmi_threshold` (from settings) as `MULTI_WORD` concepts with `multi_word_pmi_confidence`
    - Require minimum 2 occurrences per bigram
    - Skip texts shorter than 10 words
    - Call at end of `extract_concepts_ner`, merge with seed-list results, deduplicate by normalized name
    - _Requirements: 2.1, 2.7_

  - [x] 2.3 Add `CollocationCache` instance attribute to `ConceptExtractor`
    - Dictionary keyed by normalized bigram, storing cumulative frequency and document count
    - Update incrementally per document in `extract_concepts_ner`
    - Use corpus-level frequencies for PMI when available, fall back to document-level
    - _Requirements: 2.8_

  - [x] 2.4 Update `extract_concepts_ner` to assign pattern-specific confidence scores from settings
    - `MULTI_WORD` (seed): `multi_word_seed_confidence` from settings (default 0.85)
    - `MULTI_WORD` (PMI): `multi_word_pmi_confidence` from settings (default 0.65)
    - `ACRONYM`: `acronym_confidence` from settings (default 0.6)
    - Frequency boost: `frequency_boost_increment` per additional occurrence, capped at `frequency_boost_cap`
    - _Requirements: 2.6_

  - [x] 2.5 Implement `_link_acronym_expansions` method on `ConceptExtractor`
    - Detect patterns like `"Expanded Form (ACRONYM)"` and `"ACRONYM (Expanded Form)"`
    - Link matching concepts via `add_alias`
    - Call this method at the end of `extract_concepts_ner`
    - _Requirements: 2.3_

  - [ ]* 2.6 Write property tests for concept extraction (Properties 2, 3, 4, 5, 6)
    - **Property 2: Multi-word phrase extraction (seed list) with correct type**
    - **Property 3: PMI collocation discovery**
    - **Property 4: Acronym extraction with correct type**
    - **Property 5: Acronym-expansion alias linking**
    - **Property 6: Concept confidence reflects pattern type and frequency**
    - Use hypothesis to generate text with embedded phrases/acronyms and controlled word frequencies
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7**

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement concept bisection detection and boundary adjustment
  - [x] 4.1 Add `_adjust_boundary_for_concept_contiguity` method to `GenericMultiLevelChunkingFramework` in `framework.py`
    - Accept pre-boundary text, post-boundary text, boundary word index, max_chunk_size, current_chunk_size, overlap_window
    - Build overlap zone from last/first `overlap_window` tokens around boundary
    - Run `ConceptExtractor.extract_concepts_ner` on overlap zone
    - Check if any extracted concept spans the boundary position
    - If spanning concept found: shift boundary past concept end (or before concept start if exceeding max_chunk_size)
    - If multiple spanning concepts: prioritize highest confidence
    - If no spanning concepts: return boundary unchanged
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [x] 4.2 Integrate `_adjust_boundary_for_concept_contiguity` into `_perform_primary_chunking`
    - After `_find_semantic_boundary` returns a candidate split point, call `_adjust_boundary_for_concept_contiguity`
    - Use the adjusted boundary for the actual chunk split
    - Read `overlap_window` from settings
    - _Requirements: 3.1, 3.2_

  - [ ]* 4.3 Write property test for concept bisection detection (Property 7)
    - **Property 7: Concept bisection detection prevents boundary splitting**
    - Use hypothesis to generate text with multi-word concepts placed at boundary positions
    - Verify adjusted boundary keeps concept in a single chunk
    - Verify adjusted chunk does not exceed max_chunk_size
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.6**

- [x] 5. Implement bridge chunk KG integration
  - [x] 5.1 Modify `chunk_with_smart_bridges` in `framework.py` to run concept extraction on bridge chunks
    - After bridge validation, call `ConceptExtractor.extract_concepts_ner(bridge.content)`
    - Store extracted concept IDs in `bridge.metadata['extracted_concepts']`
    - Ensure `bridge.metadata['adjacent_chunk_ids']` is set from `bridge.source_chunks`
    - _Requirements: 4.1, 4.2, 4.4_

  - [ ]* 5.2 Write property test for bridge chunk KG integration (Property 8)
    - **Property 8: Bridge chunks have concepts extracted with correct metadata**
    - Use hypothesis to generate bridge chunk content with extractable concepts
    - **Validates: Requirements 4.1, 4.2, 4.4**

- [x] 6. Implement cross-reference relationship extraction
  - [x] 6.1 Add `_extract_cross_references` method to `ConceptExtractor` in `kg_builder.py`
    - Match explicit cross-reference patterns: "see Section X", "as discussed in Chapter Y", "refer to Figure Z"
    - Match backward references: "as mentioned/discussed/shown in Section X"
    - Match positional references: "Section X above/below/earlier/later"
    - Return list of `CrossReference` dataclass instances
    - _Requirements: 5.1_

  - [x] 6.2 Add `CrossReference` dataclass to `kg_retrieval.py`
    - Fields: `source_chunk_id`, `reference_type`, `target_type`, `target_label`, `raw_text`, `resolved_chunk_ids`
    - _Requirements: 5.1_

  - [x] 6.3 Add `_reconcile_cross_references` method to `KnowledgeGraphBuilder` in `kg_builder.py`
    - Accept list of `CrossReference` objects and chunk metadata mapping (section/chapter → chunk IDs)
    - Resolve target labels to chunk IDs using metadata
    - Create `REFERENCES` edges in KG for resolved references
    - Store unresolved references as pending edges with warning log
    - _Requirements: 5.2, 5.3_

  - [x] 6.4 Update `_retrieve_related_chunks` in `KGRetrievalService` to traverse `REFERENCES` edges
    - Include `REFERENCES` edge type in Neo4j traversal query
    - Treat cross-referenced chunks as `hop_distance=1`
    - _Requirements: 5.4_

  - [ ]* 6.5 Write property test for cross-reference extraction (Property 9)
    - **Property 9: Cross-reference extraction captures explicit references**
    - Use hypothesis to generate text with embedded cross-reference patterns
    - Verify extracted references have correct target_type and target_label
    - **Validates: Requirements 5.1**

- [x] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement deterministic chunk IDs and change mapping
  - [x] 8.1 Add `_generate_chunk_id(document_id, content)` method to `GenericMultiLevelChunkingFramework` in `framework.py`
    - Use SHA-256 hash of `f"{document_id}:{content}"` to produce a deterministic UUID
    - Set UUID version 4 bits for format compatibility
    - _Requirements: 7.1_

  - [x] 8.2 Replace all `uuid.uuid4()` calls in `_perform_primary_chunking` and `_split_large_chunk` with `_generate_chunk_id(document_id, content)`
    - Thread `document_id` through to chunking methods
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 8.3 Add `ChunkChangeMapping` dataclass and compute change mapping in `process_document`
    - Accept optional `previous_chunk_ids: Optional[Set[str]]` parameter
    - After chunking, compute added/removed/unchanged sets
    - Add `chunk_change_mapping` field to `ProcessedDocument`
    - _Requirements: 7.4, 7.5_

  - [ ]* 8.4 Write property tests for deterministic IDs and change mapping (Properties 13, 14)
    - **Property 13: Deterministic chunk ID generation**
    - **Property 14: Change mapping correctness**
    - Use hypothesis to generate document IDs, content strings, and previous/new ID sets
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5**

- [x] 9. Implement mixed-domain document handling
  - [x] 9.1 Add `_split_into_sections` method to `AutomatedContentAnalyzer` in `content_analyzer.py`
    - Split on markdown headings, chapter markers, section markers, and topic shifts
    - Return list of section text strings
    - _Requirements: 6.2_

  - [x] 9.2 Add `classify_sections` method to `AutomatedContentAnalyzer`
    - Iterate sections, classify each independently
    - Sections shorter than 100 tokens inherit previous section's classification
    - Return list of `(section_text, ContentType, ChunkingRequirements)` tuples
    - _Requirements: 6.1, 6.3, 6.5_

  - [x] 9.3 Add `SectionClassification` dataclass to `framework.py`
    - Fields: `section_text`, `content_type`, `chunking_requirements`, `start_offset`, `end_offset`
    - _Requirements: 6.1_

  - [x] 9.4 Modify `chunk_with_smart_bridges` to support per-section chunking
    - When `classify_sections` returns multiple sections, chunk each section with its own `ChunkingRequirements`
    - Concatenate chunk lists and generate bridges across section boundaries
    - _Requirements: 6.4_

  - [ ]* 9.5 Write property tests for mixed-domain handling (Properties 10, 11, 12)
    - **Property 10: Section splitting at structural boundaries**
    - **Property 11: Per-section classification produces domain-specific results**
    - **Property 12: Section-specific chunking requirements are applied**
    - Use hypothesis to generate documents with structural markers and mixed-domain sections
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4**

- [x] 10. Implement retrieval quality metrics with threshold overrides
  - [x] 10.1 Add `RetrievalMetrics` dataclass to `kg_retrieval_service.py`
    - Fields: `recall`, `precision`, `f1_score`, `true_positives`, `retrieved_count`, `ground_truth_count`
    - _Requirements: 8.1_

  - [x] 10.2 Add `evaluate_retrieval` method to `KGRetrievalService`
    - Accept `query`, `ground_truth_chunk_ids`, optional `top_k`, and optional `threshold_overrides` dict
    - Apply temporary threshold overrides via settings, restore in `finally` block
    - Call `self.retrieve()`, compute metrics against ground truth
    - Return metrics dictionary including `threshold_config` used
    - Handle empty ground truth (return zeros) and empty retrieved set
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 9.2, 9.3_

  - [ ]* 10.3 Write property test for retrieval metrics (Property 15)
    - **Property 15: Retrieval metrics computation**
    - Use hypothesis to generate random retrieved and ground-truth ID sets
    - Verify recall, precision, and F1 formulas hold
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.4**

- [x] 11. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests use `hypothesis` with `max_examples=100`
- All changes are backward-compatible modifications to existing files
- No new services or DI providers are introduced
- KG conceptual matching weight continues to exceed semantic similarity weight (unchanged)
- All threshold values are empirical starting points — use `evaluate_retrieval` with `threshold_overrides` to tune for your corpus
- Cross-reference reconciliation runs as a post-processing pass after all chunks in a document are processed
