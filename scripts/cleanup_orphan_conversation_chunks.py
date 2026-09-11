#!/usr/bin/env python3
"""
Remove orphaned conversation chunks from the vector store.

When a conversation is deleted, its vectors should be cleaned up from Milvus.
If the cleanup fails (timeout, connection error, or pre-dates the cleanup code),
orphaned chunks remain and can surface in semantic search results as non-existent
"sources."

This script:
1. Queries Postgres for all active conversation source_ids (knowledge_sources)
2. Queries Milvus for all conversation-typed chunks
3. Deletes chunks whose source_id is missing from Postgres

Usage:
    python scripts/cleanup_orphan_conversation_chunks.py          # check + dry-run
    python scripts/cleanup_orphan_conversation_chunks.py --commit # actually delete
"""

import argparse
import asyncio
import os
import sys
from typing import Dict, List, Set

# Add src to path so we can import project modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


async def get_active_conversation_source_ids() -> Set[str]:
    """
    Return the set of source_ids for all active (non-archived) conversation threads.

    source_id = uuid.uuid5(uuid.NAMESPACE_URL, thread_id)
    """
    import asyncpg
    import uuid as uuid_module

    pg_host = os.environ.get("POSTGRES_HOST", "postgres")
    pg_port = int(os.environ.get("POSTGRES_PORT", "5432"))
    pg_user = os.environ.get("POSTGRES_USER", "postgres")
    pg_password = os.environ.get("POSTGRES_PASSWORD", "postgres")
    pg_db = os.environ.get("POSTGRES_DB", "multimodal_librarian")

    conn = await asyncpg.connect(
        host=pg_host, port=pg_port, user=pg_user,
        password=pg_password, database=pg_db,
    )
    try:
        rows = await conn.fetch(
            "SELECT id FROM multimodal_librarian.conversation_threads "
            "WHERE is_archived = FALSE"
        )
        ids = {
            str(uuid_module.uuid5(uuid_module.NAMESPACE_URL, str(r["id"])))
            for r in rows
        }
        print(f"Postgres: {len(rows)} active threads → {len(ids)} UUID5 source_ids")
        return ids
    finally:
        await conn.close()


async def get_conversation_chunks_from_milvus() -> Dict[str, List[dict]]:
    """
    Return all conversation-typed chunks from Milvus, keyed by source_id.

    Uses the pyMilvus ORM (Collection.query) through the Docker-internal
    host.  Run this inside the app container or set env vars for your host.
    """
    from pymilvus import Collection, connections, utility

    host = os.environ.get("MILVUS_HOST", "localhost")
    port = os.environ.get("MILVUS_PORT", "19530")
    collection_name = os.environ.get("MILVUS_COLLECTION_NAME", "knowledge_chunks")
    alias = "cleanup_orphans"

    loop = asyncio.get_event_loop()

    await loop.run_in_executor(
        None, lambda: connections.connect(alias=alias, host=host, port=port, timeout=30)
    )
    try:
        has = await loop.run_in_executor(
            None, lambda: utility.has_collection(collection_name, using=alias)
        )
        if not has:
            print(f"Collection '{collection_name}' not found")
            return {}

        col = await loop.run_in_executor(
            None, lambda: Collection(collection_name, using=alias)
        )
        await loop.run_in_executor(None, col.load)

        # The Milvus query API has limits on how many results it returns in a
        # single call. Use offset/limit pagination with the newer iterator API
        # or a simple offset-based loop.
        expr = 'metadata["source_type"] == "conversation"'
        offset = 0
        limit = 1000
        all_rows: Dict[str, List[dict]] = {}

        while True:
            rows = await loop.run_in_executor(
                None,
                lambda: col.query(
                    expr=expr,
                    output_fields=["id", "metadata"],
                    offset=offset,
                    limit=limit,
                ),
            )
            if not rows:
                break
            for r in rows:
                meta = r.get("metadata", {})
                if not isinstance(meta, dict):
                    continue
                sid = meta.get("source_id", "")
                if sid:
                    all_rows.setdefault(sid, []).append(r)
            offset += limit
            print(f"  scanned {offset} conversation chunks...", end="\r")

        total = sum(len(v) for v in all_rows.values())
        print(f"\nMilvus: {total} conversation chunks across {len(all_rows)} source_ids")
        return all_rows
    finally:
        await loop.run_in_executor(None, connections.disconnect, alias)


async def delete_orphans(orphan_source_ids: Set[str], commit: bool) -> int:
    """Delete all chunks belonging to orphan source_ids from Milvus."""
    if not orphan_source_ids:
        return 0

    from pymilvus import Collection, connections, utility

    host = os.environ.get("MILVUS_HOST", "localhost")
    port = os.environ.get("MILVUS_PORT", "19530")
    collection_name = os.environ.get("MILVUS_COLLECTION_NAME", "knowledge_chunks")
    alias = "cleanup_orphans_del"

    loop = asyncio.get_event_loop()
    total_deleted = 0

    await loop.run_in_executor(
        None, lambda: connections.connect(alias=alias, host=host, port=port, timeout=30)
    )
    try:
        col = await loop.run_in_executor(
            None, lambda: Collection(collection_name, using=alias)
        )
        await loop.run_in_executor(None, col.load)

        for sid in sorted(orphan_source_ids):
            expr = f'metadata["source_id"] == "{sid}"'
            if commit:
                mut = await loop.run_in_executor(None, col.delete, expr)
                deleted = mut.delete_count if hasattr(mut, "delete_count") else 0
            else:
                # Dry-run: count how many match
                rows = await loop.run_in_executor(
                    None,
                    lambda: col.query(
                        expr=expr,
                        output_fields=["id"],
                        limit=10000,
                    ),
                )
                deleted = len(rows) if rows else 0
            total_deleted += deleted
            print(f"  {'[DRY RUN] would delete' if not commit else 'Deleted'} "
                  f"{deleted:5d} chunks for source_id={sid}")

    finally:
        await loop.run_in_executor(None, connections.disconnect, alias)

    return total_deleted


async def main():
    parser = argparse.ArgumentParser(description="Clean up orphaned conversation chunks")
    parser.add_argument("--commit", action="store_true", help="Actually delete (default: dry-run)")
    args = parser.parse_args()

    if not args.commit:
        print("=== DRY RUN (use --commit to actually delete) ===\n")

    # 1. Get active conversation sources from Postgres
    active_ids = await get_active_conversation_source_ids()

    # 2. Get all conversation chunks from Milvus
    milvus_chunks = await get_conversation_chunks_from_milvus()

    # 3. Identify orphans
    orphan_ids = set(milvus_chunks.keys()) - active_ids
    orphan_count = sum(len(milvus_chunks[sid]) for sid in orphan_ids)

    print(f"\nOrphans: {orphan_count} chunks from {len(orphan_ids)} deleted conversations")

    if not orphan_ids:
        print("No orphaned conversation chunks found.")
        return

    for sid in sorted(orphan_ids):
        chunk_ids = [r["id"] for r in milvus_chunks[sid]]
        print(f"  source_id={sid}: {len(chunk_ids)} chunks")
        for cid in chunk_ids[:3]:
            print(f"    - {cid}")
        if len(chunk_ids) > 3:
            print(f"    ... and {len(chunk_ids) - 3} more")

    # 4. Delete orphans
    total = await delete_orphans(orphan_ids, commit=args.commit)
    action = "Deleted" if args.commit else "[DRY RUN] Would delete"
    print(f"\n{action} {total} orphaned chunks from {len(orphan_ids)} sources")


if __name__ == "__main__":
    asyncio.run(main())
