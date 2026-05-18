# Implementation Plan: Data Generation Resume

## Overview

Add resume support for partially-completed ML training data generation jobs. The implementation touches four layers: the CLI pipeline script (`scripts/run-training-pipeline.py`), the FastAPI API router (`src/multimodal_librarian/api/routers/ml_training.py`), the Celery task (`src/multimodal_librarian/services/ml_training_tasks.py`), and the `TrainingDataGenerator` class (`src/multimodal_librarian/ml/training_data_generator.py`). Tasks are ordered so each builds on the previous, starting with data models and working outward to the CLI.

## Tasks

- [x] 1. Add resume data models and extend existing models
  - [x] 1.1 Add ResumeStrategyInfo and ResumeManifest Pydantic models to the API router
    - Add `ResumeStrategyInfo(BaseModel)` with `pair_count: int` (ge=0) and `complete: bool` fields
    - Add `ResumeManifest(BaseModel)` with `strategies: Dict[str, ResumeStrategyInfo]` field
    - Add these classes to `src/multimodal_librarian/api/routers/ml_training.py` alongside existing Pydantic models
    - _Requirements: 3.1_

  - [x] 1.2 Extend TrainingDataRequest with optional resume_data field
    - Add `resume_data: Optional[ResumeManifest] = Field(default=None)` to `TrainingDataRequest` in the API router
    - _Requirements: 3.1_

  - [x] 1.3 Extend TrainingDataStatusResponse with completed_strategies field
    - Add `completed_strategies: Optional[Dict[str, int]] = Field(default=None)` to `TrainingDataStatusResponse`
    - _Requirements: 6.3_

  - [x] 1.4 Add optional resume_data field to TrainingDataConfig dataclass
    - Add `resume_data: Optional[Dict] = None` to `TrainingDataConfig` in `src/multimodal_librarian/ml/models.py`
    - _Requirements: 3.3, 3.4_

- [x] 2. Implement the download-partial API endpoint
  - [x] 2.1 Add GET /download-partial/{job_id} endpoint to the API router
    - Without `strategy` query param: return JSON listing available partial files (`partial_kg.jsonl`, `partial_rag.jsonl`, `partial_umls.jsonl`) and pair counts per strategy
    - With `strategy` query param: stream the specific partial JSONL file using `FileResponse`
    - Return 404 if no partial data exists for the job
    - Return 422 if strategy param is not in the valid set (`kg`, `rag`, `umls_reasoning`)
    - Partial files are located at `/app/uploads/ml_training/{job_id}/partial_{strategy}.jsonl`
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [ ]* 2.2 Write unit tests for the download-partial endpoint
    - Test 200 response with JSON listing when partial files exist
    - Test 200 file download when strategy param is provided
    - Test 404 when no partial data exists
    - Test 422 for invalid strategy param
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 3. Implement the upload-partial API endpoint
  - [x] 3.1 Add POST /upload-partial/{job_id} endpoint to the API router
    - Accept multipart file upload with a `strategy` form field
    - Save the uploaded file to `/app/uploads/ml_training/{job_id}/partial_{strategy}.jsonl`
    - Create the job output directory if it doesn't exist
    - Count lines in the uploaded file and return 200 with `{strategy, pair_count}`
    - Validate strategy name is in the valid set
    - _Requirements: 3.2_

  - [ ]* 3.2 Write unit tests for the upload-partial endpoint
    - Test successful upload and file creation
    - Test pair count in response matches uploaded file
    - Test 422 for invalid strategy name
    - _Requirements: 3.2_

- [x] 4. Modify POST /generate to pass resume_data to Celery task
  - Update `start_generation()` in the API router to include `resume_data` in `config_dict` when present in the request
  - Serialize `resume_data` as a dict via `.model_dump()` before passing to Celery
  - _Requirements: 3.3, 3.4_

- [x] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Extend Celery task with per-strategy completion tracking and resume support
  - [x] 6.1 Add completed_strategies tracking to the progress callback
    - Extend `progress_state` dict with a `completed_strategies: Dict[str, int]` field
    - After each strategy completes (detected by phase transition in `_progress_callback`), add the strategy name and pair count to `completed_strategies`
    - Persist to Redis immediately after each strategy completion via `_persist_progress()`
    - _Requirements: 6.1, 6.2, 6.4_

  - [x] 6.2 Include completed_strategies in the status response
    - Update `get_status()` in the API router to read `completed_strategies` from the persisted progress snapshot and include it in `TrainingDataStatusResponse`
    - Include it for both `FAILURE` and `PROGRESS` states
    - _Requirements: 6.3_

  - [x] 6.3 Load pre-existing pairs from uploaded partial files in the Celery task
    - When `config_dict` contains `resume_data`, read the uploaded partial JSONL files from the job's output directory using `TrainingDataGenerator.parse_jsonl()`
    - Build a `pre_existing_pairs: Dict[str, List[InstructionTuningPair]]` dict keyed by strategy name
    - Pass `pre_existing_pairs` to `generator.generate()`
    - _Requirements: 3.3, 3.4, 4.1_

  - [ ]* 6.4 Write unit tests for completed_strategies tracking
    - Test that `completed_strategies` is populated in Redis after a strategy completes
    - Test that `completed_strategies` appears in the status response for failed jobs
    - _Requirements: 6.1, 6.2, 6.3_

