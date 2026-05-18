# Fine-Tuned Model Regression Bugfix Design

## Overview

The fine-tuned Llama 3.1 8B QLoRA model at `training_runs/2026-05-06_234338/adapters` underperforms the base model on the 50-question LLM judge evaluation with win rate 0.28, mean score delta -0.4550, catastrophic per-type regressions on Diagnostic Procedure (0%) and Sign or Symptom (10%), a -0.82 Coherence drop, and intermittent `DeepSeek generation failed: Event loop is closed` warnings. The sole net-positive semantic type is Pharmacologic Substance (60% win rate, +0.10 delta).

This design is a careful root-cause diagnostic, not a shotgun rebuild. I investigated six hypotheses using concrete evidence from `training_runs/2026-05-05_145518/training_data.jsonl` (11,481 pairs), the pipeline configs, the evaluation harness code, and the DeepSeek client. Three hypotheses are **confirmed** and drive targeted fixes; two are **ruled out**; one is **partially confirmed** as a parallel measurement concern.

The fix has two parallel tracks:

- **Track A (model quality)**: Rebalance training data per semantic type and align the evaluation prompt format with training so the model is not evaluated out of distribution. This directly targets the Diagnostic Procedure, Sign or Symptom, and Coherence regressions.
- **Track B (measurement)**: Recreate the DeepSeek `httpx.AsyncClient` per `asyncio.run` boundary so cached transport is never shared across event loops. This is a narrow correctness fix to the judge pipeline, kept separate from Track A so the two concerns do not get conflated.

The invariants established by the `conversational-training-data` spec (LOINC cleaning, LLM rewriting, quality filters, token budget, refusal training, JSONL round-trip, production system prompt) must remain intact. The fixes are expressed as config changes and small, localised code changes that slot into existing DI patterns.

## Glossary

- **Bug_Condition (C)**: The condition under which the defect manifests — a specific combination of training data composition, training/inference prompt format, and judge transport that produces the observed regression.
- **Property (P)**: The desired behavior after the fix — win rate >0.5, mean score delta ≥ +0.05, no catastrophic per-type regression, Coherence within 0.2 of base, and no `Event loop is closed` contamination.
- **Preservation**: Pharmacologic Substance wins, the existing training/evaluation artifact layout, and all invariants from the `conversational-training-data` spec must remain unchanged.
- **Training_Data_Generator**: `RAGQAStrategy` in `src/multimodal_librarian/ml/rag_qa_strategy.py`. Produces per-semantic-type seed questions, runs them through RAG, and writes `training_data.jsonl`.
- **EvaluationRunner**: `EvaluationRunner` in `srxc/multimodal_librarian/ml/evaluation_runner.py`. Generates eval questions, runs Ollama inference, calls `JudgeService.judge_pair`.
- **JudgeService**: `JudgeService` in `src/multimodal_librarian/ml/judge_service.py`. Wraps `DeepSeekAIService` to score pairs.
- **DeepSeekAIService**: `DeepSeekAIService` in `src/multimodal_librarian/services/deepseek_ai_service.py`. Holds a cached `httpx.AsyncClient` in `self._client` across all calls.
- **Per-Type Balance**: The approximate fraction of training pairs mapped to each UMLS semantic type targeted by the eval set.
- **Training/Eval Prompt Parity**: The property that the user message seen at inference time (Ollama via `EvaluationRunner._query_ollama`) has the same structure (`instruction + "\n\nContext:\n" + context`) as the training pair produced by `format_chat_message` in `qlora_trainer.py`.

## Bug Details

### Bug Condition

The regression manifests when *all* of the following coincide on an evaluation question:
1. The question's semantic type is under-represented in `training_data.jsonl` (in particular Diagnostic Procedure, Sign or Symptom, Disease or Syndrome).
2. The evaluation harness feeds the fine-tuned model a prompt whose format diverges from the training prompt (in this run: the eval set has `context=""` for all 50 questions, but every training pair had a non-empty context concatenated into the user message).
3. The adapter was produced with `distill=true` for 3 epochs on an ~11k-pair dataset with `lora_rank=32`, `lora_alpha=32`, and `num_layers=32` (all transformer layers), which is enough capacity to overwrite base-model fluency when training responses have citation markers stripped.

