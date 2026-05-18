## Purpose

The current proper noun coverage system in the Knowledge Graph-guided retrieval pipeline uses binary all-or-nothing logic: a single missing proper noun out of any number triggers a coverage gap, and chunk filtering requires ALL key nouns to be present. This works reasonably for queries with one or two proper nouns but becomes overly aggressive when queries contain many proper nouns (e.g., 15), where missing just one drops coverage to zero. This feature introduces adaptive coverage thresholds that scale with proper noun count, domain-aware threshold elevation for critical domains like medicine, and graduated chunk scoring that preserves relevance ranking order while still drawing a minimum coverage line for web search supplementation.


### Key Terms
- **Coverage_Threshold_Calculator**: The component that computes the required coverage ratio based on proper noun count and domain context
- **Relevance_Detector**: The existing component (`RelevanceDetector` class) that evaluates retrieval result quality using score distribution, concept specificity, and query term coverage signals
- **Coverage_Ratio**: The fraction of query proper nouns that are covered in retrieval results (covered_nouns / total_proper_nouns)
- **Proper_Noun_Count**: The total number of distinct proper nouns extracted from a query via spaCy NER
- **Domain_Classifier**: The component that determines the query's domain (medical, legal, technical, academic, business, general) using keyword pattern matching from `_extract_context_keywords()`
- **Chunk_Noun_Score**: A per-chunk score representing the fraction of key nouns present in that chunk's content
- **Adaptive_Threshold**: The dynamically computed minimum coverage ratio required before a proper noun gap is declared
- **Web_Search_Trigger**: The condition under which SearXNG web search supplementation is initiated to fill coverage gaps
- **RAG_Service**: The service (`rag_service.py`) that orchestrates post-processing, chunk filtering, and web search supplementation
- **KG_Retrieval_Service**: The service (`kg_retrieval_service.py`) that performs pre-reranking proper noun filtering

## Requirements

### Requirement: Adaptive Coverage Threshold Calculation

The system SHALL support: As a user querying with many proper nouns, I want the system to scale its coverage expectations based on how many proper nouns are in my query, so that a single missing noun out of fifteen does not incorrectly flag my results as irrelevant.

#### Scenario: WHEN a query contains 1 or 2 proper nouns, THE Coverage_Thre

- **THEN** WHEN a query contains 1 or 2 proper nouns, THE Coverage_Threshold_Calculator SHALL require 100% coverage ratio (all proper nouns must be covered)

#### Scenario: WHEN a query contains 3 or more proper nouns, THE Coverage_T

- **THEN** WHEN a query contains 3 or more proper nouns, THE Coverage_Threshold_Calculator SHALL compute an Adaptive_Threshold using a monotonically decreasing function of Proper_Noun_Count that floors at a configurable minimum (default 70%)

#### Scenario: THE Coverage_Threshold_Calculator SHALL declare a proper nou

- **THEN** THE Coverage_Threshold_Calculator SHALL declare a proper noun gap only when the Coverage_Ratio falls below the computed Adaptive_Threshold

#### Scenario: THE Coverage_Threshold_Calculator SHALL expose the Adaptive_

- **THEN** THE Coverage_Threshold_Calculator SHALL expose the Adaptive_Threshold value on the QueryTermCoverageResult dataclass for downstream consumers

#### Scenario: WHEN the Proper_Noun_Count is 0, THE Coverage_Threshold_Calc

- **THEN** WHEN the Proper_Noun_Count is 0, THE Coverage_Threshold_Calculator SHALL return a Coverage_Ratio of 1.0 and declare no gap

### Requirement: Domain-Aware Threshold Elevation

The system SHALL support: As a user making a medical or legal query, I want the system to apply stricter coverage requirements for critical domains, so that incomplete results in high-stakes contexts are flagged more aggressively.

#### Scenario: WHEN the Domain_Classifier detects a medical domain query, T

- **THEN** WHEN the Domain_Classifier detects a medical domain query, THE Coverage_Threshold_Calculator SHALL elevate the Adaptive_Threshold to a minimum of 95% coverage