- [x] 7. Implement resume-aware generation logic in TrainingDataGenerator
  - [x] 7.1 Extend generate() signature to accept pre_existing_pairs
    - Add `pre_existing_pairs: Optional[Dict[str, List[InstructionTuningPair]]] = None` parameter to `generate()`
    - _Requirements: 4.1_

  - [x] 7.2 Implement per-strategy target reduction and skip logic
    - For each strategy, check if `pre_existing_pairs[strategy]` count meets or exceeds the per-strategy target
    - If yes: skip the strategy entirely, log that it was skipped due to sufficient existing data, add pre-existing pairs to `all_pairs`
    - If partially complete: reduce the strategy's target by the pre-existing count, run the strategy for the remainder, then combine pre-existing + new pairs
    - _Requirements: 4.1, 4.2_

  - [ ]* 7.3 Write property test for strategy target reduction (Property 1)
    - **Property 1: Strategy target reduction**
    - For any target T > 0 and pre-existing count P >= 0, verify effective target is `max(0, T - P)` and strategy is skipped when P >= T
    - **Validates: Requirements 4.1, 4.2**

  - [x] 7.4 Implement merge of pre-existing and new pairs with correct dedup and validation scope
    - After all strategies complete, merge pre-existing pairs with newly generated pairs
    - Apply deduplication across both pre-existing and newly generated pairs using the same similarity threshold
    - Apply quality validation to newly generated pairs only — pre-existing pairs bypass validation
    - Export the combined dataset (pre-existing + new, post-dedup, post-validation) as shuffled JSONL
    - _Requirements: 4.3, 4.4, 4.5, 4.6_

  - [x] 7.5 Write property test for validation scope (Property 2)
    - **Property 2: Validation scope — pre-existing pairs bypass validation**
    - For any set of pre-existing pairs and new pairs, verify all pre-existing pairs are included (subject only to dedup) regardless of validation, while invalid new pairs are rejected
    - **Validates: Requirements 4.5**

  - [x] 7.6 Write property test for export completeness (Property 3)
    - **Property 3: Export completeness after resume**
    - For any set of pre-existing and new pairs, verify the exported JSONL contains exactly the union of (pre-existing pairs surviving dedup) and (new pairs surviving both dedup and validation), with no pairs lost or invented
    - **Validates: Requirements 4.3, 4.6**

- [x] 8. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Implement partial data download on failure in the Pipeline Client
  - [x] 9.1 Add _download_partial_data() function to the pipeline script
    - Implement `_download_partial_data(job_id: str, run_dir: Path, strategies: List[str]) -> Dict[str, int]`
    - Hit `GET /download-partial/{job_id}` to discover available partial files
    - For each available strategy, download the partial JSONL file via `GET /download-partial/{job_id}?strategy=<name>`
    - Save files to `run_dir` as `partial_kg.jsonl`, `partial_rag.jsonl`, `partial_umls.jsonl`
    - Log the number of pairs recovered per strategy
    - If download fails, log a warning and continue without aborting
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 9.2 Modify step_generate() to download partial data and print resume command on failure
    - When `job_status == "failed"`, call `_download_partial_data()` with the job's strategies
    - Print a resume command: `--resume-from <run-dir>` so the user can restart
    - _Requirements: 1.1, 1.5_