An orthogonal bug condition (measurement):
4. `src/multimodal_librarian/ml/evaluate.py` calls `asyncio.run(judge_service.verify_available())` (line 222) and then a second `asyncio.run(runner.evaluate(...))` (line 261). `DeepSeekAIService._client: Optional[httpx.AsyncClient]` is cached on first use and is tied to the *first* event loop. When the second `asyncio.run` starts a new loop, the cached client's transport pool raises `Event loop is closed` on first use and only recovers on retry.

**Formal Specification:**

```
FUNCTION isBugCondition(input)
  INPUT: input of type EvaluationSample
         (semantic_type, eval_prompt, training_run_id, judge_transport_state)
  OUTPUT: boolean

  training_imbalanced := per_type_fraction(
      training_data_jsonl,
      input.semantic_type
  ) < balance_floor        // e.g. < 0.10
  prompt_mismatched    := training_context_non_empty(training_data_jsonl)
                           AND eval_context_empty(input.eval_prompt)
  overtrained_adapter  := distill == TRUE
                           AND epochs >= 3
                           AND lora_rank >= 32
                           AND num_layers == total_layers
                           AND dataset_size < 15000
  judge_loop_shared    := uses_cached_httpx_across_asyncio_runs()

  RETURN (training_imbalanced OR prompt_mismatched OR overtrained_adapter)
         OR judge_loop_shared
END FUNCTION
```

### Evidence and Examples

I ran a heuristic classifier over `training_runs/2026-05-05_145518/training_data.jsonl` (11,481 pairs) that maps each instruction to a semantic type based on the conversational rewrite phrase stems.

| Semantic Type | Pairs Inferred | % of Total | Eval Win Rate | Eval Score Delta |
|---|---:|---:|---:|---:|
| Pharmacologic Substance | 1,603 | 14.0% | 0.60 | +0.10 |
| Sign or Symptom | 918 | 8.0% | 0.10 | −1.05 |
| Therapeutic or Preventive Procedure | 778 | 6.8% | 0.40 | −0.18 |
| Disease or Syndrome | 536 | 4.7% | 0.30 | −0.43 |
| Diagnostic Procedure | 92 | 0.8% | **0.00** | **−0.725** |
| UNKNOWN (unclassified) | 7,554 | 65.8% | — | — |

Per-type training counts are strongly rank-correlated with eval win rate. Diagnostic Procedure has **~17× less training data** than Pharmacologic Substance, which matches its collapse to 0% win rate.

Secondary evidence:
- Training context field is populated for all 13,262 distilled pairs (mean context ≈10,314 chars). Eval set `context` field is empty for all 50 questions. The eval harness at `EvaluationRunner.evaluate` builds the Ollama prompt as `"Answer the following medical question accurately and concisely.\n\nQuestion: {question}"` when `eq.context` is empty — a completely different user-message structure than training.
- Training config used `distill=true`, `epochs=3`, `lora_rank=32`, `lora_alpha=32`, `num_layers=32`, `lora_dropout=0.05`, `learning_rate=2e-5`. Distilled responses have 0 citations on average (citation markers are stripped by `_clean_response_for_distillation`), shorter median length (1,379 chars vs 2,059), and no RAG preamble — this trains the model away from base-model-style prose toward a specific distilled "voice", which explains the -0.82 Coherence drop.
- `evaluate.py` lines 222 and 261 call `asyncio.run` twice; `DeepSeekAIService._client` is cached across both.

