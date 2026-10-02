#!/usr/bin/env python3
"""
Re-hyphenate stored chunks carrying a whitespace-collapsed soft-wrap artifact.

Chunks stored before the chunker's de-hyphenation fix carry ``word- word`` —
a typeset hyphen collapsed to a space ("andro- gen", "CON- FIRMED", "B- cell").
This folds those in place WITHOUT re-chunking the document:

  * join a true soft-wrap when the merged form is a known word
    ("andro- gen" -> "androgen", "CON- FIRMED" -> "CONFIRMED");
  * otherwise drop the spurious space and keep the hyphen, restoring a
    true compound ("B- cell" -> "B-cell", "enzyme- inducing" ->
    "enzyme-inducing").

The chunk ID is deliberately PRESERVED, so there is no Neo4j / EXTRACTED_FROM
re-link and no ID churn.  Two stores are updated in place:

  1. Postgres ``knowledge_chunks``: ``content`` + ``content_hash``.
  2. Milvus ``knowledge_chunks``: the entity's ``metadata.content`` and its
     re-embedded vector (retrieval reads chunk text from Milvus metadata, not
     Postgres).

Conservative by design: the word-list discriminator never merges a true
compound.  A corpus vocabulary (UMLS + concept names) is added so medical
soft-wraps ("thromboem- bolism" -> "thromboembolism") are also joined.

Modes:
  --dry-run  (default)   scan + report, no writes
  --write                apply the Postgres + Milvus updates

Resumable / idempotent: a chunk that no longer contains the artifact is
skipped on re-run, so an interrupted --write can simply be re-run.

Usage:
  python scripts/rechunk_dehyphenate_chunks.py --dry-run
  python scripts/rechunk_dehyphenate_chunks.py --write --limit 1000
  python scripts/rechunk_dehyphenate_chunks.py --write
"""

import argparse
import hashlib
import os
import re
import sys
import time
from collections import Counter

import httpx
import psycopg2
from neo4j import GraphDatabase
from pymilvus import MilvusClient

from multimodal_librarian.components.chunking_framework.framework import (
    GenericMultiLevelChunkingFramework,
)

# --- defaults (host-visible endpoints; override via env) ---
PG_DSN = os.environ.get(
    "PG_DSN",
    "host=localhost port=5432 dbname=multimodal_librarian user=postgres password=postgres",
)
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "password")
MILVUS_URI = os.environ.get("MILVUS_URI", "http://localhost:19530")
MILVUS_COLLECTION = os.environ.get("MILVUS_COLLECTION", "knowledge_chunks")
MODEL_SERVER_URL = os.environ.get("MODEL_SERVER_URL", "http://localhost:8001")

# Chunks whose content contains "word- word" (any case continuation).
ARTIFACT_RE = r"[A-Za-z]+- [A-Za-z]"


def build_medical_vocab(driver) -> frozenset:
    """Collect single-token medical words from Neo4j (UMLS + concept names)."""
    words = set()
    with driver.session() as s:
        n = 0
        for rec in s.run(
            "MATCH (u:UMLSConcept) WHERE u.lower_name =~ '[a-z]{4,30}' "
            "RETURN u.lower_name AS name"
        ):
            words.add(rec["name"])
            n += 1
        print(f"  UMLSConcept single-token names: {n}")
        n = 0
        for rec in s.run(
            "MATCH (c:Concept) WHERE c.name =~ '[A-Za-z]{4,30}' "
            "RETURN lower(c.name) AS name"
        ):
            words.add(rec["name"])
            n += 1
        print(f"  Concept single-token names: {n}")
    return frozenset(words)


def fetch_target_ids(conn) -> list:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id::text FROM multimodal_librarian.knowledge_chunks "
            f"WHERE content ~ %s ORDER BY id",
            (ARTIFACT_RE,),
        )
        return [r[0] for r in cur.fetchall()]


def fetch_rows(conn, ids) -> dict:
    """Map chunk id -> content for a batch of ids."""
    if not ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id::text, content FROM multimodal_librarian.knowledge_chunks "
            "WHERE id = ANY(%s::uuid[])",
            (ids,),
        )
        return {r[0]: r[1] for r in cur.fetchall()}


