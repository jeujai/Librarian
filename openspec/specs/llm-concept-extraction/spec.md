## Purpose

This feature adds real LLM-based concept extraction to the existing knowledge graph pipeline by wiring the existing `OllamaClient` (llama3.2:3b, localhost:11434) into the `ConceptExtractor` class. The system currently extracts concepts via regex patterns (MULTI_WORD, CODE_TERM, ACRONYM + PMI collocations), spaCy NER via model server, definition-pattern regex (misnamed `extract_concepts_llm`), and embedding similarity. This feature introduces a new `extract_concepts_ollama` async method that sends domain-specific prompts to the local Ollama instance, parses structured JSON responses, applies anti-hallucination filtering, and feeds results into the existing `_merge_similar_concepts` deduplication pipeline. The existing `extract_concepts_llm` method is renamed to `extract_concepts_definition_patterns` to reflect its actual behavior. No existing extraction methods are removed.


### Key Terms
- **ConceptExtractor**: Class in `kg_builder.py` responsible for extracting concepts from text using multiple methods (regex, NER, embedding, definition patterns)
- **KnowledgeGraphBuilder**: Orchestrator class in `kg_builder.py` that coordinates concept extraction, relationship extraction, and knowledge graph updates
- **OllamaClient**: Async HTTP client in `ollama_client.py` for local LLM inference via Ollama API (llama3.2:3b model on localhost:11434)
- **ContentType**: Enum in `core.py` with values TECHNICAL, LEGAL, MEDICAL, NARRATIVE, ACADEMIC, GENERAL used for domain-aware processing
- **ConceptNode**: Data model representing an extracted concept with fields concept_id, concept_name, concept_type, confidence, aliases, source_chunks
- **KnowledgeChunk**: Data model representing a chunk of processed content with metadata including content type
- **Domain_Prompt_Registry**: A mapping from ContentType to domain-specific prompt templates and concept type taxonomies
- **Rationale_Filter**: Post-processing step that verifies LLM-extracted concept rationales appear in the source text
- **Merge_Pipeline**: The `_merge_similar_concepts` method that deduplicates concepts by normalized name, keeping higher confidence

## Requirements

### Requirement: Rename Misnamed Definition Pattern Method

The system SHALL support: As a developer, I want the existing `extract_concepts_llm` method renamed to `extract_concepts_definition_patterns`, so that the method name accurately reflects its regex-based behavior and frees the naming space for real LLM extraction.

#### Scenario: THE ConceptExtractor SHALL provide a method named `extract_c

- **THEN** THE ConceptExtractor SHALL provide a method named `extract_concepts_definition_patterns` with the same signature and behavior as the current `extract_concepts_llm` method

#### Scenario: WHEN any caller references `extract_concepts_llm` for defini

- **THEN** WHEN any caller references `extract_concepts_llm` for definition-pattern extraction, THE KnowledgeGraphBuilder SHALL call `extract_concepts_definition_patterns` instead

#### Scenario: THE ConceptExtractor SHALL NOT contain a method named `extra

- **THEN** THE ConceptExtractor SHALL NOT contain a method named `extract_concepts_llm` after the rename

### Requirement: Lazy OllamaClient Initialization in ConceptExtractor

The system SHALL support: As a developer, I want the OllamaClient to be lazily initialized inside ConceptExtractor without import-time connections, so that the DI architecture is preserved and module imports remain non-blocking.

#### Scenario: THE ConceptExtractor SHALL store the OllamaClient reference

- **THEN** THE ConceptExtractor SHALL store the OllamaClient reference as `None` at construction time

#### Scenario: WHEN `extract_concepts_ollama` is called for the first time,

- **THEN** WHEN `extract_concepts_ollama` is called for the first time, THE ConceptExtractor SHALL initialize the OllamaClient using the `get_ollama_client` singleton factory

#### Scenario: THE ConceptExtractor SHALL cache the OllamaClient instance a

