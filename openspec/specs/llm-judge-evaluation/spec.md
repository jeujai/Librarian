## Purpose

This feature replaces the existing cosine-similarity-based evaluation in the ML training pipeline with an LLM-as-judge approach. The current evaluation computes embedding similarity between model responses and gold-standard answers, which penalizes clinically correct responses that use different phrasing. The replacement uses DeepSeek as a judge to score responses on multiple clinical dimensions (factual accuracy, completeness, clinical relevance, coherence), pick winners with randomized A/B ordering to prevent position bias, and produce aggregate metrics (win rate, mean score delta, per-semantic-type breakdown). The system integrates into the existing pipeline as step 7 (`step_evaluate`) and produces output compatible with the current JSON and Markdown reporting format.


### Key Terms
- **Judge_Service**: The component that sends evaluation prompts to the DeepSeek API and parses structured scoring responses.
- **Evaluation_Runner**: The existing `EvaluationRunner` class in `src/multimodal_librarian/ml/evaluation_runner.py` that orchestrates evaluation set loading, model querying, scoring, and report generation.
- **DeepSeek_API**: The DeepSeek chat completions API, accessed via the existing `DeepSeekAIService` class using the `DEEPSEEK_API_KEY` environment variable.
- **Ollama**: The local model serving runtime used to query both the base model and the fine-tuned model.
- **Gold_Answer**: A RAG-generated reference answer for an evaluation question, produced during the `step_generate` phase.
- **Response_Pair**: The pair of responses (one from the base model, one from the fine-tuned model) generated for a single evaluation question.
- **Dimension_Score**: A numeric score on a 1–5 integer scale for a single scoring dimension (factual accuracy, completeness, clinical relevance, or coherence).
- **Judge_Verdict**: The structured output from a single judge call, containing four Dimension_Scores for each response, an overall winner designation (A, B, or tie), and an explanation.
- **Position_Label**: The randomized assignment of "Response A" or "Response B" to the base and fine-tuned models for a single evaluation question, used to prevent position bias.
- **Win_Rate**: The percentage of evaluation questions where the fine-tuned model is selected as the overall winner by the Judge_Service.
- **Mean_Score_Delta**: The average difference (fine-tuned minus base) of Dimension_Scores across all questions and all four dimensions.
- **Comparison_Report**: The aggregate output of the evaluation, containing per-question results, win rate, mean score delta, per-semantic-type breakdown, and recommendations.
- **Pipeline_Threshold**: The numeric improvement threshold (currently 5%) used by the pipeline to flag underperforming fine-tuned models.

## Requirements

### Requirement: Judge Prompt Construction

The system SHALL support: As a pipeline operator, I want each evaluation question to be judged with a well-structured prompt that includes the question, gold answer, and both model responses with randomized labels, so that the judge produces fair and consistent scores.

#### Scenario: WHEN an evaluation question with a Gold_Answer and a Respons

- **THEN** WHEN an evaluation question with a Gold_Answer and a Response_Pair is provided, THE Judge_Service SHALL construct a prompt containing the question text, the Gold_Answer, and both responses labeled as "Response A" and "Response B".

#### Scenario: WHEN constructing the judge prompt, THE Judge_Service SHALL

- **THEN** WHEN constructing the judge prompt, THE Judge_Service SHALL randomly assign the base model response and the fine-tuned model response to Position_Labels "A" and "B" with equal probability.

#### Scenario: THE Judge_Service SHALL include explicit scoring instruction

- **THEN** THE Judge_Service SHALL include explicit scoring instructions in the prompt requesting four Dimension_Scores (factual accuracy, completeness, clinical relevance, coherence) on a 1–5 integer scale for each response.

#### Scenario: THE Judge_Service SHALL include an instruction in the prompt

- **THEN** THE Judge_Service SHALL include an instruction in the prompt requesting an overall winner designation of "A", "B", or "tie" with a brief explanation.

#### Scenario: THE Judge_Service SHALL request the judge response in a stru

- **THEN** THE Judge_Service SHALL request the judge response in a structured JSON format specifying the expected field names and types.

### Requirement: DeepSeek Judge Invocation

The system SHALL support: As a pipeline operator, I want the judge to call the DeepSeek API for each evaluation question and parse the structured response, so that I get reliable per-question scores.

#### Scenario: WHEN a judge prompt is constructed, THE Judge_Service SHALL