Concrete per-question examples from `comparison_report.md`:
- Q41 (Diagnostic Procedure): *"What can Blood Gas Monitoring, Transcutaneous tell us clinically?"* → base 3.25, fine-tuned 1.75. Diagnostic Procedure has 0.8% training coverage; Coherence score for the fine-tuned response is well below the base.
- Q35 (Sign or Symptom): *"How would a doctor evaluate Cramp in quadriceps muscle?"* → base 3.75, fine-tuned 2.25. Sign or Symptom has 8% training coverage; evaluation prompt has no RAG context so the fine-tuned model is out-of-distribution.
- Q5 (Pharmacologic Substance): *"What is cycloSPORINE typically prescribed for?"* → base wins 4.00 vs 2.75. Even on the best-represented type, LOINC-style concept names remain hard despite `LOINCCleaner` cleaning the surface form, because the underlying concept was never rephrased.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Pharmacologic Substance win rate must stay ≥ 0.5 with non-negative score delta (clause 3.1 in bugfix.md).
- QLoRA training via `QLoRATrainer` produces adapters under `training_runs/<ts>/adapters` and exports under `training_runs/<ts>/exported_model` (clause 3.2).
- `EvaluationRunner.evaluate` produces `comparison_report.json` and `comparison_report.md` with per-question, per-dimension, and per-semantic-type aggregates (clause 3.3).
- All `conversational-training-data` invariants remain enforced: MCQ rejection, LOINC rejection, uncited-long rejection, refusal minimum-length exemption, token budget, JSONL round-trip, refusal percentage logging (clause 3.4).
- The production system prompt in `qlora_trainer.py` is used by both training pair formatting and evaluation inference (clause 3.5).
- Any evaluation question the fine-tuned model already won or tied at or above base must continue to do so (clauses 3.6 and 3.7).

**Scope:**
All inputs where the bug condition does not hold — questions in semantic types already well-represented, evaluation runs that do not trigger the cached-client reuse, and all existing tests in `tests/ml/test_conversational_training_data*.py`, `tests/ml/test_qlora_trainer.py`, `tests/ml/test_evaluation_runner.py`, `tests/ml/test_judge_service.py` — should be completely unaffected. No change to `InstructionTuningPair` schema, `PairMetadata` schema, `TrainingConfig` schema, or JSONL on-disk format.

## Hypothesized Root Cause

Each hypothesis is mapped to evidence and classified as **confirmed**, **ruled out**, or **partially confirmed**.

### 1. Training data per-semantic-type coverage gap — **Confirmed (primary)**

The evaluation hits 10 questions per semantic type, but the training data is dominated by Pharmacologic Substance (1,603 pairs) while Diagnostic Procedure has only 92 pairs (0.8%). The per-type training count rank-correlates with per-type eval win rate: most-represented type wins most, least-represented type collapses to 0%. The `conversational-training-data` LLM rewriter preserves or reduces coverage on types where UMLS concept names are hardest (LOINC-heavy Diagnostic Procedure names like `MG.stereotactic`, `Multisection perfusion^W`, `RF`). Target budget allocation in `_generate_umls_concept_seeds` is `per_type_limit = max(budget // len(active_types), 5)`, but the _actual_ per-type yield after quality filtering, refusal filtering, LOINC cleaning, and rewriter dropout is skewed because Diagnostic Procedure concepts are disproportionately filtered out (LOINC-coded terms, empty after cleaning, low-citation RAG responses).

### 2. Training/inference prompt mismatch — **Confirmed**

`format_chat_message` in `qlora_trainer.py` builds the user message as `f"{pair.instruction}\n\nContext:\n{pair.context}"` when context is present (which it is for all 13,262 distilled training pairs). `EvaluationRunner.evaluate` falls back to `f"Answer the following medical question accurately and concisely.\n\nQuestion: {eq.question}"` when `eq.context` is empty, and eval_set.jsonl has `context=""` for all 50 questions. The fine-tuned model is evaluated on a prompt that never appeared during training, and the Coherence dimension is particularly sensitive to that distribution shift. This also explains why the regression is dimension-wide (all four dimensions are negative) rather than just factual.

### 3. QLoRA overfitting damaging Coherence — **Confirmed (contributes to Coherence specifically)**

Training config used `lora_rank=32`, `lora_alpha=32` (scale 1.0), `num_layers=32` (every transformer layer), `lora_dropout=0.05`, `epochs=3`, `distill=true`. With ~11.5k training examples, 3 epochs of distilled-mode training — which strips `[Source N]` markers and RAG preambles, pushing mean citations in the training target from ~7 to 0 — overwrites the base model's fluent explanatory voice with a compressed style. The -0.82 Coherence drop is the single largest dimension regression. The prior run in `training_runs/2026-05-05_145518/pipeline_config.json` used `epochs=2, lora_dropout=0.0`, so the bump to `epochs=3` on the new run likely amplified the problem.

### 4. Refusal overtraining — **Ruled out as primary driver**