#### Scenario: WHEN the Domain_Classifier detects a legal domain query, THE

- **THEN** WHEN the Domain_Classifier detects a legal domain query, THE Coverage_Threshold_Calculator SHALL elevate the Adaptive_Threshold to a minimum of 90% coverage

#### Scenario: WHEN the Domain_Classifier detects a general, technical, aca

- **THEN** WHEN the Domain_Classifier detects a general, technical, academic, or business domain query, THE Coverage_Threshold_Calculator SHALL use the standard Adaptive_Threshold without elevation

#### Scenario: THE Coverage_Threshold_Calculator SHALL accept domain thresh

- **THEN** THE Coverage_Threshold_Calculator SHALL accept domain threshold overrides as configurable parameters so operators can tune thresholds per deployment

#### Scenario: WHEN domain detection is unavailable or returns no domain, T

- **THEN** WHEN domain detection is unavailable or returns no domain, THE Coverage_Threshold_Calculator SHALL fall back to the standard Adaptive_Threshold

### Requirement: Graduated Chunk Noun Scoring

The system SHALL support: As a user, I want chunks to receive partial credit for containing some but not all key nouns, so that a chunk covering 12 out of 15 proper nouns is ranked higher than one covering 3 out of 15 rather than both being dropped equally.

#### Scenario: THE RAG_Service SHALL compute a Chunk_Noun_Score for each ch

- **THEN** THE RAG_Service SHALL compute a Chunk_Noun_Score for each chunk as the fraction of key nouns present in that chunk's content

#### Scenario: WHEN filtering chunks in post-processing, THE RAG_Service SH

- **THEN** WHEN filtering chunks in post-processing, THE RAG_Service SHALL retain chunks whose Chunk_Noun_Score meets or exceeds the Adaptive_Threshold instead of requiring all key nouns

#### Scenario: THE RAG_Service SHALL sort retained chunks by Chunk_Noun_Sco

- **THEN** THE RAG_Service SHALL sort retained chunks by Chunk_Noun_Score descending as a secondary sort key (after final_score) so that chunks with higher noun coverage rank higher among equally-scored chunks

#### Scenario: WHEN no chunks meet the Adaptive_Threshold, THE RAG_Service

- **THEN** WHEN no chunks meet the Adaptive_Threshold, THE RAG_Service SHALL fall back to retaining the top chunks by Chunk_Noun_Score rather than dropping all chunks

### Requirement: Relevance Ranking Preservation

The system SHALL support: As a user, I want the system to guarantee that chunks with higher relevance scores always appear before chunks with lower relevance scores, so that partial noun coverage adjustments cannot cause less relevant results to outrank more relevant ones.

#### Scenario: THE RAG_Service SHALL use final_score as the primary sort ke

- **THEN** THE RAG_Service SHALL use final_score as the primary sort key and Chunk_Noun_Score as the secondary sort key when ordering results

#### Scenario: THE RAG_Service SHALL apply noun-based filtering only as a r

- **THEN** THE RAG_Service SHALL apply noun-based filtering only as a retention threshold, not as a score modifier that could reorder chunks by final_score

#### Scenario: WHEN two chunks have equal final_score values, THE RAG_Servi

- **THEN** WHEN two chunks have equal final_score values, THE RAG_Service SHALL rank the chunk with the higher Chunk_Noun_Score first

### Requirement: Pre-Reranking Filter Adaptation

The system SHALL support: As a developer, I want the pre-reranking proper noun filter to use adaptive thresholds instead of all-or-nothing matching, so that the filter does not prematurely discard chunks that have strong partial noun coverage.

#### Scenario: WHEN the two-tier filter in KG_Retrieval_Service finds no ch

- **THEN** WHEN the two-tier filter in KG_Retrieval_Service finds no chunks matching ALL key terms, THE KG_Retrieval_Service SHALL fall back to chunks matching at least the Adaptive_Threshold fraction of key terms instead of falling back to ANY single key term

#### Scenario: THE KG_Retrieval_Service SHALL pass the Adaptive_Threshold t

