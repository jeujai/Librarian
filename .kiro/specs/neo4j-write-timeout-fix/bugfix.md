# Bugfix Requirements Document

## Introduction

During document upload/processing, the `_update_knowledge_graph` function triggers Neo4j transaction timeouts. The root cause is a combination of: (1) no retry logic on write operations in `Neo4jClient._run_write_session`, unlike the read path which retries 3 times with exponential backoff; (2) large UNWIND MERGE batch sizes (up to 500 rows) that exceed the server-side transaction timeout (120s default, 30s optimized); (3) UMLS bridging (`UMLSBridger.create_same_as_edges()`) running a full graph scan on every document upload, adding timeout risk that grows with dataset size; and (4) failed batches silently losing their concepts/relationships with no retry mechanism.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a write operation (UNWIND MERGE) encounters a `TransientError` (e.g., transaction timeout) THEN the system fails immediately with no retry, unlike `_run_query_session` which retries 3 times with exponential backoff

1.2 WHEN a large UNWIND MERGE batch (up to 500 rows via `_CONCEPT_REL_SUB_BATCH`) is executed against a Neo4j instance with UMLS data loaded THEN the system exceeds the server-side `dbms.transaction.timeout` (120s or 30s) because MERGE operations are slower with more nodes/indexes to check

1.3 WHEN a batch MERGE operation fails in `_update_knowledge_graph` THEN the system logs a warning and continues, permanently losing the concepts and relationships from that batch with no retry attempt

1.4 WHEN `_update_knowledge_graph` completes and UMLS linker is available THEN the system runs `UMLSBridger.create_same_as_edges()` which fetches ALL Concept nodes and ALL UMLSConcept nodes for matching — an O(N×M) operation that grows with every document uploaded and the UMLS dataset size, adding further timeout risk

1.5 WHEN `execute_write_query` is called THEN the system does not enforce any client-side timeout, relying entirely on the server-side `dbms.transaction.timeout` setting which may be too short for large batches

### Expected Behavior (Correct)

2.1 WHEN a write operation encounters a `TransientError` THEN the system SHALL retry up to 3 times with exponential backoff, matching the retry behavior already implemented in `_run_query_session`

2.2 WHEN UNWIND MERGE batches are constructed for knowledge graph persistence THEN the system SHALL use smaller sub-batch sizes (e.g., 100 rows instead of 500) to ensure individual transactions complete within the server-side timeout

2.3 WHEN a batch MERGE operation fails in `_update_knowledge_graph` THEN the system SHALL retry the failed sub-batch (up to 3 attempts with backoff) before logging a warning and moving on, to avoid permanent data loss

2.4 WHEN `_update_knowledge_graph` completes THEN the system SHALL run UMLS bridging incrementally for only the newly created concepts from the current document, rather than scanning all Concept and UMLSConcept nodes in the graph

2.5 WHEN `execute_write_query` is called THEN the system SHALL enforce a configurable client-side timeout to prevent indefinite hangs independent of the server-side setting

### Unchanged Behavior (Regression Prevention)

3.1 WHEN read operations encounter a `TransientError` THEN the system SHALL CONTINUE TO retry up to 3 times with exponential backoff via `_run_query_session`

3.2 WHEN a write operation succeeds on the first attempt THEN the system SHALL CONTINUE TO return results immediately without unnecessary delays

3.3 WHEN `_update_knowledge_graph` processes chunks THEN the system SHALL CONTINUE TO extract concepts, generate embeddings, and persist them incrementally in batches

3.4 WHEN a document is deleted mid-processing THEN the system SHALL CONTINUE TO detect the deletion and abort KG processing gracefully

3.5 WHEN UMLS linker is not available THEN the system SHALL CONTINUE TO skip UMLS linking and bridging without errors

3.6 WHEN TCP transport is closed during a write operation THEN the system SHALL CONTINUE TO reconnect and retry via `_execute_write_with_reconnect`
