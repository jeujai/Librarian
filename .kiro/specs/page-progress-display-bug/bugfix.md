# Bug: Page Progress Display Shows Current Page Exceeding Total Pages

## Summary

During embedding generation, the progress display shows "page 236/89" — the current page number exceeds the total page count. This is confusing to users even though processing is correct.

## Root Cause

The `current_page` value comes from `chunk.metadata.page_number`, which reflects the PDF's internal page numbering (e.g., journal page numbers like 195–236). The `total_pages` value comes from `fitz.Document.page_count`, which is the physical page count of the PDF file (e.g., 89 pages). For journal articles and excerpted documents, these numbering schemes don't align.

## Affected Code

- `src/multimodal_librarian/services/celery_service.py` — `_store_embeddings_in_vector_db()` around line 2020
- `src/multimodal_librarian/services/celery_service.py` — `_store_chunks_in_database()` around line 3949

Both functions extract `max_page` from `chunk.metadata.page_number` and report it alongside `total_pages` from PDF metadata.

## Expected Behavior

The page progress indicator should never show current page exceeding total pages. Options:
1. Cap `current_page` at `total_pages`
2. Use physical page index (0-based position in PDF) instead of logical page number
3. Don't display page progress during embedding stage (it's chunk-based anyway)

## Bug 2: Completion Status Shows "100%" or "done" Inconsistently

### Summary

When a document finishes processing, the UI alternately shows "100%" or "done" as the final status. The display depends on which WebSocket message the frontend renders last.

### Root Cause

The backend sends two separate signals at completion:
1. A progress update with `progress: 100.0` and step "Processing completed successfully"
2. A WebSocket completion message with `type: 'processing_complete'`

The UI renders whichever arrives last, creating inconsistent display.

### Expected Behavior

Completion should always show the same final state (e.g., always "done" or always "100%").

## Impact

Display-only bugs. Processing is correct. No data loss or corruption.
