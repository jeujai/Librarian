# Implementation Plan: Clickable Source Citations with Popup Excerpts

## Overview

This implementation adds interactive source citations to the chat interface. The work is divided into backend enhancements (ensuring chunk excerpts are included in citation data) and frontend components (popup display, citation rendering, accessibility). The approach prioritizes including excerpt data in the initial WebSocket response to avoid additional API calls.

## Tasks

- [x] 1. Backend: Ensure chunk excerpts are included in citation data
  - [x] 1.1 Verify and enhance CitationSource dataclass in rag_service.py
    - Confirm `excerpt` field is populated during RAG response generation
    - Add `content_truncated` boolean field to indicate truncation
    - Add `excerpt_error` optional field for error states
    - _Requirements: 5.1, 5.3_

  - [x] 1.2 Create truncation utility function
    - Implement `truncate_content(content: str, max_length: int = 1000) -> Tuple[str, bool]`
    - Truncate at word boundaries when possible
    - Return tuple of (truncated_content, was_truncated)
    - Location: `src/multimodal_librarian/utils/text_utils.py`
    - _Requirements: 5.4, 3.6_

  - [ ]* 1.3 Write property test for truncation function
    - **Property 3: Excerpt Truncation Consistency**
    - **Validates: Requirements 3.6, 5.4**

  - [x] 1.4 Update RAG service to populate excerpt field
    - Modify `_search_documents` or `_semantic_search_documents` to include chunk content
    - Apply truncation to excerpts before returning
    - Handle missing content gracefully with error indicator
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 1.5 Update WebSocket handler citation serialization
    - Ensure `excerpt` field is included in streaming_start message
    - Verify chat.py `handle_streaming_rag_response` includes all citation fields
    - _Requirements: 5.2_

- [x] 2. Checkpoint - Backend verification
  - Ensure all backend tests pass
  - Verify citation data includes excerpts by testing with actual chat
  - Ask the user if questions arise

- [x] 3. Frontend: Create Citation Popup Component
  - [x] 3.1 Create CitationPopup class in new file `static/js/citation-popup.js`
    - Implement `show(citationData, triggerElement)` method
    - Implement `hide()` method with cleanup
    - Implement `createPopupElement(citationData)` for DOM structure
    - Implement `position(triggerElement)` for viewport-aware positioning
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 7.4_

  - [ ]* 3.2 Write property test for viewport positioning
    - **Property 7: Viewport Boundary Positioning**
    - **Validates: Requirements 7.4**

  - [x] 3.3 Implement popup dismissal handlers
    - Add click-outside detection with `handleClickOutside(event)`
    - Add Escape key handler with `handleKeydown(event)`
    - Add close button click handler
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 3.4 Implement focus management
    - Add `trapFocus()` method for focus trapping within popup
    - Add `restoreFocus()` method to return focus to trigger
    - Store trigger element reference on open
    - _Requirements: 4.4, 6.2, 6.4_

  - [ ]* 3.5 Write property test for focus management
    - **Property 4: Focus Management Round-Trip**
    - **Validates: Requirements 4.4, 6.4**

  - [x] 3.6 Add accessibility attributes
    - Add role="dialog", aria-modal="true", aria-labelledby
    - Ensure keyboard navigability (Tab, Shift+Tab, Enter, Escape)
    - _Requirements: 6.1, 6.5_

  - [ ]* 3.7 Write property test for accessibility attributes
    - **Property 6: Accessibility Attributes Presence**
    - **Validates: Requirements 6.1, 6.3**

- [x] 4. Frontend: Create Citation Renderer Module
  - [x] 4.1 Create CitationRenderer in `static/js/citation-renderer.js`
    - Implement `findCitationMatches(text)` using regex for "[Source N]" patterns
    - Implement `parseSourceNumber(citationText)` to extract source number
    - Implement `createCitationElement(sourceNumber, citationData)` for clickable spans
    - _Requirements: 1.1, 1.3_

  - [ ]* 4.2 Write property test for citation pattern parsing
    - **Property 1: Citation Pattern Parsing**
    - **Validates: Requirements 1.1, 2.1**

  - [x] 4.3 Implement `renderCitations(text, citations)` method
    - Parse text for citation patterns
    - Replace patterns with clickable elements
    - Attach click handlers to show popup
    - Add aria-label to each citation element
    - _Requirements: 1.1, 1.2, 6.3_

