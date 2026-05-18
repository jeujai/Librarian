# Milvus Post-Restart Retrieval Regression Bugfix Design

## Overview

After a Docker restart of the Milvus stack (`milvus`, `etcd`, `minio` in `docker-compose.yml`), the reference query "What did our team observe at Chelsea?" returns a top-10 Sources panel that contains no GenAI book page 114 chunk and no chunks about Chelsea AI Ventures. The bug is *silent*: the chat UI renders a confident "no information" response rather than a "retrieval index not ready" error, and the adjacent `chelsea-query-semantic-noise` scoring fix (already merged in `QueryDecomposer._find_semantic_matches()` and `KGRetrievalService._aggregate_and_deduplicate()`) has no material effect because the target chunk never enters the candidate set. The named volumes `milvus_data`, `etcd_data`, `minio_data` are declared at the bottom of `docker-compose.yml`, so a plain `docker compose restart milvus etcd minio` (or a container restart triggered by Docker Desktop) is expected to preserve data on disk.

This design uses triage-first reasoning: several distinct root causes (volume loss, collection not reloaded into memory, etcd↔minio segment/metadata desync, index/partition unattached, or a stale cached Milvus client in the running app process) produce the same user-visible fingerprint — unrelated top-10 sources and a "no information" answer. Without in-process state probes we cannot pick exactly one cause up front, so bugfix clause 2.3 is the spine of the fix: the system must either (a) complete re-establishment of a loaded, consistent `knowledge_chunks` collection before serving retrieval, or (b) surface a deterministic "not ready" error to the caller. The fix lives primarily in a new `MilvusReadinessGate` wired through the existing DI layer (`src/multimodal_librarian/api/dependencies/services.py`), a narrow reconnection/reload retry inside `MilvusClient` on the runtime search path, and a single structured log event that makes the *next* occurrence diagnosable without committing to fragile per-cause branching today.

The invariants established by `.kiro/specs/chelsea-query-semantic-noise/` (scoring) and `.kiro/specs/milvus-title-metadata-fix/` (citation titles) remain untouched. No destructive recovery runs against named volumes (bugfix clause 3.5) and no change is made to the ingestion field set (bugfix clause 3.4).

## Glossary

- **Bug_Condition (C)**: The condition under which the defect manifests — an `EnvironmentSample(milvus_connected, has_collection, collection_loaded, num_entities, pg_chunk_count, segment_metadata_consistent)` where any required invariant fails after a Milvus-stack restart.
- **Property (P)**: Desired behavior — the Chelsea query SHALL retrieve the GenAI book page 114 chunk, OR the caller SHALL receive a deterministic "retrieval index not ready" error; the system SHALL NOT silently return a degraded candidate set.
- **Preservation**: The scoring and citation contracts from the two adjacent specs, the ingestion field set, the named-volume contents, and healthy-path latency must remain unchanged.
- **MilvusClient**: `MilvusClient` in `src/multimodal_librarian/clients/milvus_client.py`. Wraps pymilvus; holds `_connected: bool`, `_collection_cache: Dict[str, Collection]`, `_cached_health_status: dict`, a 30-second `_health_check_interval`. Uses `pymilvus.connections.connect`, `pymilvus.utility.list_collections`, `pymilvus.Collection(name, using=alias)`, `collection.load()`, `collection.num_entities`, `collection.flush()`, `collection.upsert(...)`, `collection.create_index(...)`. Raises `pymilvus.MilvusException` on server-side failures.
- **RetrievalService**: The end-to-end retrieval path. `KGRetrievalService._perform_semantic_search` (in `src/multimodal_librarian/services/kg_retrieval_service.py`, lines ~1272–1307) dispatches to `self._vector_client.semantic_search(query=..., top_k=...)`, where `_vector_client` is a `MilvusClient` on local and an `OpenSearchClient` on AWS. Wired via `get_kg_retrieval_service` in `src/multimodal_librarian/api/dependencies/services.py` using `Depends(get_vector_client_optional)`.
- **ReadinessGate**: New component `MilvusReadinessGate` introduced by this design. Orchestrates four checks — connection, `utility.has_collection("knowledge_chunks")`, `Collection.load()` completion + index presence, and entity-count parity with PostgreSQL — and exposes an `is_ready()` coroutine plus a `readiness_status()` snapshot.
- **CollectionStateInvariant**: The post-ingestion invariant "PostgreSQL `multimodal_librarian.knowledge_chunks` row count = Milvus `Collection('knowledge_chunks').num_entities` (within tolerance) AND the collection is present AND loaded AND has an index on the `vector` field".
- **Candidate Root Causes (RC1–RC5)**:
  - **RC1 — Volume Loss**: One or more of `milvus_data`, `etcd_data`, `minio_data` was wiped (e.g., a `docker compose down -v` or a Docker Desktop prune). `utility.has_collection("knowledge_chunks")` returns `False` or `num_entities == 0`. Maps to bugfix clause 1.5 / 1.6.
  - **RC2 — Collection Not Loaded**: Collection exists on disk and etcd metadata is consistent, but no process has called `Collection.load()` against the restarted Milvus; queries return empty / degraded. Maps to bugfix clause 1.7.
  - **RC3 — etcd ↔ MinIO Desync**: `etcd` metadata lists segments that do not exist in MinIO (or vice versa) because one of the two volumes was snapshotted at a different time. Some rows are unreadable. Maps to bugfix clause 1.8.
  - **RC4 — Index / Partition Unattached**: Collection is loaded but the `vector` field index or a partition was not reattached after restart; search may silently fall back to brute-force or return empty. Maps to bugfix clause 1.8.
  - **RC5 — Stale Cached Client in Running App**: The app process did not restart with the Milvus stack. `MilvusClient._connected` is still `True` and `_collection_cache` holds `Collection` objects from before the Milvus restart; the 30 s `_cached_health_status` continues to report "healthy". The app never triggers a fresh `connect()` or `load()` against the new Milvus instance. Maps to bugfix clauses 1.4 and 1.9.

