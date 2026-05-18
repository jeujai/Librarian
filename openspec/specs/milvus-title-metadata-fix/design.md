# Milvus Title Metadata Fix - Bugfix Design

## Overview

This design addresses the bug where PDF document titles are not consistently stored in Milvus chunk metadata during document processing. The root cause is that the `_extract_pdf_content_async` function in `celery_service.py` retrieves the title from PostgreSQL's `knowledge_sources.title` column, but this value can be `None` or empty when users don't provide a title during upload. The fix will validate titles at the point of extraction and fall back to filename-based titles before storage, eliminating the need for the runtime `_enrich_chunks_with_titles()` workaround in RAG service.

## Glossary

- **Bug_Condition (C)**: The condition where a document's title is `None`, empty string (`''`), or whitespace-only when retrieved from PostgreSQL during PDF content extraction
- **Property (P)**: The desired behavior where all chunks stored in Milvus have a valid, non-empty document title in their metadata
- **Preservation**: Existing behavior for documents with valid titles, chunk storage, and search functionality must remain unchanged
- **`_extract_pdf_content_async`**: The async function in `celery_service.py` that extracts PDF content and metadata, including the document title
- **`_enrich_chunks_with_titles`**: The workaround method in `rag_service.py` that queries PostgreSQL to backfill missing titles at search time
- **`knowledge_sources`**: PostgreSQL table storing document metadata including `title` and `filename` columns

## Bug Details

### Fault Condition

The bug manifests when a document is uploaded without a user-provided title, or when the title stored in PostgreSQL is `None` or an empty string. The `_extract_pdf_content_async` function retrieves this invalid title and propagates it through the chunk serialization pipeline to Milvus storage.

**Formal Specification:**
```
FUNCTION isBugCondition(document_row)
  INPUT: document_row from knowledge_sources table with 'title' and 'filename' fields
  OUTPUT: boolean
  
  title := document_row['title']
  
  RETURN title IS NULL
         OR title = ''
         OR title.strip() = ''
END FUNCTION
```

### Examples

- **Empty string title**: User uploads `research_paper.pdf` without providing a title → PostgreSQL stores `title=''` → Milvus chunks get `title=''` → Chat UI shows "Unknown"
- **None title**: User uploads via API without title field → PostgreSQL stores `title=NULL` → Milvus chunks get `title=None` → Chat UI shows "Unknown"
- **Whitespace-only title**: User provides `"   "` as title → PostgreSQL stores `title='   '` → Milvus chunks get `title='   '` → Chat UI shows "Unknown"
- **Valid title (no bug)**: User provides `"Machine Learning Guide"` → PostgreSQL stores correctly → Milvus chunks get correct title → Chat UI shows "Machine Learning Guide"

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Documents with valid non-empty titles must continue to use those titles in Milvus chunk metadata
- All other chunk metadata fields (`source_id`, `chunk_index`, `chunk_type`, `content_type`, `page_number`) must remain unchanged
- Milvus search functionality must continue to return results with proper similarity scores
- PostgreSQL chunk storage must continue to work correctly
- Batch processing for large PDFs must continue to handle batches correctly

**Scope:**
All inputs where the document has a valid, non-empty title should be completely unaffected by this fix. This includes:
- Documents uploaded with user-provided titles
- Documents where the title was set programmatically
- All existing documents with valid titles already in the system

## Hypothesized Root Cause

Based on the code analysis, the root cause is in `_extract_pdf_content_async` (celery_service.py, lines 831-895):

1. **Insufficient Title Validation**: Line 848 retrieves the title with a simple fallback:
   ```python
   user_document_title = row['title'] or 'Unknown Document'
   ```
   This only handles `None` but not empty strings or whitespace-only strings.

2. **Missing Filename Fallback**: The function has access to the document's filename via the `metadata` column (which contains `s3_key`), but doesn't use it as a fallback for invalid titles.

3. **No Validation at Serialization**: The `generate_chunks_task` (lines 907-1020) blindly propagates whatever title it receives without validation.

4. **Workaround Masks the Issue**: The `_enrich_chunks_with_titles` method in RAG service queries PostgreSQL at search time to fix missing titles, but this adds latency and doesn't fix the root cause.

## Correctness Properties

