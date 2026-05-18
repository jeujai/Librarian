# Implementation Plan: LLM Judge Evaluation

## Overview

Replace the cosine-similarity and UMLS concept-recall scoring in the evaluation pipeline with an LLM-as-judge approach using DeepSeek. This involves creating a new `JudgeService` class, updating data models, modifying `EvaluationRunner` to use judge-based scoring, updating the CLI entry point, and producing new JSON/Markdown report formats. All changes are in Python, targeting the existing `src/multimodal_librarian/ml/` package and `tests/ml/` test directory.

## Tasks

- [x] 1. Update data models in `src/multimodal_librarian/ml/models.py`
  - [x] 1.1 Add `DimensionScores` Pydantic model with four integer fields (`factual_accuracy`, `completeness`, `clinical_relevance`, `coherence`) each constrained to `ge=1, le=5`
    - Add `Field(..., ge=1, le=5)` for each dimension
    - _Requirements: 2.5, 9.5_
  - [x] 1.2 Add `JudgeVerdict` Pydantic model with `response_a_scores: DimensionScores`, `response_b_scores: DimensionScores`, `winner: str`, `explanation: str`
    - Include `field_validator` on `winner` that normalizes to uppercase and defaults unrecognized values to `"TIE"`
    - _Requirements: 2.2, 11.3_
  - [x] 1.3 Add `JudgeResult` Pydantic model with `base_scores: DimensionScores`, `finetuned_scores: DimensionScores`, `winner: str`, `explanation: str`, `position_label: str`
    - _Requirements: 3.2, 4.1_
  - [x] 1.4 Replace the `ResponseScore` dataclass: change fields from `semantic_similarity`/`concept_recall` to `factual_accuracy`, `completeness`, `clinical_relevance`, `coherence` (integers 1–5)
    - _Requirements: 9.5_
  - [x] 1.5 Update `QuestionResult` dataclass to add `winner: str`, `judge_explanation: str`, and `position_label: str` fields
    - _Requirements: 4.1, 4.2_
  - [x] 1.6 Update `ComparisonReport` dataclass: replace `base_mean_similarity`/`finetuned_mean_similarity` with `win_rate`, `mean_score_delta`, add `judge_stats: Dict[str, Any]`, `base_mean_scores: Dict[str, float]`, `finetuned_mean_scores: Dict[str, float]`
    - _Requirements: 5.1, 5.2, 5.3, 7.2, 7.5_
  - [x] 1.7 Write property tests for `DimensionScores` validation bounds (Property 3)
    - **Property 3: Dimension score validation bounds**
    - **Validates: Requirements 2.5, 9.5**
  - [x] 1.8 Write property test for `JudgeVerdict` round-trip serialization (Property 2)
    - **Property 2: Judge verdict JSON round-trip**
    - **Validates: Requirements 2.2, 11.1, 11.4**
  - [x] 1.9 Write property test for invalid winner defaults to tie (Property 12)
    - **Property 12: Invalid winner defaults to tie**
    - **Validates: Requirements 11.3**

