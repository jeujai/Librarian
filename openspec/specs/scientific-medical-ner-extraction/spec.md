## Purpose

The Multimodal Librarian's relevance detector and query decomposer currently use spaCy's general-purpose `en_core_web_sm` model for named entity recognition (NER) during query processing. This model fails to identify scientific and medical terminology — extracting fragmented tokens like `['B', 'Healthcare', 'hepatitis']` instead of meaningful terms like `"hepatitis B surface antigen"` and `"healthcare worker"`. The library contains medical textbooks, clinical practice guidelines, and AI/ML textbooks, so accurate extraction of domain-specific terms is critical for retrieval quality.

This feature introduces a three-layer concurrent NER extraction system. Layer 1 (Base) uses spaCy's `en_core_web_sm` for general proper nouns (people, places, organizations, dates). Layer 2 (Scientific) uses scispaCy's `en_core_sci_sm` for scientific/medical entities (multi-word terms like "hepatitis B", "surface antigen"). Layer 3 (Medical Precision) adds a UMLS-enhanced n-gram lookup against the existing 1.6 million UMLS concepts in Neo4j for highest-precision medical terms (e.g., "hepatitis B surface antigen"). All three layers run concurrently for performance, and their results are merged with a priority hierarchy: UMLS > en_core_sci_sm > en_core_web_sm. Each layer degrades independently — if any single layer fails, the remaining layers still produce results.


### Key Terms
- **Relevance_Detector**: The `RelevanceDetector` class in `src/multimodal_librarian/components/kg_retrieval/relevance_detector.py` that evaluates chunk relevance using NER-based proper noun extraction, query term coverage analysis, and chunk filtering.
- **Query_Decomposer**: The `QueryDecomposer` class in `src/multimodal_librarian/components/kg_retrieval/query_decomposer.py` that decomposes user queries into entities, actions, and subjects for knowledge graph retrieval.
- **NER_Extractor**: A new module that encapsulates the three-layer concurrent NER extraction logic, providing a unified interface for extracting named entities from query text.
- **Layer_1_Base**: The base NER layer using spaCy's `en_core_web_sm` model, which recognizes general proper nouns — people, places, organizations, and dates.
- **Layer_2_Scientific**: The scientific NER layer using scispaCy's `en_core_sci_sm` model, which recognizes scientific and medical entities across biology, chemistry, computer science, and medicine (e.g., "hepatitis B", "surface antigen").
- **Layer_3_Medical**: The UMLS-enhanced precision layer that queries UMLSConcept nodes in Neo4j to find the longest, most specific medical terms (e.g., "hepatitis B surface antigen") via n-gram lookup.
- **UMLS_Client**: The existing `UMLSClient` class in `src/multimodal_librarian/components/knowledge_graph/umls_client.py` that provides cached, batched lookups against UMLSConcept and UMLSSynonym nodes in Neo4j.
- **DI_Provider**: The dependency injection provider in `src/multimodal_librarian/api/dependencies/services.py` that lazily initializes and caches service instances.
- **Key_Terms**: The set of named entities and noun phrases extracted from a query, used by the Relevance_Detector for chunk filtering and query term coverage analysis.
- **scispaCy**: A spaCy-based NLP library for biomedical and scientific text processing, providing models trained on biomedical corpora.
- **Merge_Hierarchy**: The three-way merge strategy where UMLS terms override shorter sci terms when they fully contain them, sci terms override shorter web terms when they fully contain them, and non-overlapping terms from all three layers are preserved. Override priority: UMLS > en_core_sci_sm > en_core_web_sm.
- **Concurrent_Execution**: All three NER layers run in parallel (via `asyncio.gather` or similar) so that total extraction latency is bounded by the slowest layer rather than the sum of all layers.

## Requirements

### Requirement: scispaCy Base Model Installation

The system SHALL support: As a system administrator, I want the scispaCy `en_core_sci_sm` model installed in the application container alongside the existing `en_core_web_sm` model, so that the NER system can run both general and scientific entity recognition concurrently.

#### Scenario: THE Dockerfile.app SHALL install the `scispacy` Python packa

- **THEN** THE Dockerfile.app SHALL install the `scispacy` Python package and the `en_core_sci_sm` model during the Docker image build, in addition to the existing `en_core_web_sm` model.

