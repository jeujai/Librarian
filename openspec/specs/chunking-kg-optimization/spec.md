## Purpose

This specification addresses gaps in the interaction between the dynamic chunking pipeline and the Knowledge Graph (KG) to maximize recall, accuracy, and precision across all information domains. The focus is on optimizing chunk sizes for embedding models, expanding concept extraction coverage, integrating bridge chunks into the KG, improving mixed-domain document handling, ensuring KG link stability across re-processing, and establishing measurable retrieval quality metrics.


### Key Terms
- **Content_Analyzer**: The `AutomatedContentAnalyzer` component that classifies documents into content domains and generates adaptive chunking requirements.
- **Chunking_Framework**: The `GenericMultiLevelChunkingFramework` that orchestrates content analysis, chunking, bridge generation, gap analysis, and validation.
- **Concept_Extractor**: The `ConceptExtractor` class in `kg_builder.py` that extracts concepts from chunk text using NER patterns, LLM, and embedding methods.
- **Bridge_Generator**: The `SmartBridgeGenerator` that creates bridge chunks between adjacent chunks to preserve cross-boundary context.
- **KG_Retrieval_Service**: The `KGRetrievalService` that retrieves and reranks chunks using KG concept matching and semantic similarity.
- **Chunk_ID**: A UUID-based identifier assigned to each `ProcessedChunk` during chunking.
- **Embedding_Model**: The sentence-transformers model used to generate vector embeddings for chunks and queries.
- **Recall**: The fraction of all relevant chunks that are successfully retrieved for a given query.
- **Precision**: The fraction of retrieved chunks that are actually relevant to a given query.
- **Domain_Classification**: The process of classifying document content into one of the supported content types (TECHNICAL, MEDICAL, LEGAL, ACADEMIC, NARRATIVE, GENERAL).
- **Bridge_Chunk**: A synthetic chunk generated between two adjacent chunks to preserve cross-boundary context.
- **Concept_Coverage**: The proportion of meaningful domain concepts in a chunk that are successfully extracted by the Concept_Extractor.
- **Multi_Word_Phrase**: A technical term composed of two or more words that functions as a single concept (e.g., "knowledge graph", "vector database", "machine learning").
- **Concept_Bisection**: The condition where a multi-word concept is split across a chunk boundary, causing neither chunk to contain the complete concept and preventing concept extraction from recognizing it.
- **Overlap_Window**: A configurable number of tokens at each side of a proposed chunk boundary that are inspected for concept bisection.
- **PMI (Pointwise Mutual Information)**: A statistical measure of association between words. High PMI for a word pair indicates they co-occur significantly more than chance, suggesting they form a meaningful unit (collocation).
- **Collocation**: A sequence of words that co-occur more often than expected by chance and function as a single semantic unit (e.g., "machine learning", "knowledge graph").
- **Cross_Reference**: An explicit textual pointer in a document that refers to content in a different, non-adjacent location (e.g., "see Chapter 3", "as discussed in Section 2.1", "refer to Figure 4").

## Requirements

### Requirement: Embedding-Aware Chunk Size Optimization

The system SHALL support: As a system operator, I want chunk sizes to be calibrated to the Embedding_Model's optimal input length, so that vector embeddings capture maximum semantic signal without truncation or dilution.

#### Scenario: THE Content_Analyzer SHALL expose a configurable `target_emb

- **THEN** THE Content_Analyzer SHALL expose a configurable `target_embedding_tokens` parameter that specifies the Embedding_Model's optimal input token count.

#### Scenario: WHEN generating chunking requirements, THE Content_Analyzer

- **THEN** WHEN generating chunking requirements, THE Content_Analyzer SHALL compute `preferred_chunk_size` as a function of `target_embedding_tokens`, domain type multiplier, complexity score, and conceptual density.

#### Scenario: WHEN the computed `preferred_chunk_size` exceeds the Embeddi

- **THEN** WHEN the computed `preferred_chunk_size` exceeds the Embedding_Model's maximum token limit, THE Content_Analyzer SHALL clamp the value to the maximum token limit.

