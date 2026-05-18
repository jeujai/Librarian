# Implementation Plan: Fine-Tuned Model Regression Bugfix

## Overview

This plan implements the two-track fix described in `design.md`. Track A restores model quality by propagating `semantic_type` through training pairs, enforcing a per-type training-data floor in `RAGQAStrategy`, aligning the evaluation prompt with the training format, and lowering adapter capacity via config. Track B restores measurement correctness by making the cached DeepSeek `httpx.AsyncClient` loop-aware and collapsing the two `asyncio.run` calls in `evaluate.py`.

Tasks are ordered so the smallest stateless schema change lands first, then the isolatable measurement fix (Track B), then the training-data rebalance (Track A1), then the prompt-parity fix (Track A2), then the one-line config change (Track A3). Integration tests run before the acceptance gate, which is the actual rebuild + retrain + reevaluate pass that validates Property 1 end-to-end.

Property references match the 6 correctness properties in `design.md`. Requirement references map to clauses in `bugfix.md` (1.x current defect, 2.x expected behavior, 3.x preservation).

## Tasks

- [x] 1. Add `semantic_type` to `PairMetadata` (stateless schema change)

  - [x] 1.1 Add `semantic_type: Optional[str] = None` field to `PairMetadata` in `src/multimodal_librarian/ml/models.py`
    - Use `Field(default=None)` so existing JSONL files deserialize unchanged (missing field → `None`)
    - No change to `strategy`, `source_concepts`, `confidence_score`, `source_document`, or `chunk_ids` (Property 5)
    - _Bug_Condition: the current `PairMetadata` has no per-pair semantic type, so per-type balance (Property 3) cannot be observed on disk_
    - _Expected_Behavior: `PairMetadata(semantic_type="Diagnostic Procedure")` serializes to JSONL and deserializes back identically_
    - _Preservation: JSONL round-trip continues to work for all existing fields; legacy files without `semantic_type` still load_
    - _Requirements: 3.4_

  - [x] 1.2 Unit test — `PairMetadata.semantic_type` round-trip and default
    - Assert `PairMetadata(strategy="rag", semantic_type="Diagnostic Procedure")` serializes and parses back equal
    - Assert a legacy `PairMetadata(strategy="rag")` JSON dict (no `semantic_type` key) loads with `semantic_type is None`
    - Test file: `tests/ml/test_fine_tuned_model_regression_unit.py`
    - _Requirements: 3.4_

  - [x] 1.3 Write property test — `semantic_type` JSONL round-trip
    - **Property 5: Preservation** - JSONL round-trip preserves `semantic_type`
    - Extend `instruction_tuning_pair_strategy` (or add `instruction_tuning_pair_strategy_with_semantic_type`) to populate `metadata.semantic_type` from `st.sampled_from([...five eval types..., None])`
    - Assert `InstructionTuningPair.from_jsonl_line(pair.to_jsonl_line()) == pair` for all generated pairs
    - Test file: `tests/ml/test_fine_tuned_model_regression.py`
    - **Validates: Requirements 3.4**

