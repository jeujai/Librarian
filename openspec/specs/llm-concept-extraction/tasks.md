# Implementation Plan: LLM Concept Extraction

## Overview

Add real LLM-based concept extraction to the knowledge graph pipeline by wiring `OllamaClient` into `ConceptExtractor`. This involves renaming the misnamed `extract_concepts_llm` method, adding a domain prompt registry, implementing `extract_concepts_ollama` with anti-hallucination filtering, and integrating into the existing merge pipeline. All source changes are in `kg_builder.py` and its callers.

## Tasks

- [x] 1. Rename `extract_concepts_llm` to `extract_concepts_definition_patterns` and update all callers
  - [x] 1.1 Rename the method on `ConceptExtractor` in `src/multimodal_librarian/components/knowledge_graph/kg_builder.py`
    - Rename `extract_concepts_llm` → `extract_concepts_definition_patterns` (same signature, same body)
    - _Requirements: 1.1, 1.3_
  - [x] 1.2 Update callers in `KnowledgeGraphBuilder`
    - Update `extract_concepts_from_content` (line ~975) to call `extract_concepts_definition_patterns`
    - Update `extract_concepts_from_content_async` (line ~1009) to call `extract_concepts_definition_patterns`
    - _Requirements: 1.2_
  - [x] 1.3 Update callers in test and script files
    - Update `tests/components/test_knowledge_graph.py` test method `test_extract_concepts_llm` to call `extract_concepts_definition_patterns`
    - Update `scripts/test-kg-components-only.py` (line ~110) to call `extract_concepts_definition_patterns`
    - _Requirements: 1.2_
  - [ ]* 1.4 Write property test: definition patterns rename preserves behavior
    - **Property 1: Definition patterns rename preserves behavior**
    - Create `tests/components/test_llm_concept_extraction.py` with Hypothesis test
    - Generate random text with definition patterns ("X is a Y"), verify `extract_concepts_definition_patterns` output matches expected ConceptNode names, types, and confidences
    - **Validates: Requirements 1.1**

- [x] 2. Add domain prompt registry and prompt template at module level
  - [x] 2.1 Add `DOMAIN_PROMPT_REGISTRY` and `CONCEPT_EXTRACTION_PROMPT_TEMPLATE` to `kg_builder.py`
    - Add `from ...models.core import ContentType` import (ContentType is already partially imported via KnowledgeChunk)
    - Define `DOMAIN_PROMPT_REGISTRY: Dict[ContentType, Dict[str, Any]]` with entries for all 6 ContentType values (TECHNICAL, MEDICAL, LEGAL, ACADEMIC, NARRATIVE, GENERAL)
    - Define `CONCEPT_EXTRACTION_PROMPT_TEMPLATE` string with placeholders `{domain_description}`, `{concept_types}`, `{text}` and guardrail instructions
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 9.1, 9.2, 9.3, 9.4_
  - [ ]* 2.2 Write property test: registry covers all ContentTypes
    - **Property 3: Registry covers all ContentTypes**
    - Iterate all `ContentType` values, assert each has a registry entry with non-empty `domain_description` and non-empty `concept_types` list
    - **Validates: Requirements 3.1**
  - [ ]* 2.3 Write property test: formatted prompt contains all required elements
    - **Property 4: Formatted prompt contains all required elements**
    - For random ContentType and non-empty text, format the prompt and assert it contains: domain concept types, JSON field names (name, type, rationale), guardrail instruction, grounding instruction, and the source text
    - **Validates: Requirements 3.8, 3.9, 4.2, 9.1, 9.2, 9.3, 9.4**

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Add lazy OllamaClient initialization to ConceptExtractor
  - [x] 4.1 Add `_ollama_client` attribute and `_get_ollama_client` async method to `ConceptExtractor`
    - Add `self._ollama_client: Optional[OllamaClient] = None` in `__init__` (type annotation only, no import at top)
    - Implement `async def _get_ollama_client(self) -> Optional[OllamaClient]` following the `SmartBridgeGenerator._get_ollama_client()` pattern in `bridge_generator.py`
    - Lazy import `from ...clients.ollama_client import get_ollama_client` inside the method
    - Cache the client on `self._ollama_client` after first successful `is_available()` check
    - _Requirements: 2.1, 2.2, 2.3, 2.4_
  - [ ]* 4.2 Write property test: OllamaClient caching is idempotent
    - **Property 2: OllamaClient caching is idempotent**
    - Mock `get_ollama_client` and `is_available`, call `_get_ollama_client()` N times, assert same object reference returned each time
    - **Validates: Requirements 2.3**

