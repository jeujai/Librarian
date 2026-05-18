# Implementation Plan: Medical Knowledge Fine-Tuning Pipeline

## Overview

This plan implements a three-pipeline system for medical knowledge fine-tuning: (1) training data generation inside Docker via Celery tasks using Neo4j, Milvus, and RAG, (2) QLoRA fine-tuning on the host via MLX with Metal GPU acceleration, and (3) before/after evaluation against RAG gold answers. Tasks are ordered so each builds on the previous, with data models and core utilities first, then strategies, orchestration, API/CLI, and finally evaluation.

## Tasks

- [x] 1. Define data models and core interfaces
  - [x] 1.1 Create data model module at `src/multimodal_librarian/ml/models.py`
    - Define `InstructionTuningPair`, `PairMetadata`, `TrainingDataConfig`, `TrainingConfig`, `ExportConfig`, `EvaluationConfig`, `EvaluationQuestion`, `EvaluationSet`, `ResponseScore`, `QuestionResult`, `ComparisonReport`, `TrainingDataResult`, `ValidationResult`, `DatasetSummary`, `TrainingSummary`, `ExportResult`, `SeedQuestion` dataclasses
    - Use Pydantic 2.5+ for validation where appropriate, plain dataclasses for internal-only types
    - Ensure `InstructionTuningPair` supports JSON serialization/deserialization with consistent field ordering and UTF-8 encoding
    - Add `__eq__` to `InstructionTuningPair` for round-trip comparison
    - _Requirements: 1.6, 2.6, 3.6, 4.4, 5.2, 5.8, 6.2, 7.5, 8.4, 12.1, 12.2_

  - [x] 1.2 Write property test for instruction tuning pair structural validity (Property 1)
    - **Property 1: Instruction tuning pair structural validity**
    - Use Hypothesis `@given` to generate random `InstructionTuningPair` instances; assert non-empty instruction, context, response, valid strategy, confidence_score in [0.0, 1.0]
    - File: `tests/ml/test_instruction_tuning_pair.py`
    - **Validates: Requirements 1.6, 2.6, 4.4**

  - [x] 1.3 Write property test for JSONL round-trip serialization (Property 18)
    - **Property 18: JSONL round-trip serialization**
    - Use Hypothesis to generate random `InstructionTuningPair` objects with arbitrary Unicode content; verify `parse(print(x)) == x`
    - File: `tests/ml/test_instruction_tuning_pair.py`
    - **Validates: Requirements 12.1, 12.2, 12.3**

  - [x] 1.4 Write property test for graceful handling of invalid JSONL lines (Property 19)
    - **Property 19: Graceful handling of invalid JSONL lines**
    - Use Hypothesis to generate JSONL files with a mix of valid and invalid lines; verify valid lines are parsed, invalid lines are skipped with logged line numbers
    - File: `tests/ml/test_instruction_tuning_pair.py`
    - **Validates: Requirements 12.4**

  - [x] 1.5 Create `src/multimodal_librarian/ml/__init__.py` package init
    - Set up the `ml` package under `src/multimodal_librarian/`
    - _Requirements: N/A (project structure)_