#### Scenario: THE requirements-app.txt SHALL include `scispacy` as a depen

- **THEN** THE requirements-app.txt SHALL include `scispacy` as a dependency with a pinned version range.

#### Scenario: WHEN the application container starts, THE NER_Extractor SHA

- **THEN** WHEN the application container starts, THE NER_Extractor SHALL be able to load both `en_core_web_sm` and `en_core_sci_sm` without downloading additional resources at runtime.

### Requirement: Layer 1 (Base) — en_core_web_sm NER Extraction

The system SHALL support: As a user querying general content, I want the system to use a general-purpose NER model as the base layer, so that proper nouns like people, places, organizations, and dates are reliably identified.

#### Scenario: THE NER_Extractor SHALL use `en_core_web_sm` as the Layer 1

- **THEN** THE NER_Extractor SHALL use `en_core_web_sm` as the Layer 1 (Base) spaCy model for general named entity recognition.

#### Scenario: WHEN a query containing general proper nouns is processed (e

- **THEN** WHEN a query containing general proper nouns is processed (e.g., "Chelsea", "Venezuela", "President"), THE Layer_1_Base SHALL extract those proper nouns as entities.

#### Scenario: THE NER_Extractor SHALL filter out numeric-only entities, ag

- **THEN** THE NER_Extractor SHALL filter out numeric-only entities, age descriptors (e.g., "72-year-old"), and entities with labels CARDINAL, ORDINAL, QUANTITY, DATE, TIME, PERCENT, and MONEY from the extracted Key_Terms.

#### Scenario: THE Layer_1_Base SHALL extract PROPN tokens (length > 2) and

- **THEN** THE Layer_1_Base SHALL extract PROPN tokens (length > 2) and capitalized NOUN tokens (length > 2) from noun chunks as Key_Terms.

### Requirement: Layer 2 (Scientific) — en_core_sci_sm NER Extraction

The system SHALL support: As a user querying medical or scientific content, I want the system to use a scientific NER model, so that multi-word scientific and medical terms in my queries are correctly identified as entities.

#### Scenario: THE NER_Extractor SHALL use `en_core_sci_sm` as the Layer 2

- **THEN** THE NER_Extractor SHALL use `en_core_sci_sm` as the Layer 2 (Scientific) spaCy model for scientific and medical entity recognition.

#### Scenario: WHEN a query containing scientific or medical terms is proce

- **THEN** WHEN a query containing scientific or medical terms is processed, THE Layer_2_Scientific SHALL extract multi-word entities (e.g., "hepatitis B", "surface antigen", "healthcare worker") rather than fragmenting them into individual tokens.

#### Scenario: THE Layer_2_Scientific SHALL apply the same entity filtering

- **THEN** THE Layer_2_Scientific SHALL apply the same entity filtering rules as Layer 1 (filtering out CARDINAL, ORDINAL, QUANTITY, DATE, TIME, PERCENT, MONEY labels, age descriptors, and numeric-only entities).

#### Scenario: THE Layer_2_Scientific SHALL run concurrently with Layer_1_B

- **THEN** THE Layer_2_Scientific SHALL run concurrently with Layer_1_Base and Layer_3_Medical via `asyncio.gather` or equivalent.

### Requirement: Layer 3 (Medical Precision) — UMLS-Enhanced Term Refinement

The system SHALL support: As a user querying clinical content, I want the system to refine extracted entities using the UMLS knowledge base, so that I get the most precise medical terms for retrieval (e.g., "hepatitis B surface antigen" instead of just "hepatitis B").

#### Scenario: THE Layer_3_Medical SHALL generate candidate n-grams from th

- **THEN** THE Layer_3_Medical SHALL generate candidate n-grams from the original query text by combining adjacent words into phrases of up to 5 tokens.

#### Scenario: THE Layer_3_Medical SHALL query the UMLS_Client to look up c

- **THEN** THE Layer_3_Medical SHALL query the UMLS_Client to look up candidate n-grams against UMLSConcept preferred names and synonyms in Neo4j.

#### Scenario: WHEN a UMLS match is found for a candidate n-gram, THE Layer

- **THEN** WHEN a UMLS match is found for a candidate n-gram, THE Layer_3_Medical SHALL include that term in its result set.

#### Scenario: WHEN multiple UMLS matches overlap in the query text, THE La

