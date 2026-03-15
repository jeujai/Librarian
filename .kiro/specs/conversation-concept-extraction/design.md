# Conversation Concept Extraction Bugfix Design

## Overview

Concept extraction (`ConversationKnowledgeService.convert_conversation`) is never automatically triggered during conversation lifecycle events. It only runs when explicitly called via the `POST /{thread_id}/convert-to-knowledge` endpoint. The `chat.js` `clearChat()` fires this endpoint as fire-and-forget, but `unified_interface.js` `clearChat()` does not, and no backend lifecycle event (start conversation, add message, delete conversation) triggers it either.

The fix involves two complementary changes:
1. **Backend**: Add a new endpoint that the `start_conversation` endpoint calls (fire-and-forget) to convert the *previous* conversation when a new one starts, and optionally trigger extraction on `add_message` after a configurable message threshold.
2. **Frontend**: Add the missing `_convertCurrentConversation()` call to `unified_interface.js` `clearChat()`, mirroring `chat.js` behavior.

## Glossary

- **Bug_Condition (C)**: A conversation lifecycle event occurs (new chat started, message added, chat cleared via unified_interface.js) but `convert_conversation` is never invoked for the conversation's content.
- **Property (P)**: After a conversation lifecycle event that should trigger extraction, the conversation's concepts are extracted and stored in the knowledge graph.
- **Preservation**: The existing explicit `POST /{thread_id}/convert-to-knowledge` endpoint, `chat.js` fire-and-forget behavior, empty-conversation handling, idempotent re-ingestion, and document processing pipeline must remain unchanged.
- **`convert_conversation`**: The method in `ConversationKnowledgeService` (`conversation_knowledge_service.py`) that runs the full pipeline: cleanup → chunk → embed → store → KG extract.
- **`clearChat()`**: Frontend function that resets the chat UI and starts a new conversation. Exists in both `chat.js` (correct — calls `_convertCurrentConversation`) and `unified_interface.js` (buggy — does not).
- **`conversation_manager`**: The `ConversationManager` component that manages conversation threads, messages, and state.

## Bug Details

### Bug Condition

The bug manifests when a conversation has messages and a lifecycle event occurs (new conversation started, chat cleared, messages added) but concept extraction is never triggered. The `convert_conversation` pipeline exists and works correctly, but no code path invokes it automatically.

**Formal Specification:**
```
FUNCTION isBugCondition(event)
  INPUT: event of type ConversationLifecycleEvent
  OUTPUT: boolean

  RETURN (
    (event.type == "clear_chat" AND event.source == "unified_interface.js"
     AND event.previousThread.messageCount > 0)
    OR
    (event.type == "start_conversation" AND event.previousThreadId IS NOT NULL
     AND event.previousThread.messageCount > 0
     AND NOT convertConversationCalled(event.previousThreadId))
    OR
    (event.type == "add_message" AND event.thread.messageCount > 0
     AND NOT convertConversationScheduled(event.threadId))
  )
END FUNCTION
```

### Examples

- User has a conversation with 5 messages in `unified_interface.js`, clicks "New Chat" → `clearChat()` runs but does NOT call `_convertCurrentConversation()` → concepts from those 5 messages are never extracted → searching for terms from that conversation returns "No matching concepts found"
- User starts a new conversation via `POST /api/v1/conversations/start` while a previous conversation with messages exists → the backend does not trigger `convert_conversation` for the previous thread → concepts are lost
- User adds messages to a conversation and never explicitly converts → the knowledge graph never reflects that conversation's content
- User has a conversation with 0 messages and clears chat → no extraction should occur (this is correct behavior, not a bug)

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- The explicit `POST /api/conversations/{thread_id}/convert-to-knowledge` endpoint must continue to work exactly as before, running the full pipeline and returning `ConvertToKnowledgeResponse` with accurate counts
- `chat.js` `clearChat()` must continue to fire `_convertCurrentConversation()` as fire-and-forget
- Conversations with no messages must continue to skip extraction and return zero counts without errors
- Re-ingestion (converting the same conversation multiple times) must continue to clean up existing data first and produce idempotent results
- Document processing pipeline (non-conversation knowledge sources) must remain completely unaffected
- All existing API response models and status codes must remain unchanged