- [x] 2. Implement KG Q&A Strategy
  - [x] 2.1 Implement `KGQAStrategy` at `src/multimodal_librarian/ml/kg_qa_strategy.py`
    - Implement `__init__` accepting `Neo4jClient` and `MilvusClient`
    - Implement `generate()` method: query Neo4j for Concept nodes with EXTRACTED_FROM edges and UMLS metadata (CUI, semantic type, synonyms), retrieve linked chunk content from Milvus, generate questions using concept name/semantic type/synonyms, extract answers from chunk content preserving source attribution (document title, chunk ID)
    - Implement short-chunk filtering: skip chunks with < 50 tokens
    - Support `progress_callback` for reporting generation progress
    - Handle Neo4j connection failures gracefully (log and skip)
    - Handle Milvus connection failures gracefully (log and skip affected pairs)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [x] 2.2 Write property test for KG question generation includes concept name (Property 2)
    - **Property 2: KG question generation includes concept name**
    - Use Hypothesis to generate random concept metadata (name, semantic type, synonyms); verify generated question contains concept name (case-insensitive)
    - File: `tests/ml/test_kg_qa_strategy.py`
    - **Validates: Requirements 1.3**

  - [x] 2.3 Write property test for KG answer preserves source attribution (Property 3)
    - **Property 3: KG answer preserves source attribution**
    - Use Hypothesis to generate concept-chunk pairs with source document title and chunk ID; verify answer includes both
    - File: `tests/ml/test_kg_qa_strategy.py`
    - **Validates: Requirements 1.4**

  - [x] 2.4 Write property test for short chunk filtering (Property 4)
    - **Property 4: Short chunk filtering**
    - Use Hypothesis to generate chunks with varying token counts; verify chunks < 50 tokens are skipped, chunks >= 50 tokens are processed
    - File: `tests/ml/test_kg_qa_strategy.py`
    - **Validates: Requirements 1.5**

  - [x] 2.5 Write unit tests for KG Q&A Strategy
    - Test with specific concept types (Pharmacologic Substance, Disease or Syndrome) to verify question template selection
    - Test Neo4j query construction and result parsing
    - Test Milvus chunk retrieval with mock client
    - File: `tests/ml/test_kg_qa_strategy.py`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