#### Scenario: WHEN the computed `preferred_chunk_size` falls below a minim

- **THEN** WHEN the computed `preferred_chunk_size` falls below a minimum viable threshold, THE Content_Analyzer SHALL raise the value to the minimum viable threshold.

#### Scenario: THE Content_Analyzer SHALL allow the `target_embedding_token

- **THEN** THE Content_Analyzer SHALL allow the `target_embedding_tokens` parameter to be updated without code changes via configuration. #### Threshold Rationale All configurable thresholds are empirical starting points intended to be tuned via the retrieval quality metrics feedback loop (Requirement 9). Their initial values are informed by published research and model architecture constraints: - `target_embedding_tokens = 256`: Sentence-transformer models (e.g., `all-MiniLM-L6-v2`) are trained on sequences up to 256 tokens. Embeddings degrade when input length diverges significantly from training distribution (Reimers & Gurevych, 2019). Newer models like `bge-large-en-v1.5` handle 512 well, so this should be tuned per model. - `max_embedding_tokens = 512`: Hard architectural limit for most transformer models due to positional encoding ceiling. Tokens beyond this are truncated and lost. - `min_embedding_tokens = 64`: Below ~50 tokens, embeddings become noisy due to insufficient context for meaningful representation. 64 provides a conservative floor. - Domain type multipliers (TECHNICAL=1.2, LEGAL=1.5, MEDICAL=1.3, ACADEMIC=1.4, NARRATIVE=0.8, GENERAL=1.0): Heuristic values reflecting that dense technical/legal content benefits from larger chunks for context, while narrative content benefits from smaller chunks for specificity. These are starting points for empirical tuning, not derived from specific studies.

### Requirement: Expanded Concept Extraction for Multi-Word Phrases and Acronyms

The system SHALL support: As a system operator, I want the Concept_Extractor to identify multi-word technical phrases, acronyms, and domain-specific terminology — including novel terms not in any predefined list — so that the KG captures a more complete concept graph and improves retrieval recall.

#### Scenario: THE Concept_Extractor SHALL extract Multi_Word_Phrases using

- **THEN** THE Concept_Extractor SHALL extract Multi_Word_Phrases using a two-tier approach: (a) a seed list of known domain terminology patterns for high-confidence matches, and (b) statistical collocation detection using Pointwise Mutual Information (PMI) to discover novel multi-word concepts not in the seed list.

#### Scenario: THE Concept_Extractor SHALL extract acronyms and abbreviatio

- **THEN** THE Concept_Extractor SHALL extract acronyms and abbreviations of two or more uppercase characters (e.g., "KG", "RAG", "NLP", "API"), filtering out common English stopwords ("IT", "IS", "OR", "AN", "AT", "IF", "IN", "ON", "TO", "UP", "DO", "GO", "NO", "SO", "BY", "HE", "ME", "WE", "US").

#### Scenario: WHEN an acronym appears near its expanded form in the same c

- **THEN** WHEN an acronym appears near its expanded form in the same chunk, THE Concept_Extractor SHALL link the acronym and expansion as aliases of the same concept.

#### Scenario: THE Concept_Extractor SHALL categorize extracted Multi_Word_

- **THEN** THE Concept_Extractor SHALL categorize extracted Multi_Word_Phrases under a new `MULTI_WORD` concept type.

#### Scenario: THE Concept_Extractor SHALL categorize extracted acronyms un

- **THEN** THE Concept_Extractor SHALL categorize extracted acronyms under a new `ACRONYM` concept type.

#### Scenario: WHEN a concept is extracted via the new patterns, THE Concep

- **THEN** WHEN a concept is extracted via the new patterns, THE Concept_Extractor SHALL assign a confidence score based on pattern specificity and frequency within the chunk.

#### Scenario: THE Concept_Extractor SHALL compute PMI scores for candidate

