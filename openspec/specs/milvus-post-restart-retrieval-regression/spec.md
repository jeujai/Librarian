## Purpose

After a Docker services restart that includes the Milvus stack (`etcd`, `minio`, `milvus` — see `docker-compose.yml`), the reference query "What did our team observe at Chelsea?" no longer retrieves the GenAI book page 114 chunk about Chelsea AI Ventures. Instead, the chat UI reports that there is no information about any team's observations at Chelsea, and the Sources panel is populated entirely by unrelated documents: Forsyth & Ponce's *Computer Vision: A Modern Approach* at 97% relevance, *Ferris Clinical Advisor 2021* page 1827 at 90%, *Artificial Intelligence: A Modern Approach, 3rd Edition*, Stockley's *Drug Interactions*, *Goodman & Gilman's The Pharmacological Basis of Therapeutics* page 1478, and several clinical/medical papers — none of which reference the GenAI book or Chelsea AI Ventures. The Milvus `knowledge_chunks` collection is configured via `MILVUS_COLLECTION_NAME=knowledge_chunks` in `docker-compose.yml`, and the named volumes `etcd_data`, `minio_data`, and `milvus_data` are declared at the bottom of the compose file, so a plain restart (without `down -v` or a volume prune) is expected to preserve the collection's data on disk.

Two adjacent specs characterize behaviors that this bug interacts with but neither covers the present regression:

- `.kiro/specs/chelsea-query-semantic-noise/` (all tasks complete) fixed `QueryDecomposer._find_semantic_matches()` parameters and coverage-bonus inflation in `_aggregate_and_deduplicate()` — its trigger was "queries with observation verbs against a healthy collection", not a service restart. Its scoring fixes presuppose that the target chunk is present in the candidate set.
- `.kiro/specs/milvus-title-metadata-fix/` addresses "Unknown" titles in citation metadata, not retrieval correctness or candidate-set coverage.

This bugfix characterizes the post-restart retrieval regression in terms of what is *observable* — the user-visible failure, the top-10 Sources panel, and the state of the Milvus standalone stack (`pymilvus.utility.has_collection`, `Collection.num_entities`, `Collection.load()` load state, MinIO segment object presence, etcd metadata consistency) — without prematurely committing to a single root cause. The Requirements phase defines what must be true after the fix; the Design phase will triage the candidate root causes (volume state lost, collection not reloaded into memory, etcd ↔ minio ↔ milvus metadata/segment desync, index or partition not reattached, pre-existing scoring fix silently defeated by a missing candidate) and pick an intervention.


### Defect Description
The defect is observed end-to-end (the chat UI returns the wrong answer with unrelated top sources) and can be characterized at the retrieval layer (the GenAI book page 114 chunk is absent from or not returned in the candidate set) and at the Milvus stack layer (one or more of collection presence, entity count, load state, or segment-to-metadata consistency no longer holds the post-ingestion invariant). The defect is silent: no "not ready" or "collection unavailable" error surfaces to the user.

1.1 WHEN the query "What did our team observe at Chelsea?" is submitted through the chat UI after a Docker restart of `etcd`, `minio`, and `milvus` THEN the system returns an AI response stating there is no information about any team's observations at Chelsea

1.2 WHEN the query "What did our team observe at Chelsea?" is submitted through the chat UI after a Docker restart of `etcd`, `minio`, and `milvus` THEN the top-10 Sources panel contains no chunk from the GenAI book (no source whose title identifies the GenAI book and whose page number is 114)

1.3 WHEN the query "What did our team observe at Chelsea?" is submitted through the chat UI after a Docker restart of `etcd`, `minio`, and `milvus` THEN the top-10 Sources panel is populated entirely by documents that do not discuss Chelsea AI Ventures (observed: *Computer Vision: A Modern Approach* at 97%, *Ferris Clinical Advisor 2021* page 1827 at 90%, *adult_oi* page 163 at 68%, *Goodman & Gilman's Pharmacological Basis of Therapeutics* page 1478 at 65%, *Artificial Intelligence: A Modern Approach, 3rd Edition* at 65% and 64%, *ciae104* page 120 at 64%, a tuberculosis clinical guideline at 64%, *s00134-021-06506-y* page 1230 at 64%, *Stockley's Drug Interactions* at 64%)