Total refusal fraction in the training data is 24.8%, within the `conversational-training-data` spec's 15-30% band. Per-type refusal rates (Diagnostic Procedure 5.4%, Sign or Symptom 1.6%, Disease or Syndrome 8.6%) are all *below* the global average — not above. This hypothesis does not explain why Diagnostic Procedure regresses most. Keeping it ruled out so we do not waste effort adjusting refusal balance.

### 5. Context field mismatch at inference — **Confirmed (same root as H2)**

Covered by H2. The training data has `context` populated for every pair (avg ~10k chars); the eval set has `context=""` for every question. The harness then uses a completely different prompt template. This is the same bug as H2 viewed from the eval side.

### 6. Judge `Event loop is closed` contaminating measurement — **Partially confirmed**

`evaluate.py` has two top-level `asyncio.run` calls (lines 222 and 261). `DeepSeekAIService._client` is a lazily created `httpx.AsyncClient` cached on the instance. When the first `asyncio.run` (pre-flight `verify_available`) creates the client, the client's transport pool is attached to that loop. The second `asyncio.run` (the evaluation loop) starts a new loop; on first use of the cached client the httpx transport raises `Event loop is closed`. The `JudgeService.judge_pair` retry logic does eventually succeed on subsequent attempts because the error path in `DeepSeekAIService.generate_response` eventually results in a fresh client being created (or the error surfaces as an `AIResponse` with `confidence_score == 0.0` that triggers a `JudgeParseError` retry). All 50 eval pairs produced scores in this run, so the bug did not suppress any question, but the retry window adds latency and the warning signals that judge calls are being retried in a degraded state. Classify as a correctness defect in the measurement infrastructure that must be fixed in parallel, but it is not the primary driver of the -0.4550 score delta.

## Correctness Properties

Property 1: Bug Condition — Rebuilt fine-tuned model achieves net-positive quality with no catastrophic per-type regression

_For any_ rebuild where the fix is applied (training data rebalanced per semantic type, eval prompt aligned with training format, QLoRA hyperparameters tuned to prevent Coherence damage), the rebuilt fine-tuned model SHALL achieve an aggregate win rate > 0.5, mean score delta ≥ +0.05, per-type win rate ≥ 0.4 for each of Diagnostic Procedure / Sign or Symptom / Disease or Syndrome / Therapeutic or Preventive Procedure with score delta no worse than −0.1, per-type win rate ≥ 0.5 for Pharmacologic Substance with non-negative delta, and per-dimension Coherence/Factual Accuracy/Completeness/Clinical Relevance no lower than base minus 0.2 on the same 50-question evaluation set.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 3.1**

Property 2: Bug Condition — Judge pipeline completes without transport contamination

_For any_ evaluation run, the judge pipeline SHALL produce a scored `ResponseScore` for every question without any `Event loop is closed` warning in the process output, by ensuring the `DeepSeekAIService.AsyncClient` is never reused across `asyncio.run` boundaries.

**Validates: Requirements 2.8**

Property 3: Preservation — Per-type training-data balance floor

_For any_ training data file produced by the rebuilt `RAGQAStrategy.generate` with the five target semantic types requested (`Pharmacologic Substance`, `Disease or Syndrome`, `Therapeutic or Preventive Procedure`, `Sign or Symptom`, `Diagnostic Procedure`), the fraction of accepted instruction-tuning pairs whose `metadata.semantic_type` equals any target type SHALL be at least a configured per-type floor (default 10% per target type, summing to ≥ 50% of the total), so that no single evaluation type is starved.

**Validates: Requirements 2.2, 2.3, 2.4, 2.5**

Property 4: Preservation — Training/evaluation prompt parity

_For any_ `InstructionTuningPair` produced by the training pipeline, the user message built by `format_chat_message(pair)` SHALL equal the user message built by the evaluation harness when the same pair is replayed against the fine-tuned model via Ollama. Specifically, both SHALL follow the format `"{instruction}\n\nContext:\n{context}"` when context is non-empty, and the same system prompt constant SHALL be prepended in both the training chat template and the evaluation Ollama system prompt.

**Validates: Requirements 3.5, 3.6**

Property 5: Preservation — Conversational-training-data invariants unchanged

