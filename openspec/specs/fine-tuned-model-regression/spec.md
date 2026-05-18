## Purpose

The fine-tuned Llama 3 medical Q&A model still underperforms the base model on the LLM judge evaluation even after the `conversational-training-data` spec was implemented. The evaluation run at `training_runs/2026-05-06_234338/evaluation/` shows a win rate of 0.28 (target >0.5), a mean score delta of -0.4550, and an improvement delta of -0.22 (below the +0.05 threshold). The regression is uneven across semantic types and evaluation dimensions: Diagnostic Procedure collapses to a 0% win rate with a -0.725 score delta, Sign or Symptom collapses to 10% with -1.05, Coherence drops by -0.82 (the biggest per-dimension regression), and only Pharmacologic Substance shows a net positive delta (+0.10, 60% win rate). The judge also logged intermittent `DeepSeek generation failed: Event loop is closed` warnings during evaluation, which may contaminate scores. This bugfix characterizes the regression precisely so that the subsequent design can identify the root cause and apply a targeted fix, while preserving the one semantic type where the fine-tune did help and the shared training/evaluation infrastructure that the `conversational-training-data` spec already validated.


### Defect Description
The current fine-tuned model artifact at `training_runs/2026-05-06_234338/adapters` (exported at `training_runs/2026-05-06_234338/exported_model`), trained on `training_runs/2026-05-05_145518/training_data.jsonl`, produces outputs that the LLM judge scores below the base model on the bulk of the evaluation set. The regression is concentrated on specific semantic types and on the Coherence dimension. The evaluation pipeline itself also emits transient async errors that may further depress the fine-tuned model's measured scores.

1.1 WHEN the 50-question LLM judge evaluation is run against the fine-tuned adapter at `training_runs/2026-05-06_234338/adapters` using the base model as the comparison THEN the system reports an aggregate win rate of 0.28 (below the >0.5 target) and a mean score delta of -0.4550 (below the +0.05 improvement threshold)

1.2 WHEN an evaluation question has semantic type "Diagnostic Procedure" THEN the fine-tuned model wins 0 of the associated comparisons (0.0000 win rate) and scores -0.7250 points lower on average than the base model

1.3 WHEN an evaluation question has semantic type "Sign or Symptom" THEN the fine-tuned model wins 10% of the associated comparisons and scores -1.0500 points lower on average than the base model

1.4 WHEN an evaluation question has semantic type "Disease or Syndrome" THEN the fine-tuned model wins 30% of the associated comparisons and scores -0.4250 points lower on average than the base model

1.5 WHEN an evaluation question has semantic type "Therapeutic or Preventive Procedure" THEN the fine-tuned model wins 40% of the associated comparisons and scores -0.1750 points lower on average than the base model

1.6 WHEN the LLM judge scores the fine-tuned model's output on the Coherence dimension THEN the fine-tuned model averages 3.08 versus the base model's 3.90 (a -0.82 regression, the largest of any dimension)

1.7 WHEN the LLM judge scores the fine-tuned model's output on the Factual Accuracy, Completeness, or Clinical Relevance dimensions THEN the fine-tuned model scores lower than the base model on every dimension (-0.30, -0.32, -0.38 respectively)

1.8 WHEN the DeepSeek judge client is used to score model outputs during the evaluation run THEN the pipeline intermittently logs `DeepSeek generation failed: Event loop is closed` and retries the judge call up to 2 times, leaving it ambiguous whether affected scores reflect the model's true quality or transport-layer failures

## Requirements

### Requirement: Expected Behavior: Bugfix

The system SHALL correctly handle bugfix as specified in the expected behavior.

#### Scenario 2.1

- **WHEN** the 50-question LLM judge evaluation is rerun against the rebuilt fine-tuned adapter using the base model as comparison
- **THEN** the system SHALL report an aggregate win rate greater than

#### Scenario 0.5: and a mean score delta greater than or equal to +

- **THEN** and a mean score delta greater than or equal to +

#### Scenario 0.05: (the configured improvement threshold)

- **THEN** (the configured improvement threshold)

#### Scenario 2.2

- **WHEN** an evaluation question has semantic type "Diagnostic Procedure"
- **THEN** the system SHALL achieve a win rate of at least

#### Scenario 0.4: and a score delta no worse than -

- **THEN** and a score delta no worse than -

#### Scenario 0.1: on the associated comparisons

- **THEN** on the associated comparisons

#### Scenario 2.3