- [x] 2. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Track B — Judge transport fix (measurement)

  - [x] 3.1 Make `DeepSeekAIService._get_client` loop-aware in `src/multimodal_librarian/services/deepseek_ai_service.py`
    - Add `self._client_loop: Optional[asyncio.AbstractEventLoop] = None` to `__init__`
    - On each call to `_get_client`, compare `asyncio.get_running_loop()` to `self._client_loop`
    - If `self._client is None` OR `self._client_loop` is None OR a different loop OR the tracked loop is closed, close the stale client (suppress exceptions) and construct a fresh `httpx.AsyncClient`
    - Store the new loop in `self._client_loop`
    - No change to `JudgeService.judge_pair` contract or scoring semantics (Property 6)
    - _Bug_Condition: the cached `httpx.AsyncClient` is bound to the first `asyncio.run` loop; reuse across a second `asyncio.run` raises `Event loop is closed`_
    - _Expected_Behavior: for every `asyncio.run` boundary, a fresh client is created and the old one is closed_
    - _Preservation: successful judge calls return identical `AIResponse` content and confidence as before the fix (Property 6)_
    - _Requirements: 1.8, 2.8_

  - [x] 3.2 Collapse the two `asyncio.run` calls in `src/multimodal_librarian/ml/evaluate.py` into one
    - Wrap `judge_service.verify_available()` and `runner.evaluate(...)` inside a single `async def _run()`
    - Replace the separate `asyncio.run(judge_service.verify_available())` (line ~222) and `asyncio.run(runner.evaluate(...))` (line ~261) with one `asyncio.run(_run())`
    - Preserves the structural invariant: exactly one event loop per CLI invocation
    - _Bug_Condition: two `asyncio.run` calls at top-level share a cached client across loops_
    - _Expected_Behavior: exactly one `asyncio.run` in the CLI path_
    - _Preservation: CLI still produces `comparison_report.json` and `comparison_report.md` (clause 3.3)_
    - _Requirements: 1.8, 2.8_

  - [ ]* 3.3 Unit test — loop-aware `_get_client` recreates client across loops
    - Patch `httpx.AsyncClient` constructor with a counter
    - Call `asyncio.run(service.verify_available())` then `asyncio.run(service.generate_response(...))` with a mocked transport
    - Assert the constructor was invoked twice (one client per loop)
    - Test file: `tests/ml/test_fine_tuned_model_regression_unit.py`
    - _Requirements: 1.8, 2.8_

  - [ ]* 3.4 Unit test — single `asyncio.run` in `evaluate.py`
    - Patch `asyncio.run` with a call counter
    - Invoke the CLI main function with stub config, mocked `JudgeService`, mocked `EvaluationRunner`
    - Assert the counter equals 1
    - Test file: `tests/ml/test_fine_tuned_model_regression_unit.py`
    - _Requirements: 2.8_

  - [x] 3.5 Write property test — judge-loop safety
    - **Property 2: Bug Condition** - Judge pipeline completes without transport contamination
    - `@given(num_run_calls=st.integers(min_value=2, max_value=5))`
    - For each value, invoke `asyncio.run(service.generate_response(...))` N times on the same `DeepSeekAIService` instance
    - Mock the httpx transport to raise `RuntimeError("Event loop is closed")` if its bound loop is closed when called
    - Assert no `RuntimeError("Event loop is closed")` propagates and every call returns an `AIResponse`
    - Test file: `tests/ml/test_fine_tuned_model_regression.py`
    - **Validates: Requirements 1.8, 2.8**

- [ ] 4. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Track A1 — Rebalance training data per semantic type in `RAGQAStrategy`

  - [x] 5.1 Propagate `SeedQuestion.semantic_type` to `InstructionTuningPair.metadata` in `src/multimodal_librarian/ml/rag_qa_strategy.py`
    - In `_process_seed`, set `PairMetadata.semantic_type = seed.semantic_type` when building the pair
    - No change to `strategy="rag"`, `confidence_score`, or citation logic (Property 5)
    - _Bug_Condition: seed semantic type is discarded before reaching the JSONL; Property 3 cannot be enforced without it_
    - _Expected_Behavior: every accepted pair on disk carries the originating `semantic_type`_
    - _Preservation: all conversational-training-data invariants unchanged (Property 5)_
    - _Requirements: 2.2, 2.3, 2.4, 2.5, 3.4_

  - [x] 5.2 Add `_compute_type_allocation` helper and wire a per-type floor into `RAGQAStrategy.generate`
    - Replace the implicit `per_type_limit = max(budget // len(active_types), 5)` formula with a `Dict[str, int]` allocation computed once in `generate`
    - Each of the five eval semantic types receives at least `ceil(target_count * per_type_floor)` seeds (default `per_type_floor=0.10`)
    - Sum of allocations equals `target_count` (remainder absorbed by the largest allocation)
    - Respect existing `seed_count = int(target_count * 1.5)` starting multiplier
    - _Bug_Condition: Diagnostic Procedure received 0.8% of training pairs in the regressing run; an unbounded `//` allocation gives no floor_
    - _Expected_Behavior: every target type's seed budget ≥ `target_count * 0.10`_
    - _Preservation: types not in the eval set continue to receive the residual proportional budget_
    - _Requirements: 2.2, 2.3, 2.4, 2.5_

  - [x] 5.3 Implement top-up loop for under-yielding types inside `_process_seed` / `generate`
    - Track per-type `(accepted, allocated)` counts during generation
    - When any target type's accepted count falls below 80% of its allocation after the initial seed pool is exhausted, enqueue additional seeds of that type from Neo4j
    - Cap total seed-growth at 4× the original `target_count` to bound runtime
    - Preserve existing `asyncio.Semaphore(8)` concurrency and partial-save behavior (clause 3.4)
    - _Bug_Condition: LOINC-heavy Diagnostic Procedure concepts disproportionately fail LOINC cleaning and the quality filter, so the floor is not met without top-up_
    - _Expected_Behavior: each target type reaches ≥ 80% of its allocation in accepted pairs_
    - _Preservation: quality filter and token-budget manager still apply; no pair bypasses existing invariants_
    - _Requirements: 2.2, 2.3, 2.4, 2.5_

  - [ ]* 5.4 Unit test — per-type allocation math
    - `RAGQAStrategy._compute_type_allocation(target_count=12000, types=[5 eval types], floor=0.10)` returns allocations summing to 12000
    - Each allocation ≥ `12000 * 0.10 = 1200`
    - Edge case: `target_count=100`, `floor=0.20`, 5 types → each allocation == 20, sum == 100
    - Test file: `tests/ml/test_fine_tuned_model_regression_unit.py`
    - _Requirements: 2.2, 2.3, 2.4, 2.5_

  - [ ]* 5.5 Unit test — top-up trigger for under-yielding types
    - Mock the RAG service to return a refusal for every Diagnostic Procedure seed until 80% threshold is reached
    - Mock Neo4j to return additional Diagnostic Procedure concepts on demand
    - Assert the top-up loop enqueues more seeds from that type until the allocation floor is reached or the 2.5× cap is hit
    - Test file: `tests/ml/test_fine_tuned_model_regression_unit.py`
    - _Requirements: 2.2_

  - [x] 5.6 Write property test — per-type training-data balance floor
    - **Property 3: Preservation** - Per-type training-data balance floor
    - `@given(target_count=st.integers(min_value=500, max_value=3000), type_subset=st.lists(st.sampled_from(EVAL_SEMANTIC_TYPES), min_size=1, max_size=5, unique=True))`
    - Run `RAGQAStrategy.generate` with mocked RAG/Neo4j/LLM that accept most seeds
    - Assert for every selected type, the fraction of accepted pairs whose `metadata.semantic_type == t` is ≥ 10%
    - Test file: `tests/ml/test_fine_tuned_model_regression.py`
    - **Validates: Requirements 2.2, 2.3, 2.4, 2.5**