_For any_ training pair produced by the rebuilt pipeline, all of the following SHALL hold, as defined in the `conversational-training-data` spec: no MCQ markers (3+), no uncleaned LOINC in instruction, no uncited responses over 800 tokens, refusal-length-exempt for refusals, within token budget, JSONL round-trip preserving the pair, production system prompt used. The per-run overall refusal percentage SHALL be logged and SHALL warn if outside the 15-30% band.

**Validates: Requirements 3.4, 3.5**

Property 6: Preservation — Judge transport fix does not change judge verdicts on already-working questions

_For any_ question in the current `training_runs/2026-05-06_234338` evaluation run that received a judge verdict (i.e., was not skipped), the rebuilt judge pipeline SHALL produce scores for that same `(question, base_response, finetuned_response)` tuple that are statistically indistinguishable from the original on a held-out replay (within sampling noise at temperature 0.1) — the fix only removes transport failures, it does not change scoring semantics.

**Validates: Requirements 3.7**

## Fix Implementation

The fix has two parallel tracks. All code changes respect the DI patterns in `.kiro/steering/dependency-injection.md`: no module-level instantiation, dependencies passed through constructors, cached services re-created at lifecycle boundaries, and no import-time side effects.

### Track A — Model Quality

#### A1. Rebalance training data per semantic type

**File**: `src/multimodal_librarian/ml/rag_qa_strategy.py`

**Class**: `RAGQAStrategy`

**Specific Changes**:

1. **Add per-type floor enforcement in `generate`**. Replace the implicit `per_type_limit = max(budget // len(active_types), 5)` formula in `_generate_umls_concept_seeds` with a configurable `type_allocation` dict (computed once in `generate`) that reserves a minimum budget per target type. Stratify based on the `semantic_types` argument already plumbed through `generate_seed_questions` so the five eval types each receive at least `ceil(target_count * per_type_floor)` seeds (default floor 0.10).
   - *Rationale*: The 92-pair Diagnostic Procedure bucket is the primary cause of the 0% win rate. With `target_count=12000` and a 0.10 floor, Diagnostic Procedure will have ≥ 1,200 seeds before rewriter dropout and quality filter losses.

2. **Raise the seed multiplier for under-yielding types**. Track per-type yield through `_process_seed` (pairs accepted vs seeds consumed) and top up any type that falls below 80% of its allocation by queueing more seeds from that type. Preserve the existing `seed_count = int(target_count * 1.5)` starting point but allow it to grow up to 2.5× for stubborn types.
   - *Rationale*: Diagnostic Procedure concepts are disproportionately dropped by `LOINCCleaner.clean_concept_name` (LOINC-coded names become empty) and by the quality filter (uncited RAG responses). A top-up loop guarantees the floor is met without changing the quality bar.

3. **Extend `SeedQuestion.semantic_type` propagation to `InstructionTuningPair.metadata`**. Add `semantic_type: Optional[str]` to `PairMetadata` (default `None` for backward compatibility) and populate it in `_process_seed` from the seed's `semantic_type`.
   - *Rationale*: Without per-pair semantic type on disk, we cannot later compute per-type balance in observability or enforce Property 3. Today the information is lost between `SeedQuestion` and `InstructionTuningPair`.

**File**: `src/multimodal_librarian/ml/models.py`

4. **Add `semantic_type: Optional[str] = None` field to `PairMetadata`**. Pydantic field with a default; existing JSONL files load unchanged (missing field is `None`). No schema-breaking change.

#### A2. Align evaluation prompt with training format

**File**: `src/multimodal_librarian/ml/evaluation_runner.py`

**Function**: `EvaluationRunner.evaluate` and `_query_ollama`

**Specific Changes**:

1. **Populate `context` on eval questions by default**. `generate_eval_set` already calls RAG and has access to `rag_response.sources` (see existing `_extract_context` helper at line ~180 which builds `"[Source i] {content}"` concatenation). Ensure `EvaluationQuestion.context` is always populated when RAG returns sources, and persist to `eval_set.jsonl`. The current eval_set file has `context=""` because eval set was regenerated elsewhere — the code path exists but the output file is empty.

