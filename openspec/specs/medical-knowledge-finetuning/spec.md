## Purpose

The Multimodal Librarian contains 356,376 chunks across medical textbooks, clinical guidelines, and AI/ML references in Milvus, a Neo4j knowledge graph with 7.1M nodes and 35.3M relationships, and 1.6M UMLS biomedical concepts with synonyms, semantic types, and relationships (treats, causes, inhibits). This feature leverages that curated knowledge infrastructure to demonstrate the Librarian's value as a knowledge curation platform for AI training — not just a RAG system.

The feature builds three pipelines: (1) a Training Data Generation Pipeline that uses the knowledge graph and RAG pipeline to produce 5,000–10,000 high-quality medical Q&A instruction-tuning pairs, (2) a QLoRA Fine-Tuning Pipeline that fine-tunes Llama 3.2 3B locally on Apple M2 Max using Apple MLX with 4-bit quantization, and (3) an Evaluation Pipeline that measures before/after improvement by scoring both the base and fine-tuned models against the Librarian's RAG-generated gold answers.


### Key Terms
- **Training_Data_Generator**: The service that orchestrates Q&A pair generation from the Librarian's knowledge graph, vector store, and RAG pipeline, producing instruction-tuning datasets in JSONL format.
- **KG_QA_Strategy**: The knowledge-graph-driven Q&A generation strategy that selects UMLS concepts with EXTRACTED_FROM edges to source chunks, generates questions from concept metadata, and extracts answers from linked chunks.
- **RAG_QA_Strategy**: The RAG-pipeline-driven Q&A generation strategy that runs medical questions through the existing RAG pipeline and captures cited responses as gold-standard training targets.
- **UMLS_Reasoning_Strategy**: The multi-hop reasoning Q&A generation strategy that traverses UMLS relationship edges (TREATS, CAUSES, TREATED_BY, PRESENTS_WITH, IS_A) between concepts to generate relationship-based questions and answers.
- **Instruction_Tuning_Pair**: A single training example in the format {instruction, context, response} suitable for supervised fine-tuning of language models.
- **QLoRA_Trainer**: The component that fine-tunes Llama 3.2 3B using QLoRA (4-bit quantization with LoRA adapters) via the Apple MLX framework (mlx-lm) for native Metal GPU acceleration on M2 Max.
- **Evaluation_Runner**: The component that runs a fixed set of 50 medical questions through both the base Llama 3.2 3B model and the fine-tuned model, scoring responses against RAG-generated gold answers.
- **Gold_Answer**: A RAG-generated response with citations from the Librarian's knowledge base, used as the reference answer for evaluation scoring.
- **GGUF_Exporter**: The component that converts the fine-tuned MLX model weights into GGUF format for deployment via Ollama.
- **Neo4j_Client**: The existing Neo4j graph database client used to execute Cypher queries against the knowledge graph containing Concept nodes, Chunk nodes, UMLSConcept nodes, and their relationships.
- **Vector_Store_Client**: The existing Milvus vector database client used to retrieve chunk content by chunk ID.
- **RAG_Service**: The existing RAGService class that performs retrieval-augmented generation with cited responses from the Librarian's knowledge base.
- **UMLS_Client**: The existing UMLSClient class that provides cached lookups against UMLSConcept and UMLSSynonym nodes in Neo4j, including relationship traversal.
- **Relationship_Traverser**: The existing RelationshipTraverser class that executes bounded Cypher queries to find paths between concepts via clinically relevant relationships (CAUSES, TREATS, TREATED_BY, PRESENTS_WITH, IS_A, PART_OF).
- **MLX_Framework**: Apple's MLX machine learning framework providing native Metal GPU acceleration for model training and inference on Apple Silicon.
- **QLoRA**: Quantized Low-Rank Adaptation — a parameter-efficient fine-tuning method combining 4-bit quantization with LoRA adapters to reduce memory requirements.
- **LoRA_Adapter**: Low-Rank Adaptation weights that are trained on top of frozen base model weights, enabling fine-tuning with minimal additional parameters.
- **GGUF_Format**: A binary format for storing quantized language model weights, used by Ollama and llama.cpp for efficient inference.

## Requirements

### Requirement: KG-Driven Q&A Pair Generation

The system SHALL support: As an AI researcher, I want to generate medical Q&A pairs from the knowledge graph's concept-to-chunk relationships, so that I can create training data grounded in the Librarian's curated medical knowledge.

#### Scenario: WHEN generating KG-driven Q&A pairs, THE KG_QA_Strategy SHAL

