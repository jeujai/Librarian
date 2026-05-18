## Purpose

This feature redesigns the training data generation pipeline to produce conversational, RAG-grounded Q&A pairs instead of the current textbook-style content. The existing pipeline generates questions from UMLS concept templates (e.g., "What is the mechanism of action of {concept_name}?") which resemble medical exam questions. When fine-tuned on this data, the model produces MCQ-style output (A/B/C/D options) even for simple questions, hallucinates medical information about unknown substances instead of refusing gracefully, and scores consistently lower (~1.5/5) than the base model (~2.5–3.5/5) on the LLM judge evaluation. Multiple hyperparameter adjustments did not resolve the degradation — the root cause is the training data itself. This feature replaces the UMLS template-based seed question generation with natural conversational questions, enforces token-budget-aware response formatting, strengthens refusal training for unknown concepts, and adds quality filters to reject MCQ-style or textbook-style content before training.


### Key Terms
- **Training_Data_Generator**: The component in `src/multimodal_librarian/ml/rag_qa_strategy.py` that produces seed questions and runs them through the RAG pipeline to generate instruction-tuning pairs.
- **Seed_Question**: A question generated as input to the RAG pipeline, currently produced from UMLS concept name templates.
- **Conversational_Question**: A natural-language question phrased as a real user would ask it in a chat interface, without exam-style phrasing or LOINC-coded terms.
- **RAG_Pipeline**: The existing retrieval-augmented generation service that retrieves relevant document chunks and produces cited responses.
- **Instruction_Tuning_Pair**: A training example consisting of an instruction (question), context (retrieved chunks), and response (gold answer), serialized as JSONL.
- **Gold_Answer**: A RAG-generated response with source citations used as the target output for fine-tuning.
- **Refusal_Response**: A response where the RAG pipeline or the training pair explicitly states that the requested information is not available in the knowledge base, teaching the model to say "I don't know" rather than fabricate.
- **MCQ_Contamination**: The phenomenon where a fine-tuned model produces multiple-choice-style output (A/B/C/D options, "the correct answer is") because the training data resembles medical exam questions.
- **LOINC_Coded_Term**: A concept name containing pipe-separated LOINC fields (e.g., `cycloSPORINE|Pt|Bld|LC/MS/MS`) that produces unnatural questions when used in templates.
- **Token_Budget**: The maximum number of tokens (currently 5000) for a complete training example (system prompt + user message + assistant response) before truncation occurs.
- **Quality_Filter**: A component that evaluates generated training pairs against style, format, and content criteria and rejects pairs that do not meet conversational quality standards.
- **LLM_Rewriter**: A component that uses an LLM to transform template-style questions into natural conversational phrasing.
- **Question_Style_Classifier**: A component that classifies whether a question or response exhibits textbook/exam style or conversational style.

## Requirements

### Requirement: Conversational Seed Question Generation

The system SHALL support: As a pipeline operator, I want seed questions to sound like real user queries in a medical chat interface, so that the fine-tuned model learns to respond conversationally rather than in exam style.

#### Scenario: WHEN generating seed questions from UMLS concepts, THE Train

- **THEN** WHEN generating seed questions from UMLS concepts, THE Training_Data_Generator SHALL produce Conversational_Questions that use natural phrasing a user would type in a chat interface, rather than textbook-style template questions.

#### Scenario: THE Training_Data_Generator SHALL use an LLM_Rewriter to tra

- **THEN** THE Training_Data_Generator SHALL use an LLM_Rewriter to transform UMLS concept names and semantic types into diverse conversational question phrasings, varying sentence structure, specificity, and register across the generated set.

#### Scenario: WHEN a UMLS concept name contains LOINC_Coded_Terms (pipe-se

- **THEN** WHEN a UMLS concept name contains LOINC_Coded_Terms (pipe-separated fields, HTML entities such as `&#x7C;`, or coded suffixes like `ANYProp`, `ANYTm`, `ANYSys`, `ANYMeth`), THE Training_Data_Generator SHALL strip the coded fields and use only the human-readable drug or concept name for question generation.

#### Scenario: THE Training_Data_Generator SHALL produce at least 5 distinc

- **THEN** THE Training_Data_Generator SHALL produce at least 5 distinct question phrasings per UMLS semantic type to ensure diversity across the training set.

#### Scenario: THE Training_Data_Generator SHALL not produce questions that

- **THEN** THE Training_Data_Generator SHALL not produce questions that begin with textbook stems such as "What is the mechanism of action of", "What is the pathophysiology of", "Describe the", or "What are the indications and contraindications for".

### Requirement: Refusal Training Data Generation

The system SHALL support: As a pipeline operator, I want the training data to include well-formed refusal examples, so that the fine-tuned model learns to say "I don't know" when information is unavailable rather than fabricating answers.

#### Scenario: THE Training_Data_Generator SHALL produce Refusal_Response t

- **THEN** THE Training_Data_Generator SHALL produce Refusal_Response training pairs where the Gold_Answer explicitly states that the requested information is not available in the knowledge base.