2. **Use `format_chat_message` in `_query_ollama`**. Refactor the Ollama prompt construction to import `format_chat_message` and `_SYSTEM_PROMPT` from `qlora_trainer` so training and evaluation are driven by a single source of truth. Replace the current ad-hoc prompt construction (lines ~480 in `evaluate`):
   ```python
   # BEFORE
   if eq.context and eq.context.strip():
       prompt = f"{eq.question}\n\nContext:\n{eq.context}"
   else:
       prompt = f"Answer the following medical question accurately and concisely.\n\nQuestion: {eq.question}"
   ```
   with:
   ```python
   # AFTER: build the same user message the training pipeline built,
   # then prepend the same system prompt.
   from .qlora_trainer import format_chat_message, _SYSTEM_PROMPT
   pair = InstructionTuningPair(
       instruction=eq.question,
       context=eq.context or "",
       response="",  # not used for inference
       metadata=PairMetadata(strategy="eval"),
   )
   chat = format_chat_message(pair, distill=False)
   user_msg = chat["messages"][1]["content"]
   system_msg = _SYSTEM_PROMPT
   ```
   and pass `system_msg` + `user_msg` to `_query_ollama` (which already prepends a system prompt). Drop the local `system_prompt` constant in `_query_ollama` and accept both parts as parameters so there is no divergence.

#### A3. Constrain adapter capacity to preserve Coherence

**File**: `training_runs/<new_timestamp>/pipeline_config.json` (runtime config only — no code change)

**Specific Changes**:

1. **Lower `epochs` from 3 to 2** and keep `lora_dropout=0.05`. Matches the earlier successful `2026-05-05_145518` shape but with dropout added.
2. **Lower `lora_rank` from 32 to 16**, keep `lora_alpha=32` (scale becomes 2.0, which is a common balanced configuration).
3. **Lower `num_layers` from 32 to 16** so LoRA adapts only the upper half of the transformer. The lower half retains base-model fluency, which is the biggest lever for restoring the -0.82 Coherence dimension.
4. **Keep `learning_rate=2e-5`, `batch_size=1`, `grad_accumulation=16`, `max_seq_length=5000`, `distill=true`, `mask_prompt=true`**.

These are **config-file-only** changes. No code change in `qlora_trainer.py` or `TrainingConfig`. This respects the constraint that hyperparameter tweaks should be expressed as config, not new code.

### Track B — Measurement Fix

#### B1. Recreate DeepSeek `httpx.AsyncClient` per `asyncio.run` boundary

**File**: `src/multimodal_librarian/services/deepseek_ai_service.py`

**Class**: `DeepSeekAIService`

**Specific Changes**:

1. **Bind the cached client to the running event loop**. Change `_get_client` to track the loop that created the client and recreate if the loop has changed or closed:
   ```python
   async def _get_client(self) -> httpx.AsyncClient:
       import asyncio
       current_loop = asyncio.get_running_loop()
       if (
           self._client is None
           or self._client_loop is None
           or self._client_loop is not current_loop
           or self._client_loop.is_closed()
       ):
           # Close stale client if the loop it was bound to is gone.
           if self._client is not None:
               try:
                   await self._client.aclose()
               except Exception:
                   pass
           self._client = httpx.AsyncClient(...)
           self._client_loop = current_loop
       return self._client
   ```
2. **Add `self._client_loop: Optional[asyncio.AbstractEventLoop] = None`** to `__init__`.

**File**: `src/multimodal_librarian/ml/evaluate.py`

3. **Collapse the two `asyncio.run` calls into one**. Replace lines 222 and 261 with a single `asyncio.run` that awaits both `verify_available` and `runner.evaluate` in the same loop:
   ```python
   async def _run() -> ComparisonReport:
       await judge_service.verify_available()
       return await runner.evaluate(
           eval_set_path=eval_set_path,
           base_model=config.base_model,
           finetuned_model=config.finetuned_model,
           progress_callback=_progress_callback,
       )
   report = asyncio.run(_run())
   ```
   This is the cleaner structural fix; change (1) is defence in depth for any caller that still uses two `asyncio.run` calls (e.g., in tests).

Both changes together guarantee the cached `httpx.AsyncClient` is never reused across event loops. Neither changes the `JudgeService.judge_pair` contract or scoring semantics, preserving Property 6.

## Testing Strategy