- **THEN** WHEN a judge prompt is constructed, THE Judge_Service SHALL send it to the DeepSeek_API using the existing `DeepSeekAIService` class with a low temperature setting (0.1 or below) to maximize scoring consistency.

#### Scenario: WHEN the DeepSeek_API returns a response, THE Judge_Service

- **THEN** WHEN the DeepSeek_API returns a response, THE Judge_Service SHALL parse the response body to extract four Dimension_Scores per response, the overall winner, and the explanation.

#### Scenario: IF the DeepSeek_API response cannot be parsed into the expec

- **GIVEN** the DeepSeek_API response cannot be parsed into the expected structured format
- **THEN** IF the DeepSeek_API response cannot be parsed into the expected structured format, THEN THE Judge_Service SHALL retry the request up to 2 additional times before recording the question as a judge failure.

#### Scenario: IF all retry attempts fail for a question, THEN THE Judge_Se

- **GIVEN** all retry attempts fail for a question
- **THEN** IF all retry attempts fail for a question, THEN THE Judge_Service SHALL log a warning and exclude that question from aggregate scoring rather than halting the evaluation.

#### Scenario: THE Judge_Service SHALL validate that each parsed Dimension_

- **THEN** THE Judge_Service SHALL validate that each parsed Dimension_Score is an integer between 1 and 5 inclusive.

#### Scenario: IF a parsed Dimension_Score falls outside the 1–5 range, THE

- **GIVEN** a parsed Dimension_Score falls outside the 1–5 range
- **THEN** IF a parsed Dimension_Score falls outside the 1–5 range, THEN THE Judge_Service SHALL clamp the value to the nearest bound (1 or 5) and log a warning.

### Requirement: Position Bias Mitigation

The system SHALL support: As a pipeline operator, I want the A/B label assignment to be randomized per question, so that the judge does not systematically favor whichever response appears first.

#### Scenario: THE Judge_Service SHALL assign Position_Labels independently

- **THEN** THE Judge_Service SHALL assign Position_Labels independently for each evaluation question using a pseudorandom source.

#### Scenario: WHEN the Judge_Verdict designates a winner as "A" or "B", TH

- **THEN** WHEN the Judge_Verdict designates a winner as "A" or "B", THE Judge_Service SHALL map the winner back to the actual model identity (base or fine-tuned) using the Position_Label assignment for that question.

#### Scenario: THE Comparison_Report SHALL record the Position_Label assign

- **THEN** THE Comparison_Report SHALL record the Position_Label assignment for each question so that position bias can be audited after the fact.

### Requirement: Per-Question Result Structure

The system SHALL support: As a pipeline operator, I want each question's result to include the judge scores, winner, and both model responses, so that I can inspect individual judgments.

#### Scenario: THE Evaluation_Runner SHALL produce a per-question result co

- **THEN** THE Evaluation_Runner SHALL produce a per-question result containing: the question text, the Gold_Answer, both model responses, four Dimension_Scores for the base model, four Dimension_Scores for the fine-tuned model, the overall winner (base, finetuned, or tie), the judge explanation, and the Position_Label assignment.

#### Scenario: THE Evaluation_Runner SHALL retain the semantic type and dif

- **THEN** THE Evaluation_Runner SHALL retain the semantic type and difficulty level from the evaluation question in each per-question result.

### Requirement: Aggregate Metrics Computation

The system SHALL support: As a pipeline operator, I want aggregate metrics (win rate, mean score delta, per-dimension means) computed from the per-question results, so that I can assess overall fine-tuning effectiveness.

#### Scenario: WHEN all questions have been judged, THE Evaluation_Runner S

- **THEN** WHEN all questions have been judged, THE Evaluation_Runner SHALL compute the Win_Rate as the number of questions where the fine-tuned model wins divided by the total number of successfully judged questions.

#### Scenario: WHEN all questions have been judged, THE Evaluation_Runner S

- **THEN** WHEN all questions have been judged, THE Evaluation_Runner SHALL compute the Mean_Score_Delta as the average of (fine-tuned Dimension_Score minus base Dimension_Score) across all four dimensions and all successfully judged questions.

#### Scenario: THE Evaluation_Runner SHALL compute per-dimension mean score

