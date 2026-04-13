# Bugfix Requirements Document

## Introduction

The `generate_bridges_task` Celery task generates ALL bridge chunks first (which can take 6+ hours for large documents), then attempts to store ALL of them in Milvus at the very end in a single operation. If the Milvus storage fails (e.g., gRPC connection timeout after the long generation phase), all bridge generation work is lost and must be repeated from scratch.

This bug causes significant wasted compute time and poor user experience when processing large documents. The fix requires implementing incremental storage of bridges as they are generated in batches, rather than waiting until all bridges are complete.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN `generate_bridges_task` processes a large document requiring many bridges, THEN the system generates ALL bridges via `chunking_framework.generate_bridges_for_document()` before attempting any storage operations.

1.2 WHEN all bridges have been generated (potentially after 6+ hours), THEN the system calls `_store_bridge_embeddings_in_vector_db()` with ALL bridges at once in a single Milvus `insert_vectors()` operation.

1.3 WHEN the single Milvus storage operation fails (e.g., gRPC connection timeout, `_MultiThreadedRendezvous` error), THEN ALL bridge generation work is lost and the task returns `{'status': 'failed'}`.

1.4 WHEN a storage failure occurs after hours of bridge generation, THEN there is no way to resume from where the task left off — the entire bridge generation must be repeated.

### Expected Behavior (Correct)

2.1 WHEN `generate_bridges_task` generates bridges, THEN the system SHALL store bridges incrementally in batches as they are generated (e.g., every N bridges or after each batch completes).

2.2 WHEN a batch of bridges is successfully generated, THEN the system SHALL immediately store that batch in both PostgreSQL and Milvus before proceeding to generate the next batch.

2.3 WHEN a Milvus storage operation fails for a batch, THEN the system SHALL preserve all previously-stored bridges and only lose the current batch (not all bridges).

2.4 WHEN a storage failure occurs mid-way through bridge generation, THEN the system SHALL be able to resume from the last successfully stored batch (or at minimum, preserve all previously stored bridges).

2.5 WHEN tracking progress, THEN the system SHALL report both bridges generated AND bridges stored to provide accurate progress visibility.

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a document requires no bridges (bridge_generation_data indicates `bridge_needed: false`), THEN the system SHALL CONTINUE TO return early with `bridges_generated: 0` without attempting storage.

3.2 WHEN all bridges are generated and stored successfully, THEN the system SHALL CONTINUE TO return `{'status': 'completed'}` with accurate bridge counts.

3.3 WHEN the document is deleted during bridge generation, THEN the system SHALL CONTINUE TO detect this via `_check_document_deleted()` and abort gracefully.

3.4 WHEN bridge generation fails (not storage), THEN the system SHALL CONTINUE TO return `{'status': 'failed'}` with the error details.

3.5 WHEN storing bridges in PostgreSQL via `_store_bridge_chunks_in_database()`, THEN the system SHALL CONTINUE TO use the existing storage logic (incremental storage applies to the Milvus vector DB operation).

3.6 WHEN generating embeddings for bridges, THEN the system SHALL CONTINUE TO use the model server client with batch embedding generation for performance.
