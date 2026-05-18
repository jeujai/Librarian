# Implementation Plan: Conversational Training Data

## Overview

This plan implements four new components (LOINCCleaner, LLMQuestionRewriter, QualityFilter, TokenBudgetManager) plus a RefusalFormatter utility, integrates them into the existing `RAGQAStrategy` pipeline, and adds comprehensive property-based and unit tests. Each task builds incrementally, starting with stateless utilities and ending with full pipeline integration and wiring.

## Tasks

- [x] 1. Implement LOINCCleaner utility module
  - [x] 1.1 Create `src/multimodal_librarian/ml/loinc_cleaner.py` with `clean_concept_name()` and `is_loinc_coded()` functions
    - Implement `_LOINC_PIPE_PATTERN`, `_HTML_ENTITY_PATTERN`, and `_CODED_SUFFIX_PATTERN` regex patterns
    - `clean_concept_name()` strips pipe-separated fields, HTML entities (`&#xNN;`), and coded suffixes (`ANYProp`, `ANYTm`, `ANYSys`, `ANYMeth`, `Pt`, `Bld`, `Ser`, `Plas`, etc.), returning the human-readable portion or empty string
    - `is_loinc_coded()` returns True if any LOINC pattern is present in the input
    - _Requirements: 1.3, 4.2_

  - [x] 1.2 Write property test for LOINC cleaning (Property 1)
    - **Property 1: LOINC cleaning removes all coded patterns**
    - Use `st.text()` with injected pipe/HTML/suffix patterns to generate LOINC-coded concept names
    - Assert `is_loinc_coded(clean_concept_name(raw))` returns False for all generated inputs
    - Assert cleaned output contains no pipe-separated fields, HTML entities, or coded suffixes
    - Test file: `tests/ml/test_conversational_training_data.py`
    - **Validates: Requirements 1.3, 4.2**

- [x] 2. Implement QualityFilter with textbook classifier and MCQ detection
  - [x] 2.1 Create `src/multimodal_librarian/ml/quality_filter.py` with `FilterResult`, `FilterSummary` dataclasses and `QualityFilter` class
    - Implement `evaluate()` method with all 6 checks: MCQ markers, LOINC instruction, uncited long response, response too short, textbook style, production-divergent style
    - Implement `classify_question_style()` using regex matching against textbook stems from `TEMPLATES_BY_SEMANTIC_TYPE` and exam-style patterns
    - Implement `summarize()` returning aggregate `FilterSummary` with per-reason breakdown
    - Use `estimate_tokens()` heuristic (chars / 4) for token-based length checks
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [x] 2.2 Write property test for textbook style classification (Property 2)
    - **Property 2: Textbook style classification correctness**
    - Use `st.sampled_from(TEXTBOOK_STEMS)` combined with `st.text()` to generate textbook-style questions
    - Assert `classify_question_style()` returns `"textbook"` for questions starting with known stems
    - Assert `classify_question_style()` returns `"conversational"` for questions without banned stems or exam patterns
    - Test file: `tests/ml/test_conversational_training_data.py`
    - **Validates: Requirements 1.1, 1.5, 4.5**

  - [x] 2.3 Write property test for MCQ marker detection (Property 3)
    - **Property 3: MCQ marker detection and rejection**
    - Generate response strings with varying counts of MCQ markers (`A.`, `B.`, `C.`, `D.`, `(a)`, `(b)`, `(c)`, `(d)`, `"correct answer is"`)
    - Assert rejection with reason `"mcq_markers"` when 3+ markers present
    - Assert no `"mcq_markers"` rejection when fewer than 3 markers
    - Test file: `tests/ml/test_conversational_training_data.py`
    - **Validates: Requirements 4.1**

  - [x] 2.4 Write property test for uncited long response rejection (Property 8)
    - **Property 8: Quality filter rejects uncited long responses**
    - Generate pairs with responses exceeding 800 estimated tokens and no `[Source N]` citations
    - Assert rejection with reason `"uncited_long_response"`
    - Generate pairs with responses ≤800 tokens or containing citations and assert no rejection for this reason
    - Test file: `tests/ml/test_conversational_training_data.py`
    - **Validates: Requirements 4.3**

  - [x] 2.5 Write property test for refusal length exemption (Property 9)
    - **Property 9: Quality filter exempts refusals from minimum length**
    - Generate short-response pairs (<50 tokens) and evaluate with `is_refusal=True` and `is_refusal=False`
    - Assert no `"response_too_short"` rejection when `is_refusal=True`
    - Assert `"response_too_short"` rejection when `is_refusal=False` and response <50 tokens
    - Test file: `tests/ml/test_conversational_training_data.py`
    - **Validates: Requirements 4.4**

  - [x] 2.6 Write property test for filter summary count invariant (Property 10)
    - **Property 10: Quality filter summary count invariant**
    - Generate lists of `InstructionTuningPair` objects, evaluate each, then call `summarize()`
    - Assert `total_evaluated == total_passed + total_rejected`
    - Assert `pass_rate == total_passed / total_evaluated` (when `total_evaluated > 0`)
    - Assert sum of `rejections_by_reason` values equals `total_rejected`
    - Test file: `tests/ml/test_conversational_training_data.py`
    - **Validates: Requirements 4.7**

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement RefusalFormatter utility
  - [x] 4.1 Create `src/multimodal_librarian/ml/refusal_formatter.py` with `REFUSAL_INDICATORS`, `is_refusal_response()`, `has_refusal_then_fabrication()`, and `format_refusal()` functions
    - `is_refusal_response()` checks for any phrase from `REFUSAL_INDICATORS` in the response text (case-insensitive)
    - `has_refusal_then_fabrication()` detects responses that start with a refusal but then provide unrelated medical info
    - `format_refusal()` produces a short (<200 tokens), conversational refusal that acknowledges the question without fabricating medical content
    - _Requirements: 2.1, 2.2, 2.4, 2.5_

  - [x] 4.2 Write property test for refusal detection (Property 4)
    - **Property 4: Refusal detection identifies refusal phrases**
    - Use `st.text()` with injected refusal indicator phrases
    - Assert `is_refusal_response()` returns True when any indicator is present
    - Assert `is_refusal_response()` returns False when no indicator is present
    - Test file: `tests/ml/test_conversational_training_data.py`
    - **Validates: Requirements 2.2**

  - [x] 4.3 Write property test for refusal formatting bounds (Property 5)
    - **Property 5: Refusal formatting produces bounded, non-fabricating responses**
    - Use `st.text(min_size=5, max_size=200)` for question strings
    - Assert `format_refusal()` output is under 200 estimated tokens (chars / 4)
    - Assert output contains a phrase indicating information is not available
    - Assert output does not contain medical dosage numbers, treatment regimen details, or drug interaction specifics
    - Test file: `tests/ml/test_conversational_training_data.py`
    - **Validates: Requirements 2.4**

  - [ ]* 4.4 Write unit tests for refusal-then-fabrication detection
    - Test `has_refusal_then_fabrication()` with known examples: response starting with "I could not find any information" followed by detailed drug info about a different substance
    - Test that pure refusals return False
    - Test that normal informative responses return False
    - Test file: `tests/ml/test_conversational_training_data_unit.py`
    - _Requirements: 2.5_

