cument name# Implementation Plan: NER Quality Gate

## Overview

Implement a quality gate that tracks per-document model failure rates during KG extraction and bridge generation, computes a weighted composite failure rate, hard-fails documents exceeding domain-specific thresholds, persists failure data to `job_metadata`, surfaces failures in reports and the UI, and provides a clickable breakdown popup.

## Tasks

- [x] 1. Enhance ModelServerClient retry logic
  - [x] 1.1 Change `max_retries` default from 3 to 5 in `ModelServerClient.__init__`
    - File: `src/multimodal_librarian/clients/model_server_client.py`
    - Change `max_retries: int = 3` → `max_retries: int = 5`
    - _Requirements: 1.1_
  - [x] 1.2 Replace linear backoff with exponential backoff in `_request`
    - File: `src/multimodal_librarian/clients/model_server_client.py`
    - Change `await asyncio.sleep(self.retry_delay * (attempt + 1))` → `await asyncio.sleep(min(2 ** attempt, 16))`
    - Verify the existing 120s per-request timeout is unchanged
    - _Requirements: 1.2, 1.3, 1.4_
  - [ ]* 1.3 Write property tests for retry enhancement
    - **Property 1: Exponential backoff delay formula** — for any attempt `n` in `[0, max_retries-2]`, delay = `min(2^n, 16)`
    - **Property 2: Retry exhaustion attempts** — for any `max_retries` and always-failing request, exactly `max_retries` attempts before `ModelServerUnavailable`
    - **Validates: Requirements 1.2, 1.3**

- [-] 2. Create QualityGateResult dataclass and threshold configuration
  - [x] 2.1 Create `QualityGateResult` dataclass and `get_quality_threshold()` function
    - Create new file: `src/multimodal_librarian/services/quality_gate.py`
    - Implement `QualityGateResult` dataclass with fields: `composite_rate`, `threshold`, `passed`, `content_type`, `ner_rate`, `llm_rate`, `bridge_rate`, `ner_failures`, `ner_total`, `llm_failures`, `llm_total`, `bridge_failures`, `bridge_total`, `worst_model`
    - Implement `to_dict()` method using `dataclasses.asdict()`
    - Implement `error_message()` method returning human-readable string with composite rate, threshold, content type, and worst model
    - Implement `get_quality_threshold(content_type)` with `DEFAULT_THRESHOLDS` dict (MEDICAL=0.05, LEGAL=0.10, TECHNICAL=0.15, ACADEMIC=0.15, NARRATIVE=0.25, GENERAL=0.20) and `MODEL_FAIL_THRESHOLD_{TYPE}` env var override
    - Implement `compute_quality_gate(kg_failures, bridge_failures, content_type)` function that computes rates, composite formula `max(ner_rate, llm_rate) * 0.7 + bridge_rate * 0.3`, and returns `QualityGateResult`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 2.7, 4.5_
  - [ ]* 2.2 Write property tests for quality gate logic
    - File: `tests/components/test_quality_gate_properties.py`
    - **Property 4: Failure rate computation** — for any `(failures, total)` with `total > 0`, rate = `failures / total`; when `total == 0`, rate = `0.0`
    - **Validates: Requirements 2.5, 2.6**
  - [ ]* 2.3 Write property test for composite formula
    - **Property 5: Composite formula correctness** — for any `(ner_rate, llm_rate, bridge_rate)` in `[0,1]`, composite = `max(ner_rate, llm_rate) * 0.7 + bridge_rate * 0.3`
    - **Validates: Requirements 2.7**
  - [ ]* 2.4 Write property test for threshold override
    - **Property 6: Environment variable threshold override** — for any `ContentType` and integer `v` in `[0,100]`, when `MODEL_FAIL_THRESHOLD_{TYPE}=str(v)`, returns `v/100.0`; when unset, returns default
    - **Validates: Requirements 3.3, 3.4**
  - [ ]* 2.5 Write property test for pass/fail decision
    - **Property 7: Quality gate pass/fail decision** — for any `r` in `[0,1]` and `t` in `(0,1]`, `passed=True` when `r <= t`, `passed=False` when `r > t`
    - **Validates: Requirements 4.1**
  - [ ]* 2.6 Write property test for error message
    - **Property 8: Error message contains diagnostic info** — for any `QualityGateResult` where `passed=False`, `error_message()` contains composite rate %, threshold %, and `worst_model`
    - **Validates: Requirements 4.5**
  - [ ]* 2.7 Write property test for serialization round-trip
    - **Property 9: QualityGateResult serialization round-trip** — for any valid instance, `to_dict()` → reconstruct produces equivalent object
    - **Validates: Requirements 7.5**

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Instrument failure counting in KG extraction
  - [x] 4.1 Modify `extract_concepts_with_ner` to return `Tuple[List[ConceptNode], bool]`
    - File: `src/multimodal_librarian/components/knowledge_graph/kg_builder.py`
    - Change return type to `Tuple[List[ConceptNode], bool]` where second element is `ner_failed`
    - Return `([], True)` when model server is unavailable or `get_entities` raises an exception
    - Return `(concepts, False)` on success
    - _Requirements: 2.1_
  - [x] 4.2 Modify `extract_concepts_ollama` to return `Tuple[List[ConceptNode], bool]`
    - File: `src/multimodal_librarian/components/knowledge_graph/kg_builder.py`
    - Change return type to `Tuple[List[ConceptNode], bool]` where second element is `llm_failed`
    - Return `([], True)` when both Ollama fails (and Gemini disabled/fails)
    - Return `(concepts, False)` on success
    - _Requirements: 2.2_
  - [x] 4.3 Update `extract_all_concepts_async` to propagate failure flags
    - File: `src/multimodal_librarian/components/knowledge_graph/kg_builder.py`
    - Update callers of `extract_concepts_with_ner` and `extract_concepts_ollama` to handle the new tuple return type
    - Return `Tuple[List[ConceptNode], bool, bool]` — `(concepts, ner_failed, llm_failed)`
    - _Requirements: 2.1, 2.2_
  - [x] 4.4 Update `process_knowledge_chunk_extract_only` to propagate failure flags
    - File: `src/multimodal_librarian/components/knowledge_graph/kg_builder.py`
    - Modify `KnowledgeGraphBuilder.process_knowledge_chunk_extract_only()` to return failure flags alongside the `ConceptExtraction` result (e.g., add `ner_failed` and `llm_failed` attributes to the return or wrap in a tuple)
    - _Requirements: 2.1, 2.2_
  - [x] 4.5 Add failure counters to `_update_knowledge_graph` and return failure data
    - File: `src/multimodal_librarian/services/celery_service.py`
    - Add `ner_failure_count = 0` and `llm_failure_count = 0` counters at top of function
    - In the per-batch extraction loop, unpack failure flags from each chunk's extraction result and increment counters
    - Return `{'ner_failures': ner_failure_count, 'llm_failures': llm_failure_count, 'total_chunks': total_chunks}` from the function
    - _Requirements: 2.1, 2.2, 2.5, 2.8_
  - [x] 4.6 Propagate KG failure data through `update_knowledge_graph_task` return value
    - File: `src/multimodal_librarian/services/celery_service.py`
    - Capture the return value from `_update_knowledge_graph()` (currently returns None)
    - Include `kg_failures` dict in the task's return dict: `{'status': 'completed', 'document_id': ..., 'kg_failures': {...}}`
    - _Requirements: 2.5, 2.8_
  - [ ]* 4.7 Write property test for failure counter accuracy
    - **Property 3: Failure counter accuracy** — for any set of chunks with random NER/LLM failure patterns, counters match expected counts; bridge attempts where Ollama fails but Gemini succeeds are NOT counted
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4**

