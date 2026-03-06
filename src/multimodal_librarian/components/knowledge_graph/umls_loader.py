"""
UMLS Loader Component.

Offline data loading tool for preprocessing and bulk-loading UMLS
(Unified Medical Language System) data files into Neo4j. Supports
a tiered approach: Lite Tier (semantic network only) and Full Tier
(Metathesaurus concepts and relationships).

All UMLS data uses UMLS-prefixed labels (UMLSSemanticType, UMLSConcept)
and UMLS_ prefixed relationships for namespace isolation.
"""

from dataclasses import dataclass
from typing import Any, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class LoadResult:
    """Result of a UMLS data loading operation."""

    nodes_created: int
    relationships_created: int
    batches_completed: int
    batches_failed: int
    elapsed_seconds: float
    resumed_from_batch: Optional[int] = None


@dataclass
class DryRunResult:
    """Result of a dry-run estimation before importing UMLS data."""

    estimated_nodes: int
    estimated_relationships: int
    estimated_memory_mb: float
    recommended_vocabs: Optional[List[str]] = None
    fits_in_budget: bool = True


@dataclass
class UMLSStats:
    """Statistics about loaded UMLS data in Neo4j."""

    concept_count: int
    semantic_type_count: int
    relationship_count: int
    loaded_tier: str  # "none", "lite", "full"
    umls_version: Optional[str] = None
    load_timestamp: Optional[str] = None