Property 1: Fault Condition - Invalid Titles Replaced with Filename

_For any_ document where the title is `None`, empty string, or whitespace-only (isBugCondition returns true), the fixed `_extract_pdf_content_async` function SHALL use the document's filename (without extension) as the title before storing in Milvus chunk metadata.

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Preservation - Valid Titles Unchanged

_For any_ document where the title is a valid non-empty string (isBugCondition returns false), the fixed code SHALL produce exactly the same behavior as the original code, preserving the user-provided title in all chunk metadata.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `src/multimodal_librarian/services/celery_service.py`

**Function**: `_extract_pdf_content_async`

**Specific Changes**:

1. **Add Title Validation Helper Function**: Create a helper function `_get_valid_document_title(title: Optional[str], filename: Optional[str]) -> str` that:
   - Returns the title if it's a valid non-empty string (after stripping whitespace)
   - Falls back to filename without extension if title is invalid
   - Falls back to "Untitled Document" if both are invalid

2. **Modify Database Query**: Update the query at line 833 to also fetch the `filename` column:
   ```python
   row = await conn.fetchrow("""
       SELECT metadata, title, filename FROM multimodal_librarian.knowledge_sources
       WHERE id = $1::uuid
   """, document_id)
   ```

3. **Apply Title Validation**: Replace line 848:
   ```python
   # Before:
   user_document_title = row['title'] or 'Unknown Document'
   
   # After:
   user_document_title = _get_valid_document_title(row['title'], row['filename'])
   ```

4. **Remove Workaround (Optional Follow-up)**: After the fix is verified, the `_enrich_chunks_with_titles` method in `rag_service.py` can be simplified or removed since titles will be correct at storage time.

5. **Add Logging**: Log when a title fallback is used for debugging and monitoring.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Fault Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that upload documents with various invalid title scenarios and verify the title stored in Milvus chunk metadata. Run these tests on the UNFIXED code to observe failures.

**Test Cases**:
1. **Empty String Title Test**: Upload document with `title=''` → verify Milvus chunks have empty title (will fail on unfixed code)
2. **None Title Test**: Upload document without title field → verify Milvus chunks have None title (will fail on unfixed code)
3. **Whitespace Title Test**: Upload document with `title='   '` → verify Milvus chunks have whitespace title (will fail on unfixed code)
4. **Valid Title Test**: Upload document with `title='Test Document'` → verify Milvus chunks have correct title (should pass)

**Expected Counterexamples**:
- Milvus chunks stored with empty or None titles
- RAG search results showing "Unknown Document" or "Unknown" in citations
- `_enrich_chunks_with_titles` being called to fix missing titles

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL document WHERE isBugCondition(document) DO
  result := _extract_pdf_content_async_fixed(document.id)
  ASSERT result['metadata']['title'] IS NOT NULL
  ASSERT result['metadata']['title'] != ''
  ASSERT result['metadata']['title'].strip() != ''
  ASSERT result['metadata']['title'] = _derive_title_from_filename(document.filename)
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL document WHERE NOT isBugCondition(document) DO
  ASSERT _extract_pdf_content_async_original(document.id)['metadata']['title'] 
         = _extract_pdf_content_async_fixed(document.id)['metadata']['title']
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for documents with valid titles, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Valid Title Preservation**: Verify documents with valid titles continue to use those titles after fix
2. **Metadata Preservation**: Verify all other metadata fields remain unchanged after fix
3. **Search Preservation**: Verify Milvus search results are identical for documents with valid titles

### Unit Tests

- Test `_get_valid_document_title` helper with various inputs (None, empty, whitespace, valid)
- Test title extraction with mocked database rows
- Test chunk serialization with validated titles
- Test edge cases (filename with multiple dots, no extension, special characters)

### Property-Based Tests

- Generate random document metadata with various title/filename combinations
- Verify title validation always produces non-empty result
- Verify valid titles are never modified
- Test filename-to-title conversion across many filenames

### Integration Tests

- End-to-end test: upload document without title → verify Milvus chunks have filename-based title
- End-to-end test: upload document with valid title → verify Milvus chunks have user-provided title
- Test RAG search returns correct titles without calling `_enrich_chunks_with_titles`
- Test chat UI displays correct document titles in citations