- **THEN** WHEN generating KG-driven Q&A pairs, THE KG_QA_Strategy SHALL query Neo4j for Concept nodes that have EXTRACTED_FROM edges to Chunk nodes and possess UMLS metadata (CUI, semantic type, synonyms).

#### Scenario: WHEN a Concept with EXTRACTED_FROM edges is selected, THE KG

- **THEN** WHEN a Concept with EXTRACTED_FROM edges is selected, THE KG_QA_Strategy SHALL retrieve the linked Chunk content from Milvus using the chunk IDs from the EXTRACTED_FROM edges.

#### Scenario: WHEN generating a question for a selected Concept, THE KG_QA

- **THEN** WHEN generating a question for a selected Concept, THE KG_QA_Strategy SHALL use the concept name, semantic type, and synonyms to formulate a clinically relevant question (e.g., "What is [concept_name] and how is it used in clinical practice?").

#### Scenario: WHEN generating an answer for a Concept-Chunk pair, THE KG_Q

- **THEN** WHEN generating an answer for a Concept-Chunk pair, THE KG_QA_Strategy SHALL extract the answer from the linked chunk content, preserving source attribution including source document title and chunk ID.

#### Scenario: WHEN a linked chunk contains fewer than 50 tokens of relevan

- **THEN** WHEN a linked chunk contains fewer than 50 tokens of relevant content, THE KG_QA_Strategy SHALL skip that Concept-Chunk pair and log the skip reason.

#### Scenario: THE KG_QA_Strategy SHALL produce Instruction_Tuning_Pairs in

- **THEN** THE KG_QA_Strategy SHALL produce Instruction_Tuning_Pairs in the format {instruction: question, context: chunk_excerpt, response: generated_answer}.

### Requirement: RAG-Generated Gold Answer Q&A Pairs

The system SHALL support: As an AI researcher, I want to generate Q&A pairs by running medical questions through the Librarian's RAG pipeline, so that I can capture the Librarian's cited, multi-source responses as high-quality training targets.

#### Scenario: WHEN generating RAG-based Q&A pairs, THE RAG_QA_Strategy SHA

- **THEN** WHEN generating RAG-based Q&A pairs, THE RAG_QA_Strategy SHALL accept a list of seed medical questions and run each through the existing RAG_Service.

#### Scenario: WHEN the RAG_Service returns a response, THE RAG_QA_Strategy

- **THEN** WHEN the RAG_Service returns a response, THE RAG_QA_Strategy SHALL capture the full cited response text as the gold answer, including source citations.

#### Scenario: WHEN the RAG_Service returns a response with fewer than 2 so

- **THEN** WHEN the RAG_Service returns a response with fewer than 2 source citations, THE RAG_QA_Strategy SHALL flag that pair as low-confidence and include a confidence score in the output metadata.

#### Scenario: WHEN the RAG_Service fails to return a response for a questi

- **THEN** WHEN the RAG_Service fails to return a response for a question, THE RAG_QA_Strategy SHALL skip that question, log the failure reason, and continue processing remaining questions.

#### Scenario: THE RAG_QA_Strategy SHALL generate seed questions from two s

- **THEN** THE RAG_QA_Strategy SHALL generate seed questions from two sources: UMLS concept names with clinical semantic types, and semantic-type-aware medical question templates derived from MedQA (USMLE-style), MedMCQA (AIIMS/NEET PG), and PubMedQA benchmark question-stem patterns. Templates SHALL be organised by UMLS semantic type (e.g., "mechanism of action" for Pharmacologic Substance, "pathophysiology" for Disease or Syndrome) via a `TEMPLATES_BY_SEMANTIC_TYPE` mapping, with a `DEFAULT_QUESTION_TEMPLATES` fallback for unrecognised types. The budget is split evenly across the two sources.

#### Scenario: THE RAG_QA_Strategy SHALL produce Instruction_Tuning_Pairs i

- **THEN** THE RAG_QA_Strategy SHALL produce Instruction_Tuning_Pairs in the format {instruction: question, context: retrieved_context_summary, response: rag_cited_answer}.

### Requirement: UMLS Relationship Reasoning Q&A Pairs

The system SHALL support: As an AI researcher, I want to generate multi-hop reasoning Q&A pairs by traversing UMLS relationships in the knowledge graph, so that the fine-tuned model learns clinical reasoning patterns like drug-disease-symptom chains.

#### Scenario: WHEN generating reasoning Q&A pairs, THE UMLS_Reasoning_Stra

