#!/usr/bin/env python3
"""
Backfill kg_extraction_failures for a run that predates per-source tracking.

The OLD KG code (before per-source failure tracking) logged a whole-chunk
failure as::

    KG extraction failed for chunk N: CancelledError:

where ``N`` is ``batch_start + i`` — the 0-based position of the chunk in the
``chunks`` array of the document's processing payload, NOT a UUID.  This
script maps those positions back to chunk UUIDs and inserts a durable failure
row for each of the four concept sources (ner / llm / umls / gerund), so the
normal ``recover_kg_failures_task`` can re-run them.

Why all four sources?  The old ``extract_all_concepts_async`` used
``asyncio.gather`` without ``return_exceptions=True``, so a single transient
CancelledError from one source cancelled its three siblings too.  Every source
was lost for that chunk, so all four are marked failed for re-run.

Prerequisites
-------------
1. The index->UUID mapping must be captured BEFORE ``finalize_processing_task``
   deletes the processing payload.  It was captured with::

       docker compose exec -T postgres psql -U postgres -d multimodal_librarian \
           -A -t -F $'\\t' -c \\
           "SELECT (ordinality - 1) AS idx, elem->>'id' AS chunk_id \\
            FROM multimodal_librarian.processing_payloads, \\
                 LATERAL jsonb_array_elements(payload->'chunks') \\
                 WITH ORDINALITY AS t(elem, ordinality) \\
            WHERE document_id = '<doc-id>' ORDER BY ordinality;" \\
           > .kg_failure_backfill/<doc>-chunk_order.tsv

2. Run this script (on the host, where docker + venv/bin/python + psycopg2 and
   a Postgres port-forward are available).  It greps the celery-worker logs for
   the failure lines, or you can pass a pre-extracted index list with
   ``--failure-indices-file``.

Usage
-----
    venv/bin/python scripts/backfill_kg_extraction_failures.py \\
        --document-id 6e244851-81bf-4d01-b1f9-7b8bb1f99a5a \\
        --mapping-file .kg_failure_backfill/goldman_chunk_order.tsv \\
        --dry-run
"""

import argparse
import subprocess
import sys

import psycopg2

SOURCES = ("ner", "llm", "umls", "gerund")

PG_DSN = "host=localhost port=5432 dbname=multimodal_librarian user=postgres password=postgres"

_FAILURE_RE_MSG = "KG extraction failed for chunk "


def read_mapping(path):
    """Return {position: chunk_uuid} from an ``idx<TAB>uuid`` file."""
    mapping = {}
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            idx, uuid = line.split("\t", 1)
            mapping[int(idx)] = uuid.strip()
    return mapping


def extract_indices_from_logs():
    """Run ``docker compose logs`` and return the set of failed chunk positions."""
    cmd = [
        "docker", "compose", "logs", "celery-worker",
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    except subprocess.CalledProcessError as e:
        print(f"ERROR: docker compose logs failed: {e}", file=sys.stderr)
        raise

    indices = set()
    for line in out.splitlines():
        marker = _FAILURE_RE_MSG
        pos = line.find(marker)
        if pos == -1:
            continue
        tail = line[pos + len(marker):]
        # tail is "<int>: <exc>: <msg>"
        num = tail.split(":", 1)[0].strip()
        if num.isdigit():
            indices.add(int(num))
    return indices


def read_indices_file(path):
    indices = set()
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line.isdigit():
                indices.add(int(line))
    return indices


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--document-id", required=True)
    ap.add_argument("--mapping-file", required=True)
    ap.add_argument("--failure-indices-file", default=None,
                    help="optional pre-extracted list of integer positions "
                         "(one per line); skips docker compose logs")
    ap.add_argument("--pg-dsn", default=PG_DSN)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    mapping = read_mapping(args.mapping_file)
    print(f"mapping file: {len(mapping)} entries", file=sys.stderr)

    if args.failure_indices_file:
        indices = read_indices_file(args.failure_indices_file)
        print(f"failure indices from file: {len(indices)}", file=sys.stderr)
    else:
        indices = extract_indices_from_logs()
        print(f"failure indices from logs: {len(indices)}", file=sys.stderr)

    missing = sorted(i for i in indices if i not in mapping)
    if missing:
        print(f"WARNING: {len(missing)} indices not in mapping "
              f"(range {missing[0]}..{missing[-1]}); skipped", file=sys.stderr)

    chunk_ids = sorted({mapping[i] for i in indices if i in mapping})
    print(f"failed chunk UUIDs: {len(chunk_ids)}", file=sys.stderr)

    if not chunk_ids:
        print("nothing to backfill", file=sys.stderr)
        return 0

    conn = psycopg2.connect(args.pg_dsn)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            # Keep only chunk IDs that actually exist in knowledge_chunks, so
            # the FK constraint is never violated.
            cur.execute(
                """
                SELECT id::text
                FROM multimodal_librarian.knowledge_chunks
                WHERE source_id = %s::uuid
                  AND id = ANY(%s::uuid[])
                """,
                (args.document_id, chunk_ids),
            )
            valid = {row[0] for row in cur.fetchall()}
            print(f"chunk UUIDs present in knowledge_chunks: {len(valid)}",
                  file=sys.stderr)

            rows = [
                (args.document_id, cid, src)
                for cid in chunk_ids
                if cid in valid
                for src in SOURCES
            ]
            print(f"rows to insert: {len(rows)}", file=sys.stderr)

            if args.dry_run:
                print(f"DRY RUN — would insert {len(rows)} rows "
                      f"({len(valid)} chunks x {len(SOURCES)} sources)",
                      file=sys.stderr)
                return 0

            cur.executemany(
                """
                INSERT INTO multimodal_librarian.kg_extraction_failures
                    (document_id, chunk_id, source, error_type, error_message)
                VALUES (%s::uuid, %s::uuid, %s, 'backfill', 'pre-per-source run')
                ON CONFLICT (document_id, chunk_id, source) DO NOTHING
                """,
                rows,
            )
            conn.commit()
            print(f"inserted {cur.rowcount} failure rows "
                  f"for {len(valid)} chunks", file=sys.stderr)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
