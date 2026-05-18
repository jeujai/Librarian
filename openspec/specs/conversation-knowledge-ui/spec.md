## Purpose

This feature wires the existing conversation-to-knowledge backend pipeline into the chat UI, establishes lifecycle rules for conversation knowledge documents, and provides a unified Knowledge Graph explorer for all knowledge sources (documents and conversations). Today, the backend pipeline (`ConversationKnowledgeService.convert_conversation()`) and API endpoint (`POST /api/conversations/{thread_id}/convert-to-knowledge`) exist but are never triggered from the UI. The `clearChat()` function simply clears messages and starts a new thread with no knowledge preservation. Additionally, the Knowledge Graph data extracted from both documents and conversations is not surfaced to users in any visual form. This spec covers: automatic conversion on "New Chat" and WebSocket disconnect, conversation knowledge document identity and naming, diary-style reopening of converted conversations, deletion semantics that remove search data while preserving conversation records for audit, and a neighborhood-based KG explorer that applies uniformly to all knowledge sources.


### Key Terms
- **Chat_App**: The main chat UI controller (`static/js/chat.js`, class `ChatApp`) that manages WebSocket communication, message rendering, and conversation lifecycle.
- **Document_List_Panel**: The existing document management panel (`static/js/document-list-panel.js`, class `DocumentListPanel`) that displays uploaded documents with status, stats, and action buttons.
- **Conversation_Knowledge_Document**: A knowledge document created from a conversation thread, stored in the Vector_Store and Knowledge_Graph, with a stable ID tied to the conversation thread_id.
- **Conversion_API**: The existing `POST /api/conversations/{thread_id}/convert-to-knowledge` endpoint that triggers chunking, embedding, Milvus insertion, and Neo4j concept extraction.
- **WebSocket_Manager**: The existing WebSocket client (`WebSocketManager`) used by Chat_App for real-time server communication.
- **Toast_Notification**: A brief, non-blocking UI notification displayed as a banner or toast message to inform the user of background operations.
- **Thread_ID**: The unique identifier for a conversation thread, used as the stable identity link between a conversation and its Conversation_Knowledge_Document.
- **Conversation_Manager**: The existing backend component that manages conversation threads and message persistence in PostgreSQL.
- **KG_Explorer**: A visual, interactive graph viewer that renders a bounded neighborhood of Knowledge_Graph concepts and relationships, allowing users to navigate the graph one hop at a time.
- **Ego_Graph**: A subgraph centered on a focus node, containing all nodes and edges within a fixed hop distance. The KG_Explorer renders ego graphs with a configurable maximum node count.
- **Focus_Node**: The central concept node around which the KG_Explorer renders the current neighborhood. Clicking an edge node shifts the focus to that node.
- **Neighborhood_Query**: A Cypher query that retrieves a bounded set of concepts and relationships around a focus node from Neo4j, limited by a maximum node count.
- **Concept_Node**: A node in the Knowledge_Graph representing an extracted concept, with properties including name, source_document, and source_chunks.
- **Embedding_Model**: The sentence-transformers model used to generate vector embeddings, reused here to embed user search queries for semantic concept matching.

## Requirements

### Requirement: Automatic Conversion on New Chat

The system SHALL support: As a user, I want my current conversation automatically saved to knowledge when I start a new chat, so that I never lose insights from completed conversations.

#### Scenario: WHEN the user clicks the "New Chat" button and the current c

- **THEN** WHEN the user clicks the "New Chat" button and the current conversation has one or more messages, THE Chat_App SHALL call the Conversion_API with the current Thread_ID before clearing the chat.

#### Scenario: WHEN the Conversion_API call is initiated, THE Chat_App SHAL

- **THEN** WHEN the Conversion_API call is initiated, THE Chat_App SHALL immediately clear the chat messages and start a new conversation thread without waiting for the conversion to complete.

#### Scenario: WHEN the Conversion_API call is initiated, THE Chat_App SHAL

- **THEN** WHEN the Conversion_API call is initiated, THE Chat_App SHALL display a Toast_Notification with the text "Saving conversation to knowledge..." and the auto-generated document title.

#### Scenario: WHEN the Conversion_API call completes successfully, THE Cha

- **THEN** WHEN the Conversion_API call completes successfully, THE Chat_App SHALL update the Toast_Notification to indicate success.

#### Scenario: IF the Conversion_API call fails, THEN THE Chat_App SHALL di

- **GIVEN** the Conversion_API call fails
- **THEN** IF the Conversion_API call fails, THEN THE Chat_App SHALL display an error Toast_Notification with a descriptive message.