#### Scenario: WHEN the RAG_Pipeline returns a response indicating no relev

- **THEN** WHEN the RAG_Pipeline returns a response indicating no relevant information was found (containing phrases such as "could not find any information", "not mentioned in any of the given documents", or "no information available"), THE Training_Data_Generator SHALL format the pair as a Refusal_Response with a concise, conversational refusal.

#### Scenario: THE Training_Data_Generator SHALL ensure that Refusal_Respon

- **THEN** THE Training_Data_Generator SHALL ensure that Refusal_Response pairs constitute between 15% and 30% of the total training dataset.

#### Scenario: WHEN formatting a Refusal_Response, THE Training_Data_Genera

- **THEN** WHEN formatting a Refusal_Response, THE Training_Data_Generator SHALL use a short, direct refusal (under 200 tokens) that acknowledges the question, states the information is not in the available sources, and optionally suggests where the user might look, without fabricating any medical content.

#### Scenario: IF a RAG_Pipeline response begins with a refusal but then pr

- **GIVEN** a RAG_Pipeline response begins with a refusal but then provides information about a different substance or topic
- **THEN** IF a RAG_Pipeline response begins with a refusal but then provides information about a different substance or topic, THEN THE Training_Data_Generator SHALL either truncate the response to only the refusal portion or reject the pair entirely.

### Requirement: Token-Budget-Aware Response Formatting

The system SHALL support: As a pipeline operator, I want all training examples to fit within the model's token budget without truncation, so that the model never trains on incomplete or incoherent responses.

#### Scenario: THE Training_Data_Generator SHALL estimate the total token c

- **THEN** THE Training_Data_Generator SHALL estimate the total token count of each Instruction_Tuning_Pair (system prompt + instruction + context + response) before including it in the training set.

#### Scenario: IF the estimated total token count of an Instruction_Tuning_

- **GIVEN** the estimated total token count of an Instruction_Tuning_Pair exceeds the configured Token_Budget (default 5000 tokens)
- **THEN** IF the estimated total token count of an Instruction_Tuning_Pair exceeds the configured Token_Budget (default 5000 tokens), THEN THE Training_Data_Generator SHALL either summarize the response to fit within the budget or reject the pair.

#### Scenario: THE Training_Data_Generator SHALL not produce any Instructio

- **THEN** THE Training_Data_Generator SHALL not produce any Instruction_Tuning_Pair where the response is truncated mid-sentence or mid-paragraph.

#### Scenario: WHEN summarizing a response to fit the Token_Budget, THE Tra

- **THEN** WHEN summarizing a response to fit the Token_Budget, THE Training_Data_Generator SHALL preserve all source citations and the core factual content of the original Gold_Answer.

#### Scenario: THE Training_Data_Generator SHALL log the count of pairs rej

- **THEN** THE Training_Data_Generator SHALL log the count of pairs rejected or summarized due to token budget constraints.

### Requirement: MCQ and Textbook Style Content Filtering

The system SHALL support: As a pipeline operator, I want all MCQ-style and textbook-style content removed from the training data before fine-tuning, so that the model does not learn to produce exam-format output.

#### Scenario: THE Quality_Filter SHALL reject any Instruction_Tuning_Pair

- **THEN** THE Quality_Filter SHALL reject any Instruction_Tuning_Pair where the response contains multiple-choice markers (three or more of: `A.`, `B.`, `C.`, `D.`, `(a)`, `(b)`, `(c)`, `(d)`, or the phrase "correct answer is").

#### Scenario: THE Quality_Filter SHALL reject any Instruction_Tuning_Pair

- **THEN** THE Quality_Filter SHALL reject any Instruction_Tuning_Pair where the instruction contains LOINC_Coded_Terms that were not cleaned during seed generation.

#### Scenario: THE Quality_Filter SHALL reject any Instruction_Tuning_Pair

- **THEN** THE Quality_Filter SHALL reject any Instruction_Tuning_Pair where the response exceeds 800 tokens and contains no source citations.

#### Scenario: THE Quality_Filter SHALL reject any Instruction_Tuning_Pair

- **THEN** THE Quality_Filter SHALL reject any Instruction_Tuning_Pair where the response is shorter than 50 tokens (excluding Refusal_Response pairs, which may be shorter).

#### Scenario: THE Quality_Filter SHALL classify each instruction using a Q

- **THEN** THE Quality_Filter SHALL classify each instruction using a Question_Style_Classifier and reject pairs where the instruction is classified as textbook or exam style rather than conversational.

#### Scenario: WHEN a pair is rejected, THE Quality_Filter SHALL log the re

- **THEN** WHEN a pair is rejected, THE Quality_Filter SHALL log the rejection reason and the instruction text for auditing.

#### Scenario: THE Quality_Filter SHALL produce a summary report listing th

- **THEN** THE Quality_Filter SHALL produce a summary report listing the count of pairs rejected per rejection reason and the overall pass rate.