**Scope:**
All inputs that do NOT involve conversation lifecycle events with pending unextracted content should be completely unaffected by this fix. This includes:
- Direct calls to the convert-to-knowledge endpoint
- Document upload and processing
- Search queries (behavior depends on what's in the KG, not on the fix itself)
- Conversation read operations (list, get, history)
- Export operations

## Hypothesized Root Cause

Based on the bug description and code analysis, the root causes are:

1. **Missing frontend call in `unified_interface.js`**: The `clearChat()` method in `unified_interface.js` (line ~963) simply clears the UI and starts a new conversation without calling `_convertCurrentConversation()`. The `chat.js` version (line ~1907) correctly calls it. This is a straightforward omission — the `unified_interface.js` was likely written separately or refactored without porting the conversion logic.

2. **No backend-side automatic trigger**: The `start_conversation` endpoint in `conversations.py` (line 50) creates a new thread but has no awareness of a "previous" thread that should be converted. The `add_message_to_conversation` endpoint (line 161) processes messages but never schedules or triggers concept extraction. The backend relies entirely on the frontend to call the convert endpoint at the right time.

3. **No lifecycle hook architecture**: There is no event/hook system in the conversation lifecycle that could trigger extraction. Each endpoint is self-contained and doesn't coordinate with the knowledge extraction pipeline.

4. **Architectural gap**: The `ConversationKnowledgeService` is only wired as a dependency for the `conversation_knowledge.py` router, not for the `conversations.py` router. The conversations router doesn't import or depend on the knowledge service at all.

## Correctness Properties

Property 1: Bug Condition - Automatic Concept Extraction on Lifecycle Events

_For any_ conversation lifecycle event where a conversation has messages and concept extraction should be triggered (unified_interface.js clearChat, backend start_conversation with previous thread, or message threshold reached), the fixed system SHALL invoke `convert_conversation` for the relevant thread, resulting in concepts being extracted and stored in the knowledge graph.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4**

Property 2: Preservation - Existing Behavior Unchanged

_For any_ input that does NOT involve the newly added automatic extraction triggers (explicit convert-to-knowledge calls, chat.js clearChat, empty conversations, re-ingestion, document processing), the fixed code SHALL produce exactly the same behavior as the original code, preserving all existing functionality including response models, status codes, idempotent cleanup, and pipeline stages.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `src/multimodal_librarian/static/js/unified_interface.js`

**Function**: `clearChat()`

**Specific Changes**:
1. **Add `_convertCurrentConversation()` call**: Before clearing the UI state, check if `this.messageHistory.length > 0 && this.currentThreadId` and fire `_convertCurrentConversation()` as fire-and-forget, mirroring `chat.js` behavior.
2. **Add `_convertCurrentConversation()` method**: Implement the method that calls `POST /api/conversations/{threadId}/convert-to-knowledge` with a generated title, identical to the `chat.js` implementation.

---

**File**: `src/multimodal_librarian/api/routers/conversations.py`

**Function**: `start_conversation()`

**Specific Changes**:
3. **Accept optional `previous_thread_id`**: Add an optional field to `StartConversationRequest` (or as a query param) so the frontend can pass the outgoing thread ID when starting a new conversation.
4. **Fire-and-forget conversion**: When `previous_thread_id` is provided and the previous thread has messages, schedule `convert_conversation` as a FastAPI `BackgroundTask` so it doesn't block the response.
5. **Inject `ConversationKnowledgeService`**: Add `Depends(get_conversation_knowledge_service)` (optional variant) to the endpoint so the service is available for background conversion.

---

**File**: `src/multimodal_librarian/api/routers/conversations.py`

**Function**: `add_message_to_conversation()`

**Specific Changes**:
6. **Optional: Schedule extraction on message threshold**: After adding a message, if the conversation's message count crosses a configurable threshold (e.g., every 10 messages), schedule a background `convert_conversation` call. This ensures long-running conversations get periodic extraction without waiting for chat clear. This is a secondary enhancement and can be deferred.

---

**File**: `src/multimodal_librarian/api/dependencies/services.py`

**Specific Changes**:
7. **Add optional variant**: Create `get_conversation_knowledge_service_optional()` that returns `None` instead of raising 503 when the service can't be initialized, enabling graceful degradation in the conversations router.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that simulate conversation lifecycle events and assert that `convert_conversation` is invoked. Run these tests on the UNFIXED code to observe failures and understand the root cause.

**Test Cases**:
1. **Unified Interface clearChat Test**: Call `unified_interface.js` `clearChat()` with an active conversation that has messages → assert `convert-to-knowledge` endpoint is called (will fail on unfixed code)
2. **Start Conversation with Previous Thread Test**: Call `POST /api/v1/conversations/start` with a `previous_thread_id` that has messages → assert `convert_conversation` is triggered in background (will fail on unfixed code — param doesn't exist yet)
3. **Add Message Extraction Test**: Add messages to a conversation and verify concept extraction is eventually triggered (will fail on unfixed code)
4. **Search After Conversation Test**: Create a conversation with specific terms, clear chat, then search for those terms → assert concepts are found (will fail on unfixed code)

**Expected Counterexamples**:
- `unified_interface.js` `clearChat()` never calls any conversion endpoint
- `start_conversation` endpoint has no knowledge of previous threads
- `add_message_to_conversation` endpoint never triggers extraction
- Possible causes: missing frontend call, no backend lifecycle hooks, no DI wiring for knowledge service in conversations router

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL event WHERE isBugCondition(event) DO
  result := handleLifecycleEvent_fixed(event)
  ASSERT convertConversationCalled(event.relevantThreadId)
  ASSERT knowledgeGraphContainsConcepts(event.relevantThreadId)
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL event WHERE NOT isBugCondition(event) DO
  ASSERT handleLifecycleEvent_original(event) = handleLifecycleEvent_fixed(event)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for explicit convert-to-knowledge calls, empty conversations, and document processing, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Explicit Convert Preservation**: Verify that `POST /{thread_id}/convert-to-knowledge` continues to return the same response model and status codes after the fix
2. **Empty Conversation Preservation**: Verify that conversations with no messages still return zero counts and no errors when converted
3. **Idempotent Re-ingestion Preservation**: Verify that converting the same conversation twice still cleans up and produces idempotent results
4. **Document Pipeline Preservation**: Verify that document upload and processing is completely unaffected by the changes
5. **chat.js clearChat Preservation**: Verify that `chat.js` `clearChat()` still fires `_convertCurrentConversation()` correctly

### Unit Tests

- Test `unified_interface.js` `clearChat()` calls `_convertCurrentConversation()` when conversation has messages
- Test `unified_interface.js` `clearChat()` does NOT call conversion when no messages exist
- Test `start_conversation` endpoint triggers background conversion when `previous_thread_id` is provided
- Test `start_conversation` endpoint does NOT trigger conversion when no previous thread is provided
- Test `add_message_to_conversation` schedules extraction at message threshold (if implemented)
- Test `get_conversation_knowledge_service_optional` returns `None` on initialization failure

### Property-Based Tests

- Generate random conversation states (varying message counts, thread IDs) and verify that lifecycle events with messages always trigger extraction
- Generate random non-lifecycle inputs (search queries, document uploads, read operations) and verify they produce identical results before and after the fix
- Generate random conversation sequences (create → add messages → clear → create) and verify concepts are extracted for each completed conversation

### Integration Tests

- End-to-end test: create conversation → add messages → clear chat via unified_interface path → search for concepts → verify concepts found
- End-to-end test: create conversation → add messages → start new conversation with previous_thread_id → verify background extraction completes
- End-to-end test: verify explicit convert-to-knowledge endpoint still works identically after fix
- End-to-end test: verify document processing pipeline is unaffected