- [x] 5. Instrument failure counting in bridge generation
  - [x] 5.1 Modify `batch_generate_bridges` to return `Tuple[List[BridgeChunk], BatchGenerationStats]`
    - File: `src/multimodal_librarian/components/chunking_framework/bridge_generator.py`
    - Change return type from `List[BridgeChunk]` to `Tuple[List[BridgeChunk], BatchGenerationStats]`
    - Return `(bridge_chunks, batch_stats)` at the end
    - _Requirements: 2.3, 2.4, 2.6_
  - [x] 5.2 Update `generate_bridges_for_document` to propagate stats
    - File: `src/multimodal_librarian/components/chunking_framework/framework.py`
    - Update the call to `batch_generate_bridges` to unpack `(raw_bridges, batch_stats)`
    - Return `(bridges, batch_stats)` from `generate_bridges_for_document`
    - _Requirements: 2.3, 2.6_
  - [x] 5.3 Include bridge failure data in `generate_bridges_task` return value
    - File: `src/multimodal_librarian/services/celery_service.py`
    - Unpack `(bridges, batch_stats)` from `generate_bridges_for_document`
    - Add `bridge_failures` dict to return: `{'bridge_failures': {'failed_bridges': batch_stats.failed_generations, 'total_bridges': batch_stats.total_requests}}`
    - Handle the no-bridges-needed case: return `bridge_failures: {'failed_bridges': 0, 'total_bridges': 0}`
    - _Requirements: 2.3, 2.4, 2.6, 2.8_