- [x] 5. Frontend: Enhance Sources List
  - [x] 5.1 Modify `addCitationsToElement` in chat.js
    - Make source items clickable with cursor pointer
    - Store citation data on each source element
    - Add click handler to show CitationPopup
    - Add hover state styling
    - _Requirements: 2.1, 2.2, 2.3_

  - [ ]* 5.2 Write property test for inline/sources list consistency
    - **Property 8: Inline and Sources List Consistency**
    - **Validates: Requirements 2.2**

- [x] 6. Frontend: Integrate Components
  - [x] 6.1 Update chat.js to use CitationRenderer for response text
    - Modify `handleStreamingChunk` to use CitationRenderer
    - Pass citations array to renderer
    - Store citations data for popup access
    - _Requirements: 1.1, 1.2_

  - [x] 6.2 Add script includes to index.html
    - Add `<script src="/static/js/citation-popup.js"></script>`
    - Add `<script src="/static/js/citation-renderer.js"></script>`
    - Ensure correct load order (before chat.js)
    - _Requirements: 1.1_

  - [x] 6.3 Initialize CitationPopup instance in ChatApp
    - Create singleton popup instance
    - Wire up to citation click handlers
    - _Requirements: 1.2, 2.2_

- [x] 7. Frontend: Add CSS Styles
  - [x] 7.1 Create citation popup styles in `static/css/citation-popup.css`
    - Style popup container with max-width 500px
    - Style document title, relevance score, excerpt sections
    - Add close button styling
    - Add open/close animations
    - _Requirements: 7.1, 7.2, 7.4_

  - [x] 7.2 Add inline citation styles
    - Style clickable citations with color and underline
    - Add hover state
    - Add focus state for keyboard navigation
    - _Requirements: 1.3_

  - [x] 7.3 Add responsive styles for mobile
    - Full-width popup on small screens
    - Adjust font sizes for readability
    - _Requirements: 7.3_

  - [x] 7.4 Add CSS include to index.html
    - Add `<link rel="stylesheet" href="/static/css/citation-popup.css">`
    - _Requirements: 7.1_

- [x] 8. Checkpoint - Frontend integration verification
  - Ensure all frontend components work together
  - Test popup display from both inline citations and sources list
  - Verify accessibility with keyboard navigation
  - Ask the user if questions arise

- [x] 9. Error Handling and Edge Cases
  - [x] 9.1 Handle missing excerpt data
    - Display "Excerpt not available" message in popup
    - Style error state appropriately
    - _Requirements: 1.4, 5.3_

  - [x] 9.2 Handle invalid citation references
    - Skip rendering invalid patterns as clickable
    - Log warning for debugging
    - _Requirements: 1.4_

  - [ ]* 9.3 Write unit tests for error handling
    - Test missing citation data scenarios
    - Test malformed citation patterns
    - _Requirements: 1.4, 5.3_

- [x] 10. Property Tests for API Data
  - [x]* 10.1 Write property test for citation data completeness
    - **Property 5: Citation Data Completeness in API**
    - **Validates: Requirements 5.1, 5.2**

  - [x]* 10.2 Write property test for popup content completeness
    - **Property 2: Popup Content Completeness**
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

- [x] 11. Final Checkpoint - Full integration testing
  - Ensure all tests pass
  - Test complete flow: send message → receive response with citations → click citation → view popup
  - Verify on both desktop and mobile viewports
  - Ask the user if questions arise

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- The backend already has the `excerpt` field in CitationSource; main work is ensuring it's populated
- Frontend is vanilla JavaScript to match existing codebase (no React/Vue)
- Property tests use Hypothesis (Python) and can use fast-check or custom generators (JavaScript)
- CSS follows existing chat.css patterns for consistency