- **THEN** WHEN multiple UMLS matches overlap in the query text, THE Layer_3_Medical SHALL prefer the longest matching term.

#### Scenario: THE Layer_3_Medical SHALL complete the UMLS lookup within 20

- **THEN** THE Layer_3_Medical SHALL complete the UMLS lookup within 200 milliseconds for a typical query (under 50 words).

#### Scenario: THE Layer_3_Medical SHALL run concurrently with Layer_1_Base

- **THEN** THE Layer_3_Medical SHALL run concurrently with Layer_1_Base and Layer_2_Scientific via `asyncio.gather` or equivalent.

### Requirement: Three-Way Merge with Priority Hierarchy

The system SHALL support: As a developer, I want the results from all three NER layers merged with a clear priority hierarchy, so that the most precise terms are used for retrieval while preserving non-overlapping terms from all layers.

#### Scenario: THE NER_Extractor SHALL merge results from all three layers

- **THEN** THE NER_Extractor SHALL merge results from all three layers using the priority hierarchy: UMLS (Layer 3) > en_core_sci_sm (Layer 2) > en_core_web_sm (Layer 1).

#### Scenario: WHEN a UMLS term fully contains one or more shorter Layer 2

- **THEN** WHEN a UMLS term fully contains one or more shorter Layer 2 (sci) entities, THE merge logic SHALL replace those shorter sci entities with the longer UMLS term.

#### Scenario: WHEN a Layer 2 (sci) term fully contains one or more shorter

- **THEN** WHEN a Layer 2 (sci) term fully contains one or more shorter Layer 1 (web) entities, THE merge logic SHALL replace those shorter web entities with the longer sci term.

#### Scenario: THE merge logic SHALL preserve all non-overlapping terms fro

- **THEN** THE merge logic SHALL preserve all non-overlapping terms from all three layers in the final Key_Terms set.

#### Scenario: WHEN multiple terms from the same or different layers overla

- **THEN** WHEN multiple terms from the same or different layers overlap, THE merge logic SHALL prefer the longest matching term from the highest-priority layer.

### Requirement: Graceful Degradation

The system SHALL support: As a system operator, I want the NER system to degrade gracefully when any layer's dependencies are unavailable, so that query processing continues with the remaining layers.

#### Scenario: IF `en_core_web_sm` fails to load, THEN THE NER_Extractor SH

- **GIVEN** `en_core_web_sm` fails to load
- **THEN** IF `en_core_web_sm` fails to load, THEN THE NER_Extractor SHALL disable Layer 1 and log a warning; Layer 2 and Layer 3 SHALL still operate independently.

#### Scenario: IF `en_core_sci_sm` is not installed or fails to load, THEN

- **GIVEN** `en_core_sci_sm` is not installed or fails to load
- **THEN** IF `en_core_sci_sm` is not installed or fails to load, THEN THE NER_Extractor SHALL disable Layer 2 and log a warning; Layer 1 and Layer 3 SHALL still operate independently.

#### Scenario: IF the UMLS_Client is unavailable or returns None, THEN THE

- **GIVEN** the UMLS_Client is unavailable or returns None
- **THEN** IF the UMLS_Client is unavailable or returns None, THEN THE NER_Extractor SHALL skip Layer 3 and merge results from Layer 1 and Layer 2 only.

#### Scenario: IF the UMLS lookup exceeds 200 milliseconds, THEN THE NER_Ex

- **GIVEN** the UMLS lookup exceeds 200 milliseconds
- **THEN** IF the UMLS lookup exceeds 200 milliseconds, THEN THE NER_Extractor SHALL cancel the UMLS lookup, log a warning with the elapsed time, and merge results from Layer 1 and Layer 2 only.

#### Scenario: IF all three layers fail, THEN THE NER_Extractor SHALL retur

- **GIVEN** all three layers fail
- **THEN** IF all three layers fail, THEN THE NER_Extractor SHALL return an empty result and log an error.

#### Scenario: WHEN any degradation occurs, THE NER_Extractor SHALL log the

- **THEN** WHEN any degradation occurs, THE NER_Extractor SHALL log the degradation event with sufficient detail for diagnosis (layer name, model name attempted, error message, remaining active layers).

### Requirement: Integration with Relevance Detector

