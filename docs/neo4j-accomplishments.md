# Neo4j / Cypher Engineering — Accomplishment Write-up

**Project:** Multimodal Librarian — a clinical-knowledge retrieval system built on a Neo4j knowledge graph (document-extracted concepts, UMLS clinical relationships, and concept embeddings) fronting a hybrid KG + vector retrieval pipeline.

The three areas below overlap by design — "writing Cypher" and "writing Neo4j queries" are the same craft — so I've split them by focus: *query authoring* (the Cypher constructs), *query discipline* (how queries are written safely), and *performance tuning* (making them fast and reliable). Each point is illustrated with the actual query or code.

## 1. Cypher Queries — Advanced Query Patterns

### Multi-hop path traversal with `shortestPath`

Finding the reasoning path between two concepts (e.g. a disease and a drug), returning the node names and relationship types along the way:

```cypher
MATCH (start:Concept), (end:Concept)
WHERE start.name_lower CONTAINS toLower($start_name)
  AND end.name_lower CONTAINS toLower($end_name)
  AND start <> end
WITH start, end LIMIT 1
MATCH path = shortestPath((start)-[*1..3]-(end))
RETURN
    start.name AS start_concept,
    end.name   AS end_concept,
    [node in nodes(path) | node.name]              AS path_nodes,
    [rel  in relationships(path) | type(rel)]      AS path_relationships,
    length(path)                                   AS path_length
LIMIT $limit
```

### Bounded variable-length traversal with per-edge filtering

Exploring a concept's neighborhood up to N hops, restricted to a whitelist of relationship types and ranked by distance then confidence:

```cypher
MATCH (start:Concept)
WHERE start.name_lower CONTAINS toLower($concept_name)
WITH start LIMIT 1
MATCH path = (start)-[r:RELATED_TO|IS_A|PART_OF*1..2]-(related:Concept)
WHERE related <> start
RETURN DISTINCT
    related.name                                    AS name,
    length(path)                                    AS distance,
    [rel in relationships(path) | type(rel)]        AS relationship_types
ORDER BY distance ASC, related.confidence DESC
LIMIT $limit
```

### Pattern comprehension for degree

Computing a node's degree inline — without an `OPTIONAL MATCH` + `count()` that would inflate the intermediate row cardinality:

```cypher
WITH n, size([(n)-[]->(:Concept) | 1]) AS degree
```

### Correlated `EXISTS { }` subqueries

Source-scoped filtering where a node is only kept if it is actually extracted from a chunk of the current document:

```cypher
OPTIONAL MATCH (local:Concept)
WHERE local.name_lower = toLower($focus_concept)
  AND EXISTS { MATCH (local)-[:EXTRACTED_FROM]->(lch:Chunk {source_id: $source_id}) }
WITH local LIMIT 1
```

### `OPTIONAL MATCH` + `coalesce` for graceful fallback

Resolving a focus concept against the current source first, then falling back to any source (so a cross-source node is still clickable):

```cypher
OPTIONAL MATCH (any:Concept)
WHERE any.name_lower = toLower($focus_concept)
  AND local IS NULL
WITH coalesce(local, any) AS focus
```

### In-query vector similarity

Two ways to do semantic matching inside the database itself — cosine via `gds.similarity.cosine`, and native KNN via the vector index:

```cypher
-- cosine computed in-query, ordered and limited before returning
MATCH (c:Concept)
WHERE c.embedding IS NOT NULL
WITH c, gds.similarity.cosine(c.embedding, $query_embedding) AS similarity
ORDER BY similarity DESC
LIMIT $limit
```

```cypher
-- native vector index for bridging a lay term to a canonical UMLS concept
CALL db.index.vector.queryNodes('umls_embedding_index', $top_k, $embedding)
YIELD node, score
WHERE score >= $threshold
RETURN node.cui AS cui, score AS score
ORDER BY score DESC LIMIT 1
```