- [x] 5. Implement `extract_concepts_ollama` with rationale filtering and confidence scoring
  - [x] 5.1 Implement `_filter_by_rationale` method on `ConceptExtractor`
    - Accept `candidates: List[Dict]` and `source_text: str`
    - Keep candidates where `rationale` is non-empty and `rationale.lower()` is a substring of `source_text.lower()`
    - Discard others with debug log
    - _Requirements: 5.1, 5.2, 5.3, 5.4_
  - [x] 5.2 Implement `extract_concepts_ollama` async method on `ConceptExtractor`
    - Signature: `async def extract_concepts_ollama(self, text: str, content_type: ContentType = ContentType.GENERAL) -> List[ConceptNode]`
    - Get client via `_get_ollama_client()`, return `[]` if unavailable
    - Look up prompt config from `DOMAIN_PROMPT_REGISTRY[content_type]`
    - Format `CONCEPT_EXTRACTION_PROMPT_TEMPLATE` and call `await client.generate(prompt, temperature=0.3, max_tokens=1000)`
    - Parse JSON array from response, apply `_filter_by_rationale`, create ConceptNodes with domain-aware confidence (0.70 for GENERAL/TECHNICAL/NARRATIVE/ACADEMIC, 0.65 for MEDICAL/LEGAL)
    - Wrap entire method in try/except returning `[]` on any error
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 5.1, 5.3, 6.1, 6.2, 6.3, 7.1, 7.2, 7.3_
  - [ ]* 5.3 Write property test: rationale filter correctness
    - **Property 7: Rationale filter keeps concepts iff rationale is substring of source**
    - Generate random source texts and candidate dicts with rationales (some substrings, some not, some empty), verify filter keeps/discards correctly
    - **Validates: Requirements 5.1, 5.2, 5.4**
  - [ ]* 5.4 Write property test: OllamaClient called with correct parameters
    - **Property 5: OllamaClient called with correct parameters**
    - Mock `OllamaClient.generate`, call `extract_concepts_ollama` with random text, inspect call args for `temperature=0.3` and text presence in prompt
    - **Validates: Requirements 4.3**
  - [ ]* 5.5 Write property test: valid JSON response produces ConceptNodes with correct types
    - **Property 6: Valid JSON response produces ConceptNodes with correct types**
    - Generate random valid JSON arrays with name/type/rationale (rationale drawn from source text), mock Ollama response, verify ConceptNode types match
    - **Validates: Requirements 4.4, 4.5**
  - [ ]* 5.6 Write property test: domain-aware confidence scoring
    - **Property 8: Domain-aware confidence scoring**
    - For each ContentType, mock a valid Ollama response, verify concepts get correct base confidence (0.70 or 0.65) and all values < 0.85
    - **Validates: Requirements 6.1, 6.2, 6.3**
  - [ ]* 5.7 Write property test: unavailable Ollama returns empty list
    - **Property 10: Unavailable Ollama returns empty list without exception**
    - Mock unavailable OllamaClient, call with random text and ContentType, verify empty list and no exception
    - **Validates: Requirements 7.2**

- [x] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Integrate Ollama extraction into `extract_all_concepts_async` and update callers
  - [x] 7.1 Update `extract_all_concepts_async` signature and body in `ConceptExtractor`
    - Add `content_type: ContentType = ContentType.GENERAL` parameter
    - Run NER and Ollama concurrently via `asyncio.gather`, regex synchronously
    - Merge all three result lists by normalized name, keeping higher confidence
    - _Requirements: 8.1, 8.2, 8.3, 8.4_
  - [x] 7.2 Update callers in `KnowledgeGraphBuilder` to pass `content_type`
    - Update `process_knowledge_chunk_async` to pass `content_type` from `chunk` metadata (default `ContentType.GENERAL`)
    - Update `process_knowledge_chunk_extract_only` to pass `content_type` from `chunk` metadata (default `ContentType.GENERAL`)
    - _Requirements: 8.2, 8.3, 8.5_
  - [ ]* 7.3 Write property test: merge pipeline keeps higher confidence on overlap
    - **Property 9: Merge pipeline keeps higher confidence on overlap**
    - Generate pairs of ConceptNodes with same normalized name but different confidences (LLM ≤ 0.70, regex/NER = 0.85), verify merge keeps 0.85
    - **Validates: Requirements 6.4**
  - [ ]* 7.4 Write property test: pipeline produces concepts when Ollama is down
    - **Property 11: Pipeline produces concepts from other methods when Ollama is down**
    - Mock unavailable Ollama but functional NER/regex, call with text containing known multi-word patterns, verify non-empty result
    - **Validates: Requirements 7.4**

- [x] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- All source changes are in `kg_builder.py` except caller updates in `test_knowledge_graph.py` and `test-kg-components-only.py`
- New test file: `tests/components/test_llm_concept_extraction.py` for all property-based tests
- Property tests use Hypothesis with `@settings(max_examples=100)` and `pytest-asyncio`
- The `OllamaClient` is used as-is from `ollama_client.py` — no modifications needed
- Follows existing patterns: lazy init from `bridge_generator.py`, graceful degradation from `extract_concepts_with_ner`