#### Scenario: WHEN the user clicks the "New Chat" button and the current c

- **THEN** WHEN the user clicks the "New Chat" button and the current conversation has no messages, THE Chat_App SHALL clear the chat and start a new thread without calling the Conversion_API.

### Requirement: Automatic Conversion on WebSocket Disconnect

The system SHALL support: As a user, I want my conversation saved to knowledge when my connection drops, so that no conversation data is lost due to network interruptions.

#### Scenario: WHEN the WebSocket client disconnects and the current conver

- **THEN** WHEN the WebSocket client disconnects and the current conversation has one or more messages, THE Chat_App SHALL call the Conversion_API with the current Thread_ID.

#### Scenario: WHEN the WebSocket client disconnects and the current conver

- **THEN** WHEN the WebSocket client disconnects and the current conversation has no messages, THE Chat_App SHALL take no conversion action.

#### Scenario: IF the Conversion_API call triggered by disconnect fails, TH

- **GIVEN** the Conversion_API call triggered by disconnect fails
- **THEN** IF the Conversion_API call triggered by disconnect fails, THEN THE Chat_App SHALL log the error for diagnostic purposes.

### Requirement: Document Title Auto-Generation

The system SHALL support: As a user, I want my conversation knowledge documents to have meaningful titles derived from the conversation content, so that I can identify them in the document list.

#### Scenario: WHEN a conversation is converted to knowledge, THE Chat_App

- **THEN** WHEN a conversation is converted to knowledge, THE Chat_App SHALL generate a title in the format "Conversation: {first_user_message_truncated} ({date})" where {first_user_message_truncated} is the first user message content truncated to 80 characters and {date} is the current date formatted as "Mon D, YYYY".

#### Scenario: IF the first user message content exceeds 80 characters, THE

- **GIVEN** the first user message content exceeds 80 characters
- **THEN** IF the first user message content exceeds 80 characters, THEN THE Chat_App SHALL truncate the content at 80 characters and append an ellipsis character.

#### Scenario: IF the conversation has no user messages, THEN THE Chat_App

- **GIVEN** the conversation has no user messages
- **THEN** IF the conversation has no user messages, THEN THE Chat_App SHALL use the title "Conversation: (untitled) ({date})".

### Requirement: Conversation Knowledge Document Identity

The system SHALL support: As a user, I want each conversation to map to exactly one knowledge document with a stable identity, so that reopening and updating a conversation always modifies the same document.

#### Scenario: THE system SHALL maintain a one-to-one mapping between a con

- **THEN** THE system SHALL maintain a one-to-one mapping between a conversation Thread_ID and a Conversation_Knowledge_Document ID.

#### Scenario: WHEN a conversation that already has a Conversation_Knowledg

- **THEN** WHEN a conversation that already has a Conversation_Knowledge_Document is converted again, THE Conversion_API SHALL update the existing document in place with refreshed chunks and concepts rather than creating a new document.

#### Scenario: THE Conversation_Knowledge_Document SHALL retain the same do

- **THEN** THE Conversation_Knowledge_Document SHALL retain the same document ID across all updates for a given Thread_ID.

### Requirement: Conversation Documents in Document List

The system SHALL support: As a user, I want to see my conversation knowledge documents in the document list alongside uploaded documents, so that I can manage all my knowledge sources from one place.

#### Scenario: THE Document_List_Panel SHALL display Conversation_Knowledge

- **THEN** THE Document_List_Panel SHALL display Conversation_Knowledge_Documents in the document list alongside uploaded PDF documents.

#### Scenario: THE Document_List_Panel SHALL render Conversation_Knowledge_

- **THEN** THE Document_List_Panel SHALL render Conversation_Knowledge_Documents with a conversation icon (💬) to visually distinguish them from uploaded documents which use the document icon (📄).

#### Scenario: WHEN a Conversation_Knowledge_Document is displayed, THE Doc

- **THEN** WHEN a Conversation_Knowledge_Document is displayed, THE Document_List_Panel SHALL show the auto-generated or user-edited title, the creation date, and the chunk count.

#### Scenario: THE Document_List_Panel SHALL allow the user to edit the tit

- **THEN** THE Document_List_Panel SHALL allow the user to edit the title of a Conversation_Knowledge_Document inline.

### Requirement: Conversation Reopening (Diary-Style)

The system SHALL support: As a user, I want to click a conversation knowledge document to reopen the full conversation in the chat view, so that I can continue the conversation and extend it with new messages.

#### Scenario: WHEN the user clicks a Conversation_Knowledge_Document in th