- [x] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement quality gate in finalize_processing_task
  - [x] 7.1 Add quality gate evaluation to `finalize_processing_task`
    - File: `src/multimodal_librarian/services/celery_service.py`
    - Import `compute_quality_gate`, `QualityGateResult` from `quality_gate.py`
    - Extract `kg_failures` and `bridge_failures` dicts from `parallel_results`
    - Determine document `content_type` from the processing payload or chunks metadata
    - Call `compute_quality_gate(kg_failures, bridge_failures, content_type)`
    - If `result.passed == False`: set `failed_stage='update_knowledge_graph'`, mark document FAILED, send WebSocket failure notification with `result.error_message()`
    - If `result.passed == True`: proceed with existing COMPLETED flow
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3_
  - [x] 7.2 Persist quality gate data to `job_metadata`
    - File: `src/multimodal_librarian/services/celery_service.py`
    - After quality gate evaluation (pass or fail), persist `result.to_dict()` under `job_metadata.quality_gate` key via `jsonb_set` in `_update_job_status_sync` or a dedicated helper
    - Ensure both passing and failing documents have the `quality_gate` key for report display
    - _Requirements: 7.5_

- [x] 8. Add report columns for model failure data
  - [x] 8.1 Add "Model" column to throughput report
    - File: `src/multimodal_librarian/services/status_report_service.py`
    - In `generate_throughput_report`, add "Model" column after "KG" column in the header
    - Read `quality_gate` from `job_metadata` for each row
    - Format as `"2%/5%"` (composite/threshold) when data available
    - Format as `"⚠ 35%/5% (FAIL)"` when `passed=False`
    - Display `"—"` when `quality_gate` key is absent
    - _Requirements: 7.1, 7.2, 7.4_
  - [x] 8.2 Add "Model Fail %" column to enrichment report
    - File: `src/multimodal_librarian/services/status_report_service.py`
    - In `generate_enrichment_report`, join `processing_jobs.job_metadata` to get quality gate data
    - Add "Model Fail %" column showing composite rate as percentage
    - Show `"FAILED (QG)"` in State column when quality gate failed
    - Display `"—"` when data unavailable
    - _Requirements: 6.1, 6.2, 6.3_
  - [x] 8.3 Add model failure substage row to active jobs report
    - File: `src/multimodal_librarian/services/status_report_service.py`
    - In `format_human_summary`, when KG task is running and metadata contains failure data, add substage row `"↳ Model 3%/5%"` using the in-memory progress metadata
    - _Requirements: 7.3_
  - [ ]* 8.4 Write property test for report warning indicator
    - **Property 10: Report warning indicator for threshold breach** — for any quality gate data where `passed=False`, formatted Model column contains `"⚠"` or `"(FAIL)"`; when `passed=True`, it does not
    - **Validates: Requirements 7.2**

- [x] 9. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Implement frontend model failure breakdown popup
  - [x] 10.1 Create popup component JavaScript
    - Create file: `src/multimodal_librarian/static/js/model-failure-popup.js`
    - Implement a lightweight popup bubble anchored to the composite rate value in the throughput report table
    - Popup content: NER (spaCy) rate with counts, LLM (Ollama) rate with counts, Bridges (Ollama→Gemini) rate with counts, weighting formula line
    - Dismissible via click-outside or Escape key
    - Fetch breakdown data from `job_metadata.quality_gate` via existing API
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_
  - [x] 10.2 Add popup CSS styles
    - File: `src/multimodal_librarian/static/css/` (add to existing stylesheet or create `model-failure-popup.css`)
    - Style the popup bubble with positioning, border, shadow, and dismiss behavior
    - _Requirements: 8.5_
  - [x] 10.3 Wire popup to throughput report table
    - Add click handler to the "Model" column values in the throughput report
    - Attach `data-document-id` attribute to clickable cells for data lookup
    - Include the new JS/CSS files in the relevant HTML template
    - _Requirements: 8.1_

- [x] 11. Implement UI error propagation via progress tile
  - [x] 11.1 Ensure quality gate failures propagate to progress tile
    - Verify that `notify_processing_failure_sync` is called with the quality gate error message in `finalize_processing_task` (from task 7.1)
    - Verify the progress tile displays `status-failed` CSS class and the error reason including composite rate and threshold
    - If the existing WebSocket notification path doesn't carry the error message to the progress tile, wire it through
    - _Requirements: 5.1, 5.2, 5.3_

- [x] 12. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- The design uses Python throughout — all implementation is in Python (backend) and vanilla JS (frontend popup)
- `batch_generate_bridges` currently returns only `List[BridgeChunk]`; task 5.1 changes it to return a tuple, so `generate_bridges_for_document` (task 5.2) and `generate_bridges_task` (task 5.3) must be updated in sequence
- `extract_concepts_with_ner` and `extract_concepts_ollama` signature changes (tasks 4.1–4.2) require updating all callers in `kg_builder.py` (tasks 4.3–4.4) before the celery service changes (tasks 4.5–4.6)