- **THEN** WHEN generating reasoning Q&A pairs, THE UMLS_Reasoning_Strategy SHALL use the Relationship_Traverser to find paths between UMLS concepts via clinically relevant relationships (CAUSES, TREATS, TREATED_BY, PRESENTS_WITH, IS_A, PART_OF).

#### Scenario: WHEN a 1-hop relationship path is found (e.g., Drug_A TREATS

- **THEN** WHEN a 1-hop relationship path is found (e.g., Drug_A TREATS Disease_B), THE UMLS_Reasoning_Strategy SHALL generate a question about the relationship and an answer that explains the relationship with supporting evidence from linked chunks.

#### Scenario: WHEN a 2-hop relationship path is found (e.g., Drug_A TREATS

- **THEN** WHEN a 2-hop relationship path is found (e.g., Drug_A TREATS Disease_B, Disease_B PRESENTS_WITH Symptom_C), THE UMLS_Reasoning_Strategy SHALL generate a multi-hop reasoning question that requires understanding both relationships.

#### Scenario: WHEN generating answers for relationship-based questions, TH

- **THEN** WHEN generating answers for relationship-based questions, THE UMLS_Reasoning_Strategy SHALL retrieve supporting chunk content via EXTRACTED_FROM edges from concepts along the path.

#### Scenario: IF a relationship path has no supporting chunk content from

- **GIVEN** a relationship path has no supporting chunk content from any concept along the path
- **THEN** IF a relationship path has no supporting chunk content from any concept along the path, THEN THE UMLS_Reasoning_Strategy SHALL skip that path and log the reason.

#### Scenario: THE UMLS_Reasoning_Strategy SHALL produce Instruction_Tuning

- **THEN** THE UMLS_Reasoning_Strategy SHALL produce Instruction_Tuning_Pairs that include the relationship chain in the context field and a reasoning-based answer in the response field.

### Requirement: Training Dataset Assembly and Export

The system SHALL support: As an AI researcher, I want the generated Q&A pairs from all three strategies assembled into a single, deduplicated, shuffled training dataset in JSONL format, so that I can feed it directly into the fine-tuning pipeline.

#### Scenario: WHEN assembling the training dataset, THE Training_Data_Gene

- **THEN** WHEN assembling the training dataset, THE Training_Data_Generator SHALL merge Q&A pairs from all three strategies (KG_QA_Strategy, RAG_QA_Strategy, UMLS_Reasoning_Strategy) into a single collection.

#### Scenario: WHEN merging Q&A pairs, THE Training_Data_Generator SHALL de

- **THEN** WHEN merging Q&A pairs, THE Training_Data_Generator SHALL deduplicate pairs by comparing instruction text using normalized string similarity with a threshold of 0.95 (only near-identical pairs removed).

#### Scenario: WHEN the merged dataset is assembled, THE Training_Data_Gene

- **THEN** WHEN the merged dataset is assembled, THE Training_Data_Generator SHALL shuffle the pairs using a configurable random seed for reproducibility.

#### Scenario: THE Training_Data_Generator SHALL export the final dataset a

- **THEN** THE Training_Data_Generator SHALL export the final dataset as a JSONL file where each line is a JSON object with fields: instruction, context, response, metadata (strategy, source_concepts, confidence_score).

#### Scenario: THE Training_Data_Generator SHALL produce a dataset summary

- **THEN** THE Training_Data_Generator SHALL produce a dataset summary report including: total pairs per strategy, deduplication count, average response length, concept coverage statistics, and confidence score distribution.

#### Scenario: THE Training_Data_Generator SHALL target a final dataset siz

- **THEN** THE Training_Data_Generator SHALL target a final dataset size between 5,000 and 10,000 Instruction_Tuning_Pairs after deduplication.

#### Scenario: WHEN the assembled dataset contains fewer than 1,000 pairs a

- **THEN** WHEN the assembled dataset contains fewer than 1,000 pairs after deduplication, THE Training_Data_Generator SHALL log a warning with per-strategy counts to help diagnose which strategy underperformed.

### Requirement: QLoRA Fine-Tuning with MLX

The system SHALL support: As an AI researcher, I want to fine-tune Llama 3.2 3B on the generated medical Q&A dataset using QLoRA via Apple MLX, so that I can train locally on M2 Max with 32GB unified memory without exceeding memory limits.

#### Scenario: WHEN initiating fine-tuning, THE QLoRA_Trainer SHALL load th

