# Implementation Plan

- [x] 1. Write bug condition exploration tests
  - **Property 1: Bug Condition** - Post-Restart CollectionStateInvariant Violation Served Silently
  - **CRITICAL**: These tests MUST FAIL on unfixed code — failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: These tests encode the expected behavior — they will validate the fix when they pass after implementation
  - **GOAL**: Surface counterexamples that demonstrate the retrieval endpoint silently serves a degraded candidate set when `isBugCondition(EnvironmentSample)` holds, keyed to RC1 (volume loss), RC2 (collection not loaded), RC3 (etcd↔MinIO desync), RC4 (index unattached), RC5 (stale cached client)
  - **Scoped PBT Approach**: For each probable RC, scope the property to the concrete failing fingerprint from design `isBugCondition` pseudocode
  - Create unit test file `tests/clients/test_milvus_readiness_gate_bug_condition.py`:
    - Uses fake `VectorStoreClient` + fake `RelationalStoreClient` — no Docker required
    - **PBT — RC1 Volume Loss**: Hypothesis strategy generates `EnvironmentSample` where `has_collection=False` OR `num_entities=0` while `pg_chunk_count>0`. Assert gate returns `ReadinessStatus(ready=False, gate_decision IN {"collection_missing", "entity_parity_failed"})` and chat endpoint returns 503 with body starting `retrieval_index_not_ready:` (design P2, P3)
    - **PBT — RC2 Collection Not Loaded**: Strategy generates `has_collection=True, num_entities>0, collection_loaded=False`. Assert `gate_decision == "not_loaded"` and 503 surfaces; retrieval is NOT served
    - **PBT — RC5 Stale Cached Client**: Strategy generates `client_cache_stale=True` (cached `_collection_cache` non-empty, `_cached_health_status.status=="healthy"`, connection state stale). Assert Track B invalidates cache on runtime `MilvusException("collection not loaded")` OR `ConnectionNotExistException` and surfaces 503 through the gate's `invalidate()` callback
    - **Example-based — RC4 Index Missing**: Construct `collection.indexes == []` on `vector` field. Assert `gate_decision == "index_missing"` (crafted state; PBT not applicable)
    - **Example-based — RC3 etcd↔MinIO Desync**: Construct a sample where `has_collection=True, num_entities>0` but `collection.query(expr="id in [<known_id>]")` returns empty. Assert gate refuses (design P4) and NO destructive action is taken against any volume (design P8)
  - Create integration test file `tests/integration/test_milvus_post_restart_bug_condition.py`:
    - Uses `pytest-docker` against the real `docker-compose.yml` stack
    - **T1 — RC2 end-to-end**: Ingest 10-chunk fixture including synthetic "GenAI page 114 Chelsea AI Ventures" chunk → `docker compose restart milvus` → submit Chelsea query without app restart → assert response is 503 `retrieval_index_not_ready: not_loaded` (encodes expected behavior per bugfix 1.4, 1.7, 2.3). On recovery, assert 200 with GenAI page 114 chunk in top-10 (bugfix 2.1, 2.2)
    - **T2 — RC1 end-to-end**: `docker compose down -v` → `docker compose up` with PostgreSQL seeded independently → submit Chelsea query → assert 503 `retrieval_index_not_ready: collection_missing` OR `entity_parity_failed` (bugfix 1.5, 1.6, 2.3)
    - **T3 — RC5 end-to-end**: In-process `MilvusClient` + ingest → `docker compose restart milvus` → `semantic_search` within 30 s `_health_check_interval` → assert either 503 through gate OR transparent Track B retry succeeds; assert `_cached_health_status` is NOT served stale (bugfix 1.4, 1.9)
  - Test assertions MUST match the Expected Behavior Properties P1, P2, P3, P4 from design — each test encodes the behavior after the fix, not the current buggy behavior
  - Run tests on UNFIXED code: `pytest tests/clients/test_milvus_readiness_gate_bug_condition.py tests/integration/test_milvus_post_restart_bug_condition.py -v`
  - **EXPECTED OUTCOME**: Tests FAIL (correct — no gate exists yet, retrieval endpoint returns 200 with degraded results instead of 503)
  - Document counterexamples found (e.g., "chat endpoint returns 200 with empty sources list after `docker compose restart milvus` instead of 503 `not_loaded`")
  - Mark task complete when tests are written, run, and failures are documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Healthy-Path Byte-Identity and Non-Destructive Invariants
  - **IMPORTANT**: Follow observation-first methodology — record actual unfixed-code behavior first, then assert that behavior with property-based tests
  - Create unit test file `tests/clients/test_milvus_readiness_gate_preservation.py`:
    - Observe on UNFIXED code: `KGRetrievalService.retrieve(q)` output for golden queries (scoring candidate set, ranking, relevance scores)
    - Observe on UNFIXED code: title-metadata contract — filename-derived fallback surfaces in Sources panel when PDF title is empty/None/missing; `_enrich_chunks_with_titles` is not invoked
    - Observe on UNFIXED code: ingestion schema — `(id VARCHAR, vector FLOAT_VECTOR, metadata JSON)`; metadata fields `{content, content_type, stored_at, source_id, chunk_index, page_number, title, _vector_id}`; chunk counts and content hashes
    - **PBT — P5 Scoring Byte-Identity**: Hypothesis strategy generates healthy-collection queries. Assert `pre_fix.candidate_set == post_fix.candidate_set`, `pre_fix.ranking == post_fix.ranking`, `pre_fix.relevance_scores == post_fix.relevance_scores` (bugfix 3.1, 3.2)
    - **PBT — P6 Title Contract**: For all chunks in Sources panel, `chunk.title == preFixTitleFor(chunk.id)` and `_enrich_chunks_with_titles` was NOT called (monkeypatched to raise) (bugfix 3.3)
    - **PBT — P7 Ingestion Schema**: For all ingested docs, Milvus schema and metadata field set are byte-identical to pre-fix; content hashes unchanged (bugfix 3.4)
    - **PBT — P8 Non-Destructive**: Across any sequence of gate evaluations, `utility.drop_collection` is never invoked, and no volume delete is ever called (bugfix 3.5, 3.7)
    - **PBT — P9 Healthy-Path Latency**: For all requests against a healthy collection with readiness cached, `is_ready()` causes at most one underlying probe per `ready_cache_ttl_seconds` window; no extra Milvus or PostgreSQL round-trip on the request path (bugfix 3.6)
  - Create integration test file `tests/integration/test_milvus_post_restart_preservation.py`:
    - **Scoring parity**: Use golden query set to assert `KGRetrievalService.retrieve` output is byte-identical pre/post fix on a healthy stack
    - **Ingestion parity**: Run `celery_service.store_embeddings_task` on a fixture PDF; assert Milvus schema, metadata field set, and content hashes match pre-fix values
    - **Volume non-destruction**: Record `docker volume inspect milvus_data etcd_data minio_data postgres_data neo4j_data` before and after the full fix-checking suite; assert byte-identity
    - **Healthy-path latency**: 100-query warm-up + 100-query measurement; assert p95 latency ≤ baseline × 1.05
  - **NOTE**: `tests/fixtures/kg_retrieval_golden_queries.jsonl` does NOT exist in the repo. This task MUST also create a small golden-query fixture at that path covering the Chelsea query plus 4–6 other queries that exercise the scoring path (queries with specific named entities, queries with only generic concepts, multi-concept queries). Record the pre-fix `(candidate_set, ranking, relevance_scores)` tuple per query against a seeded healthy stack and commit the fixture
  - Run tests on UNFIXED code: `pytest tests/clients/test_milvus_readiness_gate_preservation.py tests/integration/test_milvus_post_restart_preservation.py -v`
  - **EXPECTED OUTCOME**: Tests PASS (confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [x] 3. Fix for Milvus post-restart retrieval regression — deterministic readiness gate + narrow reconnection retry + structured observability

  - [x] 3.1 Track C — Introduce `ReadinessStatus` dataclass and `milvus_readiness_evaluated` structured log
    - Create new file `src/multimodal_librarian/clients/milvus_readiness_gate.py`
    - Define `@dataclass(frozen=True) class ReadinessStatus` with fields per design Track A: `ready: bool, collection_exists: bool, is_loaded: bool, has_vector_index: bool, num_entities: int, pg_chunk_count: int, delta: int, tolerance: int, gate_decision: str, evaluated_at: float`
    - `gate_decision` is one of `{"ready", "collection_missing", "not_loaded", "index_missing", "entity_parity_failed", "connection_failed"}`
    - Add module-level `structlog` logger. Emit `milvus_readiness_evaluated` event at `INFO` when `ready=True` and at `WARNING` otherwise, with the full field set from design Track C
    - **DO NOT** wire the gate into DI yet — this task lands the data shape + log contract only; zero runtime impact
    - _Bug_Condition_: observability gap — without this log, RC1–RC5 cannot be distinguished post-restart
    - _Expected_Behavior_: a single `milvus_readiness_evaluated` event per evaluation, at `INFO` (ready) or `WARNING` (not ready), containing `gate_decision` that maps 1:1 onto RC1–RC5 per design Track C table
    - _Preservation_: no runtime change — logger only emits when called; no caller yet
    - _Requirements: 2.3, 2.4_

  - [x] 3.2 Track A — Implement `MilvusReadinessGate` in `src/multimodal_librarian/clients/milvus_readiness_gate.py`
    - Public API per design Track A: `__init__(vector_client, relational_client, collection_name="knowledge_chunks", parity_tolerance_fraction=0.01, ready_cache_ttl_seconds=30.0, not_ready_cache_ttl_seconds=2.0)`, `async is_ready() -> bool`, `async readiness_status() -> ReadinessStatus`, `async invalidate() -> None`, `async close() -> None`
    - Implement `evaluateReadiness` pseudocode verbatim from design:
      1. If `vector_client` not connected → `vector_client.connect()`; on raise → `gate_decision="connection_failed"`
      2. `has_collection := utility.has_collection(collection_name)`; if False → `gate_decision="collection_missing"`
      3. `collection := Collection(collection_name, using=vector_client.connection_name)`; run `collection.load()` in executor; on `MilvusException` → `gate_decision="not_loaded"`
      4. `indexes := collection.indexes`; if no index with `field_name=="vector"` → `gate_decision="index_missing"`
      5. `num_entities := collection.num_entities`
      6. `pg_chunk_count := SELECT COUNT(*) FROM multimodal_librarian.knowledge_chunks`
      7. `tolerance := max(1, ceil(parity_tolerance_fraction * pg_chunk_count))`
      8. `delta := pg_chunk_count - num_entities`; if `abs(delta) > tolerance` → `gate_decision="entity_parity_failed"`
      9. Otherwise → `gate_decision="ready"`, `ready=True`
    - Caching: ready-path TTL 30 s, not-ready TTL 2 s (aggressive re-eval while recovering); invalidate on `invalidate()`, TTL expiry, or `close()`
    - Emit the Track C log event at the end of every evaluation
    - _Bug_Condition_: post-restart `CollectionStateInvariant` violated and retrieval endpoint served anyway (`isBugCondition` from design returns True)
    - _Expected_Behavior_: `ReadinessStatus` with one of six `gate_decision` values; healthy-path `is_ready()` returns `True` in O(1) after first evaluation within the TTL (design P3, P9)
    - _Preservation_: Track C log contract unchanged (emits from exactly one call site); gate is a pure reader — no writes to Milvus, PostgreSQL, or volumes (design P8); parity tolerance floor of 1 with 1% fraction handles in-flight batches without masking volume loss
    - _Requirements: 2.3, 2.4, 2.5, 2.6_

  - [x] 3.3 Track A — Wire `MilvusReadinessGate` through DI and into user-facing retrieval endpoints
    - Modify `src/multimodal_librarian/api/dependencies/services.py`:
      - Add module-level `_milvus_readiness_gate: Optional["MilvusReadinessGate"] = None`
      - Add `async def get_milvus_readiness(vector_client = Depends(get_vector_client_optional), relational_client = Depends(get_relational_client_optional)) -> MilvusReadinessGate` exactly per design Track A DI wiring: lazy singleton, raises `HTTPException(503, "retrieval_index_not_ready: readiness gate dependencies unavailable")` when deps unavailable
      - Add `async def get_milvus_readiness_optional(...) -> Optional[MilvusReadinessGate]` that returns `None` instead of raising
      - In `clear_all_caches()`: add `global _milvus_readiness_gate` and set `_milvus_readiness_gate = None`
      - In `cleanup_all_dependencies()`: `if _milvus_readiness_gate is not None: await _milvus_readiness_gate.close()` before `clear_all_caches()`
    - Wire into routers: search `src/multimodal_librarian/api/routers/` for handlers that use `Depends(get_kg_retrieval_service)` or `Depends(get_cached_rag_service)` (chat query path, any endpoint calling `KGRetrievalService.retrieve` or `RAGService.query`, plus the chat WebSocket send path). Add `readiness: MilvusReadinessGate = Depends(get_milvus_readiness)` plus `status = await readiness.readiness_status(); if not status.ready: raise HTTPException(503, f"retrieval_index_not_ready: {status.gate_decision}")`
    - **DO NOT** gate: health check endpoints, ingestion endpoints (`POST /documents`, Celery tasks), `/api/status`, `/api/metrics`
    - Respect DI steering contract: no import-time connections, lazy init, singleton via module-level `_variable`, proper cleanup hooks
    - _Bug_Condition_: retrieval endpoints serving 200 despite failed `CollectionStateInvariant` after Milvus restart
    - _Expected_Behavior_: deterministic 503 with body `retrieval_index_not_ready: <gate_decision>` on not-ready; 200 on ready; single O(1) boolean check per request on healthy path (design P2, P9)
    - _Preservation_: non-retrieval endpoints (health, ingestion, status, metrics) unchanged; DI steering compliance — no import-time Milvus or PostgreSQL connection opened; AWS `OpenSearchClient` path short-circuits past the gate per design Track D
    - _Requirements: 2.3, 3.6_

  - [x] 3.4 Track B — One-shot reconnection / reload retry in `MilvusClient` search path
    - Modify `src/multimodal_librarian/clients/milvus_client.py`:
      - In `search_vectors` (lines ~1900–1996) and `semantic_search` (lines ~700–900): wrap the core body in `try/except MilvusException`
      - Classify the exception: match `"collection not loaded" in str(e).lower()` OR `isinstance(e, pymilvus.exceptions.ConnectionNotExistException)` OR message contains `"failed to connect" / "connection refused" / "channel not available"`
      - On classified failure: (a) drop entry from `self._collection_cache[name]`, (b) set `self._connected = False`, (c) single re-run of `self.connect()` + `self._get_collection(name)` + `collection.load()` in executor, (d) retry the search exactly once
      - On second failure: raise `QueryError`; do NOT loop
      - Register a failure-callback hook `self.register_failure_callback(callback)` stored on the client. In `MilvusReadinessGate.__init__`, call `vector_client.register_failure_callback(self.invalidate)` so Track B's runtime failure invalidates the gate's cached `ready=True` on the next request
    - _Bug_Condition_: RC5 — stale cached `Collection` handle in `MilvusClient._collection_cache` is reused across a Milvus server restart and serves empty/degraded results; design `isBugCondition` with `client_cache_stale=True`
    - _Expected_Behavior_: search either recovers on a single transparent retry after reconnect + reload OR surfaces 503 through Track A on the next request via the invalidate callback; no infinite loop; retry count ≤ 1 per request (design P2)
    - _Preservation_: retry is path-local (search only) — ingestion path (`store_embeddings`, `insert_vectors`), schema, `flush()` semantics, content hashes, and non-search code paths of `MilvusClient` are unchanged (design P7); existing `_run_with_retry` for generic `MilvusException` at lines ~521–545 is untouched
    - _Requirements: 1.4, 1.9, 2.3_

  - [x] 3.5 Verify bug condition exploration tests now PASS
    - **Property 1: Expected Behavior** - Post-Restart Readiness Enforces Deterministic Outcome
    - **IMPORTANT**: Re-run the SAME tests from task 1 — do NOT write new tests
    - The tests from task 1 encode the expected behavior; passing now confirms the fix addresses each RC fingerprint
    - Run: `pytest tests/clients/test_milvus_readiness_gate_bug_condition.py tests/integration/test_milvus_post_restart_bug_condition.py -v`
    - **EXPECTED OUTCOME**: All tests PASS (confirms bug is fixed for RC1, RC2, RC4, RC5; RC3 tests pass by asserting refusal + non-destruction)
    - If any test still fails: STOP and surface to the user. Do NOT modify the test — the test encodes the expected behavior per design P1–P4
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [x] 3.6 Verify preservation tests still PASS
    - **Property 2: Preservation** - Healthy-Path Byte-Identity and Non-Destructive Invariants
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - Run: `pytest tests/clients/test_milvus_readiness_gate_preservation.py tests/integration/test_milvus_post_restart_preservation.py -v`
    - **EXPECTED OUTCOME**: All tests PASS (confirms no regressions on healthy path; design P5, P6, P7, P8, P9)
    - Confirm scoring byte-identity, title contract, ingestion schema, non-destructive behavior, and latency bounds all hold
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [x] 4. Checkpoint — Ensure all tests pass and DI steering compliance holds
  - Run focused suite: `pytest tests/clients/test_milvus_readiness_gate_bug_condition.py tests/clients/test_milvus_readiness_gate_preservation.py tests/integration/test_milvus_post_restart_bug_condition.py tests/integration/test_milvus_post_restart_preservation.py -v`
  - Run existing adjacent suites for wider regression confidence: `pytest tests/services/test_kg_retrieval_service.py tests/clients/ -k milvus -v`
  - DI steering compliance check — verify no import-time Milvus connection: run in a fresh process `python -c "import multimodal_librarian; import sys; assert 'pymilvus.connections' not in sys.modules or not getattr(sys.modules.get('pymilvus.connections'), '_connections', {}).get('default'), 'import opened a Milvus connection'"` and assert exit code 0
  - Verify Track C log event fires: grep structured logs for `milvus_readiness_evaluated` and confirm `gate_decision` appears at least once during the integration suite
  - Verify no destructive calls: assert `utility.drop_collection` is not referenced in any file under `src/multimodal_librarian/clients/milvus_readiness_gate.py` or newly touched lines in `src/multimodal_librarian/clients/milvus_client.py` (bugfix 3.5, design P8)
  - Ensure all tests pass; ask the user if questions arise
  - **Closing note (2026-05-07):** The original post-restart retrieval symptom ("Chelsea AI Ventures" query returning unrelated top-10 sources after `docker compose restart etcd minio milvus`) could NOT be reproduced end-to-end under the exact procedure after the gate was wired in. Live reproduction with baseline → restart etcd/minio/milvus → wait for healthy → query returned `Generative AI With LangChain` page 114 at relevance 1.0 on the first (cold, 12.1 s) and second (warm, 10.1 s) attempts, matching the pre-restart baseline byte-for-byte. The readiness gate reported `gate_decision=ready`, `delta=-1`, `num_entities=223916`, `pg_chunk_count=223915`, `is_loaded=True`, `has_vector_index=True`.
  - **Gate parity-SQL correction:** The initial implementation of `_PG_CHUNK_COUNT_SQL` in `src/multimodal_librarian/clients/milvus_readiness_gate.py` counted only `multimodal_librarian.knowledge_chunks` and omitted `multimodal_librarian.bridge_chunks`. Because `_store_bridge_embeddings_in_vector_db` (see `services/celery_service.py`) inserts LLM-generated bridge vectors into the SAME Milvus `knowledge_chunks` collection, the parity probe produced a permanent false-positive `entity_parity_failed` on any system that had ever run bridge generation. The SQL was updated to sum both tables so the invariant holds as `num_entities ≈ pg_chunk_count + pg_bridge_count`.
  - **Retained value:** The gate remains in place as a defensive readiness check covering RC5 (stale cached client after a silent Milvus restart), RC2 (collection not loaded), RC4 (index missing), and genuine RC1 volume loss. Its Track C structured log (`milvus_readiness_evaluated`) gives future incidents an actionable fingerprint. Cost on the healthy path is one cached boolean read per request plus one Milvus + Postgres probe per 30 s window.
  - **Not reproduced → not fixed in spec, but also not further investigated:** The most plausible hypotheses for the original incident are (a) a transient cold-load race at the very first post-restart query that self-healed via `search_vectors`' in-path `collection.load()` call at `clients/milvus_client.py` line ~1914, or (b) an RC5 stale-client scenario that requires a long-running app process against a silently restarted Milvus to surface. No further hardening work is pursued under this spec; any follow-up resilience work should begin with a reproducible failure, not speculation.

