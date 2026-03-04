# Requirements Document

## Introduction

This specification extends the chunking pipeline's bridge generation to be concept-aware when concept bisections cannot be resolved by boundary shifting. Currently, `_adjust_boundary_for_concept_contiguity` attempts to shift chunk boundaries to keep multi-word concepts whole, but falls back to the original boundary when shifting is not feasible (would exceed max chunk size, or multiple concepts span the boundary). The bridge generator (`SmartBridgeGenerator`) operates independently — it smooths narrative transitions but has zero awareness of which concepts were bisected. A bisected concept like `allow_dangerous_code=True` might or might not appear in the bridge text, purely by coincidence.

This spec introduces two mechanisms: (1) augmenting standard bridge prompts with bisected concept information when a bridge is already being generated for that boundary, and (2) generating additional concept-recovery bridges when bisected concepts are not covered by the standard bridge pipeline (either because no bridge was generated for that boundary, or because the bisected concepts fell outside the ~200 char context window).

## Glossary

- **Chunking_Framework**: The `GenericMultiLevelChunkingFramework` that orchestrates content analysis, chunking, bridge generation, gap analysis, and validation.
- **Bridge_Generator**: The `SmartBridgeGenerator` that creates bridge chunks between adjacent chunks to preserve cross-boundary context.
- **Concept_Extractor**: The `ConceptExtractor` class in `kg_builder.py` that extracts concepts from chunk text using NER patterns, LLM, and embedding methods.
- **Gap_Analyzer**: The `ConceptualGapAnalyzer` that scores semantic discontinuity between adjacent chunks.
- **Bisected_Concept**: A multi-word concept that spans a chunk boundary after `_adjust_boundary_for_concept_contiguity` has been unable to resolve the bisection via boundary shifting.
- **Unresolved_Bisection_Record**: A data structure recording a bisected concept, the boundary index where the bisection occurred, and the IDs of the two adjacent chunks involved.
- **Concept_Aware_Bridge**: A bridge chunk whose LLM prompt has been augmented with explicit instructions to preserve specific bisected concepts verbatim in the bridge text.
- **Concept_Recovery_Bridge**: An additional bridge chunk generated specifically to recover bisected concepts that were not covered by the standard bridge pipeline (either because no standard bridge was generated for that boundary, or because the bisected concepts fell outside the standard bridge's context window).
- **Bridge_Threshold**: The `necessity_score` threshold from gap analysis above which a standard bridge is generated for a boundary pair.
- **Context_Window**: The ~200 character excerpt from the end of chunk N and start of chunk N+1 used as context in bridge generation prompts.

## Requirements

### Requirement 1: Record Unresolved Concept Bisections

**User Story:** As a system operator, I want the chunking pipeline to record which concepts could not be kept whole by boundary adjustment, so that downstream bridge generation can target those specific concepts for recovery.

#### Acceptance Criteria

1. WHEN `_adjust_boundary_for_concept_contiguity` detects a spanning concept but cannot shift the boundary (forward shift exceeds `max_chunk_size` and backward shift would produce a zero-size chunk), THE Chunking_Framework SHALL record an Unresolved_Bisection_Record containing the concept name, concept confidence, boundary index, and the IDs of the two adjacent chunks.
2. WHEN `_adjust_boundary_for_concept_contiguity` detects multiple spanning concepts and resolves only the highest-confidence one, THE Chunking_Framework SHALL record Unresolved_Bisection_Records for all remaining unresolved spanning concepts.
3. THE Chunking_Framework SHALL accumulate Unresolved_Bisection_Records during primary chunking and make the collection available to the bridge generation phase of `chunk_with_smart_bridges`.
4. WHEN no concepts span a proposed boundary, THE Chunking_Framework SHALL not create any Unresolved_Bisection_Records for that boundary.

### Requirement 2: Augment Standard Bridge Prompts with Bisected Concepts

**User Story:** As a system operator, I want standard bridge prompts to include explicit instructions to preserve bisected concepts verbatim, so that bridges generated for high-gap-score boundaries also recover bisected terms.

#### Acceptance Criteria

1. WHEN a standard bridge is being generated for a boundary (gap score exceeds Bridge_Threshold) AND Unresolved_Bisection_Records exist for that boundary, THE Bridge_Generator SHALL augment the bridge prompt with an instruction to include each bisected concept verbatim in the bridge text.
2. WHEN the bridge prompt is augmented with bisected concepts, THE Bridge_Generator SHALL include the full text of each bisected concept in the prompt instruction, not just a reference or identifier.
3. WHEN a standard bridge is being generated for a boundary AND no Unresolved_Bisection_Records exist for that boundary, THE Bridge_Generator SHALL generate the bridge using the existing prompt without modification.
4. THE Bridge_Generator SHALL accept an optional list of bisected concept names in `create_adaptive_prompt` and `generate_bridge` without breaking existing callers that do not pass bisected concepts.

### Requirement 3: Generate Concept-Recovery Bridges for Uncovered Bisections

**User Story:** As a system operator, I want additional concept-recovery bridges to be generated when bisected concepts are not covered by the standard bridge pipeline, so that no bisected concept is left unrecoverable.

#### Acceptance Criteria

1. WHEN Unresolved_Bisection_Records exist for a boundary AND no standard bridge was generated for that boundary (gap score below Bridge_Threshold), THE Chunking_Framework SHALL generate a Concept_Recovery_Bridge for that boundary targeting the bisected concepts.
2. WHEN Unresolved_Bisection_Records exist for a boundary AND a standard bridge was generated but the bisected concepts do not appear in the bridge text (case-insensitive substring match), THE Chunking_Framework SHALL generate an additional Concept_Recovery_Bridge for that boundary targeting the missing concepts.
3. WHEN generating a Concept_Recovery_Bridge, THE Chunking_Framework SHALL use the existing bridge generation pipeline (SmartBridgeGenerator) with a concept-preserving prompt that explicitly instructs the LLM to include each target concept verbatim.
4. THE Concept_Recovery_Bridge SHALL carry metadata indicating it is a recovery bridge, the list of target bisected concepts, and the IDs of the two adjacent chunks.
5. WHEN all bisected concepts for a boundary already appear in the standard bridge text, THE Chunking_Framework SHALL not generate a Concept_Recovery_Bridge for that boundary.

### Requirement 4: Concept-Recovery Bridge Prompt Design

**User Story:** As a system operator, I want concept-recovery bridge prompts to use a wider context window around the bisection point and explicitly name the bisected concepts, so that the LLM has sufficient context to produce a coherent bridge that preserves the target terms.

#### Acceptance Criteria

1. WHEN generating a Concept_Recovery_Bridge, THE Bridge_Generator SHALL use a context window of at least 400 characters from the end of chunk N and start of chunk N+1 (double the standard 200-character window).
2. WHEN generating a Concept_Recovery_Bridge, THE Bridge_Generator SHALL include in the prompt the exact text of each bisected concept to be preserved, with an instruction to include each concept verbatim in the bridge output.
3. THE Bridge_Generator SHALL expose a configurable `recovery_bridge_context_chars` parameter (default: 400) that controls the context window size for concept-recovery bridge prompts.
4. WHEN the chunk text is shorter than the configured context window, THE Bridge_Generator SHALL use the full chunk text as context.

### Requirement 5: Concept-Recovery Bridge KG Integration

**User Story:** As a system operator, I want concept-recovery bridges to be indexed in the Knowledge Graph identically to standard bridges, so that recovered concepts are discoverable during KG-guided retrieval.

#### Acceptance Criteria

1. WHEN a Concept_Recovery_Bridge is generated, THE Chunking_Framework SHALL pass the Concept_Recovery_Bridge through the Concept_Extractor to extract concepts, identically to standard bridge chunks.
2. THE Concept_Recovery_Bridge SHALL carry metadata containing `extracted_concepts`, `adjacent_chunk_ids`, `is_recovery_bridge: true`, and `target_bisected_concepts`.
3. THE Concept_Recovery_Bridge SHALL be included in the `bridges` list of the `ChunkingResult` alongside standard bridges.

### Requirement 6: Backward Compatibility and Configuration

**User Story:** As a system operator, I want concept-aware bridge recovery to be backward-compatible and configurable, so that existing behavior is preserved when the feature is disabled and all thresholds can be tuned.

#### Acceptance Criteria

1. THE Chunking_Framework SHALL expose a configurable `enable_concept_recovery_bridges` boolean parameter (default: `true`) that controls whether concept-recovery bridges are generated.
2. WHEN `enable_concept_recovery_bridges` is `false`, THE Chunking_Framework SHALL skip concept-recovery bridge generation entirely and produce results identical to the current pipeline.
3. ALL new configurable parameters (`enable_concept_recovery_bridges`, `recovery_bridge_context_chars`) SHALL be exposed as settings in `config.py` with environment variable overrides.
4. THE Bridge_Generator's `create_adaptive_prompt` method SHALL maintain its existing signature as a valid call (bisected concepts parameter is optional with default empty list).