1.4 WHEN the Chelsea query is submitted after the restart and no GenAI book page 114 chunk is present in the Milvus candidate set THEN the system silently returns an unrelated top-10 source list instead of surfacing a "retrieval index not ready" or "candidate set unavailable" error to the user

1.5 WHEN `pymilvus.utility.has_collection("knowledge_chunks")` is evaluated against the Milvus instance after the restart THEN the returned value may be `False` (collection missing from the restarted stack), indicating that the post-ingestion invariant "the `knowledge_chunks` collection exists" no longer holds

1.6 WHEN the `knowledge_chunks` collection exists after the restart AND `Collection("knowledge_chunks").num_entities` is read THEN the returned count may be zero or materially lower than the pre-restart count and than the row count of `multimodal_librarian.knowledge_chunks` in PostgreSQL, indicating that the post-ingestion invariant "Milvus entity count equals PostgreSQL chunk count" no longer holds

1.7 WHEN the `knowledge_chunks` collection exists after the restart AND a semantic search is issued against it without the application having first invoked `Collection("knowledge_chunks").load()` since the restart THEN the search may return empty or degraded results because Milvus standalone requires a loaded collection to serve queries, and the retrieval pipeline then falls through to whatever candidates remain (yielding the unrelated top-10 observed above)

1.8 WHEN the `knowledge_chunks` collection exists after the restart AND the GenAI book page 114 chunk's vector row is queried by `id` or filtered by `source_id` / `page_number` metadata THEN the row may be missing from Milvus (or its associated segment object may be unreadable from MinIO, or its etcd metadata entry may be inconsistent with the MinIO segment set), indicating that the post-ingestion invariant "every row in PostgreSQL `knowledge_chunks` has a corresponding retrievable vector in Milvus" no longer holds

1.9 WHEN the Chelsea query is submitted after the restart THEN the `chelsea-query-semantic-noise` specificity filter and weighted coverage-bonus (already merged in `QueryDecomposer._find_semantic_matches()` and `KGRetrievalService._aggregate_and_deduplicate()`) operate on a candidate set that does not contain the GenAI book page 114 chunk, so their correct scoring has no material effect on the final ranking

1.10 WHEN unrelated queries that previously returned correct results are submitted after the restart THEN those queries may also return degraded or unrelated results for the same underlying reason as 1.5–1.8, but the user-reported symptom is concentrated on the Chelsea query because it is the reference case being validated

## Requirements

### Requirement: Expected Behavior: Bugfix

The system SHALL correctly handle bugfix as specified in the expected behavior.

#### Scenario 2.1

- **WHEN** the query "What did our team observe at Chelsea?" is submitted through the chat UI after a Docker restart of `etcd`, `minio`, and `milvus` (with named volumes preserved)
- **THEN** the system SHALL return the GenAI book page 114 chunk within the top-10 Sources panel (with a title that identifies the GenAI book and a page number of 114), matching the pre-restart retrieval behavior

#### Scenario 2.2

- **WHEN** the query "What did our team observe at Chelsea?" is submitted through the chat UI after a Docker restart of `etcd`, `minio`, and `milvus` (with named volumes preserved)
- **THEN** the system SHALL produce an AI response that draws on the GenAI book page 114 content about Chelsea AI Ventures instead of stating that there is no information

#### Scenario 2.3

- **WHEN** the application accepts a retrieval request after a restart of the Milvus stack AND the `knowledge_chunks` collection is not yet in a retrievable state (collection missing, collection not loaded, entity count not consistent with PostgreSQL, or segment-to-metadata inconsistency detected)
- **THEN** the system SHALL either (a) complete re-establishment of the loaded, consistent state before returning any retrieval result, or (b) return a deterministic "retrieval index not ready" error to the caller, but SHALL NOT silently return a top-N result list drawn from a degraded candidate set

#### Scenario 2.4

- **WHEN** the Milvus stack has completed restart AND the application begins serving retrieval requests
- **THEN** the system SHALL verify that `pymilvus.utility.has_collection("knowledge_chunks")` returns `True` and that the collection's entity count is consistent with the PostgreSQL `multimodal_librarian.knowledge_chunks` row count before declaring the retrieval path ready

