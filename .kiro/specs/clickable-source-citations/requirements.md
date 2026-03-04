# Requirements Document

## Introduction

This feature enhances the chat interface to make source citations interactive. Currently, when the RAG system returns responses with citations (e.g., "[Source 1]", "[Source 2]"), users can see a list of sources with document titles and relevance scores, but cannot view the actual chunk content that was used as context. This feature adds clickable citations that display popup excerpts showing the relevant chunk text, enabling users to verify and explore the source material directly from the chat interface.

## Glossary

- **Citation_Popup**: A dismissible overlay component that displays chunk excerpt details when a source citation is clicked
- **Chunk_Excerpt**: The actual text content from a knowledge chunk that was used as context for generating a response
- **Source_Citation**: A reference in the response text (e.g., "[Source 1]") or in the sources list that links to a specific knowledge chunk
- **Citation_Service**: Backend service responsible for retrieving chunk content by chunk ID
- **Sources_List**: The list of sources displayed below a chat response showing document titles and relevance scores

## Requirements

### Requirement 1: Clickable Source Citations in Response Text

**User Story:** As a user, I want to click on source citations in the response text, so that I can see the actual content that was used to generate the response.

#### Acceptance Criteria

1. WHEN a response contains inline citations (e.g., "[Source 1]"), THE Chat_Interface SHALL render them as clickable elements
2. WHEN a user clicks an inline citation, THE Citation_Popup SHALL display showing the chunk excerpt and metadata
3. WHEN rendering inline citations, THE Chat_Interface SHALL visually distinguish them from regular text using styling (color, underline, cursor)
4. IF a citation references a source that is not available, THEN THE Chat_Interface SHALL display an error message in the popup

### Requirement 2: Clickable Sources List

**User Story:** As a user, I want to click on items in the sources list below responses, so that I can view the full chunk content for any source.

#### Acceptance Criteria

1. WHEN sources are displayed in the Sources_List, THE Chat_Interface SHALL render each source as a clickable element
2. WHEN a user clicks a source in the Sources_List, THE Citation_Popup SHALL display with the same information as inline citation clicks
3. WHEN hovering over a source in the Sources_List, THE Chat_Interface SHALL provide visual feedback indicating it is clickable

### Requirement 3: Citation Popup Display

**User Story:** As a user, I want to see comprehensive source information in the popup, so that I can understand the context and relevance of each citation.

#### Acceptance Criteria

1. WHEN the Citation_Popup is displayed, THE Citation_Popup SHALL show the document title
2. WHEN the Citation_Popup is displayed, THE Citation_Popup SHALL show the relevance score as a percentage
3. WHEN the Citation_Popup is displayed, THE Citation_Popup SHALL show the chunk excerpt text
4. WHERE page number information is available, THE Citation_Popup SHALL display the page number or location reference
5. WHERE section title information is available, THE Citation_Popup SHALL display the section title
6. WHEN the chunk excerpt exceeds 500 characters, THE Citation_Popup SHALL truncate with an ellipsis and "show more" option

### Requirement 4: Popup Dismissal

**User Story:** As a user, I want multiple ways to close the citation popup, so that I can easily return to the conversation.

#### Acceptance Criteria

1. WHEN a user clicks outside the Citation_Popup, THE Citation_Popup SHALL close
2. WHEN a user presses the Escape key, THE Citation_Popup SHALL close
3. WHEN a user clicks the close button, THE Citation_Popup SHALL close
4. WHEN the Citation_Popup closes, THE Chat_Interface SHALL return focus to the previously focused element

### Requirement 5: Chunk Content Retrieval

**User Story:** As a developer, I want chunk content included in the API response, so that the frontend can display excerpts without additional API calls.

#### Acceptance Criteria

1. WHEN the RAG service returns citations, THE Citation_Service SHALL include the chunk content (excerpt) in the citation data
2. WHEN streaming responses begin, THE WebSocket_Handler SHALL send citation data including chunk excerpts in the streaming_start message
3. IF chunk content retrieval fails, THEN THE Citation_Service SHALL return an error indicator with the citation
4. WHEN returning chunk excerpts, THE Citation_Service SHALL limit excerpt length to 1000 characters maximum

### Requirement 6: Accessibility

**User Story:** As a user with accessibility needs, I want the citation popups to be fully accessible, so that I can use them with assistive technologies.

#### Acceptance Criteria

1. WHEN the Citation_Popup is displayed, THE Citation_Popup SHALL have appropriate ARIA attributes (role="dialog", aria-modal="true", aria-labelledby)
2. WHEN the Citation_Popup opens, THE Citation_Popup SHALL trap focus within the popup until dismissed
3. WHEN inline citations are rendered, THE Chat_Interface SHALL include aria-label describing the citation
4. WHEN the Citation_Popup closes, THE Chat_Interface SHALL restore focus to the element that triggered it
5. THE Citation_Popup SHALL be navigable using keyboard only (Tab, Shift+Tab, Enter, Escape)

### Requirement 7: Visual Design Integration

**User Story:** As a user, I want the citation popups to match the existing chat interface design, so that the experience feels cohesive.

#### Acceptance Criteria

1. THE Citation_Popup SHALL use the same color palette and typography as the existing chat interface
2. THE Citation_Popup SHALL include smooth open/close animations consistent with existing modals
3. WHEN displayed on mobile devices, THE Citation_Popup SHALL be responsive and readable
4. THE Citation_Popup SHALL have a maximum width of 500px and position itself to avoid viewport overflow