- **THEN** WHEN the user clicks a Conversation_Knowledge_Document in the Document_List_Panel, THE Chat_App SHALL load the full conversation history from the Conversation_Manager and display the messages in the chat view.

#### Scenario: WHEN a conversation is reopened, THE Chat_App SHALL set the

- **THEN** WHEN a conversation is reopened, THE Chat_App SHALL set the current Thread_ID to the reopened conversation's Thread_ID so that new messages are appended to the existing thread.

#### Scenario: WHEN a conversation is reopened, THE Chat_App SHALL place th

- **THEN** WHEN a conversation is reopened, THE Chat_App SHALL place the message input in an active, writable state so the user can continue the conversation.

#### Scenario: WHEN a reopened conversation is subsequently closed via "New

- **THEN** WHEN a reopened conversation is subsequently closed via "New Chat" or WebSocket disconnect, THE Chat_App SHALL trigger the Conversion_API to update the existing Conversation_Knowledge_Document with the extended conversation content.

#### Scenario: IF the current chat has unsaved messages when the user attem

- **GIVEN** the current chat has unsaved messages when the user attempts to reopen a different conversation
- **THEN** IF the current chat has unsaved messages when the user attempts to reopen a different conversation, THEN THE Chat_App SHALL first convert the current conversation to knowledge before loading the reopened conversation.

### Requirement: Delete Control Disabled for Active Conversations

The system SHALL support: As a user, I want the delete button disabled for a conversation document that is currently open in the chat, so that I cannot accidentally delete a document while actively using its source conversation.

#### Scenario: WHILE a conversation is reopened and active in the Chat_App,

- **THEN** WHILE a conversation is reopened and active in the Chat_App, THE Document_List_Panel SHALL disable the delete button for the corresponding Conversation_Knowledge_Document.

#### Scenario: WHILE the delete button is disabled, THE Document_List_Panel

- **THEN** WHILE the delete button is disabled, THE Document_List_Panel SHALL render the delete button in a greyed-out visual state that is visible but not clickable.

#### Scenario: WHILE the delete button is disabled, THE Document_List_Panel

- **THEN** WHILE the delete button is disabled, THE Document_List_Panel SHALL display a tooltip on the delete button explaining "Cannot delete while conversation is active".

#### Scenario: WHEN the conversation is closed (via "New Chat" or WebSocket

- **THEN** WHEN the conversation is closed (via "New Chat" or WebSocket disconnect), THE Document_List_Panel SHALL re-enable the delete button for the corresponding Conversation_Knowledge_Document.

### Requirement: Knowledge Document Deletion Semantics

The system SHALL support: As a user, I want deleting a conversation knowledge document to remove it from search results while preserving the conversation data for audit, so that deletion is clean but reversible at the data layer.

#### Scenario: WHEN the user deletes a Conversation_Knowledge_Document, THE

- **THEN** WHEN the user deletes a Conversation_Knowledge_Document, THE system SHALL remove the document's chunks from the Vector_Store (Milvus).

#### Scenario: WHEN the user deletes a Conversation_Knowledge_Document, THE

- **THEN** WHEN the user deletes a Conversation_Knowledge_Document, THE system SHALL remove the document's concepts and relationships from the Knowledge_Graph (Neo4j).

#### Scenario: WHEN the user deletes a Conversation_Knowledge_Document, THE

- **THEN** WHEN the user deletes a Conversation_Knowledge_Document, THE system SHALL preserve the original conversation messages in PostgreSQL.

#### Scenario: WHEN a Conversation_Knowledge_Document is deleted, THE Docum

- **THEN** WHEN a Conversation_Knowledge_Document is deleted, THE Document_List_Panel SHALL remove the document from the document list immediately.

#### Scenario: WHEN a Conversation_Knowledge_Document is deleted, THE Chat_

- **THEN** WHEN a Conversation_Knowledge_Document is deleted, THE Chat_App SHALL remove all UI handles to the source conversation so that the conversation is no longer surfaceable through the Librarian interface.

### Requirement: Document Title Editing

The system SHALL support: As a user, I want to rename my conversation knowledge documents, so that I can give them more meaningful titles than the auto-generated ones.

#### Scenario: WHEN the user clicks the title of a Conversation_Knowledge_D

- **THEN** WHEN the user clicks the title of a Conversation_Knowledge_Document in the Document_List_Panel, THE Document_List_Panel SHALL switch the title to an editable text input field.

#### Scenario: WHEN the user confirms the edit (by pressing Enter or clicki

- **THEN** WHEN the user confirms the edit (by pressing Enter or clicking outside the input), THE Document_List_Panel SHALL send the updated title to the server and persist the change.