- **THEN** THE Concept_Extractor SHALL compute PMI scores for candidate bigrams and trigrams within each document, and extract those exceeding a configurable PMI threshold as `MULTI_WORD` concepts.

#### Scenario: THE Concept_Extractor SHALL maintain a corpus-level collocat

- **THEN** THE Concept_Extractor SHALL maintain a corpus-level collocation frequency cache that is updated incrementally as new documents are processed, so that PMI scores improve over time without requiring full corpus recomputation. #### Confidence Score Rationale - `MULTI_WORD` (seed list match) base confidence = 0.85: High specificity — a curated phrase appearing in text is almost certainly a concept. Slightly below 1.0 to account for polysemy. - `MULTI_WORD` (PMI-discovered) base confidence = 0.65: Lower than seed matches because statistical collocation can produce false positives (e.g., "the following" has high PMI but isn't a concept). The PMI threshold filters most noise, but confidence reflects residual uncertainty. - `ACRONYM` base confidence = 0.6: Acronyms are inherently ambiguous without context ("API" is clear, "IT" could be a pronoun). Lower confidence reflects this ambiguity. - Frequency boost: +0.02 per additional occurrence within the chunk, capped at +0.

#### Scenario: Grounded in TF-IDF theory — repeated mentions within a focus

- **THEN** Grounded in TF-IDF theory — repeated mentions within a focused text segment increase the likelihood that the term is topically significant.

### Requirement: Concept Bisection Detection and Boundary Adjustment

The system SHALL support: As a system operator, I want the chunking pipeline to detect when a multi-word concept has been split across a chunk boundary, and adjust the boundary to maintain concept contiguity, so that concept extraction does not miss bisected terms.

#### Scenario: WHEN the Chunking_Framework selects a split point for a chun

- **THEN** WHEN the Chunking_Framework selects a split point for a chunk boundary, THE Chunking_Framework SHALL run concept extraction on the overlap zone (last `overlap_window` tokens of the preceding text and first `overlap_window` tokens of the following text) to detect concepts that span the proposed boundary.

#### Scenario: WHEN a concept spanning the proposed boundary is detected, T

- **THEN** WHEN a concept spanning the proposed boundary is detected, THE Chunking_Framework SHALL shift the boundary past the end of the spanning concept so that the entire concept falls within a single chunk.

#### Scenario: WHEN shifting the boundary would cause the chunk to exceed `

- **THEN** WHEN shifting the boundary would cause the chunk to exceed `max_chunk_size`, THE Chunking_Framework SHALL instead shift the boundary before the start of the spanning concept, placing the entire concept in the next chunk.

#### Scenario: WHEN multiple concepts span the proposed boundary, THE Chunk

- **THEN** WHEN multiple concepts span the proposed boundary, THE Chunking_Framework SHALL prioritize the concept with the highest confidence score for boundary adjustment.

#### Scenario: THE Chunking_Framework SHALL expose a configurable `overlap_

- **THEN** THE Chunking_Framework SHALL expose a configurable `overlap_window` parameter (default: 20 tokens) that controls the size of the boundary inspection zone.

#### Scenario: WHEN no concepts span the proposed boundary, THE Chunking_Fr

- **THEN** WHEN no concepts span the proposed boundary, THE Chunking_Framework SHALL leave the boundary unchanged.

### Requirement: Bridge Chunk KG Integration

The system SHALL support: As a system operator, I want bridge chunks to be indexed in the Knowledge Graph, so that cross-boundary concepts are discoverable during KG-guided retrieval.

#### Scenario: WHEN the Chunking_Framework generates a Bridge_Chunk, THE Ch

- **THEN** WHEN the Chunking_Framework generates a Bridge_Chunk, THE Chunking_Framework SHALL pass the Bridge_Chunk through the Concept_Extractor to extract concepts.

#### Scenario: WHEN concepts are extracted from a Bridge_Chunk, THE Chunkin

- **THEN** WHEN concepts are extracted from a Bridge_Chunk, THE Chunking_Framework SHALL store those concepts in the KG with `source_chunks` referencing the Bridge_Chunk's Chunk_ID.

