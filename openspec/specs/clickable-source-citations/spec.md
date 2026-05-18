## Purpose

This feature enhances the chat interface to make source citations interactive. Currently, when the RAG system returns responses with citations (e.g., "[Source 1]", "[Source 2]"), users can see a list of sources with document titles and relevance scores, but cannot view the actual chunk content that was used as context. This feature adds clickable citations that display popup excerpts showing the relevant chunk text, enabling users to verify and explore the source material directly from the chat interface.


### Key Terms
- **Citation_Popup**: A dismissible overlay component that displays chunk excerpt details when a source citation is clicked
- **Chunk_Excerpt**: The actual text content from a knowledge chunk that was used as context for generating a response
- **Source_Citation**: A reference in the response text (e.g., "[Source 1]") or in the sources list that links to a specific knowledge chunk
- **Citation_Service**: Backend service responsible for retrieving chunk content by chunk ID
- **Sources_List**: The list of sources displayed below a chat response showing document titles and relevance scores

## Requirements

### Requirement: Clickable Source Citations in Response Text

The system SHALL support: As a user, I want to click on source citations in the response text, so that I can see the actual content that was used to generate the response.

#### Scenario: WHEN a response contains inline citations (e.g., "[Source 1]

- **THEN** WHEN a response contains inline citations (e.g., "[Source 1]"), THE Chat_Interface SHALL render them as clickable elements

#### Scenario: WHEN a user clicks an inline citation, THE Citation_Popup SH

- **THEN** WHEN a user clicks an inline citation, THE Citation_Popup SHALL display showing the chunk excerpt and metadata

#### Scenario: WHEN rendering inline citations, THE Chat_Interface SHALL vi

- **THEN** WHEN rendering inline citations, THE Chat_Interface SHALL visually distinguish them from regular text using styling (color, underline, cursor)

#### Scenario: IF a citation references a source that is not available, THE

- **GIVEN** a citation references a source that is not available
- **THEN** IF a citation references a source that is not available, THEN THE Chat_Interface SHALL display an error message in the popup

### Requirement: Clickable Sources List

The system SHALL support: As a user, I want to click on items in the sources list below responses, so that I can view the full chunk content for any source.

#### Scenario: WHEN sources are displayed in the Sources_List, THE Chat_Int

- **THEN** WHEN sources are displayed in the Sources_List, THE Chat_Interface SHALL render each source as a clickable element

#### Scenario: WHEN a user clicks a source in the Sources_List, THE Citatio

- **THEN** WHEN a user clicks a source in the Sources_List, THE Citation_Popup SHALL display with the same information as inline citation clicks

#### Scenario: WHEN hovering over a source in the Sources_List, THE Chat_In

- **THEN** WHEN hovering over a source in the Sources_List, THE Chat_Interface SHALL provide visual feedback indicating it is clickable

### Requirement: Citation Popup Display

The system SHALL support: As a user, I want to see comprehensive source information in the popup, so that I can understand the context and relevance of each citation.

#### Scenario: WHEN the Citation_Popup is displayed, THE Citation_Popup SHA

- **THEN** WHEN the Citation_Popup is displayed, THE Citation_Popup SHALL show the document title

#### Scenario: WHEN the Citation_Popup is displayed, THE Citation_Popup SHA

- **THEN** WHEN the Citation_Popup is displayed, THE Citation_Popup SHALL show the relevance score as a percentage

#### Scenario: WHEN the Citation_Popup is displayed, THE Citation_Popup SHA

- **THEN** WHEN the Citation_Popup is displayed, THE Citation_Popup SHALL show the chunk excerpt text

#### Scenario: WHERE page number information is available, THE Citation_Pop

- **THEN** WHERE page number information is available, THE Citation_Popup SHALL display the page number or location reference

#### Scenario: WHERE section title information is available, THE Citation_P

- **THEN** WHERE section title information is available, THE Citation_Popup SHALL display the section title

#### Scenario: WHEN the chunk excerpt exceeds 500 characters, THE Citation_

- **THEN** WHEN the chunk excerpt exceeds 500 characters, THE Citation_Popup SHALL truncate with an ellipsis and "show more" option