def embed(model_url: str, texts: list) -> list:
    """Batch-embed texts via the model server /embeddings endpoint."""
    if not texts:
        return []
    r = httpx.post(
        f"{model_url}/embeddings",
        json={"texts": texts, "normalize": True},
        timeout=120.0,
    )
    r.raise_for_status()
    return r.json().get("embeddings", [])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="scan + report, no writes (default)")
    ap.add_argument("--write", action="store_true", help="apply updates")
    ap.add_argument("--limit", type=int, default=0, help="process at most N chunks (0 = all)")
    ap.add_argument("--batch-size", type=int, default=200)
    ap.add_argument("--embed-batch-size", type=int, default=50)
    ap.add_argument("--skip-medical-vocab", action="store_true",
                    help="do not build the Neo4j corpus vocabulary")
    ap.add_argument("--sample", type=int, default=20, help="dry-run before/after samples to print")
    args = ap.parse_args()

    mode = "WRITE" if args.write else "DRY-RUN"
    print(f"=== rechunk_dehyphenate_chunks ({mode}) ===")

    conn = psycopg2.connect(PG_DSN)

    extra = frozenset()
    if not args.skip_medical_vocab:
        print("Building corpus vocabulary from Neo4j ...")
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        try:
            extra = build_medical_vocab(driver)
            print(f"  total vocabulary words: {len(extra)}")
        finally:
            driver.close()
    else:
        print("Skipping corpus vocabulary (general English word list only).")

    print("Scanning for artifact chunks ...")
    all_ids = fetch_target_ids(conn)
    total = len(all_ids)
    print(f"Found {total} chunks with a 'word- word' artifact.")
    if args.limit:
        all_ids = all_ids[: args.limit]
        print(f"Limiting to first {len(all_ids)} chunks.")

    mc = None
    if args.write:
        print("Connecting to Milvus ...")
        mc = MilvusClient(uri=MILVUS_URI)
        mc.load_collection(MILVUS_COLLECTION)

    changed_total = 0
    join_samples = Counter()
    keep_samples = Counter()
    leave_samples = Counter()
    t0 = time.monotonic()
    _artifact_tok = re.compile(r"[A-Za-z]+- [A-Za-z][A-Za-z]*")

    for start in range(0, len(all_ids), args.batch_size):
        batch_ids = all_ids[start : start + args.batch_size]
        rows = fetch_rows(conn, batch_ids)

        changed = {}  # id -> new_content
        for cid, content in rows.items():
            new = GenericMultiLevelChunkingFramework._dehyphenate_space_wraps(
                content, extra_words=extra
            )
            if new != content:
                changed[cid] = new

        if not changed:
            continue

        changed_total += len(changed)
        if not args.write:
            # dry-run: tally token-level transforms for eyeballing
            for cid, new in changed.items():
                old = rows[cid]
                for m in _artifact_tok.finditer(old):
                    before = m.group(0)
                    after = GenericMultiLevelChunkingFramework._dehyphenate_space_wraps(
                        before, extra_words=extra
                    )
                    if after == before:
                        leave_samples[before] += 1
                    elif "-" in after:
                        keep_samples[before] += 1
                    else:
                        join_samples[before] += 1
            continue

        # --- write path ---
        changed_ids = list(changed.keys())
        # 1. fetch existing Milvus metadata for these ids
        metas = {}
        try:
            got = mc.get(collection_name=MILVUS_COLLECTION, ids=changed_ids,
                         output_fields=["metadata"])
            for row in got:
                metas[str(row["id"])] = row.get("metadata") or {}
        except Exception as e:
            print(f"  !! Milvus get failed for batch, skipping Milvus update: {e}")
            metas = {}

        # 2. embed new contents in sub-batches
        new_contents = [changed[cid] for cid in changed_ids]
        vecs = []
        for i in range(0, len(new_contents), args.embed_batch_size):
            vecs.extend(embed(MODEL_SERVER_URL, new_contents[i : i + args.embed_batch_size]))

        # 3. build upsert payloads
        upsert_data = []
        for cid, content, vec in zip(changed_ids, new_contents, vecs):
            meta = dict(metas.get(cid, {}))
            meta["content"] = content
            meta["word_count"] = len(content.split())
            upsert_data.append({"id": cid, "vector": vec, "metadata": meta})

        # 4. Milvus upsert
        if upsert_data:
            mc.upsert(collection_name=MILVUS_COLLECTION, data=upsert_data)

        # 5. Postgres update (content + content_hash)
        with conn.cursor() as cur:
            for cid, content in changed.items():
                cur.execute(
                    "UPDATE multimodal_librarian.knowledge_chunks "
                    "SET content = %s, content_hash = %s, updated_at = CURRENT_TIMESTAMP "
                    "WHERE id = %s::uuid",
                    (content, hashlib.sha256(content.encode("utf-8")).hexdigest(), cid),
                )
        conn.commit()

        print(f"  batch {start // args.batch_size + 1}: "
              f"changed {len(changed)}/{len(batch_ids)} (total {changed_total})")

    elapsed = time.monotonic() - t0
    print(f"\nDone in {elapsed:.1f}s. Chunks changed: {changed_total} ({mode}).")

    if not args.write and (join_samples or keep_samples or leave_samples):
        _dehyp = GenericMultiLevelChunkingFramework._dehyphenate_space_wraps
        if join_samples:
            print(f"\nJOIN (soft-wrap -> single word), top {args.sample}:")
            for before, n in join_samples.most_common(args.sample):
                print(f"  {n:4d}  {before!r} -> {_dehyp(before, extra_words=extra)!r}")
        if keep_samples:
            print(f"\nKEEP-HYPHEN (compound, drop space), top {args.sample}:")
            for before, n in keep_samples.most_common(args.sample):
                print(f"  {n:4d}  {before!r} -> {_dehyp(before, extra_words=extra)!r}")
        if leave_samples:
            print(f"\nLEAVE-ALONE (dash + function word), top {args.sample}:")
            for before, n in leave_samples.most_common(args.sample):
                print(f"  {n:4d}  {before!r}")

    if not args.write:
        print("\nDry run — no writes performed. Re-run with --write to apply.")

    conn.close()


if __name__ == "__main__":
    main()
