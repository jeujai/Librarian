## Purpose

The data generation step of the ML training pipeline (`step_generate` in `scripts/run-training-pipeline.py`) triggers a long-running Celery task that generates instruction-tuning Q&A pairs via three strategies (KG, RAG, UMLS Reasoning). For large runs (3000+ pairs with RAG), this process can take 8+ hours. Currently, if the generation job fails or is interrupted mid-way, all progress is lost and the user must restart from scratch.

This feature adds proper resume support for partially-completed data generation jobs. The server-side generator already saves partial JSONL files per strategy. The resume feature will allow the pipeline client to detect previously generated partial data, send it back to the server when re-triggering generation, and have the server skip already-completed work — producing a merged final dataset without re-generating pairs that were already successfully created.


### Key Terms
- **Pipeline_Client**: The `scripts/run-training-pipeline.py` script that orchestrates the end-to-end training pipeline from the host machine, communicating with the Docker-hosted API.
- **Generation_API**: The FastAPI router at `/api/v1/ml/training-data/` that accepts generation requests, dispatches Celery tasks, and serves status/download endpoints.
- **Generator**: The `TrainingDataGenerator` class that orchestrates Q&A pair generation across all strategies, deduplication, validation, and JSONL export inside the Celery worker.
- **Celery_Task**: The `generate_training_data_task` Celery task that wraps the Generator with live service dependencies and progress reporting.
- **Partial_Data**: JSONL files containing instruction-tuning pairs that were successfully generated before a job failed or was interrupted (e.g., `partial_kg.jsonl`, `partial_rag.jsonl`, `partial_umls.jsonl`).
- **Run_Directory**: The timestamped directory under `training_runs/` where all artifacts for a single pipeline run are stored.
- **Resume_Manifest**: A JSON structure describing previously completed work — which strategies finished, how many pairs each produced, and paths to partial data files.
- **Strategy**: One of the three generation approaches: `kg` (Knowledge Graph), `rag` (RAG Q&A), or `umls_reasoning` (UMLS Reasoning).

## Requirements

### Requirement: Download Partial Data on Failure

The system SHALL support: As a pipeline operator, I want the Pipeline_Client to automatically download any partial data when a generation job fails, so that I do not lose hours of completed LLM generation work.

#### Scenario: WHEN the Generation_API reports a job status of "failed", TH

- **THEN** WHEN the Generation_API reports a job status of "failed", THE Pipeline_Client SHALL attempt to download partial data files for each strategy that was requested.

#### Scenario: WHEN partial data files are successfully downloaded, THE Pip

- **THEN** WHEN partial data files are successfully downloaded, THE Pipeline_Client SHALL save them to the Run_Directory with filenames that identify the strategy (e.g., `partial_kg.jsonl`, `partial_rag.jsonl`, `partial_umls.jsonl`).

#### Scenario: WHEN partial data files are downloaded, THE Pipeline_Client

- **THEN** WHEN partial data files are downloaded, THE Pipeline_Client SHALL log the number of pairs recovered per strategy.

#### Scenario: IF the partial data download fails, THEN THE Pipeline_Client

- **GIVEN** the partial data download fails
- **THEN** IF the partial data download fails, THEN THE Pipeline_Client SHALL log a warning and continue without aborting.

#### Scenario: WHEN a generation job fails and partial data has been saved,

- **THEN** WHEN a generation job fails and partial data has been saved, THE Pipeline_Client SHALL print a resume command that includes `--resume-from <run-dir>` so the user can restart without losing progress.

### Requirement: Serve Partial Data Download Endpoint

The system SHALL support: As the Pipeline_Client, I want to download partial generation results from the server after a failure, so that I can preserve whatever work was completed.

#### Scenario: THE Generation_API SHALL expose a `GET /api/v1/ml/training-d

- **THEN** THE Generation_API SHALL expose a `GET /api/v1/ml/training-data/download-partial/{job_id}` endpoint that returns partial data for a failed or in-progress job.

#### Scenario: WHEN the endpoint is called for a job that has partial data

- **THEN** WHEN the endpoint is called for a job that has partial data files on disk, THE Generation_API SHALL return a JSON response containing the partial file paths and pair counts per strategy.

#### Scenario: WHEN the endpoint is called for a job that has partial data,

- **THEN** WHEN the endpoint is called for a job that has partial data, THE Generation_API SHALL serve each partial JSONL file for download via a strategy-specific query parameter (e.g., `?strategy=kg`).

#### Scenario: IF the endpoint is called for a job with no partial data, TH