### Requirement: RAG Pipeline Integration Preservation

The system SHALL support: As a pipeline operator, I want the training data generation to continue using the existing RAG pipeline for gold answer generation, so that training pairs reflect the same retrieval and citation behavior the model will encounter in production.

#### Scenario: THE Training_Data_Generator SHALL use the existing RAG_Pipel

- **THEN** THE Training_Data_Generator SHALL use the existing RAG_Pipeline (`RAGService.generate_response`) to produce Gold_Answers for each Conversational_Question.

#### Scenario: THE Training_Data_Generator SHALL preserve the citation form

- **THEN** THE Training_Data_Generator SHALL preserve the citation format from the RAG_Pipeline (e.g., `[Source N]`) in all Gold_Answers included in the training set.

#### Scenario: THE Training_Data_Generator SHALL include the retrieved docu

- **THEN** THE Training_Data_Generator SHALL include the retrieved document context from the RAG_Pipeline response as the `context` field of each Instruction_Tuning_Pair.

#### Scenario: THE Training_Data_Generator SHALL compute a confidence score

- **THEN** THE Training_Data_Generator SHALL compute a confidence score for each pair based on the number of source citations, consistent with the existing scoring logic (pairs with fewer than `min_citations` sources receive a low-confidence score).

#### Scenario: THE Training_Data_Generator SHALL maintain the existing conc

- **THEN** THE Training_Data_Generator SHALL maintain the existing concurrency controls (semaphore-limited parallel RAG calls) and partial-save behavior for incremental writing during generation.

### Requirement: Training Format Alignment with Production Usage

The system SHALL support: As a pipeline operator, I want the training data format to match how the model will be used in production (system prompt + user question with RAG context → cited assistant response), so that the fine-tuned model generalizes to real usage.

#### Scenario: THE Training_Data_Generator SHALL format each Instruction_Tu

- **THEN** THE Training_Data_Generator SHALL format each Instruction_Tuning_Pair so that the user message contains the conversational question followed by the retrieved context, matching the format used by `format_chat_message` in `qlora_trainer.py`.

#### Scenario: THE Training_Data_Generator SHALL ensure the system prompt u

- **THEN** THE Training_Data_Generator SHALL ensure the system prompt used in training pairs matches the production system prompt defined in `qlora_trainer.py`.

#### Scenario: THE Training_Data_Generator SHALL ensure that Gold_Answers u

- **THEN** THE Training_Data_Generator SHALL ensure that Gold_Answers use the same citation style and response structure that the RAG_Pipeline produces in production.

#### Scenario: THE Training_Data_Generator SHALL not include any training p

- **THEN** THE Training_Data_Generator SHALL not include any training pairs where the response style diverges from the expected production output (e.g., bullet-point-only responses without prose, or responses that address the user as "student" or reference an "exam").

### Requirement: Instruction Tuning Pair Serialization Round-Trip

The system SHALL support: As a pipeline operator, I want the generated training pairs to serialize and deserialize correctly, so that no data is lost between generation and training.

#### Scenario: FOR ALL valid Instruction_Tuning_Pairs produced by the Train

- **GIVEN** ALL valid Instruction_Tuning_Pairs produced by the Training_Data_Generator, serializing to JSONL and deserializing back
- **THEN** FOR ALL valid Instruction_Tuning_Pairs produced by the Training_Data_Generator, serializing to JSONL and deserializing back SHALL produce an equivalent Instruction_Tuning_Pair (round-trip property).

#### Scenario: THE Training_Data_Generator SHALL produce Instruction_Tuning

- **THEN** THE Training_Data_Generator SHALL produce Instruction_Tuning_Pairs that conform to the existing `InstructionTuningPair` Pydantic model schema, including valid `PairMetadata` with `strategy` set to `"rag"`.

### Requirement: Generation Pipeline Observability

The system SHALL support: As a pipeline operator, I want detailed logging and metrics from the training data generation process, so that I can diagnose issues and track quality over time.

#### Scenario: WHEN generation completes, THE Training_Data_Generator SHALL

- **THEN** WHEN generation completes, THE Training_Data_Generator SHALL log a summary including: total pairs generated, pairs rejected by the Quality_Filter (with per-reason breakdown), pairs summarized for token budget, Refusal_Response count and percentage, and mean confidence score.

#### Scenario: THE Training_Data_Generator SHALL log a warning WHEN the Ref

- **THEN** THE Training_Data_Generator SHALL log a warning WHEN the Refusal_Response percentage falls outside the 15%–30% target range.

#### Scenario: THE Training_Data_Generator SHALL log a warning WHEN the Qua

- **THEN** THE Training_Data_Generator SHALL log a warning WHEN the Quality_Filter rejection rate exceeds 40% of generated pairs, indicating a potential issue with seed question quality.

#### Scenario: THE Training_Data_Generator SHALL support a `progress_callba

- **THEN** THE Training_Data_Generator SHALL support a `progress_callback` parameter consistent with the existing API, reporting `(generated, target)` counts during generation.