- **THEN** WHEN initiating fine-tuning, THE QLoRA_Trainer SHALL load the base Llama 3.2 3B model in 4-bit quantized format using the mlx-lm library.

#### Scenario: WHEN configuring LoRA adapters, THE QLoRA_Trainer SHALL appl

- **THEN** WHEN configuring LoRA adapters, THE QLoRA_Trainer SHALL apply LoRA adapters with configurable rank (default: 16), alpha (default: 32), and target modules (default: q_proj, v_proj, k_proj, o_proj).

#### Scenario: WHEN loading the training dataset, THE QLoRA_Trainer SHALL r

- **THEN** WHEN loading the training dataset, THE QLoRA_Trainer SHALL read the JSONL file produced by the Training_Data_Generator and format each pair into the model's chat template with instruction, context, and response fields.

#### Scenario: WHEN training, THE QLoRA_Trainer SHALL use configurable hype

- **THEN** WHEN training, THE QLoRA_Trainer SHALL use configurable hyperparameters: learning rate (default: 1e-4), batch size (default: 4), gradient accumulation steps (default: 4), number of epochs (default: 3), and warmup ratio (default: 0.03).

#### Scenario: WHILE training is in progress, THE QLoRA_Trainer SHALL log t

- **THEN** WHILE training is in progress, THE QLoRA_Trainer SHALL log training loss, learning rate, and memory usage at configurable intervals (default: every 10 steps).

#### Scenario: WHEN training completes, THE QLoRA_Trainer SHALL save the Lo

- **THEN** WHEN training completes, THE QLoRA_Trainer SHALL save the LoRA adapter weights to a configurable output directory.

#### Scenario: IF peak memory usage exceeds 28GB during training, THEN THE

- **GIVEN** peak memory usage exceeds 28GB during training
- **THEN** IF peak memory usage exceeds 28GB during training, THEN THE QLoRA_Trainer SHALL reduce batch size by half and restart the current epoch, logging the memory adjustment.

#### Scenario: WHEN training completes, THE QLoRA_Trainer SHALL produce a t

- **THEN** WHEN training completes, THE QLoRA_Trainer SHALL produce a training summary including: total training time, final loss, peak memory usage, total steps, and adapter file size.

### Requirement: Model Export to GGUF for Ollama

The system SHALL support: As an AI researcher, I want to export the fine-tuned model in GGUF format, so that I can deploy it locally via Ollama for inference and comparison.

#### Scenario: WHEN exporting the fine-tuned model, THE GGUF_Exporter SHALL

- **THEN** WHEN exporting the fine-tuned model, THE GGUF_Exporter SHALL merge the LoRA adapter weights with the base Llama 3.2 3B model weights.

#### Scenario: WHEN merging is complete, THE GGUF_Exporter SHALL convert th

- **THEN** WHEN merging is complete, THE GGUF_Exporter SHALL convert the merged model to GGUF format using Q4_K_M quantization (default) with configurable quantization level.

#### Scenario: WHEN the GGUF file is produced, THE GGUF_Exporter SHALL gene

- **THEN** WHEN the GGUF file is produced, THE GGUF_Exporter SHALL generate an Ollama Modelfile that references the GGUF file and includes appropriate system prompt and parameter settings.

#### Scenario: WHEN the Modelfile is generated, THE GGUF_Exporter SHALL reg

- **THEN** WHEN the Modelfile is generated, THE GGUF_Exporter SHALL register the model with the local Ollama instance using `ollama create` with the generated Modelfile.

#### Scenario: IF the Ollama instance is not running or unreachable, THEN T

- **GIVEN** the Ollama instance is not running or unreachable
- **THEN** IF the Ollama instance is not running or unreachable, THEN THE GGUF_Exporter SHALL save the GGUF file and Modelfile to the output directory and log instructions for manual Ollama registration.

### Requirement: Evaluation Question Set Generation

The system SHALL support: As an AI researcher, I want a curated set of 50 medical evaluation questions with gold-standard answers from the Librarian's RAG pipeline, so that I can measure the fine-tuned model's improvement over the base model.

#### Scenario: WHEN generating the evaluation set, THE Evaluation_Runner SH

- **THEN** WHEN generating the evaluation set, THE Evaluation_Runner SHALL select 50 medical questions spanning at least 5 distinct UMLS semantic types (e.g., Pharmacologic Substance, Disease or Syndrome, Therapeutic Procedure, Body Part, Clinical Attribute).

#### Scenario: WHEN selecting evaluation questions, THE Evaluation_Runner S