### UMLS clinical-reasoning bridge

The most complex path authored: walking `Concept → SAME_AS → UMLSConcept → UMLS_REL → UMLSConcept ← SAME_AS ← Concept`, bridging back to document concepts on *both* sides so treatment-related chunks reachable via a clinical relationship are surfaced even when the target concept wasn't matched in the query:

```cypher
MATCH (a:Concept {concept_id: $concept_id_a})-[:SAME_AS|SIMILAR_TO]-(ua:UMLSConcept)
MATCH (b:Concept {concept_id: $concept_id_b})-[:SAME_AS|SIMILAR_TO]-(ub:UMLSConcept)
MATCH (ua)-[r:UMLS_REL]-(ub)
WHERE r.rela_type IN $clinical_rela
OPTIONAL MATCH (cb_ua:Concept)-[:SAME_AS|SIMILAR_TO]-(ua)
OPTIONAL MATCH (cb_ub:Concept)-[:SAME_AS|SIMILAR_TO]-(ub)
WITH a, b, ua, r, ub,
     collect(DISTINCT a) + collect(DISTINCT b) +
     collect(DISTINCT cb_ua) + collect(DISTINCT cb_ub) AS concept_nodes
UNWIND concept_nodes AS n
OPTIONAL MATCH (n)-[:EXTRACTED_FROM]->(ch:Chunk)
RETURN DISTINCT ch.chunk_id      AS chunk_id,
                r.rela_type      AS umls_relationship,
                'umls_1hop'      AS path_type
```

### Shared-chunk co-occurrence

Capturing implicit relationships — two concepts that appear in the same document passage even when no explicit edge connects them:

```cypher
MATCH (a:Concept {concept_id: $concept_id_a})-[:EXTRACTED_FROM]->(ch:Chunk)
      <-[:EXTRACTED_FROM]-(b:Concept {concept_id: $concept_id_b})
RETURN DISTINCT ch.chunk_id AS chunk_id,
                'shared_chunk' AS path_type
LIMIT $max_paths
```

### Bulk idempotent writes with `UNWIND … MERGE`

Batch-creating `SAME_AS` edges between extracted concepts and canonical UMLS concepts in one round-trip:

```cypher
UNWIND $items AS item
MATCH (c:Concept) WHERE c.name_lower = item.lower_name
MATCH (u:UMLSConcept {cui: item.cui})
MERGE (c)-[r:SAME_AS]->(u)
ON CREATE SET r.match_type = item.match_type, r.created_at = item.created_at
RETURN count(r) AS cnt
```

## 2. Writing Neo4j Queries — Discipline & Safety

Beyond individual queries, established the *patterns for writing* them so they're correct, safe, and maintainable.

### Parameterization for values, validated formatting for structure

Every runtime value flows through Cypher parameters. The only string-interpolated pieces are *structural* — relationship-type lists and hop counts — assembled from an allowlist and never from user input:

```python
rel_types = "|".join(self.CLINICALLY_RELEVANT_RELATIONSHIPS)

cypher = (
    f"MATCH path = (a:Concept {{concept_id: $concept_id_a}})"
    f"-[:{rel_types}*1..{self._hop_limit}]"
    f"-(b:Concept {{concept_id: $concept_id_b}}) "
    f"WITH path, nodes(path) AS path_nodes "
    f"LIMIT $max_paths "
    f"UNWIND path_nodes AS n "
    f"OPTIONAL MATCH (n)-[:EXTRACTED_FROM]->(ch:Chunk) "
    f"RETURN DISTINCT ch.chunk_id AS chunk_id"
)

parameters = {
    "concept_id_a": concept_id_a,
    "concept_id_b": concept_id_b,
    "max_paths": self._max_paths_per_pair,
}
```

### Parameter-key and type validation before every query