- **THEN** THE Evaluation_Runner SHALL compute per-dimension mean scores for both the base and fine-tuned models (mean factual accuracy, mean completeness, mean clinical relevance, mean coherence).

#### Scenario: THE Evaluation_Runner SHALL compute the Win_Rate and Mean_Sc

- **THEN** THE Evaluation_Runner SHALL compute the Win_Rate and Mean_Score_Delta broken down by semantic type.

#### Scenario: THE Evaluation_Runner SHALL compute the Win_Rate and Mean_Sc

- **THEN** THE Evaluation_Runner SHALL compute the Win_Rate and Mean_Score_Delta broken down by difficulty level.

### Requirement: Pipeline Threshold Integration

The system SHALL support: As a pipeline operator, I want the LLM-judge evaluation to produce a single numeric delta compatible with the existing pipeline threshold check, so that the pipeline can automatically flag underperforming models.

#### Scenario: THE Evaluation_Runner SHALL produce an `improvement_delta` v

- **THEN** THE Evaluation_Runner SHALL produce an `improvement_delta` value derived from the Win_Rate, computed as `(win_rate - 0.5)` so that a win rate above 50% yields a positive delta and a win rate at 50% yields zero.

#### Scenario: THE Comparison_Report SHALL set the `flagged` field to true

- **THEN** THE Comparison_Report SHALL set the `flagged` field to true WHEN the `improvement_delta` is below the configured Pipeline_Threshold.

#### Scenario: WHEN the model is flagged, THE Comparison_Report SHALL inclu

- **THEN** WHEN the model is flagged, THE Comparison_Report SHALL include recommendations describing the win rate, the threshold, and suggested remediation steps.

### Requirement: JSON Report Output

The system SHALL support: As a pipeline operator, I want the evaluation to produce a JSON report file compatible with the existing pipeline reporting, so that downstream tools and dashboards continue to work.

#### Scenario: THE Evaluation_Runner SHALL export a `comparison_report.json

- **THEN** THE Evaluation_Runner SHALL export a `comparison_report.json` file to the evaluation output directory.

#### Scenario: THE JSON report SHALL contain top-level fields: `win_rate`,

- **THEN** THE JSON report SHALL contain top-level fields: `win_rate`, `mean_score_delta`, `improvement_delta`, `flagged`, `recommendations`, `by_semantic_type`, `by_difficulty`, `judge_stats`, and `results`.

#### Scenario: THE `by_semantic_type` section SHALL contain per-type entrie

- **THEN** THE `by_semantic_type` section SHALL contain per-type entries with `win_rate`, `mean_score_delta`, `base_mean_scores`, `finetuned_mean_scores`, and `count`.

#### Scenario: THE `results` array SHALL contain one entry per successfully

- **THEN** THE `results` array SHALL contain one entry per successfully judged question with all fields from the per-question result structure.

#### Scenario: THE `judge_stats` section SHALL contain `total_questions`, `

- **THEN** THE `judge_stats` section SHALL contain `total_questions`, `successful_judgments`, `failed_judgments`, and `judge_model` fields.

### Requirement: Markdown Report Output

The system SHALL support: As a pipeline operator, I want a human-readable Markdown report summarizing the evaluation results, so that I can quickly review fine-tuning effectiveness.

#### Scenario: THE Evaluation_Runner SHALL export a `comparison_report.md`

- **THEN** THE Evaluation_Runner SHALL export a `comparison_report.md` file to the evaluation output directory.

#### Scenario: THE Markdown report SHALL contain a summary table with win r

- **THEN** THE Markdown report SHALL contain a summary table with win rate, mean score delta, improvement delta, flagged status, and total questions.

#### Scenario: THE Markdown report SHALL contain a per-dimension breakdown

- **THEN** THE Markdown report SHALL contain a per-dimension breakdown table showing mean scores for both models across all four dimensions.

#### Scenario: THE Markdown report SHALL contain a per-semantic-type breakd

- **THEN** THE Markdown report SHALL contain a per-semantic-type breakdown table with win rate and mean score delta per type.

#### Scenario: THE Markdown report SHALL contain a per-difficulty breakdown

- **THEN** THE Markdown report SHALL contain a per-difficulty breakdown table with win rate and mean score delta per difficulty level.

### Requirement: Removal of Similarity-Based Scoring

The system SHALL support: As a pipeline operator, I want the cosine-similarity and concept-recall scoring to be fully replaced by the LLM-judge scoring, so that there is a single consistent evaluation methodology.