### Requirement: Popup Dismissal

The system SHALL support: As a user, I want multiple ways to close the citation popup, so that I can easily return to the conversation.

#### Scenario: WHEN a user clicks outside the Citation_Popup, THE Citation_

- **THEN** WHEN a user clicks outside the Citation_Popup, THE Citation_Popup SHALL close

#### Scenario: WHEN a user presses the Escape key, THE Citation_Popup SHALL

- **THEN** WHEN a user presses the Escape key, THE Citation_Popup SHALL close

#### Scenario: WHEN a user clicks the close button, THE Citation_Popup SHAL

- **THEN** WHEN a user clicks the close button, THE Citation_Popup SHALL close

#### Scenario: WHEN the Citation_Popup closes, THE Chat_Interface SHALL ret

- **THEN** WHEN the Citation_Popup closes, THE Chat_Interface SHALL return focus to the previously focused element

### Requirement: Chunk Content Retrieval

The system SHALL support: As a developer, I want chunk content included in the API response, so that the frontend can display excerpts without additional API calls.

#### Scenario: WHEN the RAG service returns citations, THE Citation_Service

- **THEN** WHEN the RAG service returns citations, THE Citation_Service SHALL include the chunk content (excerpt) in the citation data

#### Scenario: WHEN streaming responses begin, THE WebSocket_Handler SHALL

- **THEN** WHEN streaming responses begin, THE WebSocket_Handler SHALL send citation data including chunk excerpts in the streaming_start message

#### Scenario: IF chunk content retrieval fails, THEN THE Citation_Service

- **GIVEN** chunk content retrieval fails
- **THEN** IF chunk content retrieval fails, THEN THE Citation_Service SHALL return an error indicator with the citation

#### Scenario: WHEN returning chunk excerpts, THE Citation_Service SHALL li

- **THEN** WHEN returning chunk excerpts, THE Citation_Service SHALL limit excerpt length to 1000 characters maximum

### Requirement: Accessibility

The system SHALL support: As a user with accessibility needs, I want the citation popups to be fully accessible, so that I can use them with assistive technologies.

#### Scenario: WHEN the Citation_Popup is displayed, THE Citation_Popup SHA

- **THEN** WHEN the Citation_Popup is displayed, THE Citation_Popup SHALL have appropriate ARIA attributes (role="dialog", aria-modal="true", aria-labelledby)

#### Scenario: WHEN the Citation_Popup opens, THE Citation_Popup SHALL trap

- **THEN** WHEN the Citation_Popup opens, THE Citation_Popup SHALL trap focus within the popup until dismissed

#### Scenario: WHEN inline citations are rendered, THE Chat_Interface SHALL

- **THEN** WHEN inline citations are rendered, THE Chat_Interface SHALL include aria-label describing the citation

#### Scenario: WHEN the Citation_Popup closes, THE Chat_Interface SHALL res

- **THEN** WHEN the Citation_Popup closes, THE Chat_Interface SHALL restore focus to the element that triggered it

#### Scenario: THE Citation_Popup SHALL be navigable using keyboard only (T

- **THEN** THE Citation_Popup SHALL be navigable using keyboard only (Tab, Shift+Tab, Enter, Escape)

### Requirement: Visual Design Integration

The system SHALL support: As a user, I want the citation popups to match the existing chat interface design, so that the experience feels cohesive.

#### Scenario: THE Citation_Popup SHALL use the same color palette and typo

- **THEN** THE Citation_Popup SHALL use the same color palette and typography as the existing chat interface

#### Scenario: THE Citation_Popup SHALL include smooth open/close animation

- **THEN** THE Citation_Popup SHALL include smooth open/close animations consistent with existing modals

#### Scenario: WHEN displayed on mobile devices, THE Citation_Popup SHALL b

- **THEN** WHEN displayed on mobile devices, THE Citation_Popup SHALL be responsive and readable

#### Scenario: THE Citation_Popup SHALL have a maximum width of 500px and p

- **THEN** THE Citation_Popup SHALL have a maximum width of 500px and position itself to avoid viewport overflow