#### Scenario: IF the user presses Escape while editing, THEN THE Document_

- **GIVEN** the user presses Escape while editing
- **THEN** IF the user presses Escape while editing, THEN THE Document_List_Panel SHALL revert the title to its previous value and exit edit mode.

#### Scenario: IF the user submits an empty title, THEN THE Document_List_P

- **GIVEN** the user submits an empty title
- **THEN** IF the user submits an empty title, THEN THE Document_List_Panel SHALL revert to the previous title and display a validation message.

### Requirement: Conversion Status Feedback

The system SHALL support: As a user, I want clear visual feedback during the conversation-to-knowledge conversion process, so that I know the status of the background operation.

#### Scenario: WHEN a conversion is in progress, THE Chat_App SHALL display

- **THEN** WHEN a conversion is in progress, THE Chat_App SHALL display a Toast_Notification with a loading indicator and the text "Saving conversation to knowledge..." followed by the document title.

#### Scenario: WHEN the conversion completes successfully, THE Chat_App SHA

- **THEN** WHEN the conversion completes successfully, THE Chat_App SHALL update the Toast_Notification to show a success indicator with the text "Conversation saved to knowledge" and the document title.

#### Scenario: IF the conversion fails, THEN THE Chat_App SHALL update the

- **GIVEN** the conversion fails
- **THEN** IF the conversion fails, THEN THE Chat_App SHALL update the Toast_Notification to show an error indicator with the text "Failed to save conversation" and a brief error description.

#### Scenario: THE Toast_Notification SHALL auto-dismiss after 5 seconds fo

- **THEN** THE Toast_Notification SHALL auto-dismiss after 5 seconds for success notifications and remain visible until manually dismissed for error notifications.

### Requirement: KG Explorer — Neighborhood-Based Graph Visualization

The system SHALL support: As a user, I want to visually explore the knowledge graph extracted from my documents and conversations, so that I can discover concepts, relationships, and connections across my knowledge base.

#### Scenario: THE Document_List_Panel SHALL provide a "View Concepts" acti

- **THEN** THE Document_List_Panel SHALL provide a "View Concepts" action on each knowledge source (both uploaded documents and Conversation_Knowledge_Documents) that opens the KG_Explorer for that source.

#### Scenario: WHEN the KG_Explorer is opened for a knowledge source, THE s

- **THEN** WHEN the KG_Explorer is opened for a knowledge source, THE system SHALL query Neo4j for concepts where `source_document` matches the source ID and display a landing view showing the top 10 concepts ranked by degree (number of relationships), allowing the user to select which concept to explore.

#### Scenario: WHEN the user selects a concept from the landing view, THE K

- **THEN** WHEN the user selects a concept from the landing view, THE KG_Explorer SHALL set that concept as the initial Focus_Node and render its neighborhood.

#### Scenario: THE KG_Explorer SHALL render at most 50 Concept_Nodes and th

- **THEN** THE KG_Explorer SHALL render at most 50 Concept_Nodes and their connecting relationships at any given time to maintain browser performance.

#### Scenario: THE KG_Explorer SHALL use a force-directed graph layout (D3.

- **THEN** THE KG_Explorer SHALL use a force-directed graph layout (D3.js or equivalent) to position nodes and edges in the viewport.

#### Scenario: THE KG_Explorer SHALL render Concept_Nodes as labeled circle

- **THEN** THE KG_Explorer SHALL render Concept_Nodes as labeled circles and relationships as labeled directed edges between them.

### Requirement: KG Explorer — Neighborhood Navigation

The system SHALL support: As a user, I want to navigate through the knowledge graph by clicking on edge nodes, so that I can explore beyond the currently visible neighborhood without loading the entire graph.

#### Scenario: WHEN the user clicks a Concept_Node at the edge of the curre

- **THEN** WHEN the user clicks a Concept_Node at the edge of the current neighborhood, THE KG_Explorer SHALL shift the Focus_Node to the clicked node and execute a new Neighborhood_Query centered on it.

#### Scenario: WHEN the neighborhood shifts, THE KG_Explorer SHALL retain n

- **THEN** WHEN the neighborhood shifts, THE KG_Explorer SHALL retain nodes that are still within the new neighborhood (smooth transition) and fade out nodes that are no longer connected.

#### Scenario: WHEN the neighborhood shifts, THE KG_Explorer SHALL fade in

- **THEN** WHEN the neighborhood shifts, THE KG_Explorer SHALL fade in newly visible nodes from the expanded neighborhood.

#### Scenario: THE KG_Explorer SHALL maintain a navigation history stack so

