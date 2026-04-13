# Incremental Bridge Storage Bugfix Design

## Overview

This design addresses a critical bug in the `generate_bridges_task` Celery task where all bridge chunks are generated first (potentially taking 6+ hours for large documents), then stored in Milvus in a single operation at the end. If the Milvus storage fails (e.g., gRPC connection timeout), all bridge generation work is lost.

The fix implements incremental storage of bridges as they are generated in batches, ensuring that previously-stored bridges are preserved even if a later storage operation fails.

## Glossary

- **Bug_Condition (C)**: The condition where bridge storage is attempted only after ALL bridges are generated, causing total data loss on storage failure
- **Property (P)**: The desired behavior where bridges are stored incrementally in batches as they are generated
- **Preservation**: Existing behavior for documents requiring no bridges, successful completions, and PostgreSQL storage logic
- **generate_bridges_task**: The Celery task in `celery_service.py` that generates and stores bridge chunks
- **batch_generate_bridges**: The method in `SmartBridgeGenerator` that processes bridges in batches of 60
- **_store_bridge_embeddings_in_vector_db**: The async function that stores bridge embeddings in Milvus
- **_store_bridge_chunks_in_database**: The async function that stores bridge metadata in PostgreSQL

## Bug Details

### Bug Condition

The bug manifests when a large document requires many bridges (potentially hundreds) and the Milvus storage operation fails after all bridges have been generated. The current implementation generates ALL bridges first, then attempts to store ALL of them in a single Milvus `insert_vectors()` operation.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type BridgeGenerationContext
  OUTPUT: boolean
  
  RETURN input.bridges_needed > 0
         AND input.all_bridges_generated = true
         AND input.milvus_storage_attempted = true
         AND input.milvus_storage_failed = true
         AND input.bridges_stored_before_failure = 0
