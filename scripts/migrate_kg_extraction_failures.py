#!/usr/bin/env python3
"""
Add the durable KG-extraction failure table (idempotent).

Creates ``multimodal_librarian.kg_extraction_failures``, the table the KG
pipeline writes to when one of a chunk's four concept-extraction sources
(NER / Ollama / UMLS / gerund) fails (e.g. a transient CancelledError from
the model server / Ollama pool).  Each row tracks a single ``(chunk, source)``
pair, so the recovery task (``recover_kg_failures_task``) can re-run only the
failed source(s) instead of re-running all four for the chunk.

Idempotent: uses ``CREATE TABLE IF NOT EXISTS`` and ``CREATE INDEX IF NOT
EXISTS``, so it is safe to run repeatedly.

Usage (inside the app container, which reaches host=postgres):

    docker compose cp scripts/migrate_kg_extraction_failures.py app:/tmp/migrate_kg_extraction_failures.py
    docker compose exec -T app python /tmp/migrate_kg_extraction_failures.py

Environment:
    PG_DSN   (default: host=postgres dbname=multimodal_librarian user=postgres password=postgres)
"""

import sys

import psycopg2

PG_DSN = "host=postgres dbname=multimodal_librarian user=postgres password=postgres"

_DDL = """
CREATE TABLE IF NOT EXISTS multimodal_librarian.kg_extraction_failures (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES multimodal_librarian.knowledge_sources(id) ON DELETE CASCADE,
    chunk_id UUID NOT NULL REFERENCES multimodal_librarian.knowledge_chunks(id) ON DELETE CASCADE,
    source VARCHAR(50) NOT NULL,
    error_type VARCHAR(255) NOT NULL,
    error_message TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 1,
    resolved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(document_id, chunk_id, source)
);

CREATE INDEX IF NOT EXISTS idx_kg_extraction_failures_unresolved
    ON multimodal_librarian.kg_extraction_failures(document_id)
    WHERE resolved_at IS NULL;
"""


def _table_exists(cur):
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'multimodal_librarian'
              AND table_name = 'kg_extraction_failures'
        )
        """
    )
    return cur.fetchone()[0]


def _has_source_column(cur):
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'multimodal_librarian'
              AND table_name = 'kg_extraction_failures'
              AND column_name = 'source'
        )
        """
    )
    return cur.fetchone()[0]


def main():
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            # Pre-`source` versions of the table tracked only (document_id,
            # chunk_id).  The table holds transient failure rows only (no
            # user data), so if it predates the per-source schema we drop and
            # recreate it rather than attempt an in-place migration of the
            # unique key from (document_id, chunk_id) to
            # (document_id, chunk_id, source).
            if _table_exists(cur) and not _has_source_column(cur):
                cur.execute("DROP TABLE multimodal_librarian.kg_extraction_failures")
                print("dropped pre-source kg_extraction_failures table")
            cur.execute(_DDL)
        print("kg_extraction_failures table + unresolved index ensured")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
