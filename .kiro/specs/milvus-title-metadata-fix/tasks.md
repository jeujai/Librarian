# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Fault Condition** - Invalid Title Storage in Milvus
  - **IMPORTANT**: Write this property-based test BEFORE implementing the fix
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: Scope the property to concrete failing cases where title is None, empty string (''), or whitespace-only ('   ')
  - Test that `_extract_pdf_content_async` with invalid titles (None, '', '   ') stores invalid titles in chunk metadata
  - Bug condition from design: `isBugCondition(document_row)` returns true when `title IS NULL OR title = '' OR title.strip() = ''`
  - Expected behavior: chunks should have valid non-empty title derived from filename
  - Create test file at `tests/components/test_milvus_title_metadata_bug.py`
  - Mock database row with invalid title scenarios and valid filename
  - Run test on UNFIXED code - expect FAILURE (this confirms the bug exists)
  - Document counterexamples found (e.g., "chunks stored with empty title instead of filename-based title")
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Valid Title Behavior Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - **IMPORTANT**: Write these tests BEFORE implementing the fix
  - Observe: Documents with valid non-empty titles (e.g., "Machine Learning Guide") store that exact title in Milvus chunks
  - Observe: All other metadata fields (source_id, chunk_index, chunk_type, content_type, page_number) are stored correctly
  - Write property-based test: for all documents where title is valid non-empty string, the title in chunk metadata equals the user-provided title
  - Test that valid titles like "Research Paper", "User Guide 2024", "Report_v2" are preserved exactly
  - Add test cases to `tests/components/test_milvus_title_metadata_bug.py`
  - Verify test passes on UNFIXED code (confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 3. Fix for invalid document titles not stored correctly in Milvus chunk metadata

  - [x] 3.1 Add `_get_valid_document_title` helper function
    - Create helper function in `src/multimodal_librarian/services/celery_service.py`
    - Function signature: `def _get_valid_document_title(title: Optional[str], filename: Optional[str]) -> str`
    - Return title if it's a valid non-empty string (after stripping whitespace)
    - Fall back to filename without extension if title is invalid
    - Fall back to "Untitled Document" if both title and filename are invalid
    - Handle edge cases: filename with multiple dots, no extension, special characters
    - Add logging when fallback is used for debugging
    - _Bug_Condition: isBugCondition(document_row) where title IS NULL OR title = '' OR title.strip() = ''_
    - _Expected_Behavior: Return valid non-empty title string, preferring user title, then filename, then default_
    - _Preservation: Valid non-empty titles are returned unchanged_
    - _Requirements: 2.1, 2.2, 2.3, 3.1_

  - [x] 3.2 Modify database query to fetch filename column
    - Update query in `_extract_pdf_content_async` function (around line 833)
    - Change from: `SELECT metadata, title FROM multimodal_librarian.knowledge_sources WHERE id = $1::uuid`
    - Change to: `SELECT metadata, title, filename FROM multimodal_librarian.knowledge_sources WHERE id = $1::uuid`
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 3.3 Apply title validation in `_extract_pdf_content_async`
    - Replace line 848: `user_document_title = row['title'] or 'Unknown Document'`
    - With: `user_document_title = _get_valid_document_title(row['title'], row['filename'])`
    - Ensure the validated title propagates to all chunk metadata
    - _Bug_Condition: isBugCondition(document_row) where title IS NULL OR title = '' OR title.strip() = ''_
    - _Expected_Behavior: Chunks stored with valid title from _get_valid_document_title_
    - _Preservation: Documents with valid titles continue to use those titles_
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.1_

  - [x] 3.4 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Invalid Title Storage in Milvus
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 3.5 Verify preservation tests still pass
    - **Property 2: Preservation** - Valid Title Behavior Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all tests still pass after fix (no regressions)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 4. Checkpoint - Ensure all tests pass
  - Run full test suite to ensure no regressions
  - Verify bug condition exploration test passes (confirms fix works)
  - Verify preservation tests pass (confirms no regressions)
  - Ensure all tests pass, ask the user if questions arise