- **WHEN** an evaluation question has semantic type "Sign or Symptom"
- **THEN** the system SHALL achieve a win rate of at least

#### Scenario 0.4: and a score delta no worse than -

- **THEN** and a score delta no worse than -

#### Scenario 0.1: on the associated comparisons

- **THEN** on the associated comparisons

#### Scenario 2.4

- **WHEN** an evaluation question has semantic type "Disease or Syndrome"
- **THEN** the system SHALL achieve a win rate of at least

#### Scenario 0.4: and a score delta no worse than -

- **THEN** and a score delta no worse than -

#### Scenario 0.1: on the associated comparisons

- **THEN** on the associated comparisons

#### Scenario 2.5

- **WHEN** an evaluation question has semantic type "Therapeutic or Preventive Procedure"
- **THEN** the system SHALL achieve a win rate of at least

#### Scenario 0.4: and a score delta no worse than -

- **THEN** and a score delta no worse than -

#### Scenario 0.1: on the associated comparisons

- **THEN** on the associated comparisons

#### Scenario 2.6

- **WHEN** the LLM judge scores the fine-tuned model's output on the Coherence dimension
- **THEN** the system SHALL score no lower than base -

#### Scenario 0.2: (i.e., preserving coherence within

- **THEN** (i.e., preserving coherence within

#### Scenario 0.2: points of the base model's 3.90)

- **THEN** points of the base model's 3.90)

#### Scenario 2.7

- **WHEN** the LLM judge scores the fine-tuned model's output on the Factual Accuracy, Completeness, or Clinical Relevance dimensions
- **THEN** the system SHALL score no lower than the base model minus

#### Scenario 0.2: on each dimension

- **THEN** on each dimension

#### Scenario 2.8

- **WHEN** the DeepSeek judge client is used during an evaluation run
- **THEN** the system SHALL complete all 50 question comparisons without any `Event loop is closed` errors in the pipeline output, or SHALL isolate and recover from any such transport failures so that every scored comparison reflects a successfully completed judge call (no score derived from a degraded or timed-out judge response)

### Requirement: Regression Prevention: Bugfix

The system SHALL CONTINUE TO maintain existing correct behavior for bugfix after the fix.

#### Scenario 3.1

- **WHEN** an evaluation question has semantic type "Pharmacologic Substance"
- **THEN** the system SHALL CONTINUE TO achieve a win rate of at least

#### Scenario 0.5: and a non-negative score delta (the current run shows

- **THEN** and a non-negative score delta (the current run shows

#### Scenario 0.60: / +0.10)

- **THEN** / +0.10)

#### Scenario 3.2

- **WHEN** the QLoRA training pipeline is invoked with a valid `TrainingConfig` and a valid `training_data.jsonl` file
- **THEN** the system SHALL CONTINUE TO produce a trained adapter and an exported model under `training_runs/<timestamp>/adapters` and `training_runs/<timestamp>/exported_model` respectively

#### Scenario 3.3

- **WHEN** the LLM judge evaluation pipeline is invoked with a valid fine-tuned adapter, a base model reference, and an evaluation question set
- **THEN** the system SHALL CONTINUE TO produce `comparison_report.json` and `comparison_report.md` artifacts under `training_runs/<timestamp>/evaluation/` containing per-question scores, per-dimension aggregates, per-semantic-type aggregates, and overall win rate / score delta / improvement delta metrics

#### Scenario 3.4

- **WHEN** the `conversational-training-data` pipeline generates a training pair
- **THEN** the system SHALL CONTINUE TO satisfy all invariants established by that spec: MCQ markers rejected, LOINC-coded instructions rejected, uncited long responses rejected, refusals preserved under the minimum-length exemption, token budget respected, JSONL round-trip preserved, and refusal percentage logged with the 15%–30% warning band

#### Scenario 3.5

- **WHEN** the training pipeline produces a training pair
- **THEN** the system SHALL CONTINUE TO use the production system prompt defined in `qlora_trainer.py` so that training and inference share the same system prompt contract

#### Scenario 3.6

- **WHEN** an evaluation question is not flagged as affecting a regressing semantic type and the fine-tuned model already scored at or above the base model on that question in the current run
- **THEN** the system SHALL CONTINUE TO score at or above the base model on that question after the bugfix is applied

#### Scenario 3.7

- **WHEN** the evaluation pipeline records a judge call that succeeded on the first attempt in the current run
- **THEN** the system SHALL CONTINUE TO produce a comparable (non-degraded) score for that same question from the judge