- [x] 6. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Track A2 — Align evaluation prompt with training format

  - [x] 7.1 Extract shared user-message builder in `src/multimodal_librarian/ml/qlora_trainer.py`
    - Add `build_inference_user_message(instruction: str, context: str) -> str` helper that returns `f"{instruction}\n\nContext:\n{context}"` when `context` is non-empty, else `instruction`
    - Refactor `format_chat_message` so its user-message branch delegates to this helper — single source of truth
    - Export `_SYSTEM_PROMPT` and `build_inference_user_message` for use by `EvaluationRunner` (keep `_SYSTEM_PROMPT` stable — Property 5 / clause 3.5)
    - _Bug_Condition: the training and evaluation prompt formats diverge because the user message is built in two different places_
    - _Expected_Behavior: `format_chat_message(pair)` second message == `build_inference_user_message(pair.instruction, pair.context)` for all pairs_
    - _Preservation: the production `_SYSTEM_PROMPT` string and `format_chat_message` output on existing training pairs are byte-equal to today (clause 3.5)_
    - _Requirements: 3.5, 3.6_

  - [x] 7.2 Use `build_inference_user_message` and `_SYSTEM_PROMPT` in `EvaluationRunner._query_ollama`
    - Import `build_inference_user_message` and `_SYSTEM_PROMPT` from `qlora_trainer`
    - Replace the local `"Answer the following medical question accurately and concisely.\n\nQuestion: {eq.question}"` fallback with `build_inference_user_message(eq.question, eq.context or "")`
    - Pass `_SYSTEM_PROMPT` as the Ollama system message so both training and eval share the same system prompt (clause 3.5)
    - Accept `system_prompt` and `user_message` as parameters on `_query_ollama` so callers cannot diverge
    - _Bug_Condition: eval prompt used a different user-message structure when `eq.context` was empty, taking the fine-tuned model out of distribution (H2, H5)_
    - _Expected_Behavior: eval user message is byte-equal to what training built for the same `(instruction, context)`_
    - _Preservation: Ollama inference contract unchanged; no change to response-parsing logic in `EvaluationRunner`_
    - _Requirements: 3.5, 3.6_

  - [x] 7.3 Populate `EvaluationQuestion.context` from RAG sources in `generate_eval_set`
    - Wire the existing `_extract_context` helper output into the persisted `EvaluationQuestion`
    - Ensure `eval_set.jsonl` has non-empty `context` whenever RAG returned sources (the code path exists but the prior eval set persisted `context=""`)
    - _Bug_Condition: the regressing eval set had `context=""` for all 50 questions, causing H2 to manifest_
    - _Expected_Behavior: rerun `generate_eval_set` and `eval_set.jsonl` has populated `context` fields_
    - _Preservation: eval set schema and question IDs unchanged; existing tests of `EvaluationQuestion` pass_
    - _Requirements: 3.5, 3.6_

  - [ ]* 7.4 Unit test — `build_inference_user_message` parity helper
    - Assert `build_inference_user_message("q", "ctx") == "q\n\nContext:\nctx"`
    - Assert `build_inference_user_message("q", "") == "q"`
    - Assert `format_chat_message(pair)["messages"][1]["content"] == build_inference_user_message(pair.instruction, pair.context)` for several `InstructionTuningPair` fixtures
    - Test file: `tests/ml/test_fine_tuned_model_regression_unit.py`
    - _Requirements: 3.5, 3.6_

  - [x] 7.5 Write property test — training/evaluation prompt parity
    - **Property 4: Preservation** - Training/evaluation prompt parity
    - `@given(instruction_tuning_pair_strategy())` from the existing test suite
    - Compute `training_user_msg = format_chat_message(pair)["messages"][1]["content"]`
    - Compute `eval_user_msg = build_inference_user_message(pair.instruction, pair.context)` (the code path `EvaluationRunner._query_ollama` now uses)
    - Assert `training_user_msg == eval_user_msg`
    - Also assert both paths use the same `_SYSTEM_PROMPT` constant
    - Test file: `tests/ml/test_fine_tuned_model_regression.py`
    - **Validates: Requirements 3.5, 3.6**

