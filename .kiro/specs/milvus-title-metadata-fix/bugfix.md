# Bugfix Requirements Document

## Introduction

Document titles are not consistently stored in Milvus chunk metadata during document processing. This causes the chat UI to display "Unknown" for source citations instead of the actual document title. The root cause is that PDF metadata can contain empty strings or None values for the title field, which are not properly handled before being stored in Milvus. A runtime workaround (`_enrich_chunks_with_titles()`) currently queries PostgreSQL to backfill missing titles, adding unnecessary overhead to every search operation.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a PDF has an empty string (`''`) as its metadata title THEN the system stores the empty string in Milvus chunk metadata instead of a meaningful fallback title

1.2 WHEN a PDF has `None` as its metadata title THEN the system stores `None` in Milvus chunk metadata instead of a meaningful fallback title

1.3 WHEN a PDF's embedded metadata title field is missing entirely THEN the system stores "Untitled Document" but this is inconsistent with the filename-based title stored in PostgreSQL

1.4 WHEN chunks with missing/empty titles are retrieved from Milvus THEN the system must perform an additional PostgreSQL query via `_enrich_chunks_with_titles()` to display proper citations

### Expected Behavior (Correct)

2.1 WHEN a PDF has an empty string (`''`) as its metadata title THEN the system SHALL use the document's filename (without extension) as the title before storing in Milvus

2.2 WHEN a PDF has `None` as its metadata title THEN the system SHALL use the document's filename (without extension) as the title before storing in Milvus

2.3 WHEN a PDF's embedded metadata title field is missing entirely THEN the system SHALL use the document's filename (without extension) as the title, consistent with PostgreSQL storage

2.4 WHEN chunks are retrieved from Milvus THEN the system SHALL return the correct document title from metadata without requiring additional PostgreSQL queries

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a PDF has a valid non-empty title in its metadata THEN the system SHALL CONTINUE TO use that title in Milvus chunk metadata

3.2 WHEN chunks are stored in Milvus THEN the system SHALL CONTINUE TO include all other metadata fields (source_id, chunk_index, chunk_type, content_type, page_number)

3.3 WHEN searching for chunks in Milvus THEN the system SHALL CONTINUE TO return results with proper similarity scores and metadata

3.4 WHEN storing chunks in PostgreSQL THEN the system SHALL CONTINUE TO store chunks with correct metadata and relationships

3.5 WHEN processing large PDFs with batch processing THEN the system SHALL CONTINUE TO handle batches correctly with proper title propagation