### Validation Approach

Two-phase: first surface counterexamples on the *current* (unfixed) pipeline to confirm the root causes, then verify the fix works and preserves invariants.

### Exploratory Bug Condition Checking

**Goal**: Confirm the three confirmed root causes with failing tests on the unfixed code. If a test unexpectedly passes, re-examine the hypothesis.

**Test Plan**: Write targeted unit tests that reproduce each confirmed bug condition against fixtures derived from `training_runs/2026-05-05_145518/training_data.jsonl` and `eval_set.jsonl`.

**Test Cases**:
1. **Per-type balance test** (H1): Load `training_data.jsonl`, map each instruction to inferred semantic type using the same heuristics used in the evidence scan, assert that each of the five eval types has < 10% coverage → passes on unfixed data (Diagnostic Procedure 0.8%), fails after rebalance.
2. **Training/eval prompt mismatch test** (H2): Build a training pair with non-empty context via `format_chat_message`, build the Ollama prompt for the same question via the current `EvaluationRunner` code path with `context=""`, assert user-message equality → fails on unfixed code (the two differ structurally).
3. **Coherence-damaging capacity test** (H3): This one cannot be unit-tested cheaply because it requires a training run. Instead, assert the `pipeline_config.json` values against a ceiling (e.g. `epochs <= 2`, `lora_rank <= 16`, `num_layers <= 16` when `distill=true` and `dataset_size < 15000`) → fails on unfixed config.
4. **Event loop closed reproduction** (H6): Create a `DeepSeekAIService`, call `asyncio.run(service.verify_available())`, then call `asyncio.run(service.generate_response(...))` with a mocked httpx transport that raises `RuntimeError("Event loop is closed")` when used on a different loop → fails on unfixed code; passes once `_get_client` is loop-aware.

**Expected Counterexamples**:
- Per-type coverage for Diagnostic Procedure = 0.8% (≪ 10%).
- User messages built by `format_chat_message` vs `EvaluationRunner._query_ollama` differ by a full `"Answer the following medical question accurately and concisely.\n\nQuestion: "` prefix when eval context is empty.
- `pipeline_config.json` has `epochs=3`, `lora_rank=32`, `num_layers=32`.
- `asyncio.run` reuse across calls triggers `Event loop is closed`.

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed pipeline produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  // Track A: rebuild, reevaluate
  rebuilt_pair_dataset := rebuildTrainingData(input.semantic_type)
  rebuilt_adapter      := retrainQLoRA(rebuilt_pair_dataset, fixed_config)
  rebuilt_report       := evaluateWithAlignedPrompt(rebuilt_adapter)
  ASSERT rebuilt_report.win_rate > 0.5
  ASSERT rebuilt_report.by_semantic_type[input.semantic_type].win_rate >= 0.4
  ASSERT rebuilt_report.per_dim.coherence_delta >= -0.2

  // Track B: judge transport
  run1 := asyncio.run(verify_available_only())
  run2 := asyncio.run(evaluate_many())
  ASSERT no `Event loop is closed` warning emitted
  ASSERT every question received a ResponseScore (no skipped)
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the rebuilt pipeline produces the same result as the original.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  // Preservation: Pharmacologic Substance wins
  ASSERT rebuilt_report.by_semantic_type["Pharmacologic Substance"].win_rate >= 0.5
  ASSERT rebuilt_report.by_semantic_type["Pharmacologic Substance"].score_delta >= 0.0

  // Preservation: conversational-training-data invariants
  FOR ALL pair IN rebuilt_training_data DO
    ASSERT quality_filter.evaluate(pair).passed
    ASSERT token_budget_manager.fits_budget(pair, _SYSTEM_PROMPT)
    ASSERT round_trip(pair) == pair
  END FOR

  // Preservation: judge scoring semantics
  FOR ALL q IN previously_judged_questions DO
    ASSERT abs(rebuilt_score[q] - original_score[q]) <= 1  // within clamped [1,5] noise
  END FOR
