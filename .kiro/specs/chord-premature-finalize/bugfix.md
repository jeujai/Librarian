# Bugfix Requirements Document

## Introduction

When processing large documents, the Celery chord that orchestrates parallel tasks (bridge generation + knowledge graph extraction) fires its callback (`finalize_processing_task`) prematurely. This happens because duplicate task invocations — caused by Celery visibility timeout redelivery — produce a `skipped_duplicate` result that the chord counts as a valid completion. The finalize callback then runs with missing KG data, marking the document as COMPLETED even though knowledge graph extraction never finished. This results in documents with incomplete knowledge graphs being silently accepted by the quality gate (which sees zero chunks and passes).

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a parallel task (e.g., `generate_bridges_task`) is redelivered by Celery due to visibility timeout and the `redis_task_lock` decorator returns `{'status': 'skipped_duplicate'}`, THEN the chord counts the `skipped_duplicate` result as a valid task completion, potentially firing the callback before the original (real) task invocation finishes.

1.2 WHEN `finalize_processing_task` receives `parallel_results` containing one or more `skipped_duplicate` entries, THEN it logs a warning but continues to mark the document as COMPLETED without verifying that real results were produced by both parallel tasks.

1.3 WHEN the chord fires prematurely due to a `skipped_duplicate` result and the KG task has not yet completed, THEN the quality gate evaluates with `kg_failures` defaulting to `{'ner_failures': 0, 'llm_failures': 0, 'total_chunks': 0}` (zero chunks), which trivially passes the quality threshold.

1.4 WHEN a duplicate task invocation returns `skipped_duplicate`, THEN the Celery result backend stores two results for the same task ID — the `skipped_duplicate` and eventually the real result — causing the chord's internal completion counter to be corrupted.

### Expected Behavior (Correct)

2.1 WHEN a parallel task detects a duplicate invocation via `redis_task_lock`, THEN the duplicate invocation SHALL NOT store a result that the chord can count toward completion — it should either raise `Ignore()` to suppress the result, or use `task_id` replacement so the chord only tracks the original invocation.

2.2 WHEN `finalize_processing_task` receives `parallel_results`, THEN it SHALL validate that every parallel task result contains real completion data (i.e., `status` is `'completed'` or `'aborted'` for deleted documents, and NOT `'skipped_duplicate'`) before proceeding with document finalization.

2.3 WHEN `finalize_processing_task` detects that any parallel result is `skipped_duplicate` or missing expected data (e.g., no `kg_failures` key from the KG task, no `bridge_failures` key from the bridge task), THEN it SHALL mark the document as FAILED with a descriptive error message indicating incomplete parallel processing.

2.4 WHEN the quality gate evaluates `kg_failures` with `total_chunks: 0`, THEN the system SHALL treat this as an invalid/incomplete result rather than a trivially passing score, unless the document genuinely has zero chunks.

### Unchanged Behavior (Regression Prevention)

3.1 WHEN both parallel tasks (`generate_bridges_task` and `update_knowledge_graph_task`) complete successfully with real results and no duplicate invocations occur, THEN the system SHALL CONTINUE TO fire the chord callback and finalize the document normally.

3.2 WHEN a parallel task completes with `status: 'aborted'` because the document was deleted during processing, THEN the system SHALL CONTINUE TO handle the abort gracefully in `finalize_processing_task`.

3.3 WHEN bridge generation fails with an exception but KG completes successfully, THEN the system SHALL CONTINUE TO handle the bridge failure according to existing error handling (bridges are non-fatal).

3.4 WHEN no duplicate task redelivery occurs (normal single-invocation flow), THEN the `redis_task_lock` decorator SHALL CONTINUE TO acquire the lock, execute the task, and release the lock without affecting chord behavior.

3.5 WHEN the quality gate evaluates a document with genuine non-zero `kg_failures` and `bridge_failures` data, THEN the system SHALL CONTINUE TO compute the composite failure rate and apply the content-type-specific threshold correctly.
