#!/usr/bin/env python3
"""Phase 6 end-to-end ingestion smoke test (scope write path through Celery).

Uploads two small PDFs (one public, one private) through the live HTTP API,
waits for the Celery pipeline to fully ingest each, then verifies the *whole*
privacy-scope write path:

  1. Postgres ``knowledge_sources.scope`` persisted correctly.
  2. Neo4j ``:Concept`` nodes minted from each doc carry the matching
     ``scope`` / ``owner_id`` / ``concept_id`` (``public:*`` vs ``private:*``).
  3. The scope predicate gates visibility: a public concept is visible to any
     user (and to ``None``); a private concept is visible only to its owner.

Unlike ``smoke_test_phase6.py`` (which exercises ``_persist_concepts`` directly),
this script drives the real upload → S3 → extract → chunk → bridge → embed →
knowledge-graph chain, so it validates the code changes in
``documents.py``, ``upload_service.py``, and ``celery_service._update_knowledge_graph``
end to end.

Requires the live stack (app :8000, neo4j :7687, model server :8001, celery
worker) with the Phase 6 code already loaded (restart ``app`` + ``celery-worker``
first). Run with:

    venv/bin/python scripts/smoke_test_phase6_ingestion.py
"""

import asyncio
import io
import os
import sys
import time
import uuid

import asyncpg
import requests

from multimodal_librarian.clients.neo4j_client import Neo4jClient  # noqa: E402

APP_BASE = "http://localhost:8000"
PG_DSN = {
    "host": "localhost",
    "port": 5432,
    "user": "postgres",
    "password": "postgres",
    "database": "multimodal_librarian",
}
NEO4J = {"uri": "bolt://localhost:7687", "user": "neo4j", "password": "password"}

# Give the pipeline plenty of headroom; a one-page PDF should finish in ~1-2m.
INGEST_TIMEOUT_S = 420
POLL_INTERVAL_S = 5

RESULTS = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] {name}" + (f"  -- {detail}" if detail else ""))