- **THEN** THE ConceptExtractor SHALL cache the OllamaClient instance after first initialization for subsequent calls

#### Scenario: THE ConceptExtractor SHALL NOT import or instantiate OllamaC

- **THEN** THE ConceptExtractor SHALL NOT import or instantiate OllamaClient at module import time or during `__init__`

### Requirement: Domain-Specific Prompt Registry

The system SHALL support: As a developer, I want domain-specific prompt templates mapped to each ContentType, so that the LLM receives tailored instructions with appropriate concept type taxonomies for each domain.

#### Scenario: THE Domain_Prompt_Registry SHALL map each ContentType value

- **THEN** THE Domain_Prompt_Registry SHALL map each ContentType value to a prompt configuration containing a domain description and a list of valid concept types

#### Scenario: WHEN ContentType is MEDICAL, THE Domain_Prompt_Registry SHAL

- **THEN** WHEN ContentType is MEDICAL, THE Domain_Prompt_Registry SHALL specify concept types DISEASE, DRUG, PROCEDURE, ANATOMY, LAB_TEST, GENE, PATHWAY

#### Scenario: WHEN ContentType is LEGAL, THE Domain_Prompt_Registry SHALL

- **THEN** WHEN ContentType is LEGAL, THE Domain_Prompt_Registry SHALL specify concept types STATUTE, CASE_NAME, DOCTRINE, PARTY, JURISDICTION, REGULATORY_BODY

#### Scenario: WHEN ContentType is TECHNICAL, THE Domain_Prompt_Registry SH

- **THEN** WHEN ContentType is TECHNICAL, THE Domain_Prompt_Registry SHALL specify concept types API, PROTOCOL, ALGORITHM, DATA_STRUCTURE, FRAMEWORK, DESIGN_PATTERN

#### Scenario: WHEN ContentType is ACADEMIC, THE Domain_Prompt_Registry SHA

- **THEN** WHEN ContentType is ACADEMIC, THE Domain_Prompt_Registry SHALL specify concept types THEORY, METHODOLOGY, RESEARCHER, INSTITUTION, DATASET, METRIC

#### Scenario: WHEN ContentType is NARRATIVE, THE Domain_Prompt_Registry SH

- **THEN** WHEN ContentType is NARRATIVE, THE Domain_Prompt_Registry SHALL specify concept types CHARACTER, LOCATION, EVENT, THEME, TIME_PERIOD

#### Scenario: WHEN ContentType is GENERAL, THE Domain_Prompt_Registry SHAL

- **THEN** WHEN ContentType is GENERAL, THE Domain_Prompt_Registry SHALL specify concept types ENTITY, TOPIC, ORGANIZATION, PERSON, LOCATION

#### Scenario: THE Domain_Prompt_Registry SHALL use a common prompt skeleto

- **THEN** THE Domain_Prompt_Registry SHALL use a common prompt skeleton across all domains requiring JSON output with fields name, type, and rationale

#### Scenario: THE Domain_Prompt_Registry SHALL include the guardrail instr

- **THEN** THE Domain_Prompt_Registry SHALL include the guardrail instruction "Only extract terms explicitly mentioned or directly implied" in every prompt

### Requirement: Ollama-Based Concept Extraction Method

The system SHALL support: As a developer, I want an async `extract_concepts_ollama` method that sends domain-aware prompts to the local Ollama instance and parses structured JSON responses into ConceptNode objects, so that the knowledge graph benefits from LLM semantic understanding.

#### Scenario: THE ConceptExtractor SHALL provide an async method `extract_

- **THEN** THE ConceptExtractor SHALL provide an async method `extract_concepts_ollama` accepting text content and a ContentType parameter

#### Scenario: WHEN `extract_concepts_ollama` is called, THE ConceptExtract

- **THEN** WHEN `extract_concepts_ollama` is called, THE ConceptExtractor SHALL select the prompt template from the Domain_Prompt_Registry based on the provided ContentType