The system SHALL support: As a developer, I want the Relevance_Detector to use the new NER_Extractor, so that chunk filtering and query term coverage analysis benefit from improved entity extraction.

#### Scenario: THE DI_Provider SHALL initialize the NER_Extractor with both

- **THEN** THE DI_Provider SHALL initialize the NER_Extractor with both spaCy models and optionally the UMLS_Client, then pass the NER_Extractor to the Relevance_Detector.

#### Scenario: THE Relevance_Detector `filter_chunks_by_proper_nouns` metho

- **THEN** THE Relevance_Detector `filter_chunks_by_proper_nouns` method SHALL use Key_Terms produced by the NER_Extractor (including three-layer merged terms) for chunk filtering.

#### Scenario: THE `analyze_query_term_coverage` function SHALL use Key_Ter

- **THEN** THE `analyze_query_term_coverage` function SHALL use Key_Terms produced by the NER_Extractor for proper noun coverage analysis.

#### Scenario: WHEN the NER_Extractor produces merged terms from all three

- **THEN** WHEN the NER_Extractor produces merged terms from all three layers, THE Relevance_Detector SHALL use those merged terms in the `key_terms` set for the three-tier chunk filter.

### Requirement: Integration with Query Decomposer

The system SHALL support: As a developer, I want the Query_Decomposer to benefit from improved entity extraction, so that knowledge graph concept matching uses better query terms.

#### Scenario: THE Query_Decomposer SHALL accept an optional NER_Extractor

- **THEN** THE Query_Decomposer SHALL accept an optional NER_Extractor or spaCy model for entity-aware query tokenization.

#### Scenario: WHEN an NER_Extractor is available, THE Query_Decomposer `_f

- **THEN** WHEN an NER_Extractor is available, THE Query_Decomposer `_find_entity_matches` method SHALL use extracted multi-word entities as search terms in addition to individual word tokens, improving concept matching for compound medical terms.

### Requirement: Non-Regression for General Queries

The system SHALL support: As a user querying non-medical content, I want the system to continue extracting proper nouns and key terms accurately, so that queries about sports, geography, and general topics are not degraded.

#### Scenario: WHEN a query contains general proper nouns (e.g., "Chelsea",

- **THEN** WHEN a query contains general proper nouns (e.g., "Chelsea", "Venezuela", "President"), THE NER_Extractor SHALL extract those terms as Key_Terms via Layer 1 (and potentially Layer 2).

#### Scenario: WHEN a query contains no scientific or medical terms, THE La

- **THEN** WHEN a query contains no scientific or medical terms, THE Layer_3_Medical SHALL return an empty set of UMLS matches, and THE Layer_2_Scientific may return entities that overlap with Layer 1; the merge logic SHALL deduplicate them.

#### Scenario: THE NER_Extractor SHALL continue to extract capitalized NOUN

- **THEN** THE NER_Extractor SHALL continue to extract capitalized NOUN tokens from noun chunks (e.g., "President", "Minister") as Key_Terms, matching the existing behavior of the Relevance_Detector.

### Requirement: NER Extraction as a Reusable Module

The system SHALL support: As a developer, I want the NER extraction logic encapsulated in a dedicated module, so that both the Relevance_Detector and Query_Decomposer share the same extraction logic without duplication.

#### Scenario: THE NER_Extractor SHALL be implemented as a class in a new m

- **THEN** THE NER_Extractor SHALL be implemented as a class in a new module at `src/multimodal_librarian/components/kg_retrieval/ner_extractor.py`.

#### Scenario: THE NER_Extractor SHALL expose a method that accepts a query

- **THEN** THE NER_Extractor SHALL expose a method that accepts a query string and returns a structured result containing: the list of Layer 1 (web) entities, the list of Layer 2 (sci) entities, the list of Layer 3 (UMLS) entities, and the merged Key_Terms set.

#### Scenario: THE NER_Extractor SHALL accept both spaCy models (web and sc

- **THEN** THE NER_Extractor SHALL accept both spaCy models (web and sci) and an optional UMLS_Client as constructor parameters, following the project's dependency injection pattern.

#### Scenario: FOR ALL valid query strings, extracting entities then serial

- **GIVEN** ALL valid query strings, extracting entities then serializing and deserializing the result
- **THEN** FOR ALL valid query strings, extracting entities then serializing and deserializing the result SHALL produce an equivalent result (round-trip property).
