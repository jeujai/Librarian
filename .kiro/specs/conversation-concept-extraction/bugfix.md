# Bugfix Requirements Document

## Introduction

When a conversation is created and messages are added, concepts are not extracted from the conversation content and stored in the knowledge graph. Searching for terms that appear in conversation messages (e.g., "team") returns "No matching concepts found." The concept extraction pipeline (`ConversationKnowledgeService.convert_conversation`) exists and functions correctly, but it is never automatically triggered when conversation content changes. It is only invoked via an explicit `POST /{thread_id}/convert-to-knowledge` call, which the `chat.js` `clearChat()` fires as a fire-and-forget request — but the `unified_interface.js` `clearChat()` does not, and no other conversation lifecycle event triggers it either.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a new conversation is created via `POST /api/v1/conversations/start` with an initial message THEN the system stores the conversation thread but does not extract or store any concepts from the message content in the knowledge graph

1.2 WHEN messages are added to a conversation via `POST /api/v1/conversations/{thread_id}/messages` THEN the system processes and stores the messages but does not trigger concept extraction, leaving the knowledge graph empty for that conversation's content

1.3 WHEN a user clears the chat via `unified_interface.js` `clearChat()` THEN the system starts a new conversation without converting the previous conversation to knowledge (no call to `/convert-to-knowledge`), so concepts from that conversation are never extracted

1.4 WHEN a user searches for concepts that exist only in conversation content (e.g., searching "team" after a conversation mentioning "team") THEN the system returns "No matching concepts found" because concept extraction was never triggered

### Expected Behavior (Correct)

2.1 WHEN a new conversation is created and messages are added THEN the system SHALL trigger the concept extraction pipeline (`convert_conversation`) so that concepts from the conversation content are extracted and stored in the knowledge graph

2.2 WHEN messages are added to an existing conversation THEN the system SHALL ensure that concept extraction is triggered (either immediately or upon conversation completion) so that the knowledge graph reflects the conversation's content

2.3 WHEN a user clears the chat or ends a conversation through any UI path (including `unified_interface.js`) THEN the system SHALL trigger the conversion pipeline for the outgoing conversation, consistent with the `chat.js` behavior

2.4 WHEN a user searches for concepts that appear in conversation content THEN the system SHALL return matching concepts from the knowledge graph, provided the conversation has been processed through the extraction pipeline

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a conversation is explicitly converted via `POST /api/conversations/{thread_id}/convert-to-knowledge` THEN the system SHALL CONTINUE TO run the full pipeline (chunk → embed → store → KG extract) and return a `ConvertToKnowledgeResponse` with accurate counts

3.2 WHEN `chat.js` `clearChat()` is invoked on a conversation with messages THEN the system SHALL CONTINUE TO fire the `_convertCurrentConversation()` call as a fire-and-forget request

3.3 WHEN a conversation has no messages THEN the system SHALL CONTINUE TO skip concept extraction and return zero counts without errors

3.4 WHEN the same conversation is converted multiple times (re-ingestion) THEN the system SHALL CONTINUE TO clean up existing data first and produce an idempotent result with no duplicate concepts or vectors

3.5 WHEN documents (non-conversation knowledge sources) are processed THEN the system SHALL CONTINUE TO extract and store concepts through the existing document processing pipeline without interference from conversation concept extraction changes