END FOR
```

**Testing Approach**: Property-based testing is the right fit for Preservation because:
- The invariant set is large (all `conversational-training-data` properties plus semantic type distribution plus prompt parity) and PBT generates many inputs across the full input domain.
- Catches edge cases such as pairs with LOINC-coded concepts that become empty after cleaning, pairs at the token budget boundary, and pairs whose semantic type is ambiguous.
- Gives strong guarantees that behavior is unchanged for non-buggy inputs with a small number of test definitions.

**Test Plan**: Observe behavior on the unfixed pipeline first — run the existing `tests/ml/test_conversational_training_data*.py` suite to confirm all 12 properties still hold on the unfixed code, then write new property tests that capture the new preservation guarantees.

**Test Cases**:
1. **Per-type balance preservation**: Hypothesis generates random `target_count` and random subsets of the five eval types; assert every selected type has ≥ 10% of accepted pairs after a mocked `RAGQAStrategy.generate` run.
2. **Prompt parity property**: Hypothesis generates `InstructionTuningPair` objects via the existing `instruction_tuning_pair_strategy`; assert the user message from `format_chat_message(pair)` equals the user message the refactored `EvaluationRunner._query_ollama` would build if passed the same pair's instruction and context.
3. **Judge scoring stability**: Replay `(question, base_response, finetuned_response)` triples from `comparison_report.json` through the patched `JudgeService` with `temperature=0.1` and assert scores match within ±1 point (the clamp noise band).
4. **Conversational-training-data invariants**: Re-run the existing property tests on rebuilt training data.

### Unit Tests

- **Per-type allocation math**: `RAGQAStrategy._compute_type_allocation(target_count=12000, types=[...], floor=0.10)` returns allocations summing to `target_count` and each ≥ `target_count * 0.10 / len(types)` adjusted.
- **Top-up trigger**: When a type's accepted-pair count drops below 80% of its allocation, `_process_seed`'s top-up loop enqueues more seeds from that type (verified with a mocked RAG service).
- **`format_chat_message` parity helper**: A new helper `build_inference_user_message(instruction, context)` lives in `qlora_trainer.py` and is called by both `format_chat_message` and `EvaluationRunner`; identical output on identical input.
- **Loop-aware `_get_client`**: Mock two event loops and verify a new client is created for the second loop (observed via `httpx.AsyncClient.__init__` mock).
- **`evaluate.py` single `asyncio.run`**: Test that the CLI path invokes exactly one `asyncio.run` call (inspect coverage or use an `asyncio.run` patch counter).
- **`PairMetadata.semantic_type`**: Pydantic model accepts and round-trips `semantic_type="Diagnostic Procedure"`; missing field defaults to `None`.

### Property-Based Tests

- **Property: per-type floor**: `@given(target_count, type_subset)` — rebuilt dataset has each target type ≥ floor.
- **Property: prompt parity**: `@given(instruction_tuning_pair_strategy())` — `format_chat_message(pair)` user-message segment equals `build_inference_user_message(pair.instruction, pair.context)`.
- **Property: semantic_type round-trips in JSONL**: `@given(instruction_tuning_pair_strategy_with_semantic_type)` — `InstructionTuningPair.from_jsonl_line(pair.to_jsonl_line()) == pair`.
- **Property: judge-loop safety**: `@given(num_run_calls in [2, 5])` — invoking `DeepSeekAIService.generate_response` across N separate `asyncio.run` calls never raises `Event loop is closed`.
- Preserve all 12 properties from the `conversational-training-data` spec. Re-run on the rebuilt pipeline.

### Integration Tests

- **Full rebuild smoke test**: Run `RAGQAStrategy.generate(target_count=500, semantic_types=[5 eval types])` with mocked RAG/Neo4j/LLM, assert per-type accepted pairs ≥ 10% each and that JSONL round-trip works.
- **End-to-end prompt parity**: Run `EvaluationRunner.evaluate` against a small eval set with mocked Ollama, capture the user message passed to `_query_ollama`, assert it matches `format_chat_message` output for the same question.
- **Two-loop judge**: Run `python -m multimodal_librarian.ml.evaluate ...` against a mocked DeepSeek endpoint that fails any client reused across loops; assert the process exits cleanly with 0 `Event loop is closed` warnings in logs.
- **Before/after regression gate**: On a held-out 10-question subset, assert rebuilt fine-tuned model wins ≥ 5 while base-model-wins subset from the prior run stays ≤ original (clauses 3.6, 3.7).