- [x] 3. Implement RAG Q&A Strategy
  - [x] 3.1 Implement `RAGQAStrategy` at `src/multimodal_librarian/ml/rag_qa_strategy.py`
    - Implement `__init__` accepting `RAGService`, `Neo4jClient`, `UMLSClient`
    - Implement `generate_seed_questions()`: generate from UMLS concept names with clinical semantic types (using `TEMPLATES_BY_SEMANTIC_TYPE` for type-appropriate questions) and semantic-type-aware medical question templates derived from MedQA/MedMCQA/PubMedQA benchmark question-stem patterns; budget split evenly across the two sources
    - Implement `generate()`: run seed questions through RAG_Service, capture cited responses as gold answers, flag pairs with < 2 citations as low-confidence, skip questions where RAG fails (log failure reason, continue)
    - Support `progress_callback` for reporting generation progress
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 3.2 Write property test for low-confidence flagging by citation count (Property 5)
    - **Property 5: Low-confidence flagging by citation count**
    - Use Hypothesis to generate RAG responses with varying citation counts; verify < 2 citations → low confidence, >= 2 citations → not flagged
    - File: `tests/ml/test_rag_qa_strategy.py`
    - **Validates: Requirements 2.3**

  - [x] 3.3 Write unit tests for RAG Q&A Strategy
    - Test seed question generation from each of the two sources independently
    - Test RAG failure handling (skip and continue)
    - Test citation counting and confidence scoring
    - File: `tests/ml/test_rag_qa_strategy.py`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [x] 4. Implement UMLS Reasoning Strategy
  - [x] 4.1 Implement `UMLSReasoningStrategy` at `src/multimodal_librarian/ml/umls_reasoning_strategy.py`
    - Implement `__init__` accepting `RelationshipTraverser`, `UMLSClient`, `MilvusClient`
    - Implement `generate()`: use RelationshipTraverser to find 1-hop and 2-hop paths via CAUSES, TREATS, TREATED_BY, PRESENTS_WITH, IS_A, PART_OF relationships; generate relationship-based questions referencing all concepts in the path; produce reasoning answers with supporting chunk content from EXTRACTED_FROM edges; skip paths with no supporting chunk content
    - Support `max_hops` parameter (default 2) and configurable `relationship_types`
    - Support `progress_callback` for reporting generation progress
    - Handle RelationshipTraverser timeouts gracefully (skip and log)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [x] 4.2 Write property test for relationship question references all path concepts (Property 6)
    - **Property 6: Relationship question references all path concepts**
    - Use Hypothesis to generate 1-hop (A→B) and 2-hop (A→B→C) paths; verify all concept names appear in the generated question
    - File: `tests/ml/test_umls_reasoning_strategy.py`
    - **Validates: Requirements 3.2, 3.3**

  - [x] 4.3 Write property test for UMLS reasoning context contains relationship chain (Property 7)
    - **Property 7: UMLS reasoning context contains relationship chain**
    - Use Hypothesis to generate relationship paths; verify the context field contains the relationship chain string
    - File: `tests/ml/test_umls_reasoning_strategy.py`
    - **Validates: Requirements 3.6**

  - [x] 4.4 Write unit tests for UMLS Reasoning Strategy
    - Test specific relationship chains (e.g., Aspirin TREATS Headache, Headache PRESENTS_WITH Photophobia)
    - Test 1-hop vs 2-hop question generation
    - Test skip behavior when no supporting chunks exist
    - File: `tests/ml/test_umls_reasoning_strategy.py`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [x] 5. Checkpoint - Verify all three strategies
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement Training Data Generator orchestrator
  - [x] 6.1 Implement `TrainingDataGenerator` at `src/multimodal_librarian/ml/training_data_generator.py`
    - Implement `__init__` accepting all six service dependencies (Neo4jClient, MilvusClient, RAGService, UMLSClient, RelationshipTraverser, NER_Extractor)
    - Implement `generate()`: run all three strategies, merge results, deduplicate, validate, export JSONL
    - Implement `deduplicate()`: normalized string similarity with configurable threshold (default 0.85)
    - Implement `validate_dataset()`: check min response length (50 tokens), non-empty fields, valid JSON structure, at least one NER-recognized UMLS concept in response; partition into accepted/rejected with rejection reasons
    - Implement `export_jsonl()`: shuffle with configurable seed, write JSONL with metadata, produce dataset summary (total pairs per strategy, dedup count, avg response length, concept coverage, confidence distribution)
    - Implement `parse_jsonl()` static method: deserialize JSONL lines into InstructionTuningPair objects, skip invalid lines with logged line numbers
    - Implement `print_jsonl()` static method: serialize InstructionTuningPair objects to JSONL with consistent field ordering
    - Log warning when assembled dataset < 1,000 pairs after dedup
    - Log warning when quality pass rate < 70%
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 11.1, 11.2, 11.3, 11.4, 11.5, 12.1, 12.2, 12.3, 12.4_

  - [x] 6.2 Write property test for deduplication (Property 8)
    - **Property 8: Deduplication preserves unique pairs and removes near-duplicates**
    - Use Hypothesis to generate lists of instruction strings with controlled similarity; verify no two remaining pairs have similarity >= 0.85 and every removed pair has similarity >= 0.85 with at least one remaining pair
    - File: `tests/ml/test_training_data_generator.py`
    - **Validates: Requirements 4.2**

  - [x] 6.3 Write property test for deterministic shuffling (Property 9)
    - **Property 9: Deterministic shuffling with seed**
    - Use Hypothesis to generate random lists and seeds; verify shuffling twice with same seed produces identical orderings
    - File: `tests/ml/test_training_data_generator.py`
    - **Validates: Requirements 4.3**

  - [x] 6.4 Write property test for dataset validation partitioning (Property 16)
    - **Property 16: Dataset validation correctly partitions pairs**
    - Use Hypothesis to generate lists of InstructionTuningPairs with varying quality; verify accepted pairs meet all checks, rejected pairs fail at least one check with non-empty rejection reason
    - File: `tests/ml/test_dataset_validation.py`
    - **Validates: Requirements 11.1, 11.2, 11.3**

  - [x] 6.5 Write property test for quality warning threshold (Property 17)
    - **Property 17: Quality warning threshold**
    - Use Hypothesis to generate validation results with varying pass rates; verify warning logged when < 0.70, no warning when >= 0.70
    - File: `tests/ml/test_dataset_validation.py`
    - **Validates: Requirements 11.5**

  - [x] 6.6 Write unit tests for Training Data Generator
    - Test deduplication with exact duplicates, near-duplicates at boundary (0.84 vs 0.86 similarity), and completely distinct pairs
    - Test validation edge cases: response with exactly 50 tokens, empty metadata fields, Unicode content
    - Test dataset summary report generation
    - File: `tests/ml/test_training_data_generator.py`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 11.1, 11.2, 11.3, 11.4, 11.5_