#### Scenario: THE Evaluation_Runner SHALL remove the embedding-based seman

- **THEN** THE Evaluation_Runner SHALL remove the embedding-based semantic similarity computation from the response scoring path.

#### Scenario: THE Evaluation_Runner SHALL remove the UMLS concept recall c

- **THEN** THE Evaluation_Runner SHALL remove the UMLS concept recall computation from the response scoring path.

#### Scenario: THE Evaluation_Runner SHALL remove the dependency on `senten

- **THEN** THE Evaluation_Runner SHALL remove the dependency on `sentence-transformers` for evaluation scoring.

#### Scenario: THE Evaluation_Runner SHALL remove the `_load_embedding_mode

- **THEN** THE Evaluation_Runner SHALL remove the `_load_embedding_model`, `_embed`, `_cosine_similarity`, `_compute_concept_recall`, and `_extract_candidate_concepts` methods.

#### Scenario: THE `ResponseScore` data model SHALL be replaced with a new

- **THEN** THE `ResponseScore` data model SHALL be replaced with a new model containing four Dimension_Scores (factual_accuracy, completeness, clinical_relevance, coherence) as integers in the 1–5 range.

### Requirement: Error Handling and Resilience

The system SHALL support: As a pipeline operator, I want the evaluation to handle API failures, malformed responses, and partial completions gracefully, so that a few bad judge calls do not invalidate the entire evaluation run.

#### Scenario: IF the DeepSeek_API is unreachable at the start of evaluatio

- **GIVEN** the DeepSeek_API is unreachable at the start of evaluation
- **THEN** IF the DeepSeek_API is unreachable at the start of evaluation, THEN THE Evaluation_Runner SHALL raise an error and halt before processing any questions.

#### Scenario: IF a single judge call fails after all retries, THEN THE Eva

- **GIVEN** a single judge call fails after all retries
- **THEN** IF a single judge call fails after all retries, THEN THE Evaluation_Runner SHALL skip that question and continue with the remaining questions.

#### Scenario: WHEN the evaluation completes, THE Evaluation_Runner SHALL l

- **THEN** WHEN the evaluation completes, THE Evaluation_Runner SHALL log the count of successful and failed judge calls.

#### Scenario: IF more than 50% of judge calls fail, THEN THE Evaluation_Ru

- **GIVEN** more than 50% of judge calls fail
- **THEN** IF more than 50% of judge calls fail, THEN THE Evaluation_Runner SHALL set the `flagged` field to true and include a recommendation noting the high failure rate.

#### Scenario: IF the Ollama model query fails for either model on a given

- **GIVEN** the Ollama model query fails for either model on a given question
- **THEN** IF the Ollama model query fails for either model on a given question, THEN THE Evaluation_Runner SHALL skip that question and log a warning, consistent with the existing behavior.

### Requirement: Judge Response Parsing

The system SHALL support: As a pipeline operator, I want the judge response to be reliably parsed from the DeepSeek output, so that scoring is consistent even when the LLM output varies slightly in format.

#### Scenario: THE Judge_Service SHALL parse the judge response as JSON, ex

- **THEN** THE Judge_Service SHALL parse the judge response as JSON, extracting scores and winner from the expected field structure.

#### Scenario: IF the response contains JSON embedded within markdown code

- **GIVEN** the response contains JSON embedded within markdown code fences or surrounding text
- **THEN** IF the response contains JSON embedded within markdown code fences or surrounding text, THEN THE Judge_Service SHALL extract the JSON block before parsing.

#### Scenario: IF the winner field contains a value other than "A", "B", or

- **GIVEN** the winner field contains a value other than "A", "B", or "tie" (case-insensitive)
- **THEN** IF the winner field contains a value other than "A", "B", or "tie" (case-insensitive), THEN THE Judge_Service SHALL treat the result as a tie and log a warning.

#### Scenario: FOR ALL valid Judge_Verdicts, parsing the JSON output and th

- **GIVEN** ALL valid Judge_Verdicts, parsing the JSON output and then serializing it back to JSON and re-parsing
- **THEN** FOR ALL valid Judge_Verdicts, parsing the JSON output and then serializing it back to JSON and re-parsing SHALL produce an equivalent Judge_Verdict (round-trip property).