#### Scenario: WHEN a Bridge_Chunk's concepts are stored in the KG, THE KG_

- **THEN** WHEN a Bridge_Chunk's concepts are stored in the KG, THE KG_Retrieval_Service SHALL treat Bridge_Chunk results identically to regular chunk results during retrieval.

#### Scenario: THE Bridge_Chunk SHALL carry metadata indicating the Chunk_I

- **THEN** THE Bridge_Chunk SHALL carry metadata indicating the Chunk_IDs of the two adjacent chunks it bridges.

### Requirement: Cross-Reference Relationship Extraction

The system SHALL support: As a system operator, I want explicit textual cross-references (e.g., "see Chapter 3", "as discussed in Section 2.1") to be captured as KG relationships between the referencing chunk and the referenced content, so that non-adjacent but semantically linked content is discoverable during retrieval.

#### Scenario: WHEN a chunk contains an explicit cross-reference pattern (e

- **THEN** WHEN a chunk contains an explicit cross-reference pattern (e.g., "see Section X", "as discussed in Chapter Y", "refer to Figure Z"), THE Concept_Extractor SHALL extract a `CROSS_REFERENCE` relationship linking the current chunk to the referenced target.

#### Scenario: WHEN the referenced target can be resolved to a specific chu

- **THEN** WHEN the referenced target can be resolved to a specific chunk or set of chunks (via section/chapter/page metadata), THE Concept_Extractor SHALL create a KG edge of type `REFERENCES` between the source chunk's concepts and the target chunk's concepts.

#### Scenario: WHEN the referenced target cannot be resolved to a specific

- **THEN** WHEN the referenced target cannot be resolved to a specific chunk (e.g., the referenced section is not yet processed), THE Concept_Extractor SHALL store the unresolved reference as a pending edge with the raw reference text, to be resolved during a post-processing reconciliation pass.

#### Scenario: THE KG_Retrieval_Service SHALL traverse `REFERENCES` edges d

- **THEN** THE KG_Retrieval_Service SHALL traverse `REFERENCES` edges during related chunk retrieval, treating cross-referenced chunks as hop_distance=1 from the referencing chunk's concepts.

### Requirement: Mixed-Domain Document Handling

The system SHALL support: As a system operator, I want documents containing multiple content domains to receive per-section domain classification, so that each section is chunked with parameters optimized for its specific domain.

#### Scenario: WHEN a document contains sections with distinct content doma

- **THEN** WHEN a document contains sections with distinct content domains, THE Content_Analyzer SHALL classify each section independently rather than assigning a single domain to the entire document.

#### Scenario: THE Content_Analyzer SHALL split a document into sections us

- **THEN** THE Content_Analyzer SHALL split a document into sections using structural cues (headings, chapter markers, significant topic shifts).

#### Scenario: WHEN per-section classification is performed, THE Content_An

- **THEN** WHEN per-section classification is performed, THE Content_Analyzer SHALL generate separate ChunkingRequirements for each classified section.

#### Scenario: WHEN a section's domain classification differs from the prec

- **THEN** WHEN a section's domain classification differs from the preceding section, THE Chunking_Framework SHALL apply the section-specific ChunkingRequirements to that section's text.

#### Scenario: IF a section is too short to classify reliably (fewer than 1

- **GIVEN** a section is too short to classify reliably (fewer than 100 tokens)
- **THEN** IF a section is too short to classify reliably (fewer than 100 tokens), THEN THE Content_Analyzer SHALL inherit the domain classification from the nearest preceding section.

### Requirement: Stable Chunk ID Linkage Across Re-Processing

The system SHALL support: As a system operator, I want chunk IDs to remain stable when a document is re-processed with the same content, so that KG concept-to-chunk links do not become stale.

#### Scenario: THE Chunking_Framework SHALL generate Chunk_IDs deterministi

- **THEN** THE Chunking_Framework SHALL generate Chunk_IDs deterministically from the document ID and chunk content hash.