- [x] 2. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Implement `JudgeService` in `src/multimodal_librarian/ml/judge_service.py`
  - [x] 3.1 Create `JudgeService` class with `__init__` accepting `DeepSeekAIService`, `max_retries: int = 2`, `temperature: float = 0.1`
    - Store the DeepSeek service, retry count, temperature, and success/failure counters
    - _Requirements: 2.1_
  - [x] 3.2 Implement `build_judge_prompt` method that constructs the judge prompt with question, gold answer, Response A, Response B, scoring instructions (four dimensions, 1–5 scale), winner instruction ("A", "B", or "tie"), and JSON format specification
    - _Requirements: 1.1, 1.3, 1.4, 1.5_
  - [x] 3.3 Implement `parse_judge_response` method that extracts JSON from raw LLM output (handling markdown code fences and surrounding text), parses into `JudgeVerdict`, clamps out-of-range scores to [1, 5], and logs warnings for clamped values or unrecognized winners
    - _Requirements: 2.2, 2.5, 2.6, 11.1, 11.2, 11.3_
  - [x] 3.4 Implement `judge_pair` method that randomly assigns base/finetuned to A/B labels, calls `build_judge_prompt`, sends to DeepSeek via `generate_response` with low temperature, parses the response, retries up to `max_retries` on parse failure, maps the verdict winner back to model identities, and returns a `JudgeResult`
    - On all retries exhausted, raise an exception or return a sentinel indicating failure
    - _Requirements: 1.2, 2.1, 2.3, 2.4, 3.1, 3.2_
  - [x] 3.5 Implement `verify_available` method that delegates to `DeepSeekAIService.verify_available()`
    - _Requirements: 10.1_
  - [x] 3.6 Write property test for prompt construction includes all inputs (Property 1)
    - **Property 1: Prompt construction includes all inputs with correct A/B ordering**
    - **Validates: Requirements 1.1, 1.2, 3.1**
  - [x] 3.7 Write property test for dimension score clamping (Property 4)
    - **Property 4: Dimension score clamping**
    - **Validates: Requirements 2.6**
  - [x] 3.8 Write property test for winner mapping consistency (Property 5)
    - **Property 5: Winner mapping consistency**
    - **Validates: Requirements 3.2**
  - [x] 3.9 Write property test for code fence JSON extraction (Property 11)
    - **Property 11: Code fence JSON extraction**
    - **Validates: Requirements 11.2**

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Modify `EvaluationRunner` in `src/multimodal_librarian/ml/evaluation_runner.py`
  - [x] 5.1 Remove embedding and concept-recall methods: `_load_embedding_model`, `_embed`, `_extract_candidate_concepts`, `_compute_concept_recall`, `_score_response`, and the `_cosine_similarity` module-level function
    - Remove the `numpy` import and `sentence-transformers` dependency from this module
    - Remove `self._embedding_model` and `self._embedding_fallback` from `__init__`
    - _Requirements: 9.1, 9.2, 9.3, 9.4_
  - [x] 5.2 Update `__init__` to accept a `JudgeService` instance (stored as `self._judge`) instead of managing embedding models
    - _Requirements: 9.1_
  - [x] 5.3 Update `evaluate` method to use `JudgeService.judge_pair()` for each question instead of `_score_response`, collect `JudgeResult` objects, build `QuestionResult` with new fields (`winner`, `judge_explanation`, `position_label`), skip questions where judge fails after retries, and track success/failure counts
    - _Requirements: 2.3, 2.4, 4.1, 10.2, 10.3, 10.5_
  - [x] 5.4 Update `_build_report` to compute `win_rate`, `mean_score_delta`, `improvement_delta` (= win_rate - 0.5), per-dimension mean scores for both models, per-semantic-type and per-difficulty breakdowns with `win_rate`, `mean_score_delta`, `base_mean_scores`, `finetuned_mean_scores`, and `count`
    - Include `judge_stats` dict with `total_questions`, `successful_judgments`, `failed_judgments`, `judge_model`
    - Flag if improvement_delta < threshold OR if >50% of judge calls failed
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.3, 10.4_
  - [x] 5.5 Update `_export_json_report` to output the new JSON schema with top-level fields: `win_rate`, `mean_score_delta`, `improvement_delta`, `flagged`, `recommendations`, `by_semantic_type`, `by_difficulty`, `judge_stats`, `results`
    - Each result entry includes all per-question fields including `winner`, `judge_explanation`, `position_label`, and four dimension scores per model
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_
  - [x] 5.6 Update `_export_markdown_report` to output the new Markdown format with summary table (win rate, mean score delta, improvement delta, flagged, total questions), per-dimension breakdown table, per-semantic-type table, and per-difficulty table
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_
  - [x] 5.7 Write property test for aggregate metrics computation (Property 6)
    - **Property 6: Aggregate metrics computation**
    - **Validates: Requirements 5.1, 5.2, 5.3, 6.1**
  - [x] 5.8 Write property test for breakdown computation by grouping key (Property 7)
    - **Property 7: Breakdown computation by grouping key**
    - **Validates: Requirements 5.4, 5.5**
  - [x] 5.9 Write property test for flagging threshold (Property 8)
    - **Property 8: Flagging threshold**
    - **Validates: Requirements 6.2**
  - [x] 5.10 Write property test for JSON report required fields (Property 9)
    - **Property 9: JSON report contains all required fields**
    - **Validates: Requirements 7.2, 7.3, 7.4**
  - [x] 5.11 Write property test for Markdown report contains report values (Property 10)
    - **Property 10: Markdown report contains report values**
    - **Validates: Requirements 8.2**
  - [x] 5.12 Write property test for high failure rate triggers flagging (Property 13)
    - **Property 13: High failure rate triggers flagging**
    - **Validates: Requirements 10.4**

- [x] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Update CLI entry point `src/multimodal_librarian/ml/evaluate.py`
  - [x] 7.1 Update `main` to instantiate `DeepSeekAIService`, then `JudgeService`, then pass `JudgeService` to `EvaluationRunner`
    - Call `judge_service.verify_available()` before starting evaluation to fail fast if DeepSeek is unreachable
    - Remove `--embedding-model` CLI argument, add `--judge-temperature` and `--judge-retries` optional arguments
    - _Requirements: 2.1, 10.1_
  - [x] 7.2 Update the summary output to display win rate, mean score delta, and per-dimension scores instead of similarity metrics
    - _Requirements: 8.2_
  - [ ]* 7.3 Write unit tests for CLI wiring: verify `DeepSeekAIService` and `JudgeService` are instantiated and passed correctly, verify `verify_available` is called before evaluation
    - _Requirements: 10.1_

- [x] 8. Update existing tests in `tests/ml/test_evaluation_runner.py`
  - [x] 8.1 Remove or update tests that reference `_cosine_similarity`, `_score_response`, `_load_embedding_model`, `_embed`, `_extract_candidate_concepts`, `_compute_concept_recall`, `ResponseScore.semantic_similarity`, or `ResponseScore.concept_recall`
    - Update any test fixtures that construct `ResponseScore`, `QuestionResult`, or `ComparisonReport` to use the new field names
    - _Requirements: 9.1, 9.2, 9.3, 9.4_
  - [x] 8.2 Write integration test: mock both Ollama and DeepSeek, run full `evaluate()`, verify JSON and Markdown reports are produced with correct structure
    - _Requirements: 7.1, 7.2, 8.1_

- [x] 9. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate the 13 universal correctness properties defined in the design document
- Unit tests validate specific examples and edge cases
- The design uses Python throughout, so all implementation tasks use Python
- Hypothesis is already configured in the project (`.hypothesis/` directory exists)
- Test files: `tests/ml/test_judge_service.py` (new), `tests/ml/test_evaluation_models.py` (new), `tests/ml/test_evaluation_runner.py` (updated)