- **THEN** THE KG_Explorer SHALL maintain a navigation history stack so the user can navigate back to previously visited Focus_Nodes using a back button.

#### Scenario: WHEN the user clicks a Concept_Node that is already the Focu

- **THEN** WHEN the user clicks a Concept_Node that is already the Focus_Node, THE KG_Explorer SHALL display a detail panel showing the concept name, source document, related chunks, and relationship count.

### Requirement: KG Explorer — Prompt-Based Filtering

The system SHALL support: As a user, I want to search for specific topics in the knowledge graph using natural language, so that I can jump directly to the relevant neighborhood instead of navigating manually.

#### Scenario: THE KG_Explorer SHALL provide a search input field where the

- **THEN** THE KG_Explorer SHALL provide a search input field where the user can type a natural language query to find relevant concepts.

#### Scenario: WHEN the user submits a search query, THE system SHALL embed

- **THEN** WHEN the user submits a search query, THE system SHALL embed the query using the Embedding_Model and find the most semantically similar Concept_Nodes by comparing against concept name embeddings.

#### Scenario: WHEN matching concepts are found, THE KG_Explorer SHALL set

- **THEN** WHEN matching concepts are found, THE KG_Explorer SHALL set the highest-scoring concept as the Focus_Node and render its neighborhood.

#### Scenario: IF no concepts match the search query above a minimum simila

- **GIVEN** no concepts match the search query above a minimum similarity threshold
- **THEN** IF no concepts match the search query above a minimum similarity threshold, THEN THE KG_Explorer SHALL display a message "No matching concepts found" and retain the current view.

#### Scenario: THE KG_Explorer SHALL display the search results as a ranked

- **THEN** THE KG_Explorer SHALL display the search results as a ranked list of matching concept names, allowing the user to select which concept to focus on if multiple matches exist.

### Requirement: KG Explorer — Cross-Source Exploration

The system SHALL support: As a user, I want the KG explorer to show connections between concepts from different knowledge sources, so that I can discover how my documents and conversations relate to each other.

#### Scenario: WHEN the KG_Explorer renders a neighborhood, THE system SHAL

- **THEN** WHEN the KG_Explorer renders a neighborhood, THE system SHALL include related Concept_Nodes from other knowledge sources if they are connected by relationships in the Knowledge_Graph.

#### Scenario: THE KG_Explorer SHALL visually distinguish Concept_Nodes by

- **THEN** THE KG_Explorer SHALL visually distinguish Concept_Nodes by source type using color coding: one color for document-sourced concepts and another for conversation-sourced concepts.

#### Scenario: THE KG_Explorer SHALL display the source document name as a

- **THEN** THE KG_Explorer SHALL display the source document name as a subtitle on each Concept_Node so the user can identify which knowledge source a concept originated from.

#### Scenario: WHEN the user clicks a cross-source Concept_Node, THE KG_Exp

- **THEN** WHEN the user clicks a cross-source Concept_Node, THE KG_Explorer SHALL navigate to that node's neighborhood, potentially spanning multiple knowledge sources.

### Requirement: KG Explorer — Backend API

The system SHALL support: As a developer, I want API endpoints that serve bounded graph neighborhoods and concept search results, so that the KG_Explorer frontend can query the knowledge graph efficiently.

#### Scenario: THE API SHALL expose a `GET /api/knowledge-graph/{source_id}

- **THEN** THE API SHALL expose a `GET /api/knowledge-graph/{source_id}/neighborhood` endpoint that accepts a `focus_concept` parameter and a `max_nodes` parameter (default 50) and returns the ego graph around the focus concept.

#### Scenario: THE API SHALL expose a `GET /api/knowledge-graph/search` end

- **THEN** THE API SHALL expose a `GET /api/knowledge-graph/search` endpoint that accepts a `query` parameter and an optional `source_id` parameter and returns a ranked list of matching concepts with similarity scores.

#### Scenario: THE neighborhood endpoint SHALL return nodes (concept name,

- **THEN** THE neighborhood endpoint SHALL return nodes (concept name, source_document, degree) and edges (source, target, relationship_type) in a JSON format suitable for D3.js rendering.

#### Scenario: THE search endpoint SHALL return at most 10 matching concept

- **THEN** THE search endpoint SHALL return at most 10 matching concepts, each with concept name, source_document, similarity score, and degree.

#### Scenario: IF the `source_id` parameter is omitted from the search endp

- **GIVEN** the `source_id` parameter is omitted from the search endpoint
- **THEN** IF the `source_id` parameter is omitted from the search endpoint, THEN THE API SHALL search across all knowledge sources.