#### Scenario: WHEN a document is re-processed with identical content, THE

- **THEN** WHEN a document is re-processed with identical content, THE Chunking_Framework SHALL produce the same Chunk_IDs as the previous processing run.

#### Scenario: WHEN a document is re-processed with modified content, THE C

- **THEN** WHEN a document is re-processed with modified content, THE Chunking_Framework SHALL produce new Chunk_IDs only for chunks whose content has changed.

#### Scenario: WHEN chunk IDs change during re-processing, THE Chunking_Fra

- **THEN** WHEN chunk IDs change during re-processing, THE Chunking_Framework SHALL emit a mapping of old Chunk_IDs to new Chunk_IDs for downstream KG update.

#### Scenario: IF a chunk is removed during re-processing, THEN THE Chunkin

- **GIVEN** a chunk is removed during re-processing
- **THEN** IF a chunk is removed during re-processing, THEN THE Chunking_Framework SHALL include the removed Chunk_ID in the change mapping with a null new ID.

### Requirement: Retrieval Quality Metrics

The system SHALL support: As a system operator, I want to measure recall, precision, and F1 score for the retrieval pipeline, so that I can quantify the impact of chunking and KG changes on retrieval quality.

#### Scenario: THE KG_Retrieval_Service SHALL compute and return recall, pr

- **THEN** THE KG_Retrieval_Service SHALL compute and return recall, precision, and F1 score when a ground-truth relevance set is provided alongside a query.

#### Scenario: WHEN computing recall, THE KG_Retrieval_Service SHALL calcul

- **THEN** WHEN computing recall, THE KG_Retrieval_Service SHALL calculate the fraction of ground-truth relevant chunk IDs that appear in the retrieved results.

#### Scenario: WHEN computing precision, THE KG_Retrieval_Service SHALL cal

- **THEN** WHEN computing precision, THE KG_Retrieval_Service SHALL calculate the fraction of retrieved chunk IDs that appear in the ground-truth relevant set.

#### Scenario: WHEN computing F1 score, THE KG_Retrieval_Service SHALL calc

- **THEN** WHEN computing F1 score, THE KG_Retrieval_Service SHALL calculate the harmonic mean of recall and precision.

#### Scenario: THE KG_Retrieval_Service SHALL expose a `evaluate_retrieval`

- **THEN** THE KG_Retrieval_Service SHALL expose a `evaluate_retrieval` method that accepts a query, ground-truth chunk IDs, and optional retrieval parameters, and returns a metrics dictionary.

#### Scenario: WHEN no ground-truth set is provided, THE KG_Retrieval_Servi

- **THEN** WHEN no ground-truth set is provided, THE KG_Retrieval_Service SHALL skip metrics computation and return results without metrics.

### Requirement: Threshold Tuning via Metrics Feedback Loop

The system SHALL support: As a system operator, I want all configurable thresholds (chunk sizes, confidence scores, PMI thresholds, overlap windows) to be adjustable via configuration and validated against retrieval quality metrics, so that I can empirically optimize the pipeline for my specific corpus.

#### Scenario: ALL configurable thresholds (target_embedding_tokens, min/ma

- **THEN** ALL configurable thresholds (target_embedding_tokens, min/max_embedding_tokens, domain multipliers, MULTI_WORD confidence, ACRONYM confidence, PMI threshold, overlap_window, frequency boost cap) SHALL be exposed as settings in `config.py` with environment variable overrides.

#### Scenario: THE `evaluate_retrieval` method SHALL accept an optional `th

- **THEN** THE `evaluate_retrieval` method SHALL accept an optional `threshold_overrides` dictionary that temporarily applies alternative threshold values for A/B comparison without modifying persistent configuration.

#### Scenario: THE `evaluate_retrieval` method SHALL return the threshold c

- **THEN** THE `evaluate_retrieval` method SHALL return the threshold configuration used alongside the metrics, so that results can be correlated with specific parameter values.