- [x] 8. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Track A3 — Constrain adapter capacity (config-only)

  - [x] 9.1 Update `pipeline_config.json` for the next training run
    - Set `epochs=2` (down from 3)
    - Set `lora_rank=16` (down from 32)
    - Set `num_layers=16` (down from 32 — LoRA adapts only the upper half of the transformer, preserving base-model fluency in the lower half)
    - Keep `lora_dropout=0.05`, `lora_alpha=32`, `learning_rate=2e-5`, `batch_size=1`, `grad_accumulation=16`, `max_seq_length=5000`, `distill=true`, `mask_prompt=true`
    - No code change to `qlora_trainer.py` or `TrainingConfig` — hyperparameter tweaks are expressed as config only
    - _Bug_Condition: distilled-mode training with rank 32, 32 layers, and 3 epochs on ~11.5k pairs damaged Coherence by -0.82 (H3)_
    - _Expected_Behavior: Coherence delta ≥ -0.2 versus base model on the rebuilt adapter (clause 2.6)_
    - _Preservation: `TrainingConfig` schema unchanged; adapter/export output paths unchanged (clause 3.2)_
    - _Requirements: 2.6, 2.7_

- [ ] 10. Integration tests — full pipeline validation

  - [ ]* 10.1 Integration test — full rebuild smoke test
    - Run `RAGQAStrategy.generate(target_count=500, semantic_types=[5 eval types])` with mocked RAG/Neo4j/LLM that accept most seeds
    - Assert per-type accepted-pair fraction ≥ 10% for each of the five target types
    - Assert every accepted pair round-trips through JSONL
    - Assert refusal percentage stays in the 15–30% band (clause 3.4)
    - Test file: `tests/ml/test_fine_tuned_model_regression_integration.py`
    - _Requirements: 2.2, 2.3, 2.4, 2.5, 3.4_

  - [ ]* 10.2 Integration test — end-to-end prompt parity
    - Run `EvaluationRunner.evaluate` against a small eval set (3 questions with non-empty `context`) with mocked Ollama that echoes the received user message back
    - Capture the user message Ollama saw and compare it to `format_chat_message` output for the same `(instruction, context)`
    - Assert byte-equal
    - Test file: `tests/ml/test_fine_tuned_model_regression_integration.py`
    - _Requirements: 3.5, 3.6_

  - [ ]* 10.3 Integration test — two-loop judge (transport fix)
    - Boot `evaluate.py`'s main path against a mocked DeepSeek endpoint whose transport raises `RuntimeError("Event loop is closed")` if a client is reused across loops
    - Assert the process completes with an exit code of 0 and no `Event loop is closed` lines in the captured log
    - Assert every eval question received a `ResponseScore` (none skipped)
    - Test file: `tests/ml/test_fine_tuned_model_regression_integration.py`
    - _Requirements: 1.8, 2.8_

  - [ ]* 10.4 Re-run existing `conversational-training-data` property tests on the rebuilt pipeline
    - Execute `pytest tests/ml/test_conversational_training_data.py tests/ml/test_conversational_training_data_unit.py tests/ml/test_conversational_training_data_integration.py`
    - Assert all 12 invariant properties still hold against the rebuilt pipeline (Property 5)
    - _Requirements: 3.4_