END FUNCTION
```

### Examples

- **Large document (200 bridges)**: After 6 hours of generation, Milvus times out → ALL 200 bridges lost, must regenerate from scratch
- **Medium document (50 bridges)**: After 1 hour of generation, gRPC connection drops → ALL 50 bridges lost
- **Network hiccup during storage**: Even a brief network issue causes total loss of all generated bridges
- **Successful case (no bug)**: Small document with 10 bridges, storage succeeds → All bridges stored correctly

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Documents requiring no bridges (`bridge_needed: false`) must continue to return early with `bridges_generated: 0`
- Successful completion must continue to return `{'status': 'completed'}` with accurate bridge counts
- Document deletion detection via `_check_document_deleted()` must continue to abort gracefully
- Bridge generation failures (not storage) must continue to return `{'status': 'failed'}`
- PostgreSQL storage via `_store_bridge_chunks_in_database()` must continue to use existing logic
- Embedding generation must continue to use the model server client with batch processing

**Scope:**
All inputs that do NOT involve Milvus storage failures should be completely unaffected by this fix. This includes:
- Documents with no bridges needed
- Successful bridge generation and storage
- Bridge generation failures (LLM errors, etc.)
- Document deletion during processing

## Hypothesized Root Cause

Based on the bug description and code analysis, the root cause is the architectural decision to:

1. **Batch-then-Store Pattern**: The `generate_bridges_task` calls `chunking_framework.generate_bridges_for_document()` which generates ALL bridges via `batch_generate_bridges()`, then stores ALL bridges at once via `_store_bridge_embeddings_in_vector_db()`.

2. **No Incremental Storage Hook**: The `batch_generate_bridges()` method in `SmartBridgeGenerator` processes bridges in batches of 60 internally, but only returns the complete list of bridges after ALL batches are processed. There's no callback mechanism to store bridges as each batch completes.

3. **Single Storage Call**: The storage functions `_store_bridge_chunks_in_database()` and `_store_bridge_embeddings_in_vector_db()` are called once with ALL bridges, creating a single point of failure.

4. **No Partial Progress Tracking**: There's no mechanism to track which bridges have been successfully stored, making it impossible to resume from a partial failure.

## Correctness Properties

Property 1: Bug Condition - Incremental Bridge Storage

_For any_ bridge generation context where bridges are generated in batches, the fixed `generate_bridges_task` SHALL store each batch of bridges in both PostgreSQL and Milvus immediately after that batch is generated, before proceeding to generate the next batch.

**Validates: Requirements 2.1, 2.2**

Property 2: Preservation - Partial Failure Recovery

_For any_ Milvus storage failure that occurs after some batches have been successfully stored, the fixed code SHALL preserve all previously-stored bridges and only lose the current batch (not all bridges).

**Validates: Requirements 2.3, 2.4**

Property 3: Preservation - Non-Bridge Document Behavior

_For any_ document that requires no bridges (bridge_needed: false), the fixed code SHALL produce exactly the same behavior as the original code, returning early with `bridges_generated: 0`.

**Validates: Requirements 3.1**

Property 4: Preservation - Successful Completion Behavior

_For any_ document where all bridges are generated and stored successfully, the fixed code SHALL produce exactly the same result as the original code, returning `{'status': 'completed'}` with accurate counts.

**Validates: Requirements 3.2**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `src/multimodal_librarian/services/celery_service.py`

**Function**: `generate_bridges_task`

**Specific Changes**:

1. **Add Incremental Storage Callback**: Modify the `_bridge_progress` callback (or create a new `_bridge_storage_callback`) to store bridges incrementally as each batch completes in `batch_generate_bridges()`.

2. **Modify batch_generate_bridges Interface**: Add an optional `storage_callback` parameter to `batch_generate_bridges()` that is called after each batch of bridges is generated and validated.

3. **Track Stored Bridge Count**: Maintain a counter of successfully stored bridges to enable accurate progress reporting and partial failure recovery.

4. **Handle Partial Storage Failures**: When a Milvus storage operation fails, log the error, preserve the count of successfully stored bridges, and either continue with remaining batches or fail gracefully with partial progress preserved.

5. **Update Progress Reporting**: Report both `bridges_generated` and `bridges_stored` separately to provide accurate visibility into the pipeline state.

**File**: `src/multimodal_librarian/components/chunking_framework/bridge_generator.py`

**Function**: `batch_generate_bridges`

**Specific Changes**:

1. **Add Storage Callback Parameter**: Add an optional `storage_callback: Optional[Callable[[List[BridgeChunk]], None]]` parameter that is invoked after each batch is processed.

2. **Invoke Callback Per Batch**: After each batch of bridges is generated and validated, invoke the storage callback with the batch of bridges.

**File**: `src/multimodal_librarian/components/chunking_framework/framework.py`

**Function**: `generate_bridges_for_document`

**Specific Changes**:

1. **Pass Storage Callback**: Accept and pass through the storage callback to `batch_generate_bridges()`.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that simulate Milvus storage failures after bridge generation and verify that all bridges are lost. Run these tests on the UNFIXED code to observe failures and understand the root cause.

**Test Cases**:
1. **Large Document Storage Failure**: Generate 100+ bridges, simulate Milvus timeout → verify all bridges lost (will fail on unfixed code)
2. **Mid-Batch Storage Failure**: Generate 60 bridges (1 batch), fail on storage → verify all bridges lost (will fail on unfixed code)
3. **Network Error During Storage**: Simulate gRPC connection error → verify all bridges lost (will fail on unfixed code)
4. **Partial Batch Failure**: Generate 120 bridges (2 batches), fail on second batch storage → verify first batch preserved (will fail on unfixed code)

**Expected Counterexamples**:
- All bridges are lost when Milvus storage fails, regardless of how many were generated
- No partial progress is preserved
- Possible causes: single storage call at end, no incremental storage mechanism

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := generate_bridges_task_fixed(input)
  ASSERT bridges_stored_before_failure > 0
  ASSERT bridges_stored_before_failure = (failed_batch_index * batch_size)
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT generate_bridges_task_original(input) = generate_bridges_task_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for successful storage, no-bridge documents, and generation failures, then write property-based tests capturing that behavior.

**Test Cases**:
1. **No Bridges Needed Preservation**: Verify documents with `bridge_needed: false` return early with same result
2. **Successful Storage Preservation**: Verify successful storage produces same final result and counts
3. **Generation Failure Preservation**: Verify LLM generation failures produce same error handling
4. **Document Deletion Preservation**: Verify document deletion detection continues to work

### Unit Tests

- Test incremental storage callback is invoked after each batch
- Test storage failure handling preserves previously stored bridges
- Test progress reporting includes both generated and stored counts
- Test edge cases (single bridge, exactly batch_size bridges, batch_size + 1 bridges)

### Property-Based Tests

- Generate random bridge counts and verify incremental storage is called correct number of times
- Generate random failure points and verify partial progress is preserved
- Test that all non-failure scenarios produce identical results to original code

### Integration Tests

- Test full pipeline with simulated Milvus failures at various points
- Test recovery from partial storage failures
- Test that WebSocket progress updates reflect accurate stored counts