- [x] 7. Implement Celery task and FastAPI endpoint for training data generation
  - [x] 7.1 Create Celery task for training data generation
    - Add async Celery task that instantiates `TrainingDataGenerator` with existing service dependencies and calls `generate()`
    - Report progress via Celery task state updates (phase, percentage, pairs per strategy, ETA)
    - Handle hard timeouts gracefully with progress persistence in Redis
    - Wire into existing Celery task infrastructure
    - _Requirements: 9.1, 9.3_

  - [x] 7.2 Implement FastAPI router at `src/multimodal_librarian/api/routers/ml_training.py`
    - Implement `POST /api/v1/ml/training-data/generate`: accept `TrainingDataRequest` config (target_pair_count, strategies, random_seed, min_confidence_score), dispatch Celery task, return job ID and status URL
    - Implement `GET /api/v1/ml/training-data/status/{job_id}`: return job status (phase, progress percentage, pairs per strategy, ETA)
    - Implement `GET /api/v1/ml/training-data/download/{job_id}`: return completed dataset JSONL as FileResponse
    - Define Pydantic request/response models (`TrainingDataRequest`, `TrainingDataJobResponse`, `TrainingDataStatusResponse`)
    - Use FastAPI dependency injection for Celery service access
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x] 7.3 Write integration tests for ML training API endpoints
    - Test POST /generate → GET /status → GET /download lifecycle with mocked Celery
    - Test configuration parameter validation
    - Test error responses for invalid job IDs
    - File: `tests/integration/test_ml_training_api.py`
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [x] 8. Checkpoint - Verify data generation pipeline
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Implement QLoRA Trainer
  - [x] 9.1 Implement `QLoRATrainer` at `src/multimodal_librarian/ml/qlora_trainer.py`
    - Implement `__init__` accepting `TrainingConfig`
    - Implement `train()`: load base model in 4-bit via `mlx_lm.load()`, apply LoRA adapters to target modules (q_proj, v_proj, k_proj, o_proj), format dataset into chat template, train with `mlx_lm.lora.train()`, monitor memory and reduce batch size if > 28GB, save adapter weights, produce `TrainingSummary`
    - Implement `_format_dataset()`: convert JSONL to mlx-lm chat format with instruction/context/response mapped to the Llama chat template
    - Log training loss, learning rate, and memory usage at configurable intervals (default every 10 steps)
    - Handle NaN loss by aborting and saving last valid checkpoint
    - Handle disk space errors with descriptive messages
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8_

  - [x] 9.2 Write property test for chat template formatting preserves content (Property 10)
    - **Property 10: Chat template formatting preserves content**
    - Use Hypothesis to generate random InstructionTuningPairs; verify formatted chat template string contains original instruction, context, and response text
    - File: `tests/ml/test_qlora_trainer.py`
    - **Validates: Requirements 5.3**

  - [ ]* 9.3 Write unit tests for QLoRA Trainer
    - Test `_format_dataset()` with known input/output pairs
    - Test `TrainingConfig` defaults and validation
    - Test memory threshold batch size reduction logic
    - File: `tests/ml/test_qlora_trainer.py`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.7_