## Bug Details

### Bug Condition

After a Milvus-stack restart, the retrieval path becomes defective when any component of the CollectionStateInvariant is violated and the `MilvusClient` / retrieval code does not detect the violation before serving a user query.

**Formal Specification:**

```
FUNCTION isBugCondition(input)
  INPUT: input of type EnvironmentSample
         ( milvus_connected: bool,
           has_collection: bool,
           collection_loaded: bool,
           has_vector_index: bool,
           num_entities: int,
           pg_chunk_count: int,
           segment_metadata_consistent: bool,
           client_cache_stale: bool )
  OUTPUT: boolean

  restart_invariant_violated :=
         (NOT milvus_connected)
      OR (NOT has_collection)
      OR (NOT collection_loaded)
      OR (NOT has_vector_index)
      OR (num_entities < pg_chunk_count - tolerance(pg_chunk_count))
      OR (NOT segment_metadata_consistent)
      OR client_cache_stale

  retrieval_served_anyway :=
         retrievalEndpointAcceptsRequest()
      AND NOT readinessGateGuardsRequest()

  RETURN restart_invariant_violated AND retrieval_served_anyway
END FUNCTION

FUNCTION tolerance(n)
  // Allow a small delta for in-flight inserts that have not yet flushed.
  // Default: max(1, 1% of pg_chunk_count). See Fix Implementation / Track A.
  RETURN max(1, ceil(0.01 * n))
END FUNCTION
```

### Evidence and Examples

The in-process code paths that are defective today:

- **`MilvusClient.connect`** (`clients/milvus_client.py` lines ~209–276): Connection is established once; the `_connected` flag, set at line ~258, is never cleared by the client unless an explicit `disconnect()` is called. There is no hook that fires when the *remote* Milvus server restarts.
- **`MilvusClient._get_collection`** (lines ~1697–1717): Caches `Collection(name, using=self.connection_name)` objects in `_collection_cache`. After a Milvus server restart, a cached object is reused without `load()` being re-evaluated unless the caller happens to be `search_vectors`, `semantic_search`, `get_vector_by_id`, `delete_chunks_by_source`, `delete_vectors`, or `get_collection_stats` — each of which independently calls `loop.run_in_executor(None, collection.load)` at the top of its try block (e.g., line ~1914 for `search_vectors`, line ~905 for batch get, line ~981 for delete).
- **`MilvusClient.health_check`** (lines ~347–449): Results are cached for 30 s (`_health_check_interval`), so a stale "healthy" status can survive a Milvus restart for up to half a minute.
- **`KGRetrievalService._perform_semantic_search`** (`services/kg_retrieval_service.py` lines ~1272–1307): Calls `self._vector_client.semantic_search(query=..., top_k=...)` with no pre-flight readiness check and no distinction between "candidate set is empty because nothing matched" and "candidate set is empty because the collection is not ready".
- **`docker-compose.yml`** `app.depends_on.milvus.condition: service_started` (lines ~162–165, ~474–477): The app starts when the Milvus *container* starts, not when the Milvus collection is queryable. The `milvus` service has no `healthcheck` block; only `minio` has one.