- [x] 11. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 12. Acceptance gate — Rebuild, retrain, reevaluate

  > **Note**: Steps 12.1–12.3 require the user to execute training and evaluation on a real GPU. Mark each step complete only after the corresponding artifacts are produced under `training_runs/<new_timestamp>/`.

  - [ ] 12.1 Rebuild `training_data.jsonl` with the rebalanced pipeline
    - Invoke the training-data generation CLI with the five eval semantic types and `per_type_floor=0.10`
    - Verify each target type's accepted-pair fraction is ≥ 10% in the generated JSONL
    - Verify overall refusal percentage is within the 15–30% band
    - Verify every pair carries `metadata.semantic_type` (no `None` for the five target types)
    - _Requirements: 2.2, 2.3, 2.4, 2.5, 3.4_

  - [ ] 12.2 Regenerate `eval_set.jsonl` with populated `context`
    - Run `generate_eval_set` against the updated knowledge base
    - Verify every `EvaluationQuestion.context` is non-empty when RAG returned sources
    - _Requirements: 3.5, 3.6_

  - [ ] 12.3 Retrain QLoRA adapter with the updated `pipeline_config.json`
    - Run `QLoRATrainer` against the rebuilt `training_data.jsonl`
    - Produce adapter and exported model under a new `training_runs/<timestamp>/adapters` and `training_runs/<timestamp>/exported_model` (clause 3.2)
    - _Requirements: 3.2_

  - [ ] 12.4 Reevaluate against base model on the 50-question eval set
    - Run the patched `evaluate.py` CLI (single `asyncio.run`, aligned prompt, loop-aware DeepSeek client)
    - Produce `comparison_report.json` and `comparison_report.md` under `training_runs/<timestamp>/evaluation/` (clause 3.3)
    - _Requirements: 3.3, 3.5, 3.6_

  - [ ] 12.5 Acceptance — Verify Property 1 thresholds on the rebuilt report
    - **Property 1: Expected Behavior** - Rebuilt fine-tuned model achieves net-positive quality with no catastrophic per-type regression
    - Assert aggregate `win_rate > 0.5` and `mean_score_delta >= +0.05`
    - Assert per-type `win_rate >= 0.4` and `score_delta >= -0.1` for Diagnostic Procedure, Sign or Symptom, Disease or Syndrome, Therapeutic or Preventive Procedure
    - Assert Pharmacologic Substance `win_rate >= 0.5` with non-negative score delta (Property 5 preservation, clause 3.1)
    - Assert Coherence, Factual Accuracy, Completeness, and Clinical Relevance deltas are all `>= -0.2`
    - Assert 0 `Event loop is closed` warnings in the run log (Property 2)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 3.1_

  - [ ]* 12.6 Replay judge scores on previously-scored questions (Property 6)
    - **Property 6: Preservation** - Judge transport fix does not change judge verdicts on already-working questions
    - Replay `(question, base_response, finetuned_response)` triples from the prior `training_runs/2026-05-06_234338/evaluation/comparison_report.json` through the patched `JudgeService` at temperature 0.1
    - Assert each replayed score differs from the original by at most ±1 point (the score-clamp noise band for `[1,5]`)
    - _Requirements: 3.7_

- [ ] 13. Final checkpoint — All tests pass and acceptance gate met
  - Ensure all unit, property, and integration tests pass
  - Ensure Property 1 thresholds are met on the rebuilt model (task 12.5)
  - Ensure no `Event loop is closed` warnings appear in the evaluation run log
  - Ask the user if questions arise

## Notes

- Tasks marked with `*` are optional and may be deferred for a faster MVP
- Each task references specific bugfix-requirement clauses (1.x current defect, 2.x expected behavior, 3.x preservation) for traceability
- Property references use the 6 correctness properties from `design.md` (Properties 1–6)
- Property tests use `@settings(max_examples=100)` consistent with the existing `tests/ml/` suite
- New tests go under `tests/ml/test_fine_tuned_model_regression.py` (property), `tests/ml/test_fine_tuned_model_regression_unit.py` (unit), and `tests/ml/test_fine_tuned_model_regression_integration.py` (integration)
- All code changes respect the DI patterns in `.kiro/steering/dependency-injection.md`: no module-level instantiation, lazy init, graceful degradation, singleton caching, and proper cleanup
- Track A3 is config-only; do not modify `TrainingConfig` schema or `qlora_trainer.py`
- The Track B fix (tasks 3.1 and 3.2) is defence-in-depth: either change alone would prevent the `Event loop is closed` warning, and both together guarantee it cannot regress