- [x] 10. Implement GGUF Exporter
  - [x] 10.1 Implement `GGUFExporter` at `src/multimodal_librarian/ml/gguf_exporter.py`
    - Implement `__init__` accepting `ExportConfig`
    - Implement `export()`: fuse LoRA adapters with base model via `mlx_lm.fuse()`, convert fused model to GGUF via llama.cpp convert script, quantize to Q4_K_M (configurable), generate Ollama Modelfile, register with Ollama via `ollama create`
    - Implement `_generate_modelfile()`: produce Modelfile with FROM directive referencing GGUF path, PARAMETER directives, and SYSTEM directive with medical assistant system prompt
    - Handle Ollama not running: save GGUF + Modelfile to output dir, log manual instructions, exit code 0
    - Handle mlx_lm.fuse and llama.cpp conversion failures with descriptive error messages
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 10.2 Write property test for Modelfile contains required directives (Property 11)
    - **Property 11: Modelfile contains required directives**
    - Use Hypothesis to generate random GGUF file paths and model names; verify Modelfile contains FROM directive, at least one PARAMETER directive, and SYSTEM directive with non-empty prompt
    - File: `tests/ml/test_gguf_exporter.py`
    - **Validates: Requirements 6.3**

  - [ ]* 10.3 Write unit tests for GGUF Exporter
    - Test Modelfile generation with known inputs
    - Test Ollama-not-running fallback behavior
    - Test export config validation
    - File: `tests/ml/test_gguf_exporter.py`
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [-] 11. Implement Evaluation Runner
  - [x] 11.1 Implement `EvaluationRunner` at `src/multimodal_librarian/ml/evaluation_runner.py`
    - Implement `__init__` accepting `EvaluationConfig`
    - Implement `generate_eval_set()`: select 50 questions spanning 5+ UMLS semantic types, exclude training set questions, generate gold answers via RAG, replace failed questions with alternatives from same semantic type, export as JSONL
    - Implement `evaluate()`: send each question to both base and fine-tuned models via Ollama, score with `_score_response()`, produce `ComparisonReport` with per-question scores, aggregate means, improvement delta, breakdown by semantic type and difficulty level
    - Implement `_score_response()`: compute semantic similarity via bge-base-en-v1.5 embeddings (cosine similarity), compute concept recall via NER_Extractor UMLS concept overlap
    - Export comparison report as JSON and Markdown files
    - Flag report when improvement < 5% with recommendations
    - Handle Ollama model not found, embedding model unavailable (fallback to local sentence-transformers), NER_Extractor failure (use embedding only, set concept_recall to -1.0)
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [x] 11.2 Write property test for evaluation set excludes training questions (Property 12)
    - **Property 12: Evaluation set excludes training questions**
    - Use Hypothesis to generate training datasets and evaluation sets; verify intersection of instruction texts and evaluation question texts is empty
    - File: `tests/ml/test_evaluation_runner.py`
    - **Validates: Requirements 7.2**

  - [x] 11.3 Write property test for evaluation set JSONL format (Property 13)
    - **Property 13: Evaluation set JSONL format**
    - Use Hypothesis to generate evaluation sets; verify each JSONL line contains question, gold_answer, semantic_type, source_citations, difficulty_level — all non-empty
    - File: `tests/ml/test_evaluation_runner.py`
    - **Validates: Requirements 7.5**

  - [x] 11.4 Write property test for scoring metrics bounded and well-behaved (Property 14)
    - **Property 14: Scoring metrics are bounded and well-behaved**
    - Use Hypothesis to generate random embedding vectors and concept sets; verify semantic similarity in [0.0, 1.0], concept recall in [0.0, 1.0], identical response → similarity >= 0.95, all gold concepts present → recall == 1.0
    - File: `tests/ml/test_evaluation_runner.py`
    - **Validates: Requirements 8.2, 8.3**

  - [x] 11.5 Write property test for improvement flagging threshold (Property 15)
    - **Property 15: Improvement flagging threshold**
    - Use Hypothesis to generate comparison reports with varying improvement deltas; verify < 5% → flagged=True with recommendations, >= 5% → flagged=False
    - File: `tests/ml/test_evaluation_runner.py`
    - **Validates: Requirements 8.6**

  - [ ]* 11.6 Write unit tests for Evaluation Runner
    - Test evaluation with mocked Ollama responses against a known eval set
    - Test report structure and score calculations
    - Test semantic type distribution enforcement (5+ types)
    - Test Markdown report formatting
    - File: `tests/ml/test_evaluation_runner.py`
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