Observable signatures expected at each root cause (used to key Track C's structured log):

| RC | Expected signature | Bugfix clause |
|----|--------------------|---------------|
| RC1 — Volume Loss | `utility.has_collection("knowledge_chunks") == False` OR `num_entities == 0` with `pg_chunk_count > 0` | 1.5, 1.6 |
| RC2 — Collection Not Loaded | `has_collection == True`, `num_entities > 0`, `load()` not yet invoked since restart, search returns empty | 1.7 |
| RC3 — etcd ↔ MinIO Desync | `has_collection == True`, `num_entities > 0`, but `collection.query(expr="id in [<known-id>]")` returns empty OR raises segment-fetch error | 1.8 |
| RC4 — Index / Partition Unattached | `collection.indexes` is empty on the `vector` field OR returns a non-flat search path unexpectedly | 1.8 |
| RC5 — Stale Cached Client | App logs show no reconnect since last Milvus start timestamp; cached `_collection_cache` non-empty; cached `_cached_health_status.status == "healthy"` while Milvus uptime is seconds | 1.4, 1.9 |

Concrete Chelsea-query examples:
- Expected: top-10 includes the GenAI book (title filename-derived per the `milvus-title-metadata-fix` spec), `page_number == 114`, content contains "Chelsea AI Ventures".
- Observed post-restart: top-10 dominated by `Computer Vision: A Modern Approach` (97%), `Ferris Clinical Advisor 2021` page 1827 (90%), `Artificial Intelligence: A Modern Approach, 3rd Edition`, clinical guidelines — none reference Chelsea AI Ventures.
- Edge case: `num_entities` reports a nonzero value but the specific GenAI book segment is absent; the query still succeeds structurally (no exception) because cosine similarity retains unrelated chunks.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- **3.1 / 3.2 (scoring parity)**: `QueryDecomposer._find_semantic_matches()` and `KGRetrievalService._aggregate_and_deduplicate()` are not touched. When a healthy candidate set is available, pre-fix and post-fix outputs are byte-identical — same top-N order, same relevance scores. No field is added to or removed from the score tuple.
- **3.3 (title-metadata contract)**: The filename-derived fallback for titles established by `.kiro/specs/milvus-title-metadata-fix/` continues to surface in the Sources panel. The fix does not re-introduce the PostgreSQL `_enrich_chunks_with_titles()` workaround.
- **3.4 (ingestion contract)**: `MilvusClient.store_embeddings` and `MilvusClient.insert_vectors` write the same schema as today — primary key `id` (VARCHAR, UUID), `vector` (FLOAT_VECTOR, configured dimension), `metadata` (JSON) containing `content`, `content_type`, `stored_at`, plus the ingestion-supplied fields `source_id`, `chunk_index`, `page_number`, `title`, plus the internal `_vector_id`. No field is added, renamed, or removed. Chunk counts, content hashes, and PostgreSQL ↔ Milvus ↔ Neo4j row correspondence are unchanged.
- **3.5 / 3.7 (non-destructive recovery)**: No code path introduced by this fix calls `utility.drop_collection`, deletes any volume, or rewrites MinIO objects. The fix may only *read* from Milvus/PostgreSQL and may call `Collection.load()`, which is idempotent and non-destructive.
- **3.6 (latency)**: On a healthy collection, the readiness gate does at most one cached in-memory check per request (see Track A cache design); no extra Milvus round-trip is added on the request path once readiness has been established.

**Scope:**
All inputs where `isBugCondition` returns false — queries against a healthy collection, queries against `OpenSearchClient` in the AWS environment, queries against unrelated collections, and all non-retrieval endpoints — must behave byte-identically. Specifically unaffected:
- The AWS environment path through `_create_aws_opensearch_client` in `clients/database_factory.py`.
- The ingestion path (`celery_service.store_embeddings_task` and `_store_embeddings_in_vector_db`).
- Existing tests: `tests/services/test_kg_retrieval_service.py`, `tests/components/test_pdf_processor.py`, tests under `tests/components/vector_store/`, and any test that constructs `MilvusClient` or calls `semantic_search` through `TestClient`.
- The `ConnectionManager` WebSocket chat path (`api/dependencies/services.py` `ConnectionManager`) beyond the readiness-gate guard being added at the chat endpoint boundary.

## Hypothesized Root Cause

Each candidate is classified honestly; none is confirmed by a live reproduction today because the bug is observed in production without the probes that would distinguish them. The fix is designed to work for all five simultaneously.

### RC1 — Volume Loss — **Probable, verification test required**

The bug reporter's stack uses named Docker volumes; a plain `docker compose restart` preserves them, but Docker Desktop GUI "reset" or `docker volume prune` after an earlier `docker compose down -v` would not. If any of the three volumes was wiped, Milvus comes up with an empty `knowledge_chunks` collection (or no collection at all), which matches bugfix clauses 1.5 and 1.6. A single `utility.has_collection("knowledge_chunks")` + `collection.num_entities` probe against `multimodal_librarian.knowledge_chunks` row count in PostgreSQL resolves this directly. Verification test: T2 (below).

### RC2 — Collection Not Loaded — **Probable, most likely for a restart without volume loss**

Milvus standalone requires `Collection.load()` to be invoked after any server restart before it will serve queries on that collection. The code at `MilvusClient.search_vectors` line ~1914 does call `loop.run_in_executor(None, collection.load)` on every search, so under normal conditions RC2 should self-heal on the first query — *but* the `_collection_cache` entry is a `pymilvus.Collection` object tied to `self.connection_name`, and if the underlying pymilvus `connections` state is stale post-restart, the `load` call may succeed silently while targeting the wrong handle. Also, the very first search on a large collection after a cold restart can take tens of seconds to load; a request that times out on the client side leaves the system in a half-loaded state. Classify as probable. Verification test: T1.

### RC3 — etcd ↔ MinIO Desync — **To-be-verified**

Each of etcd and MinIO is on its own volume. If a restart was partial (e.g., Docker OOM-killed one of them mid-flush) the two stores can disagree about which segments exist. This is the hardest case to detect programmatically and the hardest to safely recover from. Per bugfix clause 3.5 the fix must not take destructive action, so for RC3 the fix surfaces a readiness failure and leaves recovery to the operator. Verification requires constructing a crafted inconsistency, which is out of scope for the initial fix.

### RC4 — Index / Partition Unattached — **To-be-verified**

If the index file on disk is present but etcd's view of the index has drifted, search may silently fall back. `collection.indexes` should be non-empty on the `vector` field post-load; the readiness gate checks this explicitly. Verification requires a crafted Milvus state; to-be-verified.

### RC5 — Stale Cached Client in Running App — **Probable, applies whenever the app process survives a Milvus restart**

`MilvusClient._connected` is a boolean latched on first connect (line ~258). `_collection_cache` retains `Collection` objects across restarts. `_cached_health_status` is valid for 30 s. The `get_vector_client_optional` DI function caches `_vector_client` at module level and does not refresh it on Milvus reconnection events. No code path today invalidates any of these on a Milvus server restart. This is almost certainly triggering on every `docker compose restart milvus` when the `app` container is not also restarted. Verification test: T3.

## Correctness Properties

Property 1: Bug Condition — Post-restart Chelsea query returns GenAI page 114

_For any_ application state where `docker compose restart etcd minio milvus` has completed with the named volumes `milvus_data`, `etcd_data`, `minio_data` preserved on disk and the ingestion pipeline has previously stored the GenAI book page 114 chunk, when the query "What did our team observe at Chelsea?" is submitted through the chat UI, the system SHALL return the GenAI book page 114 chunk within the top-10 Sources panel with a filename-derived title identifying the GenAI book and `page_number == 114`, and the AI response SHALL draw on that chunk's content about Chelsea AI Ventures.

**Validates: Requirements 2.1, 2.2, 2.7**

Property 2: Bug Condition — Deterministic readiness outcome, never silent degradation

_For any_ retrieval request that reaches the chat or retrieval endpoint after a Milvus-stack restart, the system SHALL either (a) return a result list drawn from a fully ready `knowledge_chunks` collection, or (b) return a deterministic `503 retrieval_index_not_ready` response whose body names the failed readiness check, but SHALL NOT return a top-N result list drawn from a degraded candidate set.

**Validates: Requirements 2.3**

Property 3: Bug Condition — Readiness establishes connection, presence, load, and parity before serving

_For any_ retrieval request, the readiness gate SHALL, before returning "ready", verify all of:
(i) `MilvusClient` is connected to the current Milvus server (connection re-established if the server restarted),
(ii) `pymilvus.utility.has_collection("knowledge_chunks")` returns `True`,
(iii) `Collection("knowledge_chunks").load()` has completed at least once since the most recent connection,
(iv) `collection.indexes` contains an index entry for the `vector` field,
(v) `collection.num_entities` is within `tolerance(pg_chunk_count)` of the PostgreSQL `multimodal_librarian.knowledge_chunks` row count.
Failure of any check SHALL prevent the "ready" state from being granted.

**Validates: Requirements 2.4, 2.5**

Property 4: Bug Condition — Detected etcd ↔ MinIO desync blocks retrieval

_For any_ observable inconsistency between etcd metadata and the MinIO segment set for `knowledge_chunks` (detected via a readiness probe that queries a known-present chunk by id and fails, or via an index-presence mismatch), the system SHALL refuse to serve retrieval requests that depend on the affected collection and SHALL surface the inconsistency in the structured readiness log. The system SHALL NOT take destructive repair action.

**Validates: Requirements 2.6**

Property 5: Preservation — Scoring byte-identity on healthy collections

_For any_ query submitted against a healthy `knowledge_chunks` collection, the candidate set passed into `QueryDecomposer._find_semantic_matches()` and the scored output of `KGRetrievalService._aggregate_and_deduplicate()` SHALL be byte-identical to pre-fix behavior — same candidate set, same intermediate coverage-bonus values, same final ranking, same relevance scores.

**Validates: Requirements 3.1, 3.2**

Property 6: Preservation — Title-metadata contract unchanged

_For any_ chunk returned in the Sources panel, its surfaced title SHALL continue to follow the `.kiro/specs/milvus-title-metadata-fix/` contract (filename-derived fallback when the PDF metadata title is empty/`None`/missing), and the system SHALL NOT invoke the PostgreSQL `_enrich_chunks_with_titles()` workaround.

**Validates: Requirements 3.3**

Property 7: Preservation — Ingestion field set and cross-store relationships unchanged

_For any_ document ingested through `celery_service.store_embeddings_task` → `_store_embeddings_in_vector_db` → `MilvusClient.store_embeddings` → `MilvusClient.insert_vectors`, the Milvus schema SHALL remain `(id VARCHAR primary, vector FLOAT_VECTOR, metadata JSON)`, the metadata JSON SHALL contain exactly the same fields as today (`content`, `content_type`, `stored_at`, `source_id`, `chunk_index`, `page_number`, `title`, `_vector_id`), and the chunk counts, content hashes, and PostgreSQL ↔ Milvus ↔ Neo4j row correspondence SHALL match pre-fix behavior.

**Validates: Requirements 3.4**

Property 8: Preservation — No destructive recovery against named volumes

_For any_ code path introduced by this fix, the fix SHALL NOT invoke `pymilvus.utility.drop_collection`, SHALL NOT delete or recreate the named volumes `milvus_data`, `etcd_data`, `minio_data`, `postgres_data`, `neo4j_data`, and SHALL NOT reinitialize ingestion without explicit operator action. A clean `docker compose down` (without `-v`) followed by `docker compose up` SHALL restore the collection to a retrievable state under the fix's restart semantics.

**Validates: Requirements 3.5, 3.7**

Property 9: Preservation — Per-request latency unchanged on healthy collections

_For any_ retrieval request against a healthy `knowledge_chunks` collection where readiness has previously been established, the per-request latency overhead introduced by the readiness gate SHALL be bounded by a single in-memory boolean check (an O(1) read of a cached `Ready` state) and SHALL NOT add any extra Milvus or PostgreSQL round-trip on the request path. The readiness-gate caches are invalidated only on (a) connection events, (b) a configurable TTL, or (c) an explicit runtime search failure per Track B.

**Validates: Requirements 3.6**

## Fix Implementation

The fix has four tracks. All code changes respect the DI steering contract in `.kiro/steering/dependency-injection.md`: no module-level instantiation, all wiring through `Depends(...)`, singleton caching via a module-level `_variable`, and cleanup through the existing `clear_all_caches` / `cleanup_all_dependencies` in `src/multimodal_librarian/api/dependencies/services.py`.

### Track A — Post-Restart Readiness Gate (primary fix path)

**Goal**: Make retrieval endpoints refuse to serve until `knowledge_chunks` is connected, present, loaded, indexed, and in entity-count parity with PostgreSQL. Deterministic 503 on failure; transparent pass on success.

**Files**:
- **New**: `src/multimodal_librarian/clients/milvus_readiness_gate.py` — `class MilvusReadinessGate` and dataclass `ReadinessStatus`.
- **Modify**: `src/multimodal_librarian/api/dependencies/services.py` — add `get_milvus_readiness()` and optional variant; add `_milvus_readiness_gate: Optional[MilvusReadinessGate] = None` module-level cache; add cleanup hooks in `clear_all_caches` and `cleanup_all_dependencies`.
- **Modify**: The chat / retrieval routers that currently use `Depends(get_kg_retrieval_service)` or `Depends(get_cached_rag_service)` — add a readiness-gate dependency alongside.

**Public API (`MilvusReadinessGate`)**:

```python
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class ReadinessStatus:
    ready: bool
    collection_exists: bool
    is_loaded: bool
    has_vector_index: bool
    num_entities: int
    pg_chunk_count: int
    delta: int
    tolerance: int
    gate_decision: str           # one of: "ready", "collection_missing",
                                 #         "not_loaded", "index_missing",
                                 #         "entity_parity_failed",
                                 #         "connection_failed"
    evaluated_at: float          # time.time()


class MilvusReadinessGate:
    """Readiness gate for the `knowledge_chunks` Milvus collection.

    Evaluates CollectionStateInvariant lazily and caches the outcome so
    healthy-path requests pay only an O(1) boolean read (Property 9).
    """

    def __init__(
        self,
        vector_client,              # VectorStoreClient (MilvusClient locally)
        relational_client,          # RelationalStoreClient (PostgreSQL)
        collection_name: str = "knowledge_chunks",
        parity_tolerance_fraction: float = 0.01,   # 1 % — justified below
        ready_cache_ttl_seconds: float = 30.0,
        not_ready_cache_ttl_seconds: float = 2.0,  # retry fast when not ready
    ): ...

    async def is_ready(self) -> bool: ...
    async def readiness_status(self) -> ReadinessStatus: ...
    async def invalidate(self) -> None: ...   # called by Track B on runtime failure
    async def close(self) -> None: ...        # called by cleanup_all_dependencies
```

**Readiness evaluation pseudocode**:

```
FUNCTION evaluateReadiness()
  1. If vector_client is not connected, call vector_client.connect().
     If connect raises, return ReadinessStatus(ready=False, gate_decision="connection_failed").
  2. Run has_collection := utility.has_collection(collection_name).
     If False, return ReadinessStatus(ready=False, gate_decision="collection_missing",
                                      num_entities=0, ...).
  3. collection := Collection(collection_name, using=vector_client.connection_name).
     Run collection.load() in the executor.
     If MilvusException, return gate_decision="not_loaded".
  4. indexes := collection.indexes.
     If no index with field_name == "vector", return gate_decision="index_missing".
  5. num_entities := collection.num_entities.
  6. pg_chunk_count := SELECT COUNT(*) FROM multimodal_librarian.knowledge_chunks.
  7. tolerance := max(1, ceil(parity_tolerance_fraction * pg_chunk_count)).
  8. delta := pg_chunk_count - num_entities.
     If abs(delta) > tolerance, return gate_decision="entity_parity_failed".
  9. Return ReadinessStatus(ready=True, gate_decision="ready", ...).
END FUNCTION
```

**Parity tolerance choice**: `parity_tolerance_fraction=0.01` (1 %) with a floor of 1. Justification: ingestion is eventually consistent — `MilvusClient.insert_vectors` calls `collection.flush()` after `upsert` (`clients/milvus_client.py` lines ~1834–1859, with retry on "node not match"), and a batch in flight between PostgreSQL commit and Milvus flush can produce a transient delta. One percent is large enough to tolerate the largest single batch observed in `celery_service._store_embeddings_in_vector_db` (batched at 50 chunks, bridges at similar sizes) relative to a collection that typically holds hundreds to tens of thousands of chunks, and small enough that a volume loss (delta = full count) is never mistaken for in-flight inserts. The floor of 1 handles very small collections. If operational data later shows the default is too tight, it is a single constructor argument to adjust — no schema or code restructure.

**Caching**: `is_ready()` returns `True` without re-evaluating for up to `ready_cache_ttl_seconds` (default 30 s). When the most recent evaluation returned `False`, the gate re-evaluates more aggressively (every `not_ready_cache_ttl_seconds`, default 2 s) so a legitimate load-in-progress is picked up quickly. The cache is invalidated on: (i) any call to `invalidate()`, (ii) TTL expiry, (iii) `close()`. This satisfies Property 9 (single O(1) read on healthy path).

**DI wiring (`api/dependencies/services.py`)**:

```python
_milvus_readiness_gate: Optional["MilvusReadinessGate"] = None

async def get_milvus_readiness(
    vector_client: Optional["VectorStoreClient"] = Depends(get_vector_client_optional),
    relational_client: Optional["RelationalStoreClient"] = Depends(get_relational_client_optional),
) -> "MilvusReadinessGate":
    """Readiness gate for the Milvus `knowledge_chunks` collection.

    Lazy singleton. No import-time connections. Cached across requests.
    Cleared in clear_all_caches() and closed in cleanup_all_dependencies().
    """
    global _milvus_readiness_gate
    if _milvus_readiness_gate is None:
        if vector_client is None or relational_client is None:
            # Graceful degradation: no gate means callers SHOULD 503 themselves.
            raise HTTPException(
                status_code=503,
                detail="retrieval_index_not_ready: readiness gate dependencies unavailable",
            )
        from ...clients.milvus_readiness_gate import MilvusReadinessGate
        _milvus_readiness_gate = MilvusReadinessGate(
            vector_client=vector_client,
            relational_client=relational_client,
        )
    return _milvus_readiness_gate


async def get_milvus_readiness_optional(...) -> Optional["MilvusReadinessGate"]:
    try:
        return await get_milvus_readiness(...)
    except HTTPException:
        return None
```

Cleanup additions:

- In `clear_all_caches()` (`services.py` ~line 2830): add `global _milvus_readiness_gate` to the globals list, and set `_milvus_readiness_gate = None` after the other clears.
- In `cleanup_all_dependencies()` (`services.py` ~line 2955): add a block `if _milvus_readiness_gate is not None: await _milvus_readiness_gate.close()` before `clear_all_caches()`.

**Endpoint wiring**: The readiness gate is applied at the boundary of *user-facing retrieval* — specifically the chat query path and any endpoint that calls `KGRetrievalService.retrieve` or `RAGService.query`. It is NOT applied to:
- Health check endpoints (the gate IS a health check of its own; adding it would be circular).
- Ingestion endpoints (`POST /documents`, Celery tasks) — ingestion legitimately writes to Milvus before the collection is "ready" by our definition.
- The `/api/status` / `/api/metrics` endpoints — they should be able to *report* the gate's state, not be blocked by it.

Concretely, add `readiness: MilvusReadinessGate = Depends(get_milvus_readiness)` plus `if not await readiness.is_ready(): raise HTTPException(503, "retrieval_index_not_ready: " + status.gate_decision)` to the chat WebSocket send path and the HTTP chat endpoint(s). The exact router file names need to be enumerated in the tasks phase against `src/multimodal_librarian/api/routers/`.

### Track B — Reconnection / Reload on Transient Failure

**Goal**: When a runtime search raises a Milvus-level "not loaded" or connection error, attempt exactly one readiness re-evaluation plus one retry, then propagate the failure. No infinite loops.

**File**: `src/multimodal_librarian/clients/milvus_client.py`

**Function**: `MilvusClient.search_vectors` (lines ~1900–1996) and `MilvusClient.semantic_search` (lines ~700–900, the public entry the retrieval service uses).

**Specific changes**:

1. Wrap the core search body in a `try/except MilvusException as e`. Classify the exception:
   - If `"collection not loaded"` in `str(e).lower()` or the pymilvus error code corresponds to "collection not loaded" (pymilvus exposes these as subclasses under `MilvusException` — the check is a defensive string match plus code check because pymilvus 2.3.4's exception taxonomy is not perfectly stable across minor versions).
   - If `isinstance(e, pymilvus.exceptions.ConnectionNotExistException)` or the error message contains `"failed to connect"`, `"connection refused"`, `"channel not available"`.
2. On either classification: (a) drop the relevant entry from `self._collection_cache`, (b) set `self._connected = False`, (c) await a *single* re-run of `self.connect()` followed by a `_get_collection(name)` + `collection.load()`, (d) retry the search exactly once.
3. On the second failure, re-raise as `QueryError` and let the caller surface a 503 through Track A's error contract. Also call the readiness-gate's `invalidate()` via a weak-reference callback registered at gate construction time (the gate calls `vector_client.register_failure_callback(self.invalidate)` in `__init__`) so the next request re-evaluates rather than returning a stale cached `ready=True`.

This narrows the blast radius to the exact two pymilvus exception classes we have evidence for (see the existing retry block at lines ~521–545 that already handles `MilvusException` generically in `_run_with_retry` — Track B specializes the semantics for the search path).

### Track C — Diagnostic Logging and Observability

**Goal**: Emit a single structured log event per readiness-gate evaluation so the next occurrence can be triaged between RC1–RC5 without guesswork.

**File**: `src/multimodal_librarian/clients/milvus_readiness_gate.py` (new).

**Log event**: Logged via `structlog` (project standard per `.kiro/steering/tech.md`) at `INFO` when ready and at `WARNING` when not ready. Event name: `milvus_readiness_evaluated`. Fields:

```
{
  "event": "milvus_readiness_evaluated",
  "collection_name": "knowledge_chunks",
  "connection_established": bool,
  "collection_exists": bool,
  "is_loaded": bool,
  "has_vector_index": bool,
  "num_entities": int,
  "pg_chunk_count": int,
  "delta": int,
  "tolerance": int,
  "gate_decision": "ready" | "collection_missing" | "not_loaded"
                 | "index_missing" | "entity_parity_failed"
                 | "connection_failed",
  "evaluated_at_ms": int,
  "evaluation_duration_ms": float
}
```

The `gate_decision` value maps 1:1 onto RC1–RC5 (`collection_missing`/`entity_parity_failed` → RC1, `not_loaded` → RC2, delta consistent but queries fail → requires a follow-up probe for RC3, `index_missing` → RC4, `connection_failed` while the server is known up → RC5). No per-cause branching in code — the log is the diagnostic.

### Track D — Deliberately Out of Scope

Explicitly NOT implemented in this spec, to prevent scope creep and to honor bugfix clause 3.5:

- **No auto-repair of etcd ↔ MinIO desync.** RC3 is surfaced as a readiness failure; recovery requires operator action (typically a clean stack restart or a controlled re-ingestion, neither of which this spec performs automatically).
- **No auto-reingestion.** The fix never calls `store_embeddings` or any ingestion entry point as a recovery action.
- **No modification of the scoring path.** `QueryDecomposer._find_semantic_matches()` and `KGRetrievalService._aggregate_and_deduplicate()` are not touched (Property 5).
- **No modification of the ingestion field set or schema** (Property 7).
- **No new Milvus collection, no index rebuild, no volume management** (Property 8).
- **No change to the OpenSearch (AWS) path.** `_create_aws_opensearch_client` and the OpenSearch retrieval path are not affected. The readiness gate is gated behind the factory-based `MilvusClient` instance check; on AWS the gate short-circuits to `ready=True` (or is simply not wired into that environment).
- **No Docker Compose healthcheck changes in this spec.** Adding a Milvus healthcheck is a reasonable follow-up that would complement the in-process gate, but it is an infrastructure change and its rollout is not tied to this fix.

## Testing Strategy

### Validation Approach

Two-phase: (1) reproduce the bug on unfixed code with concrete counterexamples keyed to RC1–RC5; (2) verify the fix enforces both the fix-checking and preservation-checking invariants. Unit tests run against a fake Milvus double; integration tests run against the real stack in `docker-compose.yml`.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute each root cause's fingerprint. If a test unexpectedly passes on unfixed code, re-hypothesize.

**Test Plan**: Tests live under `tests/clients/test_milvus_readiness_gate.py` and `tests/integration/test_milvus_post_restart.py`. Unit tests use a fake `VectorStoreClient` + fake `RelationalStoreClient`. Integration tests drive the real `docker-compose.yml` stack with `pytest-docker`.

**Test Cases**:

1. **T1 — RC2 collection-not-loaded**: Spin up the Milvus stack, ingest a small fixture (10 chunks including a synthetic "GenAI page 114" chunk), stop and restart only the `milvus` container, then immediately issue the Chelsea query through the chat endpoint with the app process *not* restarted. Expected on unfixed code: top-10 does not include the synthetic chunk, response is a confident "no information" (targets RC2, bugfix clauses 1.4, 1.7). Expected counterexample: empty or degraded candidate set, no 503.

2. **T2 — RC1 volume-loss**: With the stack running and data ingested, `docker compose down -v`, then `docker compose up`. Verify `utility.has_collection("knowledge_chunks")` is `False` or `num_entities == 0` while PostgreSQL still reports its row count (PostgreSQL is on a different volume, but for this test we seed PostgreSQL independently to guarantee the mismatch). Issue the Chelsea query. Expected on unfixed code: degraded top-10, no error (targets RC1, bugfix clauses 1.5, 1.6). Expected counterexample: `num_entities=0`, `pg_chunk_count>0`, retrieval served anyway.

3. **T3 — RC5 stale-cached-client**: In a single test process: (a) construct `MilvusClient`, connect, `store_embeddings` a fixture, `semantic_search`, verify healthy. (b) Restart Milvus in-place (via `docker compose restart milvus` from the test fixture). (c) Without touching the `MilvusClient` instance, issue a `semantic_search` within the 30-second `_health_check_interval`. Expected on unfixed code: `_cached_health_status.status == "healthy"` despite Milvus uptime being seconds; `_collection_cache` is non-empty and reused; search returns empty or raises (targets RC5, bugfix clauses 1.4, 1.9). Expected counterexample: stale cache served.

4. **T4 — (auxiliary) RC4 missing-vector-index**: Use `utility.drop_index` on a test collection, then verify the readiness gate reports `gate_decision="index_missing"` and the chat endpoint returns 503 (targets RC4, bugfix clause 1.8). This is an edge-case test; it does not attempt repair.

**Expected Counterexamples**:
- T1: chat response body contains `"no information about ... Chelsea"` and sources list is empty of the synthetic chunk.
- T2: `num_entities=0` while PostgreSQL reports a positive row count; no 503.
- T3: `MilvusClient._cached_health_status["status"] == "healthy"` is returned within 30 s of a Milvus restart.
- T4: `collection.indexes` is empty on the `vector` field while search returns a non-empty but misleading result set.

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed pipeline either returns the correct result or returns the deterministic 503.

**Pseudocode:**

```
FOR ALL input WHERE isBugCondition(input) DO
  readiness := get_milvus_readiness()
  status    := await readiness.readiness_status()

  // Property 3 — readiness evaluates all five sub-checks
  ASSERT status.gate_decision IN
         { "ready",
           "connection_failed", "collection_missing",
           "not_loaded", "index_missing",
           "entity_parity_failed" }

  // Property 2 — deterministic outcome
  request_result := await chatEndpoint.handle(chelsea_query)
  IF status.ready THEN
    ASSERT request_result.status_code == 200
    // Property 1 — correctness once ready
    IF fixtureIncludesGenAIPage114() THEN
      ASSERT request_result.sources CONTAINS
             (title.endsWith("GenAI") AND page_number == 114)
    END IF
  ELSE
    ASSERT request_result.status_code == 503
    ASSERT request_result.json.detail STARTS_WITH "retrieval_index_not_ready:"
    ASSERT request_result.json.detail CONTAINS status.gate_decision
  END IF

  // Property 4 — desync yields refusal, never silent degradation
  IF isSimulatedDesync(input) THEN
    ASSERT request_result.status_code == 503
    ASSERT NO destructive action was taken against volumes
  END IF

  // Track B — single retry, no infinite loop
  ASSERT searchRetryCount(input) <= 1
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed pipeline behaves byte-identically to the pre-fix pipeline.

**Pseudocode:**

```
FOR ALL input WHERE NOT isBugCondition(input) DO
  // Property 5 — scoring byte-identity
  pre  := preFixKGRetrieve(input.query)
  post := postFixKGRetrieve(input.query)
  ASSERT pre.candidate_set == post.candidate_set          // same chunks
  ASSERT pre.ranking       == post.ranking                // same order
  ASSERT pre.relevance_scores == post.relevance_scores    // same scores

  // Property 6 — title contract unchanged
  FOR chunk IN post.sources DO
    ASSERT chunk.title == preFixTitleFor(chunk.id)
    ASSERT NOT postgresEnrichTitlesWasCalled()
  END FOR

  // Property 7 — ingestion field set unchanged
  FOR doc IN ingestedDocs DO
    ASSERT milvusSchema(doc.collection) == EXPECTED_SCHEMA
    ASSERT metadataFields(doc) ==
           { "content", "content_type", "stored_at",
             "source_id", "chunk_index", "page_number",
             "title", "_vector_id" }
    ASSERT contentHash(doc.chunks) == preFixContentHash(doc.chunks)
  END FOR

  // Property 8 — no destructive recovery
  ASSERT volumeState(milvus_data, etcd_data, minio_data,
                     postgres_data, neo4j_data) UNCHANGED
  ASSERT NOT utilityDropCollectionWasCalled()

  // Property 9 — no extra round-trips on healthy path
  baseline := measureLatency(preFixChatEndpoint, input.query)
  fixed    := measureLatency(postFixChatEndpoint, input.query)
  ASSERT fixed.milvus_round_trips == baseline.milvus_round_trips
  ASSERT fixed.postgres_round_trips == baseline.postgres_round_trips
  ASSERT fixed.p95_latency_ms <= baseline.p95_latency_ms * 1.05
END FOR
```

**Testing Approach**: Property-based testing is a good fit for the preservation half of the suite because:
- The healthy-path invariants (same candidate set, same ranking, same scores, same schema) must hold across a large space of queries and document corpora.
- Randomly generated small-document fixtures exercise edge cases at the parity tolerance boundary (`delta == tolerance`, `delta == tolerance + 1`).
- PBT generates many input sequences of `(ingest, query, restart, query)` to explore reconnection / retry paths without hand-written cases.

For fix-checking (the 503 contract) PBT is less natural because the observable is categorical (200 vs 503 + decision string); example-based tests are a better fit there.

**Test Plan**: Observe unfixed behavior on healthy collections first using the existing `tests/services/test_kg_retrieval_service.py` suite as a baseline — record the pre-fix candidate set, ranking, and relevance scores for a small set of golden queries (including the Chelsea query against a seeded fixture). Then write post-fix tests that assert byte-identity against those recorded baselines.

**Test Cases**:

1. **Scoring parity**: Against a healthy fixture, assert `KGRetrievalService.retrieve(q)` produces the same `(candidate_set, ranking, relevance_scores)` before and after the fix for every query in `tests/fixtures/kg_retrieval_golden_queries.jsonl`.
2. **Title contract parity**: Against a healthy fixture, assert titles in the Sources panel are identical pre/post and that `_enrich_chunks_with_titles` is not invoked (monkeypatched to raise).
3. **Ingestion parity**: Run `celery_service.store_embeddings_task` on a fixture PDF; assert the Milvus schema, metadata field set, and content hashes match pre-fix values.
4. **Volume non-destruction**: Record `docker volume inspect` output before and after running the full fix-checking suite; assert byte-identity.
5. **Healthy-path latency**: Measure p95 chat latency on a warm cache; assert ≤ 5 % overhead vs baseline.

### Unit Tests

- **`test_readiness_gate_all_decisions`**: For each `gate_decision` branch (`ready`, `collection_missing`, `not_loaded`, `index_missing`, `entity_parity_failed`, `connection_failed`), inject a fake `VectorStoreClient` that produces the corresponding state and assert `ReadinessStatus.gate_decision` matches.
- **`test_readiness_gate_parity_tolerance`**: Parameterize over `(pg_count, milvus_count)` with `pg_count` in `{0, 1, 50, 100, 5000}` and `abs(pg - milvus)` spanning the tolerance boundary; assert exactly the values within `tolerance(pg_count)` return `ready=True`.
- **`test_readiness_gate_caches_ready_for_ttl`**: Call `is_ready()` twice within `ready_cache_ttl_seconds`; assert the underlying fake client is called only once (Property 9).
- **`test_readiness_gate_invalidate_on_runtime_failure`**: Call `is_ready()` → True, then `invalidate()`, then `is_ready()` — assert re-evaluation.
- **`test_milvus_client_track_b_single_retry`**: Mock `collection.search` to raise `MilvusException("collection not loaded")` once, then succeed; assert exactly one retry and one subsequent success.
- **`test_milvus_client_track_b_no_infinite_loop`**: Mock to raise twice; assert the second failure propagates as `QueryError`.
- **`test_dependency_cleanup_closes_readiness_gate`**: Populate `_milvus_readiness_gate`, call `cleanup_all_dependencies`; assert `gate.close()` was awaited and `_milvus_readiness_gate is None` afterward.

### Property-Based Tests

- **Property: readiness cache monotonicity on the healthy path**: `@given(num_requests in [1, 100])` — when the underlying state is healthy for the duration, `is_ready()` calls underlying probes at most `ceil(num_requests * request_interval / ready_cache_ttl)` times.
- **Property: scoring byte-identity on healthy collections**: `@given(query_strategy())` — `KGRetrievalService.retrieve` output is identical pre- and post-fix when the gate reports `ready=True`.
- **Property: deterministic 503 body shape**: `@given(gate_decision_strategy)` — the chat endpoint's 503 response body always contains `"retrieval_index_not_ready: "` followed by one of the six decision tokens.
- **Property: no destructive call is ever made**: `@given(arbitrary_gate_decisions_over_time)` — across any sequence of evaluations, `utility.drop_collection` and volume-deletion calls are never invoked by gate code.

### Integration Tests

- **`test_integration_post_restart_readiness`**: End-to-end reproduction of T1 (collection-not-loaded) — spin up the stack, ingest, restart `milvus`, verify the chat endpoint returns 503 with `gate_decision="not_loaded"` at least once, then verify it recovers to 200 and returns the synthetic GenAI-page-114 chunk once `Collection.load()` completes.
- **`test_integration_post_restart_volume_loss`**: End-to-end reproduction of T2 — `docker compose down -v`, then `docker compose up`, verify chat returns 503 with `gate_decision="collection_missing"` or `"entity_parity_failed"`.
- **`test_integration_context_switching`**: Verify that after a restart and readiness recovery, the Sources panel title-fallback contract, ingestion field set, and scoring parity all hold on a golden query set.
- **`test_integration_healthy_path_latency`**: Run a 100-query warm-up and 100-query measurement loop against a healthy stack; assert p95 latency is within 5 % of a pre-fix baseline recorded from the current `main` branch.