#### Scenario 2.5

- **WHEN** the Milvus stack has completed restart AND the `knowledge_chunks` collection is present
- **THEN** the system SHALL ensure the collection is loaded into memory via `Collection("knowledge_chunks").load()` (and that its index is attached) before issuing the first user-facing semantic search against it

#### Scenario 2.6

- **WHEN** the Milvus stack has completed restart AND an inconsistency is detected between etcd metadata and the MinIO segment set for the `knowledge_chunks` collection
- **THEN** the system SHALL either actively repair the inconsistency as part of startup or SHALL refuse to serve retrieval requests that depend on the affected collection until the inconsistency is resolved, rather than serving a partial candidate set

#### Scenario 2.7

- **WHEN** the `knowledge_chunks` collection is in a retrievable state AND the Chelsea query is submitted
- **THEN** the system SHALL continue to rank the GenAI book page 114 chunk above unrelated chunks, because the candidate set once again contains that chunk

### Requirement: Regression Prevention: Bugfix

The system SHALL CONTINUE TO maintain existing correct behavior for bugfix after the fix.

#### Scenario 3.1

- **WHEN** the Chelsea query is submitted against a healthy `knowledge_chunks` collection
- **THEN** the system SHALL CONTINUE TO apply the `chelsea-query-semantic-noise` specificity filter in `QueryDecomposer._find_semantic_matches()` (generic verb-derived concepts removed, `semantic_max_results` and `similarity_threshold` at their tightened defaults) and the weighted coverage-bonus in `KGRetrievalService._aggregate_and_deduplicate()` (generic concepts excluded from the `log2(num_specific_concepts) * 0.1` bonus) with unchanged inputs, intermediate values, and outputs

#### Scenario 3.2

- **WHEN** any query is submitted against a healthy `knowledge_chunks` collection and that query's pre-bugfix top-N source list contains the correct chunks
- **THEN** the system SHALL CONTINUE TO contain those same chunks in the same order, with the same relevance scores

#### Scenario 3.3

- **WHEN** a chunk is retrieved from Milvus and its title metadata is populated correctly per `.kiro/specs/milvus-title-metadata-fix/` (filename-derived fallback used when the PDF metadata title is empty, `None`, or missing)
- **THEN** the system SHALL CONTINUE TO surface that title in the chat UI Sources panel without invoking the PostgreSQL `_enrich_chunks_with_titles()` workaround

#### Scenario 3.4

- **WHEN** a document is uploaded and ingested through the upload pipeline (PDF extraction, chunking, embedding, Milvus insert, PostgreSQL insert, Neo4j concept extraction)
- **THEN** the system SHALL CONTINUE TO complete ingestion with the same chunk counts, same content hashes, same metadata fields (`source_id`, `chunk_index`, `chunk_type`, `content_type`, `page_number`, `title`), and same PostgreSQL ↔ Milvus ↔ Neo4j relationships as before the bugfix

#### Scenario 3.5

- **WHEN** the Docker stack is started or restarted
- **THEN** the system SHALL CONTINUE TO preserve the contents of the named volumes `etcd_data`, `minio_data`, `milvus_data`, `postgres_data`, and `neo4j_data` — specifically, the bugfix SHALL NOT delete, recreate, or reinitialize these volumes as a recovery action, and SHALL NOT drop the `knowledge_chunks` collection as a recovery action without explicit operator intervention

#### Scenario 3.6

- **WHEN** retrieval requests are submitted against a healthy `knowledge_chunks` collection (collection present, loaded, entity count consistent with PostgreSQL)
- **THEN** the system SHALL CONTINUE TO serve those requests without any added latency, extra round-trips, or readiness gating beyond what existed before the bugfix

#### Scenario 3.7

- **WHEN** the application shuts down cleanly (e.g., `docker compose down` without `-v`)
- **THEN** the system SHALL CONTINUE TO leave the `etcd_data`, `minio_data`, and `milvus_data` volumes in a state from which a subsequent `docker compose up` restores the `knowledge_chunks` collection to a retrievable state under the fix's restart semantics