- **GIVEN** the endpoint is called for a job with no partial data
- **THEN** IF the endpoint is called for a job with no partial data, THEN THE Generation_API SHALL return a 404 response with a descriptive message.

### Requirement: Accept Previously Generated Pairs on Resume

The system SHALL support: As a pipeline operator, I want to submit previously generated pairs when re-triggering data generation, so that the server can skip strategies that are already complete.

#### Scenario: THE Generation_API SHALL accept an optional `resume_data` fi

- **THEN** THE Generation_API SHALL accept an optional `resume_data` field in the `POST /generate` request body containing a Resume_Manifest with per-strategy pair counts and an indication of which strategies are already complete.

#### Scenario: THE Generation_API SHALL accept an optional `POST /api/v1/ml

- **THEN** THE Generation_API SHALL accept an optional `POST /api/v1/ml/training-data/upload-partial/{job_id}` endpoint that allows the Pipeline_Client to upload partial JSONL files before triggering a resumed generation.

#### Scenario: WHEN `resume_data` indicates a strategy is fully complete, T

- **THEN** WHEN `resume_data` indicates a strategy is fully complete, THE Generation_API SHALL pass this information to the Celery_Task so the Generator can skip that strategy entirely.

#### Scenario: WHEN `resume_data` indicates a strategy is partially complet

- **THEN** WHEN `resume_data` indicates a strategy is partially complete with a pair count, THE Generation_API SHALL pass the existing pair count so the Generator can reduce the target for that strategy accordingly.

### Requirement: Resume-Aware Generation Logic

The system SHALL support: As the Generator, I want to incorporate previously generated pairs and skip completed strategies, so that resumed jobs only generate the missing data.

#### Scenario: WHEN the Generator receives a configuration with pre-existin

- **THEN** WHEN the Generator receives a configuration with pre-existing pairs for a strategy, THE Generator SHALL reduce that strategy's target count by the number of pre-existing pairs.

#### Scenario: WHEN a strategy's pre-existing pair count meets or exceeds i

- **THEN** WHEN a strategy's pre-existing pair count meets or exceeds its target, THE Generator SHALL skip that strategy entirely and log that it was skipped due to sufficient existing data.

#### Scenario: WHEN the Generator completes a resumed run, THE Generator SH

- **THEN** WHEN the Generator completes a resumed run, THE Generator SHALL merge pre-existing pairs with newly generated pairs before deduplication.

#### Scenario: THE Generator SHALL apply deduplication across both pre-exis

- **THEN** THE Generator SHALL apply deduplication across both pre-existing and newly generated pairs using the same similarity threshold.

#### Scenario: THE Generator SHALL apply quality validation to newly genera

- **THEN** THE Generator SHALL apply quality validation to newly generated pairs only, treating pre-existing pairs as already validated.

#### Scenario: WHEN the Generator exports the final dataset, THE Generator

- **THEN** WHEN the Generator exports the final dataset, THE Generator SHALL include both pre-existing and newly generated pairs in the shuffled JSONL output.

### Requirement: Pipeline Client Resume Flag

The system SHALL support: As a pipeline operator, I want a `--resume-from` CLI flag that points to a previous run directory, so that I can resume a failed generation with a single command.

#### Scenario: THE Pipeline_Client SHALL accept a `--resume-from` argument

- **THEN** THE Pipeline_Client SHALL accept a `--resume-from` argument that takes a path to a previous Run_Directory.

#### Scenario: WHEN `--resume-from` is provided, THE Pipeline_Client SHALL

- **THEN** WHEN `--resume-from` is provided, THE Pipeline_Client SHALL scan the specified directory for partial data files (`partial_kg.jsonl`, `partial_rag.jsonl`, `partial_umls.jsonl`).

#### Scenario: WHEN partial data files are found, THE Pipeline_Client SHALL

- **THEN** WHEN partial data files are found, THE Pipeline_Client SHALL count the pairs in each file and construct a Resume_Manifest.

#### Scenario: WHEN `--resume-from` is provided, THE Pipeline_Client SHALL

- **THEN** WHEN `--resume-from` is provided, THE Pipeline_Client SHALL upload the partial data files to the server and include the Resume_Manifest in the generation request.

#### Scenario: WHEN `--resume-from` is provided without a `--run-dir`, THE

- **THEN** WHEN `--resume-from` is provided without a `--run-dir`, THE Pipeline_Client SHALL reuse the resumed run's directory as the current Run_Directory to keep all artifacts together.

#### Scenario: IF `--resume-from` points to a directory with no partial dat