- [x] 5. Implement TokenBudgetManager
  - [x] 5.1 Create `src/multimodal_librarian/ml/token_budget.py` with `TokenBudgetManager` class
    - Implement `estimate_tokens()` using chars / 4.0 heuristic
    - Implement `estimate_pair_tokens()` accounting for system prompt + instruction + context + response + ~20 token chat template overhead
    - Implement `fits_budget()` comparing estimated tokens against `max_tokens` (default 5000)
    - Implement `summarize_response()` that uses LLM client to condense over-budget responses while preserving all `[Source N]` citations; returns None if no LLM client or summarization fails
    - _Requirements: 3.1, 3.2, 3.4, 3.5_

  - [x] 5.2 Write property test for token budget estimation consistency (Property 6)
    - **Property 6: Token budget estimation consistency**
    - Assert `fits_budget()` returns True iff `estimate_pair_tokens() <= max_tokens`
    - Assert `estimate_tokens()` is monotonically non-decreasing with respect to string length
    - Use `instruction_tuning_pair_strategy()` and `st.text()` for system prompts
    - Test file: `tests/ml/test_conversational_training_data.py`
    - **Validates: Requirements 3.1, 3.2**

  - [x] 5.3 Write property test for citation preservation through summarization (Property 7)
    - **Property 7: Citation preservation through summarization**
    - Generate response strings with injected `[Source N]` markers
    - Mock the LLM client to return a summarized response that preserves citations
    - Assert all original `[Source N]` markers appear in the summarized output
    - Test file: `tests/ml/test_conversational_training_data.py`
    - **Validates: Requirements 3.4**

  - [ ]* 5.4 Write unit tests for token budget edge cases
    - Test that summarized responses end with complete sentences (not truncated mid-word)
    - Test that pairs rejected for `"token_budget_exceeded"` are logged
    - Test with the production system prompt from `qlora_trainer.py`
    - Test file: `tests/ml/test_conversational_training_data_unit.py`
    - _Requirements: 3.3, 3.5_

- [x] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement LLMQuestionRewriter
  - [x] 7.1 Create `src/multimodal_librarian/ml/question_rewriter.py` with `LLMQuestionRewriter` class
    - Implement `rewrite_questions()` that batch-rewrites seed questions via LLM with a conversational rephrasing prompt
    - Implement `_rewrite_single()` for individual LLM calls with its own semaphore (default 4 concurrent)
    - On rewrite failure (LLM error, empty/short result, identical to input), keep the original question text
    - Log error-level message if >50% of rewrites fail
    - Set `source="llm_rewritten"` on successfully rewritten `SeedQuestion` objects
    - _Requirements: 1.1, 1.2, 1.4, 1.5_

  - [ ]* 7.2 Write unit tests for LLMQuestionRewriter
    - Test that failed rewrites preserve original question text
    - Test that successful rewrites set `source="llm_rewritten"`
    - Test that empty/short LLM responses (<10 chars) fall back to original
    - Test that >50% failure rate triggers error-level log
    - Mock the LLM client for all tests
    - Test file: `tests/ml/test_conversational_training_data_unit.py`
    - _Requirements: 1.1, 1.2_

