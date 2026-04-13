# Bugfix Requirements Document

## Introduction

Deleting a document that is currently being processed by Celery does not reliably cancel the associated Celery task. The task continues running in the background after the document has been deleted. This is caused by a combination of four issues: a race condition on the nullable `task_id` column, swallowed cancellation errors, CASCADE deletion destroying the `processing_jobs` record before revocation can be retried, and no verification that the revoked task actually stopped.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a document is deleted before the Celery worker has written the `task_id` to the `processing_jobs` table THEN the system silently returns `False` from `cancel_job()` because `task_id` is `None`, and the Celery task continues running uninterrupted.

1.2 WHEN `cancel_processing()` raises an exception (e.g., Celery broker unreachable, revoke timeout) THEN the system swallows the error in a bare `try/except: pass` block in `delete_document_completely()`, proceeds with deletion, and the task is orphaned with no record of the failed cancellation.

1.3 WHEN the `knowledge_sources` row is deleted THEN the `processing_jobs` row (containing the `task_id`) is CASCADE-deleted, making it impossible to retry revocation later since the task identifier is permanently lost.

1.4 WHEN `celery_app.control.revoke()` is called with `terminate=True` THEN the system does not verify whether the task actually stopped, so a task that ignores SIGTERM continues processing a now-deleted document.

### Expected Behavior (Correct)

2.1 WHEN a document is deleted before the `task_id` is written to `processing_jobs` THEN the system SHALL ensure the task is still cancelled, either by waiting for the `task_id` to become available or by marking the document as pending-cancellation so the task self-terminates when it checks for deletion.

2.2 WHEN `cancel_processing()` raises an exception THEN the system SHALL propagate or log the error and SHALL NOT proceed with document deletion until cancellation has been confirmed or the failure has been recorded for retry.

2.3 WHEN a document with an active processing job is deleted THEN the system SHALL revoke the Celery task BEFORE deleting the `processing_jobs` row, ensuring the `task_id` is available for cancellation and potential retry.

2.4 WHEN `revoke()` is called on a Celery task THEN the system SHALL verify that the task has actually stopped (or is in a terminal state) before considering cancellation complete, using either task state polling or the existing `_check_document_deleted()` mechanism to ensure the task self-terminates.

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a document with no active processing job is deleted THEN the system SHALL CONTINUE TO delete the document and all associated data (Milvus vectors, Neo4j nodes, MinIO files, PostgreSQL rows) successfully.

3.2 WHEN a document is deleted and the Celery task has already completed THEN the system SHALL CONTINUE TO delete the document without errors, treating the completed task as a no-op for cancellation.

3.3 WHEN a document is deleted and the Celery task is successfully revoked on the first attempt THEN the system SHALL CONTINUE TO complete the full deletion flow (Milvus, Neo4j, MinIO, PostgreSQL) as it does today.

3.4 WHEN the `_check_document_deleted()` helper is called by a running Celery task and the document still exists THEN the system SHALL CONTINUE TO allow the task to proceed normally without interruption.

3.5 WHEN a non-processing document (e.g., a conversation document) is deleted THEN the system SHALL CONTINUE TO archive the conversation thread and delete the knowledge source row with CASCADE behavior as it does today.