- [x] 12. Checkpoint - Verify training, export, and evaluation components
  - Ensure all tests pass, ask the user if questions arise.

- [x] 13. Implement CLI commands
  - [x] 13.1 Implement fine-tuning CLI at `src/multimodal_librarian/ml/finetune.py`
    - Entry point: `python -m multimodal_librarian.ml.finetune --dataset <path>`
    - Accept CLI arguments for all `TrainingConfig` hyperparameters (learning rate, batch size, epochs, lora rank, etc.)
    - Display progress bar with current step, elapsed time, and ETA using `rich`
    - Display descriptive error messages with corrective suggestions on failure
    - Wire to `QLoRATrainer.train()`
    - _Requirements: 10.1, 10.4, 10.5_

  - [x] 13.2 Implement export CLI at `src/multimodal_librarian/ml/export.py`
    - Entry point: `python -m multimodal_librarian.ml.export --adapter <path> --output <path>`
    - Accept CLI arguments for quantization level, model name, Ollama registration toggle
    - Display progress bar with current step, elapsed time, and ETA using `rich`
    - Display descriptive error messages with corrective suggestions on failure
    - Wire to `GGUFExporter.export()`
    - _Requirements: 10.2, 10.4, 10.5_

  - [x] 13.3 Implement evaluation CLI at `src/multimodal_librarian/ml/evaluate.py`
    - Entry point: `python -m multimodal_librarian.ml.evaluate --eval-set <path> --base-model <name> --finetuned-model <name>`
    - Accept CLI arguments for output directory, report format options
    - Display progress bar with current step, elapsed time, and ETA using `rich`
    - Display descriptive error messages with corrective suggestions on failure
    - Wire to `EvaluationRunner.evaluate()`
    - _Requirements: 10.3, 10.4, 10.5_

  - [ ]* 13.4 Write unit tests for CLI argument parsing
    - Test each CLI command with valid and invalid argument combinations
    - Test error message formatting
    - File: `tests/ml/test_cli.py`
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [x] 14. Wire everything together and add dependencies
  - [x] 14.1 Update `requirements.txt` with new dependencies
    - Add `mlx-lm` (for QLoRA training and model fusing on host)
    - Add `llama-cpp-python` (for GGUF conversion on host)
    - Add `rich` (for CLI progress bars)
    - Pin exact versions for reproducibility
    - _Requirements: 5.1, 6.2, 10.4_

  - [x] 14.2 Register the ML training router in the FastAPI app
    - Import and include the `ml_training` router in `src/multimodal_librarian/main.py`
    - Add dependency injection providers for `TrainingDataGenerator` service dependencies
    - _Requirements: 9.1_

  - [x] 14.3 Write integration test for end-to-end data generation (small scale)
    - Run a small-scale generation (target 50 pairs) against mocked Neo4j/Milvus/RAG services with known data
    - Verify output JSONL structure, deduplication, validation, and summary report
    - File: `tests/integration/test_ml_training_api.py`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 9.1_

- [x] 15. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation after each major component group
- Property tests validate the 19 universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Training data generation runs inside Docker (Celery tasks with access to Neo4j, Milvus, RAG)
- Fine-tuning, export, and evaluation run on the host machine (Metal GPU access via MLX)
- All new ML code goes under `src/multimodal_librarian/ml/`
- Test files go under `tests/ml/` for unit/property tests and `tests/integration/` for integration tests