#### Scenario: WHEN `extract_concepts_ollama` is called, THE ConceptExtract

- **THEN** WHEN `extract_concepts_ollama` is called, THE ConceptExtractor SHALL format the prompt with the source text and send the request to OllamaClient with temperature 0.3 and stream disabled

#### Scenario: WHEN OllamaClient returns a valid response, THE ConceptExtra

- **THEN** WHEN OllamaClient returns a valid response, THE ConceptExtractor SHALL parse the JSON array from the response content

#### Scenario: WHEN a parsed concept entry contains name, type, and rationa

- **THEN** WHEN a parsed concept entry contains name, type, and rationale fields, THE ConceptExtractor SHALL create a ConceptNode with concept_type set to the LLM-provided type value

#### Scenario: IF the OllamaClient response contains malformed JSON, THEN T

- **GIVEN** the OllamaClient response contains malformed JSON
- **THEN** IF the OllamaClient response contains malformed JSON, THEN THE ConceptExtractor SHALL log a warning and return an empty list

#### Scenario: IF the OllamaClient response contains an error, THEN THE Con

- **GIVEN** the OllamaClient response contains an error
- **THEN** IF the OllamaClient response contains an error, THEN THE ConceptExtractor SHALL log a warning and return an empty list

### Requirement: Anti-Hallucination Rationale Filtering

The system SHALL support: As a developer, I want every LLM-extracted concept validated against the source text via its rationale field, so that hallucinated concepts not grounded in the text are discarded.

#### Scenario: WHEN `extract_concepts_ollama` produces a list of candidate

- **THEN** WHEN `extract_concepts_ollama` produces a list of candidate concepts, THE Rationale_Filter SHALL verify that each concept's rationale text appears as a substring within the source text (case-insensitive)

#### Scenario: IF a concept's rationale text does not appear in the source

- **GIVEN** a concept's rationale text does not appear in the source text
- **THEN** IF a concept's rationale text does not appear in the source text, THEN THE Rationale_Filter SHALL discard that concept and log a debug message

#### Scenario: THE Rationale_Filter SHALL perform the verification after JS

- **THEN** THE Rationale_Filter SHALL perform the verification after JSON parsing and before returning the final concept list

#### Scenario: WHEN a concept's rationale is an empty string or missing, TH

- **THEN** WHEN a concept's rationale is an empty string or missing, THE Rationale_Filter SHALL discard that concept

### Requirement: Domain-Aware Confidence Scoring

The system SHALL support: As a developer, I want LLM-extracted concepts to receive domain-aware confidence scores that are lower than regex and NER baselines, so that the merge pipeline correctly prioritizes higher-certainty extraction methods while still incorporating novel LLM discoveries.

#### Scenario: THE ConceptExtractor SHALL assign a base confidence of 0.7 t

- **THEN** THE ConceptExtractor SHALL assign a base confidence of 0.7 to LLM-extracted concepts for GENERAL, TECHNICAL, NARRATIVE, and ACADEMIC content types

#### Scenario: THE ConceptExtractor SHALL assign a base confidence of 0.65

- **THEN** THE ConceptExtractor SHALL assign a base confidence of 0.65 to LLM-extracted concepts for MEDICAL and LEGAL content types

#### Scenario: THE ConceptExtractor SHALL ensure LLM-extracted concept conf

- **THEN** THE ConceptExtractor SHALL ensure LLM-extracted concept confidence values remain below the regex seed confidence of 0.85 and the NER confidence of 0.85

#### Scenario: WHEN an LLM-extracted concept overlaps with a regex or NER c

- **THEN** WHEN an LLM-extracted concept overlaps with a regex or NER concept during merge, THE Merge_Pipeline SHALL keep the higher confidence value from the regex or NER source

### Requirement: Graceful Degradation When Ollama Is Unavailable