- **THEN** WHEN selecting evaluation questions, THE Evaluation_Runner SHALL exclude questions that appear in the training dataset to prevent data leakage.

#### Scenario: WHEN generating gold answers, THE Evaluation_Runner SHALL ru

- **THEN** WHEN generating gold answers, THE Evaluation_Runner SHALL run each evaluation question through the RAG_Service and capture the cited response as the Gold_Answer.

#### Scenario: IF the RAG_Service fails to produce a cited response for an

- **GIVEN** the RAG_Service fails to produce a cited response for an evaluation question
- **THEN** IF the RAG_Service fails to produce a cited response for an evaluation question, THEN THE Evaluation_Runner SHALL replace that question with an alternative from the same semantic type.

#### Scenario: THE Evaluation_Runner SHALL export the evaluation set as a J

- **THEN** THE Evaluation_Runner SHALL export the evaluation set as a JSONL file with fields: question, gold_answer, semantic_type, source_citations, difficulty_level (single-concept, multi-concept, reasoning).

### Requirement: Before/After Model Evaluation

The system SHALL support: As an AI researcher, I want to run the same 50 evaluation questions through both the base and fine-tuned models and score the results, so that I can quantify the improvement from fine-tuning on the Librarian's medical knowledge.

#### Scenario: WHEN running evaluation, THE Evaluation_Runner SHALL send ea

- **THEN** WHEN running evaluation, THE Evaluation_Runner SHALL send each of the 50 evaluation questions to both the base Llama 3.2 3B model and the fine-tuned model via Ollama, using identical prompting.

#### Scenario: WHEN scoring responses, THE Evaluation_Runner SHALL compute

- **THEN** WHEN scoring responses, THE Evaluation_Runner SHALL compute a semantic similarity score between each model response and the Gold_Answer using the existing embedding model (BAAI/bge-base-en-v1.5).

#### Scenario: WHEN scoring responses, THE Evaluation_Runner SHALL compute

- **THEN** WHEN scoring responses, THE Evaluation_Runner SHALL compute a factual overlap score by extracting UMLS concepts from both the model response and the Gold_Answer using the existing NER_Extractor and calculating concept recall.

#### Scenario: WHEN all 50 questions are scored, THE Evaluation_Runner SHAL

- **THEN** WHEN all 50 questions are scored, THE Evaluation_Runner SHALL produce a comparison report including: per-question scores for both models, aggregate mean scores, improvement delta, breakdown by semantic type, and breakdown by difficulty level.

#### Scenario: THE Evaluation_Runner SHALL export the comparison report as

- **THEN** THE Evaluation_Runner SHALL export the comparison report as both a JSON file (machine-readable) and a Markdown file (human-readable with tables).

#### Scenario: WHEN the fine-tuned model shows less than 5% improvement in

- **THEN** WHEN the fine-tuned model shows less than 5% improvement in mean semantic similarity over the base model, THE Evaluation_Runner SHALL flag this in the report with recommendations for dataset quality review.

### Requirement: Training Data Generation API Endpoint

The system SHALL support: As a developer, I want a FastAPI endpoint to trigger and monitor training data generation, so that I can integrate the pipeline into the Librarian's existing API infrastructure.

#### Scenario: WHEN a POST request is sent to `/api/v1/ml/training-data/gen

- **THEN** WHEN a POST request is sent to `/api/v1/ml/training-data/generate`, THE Training_Data_Generator SHALL start an asynchronous training data generation job using the existing Celery task queue.

#### Scenario: WHEN the generation job is started, THE API SHALL return a j

- **THEN** WHEN the generation job is started, THE API SHALL return a job ID and status URL for polling.

#### Scenario: WHEN a GET request is sent to `/api/v1/ml/training-data/stat

- **THEN** WHEN a GET request is sent to `/api/v1/ml/training-data/status/{job_id}`, THE API SHALL return the current job status including: phase (kg_generation, rag_generation, umls_generation, assembly), progress percentage, pairs generated per strategy, and estimated time remaining.

#### Scenario: WHEN the generation job completes, THE API SHALL make the da

- **THEN** WHEN the generation job completes, THE API SHALL make the dataset available for download at `/api/v1/ml/training-data/download/{job_id}`.

#### Scenario: THE API SHALL accept configuration parameters including: tar

- **THEN** THE API SHALL accept configuration parameters including: target_pair_count (default: 7500), strategies (default: all three), random_seed (default: 42), and min_confidence_score (default: 0.5).

### Requirement: Fine-Tuning and Evaluation CLI

