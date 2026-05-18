## Purpose

During embedding generation, the progress display shows "page 236/89" — the current page number exceeds the total page count. This is confusing to users even though processing is correct.

## Requirements

### Requirement: Expected Behavior: Bug: Page Progress Display Shows Current Page Exceeding Total Pages

The system SHALL The page progress indicator should never show current page exceeding total pages. Options:
1. Cap `current_page` at `total_pages`
2. Use physical page index (0-based position in PDF) instead of logical page number
3. Don't display page progress during embedding stage (it's chunk-based anyway)

#### Scenario: Bug: Page Progress Display Shows Current Page Exceeding Total Pages

- **THEN** The page progress indicator should never show current page exceeding total pages. Options:
1. Cap `current_page` at `total_pages`
2. Use physical page index (0-based position in PDF) instead of logica

### Requirement: Expected Behavior: Bug: Page Progress Display Shows Current Page Exceeding Total Pages (Part 2)

The system SHALL Completion should always show the same final state (e.g., always "done" or always "100%").

#### Scenario: Bug: Page Progress Display Shows Current Page Exceeding Total Pages

- **THEN** Completion should always show the same final state (e.g., always "done" or always "100%").