The system SHALL support: As a developer, I want the LLM extraction to silently skip when Ollama is unavailable, so that the existing regex/NER/PMI pipeline continues to function without errors.

#### Scenario: WHEN `extract_concepts_ollama` is called, THE ConceptExtract

- **THEN** WHEN `extract_concepts_ollama` is called, THE ConceptExtractor SHALL first check OllamaClient availability via `is_available()`

#### Scenario: IF OllamaClient is not available, THEN THE ConceptExtractor

- **GIVEN** OllamaClient is not available
- **THEN** IF OllamaClient is not available, THEN THE ConceptExtractor SHALL log a warning and return an empty list without raising an exception

#### Scenario: IF OllamaClient times out during generation, THEN THE Concep

- **GIVEN** OllamaClient times out during generation
- **THEN** IF OllamaClient times out during generation, THEN THE ConceptExtractor SHALL log a warning and return an empty list without raising an exception

#### Scenario: WHILE Ollama is unavailable, THE KnowledgeGraphBuilder SHALL

- **THEN** WHILE Ollama is unavailable, THE KnowledgeGraphBuilder SHALL continue processing chunks using regex, NER, definition patterns, and embedding extraction methods

### Requirement: Integration into Extraction Orchestration

The system SHALL support: As a developer, I want the Ollama extraction results integrated into the existing async extraction pipeline alongside regex, NER, and embedding results, so that all extraction methods contribute to the merged concept set.

#### Scenario: WHEN `extract_all_concepts_async` is called, THE ConceptExtr

- **THEN** WHEN `extract_all_concepts_async` is called, THE ConceptExtractor SHALL invoke `extract_concepts_ollama` in addition to `extract_concepts_with_ner` and `extract_concepts_regex`

#### Scenario: THE ConceptExtractor SHALL pass the ContentType from the Kno

- **THEN** THE ConceptExtractor SHALL pass the ContentType from the KnowledgeChunk metadata to `extract_concepts_ollama`

#### Scenario: WHEN ContentType is not available in chunk metadata, THE Con

- **THEN** WHEN ContentType is not available in chunk metadata, THE ConceptExtractor SHALL default to ContentType.GENERAL for the Ollama extraction prompt

#### Scenario: THE ConceptExtractor SHALL feed Ollama extraction results in

- **THEN** THE ConceptExtractor SHALL feed Ollama extraction results into the existing `_merge_similar_concepts` deduplication alongside NER and regex results

#### Scenario: WHEN `process_knowledge_chunk_async` and `process_knowledge_

- **THEN** WHEN `process_knowledge_chunk_async` and `process_knowledge_chunk_extract_only` call the extraction pipeline, THE KnowledgeGraphBuilder SHALL include Ollama-extracted concepts in the combined result

### Requirement: Prompt Template Structure

The system SHALL support: As a developer, I want a consistent prompt template structure across all domains that enforces JSON output with grounding rationale, so that the LLM responses are parseable and verifiable.

#### Scenario: THE Domain_Prompt_Registry SHALL use a prompt template conta

- **THEN** THE Domain_Prompt_Registry SHALL use a prompt template containing: a domain-specific extraction instruction, the list of valid concept types for the domain, the JSON output format specification (name, type, rationale fields), the anti-hallucination guardrail, and the source text

#### Scenario: THE Domain_Prompt_Registry SHALL instruct the LLM to return

- **THEN** THE Domain_Prompt_Registry SHALL instruct the LLM to return a JSON array as the top-level response structure

#### Scenario: THE Domain_Prompt_Registry SHALL instruct the LLM to quote t

- **THEN** THE Domain_Prompt_Registry SHALL instruct the LLM to quote the supporting phrase from the source text in the rationale field

#### Scenario: THE Domain_Prompt_Registry SHALL include the instruction "Do

- **THEN** THE Domain_Prompt_Registry SHALL include the instruction "Do not infer concepts not grounded in the text" in every prompt