The system SHALL support: As an AI researcher, I want CLI commands to run fine-tuning and evaluation locally, so that I can execute the compute-intensive training and evaluation steps outside the Docker container on the host M2 Max machine.

#### Scenario: WHEN the user runs `python -m multimodal_librarian.ml.finetu

- **THEN** WHEN the user runs `python -m multimodal_librarian.ml.finetune --dataset <path>`, THE QLoRA_Trainer SHALL load the dataset and begin fine-tuning with configurable hyperparameters passed as CLI arguments.

#### Scenario: WHEN the user runs `python -m multimodal_librarian.ml.export

- **THEN** WHEN the user runs `python -m multimodal_librarian.ml.export --adapter <path> --output <path>`, THE GGUF_Exporter SHALL merge adapters, convert to GGUF, and register with Ollama.

#### Scenario: WHEN the user runs `python -m multimodal_librarian.ml.evalua

- **THEN** WHEN the user runs `python -m multimodal_librarian.ml.evaluate --eval-set <path> --base-model <name> --finetuned-model <name>`, THE Evaluation_Runner SHALL execute the before/after comparison and produce the report.

#### Scenario: WHILE any CLI command is running, THE CLI SHALL display a pr

- **THEN** WHILE any CLI command is running, THE CLI SHALL display a progress bar with current step, elapsed time, and estimated time remaining.

#### Scenario: IF a CLI command fails, THEN THE CLI SHALL display a descrip

- **GIVEN** a CLI command fails
- **THEN** IF a CLI command fails, THEN THE CLI SHALL display a descriptive error message with the failure context and suggest corrective actions.

### Requirement: Dataset Quality Validation

The system SHALL support: As an AI researcher, I want automated quality checks on the generated training dataset, so that I can identify and filter out low-quality Q&A pairs before fine-tuning.

#### Scenario: WHEN validating the training dataset, THE Training_Data_Gene

- **THEN** WHEN validating the training dataset, THE Training_Data_Generator SHALL check each Instruction_Tuning_Pair for: minimum response length (50 tokens), non-empty instruction, non-empty context, and valid JSON structure.

#### Scenario: WHEN validating response quality, THE Training_Data_Generato

- **THEN** WHEN validating response quality, THE Training_Data_Generator SHALL verify that each response contains at least one UMLS concept recognized by the NER_Extractor.

#### Scenario: WHEN validation identifies pairs that fail quality checks, T

- **THEN** WHEN validation identifies pairs that fail quality checks, THE Training_Data_Generator SHALL move failed pairs to a separate rejected file with rejection reasons.

#### Scenario: THE Training_Data_Generator SHALL log a quality summary incl

- **THEN** THE Training_Data_Generator SHALL log a quality summary including: total pairs validated, pass rate, rejection reasons distribution, and average quality metrics.

#### Scenario: IF the pass rate falls below 70%, THEN THE Training_Data_Gen

- **GIVEN** the pass rate falls below 70%
- **THEN** IF the pass rate falls below 70%, THEN THE Training_Data_Generator SHALL log a warning recommending review of the generation strategy parameters.

### Requirement: Parse and Print Training Dataset

The system SHALL support: As an AI researcher, I want to parse existing JSONL training datasets back into structured objects and print them back to JSONL, so that I can validate dataset integrity through round-trip serialization.

#### Scenario: WHEN parsing a JSONL training dataset file, THE Training_Dat

- **THEN** WHEN parsing a JSONL training dataset file, THE Training_Data_Generator SHALL deserialize each line into an Instruction_Tuning_Pair object with validated fields (instruction, context, response, metadata).

#### Scenario: WHEN printing Instruction_Tuning_Pair objects to JSONL, THE

- **THEN** WHEN printing Instruction_Tuning_Pair objects to JSONL, THE Training_Data_Generator SHALL serialize each object to a single JSON line with consistent field ordering and UTF-8 encoding.

#### Scenario: FOR ALL valid Instruction_Tuning_Pair objects, parsing then

- **GIVEN** ALL valid Instruction_Tuning_Pair objects, parsing then printing then parsing
- **THEN** FOR ALL valid Instruction_Tuning_Pair objects, parsing then printing then parsing SHALL produce an equivalent object (round-trip property).

#### Scenario: WHEN a JSONL line contains invalid JSON or missing required

- **THEN** WHEN a JSONL line contains invalid JSON or missing required fields, THE Training_Data_Generator SHALL skip that line, log the line number and error, and continue processing remaining lines.