- **GIVEN** `--resume-from` points to a directory with no partial data files
- **THEN** IF `--resume-from` points to a directory with no partial data files, THEN THE Pipeline_Client SHALL log a warning and proceed with a fresh generation.

### Requirement: Progress Persistence for Recovery

The system SHALL support: As a pipeline operator, I want the server to persist per-strategy completion status, so that even if the Celery worker crashes, I can determine which strategies finished.

#### Scenario: WHEN a strategy completes successfully, THE Celery_Task SHAL

- **THEN** WHEN a strategy completes successfully, THE Celery_Task SHALL persist the strategy name and pair count to the Redis progress snapshot.

#### Scenario: WHEN the Celery_Task persists progress, THE Celery_Task SHAL

- **THEN** WHEN the Celery_Task persists progress, THE Celery_Task SHALL include a `completed_strategies` field listing all strategies that have finished with their pair counts.

#### Scenario: WHEN the Pipeline_Client polls a failed job's status, THE Ge

- **THEN** WHEN the Pipeline_Client polls a failed job's status, THE Generation_API SHALL include the `completed_strategies` field in the status response so the client knows which work was saved.

#### Scenario: THE Celery_Task SHALL persist progress to Redis after each s

- **THEN** THE Celery_Task SHALL persist progress to Redis after each strategy completes, not only at periodic intervals.

### Requirement: Partial Data Integrity

The system SHALL support: As a pipeline operator, I want partial data files to be validated before use in a resumed run, so that corrupted or incomplete files do not produce a broken final dataset.

#### Scenario: WHEN the Pipeline_Client reads partial data files for resume

- **THEN** WHEN the Pipeline_Client reads partial data files for resume, THE Pipeline_Client SHALL validate that each file contains valid JSONL with parseable `InstructionTuningPair` objects.

#### Scenario: IF a partial data file contains invalid lines, THEN THE Pipe

- **GIVEN** a partial data file contains invalid lines
- **THEN** IF a partial data file contains invalid lines, THEN THE Pipeline_Client SHALL skip those lines, log a warning with the line number, and use only the valid pairs.

#### Scenario: WHEN the Generator loads pre-existing pairs from uploaded pa

- **THEN** WHEN the Generator loads pre-existing pairs from uploaded partial files, THE Generator SHALL parse them using the existing `parse_jsonl` method which already skips invalid lines with logging.

#### Scenario: THE Pipeline_Client SHALL log the total number of valid pair

- **THEN** THE Pipeline_Client SHALL log the total number of valid pairs loaded from each partial file during resume.

### Requirement: Restore Pipeline Configuration on Resume

The system SHALL support: As a pipeline operator, I want the `--resume-from` flag to automatically restore all generation and fine-tuning parameters from the failed run's saved config, so that I do not need to re-specify `--strategies`, `--semantic-types`, `--pair-count`, and other arguments on the resume command.

#### Scenario: WHEN the Pipeline_Client saves `pipeline_config.json` to the

- **THEN** WHEN the Pipeline_Client saves `pipeline_config.json` to the Run_Directory at the start of a run, THE Pipeline_Client SHALL include all CLI arguments so that the configuration is available for future resume.

#### Scenario: WHEN `--resume-from` is provided and the specified Run_Direc

- **THEN** WHEN `--resume-from` is provided and the specified Run_Directory contains a `pipeline_config.json` file, THE Pipeline_Client SHALL read the saved configuration and apply its values as defaults for all CLI arguments.

#### Scenario: WHEN `--resume-from` is provided and the saved configuration

- **THEN** WHEN `--resume-from` is provided and the saved configuration is loaded, THE Pipeline_Client SHALL allow CLI arguments explicitly provided on the resume command to override the corresponding saved configuration values.

#### Scenario: WHEN `--resume-from` is provided and the specified Run_Direc

- **THEN** WHEN `--resume-from` is provided and the specified Run_Directory does not contain a `pipeline_config.json` file, THE Pipeline_Client SHALL log a warning and proceed using the standard CLI defaults.

#### Scenario: IF the `pipeline_config.json` file contains invalid JSON, TH

- **GIVEN** the `pipeline_config.json` file contains invalid JSON
- **THEN** IF the `pipeline_config.json` file contains invalid JSON, THEN THE Pipeline_Client SHALL log a warning and proceed using the standard CLI defaults.

#### Scenario: WHEN `--resume-from` restores configuration successfully, TH

- **THEN** WHEN `--resume-from` restores configuration successfully, THE Pipeline_Client SHALL log which parameters were restored from the saved configuration.