def make_pdf(path: str, title: str, body: str) -> str:
    """Write a single-page PDF with the given text; returns the path."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(path, pagesize=letter)
    c.drawString(100, 750, title)
    y = 720
    for line in body.split("\n"):
        for chunk in _wrap(line, 90):
            c.drawString(100, y, chunk)
            y -= 16
            if y < 60:
                c.showPage()
                y = 750
    c.showPage()
    c.save()
    return path


def _wrap(text: str, width: int):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


def upload_pdf(path: str, scope: str, user_id: str, title: str):
    with open(path, "rb") as f:
        return requests.post(
            f"{APP_BASE}/api/documents/upload",
            files={"file": (os.path.basename(path), f, "application/pdf")},
            data={"scope": scope, "user_id": user_id, "title": title},
            timeout=60,
        )


async def wait_for_ingest(pg, doc_id: str) -> tuple[str, str]:
    """Poll knowledge_sources.processing_status until terminal. Returns (status, scope)."""
    deadline = time.monotonic() + INGEST_TIMEOUT_S
    last = None
    while time.monotonic() < deadline:
        row = await pg.fetchrow(
            "SELECT processing_status::text AS status, scope::text AS scope "
            "FROM multimodal_librarian.knowledge_sources WHERE id = $1::uuid",
            doc_id,
        )
        if row is None:
            return "missing", ""
        status, scope = (row["status"] or "").lower(), row["scope"]
        if status != last:
            print(f"    [{doc_id[:8]}] status={status} scope={scope}")
            last = status
        if status in ("completed", "failed"):
            return status, scope or "private"
        await asyncio.sleep(POLL_INTERVAL_S)
    return "timeout", (last or "")


async def get_concepts(neo4j, doc_id: str):
    return await neo4j.execute_query(
        """
        MATCH (c:Concept)-[:EXTRACTED_FROM]->(ch:Chunk {source_id: $doc_id})
        RETURN c.name AS name, c.scope AS scope, c.owner_id AS owner_id,
               c.concept_id AS concept_id
        ORDER BY c.name
        """,
        {"doc_id": doc_id},
    )


async def visibility(neo4j, concept_id: str, user_id) -> bool:
    rows = await neo4j.execute_query(
        """
        MATCH (c:Concept {concept_id: $cid})
        WHERE (c.scope = 'public' OR ($user_id IS NOT NULL AND c.owner_id = $user_id))
        RETURN count(c) AS n
        """,
        {"cid": concept_id, "user_id": user_id},
    )
    return bool(rows) and rows[0]["n"] >= 1


async def cleanup(neo4j, doc_ids, run_started_at):
    # Sweep Neo4j first, before the API delete, so there is no write-lock
    # contention with ``delete_document_completely``. Delete every ``:Concept``
    # minted during this run — both the EXTRACTED_FROM concepts and the
    # ConceptNet/UMLS ``EXTERNAL`` bridge concepts the pipeline also creates.
    await neo4j.execute_write_query(
        "MATCH (c:Concept) WHERE c.created_at >= $since DETACH DELETE c",
        {"since": run_started_at},
    )
    await neo4j.execute_write_query(
        "MATCH (ch:Chunk) WHERE ch.source_id IN $ids DETACH DELETE ch",
        {"ids": doc_ids},
    )
    for did in doc_ids:
        try:
            requests.delete(f"{APP_BASE}/api/documents/{did}", timeout=60)
        except Exception as e:  # noqa: BLE001
            print(f"    [WARN] API delete {did[:8]} failed: {e}")


async def main() -> int:
    run_id = uuid.uuid4().hex[:6]
    user_owner = f"smoke_owner_{run_id}"
    user_other = "00000000-0000-0000-0000-000000000001"  # never == admin uuid

    tmp_public = f"/tmp/smoke_public_{run_id}.pdf"
    tmp_private = f"/tmp/smoke_private_{run_id}.pdf"

    public_body = (
        "Treatment of refractory asthma with Montelukast has shown promise.\n"
        "A randomized trial by Dr. Eleanor Vance at Meridian Clinic examined\n"
        "leukotriene receptor antagonists. The study enrolled 240 patients\n"
        "with eosinophilic asthma and measured FEV1 improvement.\n"
        "Montelukast reduced exacerbations by 32 percent compared to placebo."
    )
    private_body = (
        "Hyperkalemia is a common complication of chronic kidney disease.\n"
        "Dr. Marcus Reed at Northgate Hospital reviewed sodium polystyrene\n"
        "sulfonate and patiromer for potassium management. The retrospective\n"
        "cohort included 180 patients on loop diuretics. Patiromer reduced\n"
        "serum potassium by 0.8 milliequivalents per liter."
    )

    neo4j = None
    pg = None
    doc_ids = []
    run_started_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    try:
        make_pdf(tmp_public, "Public Scope Smoke", public_body)
        make_pdf(tmp_private, "Private Scope Smoke", private_body)

        neo4j = Neo4jClient(**NEO4J)
        await neo4j.connect()
        pg = await asyncpg.connect(**PG_DSN)

        # --- Upload both docs ---
        print("\n== Upload (public + private) ==")
        r_pub = upload_pdf(tmp_public, "public", user_owner, "Public Scope Smoke")
        r_priv = upload_pdf(tmp_private, "private", user_owner, "Private Scope Smoke")
        check("public upload HTTP 200", r_pub.status_code == 200,
              f"status={r_pub.status_code} body={r_pub.text[:200]}")
        check("private upload HTTP 200", r_priv.status_code == 200,
              f"status={r_priv.status_code} body={r_priv.text[:200]}")

        pub_id = r_pub.json().get("document_id") if r_pub.status_code == 200 else None
        priv_id = r_priv.json().get("document_id") if r_priv.status_code == 200 else None
        if not pub_id or not priv_id:
            print("  [ABORT] upload failed; skipping ingestion checks")
            return 1
        doc_ids = [pub_id, priv_id]

        # --- Wait for ingestion ---
        print("\n== Ingest (Celery pipeline) ==")
        pub_status, pub_scope = await wait_for_ingest(pg, pub_id)
        priv_status, priv_scope = await wait_for_ingest(pg, priv_id)
        check("public doc ingested (completed)", pub_status == "completed", f"status={pub_status}")
        check("private doc ingested (completed)", priv_status == "completed", f"status={priv_status}")
        check("public scope persisted in Postgres", pub_scope == "public", f"scope={pub_scope}")
        check("private scope persisted in Postgres", priv_scope == "private", f"scope={priv_scope}")

        # --- Verify minted concepts ---
        print("\n== Neo4j concept stamping ==")
        pub_concepts = await get_concepts(neo4j, pub_id)
        priv_concepts = await get_concepts(neo4j, priv_id)
        check("public doc minted >=1 concept", len(pub_concepts) >= 1,
              f"count={len(pub_concepts)}")
        check("private doc minted >=1 concept", len(priv_concepts) >= 1,
              f"count={len(priv_concepts)}")

        def all_match(concepts, pred) -> bool:
            return len(concepts) >= 1 and all(pred(c) for c in concepts)

        pub_ok = all_match(pub_concepts, lambda c: (
            c["scope"] == "public" and c["owner_id"] is None
            and str(c["concept_id"]).startswith("public:")
        ))
        priv_ok = all_match(priv_concepts, lambda c: (
            c["scope"] == "private" and c["owner_id"] is not None
            and str(c["concept_id"]).startswith("private:")
        ))
        check("public concepts stamped public / owner NULL / public: id", pub_ok,
              f"sample={[ (c['concept_id'], c['scope'], c['owner_id']) for c in pub_concepts[:3] ]}")
        check("private concepts stamped private / owner set / private: id", priv_ok,
              f"sample={[ (c['concept_id'], c['scope'], c['owner_id']) for c in priv_concepts[:3] ]}")

        # --- Visibility predicate ---
        print("\n== Scope-predicate visibility ==")
        if pub_concepts and priv_concepts:
            pub_cid = pub_concepts[0]["concept_id"]
            priv_cid = priv_concepts[0]["concept_id"]
            priv_owner = priv_concepts[0]["owner_id"]

            check("public concept visible to another user",
                  await visibility(neo4j, pub_cid, user_other), f"cid={pub_cid}")
            check("public concept visible to user_id=None",
                  await visibility(neo4j, pub_cid, None), f"cid={pub_cid}")
            check("private concept visible to its owner",
                  await visibility(neo4j, priv_cid, priv_owner), f"cid={priv_cid}")
            check("private concept hidden from another user",
                  not await visibility(neo4j, priv_cid, user_other), f"cid={priv_cid}")
            check("private concept hidden from user_id=None",
                  not await visibility(neo4j, priv_cid, None), f"cid={priv_cid}")

    finally:
        if neo4j is not None:
            try:
                await cleanup(neo4j, doc_ids, run_started_at)
            finally:
                await neo4j.close()
        if pg is not None:
            await pg.close()
        for p in (tmp_public, tmp_private):
            if os.path.exists(p):
                os.remove(p)

    print("\n" + "=" * 60)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = [r for r in RESULTS if not r[1]]
    print(f"INGESTION SMOKE RESULTS: {passed}/{len(RESULTS)} passed")
    if failed:
        for name, _, detail in failed:
            print(f"  FAILED: {name} -- {detail}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