- **THEN** THE KG_Retrieval_Service SHALL pass the Adaptive_Threshold to the filter_chunks_by_proper_nouns method so the filter can apply graduated matching

#### Scenario: WHEN no chunks meet the Adaptive_Threshold fraction of key t

- **THEN** WHEN no chunks meet the Adaptive_Threshold fraction of key terms, THE KG_Retrieval_Service SHALL fall back to chunks matching ANY key term to avoid returning an empty set

### Requirement: Web Search Supplementation Trigger

The system SHALL support: As a user, I want the system to trigger web search supplementation only when too few chunks survive adaptive threshold filtering, so that web results fill genuine gaps rather than triggering on coverage ratio alone.

#### Scenario: WHEN the number of chunks whose Chunk_Noun_Score meets or ex

- **THEN** WHEN the number of chunks whose Chunk_Noun_Score meets or exceeds the Adaptive_Threshold is fewer than the web_search_result_count_threshold (default 3), THE RAG_Service SHALL trigger SearXNG web search supplementation

#### Scenario: WHEN 3 or more chunks survive adaptive threshold filtering,

- **THEN** WHEN 3 or more chunks survive adaptive threshold filtering, THE RAG_Service SHALL NOT trigger web search supplementation for the proper noun coverage signal (other signals such as score-based irrelevance may still trigger web search independently)

#### Scenario: THE RAG_Service SHALL merge web search results with retained

- **THEN** THE RAG_Service SHALL merge web search results with retained local chunks using the existing merge-and-sort logic, preserving the librarian boost for local results

#### Scenario: IF SearXNG is unavailable, THEN THE RAG_Service SHALL procee

- **GIVEN** SearXNG is unavailable
- **THEN** IF SearXNG is unavailable, THEN THE RAG_Service SHALL proceed with the retained local chunks without error

#### Scenario: THE web_search_result_count_threshold SHALL remain configura

- **THEN** THE web_search_result_count_threshold SHALL remain configurable via the existing settings parameter

### Requirement: Co-occurrence Gap Adaptation

The system SHALL support: As a user querying with many proper nouns, I want the co-occurrence check to also use adaptive thresholds, so that a chunk containing 13 out of 15 key nouns is not treated the same as a chunk containing 1 out of 15.

#### Scenario: WHEN checking co-occurrence, THE Relevance_Detector SHALL co

- **THEN** WHEN checking co-occurrence, THE Relevance_Detector SHALL compute a per-chunk co-occurrence score as the fraction of key nouns present in each chunk

#### Scenario: THE Relevance_Detector SHALL declare a co-occurrence gap onl

- **THEN** THE Relevance_Detector SHALL declare a co-occurrence gap only when no chunk achieves a co-occurrence score meeting or exceeding the Adaptive_Threshold

#### Scenario: WHEN at least one chunk meets the Adaptive_Threshold for co-

- **THEN** WHEN at least one chunk meets the Adaptive_Threshold for co-occurrence, THE Relevance_Detector SHALL set has_cooccurrence_gap to False

### Requirement: Configuration and Observability

The system SHALL support: As an operator, I want all adaptive threshold parameters to be configurable and all threshold decisions to be logged, so that I can tune the system and diagnose coverage decisions in production.

#### Scenario: THE Coverage_Threshold_Calculator SHALL accept the following

- **THEN** THE Coverage_Threshold_Calculator SHALL accept the following configurable parameters: base_threshold_floor (default 0.70), medical_threshold (default 0.95), legal_threshold (default 0.90), small_query_noun_limit (default 2)

#### Scenario: WHEN a coverage decision is made, THE Relevance_Detector SHA

- **THEN** WHEN a coverage decision is made, THE Relevance_Detector SHALL log the Proper_Noun_Count, computed Adaptive_Threshold, actual Coverage_Ratio, detected domain, and gap decision at INFO level

#### Scenario: THE QueryTermCoverageResult SHALL include the adaptive_thres

- **THEN** THE QueryTermCoverageResult SHALL include the adaptive_threshold and detected_domain fields so downstream consumers can inspect the decision basis