```python
for key, value in parameters.items():
    if not isinstance(key, str) or not key.isidentifier():
        raise ValidationError(f"Invalid parameter key: {key}")
    if isinstance(value, (str, int, float, bool, list, dict)):
        sanitized[key] = value
    else:
        sanitized[key] = str(value)
```

### Strict read/write separation

Reads go through `execute_query`; writes through `execute_write_query`, which wraps the call in a driver-managed write transaction — so transactional semantics and retry behavior are enforced at the API boundary rather than left to callers:

```python
async def _run_write_session(self, query, sanitized_params):
    async with self.driver.session(database=self.database) as session:
        async def write_transaction(tx):
            result = await tx.run(query, sanitized_params)
            ...
        return await session.execute_write(write_transaction)
```

### Idempotent schema and MERGE-based writes

All node/edge creation uses `MERGE … ON CREATE SET` so re-runs are safe, and the relationship traverser is explicitly read-only:

```cypher
MERGE (c)-[r:SAME_AS]->(u)
ON CREATE SET r.match_type = item.match_type
```

### Self-documenting queries with named builders

Each query lives in its own builder method (`_build_pair_cypher`, `_build_umls_pair_cypher`, `_build_umls_2hop_cypher`, `_build_shared_chunk_cypher`), so the intent and edge cases of every query are explicit and individually testable.

### Strategic query selection

Rather than one monolithic query, the traverser composes up to four strategies per concept pair in order of clinical specificity — UMLS 1-hop → UMLS 2-hop → direct document edges → shared-chunk co-occurrence — giving precedence to the highest-signal path:

```python
strategies: List[Tuple[str, Any]] = []
if has_umls_bridges:
    strategies.append(("umls_1hop", self._build_umls_pair_cypher))
    strategies.append(("umls_2hop", self._build_umls_2hop_cypher))
strategies.append(("direct", self._build_pair_cypher))
strategies.append(("shared_chunk", self._build_shared_chunk_cypher))
```

## 3. Performance Tuning with Neo4j

This is where most of the effort and impact lived — driven by a measured problem: graph traversal was the dominant cost in a ~22s chat pipeline (retrieval ≈ 66% of latency, from fan-out across ~15k-chunk concept neighborhoods).

### Index strategy — the biggest lever

A single idempotent `ensure_indexes` pass creates every index and constraint, `IF NOT EXISTS` everywhere. Full-text for query decomposition, a precomputed `name_lower` so case-insensitive lookups avoid `toLower(c.name)` full scans (a real regression caught and fixed), unique constraints doubling as backing indexes, and cosine vector indexes:

```cypher
CREATE FULLTEXT INDEX concept_name_fulltext IF NOT EXISTS
  FOR (c:Concept) ON EACH [c.name]

CREATE INDEX concept_name_lower IF NOT EXISTS
  FOR (c:Concept) ON (c.name_lower)

CREATE CONSTRAINT concept_id_unique IF NOT EXISTS
  FOR (c:Concept) REQUIRE c.concept_id IS UNIQUE

CREATE CONSTRAINT chunk_id_unique IF NOT EXISTS
  FOR (ch:Chunk) REQUIRE ch.chunk_id IS UNIQUE

CALL db.index.vector.createNodeIndex(
  'concept_embedding_index', 'Concept', 'embedding', 768, 'cosine')
```

Index creation is skipped on reconnect — recreating a full-text index can transiently make it unavailable and return empty results:

```python
if not self._indexes_ensured:
    await self.ensure_indexes()
    self._indexes_ensured = True
```

### Bounded, budgeted traversal

The traverser enforces hard cost limits so multi-concept queries can't blow the latency budget: a total 3s ceiling, per-query timeouts carved out of the remaining budget, and short-circuiting the expensive 2-hop UMLS pass when 1-hop already resolved the pair:

```python
for cid_a, cid_b in pairs:
    for strategy_name, cypher_builder in strategies:
        elapsed = time.monotonic() - start_time
        if elapsed >= self._timeout_seconds:
            total_timeout_reached = True
            break

        # Skip 2-hop UMLS when 1-hop already found paths for this pair
        if strategy_name == "umls_2hop" and pair_key in pairs_with_umls_1hop:
            continue

        remaining = self._timeout_seconds - elapsed
        query_timeout = max(0.3, remaining * 0.5)
        records = await asyncio.wait_for(
            self._execute_cypher(cypher, params),
            timeout=query_timeout,
        )
```

Concept count is capped at 5 (bounding `C(n,2)` pair generation), and each pair is limited to `max_paths=50`.

### Cheap pre-check to skip whole strategies

Before running any UMLS traversal, one `LIMIT 1` query determines whether any matched concept even bridges to UMLS — if not, all UMLS strategies are skipped, preserving the timeout budget for non-clinical queries:

```cypher
MATCH (c:Concept)-[:SAME_AS|SIMILAR_TO]-(:UMLSConcept)
WHERE c.concept_id IN $concept_ids
RETURN count(c) > 0 AS has_bridge
LIMIT 1
```

### Bulk-write batching

`UNWIND … MERGE` runs in sub-batches — 200 names per match pass, 500 edges per merge pass — to avoid Neo4j transaction timeouts on large UMLS imports:

```python
MATCH_BATCH = 200
for sb_start in range(0, len(concept_names), MATCH_BATCH):
    sb_names = concept_names[sb_start:sb_start + MATCH_BATCH]
    batch_matches = await self._match_concepts_batch(sb_names)
    ...
# then MERGE SAME_AS edges in batches of 500
```

Failed batches retry with exponential backoff (1s, 2s, 4s).

### Connection-pool & driver resilience

An async driver with explicit pool sizing, keepalive to prevent idle TCP transports from closing, and exponential-backoff retry on transient errors:

```python
driver_kwargs = {
    "auth": (self.user, self.password),
    "max_connection_lifetime": 3600,
    "max_connection_pool_size": 50,
    "connection_acquisition_timeout": 60,
    "max_transaction_retry_time": 30,
    "keep_alive": True,
}
driver = AsyncGraphDatabase.driver(self.uri, **driver_kwargs)
```

```python
# keepalive ping to stop the TCP transport closing when idle
while True:
    await asyncio.sleep(self._keepalive_interval)  # 15s
    async with self.driver.session(database=self.database) as session:
        result = await session.run("RETURN 1")
        await result.consume()
```

```python
# transient-error retry with exponential backoff
except TransientError as e:
    retry_count += 1
    if retry_count >= max_retries:
        raise QueryError(...)
    await asyncio.sleep(0.1 * (2 ** retry_count))
```

The driver is also rebuilt when it's detected on a different event loop (the Neo4j async driver is single-loop-bound), avoiding "Future attached to a different loop" failures across `asyncio.run()` boundaries.

### Orphaned-transaction cleanup

Diagnosed a production incident where killing a client left `apoc.periodic.iterate` transactions running as orphans holding locks. The fix moved writes to bounded-chunk loops and added explicit orphan cleanup:

```cypher
SHOW TRANSACTIONS
YIELD transactionId, currentQuery, elapsedTime
-- then terminate the stale transactionId
```

### Observability

Queries are wrapped by a `log_neo4j_queries` decorator, and a pool optimizer samples graph statistics to surface recommendations (large-graph, high-connectivity):

```python
stats_queries = {
    "node_count":         "MATCH (n) RETURN count(n) AS count",
    "relationship_count": "MATCH ()-[r]->() RETURN count(r) AS count",
    "label_count":        "CALL db.labels() YIELD label RETURN count(label) AS count",
}
```

**Net effect:** the graph layer went from an in-memory, restart-fragile dictionary to a persistent, indexed Neo4j backend with safe parameterized queries, idempotent batch writes, and hard latency budgets — turning the knowledge graph into the system's actual reasoning substrate rather than a lookup cache.