class UMLSLoader:
    """Bulk-loads UMLS data files into Neo4j.

    Supports two tiers:
      - Lite: Semantic Network only (127 types, 54 relationships)
      - Full: Metathesaurus concepts (MRCONSO) and relationships (MRREL)

    All Neo4j labels use UMLS prefixes for namespace isolation.
    """

    def __init__(self, neo4j_client: Any) -> None:
        self._neo4j = neo4j_client
        logger.info("umls_loader_initialized")

    async def _execute_batch_with_retry(
        self,
        query: str,
        params: dict,
        max_retries: int = 3,
    ) -> list:
        """Execute a write query with retry and exponential backoff.

        Retries failed batches up to max_retries times with delays
        of 1s, 2s, 4s (exponential backoff).

        Args:
            query: Cypher write query to execute.
            params: Query parameters.
            max_retries: Maximum number of retry attempts (default 3).

        Returns:
            Query result list.

        Raises:
            Exception: If all retries are exhausted.
        """
        import asyncio

        backoff_delays = [1, 2, 4]
        last_exception = None

        for attempt in range(max_retries + 1):
            try:
                return await self._neo4j.execute_write_query(
                    query, params
                )
            except Exception as exc:
                last_exception = exc
                if attempt < max_retries:
                    delay = backoff_delays[attempt]
                    logger.warning(
                        "batch_retry",
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        delay_seconds=delay,
                        error=str(exc),
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "batch_retries_exhausted",
                        attempts=max_retries + 1,
                        error=str(exc),
                    )

        raise last_exception

    async def create_indexes(self) -> None:
        """Create Neo4j indexes for UMLS nodes before data import."""
        index_queries = [
            (
                "CREATE INDEX umls_concept_cui IF NOT EXISTS "
                "FOR (c:UMLSConcept) ON (c.cui)"
            ),
            (
                "CREATE INDEX umls_concept_name IF NOT EXISTS "
                "FOR (c:UMLSConcept) ON (c.preferred_name)"
            ),
            (
                "CREATE INDEX umls_semtype_id IF NOT EXISTS "
                "FOR (s:UMLSSemanticType) ON (s.type_id)"
            ),
        ]
        for query in index_queries:
            await self._neo4j.execute_query(query)
        logger.info("umls_indexes_created", count=len(index_queries))

    async def load_semantic_network(self, srdef_path: str) -> LoadResult:
        """Load UMLS Semantic Network from SRDEF file (Lite Tier).

        Parses the SRDEF pipe-delimited file to extract:
        - Semantic type definitions (STY records) → UMLSSemanticType nodes
        - Relationship definitions (RL records) → stored as metadata
        - Tree-number hierarchy → UMLS_SEMANTIC_REL edges (isa parent-child)

        Creates/updates a UMLSMetadata singleton node with loaded_tier="lite".

        Args:
            srdef_path: Path to the SRDEF file.

        Returns:
            LoadResult with counts of nodes and relationships created.

        Raises:
            FileNotFoundError: If the SRDEF file does not exist.
        """
        import os
        import time
        from datetime import datetime, timezone

        start_time = time.time()

        if not os.path.exists(srdef_path):
            raise FileNotFoundError(
                f"SRDEF file not found: {srdef_path}"
            )

        # Parse SRDEF file
        semantic_types = []
        relationship_defs = []

        with open(srdef_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                fields = line.split("|")
                if len(fields) < 5:
                    logger.warning(
                        "srdef_malformed_row",
                        line_num=line_num,
                        content=line[:100],
                    )
                    continue

                record_type = fields[0].strip()
                if record_type == "STY":
                    semantic_types.append({
                        "type_id": fields[1].strip(),
                        "type_name": fields[2].strip(),
                        "tree_number": fields[3].strip(),
                        "definition": (
                            fields[4].strip()
                            if len(fields) > 4
                            else ""
                        ),
                    })
                elif record_type == "RL":
                    rel_inverse = ""
                    if len(fields) > 9:
                        rel_inverse = fields[9].strip()
                    elif len(fields) > 1:
                        rel_inverse = fields[-1].strip()
                    relationship_defs.append({
                        "rel_id": fields[1].strip(),
                        "relation_name": fields[2].strip(),
                        "tree_number": fields[3].strip(),
                        "definition": (
                            fields[4].strip()
                            if len(fields) > 4
                            else ""
                        ),
                        "relation_inverse": rel_inverse,
                    })

        logger.info(
            "srdef_parsed",
            semantic_types=len(semantic_types),
            relationship_defs=len(relationship_defs),
        )

        nodes_created = 0
        relationships_created = 0

        # Create UMLSSemanticType nodes using MERGE for idempotency
        if semantic_types:
            create_types_query = """
            UNWIND $types AS t
            MERGE (s:UMLSSemanticType {type_id: t.type_id})
            SET s.type_name = t.type_name,
                s.definition = t.definition,
                s.tree_number = t.tree_number
            RETURN count(s) as count
            """
            result = await self._neo4j.execute_write_query(
                create_types_query, {"types": semantic_types}
            )
            nodes_created = result[0]["count"] if result else 0
            logger.info("umls_semantic_types_created", count=nodes_created)

        # Build tree-number-to-type_id mapping for hierarchy edges
        tree_to_type_id = {
            st["tree_number"]: st["type_id"] for st in semantic_types
        }

        # Derive parent-child UMLS_SEMANTIC_REL edges
        # from tree number hierarchy.
        # e.g., tree_number "A1.1.1" has parent "A1.1"
        hierarchy_edges = []
        for st in semantic_types:
            tn = st["tree_number"]
            # Find parent by removing last segment
            if "." in tn:
                parent_tn = tn.rsplit(".", 1)[0]
                if parent_tn in tree_to_type_id:
                    hierarchy_edges.append({
                        "parent_type_id": tree_to_type_id[parent_tn],
                        "child_type_id": st["type_id"],
                        "relation_name": "isa",
                        "relation_inverse": "inverse_isa",
                        "definition": (
                            "Hierarchical is-a relationship"
                            " derived from tree numbers"
                        ),
                    })

        if hierarchy_edges:
            create_hierarchy_query = (
                "UNWIND $edges AS e "
                "MATCH (parent:UMLSSemanticType "
                "{type_id: e.parent_type_id}) "
                "MATCH (child:UMLSSemanticType "
                "{type_id: e.child_type_id}) "
                "MERGE (child)-[r:UMLS_SEMANTIC_REL "
                "{relation_name: e.relation_name}]"
                "->(parent) "
                "SET r.relation_inverse = "
                "e.relation_inverse, "
                "r.definition = e.definition "
                "RETURN count(r) as count"
            )
            result = await self._neo4j.execute_write_query(
                create_hierarchy_query, {"edges": hierarchy_edges}
            )
            relationships_created += result[0]["count"] if result else 0
            logger.info(
                "umls_hierarchy_edges_created",
                count=relationships_created,
            )

        # Store relationship definitions (RL records) as additional
        # UMLS_SEMANTIC_REL edges on the UMLSMetadata node for reference
        if relationship_defs:
            create_rel_defs_query = """
            UNWIND $rels AS r
            MERGE (rd:UMLSRelationshipDef {rel_id: r.rel_id})
            SET rd.relation_name = r.relation_name,
                rd.relation_inverse = r.relation_inverse,
                rd.definition = r.definition,
                rd.tree_number = r.tree_number
            RETURN count(rd) as count
            """
            result = await self._neo4j.execute_write_query(
                create_rel_defs_query, {"rels": relationship_defs}
            )
            rel_def_count = result[0]["count"] if result else 0
            relationships_created += rel_def_count
            logger.info(
                "umls_relationship_defs_created",
                count=rel_def_count,
            )

        # Create/update UMLSMetadata singleton node
        now_iso = datetime.now(timezone.utc).isoformat()
        metadata_query = """
        MERGE (m:UMLSMetadata {singleton: true})
        SET m.loaded_tier = $loaded_tier,
            m.load_timestamp = $load_timestamp,
            m.umls_version = $umls_version,
            m.import_status = "complete"
        RETURN m
        """
        await self._neo4j.execute_write_query(
            metadata_query,
            {
                "loaded_tier": "lite",
                "load_timestamp": now_iso,
                "umls_version": "2024AA",
            },
        )
        logger.info("umls_metadata_updated", loaded_tier="lite")

        elapsed = time.time() - start_time
        load_result = LoadResult(
            nodes_created=nodes_created,
            relationships_created=relationships_created,
            batches_completed=1,
            batches_failed=0,
            elapsed_seconds=round(elapsed, 3),
        )

        logger.info(
            "umls_semantic_network_loaded",
            nodes_created=load_result.nodes_created,
            relationships_created=load_result.relationships_created,
            elapsed_seconds=load_result.elapsed_seconds,
        )

        return load_result

    async def load_concepts(
        self,
        mrconso_path: str,
        mrsty_path: str,
        source_vocabs: Optional[List[str]] = None,
        batch_size: int = 5000,
        memory_limit_mb: Optional[int] = None,
    ) -> LoadResult:
        """Load UMLS Metathesaurus concepts from MRCONSO (Full Tier).

        Parses MRCONSO pipe-delimited file to extract English-language
        concept entries, aggregates synonyms per CUI, batch-creates
        UMLSConcept nodes, then parses MRSTY to create HAS_SEMANTIC_TYPE
        edges from concepts to semantic types.

        Args:
            mrconso_path: Path to the MRCONSO.csv file.
            mrsty_path: Path to the MRSTY file.
            source_vocabs: Optional list of source vocabularies to
                filter (e.g., ["SNOMEDCT_US", "MSH", "RXNORM"]).
                If None, all vocabularies are included.
            batch_size: Number of nodes per transaction (default 5000).
            memory_limit_mb: Optional memory limit in MB. Stops import
                if estimated memory usage exceeds this limit.

        Returns:
            LoadResult with counts of nodes and relationships created.

        Raises:
            FileNotFoundError: If MRCONSO or MRSTY file does not exist.
        """
        import os
        import time
        from datetime import datetime, timezone

        start_time = time.time()

        if not os.path.exists(mrconso_path):
            raise FileNotFoundError(
                f"MRCONSO file not found: {mrconso_path}"
            )
        if not os.path.exists(mrsty_path):
            raise FileNotFoundError(
                f"MRSTY file not found: {mrsty_path}"
            )

        # --- Version replacement: remove previous data if exists ---
        meta_result = await self._neo4j.execute_query(
            "MATCH (m:UMLSMetadata {singleton: true}) "
            "RETURN m.loaded_tier AS loaded_tier, "
            "m.umls_version AS umls_version"
        )
        if meta_result and meta_result[0].get("loaded_tier") in (
            "lite",
            "full",
        ):
            prev_version = meta_result[0].get("umls_version")
            logger.info(
                "umls_version_replacement",
                previous_version=prev_version,
                message="Removing previous UMLS data before import",
            )
            await self.remove_all_umls_data()

        # Set import_status to in_progress
        now_iso = datetime.now(timezone.utc).isoformat()
        await self._neo4j.execute_write_query(
            "MERGE (m:UMLSMetadata {singleton: true}) "
            "SET m.import_status = 'in_progress', "
            "m.load_timestamp = $ts",
            {"ts": now_iso},
        )

        # --- Pass 1: Parse MRCONSO, aggregate by CUI ---
        source_vocabs_set = (
            set(source_vocabs) if source_vocabs else None
        )
        # cui -> {preferred_name, synonyms, source_vocabulary,
        #         suppressed}
        concepts: dict = {}
        records_processed = 0
        log_interval = 50000

        with open(mrconso_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n").rstrip("\r")
                if not line:
                    continue
                fields = line.split("|")
                if len(fields) < 17:
                    logger.warning(
                        "mrconso_malformed_row",
                        content=line[:120],
                    )
                    continue

                lat = fields[1]
                if lat != "ENG":
                    continue

                sab = fields[11]
                if source_vocabs_set and sab not in source_vocabs_set:
                    continue

                cui = fields[0]
                ts = fields[2]
                stt = fields[4]
                name = fields[14]
                suppress = fields[16]

                if cui not in concepts:
                    concepts[cui] = {
                        "cui": cui,
                        "preferred_name": None,
                        "synonyms": [],
                        "source_vocabulary": sab,
                        "suppressed": suppress != "N",
                    }

                entry = concepts[cui]

                # Preferred name: TS=P and STT=PF
                if ts == "P" and stt == "PF":
                    if entry["preferred_name"] is None:
                        entry["preferred_name"] = name
                    elif name != entry["preferred_name"]:
                        if name not in entry["synonyms"]:
                            entry["synonyms"].append(name)
                else:
                    if (
                        name != entry["preferred_name"]
                        and name not in entry["synonyms"]
                    ):
                        entry["synonyms"].append(name)

                records_processed += 1
                if records_processed % log_interval == 0:
                    elapsed = time.time() - start_time
                    rate = records_processed / elapsed if elapsed > 0 else 0
                    remaining = (
                        "unknown"
                    )
                    logger.info(
                        "mrconso_parse_progress",
                        records_processed=records_processed,
                        concepts_found=len(concepts),
                        elapsed_seconds=round(elapsed, 1),
                        records_per_second=round(rate, 0),
                        eta=remaining,
                    )

        # Fill in preferred_name for CUIs that had no TS=P/STT=PF row
        for cui, entry in concepts.items():
            if entry["preferred_name"] is None:
                if entry["synonyms"]:
                    entry["preferred_name"] = entry["synonyms"].pop(0)
                else:
                    entry["preferred_name"] = cui

        logger.info(
            "mrconso_parsed",
            total_records=records_processed,
            unique_concepts=len(concepts),
            elapsed_seconds=round(time.time() - start_time, 1),
        )

        # --- Memory limit check ---
        if memory_limit_mb is not None:
            estimated_memory_mb = len(concepts) * 2 / 1024
            try:
                import psutil

                process_memory_mb = (
                    psutil.Process().memory_info().rss / (1024 * 1024)
                )
                estimated_memory_mb = max(
                    estimated_memory_mb, process_memory_mb
                )
            except ImportError:
                pass

            if estimated_memory_mb > memory_limit_mb:
                logger.warning(
                    "memory_limit_exceeded",
                    estimated_mb=round(estimated_memory_mb, 1),
                    limit_mb=memory_limit_mb,
                    concepts_loaded=len(concepts),
                )
                await self._neo4j.execute_write_query(
                    "MERGE (m:UMLSMetadata {singleton: true}) "
                    "SET m.import_status = "
                    "'memory_limit_exceeded'",
                    {},
                )
                elapsed = time.time() - start_time
                return LoadResult(
                    nodes_created=0,
                    relationships_created=0,
                    batches_completed=0,
                    batches_failed=0,
                    elapsed_seconds=round(elapsed, 3),
                )

        # --- Pass 2: Batch create UMLSConcept nodes ---
        concept_list = list(concepts.values())
        nodes_created = 0
        batches_completed = 0
        batches_failed = 0

        create_concepts_query = """
        UNWIND $concepts AS c
        MERGE (n:UMLSConcept {cui: c.cui})
        SET n.preferred_name = c.preferred_name,
            n.synonyms = c.synonyms,
            n.source_vocabulary = c.source_vocabulary,
            n.suppressed = c.suppressed
        RETURN count(n) as count
        """

        for i in range(0, len(concept_list), batch_size):
            batch = concept_list[i : i + batch_size]
            batch_num = i // batch_size + 1
            try:
                result = await self._execute_batch_with_retry(
                    create_concepts_query, {"concepts": batch}
                )
                count = result[0]["count"] if result else 0
                nodes_created += count
                batches_completed += 1

                # Update last_batch_number for resume support
                await self._neo4j.execute_write_query(
                    "MERGE (m:UMLSMetadata {singleton: true}) "
                    "SET m.last_batch_number = $batch_num",
                    {"batch_num": batch_num},
                )
            except Exception as exc:
                batches_failed += 1
                logger.error(
                    "concept_batch_failed",
                    batch_num=batch_num,
                    batch_size=len(batch),
                    error=str(exc),
                )

            if (i + batch_size) % log_interval < batch_size:
                elapsed = time.time() - start_time
                total_batches = (
                    len(concept_list) + batch_size - 1
                ) // batch_size
                if batches_completed > 0:
                    eta_seconds = (
                        elapsed
                        / batches_completed
                        * (total_batches - batches_completed)
                    )
                    eta_str = f"{eta_seconds:.0f}s"
                else:
                    eta_str = "unknown"
                logger.info(
                    "concept_load_progress",
                    nodes_created=nodes_created,
                    batches_completed=batches_completed,
                    total_batches=total_batches,
                    elapsed_seconds=round(elapsed, 1),
                    eta=eta_str,
                )

        logger.info(
            "concepts_loaded",
            nodes_created=nodes_created,
            batches_completed=batches_completed,
            batches_failed=batches_failed,
        )

        # --- Pass 3: Parse MRSTY and create HAS_SEMANTIC_TYPE edges ---
        loaded_cuis = set(concepts.keys())
        sty_edges: list = []
        relationships_created = 0

        with open(mrsty_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n").rstrip("\r")
                if not line:
                    continue
                fields = line.split("|")
                if len(fields) < 2:
                    logger.warning(
                        "mrsty_malformed_row",
                        content=line[:120],
                    )
                    continue

                cui = fields[0]
                tui = fields[1]

                if cui not in loaded_cuis:
                    continue

                sty_edges.append({"cui": cui, "tui": tui})

        logger.info(
            "mrsty_parsed",
            edges_to_create=len(sty_edges),
        )

        create_sty_edges_query = """
        UNWIND $edges AS e
        MATCH (c:UMLSConcept {cui: e.cui})
        MATCH (s:UMLSSemanticType {type_id: e.tui})
        MERGE (c)-[r:HAS_SEMANTIC_TYPE]->(s)
        RETURN count(r) as count
        """

        for i in range(0, len(sty_edges), batch_size):
            batch = sty_edges[i : i + batch_size]
            batch_num = i // batch_size + 1
            try:
                result = await self._execute_batch_with_retry(
                    create_sty_edges_query, {"edges": batch}
                )
                count = result[0]["count"] if result else 0
                relationships_created += count
                batches_completed += 1
            except Exception as exc:
                batches_failed += 1
                logger.error(
                    "sty_edge_batch_failed",
                    batch_num=batch_num,
                    batch_size=len(batch),
                    error=str(exc),
                )

        logger.info(
            "sty_edges_loaded",
            relationships_created=relationships_created,
        )

        # --- Update UMLSMetadata ---
        total_concept_batches = (
            (len(concept_list) + batch_size - 1) // batch_size
            if concept_list
            else 0
        )
        now_iso = datetime.now(timezone.utc).isoformat()
        await self._neo4j.execute_write_query(
            "MERGE (m:UMLSMetadata {singleton: true}) "
            "SET m.loaded_tier = 'full', "
            "m.load_timestamp = $ts, "
            "m.last_batch_number = $last_batch, "
            "m.import_status = 'complete'",
            {
                "ts": now_iso,
                "last_batch": total_concept_batches,
            },
        )
        logger.info("umls_metadata_updated", loaded_tier="full")

        elapsed = time.time() - start_time
        load_result = LoadResult(
            nodes_created=nodes_created,
            relationships_created=relationships_created,
            batches_completed=batches_completed,
            batches_failed=batches_failed,
            elapsed_seconds=round(elapsed, 3),
        )

        logger.info(
            "umls_concepts_loaded",
            nodes_created=load_result.nodes_created,
            relationships_created=load_result.relationships_created,
            batches_completed=load_result.batches_completed,
            elapsed_seconds=load_result.elapsed_seconds,
        )

        return load_result

    async def load_relationships(
        self,
        mrrel_path: str,
        source_vocabs: Optional[List[str]] = None,
        batch_size: int = 10000,
    ) -> LoadResult:
        """Load UMLS relationships from MRREL (Full Tier).

        Parses the MRREL pipe-delimited file to extract relationship
        entries between UMLSConcept nodes. Creates UMLS_REL edges with
        properties storing the specific relationship type information.

        Only relationships where BOTH source and target CUIs exist in
        the loaded concept set are created. Optionally filters by
        source vocabulary.

        Args:
            mrrel_path: Path to the MRREL.csv file.
            source_vocabs: Optional list of source vocabularies to
                filter (e.g., ["SNOMEDCT_US", "MSH", "RXNORM"]).
                If None, all vocabularies are included.
            batch_size: Number of edges per transaction (default 10000).

        Returns:
            LoadResult with counts of relationships created.

        Raises:
            FileNotFoundError: If MRREL file does not exist.
        """
        import os
        import time
        from datetime import datetime, timezone

        start_time = time.time()

        if not os.path.exists(mrrel_path):
            raise FileNotFoundError(
                f"MRREL file not found: {mrrel_path}"
            )

        # --- Step 1: Query Neo4j for all loaded UMLSConcept CUIs ---
        loaded_cuis_result = await self._neo4j.execute_query(
            "MATCH (c:UMLSConcept) RETURN c.cui AS cui"
        )
        loaded_cuis: set = set()
        if loaded_cuis_result:
            for record in loaded_cuis_result:
                if record.get("cui"):
                    loaded_cuis.add(record["cui"])

        logger.info(
            "umls_loaded_cuis_fetched",
            loaded_cui_count=len(loaded_cuis),
        )

        if not loaded_cuis:
            logger.warning(
                "umls_no_concepts_loaded",
                message=(
                    "No UMLSConcept nodes found; "
                    "skipping relationship loading"
                ),
            )
            elapsed = time.time() - start_time
            return LoadResult(
                nodes_created=0,
                relationships_created=0,
                batches_completed=0,
                batches_failed=0,
                elapsed_seconds=round(elapsed, 3),
            )

        # --- Step 2: Parse MRREL, filter by vocab and loaded CUIs ---
        source_vocabs_set = (
            set(source_vocabs) if source_vocabs else None
        )
        relationships: list = []
        records_processed = 0
        records_skipped_vocab = 0
        records_skipped_dangling = 0
        log_interval = 50000

        with open(mrrel_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n").rstrip("\r")
                if not line:
                    continue
                fields = line.split("|")
                if len(fields) < 11:
                    logger.warning(
                        "mrrel_malformed_row",
                        content=line[:120],
                    )
                    continue

                cui1 = fields[0]
                rel = fields[3]
                cui2 = fields[4]
                rela = fields[7]
                sab = fields[10]

                records_processed += 1

                # Filter by source vocabulary
                if source_vocabs_set and sab not in source_vocabs_set:
                    records_skipped_vocab += 1
                    if records_processed % log_interval == 0:
                        elapsed = time.time() - start_time
                        logger.info(
                            "mrrel_parse_progress",
                            records_processed=records_processed,
                            relationships_kept=len(relationships),
                            elapsed_seconds=round(elapsed, 1),
                        )
                    continue

                # Skip if BOTH CUIs are absent from loaded set
                if cui1 not in loaded_cuis or cui2 not in loaded_cuis:
                    records_skipped_dangling += 1
                    if records_processed % log_interval == 0:
                        elapsed = time.time() - start_time
                        logger.info(
                            "mrrel_parse_progress",
                            records_processed=records_processed,
                            relationships_kept=len(relationships),
                            elapsed_seconds=round(elapsed, 1),
                        )
                    continue

                # Determine edge type label: UMLS_{RELA} if RELA
                # non-empty, otherwise UMLS_{REL}
                edge_type = (
                    f"UMLS_{rela}" if rela else f"UMLS_{rel}"
                )

                cui_pair = f"{cui1}-{cui2}"

                relationships.append(
                    {
                        "cui1": cui1,
                        "cui2": cui2,
                        "rel_type": rel,
                        "rela_type": rela,
                        "source_vocabulary": sab,
                        "cui_pair": cui_pair,
                        "edge_type": edge_type,
                    }
                )

                if records_processed % log_interval == 0:
                    elapsed = time.time() - start_time
                    logger.info(
                        "mrrel_parse_progress",
                        records_processed=records_processed,
                        relationships_kept=len(relationships),
                        elapsed_seconds=round(elapsed, 1),
                    )

        logger.info(
            "mrrel_parsed",
            total_records=records_processed,
            relationships_to_create=len(relationships),
            skipped_vocab_filter=records_skipped_vocab,
            skipped_dangling=records_skipped_dangling,
            elapsed_seconds=round(time.time() - start_time, 1),
        )

        # --- Step 3: Batch create UMLS_REL edges ---
        relationships_created = 0
        batches_completed = 0
        batches_failed = 0

        create_rels_query = """
        UNWIND $rels AS r
        MATCH (src:UMLSConcept {cui: r.cui1})
        MATCH (tgt:UMLSConcept {cui: r.cui2})
        MERGE (src)-[e:UMLS_REL {cui_pair: r.cui_pair}]->(tgt)
        SET e.rel_type = r.rel_type,
            e.rela_type = r.rela_type,
            e.source_vocabulary = r.source_vocabulary,
            e.edge_type = r.edge_type
        RETURN count(e) as count
        """

        for i in range(0, len(relationships), batch_size):
            batch = relationships[i : i + batch_size]
            batch_num = i // batch_size + 1
            try:
                result = await self._execute_batch_with_retry(
                    create_rels_query, {"rels": batch}
                )
                count = result[0]["count"] if result else 0
                relationships_created += count
                batches_completed += 1
            except Exception as exc:
                batches_failed += 1
                logger.error(
                    "relationship_batch_failed",
                    batch_num=batch_num,
                    batch_size=len(batch),
                    error=str(exc),
                )

            if (i + batch_size) % log_interval < batch_size:
                elapsed = time.time() - start_time
                total_batches = (
                    (len(relationships) + batch_size - 1) // batch_size
                    if relationships
                    else 0
                )
                if batches_completed > 0:
                    eta_seconds = (
                        elapsed
                        / batches_completed
                        * (total_batches - batches_completed)
                    )
                    eta_str = f"{eta_seconds:.0f}s"
                else:
                    eta_str = "unknown"
                logger.info(
                    "relationship_load_progress",
                    relationships_created=relationships_created,
                    batches_completed=batches_completed,
                    total_batches=total_batches,
                    elapsed_seconds=round(elapsed, 1),
                    eta=eta_str,
                )

        # --- Step 4: Update UMLSMetadata with relationship count ---
        now_iso = datetime.now(timezone.utc).isoformat()
        await self._neo4j.execute_write_query(
            "MERGE (m:UMLSMetadata {singleton: true}) "
            "SET m.relationship_count = $rel_count, "
            "m.load_timestamp = $ts",
            {"rel_count": relationships_created, "ts": now_iso},
        )

        elapsed = time.time() - start_time
        load_result = LoadResult(
            nodes_created=0,
            relationships_created=relationships_created,
            batches_completed=batches_completed,
            batches_failed=batches_failed,
            elapsed_seconds=round(elapsed, 3),
        )

        logger.info(
            "umls_relationships_loaded",
            relationships_created=load_result.relationships_created,
            batches_completed=load_result.batches_completed,
            batches_failed=load_result.batches_failed,
            elapsed_seconds=load_result.elapsed_seconds,
        )

        return load_result

    async def dry_run(
        self,
        mrconso_path: str,
        mrrel_path: str,
        source_vocabs: Optional[List[str]] = None,
        memory_budget_mb: int = 2048,
    ) -> DryRunResult:
        """Estimate import size without loading data.

        Scans MRCONSO and MRREL files to count unique CUIs and
        relationships, then estimates memory usage. Returns a
        DryRunResult indicating whether the data fits in the
        configured memory budget.

        Args:
            mrconso_path: Path to the MRCONSO.csv file.
            mrrel_path: Path to the MRREL.csv file.
            source_vocabs: Optional list of source vocabularies to
                filter (e.g., ["SNOMEDCT_US", "MSH", "RXNORM"]).
            memory_budget_mb: Memory budget in MB (default 2048).

        Returns:
            DryRunResult with estimates and budget assessment.

        Raises:
            FileNotFoundError: If MRCONSO or MRREL file does not exist.
        """
        import os

        if not os.path.exists(mrconso_path):
            raise FileNotFoundError(
                f"MRCONSO file not found: {mrconso_path}"
            )
        if not os.path.exists(mrrel_path):
            raise FileNotFoundError(
                f"MRREL file not found: {mrrel_path}"
            )

        source_vocabs_set = (
            set(source_vocabs) if source_vocabs else None
        )

        # Scan MRCONSO for unique CUIs (English only, filtered by vocab)
        unique_cuis: set = set()
        with open(mrconso_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n").rstrip("\r")
                if not line:
                    continue
                fields = line.split("|")
                if len(fields) < 17:
                    continue

                lat = fields[1]
                if lat != "ENG":
                    continue

                sab = fields[11]
                if source_vocabs_set and sab not in source_vocabs_set:
                    continue

                unique_cuis.add(fields[0])

        estimated_nodes = len(unique_cuis)

        # Scan MRREL for relationship count
        estimated_relationships = 0
        with open(mrrel_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n").rstrip("\r")
                if not line:
                    continue
                fields = line.split("|")
                if len(fields) < 11:
                    continue

                cui1 = fields[0]
                cui2 = fields[4]
                sab = fields[10]

                if source_vocabs_set and sab not in source_vocabs_set:
                    continue

                # Only count if both CUIs are in the loaded set
                if cui1 in unique_cuis and cui2 in unique_cuis:
                    estimated_relationships += 1

        # Estimate memory: ~2KB per concept, ~0.5KB per relationship
        estimated_memory_mb = (
            estimated_nodes * 2 / 1024
            + estimated_relationships * 0.5 / 1024
        )

        fits_in_budget = estimated_memory_mb <= memory_budget_mb

        recommended_vocabs = None
        if not fits_in_budget:
            recommended_vocabs = ["SNOMEDCT_US", "MSH", "RXNORM"]

        logger.info(
            "umls_dry_run_complete",
            estimated_nodes=estimated_nodes,
            estimated_relationships=estimated_relationships,
            estimated_memory_mb=round(estimated_memory_mb, 1),
            fits_in_budget=fits_in_budget,
        )

        return DryRunResult(
            estimated_nodes=estimated_nodes,
            estimated_relationships=estimated_relationships,
            estimated_memory_mb=round(estimated_memory_mb, 2),
            recommended_vocabs=recommended_vocabs,
            fits_in_budget=fits_in_budget,
        )

    async def remove_all_umls_data(self) -> None:
        """Remove all UMLS nodes and relationships from Neo4j.

        Deletes in order:
        1. All UMLS_REL relationships
        2. All UMLS_SEMANTIC_REL relationships
        3. All HAS_SEMANTIC_TYPE relationships
        4. All UMLSConcept nodes (DETACH DELETE)
        5. All UMLSSemanticType nodes (DETACH DELETE)
        6. All UMLSRelationshipDef nodes (DETACH DELETE)
        7. All UMLSMetadata nodes (DETACH DELETE)
        """
        delete_queries = [
            (
                "MATCH ()-[r:UMLS_REL]->() DELETE r",
                "umls_rel_relationships",
            ),
            (
                "MATCH ()-[r:UMLS_SEMANTIC_REL]->() DELETE r",
                "umls_semantic_rel_relationships",
            ),
            (
                "MATCH ()-[r:HAS_SEMANTIC_TYPE]->() DELETE r",
                "has_semantic_type_relationships",
            ),
            (
                "MATCH (n:UMLSConcept) DETACH DELETE n",
                "umls_concept_nodes",
            ),
            (
                "MATCH (n:UMLSSemanticType) DETACH DELETE n",
                "umls_semantic_type_nodes",
            ),
            (
                "MATCH (n:UMLSRelationshipDef) DETACH DELETE n",
                "umls_relationship_def_nodes",
            ),
            (
                "MATCH (n:UMLSMetadata) DETACH DELETE n",
                "umls_metadata_nodes",
            ),
        ]

        for query, label in delete_queries:
            await self._neo4j.execute_write_query(query, {})
            logger.info("umls_data_deleted", target=label)

        logger.info("umls_all_data_removed")

    async def get_umls_stats(self) -> UMLSStats:
        """Return statistics about loaded UMLS data.

        Queries Neo4j for counts of UMLSConcept nodes,
        UMLSSemanticType nodes, UMLS_REL relationships, and
        metadata from the UMLSMetadata singleton node.

        Returns:
            UMLSStats with counts and metadata.
        """
        # Count UMLSConcept nodes
        concept_result = await self._neo4j.execute_query(
            "MATCH (c:UMLSConcept) RETURN count(c) AS count"
        )
        concept_count = (
            concept_result[0]["count"]
            if concept_result
            else 0
        )

        # Count UMLSSemanticType nodes
        semtype_result = await self._neo4j.execute_query(
            "MATCH (s:UMLSSemanticType) RETURN count(s) AS count"
        )
        semantic_type_count = (
            semtype_result[0]["count"]
            if semtype_result
            else 0
        )

        # Count UMLS_REL relationships
        rel_result = await self._neo4j.execute_query(
            "MATCH ()-[r:UMLS_REL]->() RETURN count(r) AS count"
        )
        relationship_count = (
            rel_result[0]["count"]
            if rel_result
            else 0
        )

        # Get metadata
        meta_result = await self._neo4j.execute_query(
            "MATCH (m:UMLSMetadata {singleton: true}) "
            "RETURN m.loaded_tier AS loaded_tier, "
            "m.umls_version AS umls_version, "
            "m.load_timestamp AS load_timestamp"
        )

        loaded_tier = "none"
        umls_version = None
        load_timestamp = None

        if meta_result and meta_result[0].get("loaded_tier"):
            loaded_tier = meta_result[0]["loaded_tier"]
            umls_version = meta_result[0].get("umls_version")
            load_timestamp = meta_result[0].get("load_timestamp")

        logger.info(
            "umls_stats_retrieved",
            concept_count=concept_count,
            semantic_type_count=semantic_type_count,
            relationship_count=relationship_count,
            loaded_tier=loaded_tier,
        )

        return UMLSStats(
            concept_count=concept_count,
            semantic_type_count=semantic_type_count,
            relationship_count=relationship_count,
            loaded_tier=loaded_tier,
            umls_version=umls_version,
            load_timestamp=load_timestamp,
        )

    async def resume_import(
        self,
        mrconso_path: str,
        mrsty_path: str,
        source_vocabs: Optional[List[str]] = None,
        batch_size: int = 5000,
        memory_limit_mb: Optional[int] = None,
    ) -> LoadResult:
        """Resume an interrupted import from the last successful batch.

        Reads last_batch_number from UMLSMetadata, calculates how many
        concepts to skip, then calls load_concepts starting from that
        offset.

        Args:
            mrconso_path: Path to the MRCONSO.csv file.
            mrsty_path: Path to the MRSTY file.
            source_vocabs: Optional list of source vocabularies to filter.
            batch_size: Number of nodes per transaction (default 5000).
            memory_limit_mb: Optional memory limit in MB.

        Returns:
            LoadResult with counts and resumed_from_batch set.
        """
        import os
        import time
        from datetime import datetime, timezone

        start_time = time.time()

        if not os.path.exists(mrconso_path):
            raise FileNotFoundError(
                f"MRCONSO file not found: {mrconso_path}"
            )
        if not os.path.exists(mrsty_path):
            raise FileNotFoundError(
                f"MRSTY file not found: {mrsty_path}"
            )

        # Read last_batch_number from UMLSMetadata
        meta_result = await self._neo4j.execute_query(
            "MATCH (m:UMLSMetadata {singleton: true}) "
            "RETURN m.last_batch_number AS last_batch_number"
        )

        last_batch_number = 0
        if meta_result and meta_result[0].get("last_batch_number"):
            last_batch_number = meta_result[0]["last_batch_number"]

        if last_batch_number == 0:
            logger.info(
                "umls_resume_no_previous_batch",
                message="No previous batch found, starting fresh",
            )
            return await self.load_concepts(
                mrconso_path=mrconso_path,
                mrsty_path=mrsty_path,
                source_vocabs=source_vocabs,
                batch_size=batch_size,
                memory_limit_mb=memory_limit_mb,
            )

        logger.info(
            "umls_resume_import",
            last_batch_number=last_batch_number,
            batch_size=batch_size,
        )

        # Set import_status to in_progress
        now_iso = datetime.now(timezone.utc).isoformat()
        await self._neo4j.execute_write_query(
            "MERGE (m:UMLSMetadata {singleton: true}) "
            "SET m.import_status = 'in_progress', "
            "m.load_timestamp = $ts",
            {"ts": now_iso},
        )

        # Parse MRCONSO again to build concept list
        source_vocabs_set = (
            set(source_vocabs) if source_vocabs else None
        )
        concepts: dict = {}

        with open(mrconso_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n").rstrip("\r")
                if not line:
                    continue
                fields = line.split("|")
                if len(fields) < 17:
                    continue

                lat = fields[1]
                if lat != "ENG":
                    continue

                sab = fields[11]
                if source_vocabs_set and sab not in source_vocabs_set:
                    continue

                cui = fields[0]
                ts = fields[2]
                stt = fields[4]
                name = fields[14]
                suppress = fields[16]

                if cui not in concepts:
                    concepts[cui] = {
                        "cui": cui,
                        "preferred_name": None,
                        "synonyms": [],
                        "source_vocabulary": sab,
                        "suppressed": suppress != "N",
                    }

                entry = concepts[cui]
                if ts == "P" and stt == "PF":
                    if entry["preferred_name"] is None:
                        entry["preferred_name"] = name
                    elif name != entry["preferred_name"]:
                        if name not in entry["synonyms"]:
                            entry["synonyms"].append(name)
                else:
                    if (
                        name != entry["preferred_name"]
                        and name not in entry["synonyms"]
                    ):
                        entry["synonyms"].append(name)

        # Fill in preferred_name for CUIs without TS=P/STT=PF
        for cui, entry in concepts.items():
            if entry["preferred_name"] is None:
                if entry["synonyms"]:
                    entry["preferred_name"] = entry["synonyms"].pop(0)
                else:
                    entry["preferred_name"] = cui

        concept_list = list(concepts.values())
        skip_count = last_batch_number * batch_size
        remaining_concepts = concept_list[skip_count:]

        logger.info(
            "umls_resume_skipping_batches",
            total_concepts=len(concept_list),
            skipping=skip_count,
            remaining=len(remaining_concepts),
        )

        # Batch create remaining UMLSConcept nodes
        nodes_created = 0
        batches_completed = 0
        batches_failed = 0

        create_concepts_query = """
        UNWIND $concepts AS c
        MERGE (n:UMLSConcept {cui: c.cui})
        SET n.preferred_name = c.preferred_name,
            n.synonyms = c.synonyms,
            n.source_vocabulary = c.source_vocabulary,
            n.suppressed = c.suppressed
        RETURN count(n) as count
        """

        for i in range(0, len(remaining_concepts), batch_size):
            batch = remaining_concepts[i : i + batch_size]
            batch_num = last_batch_number + (i // batch_size) + 1
            try:
                result = await self._execute_batch_with_retry(
                    create_concepts_query, {"concepts": batch}
                )
                count = result[0]["count"] if result else 0
                nodes_created += count
                batches_completed += 1

                await self._neo4j.execute_write_query(
                    "MERGE (m:UMLSMetadata {singleton: true}) "
                    "SET m.last_batch_number = $batch_num",
                    {"batch_num": batch_num},
                )
            except Exception as exc:
                batches_failed += 1
                logger.error(
                    "resume_concept_batch_failed",
                    batch_num=batch_num,
                    batch_size=len(batch),
                    error=str(exc),
                )

        # Parse MRSTY and create HAS_SEMANTIC_TYPE edges
        loaded_cuis = set(concepts.keys())
        sty_edges: list = []
        relationships_created = 0

        with open(mrsty_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n").rstrip("\r")
                if not line:
                    continue
                fields = line.split("|")
                if len(fields) < 2:
                    continue
                cui = fields[0]
                tui = fields[1]
                if cui not in loaded_cuis:
                    continue
                sty_edges.append({"cui": cui, "tui": tui})

        create_sty_edges_query = """
        UNWIND $edges AS e
        MATCH (c:UMLSConcept {cui: e.cui})
        MATCH (s:UMLSSemanticType {type_id: e.tui})
        MERGE (c)-[r:HAS_SEMANTIC_TYPE]->(s)
        RETURN count(r) as count
        """

        for i in range(0, len(sty_edges), batch_size):
            batch = sty_edges[i : i + batch_size]
            try:
                result = await self._execute_batch_with_retry(
                    create_sty_edges_query, {"edges": batch}
                )
                count = result[0]["count"] if result else 0
                relationships_created += count
                batches_completed += 1
            except Exception as exc:
                batches_failed += 1
                logger.error(
                    "resume_sty_batch_failed",
                    batch_size=len(batch),
                    error=str(exc),
                )

        # Update metadata
        total_concept_batches = (
            (len(concept_list) + batch_size - 1) // batch_size
            if concept_list
            else 0
        )
        now_iso = datetime.now(timezone.utc).isoformat()
        await self._neo4j.execute_write_query(
            "MERGE (m:UMLSMetadata {singleton: true}) "
            "SET m.loaded_tier = 'full', "
            "m.load_timestamp = $ts, "
            "m.last_batch_number = $last_batch, "
            "m.import_status = 'complete'",
            {
                "ts": now_iso,
                "last_batch": total_concept_batches,
            },
        )

        elapsed = time.time() - start_time
        load_result = LoadResult(
            nodes_created=nodes_created,
            relationships_created=relationships_created,
            batches_completed=batches_completed,
            batches_failed=batches_failed,
            elapsed_seconds=round(elapsed, 3),
            resumed_from_batch=last_batch_number,
        )

        logger.info(
            "umls_resume_import_complete",
            nodes_created=load_result.nodes_created,
            relationships_created=load_result.relationships_created,
            resumed_from_batch=last_batch_number,
            elapsed_seconds=load_result.elapsed_seconds,
        )

        return load_result