- [x] 10. Implement --resume-from CLI flag and resume flow in the Pipeline Client
  - [x] 10.1 Add --resume-from argument to the CLI parser
    - Add `--resume-from` argument to `build_parser()` that takes a path to a previous Run_Directory
    - _Requirements: 5.1_

  - [x] 10.2 Add _scan_partial_data() function for reading and validating partial files
    - Implement `_scan_partial_data(run_dir: Path) -> Dict[str, dict]`
    - Scan the directory for `partial_kg.jsonl`, `partial_rag.jsonl`, `partial_umls.jsonl`
    - Parse each file line by line, validate each line as a valid `InstructionTuningPair` JSON object
    - Skip invalid lines with a warning including the line number
    - Return a dict mapping strategy name → `{path, pair_count, pairs}` with only valid pairs
    - Log the total number of valid pairs loaded from each file
    - If no partial files found, log a warning
    - _Requirements: 5.2, 5.3, 7.1, 7.2, 7.4_

  - [ ]* 10.3 Write property test for JSONL parsing resilience (Property 4)
    - **Property 4: JSONL partial file parsing resilience**
    - For any JSONL file with a mix of valid InstructionTuningPair lines and invalid lines (malformed JSON, missing fields, empty lines), verify the parser returns exactly the set of valid pairs, skipping all invalid lines without error
    - **Validates: Requirements 7.1, 7.2**

  - [ ]* 10.4 Write property test for resume manifest pair count accuracy (Property 5)
    - **Property 5: Resume manifest pair count accuracy**
    - For any partial JSONL file containing N valid InstructionTuningPair lines and any number of invalid lines, verify the Resume_Manifest reports pair_count of exactly N
    - **Validates: Requirements 5.3**

  - [x] 10.5 Add _upload_partial_data() function for uploading partial files to the server
    - Implement `_upload_partial_data(job_id: str, partial_data: Dict) -> bool`
    - Upload each partial JSONL file to the server via `POST /upload-partial/{job_id}`
    - Return True on success, log warning and return False on failure
    - _Requirements: 5.4_

  - [x] 10.6 Wire resume flow into step_generate() and main()
    - When `--resume-from` is provided, call `_scan_partial_data()` on the specified directory
    - If partial files found: trigger a new generation job, upload partial data via `_upload_partial_data()`, include `resume_data` (ResumeManifest) in the POST /generate payload
    - When `--resume-from` is provided without `--run-dir`, reuse the resumed run's directory as the current Run_Directory
    - If `--resume-from` points to a directory with no partial files, log a warning and proceed with fresh generation
    - _Requirements: 5.2, 5.3, 5.4, 5.5, 5.6_

  - [x] 10.7 Add _load_saved_config() function to read pipeline_config.json from a resume directory
    - Implement `_load_saved_config(run_dir: Path) -> Optional[Dict]`
    - Read and parse `pipeline_config.json` from the specified Run_Directory
    - Return the parsed dict on success
    - If the file is missing, log a warning and return None
    - If the file contains invalid JSON, log a warning and return None
    - _Requirements: 8.1, 8.4, 8.5_

  - [x] 10.8 Add _apply_saved_config() function to merge saved config with CLI args
    - Implement `_apply_saved_config(args: argparse.Namespace, saved_config: Dict, explicit_args: Set[str]) -> argparse.Namespace`
    - For each key in `saved_config` that is NOT in `explicit_args`, overwrite the corresponding value in `args`
    - Log which parameters were restored from the saved configuration
    - Return the updated args namespace
    - _Requirements: 8.2, 8.3, 8.6_

  - [x] 10.9 Wire config restoration into main() before pipeline execution
    - After `parser.parse_args()`, determine which arguments were explicitly provided by the user (compare against parser defaults or use a sentinel approach)
    - When `--resume-from` is provided, call `_load_saved_config()` on the resume directory
    - If a saved config is found, call `_apply_saved_config()` to merge saved values as defaults, with explicit CLI args taking precedence
    - This must happen before the run directory is created and before any pipeline steps execute
    - _Requirements: 8.2, 8.3_

  - [x] 10.10 Write property test for saved config restoration with CLI override precedence (Property 6)
    - **Property 6: Saved config restoration with CLI override precedence**
    - For any saved config dict S and any set of explicit CLI overrides E, verify that the merged result equals S overridden by E: explicit args always win, non-explicit args are restored from saved config
    - **Validates: Requirements 8.2, 8.3**

- [x] 11. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Final integration wiring and end-to-end validation
  - [x] 12.1 Verify the full resume flow end-to-end
    - Ensure step_generate failure → partial download → resume-from → upload → resumed generation → merged output works as a connected flow
    - Verify that the `completed_strategies` field flows from Redis through the status endpoint to the client
    - Verify that the resume command printed on failure is correct and usable
    - Verify that `--resume-from` restores `pipeline_config.json` parameters and that explicit CLI args override saved values
    - _Requirements: 1.1, 1.5, 3.1, 3.2, 5.1, 5.4, 6.3, 8.2, 8.3_

  - [x] 12.2 Write integration tests for the resume flow
    - Test: upload partial data → trigger resumed generation with resume_data → verify status includes completed_strategies
    - Test: download-partial endpoint returns correct files after a job produces partial data
    - _Requirements: 1.1, 2.1, 3.1, 5.4, 6.3_

- [x] 13. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document using Hypothesis (already configured in the project)
- Unit tests validate specific examples and edge cases
- The implementation language is Python, matching the existing codebase