- [x] 8. Implement confidence score computation and JSONL round-trip validation
  - [x]* 8.1 Write property test for confidence score bounds and monotonicity (Property 11)
    - **Property 11: Confidence score is bounded and monotonic**
    - Use `st.integers(min_value=0, max_value=100)` for citation counts and `st.integers(min_value=1, max_value=10)` for min_citations
    - Assert confidence score is in [0.0, 1.0] for all inputs
    - Assert for `a < b` (same `min_citations`), confidence(a) <= confidence(b)
    - Test the existing confidence scoring logic in `rag_qa_strategy.py`
    - Test file: `tests/ml/test_conversational_training_data.py`
    - **Validates: Requirements 5.4**

  - [x]* 8.2 Write property test for JSONL round-trip preservation (Property 12)
    - **Property 12: JSONL round-trip preservation for new pipeline output**
    - Generate `InstructionTuningPair` objects including pairs with `source="llm_rewritten"` metadata and refusal-formatted responses
    - Assert `InstructionTuningPair.from_jsonl_line(pair.to_jsonl_line()) == pair`
    - Reuse or extend `unicode_instruction_tuning_pair_strategy()` from existing test suite
    - Test file: `tests/ml/test_conversational_training_data.py`
    - **Validates: Requirements 7.1, 7.2**

- [x] 9. Integrate new components into RAGQAStrategy
  - [x] 9.1 Modify `RAGQAStrategy.__init__()` to accept optional `question_rewriter`, `quality_filter`, and `token_budget_manager` parameters
    - Store new dependencies as instance attributes
    - Maintain backward compatibility: all new parameters default to None
    - _Requirements: 5.1, 5.5_

  - [x] 9.2 Modify seed generation methods to use LOINCCleaner and LLMQuestionRewriter
    - In `_generate_umls_concept_seeds()` and `_generate_template_seeds()`, call `clean_concept_name()` before template filling; skip concepts that clean to empty
    - After all seeds are generated in `generate_seed_questions()`, pass them through `question_rewriter.rewrite_questions()` if the rewriter is available
    - Ensure at least 5 distinct phrasings per semantic type via the rewriter's diversity prompt
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [x] 9.3 Modify `_process_seed()` to integrate refusal detection, token budget, and quality filtering
    - After receiving RAG response, check `is_refusal_response()` and format with `format_refusal()` if detected; also check `has_refusal_then_fabrication()` and reject if detected
    - Check `token_budget_manager.fits_budget()` for non-refusal pairs; attempt `summarize_response()` if over budget; reject with `"token_budget_exceeded"` if summarization fails
    - Run `quality_filter.evaluate()` on the pair; skip (don't count toward target) if rejected
    - _Requirements: 2.1, 2.2, 2.4, 2.5, 3.1, 3.2, 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 9.4 Add post-generation logging: FilterSummary, refusal statistics, and warnings
    - After generation loop, log total pairs, rejection breakdown, refusal count/percentage, mean confidence score, and token-budget summarization count
    - Log warning if refusal percentage is outside 15%–30%
    - Log warning if rejection rate exceeds 40%
    - Invoke `progress_callback` consistent with existing API
    - _Requirements: 2.3, 8.1, 8.2, 8.3, 8.4_

- [x] 10. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Write integration tests and remaining unit tests
  - [ ]* 11.1 Write unit tests for pipeline observability and logging
    - Test that generation summary log contains expected fields (total, rejected, refusal count, mean confidence)
    - Test warning logged when refusal percentage outside 15–30%
    - Test warning logged when rejection rate exceeds 40%
    - Test that system prompt used in token budget matches `_SYSTEM_PROMPT` from `qlora_trainer.py`
    - Test that rejection log entries contain reason code and instruction text
    - Test file: `tests/ml/test_conversational_training_data_unit.py`
    - _Requirements: 4.6, 6.2, 8.1, 8.2, 8.3_

  - [ ]* 11.2 Write integration tests for full pipeline with mocked services
    - Test full `RAGQAStrategy.generate()` with mocked RAG service, Neo4j client, and LLM client
    - Assert LLM rewriter is called and produces non-identical outputs
    - Assert at least 5 distinct question phrasings per semantic type
    - Assert refusal pairs produced when RAG returns refusal responses
    - Assert concurrency controls preserved (semaphore limits)
    - Assert partial save file written incrementally
    - Assert citation format preserved from RAG response
    - Assert context field populated from RAG response sources
    - Test file: `tests/ml/test_conversational_training_data_integration.py`
    - _Requirements: 1.2, 1.4, 2.1, 5.1, 5.2, 5.3, 5.5_

- [x] 12. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate the 12 universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The project uses Python 3.9+, Pydantic 2.5+, asyncio, and Hypothesis for property-based testing
- All new modules go under `src/multimodal_librarian/ml/`
- All tests go under `tests/ml/`
- The token budget default is 5000 (from `TrainingConfig.max_seq_length`), not 4096
