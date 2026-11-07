"""
UMLS Client for querying UMLS data stored in Neo4j.

Provides async query methods for looking up concepts, synonyms,
semantic types, and relationships. Follows the ConceptNetValidator
pattern with graceful degradation when Neo4j is unavailable or
UMLS data is not loaded.

All methods return None when unavailable. Query latency is logged
via structlog.
"""

import os
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

import structlog

from multimodal_librarian.components.knowledge_graph.bloom_filter import (
    BloomFilter,
)

logger = structlog.get_logger(__name__)


class _TTLLRUCache:
    """Simple thread-safe LRU cache with TTL expiration.

    Uses an OrderedDict for LRU ordering and per-entry timestamps
    for TTL eviction. Used instead of cachetools.TTLCache since
    cachetools is not in the project dependencies.
    """

    def __init__(self, maxsize: int, ttl: int) -> None:
        self._maxsize = maxsize
        self._ttl = ttl
        self._cache: OrderedDict[Tuple, Tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: Tuple) -> Tuple[bool, Any]:
        """Return (hit, value). Evicts expired entries on access."""
        with self._lock:
            if key not in self._cache:
                return False, None
            ts, value = self._cache[key]
            if time.time() - ts > self._ttl:
                del self._cache[key]
                return False, None
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            return True, value

    def put(self, key: Tuple, value: Any) -> None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = (time.time(), value)
                return
            # Evict LRU entries if at capacity
            while len(self._cache) >= self._maxsize:
                self._cache.popitem(last=False)
            self._cache[key] = (time.time(), value)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)


class UMLSClient:
    """Async query client for UMLS data in Neo4j.

    Provides lookup, search, synonym, semantic type, and relationship
    queries against UMLS data loaded into Neo4j by UMLSLoader.

    All methods return None when Neo4j is unavailable or UMLS data
    is not loaded. Query latency is logged via structlog.
    """

    def __init__(
        self,
        neo4j_client: Any,
        cache_ttl: int = 3600,
        cache_max_size: int = 50000,
        bloom_filter_path: Optional[str] = None,
    ) -> None:
        self._neo4j = neo4j_client
        self._cache = _TTLLRUCache(maxsize=cache_max_size, ttl=cache_ttl)
        self._is_umls_loaded: bool = False
        self._unavailable_logged: bool = False
        # Optional pre-filter over the UMLS vocabulary; rejects non-UMLS
        # n-grams before a Neo4j round-trip.  Path defaults to the env var so
        # construction sites need no change.
        self._bloom_filter_path = (
            bloom_filter_path
            if bloom_filter_path is not None
            else os.environ.get("UMLS_BLOOM_FILTER_PATH")
        )
        self._bloom_filter: Optional[BloomFilter] = None

    async def initialize(self) -> None:
        """Check if UMLS data is loaded by looking for UMLSMetadata node."""
        try:
            result = await self._neo4j.execute_query(
                "MATCH (m:UMLSMetadata) RETURN m.loaded_tier AS tier LIMIT 1",
                {},
            )
            if result and result[0].get("tier") in ("lite", "full"):
                self._is_umls_loaded = True
                logger.info(
                    "umls_client_initialized",
                    loaded_tier=result[0]["tier"],
                )
            else:
                self._is_umls_loaded = False
                logger.warning("umls_data_not_loaded")
        except Exception:
            self._is_umls_loaded = False
            logger.warning("umls_client_init_failed", exc_info=True)

        # Load the optional Bloom filter.  Failure is non-fatal — extraction
        # degrades to the un-filtered path rather than erroring.
        if self._bloom_filter_path:
            try:
                self._bloom_filter = BloomFilter.load(self._bloom_filter_path)
                logger.info(
                    "umls_bloom_filter_loaded",
                    path=self._bloom_filter_path,
                    m=self._bloom_filter.m,
                    k=self._bloom_filter.k,
                    n=self._bloom_filter.n,
                    est_fp_rate=round(self._bloom_filter.estimate_fp_rate(), 6),
                )
            except Exception:
                self._bloom_filter = None
                logger.warning(
                    "umls_bloom_filter_load_failed",
                    path=self._bloom_filter_path,
                    exc_info=True,
                )

    async def is_available(self) -> bool:
        """Return True only if Neo4j is reachable AND UMLS data is loaded."""
        if not self._is_umls_loaded:
            return False
        try:
            await self._neo4j.execute_query(
                "RETURN 1 AS ping", {},
            )
            return True
        except Exception:
            return False

    async def get_loaded_tier(self) -> str:
        """Return the loaded UMLS tier: 'none', 'lite', or 'full'."""
        try:
            result = await self._neo4j.execute_query(
                "MATCH (m:UMLSMetadata) RETURN m.loaded_tier AS tier LIMIT 1",
                {},
            )
            if result and result[0].get("tier"):
                return result[0]["tier"]
        except Exception:
            pass
        return "none"

    def _check_available(self) -> bool:
        """Check availability flag; log warning once if unavailable."""
        if not self._is_umls_loaded:
            if not self._unavailable_logged:
                logger.warning("umls_client_unavailable")
                self._unavailable_logged = True
            return False
        return True

    async def lookup_by_cui(self, cui: str) -> Optional[Dict[str, Any]]:
        """Look up a UMLSConcept node by CUI.

        Returns dict with cui, preferred_name, synonyms,
        source_vocabulary, suppressed. Returns None if unavailable
        or CUI not found.
        """
        if not self._check_available():
            return None

        cache_key = ("lookup_by_cui", cui)
        hit, cached = self._cache.get(cache_key)
        if hit:
            return cached

        start = time.time()
        try:
            result = await self._neo4j.execute_query(
                "MATCH (c:UMLSConcept {cui: $cui}) "
                "RETURN c.cui AS cui, "
                "c.preferred_name AS preferred_name, "
                "c.synonyms AS synonyms, "
                "c.source_vocabulary AS source_vocabulary"
                ", c.suppressed AS suppressed",
                {"cui": cui},
            )
            latency = time.time() - start
            logger.debug(
                "umls_client_query",
                method="lookup_by_cui",
                cui=cui,
                latency_ms=round(latency * 1000, 1),
            )
            if not result:
                self._cache.put(cache_key, None)
                return None
            record = dict(result[0])
            self._cache.put(cache_key, record)
            return record
        except Exception:
            latency = time.time() - start
            logger.warning(
                "umls_client_query_failed",
                method="lookup_by_cui",
                cui=cui,
                latency_ms=round(latency * 1000, 1),
                exc_info=True,
            )
            return None

    async def search_by_name(
        self, name: str,
    ) -> Optional[List[Dict[str, Any]]]:
        """Case-insensitive search against preferred_name and synonyms.

        Returns list of dicts with cui and preferred_name.
        Returns None if unavailable.
        """
        if not self._check_available():
            return None

        cache_key = ("search_by_name", name.lower())
        hit, cached = self._cache.get(cache_key)
        if hit:
            return cached

        start = time.time()
        try:
            result = await self._neo4j.execute_query(
                "MATCH (c:UMLSConcept) WHERE c.lower_name = $lower_name "
                "RETURN c.cui AS cui, c.preferred_name AS preferred_name "
                "UNION "
                "MATCH (s:UMLSSynonym {name: $lower_name})"
                "<-[:HAS_SYNONYM]-(c:UMLSConcept) "
                "RETURN c.cui AS cui, "
                "c.preferred_name AS preferred_name",
                {"lower_name": name.lower()},
            )
            latency = time.time() - start
            logger.debug(
                "umls_client_query",
                method="search_by_name",
                name=name,
                latency_ms=round(latency * 1000, 1),
            )
            if not result:
                self._cache.put(cache_key, None)
                return None
            records = [dict(r) for r in result]
            self._cache.put(cache_key, records)
            return records
        except Exception:
            latency = time.time() - start
            logger.warning(
                "umls_client_query_failed",
                method="search_by_name",
                name=name,
                latency_ms=round(latency * 1000, 1),
                exc_info=True,
            )
            return None

    async def get_synonyms(self, cui: str) -> Optional[List[str]]:
        """Return synonyms list for a CUI.

        Returns empty list [] when CUI exists but has no synonyms.
        Returns None when unavailable or CUI not found.
        """
        if not self._check_available():
            return None

        cache_key = ("get_synonyms", cui)
        hit, cached = self._cache.get(cache_key)
        if hit:
            return cached

        start = time.time()
        try:
            result = await self._neo4j.execute_query(
                "MATCH (c:UMLSConcept {cui: $cui}) "
                "RETURN c.synonyms AS synonyms",
                {"cui": cui},
            )
            latency = time.time() - start
            logger.debug(
                "umls_client_query",
                method="get_synonyms",
                cui=cui,
                latency_ms=round(latency * 1000, 1),
            )
            if not result:
                # CUI not found
                self._cache.put(cache_key, None)
                return None
            synonyms = result[0].get("synonyms")
            if synonyms is None:
                synonyms = []
            value = list(synonyms)
            self._cache.put(cache_key, value)
            return value
        except Exception:
            latency = time.time() - start
            logger.warning(
                "umls_client_query_failed",
                method="get_synonyms",
                cui=cui,
                latency_ms=round(latency * 1000, 1),
                exc_info=True,
            )
            return None

    async def get_semantic_types(self, cui: str) -> Optional[List[str]]:
        """Return semantic type names for a CUI via HAS_SEMANTIC_TYPE edges.

        Returns None if unavailable or CUI not found.
        """
        if not self._check_available():
            return None

        cache_key = ("get_semantic_types", cui)
        hit, cached = self._cache.get(cache_key)
        if hit:
            return cached

        start = time.time()
        try:
            result = await self._neo4j.execute_query(
                "MATCH (c:UMLSConcept {cui: $cui})"
                "-[:HAS_SEMANTIC_TYPE]->"
                "(s:UMLSSemanticType) "
                "RETURN s.type_name AS type_name",
                {"cui": cui},
            )
            latency = time.time() - start
            logger.debug(
                "umls_client_query",
                method="get_semantic_types",
                cui=cui,
                latency_ms=round(latency * 1000, 1),
            )
            if not result:
                self._cache.put(cache_key, None)
                return None
            types = [r["type_name"] for r in result if r.get("type_name")]
            self._cache.put(cache_key, types)
            return types
        except Exception:
            latency = time.time() - start
            logger.warning(
                "umls_client_query_failed",
                method="get_semantic_types",
                cui=cui,
                latency_ms=round(latency * 1000, 1),
                exc_info=True,
            )
            return None

    async def get_related_concepts(
        self,
        cui: str,
        relationship_type: Optional[str] = None,
        limit: int = 20,
    ) -> Optional[List[Dict[str, Any]]]:
        """Traverse UMLS_REL edges from a concept.

        Optionally filter by rela_type. Returns list of dicts with
        cui, preferred_name, rel_type, rela_type.
        Returns None if unavailable.
        """
        if not self._check_available():
            return None

        cache_key = ("get_related_concepts", cui, relationship_type, limit)
        hit, cached = self._cache.get(cache_key)
        if hit:
            return cached

        start = time.time()
        try:
            result = await self._neo4j.execute_query(
                "MATCH (c:UMLSConcept {cui: $cui})"
                "-[r:UMLS_REL]->"
                "(related:UMLSConcept) "
                "WHERE $rel_type IS NULL "
                "OR r.rela_type = $rel_type "
                "RETURN related.cui AS cui, "
                "related.preferred_name "
                "AS preferred_name, "
                "r.rel_type AS rel_type, "
                "r.rela_type AS rela_type "
                "LIMIT $limit",
                {"cui": cui, "rel_type": relationship_type, "limit": limit},
            )
            latency = time.time() - start
            logger.debug(
                "umls_client_query",
                method="get_related_concepts",
                cui=cui,
                relationship_type=relationship_type,
                limit=limit,
                latency_ms=round(latency * 1000, 1),
            )
            if not result:
                self._cache.put(cache_key, None)
                return None
            records = [dict(r) for r in result]
            self._cache.put(cache_key, records)
            return records
        except Exception:
            latency = time.time() - start
            logger.warning(
                "umls_client_query_failed",
                method="get_related_concepts",
                cui=cui,
                latency_ms=round(latency * 1000, 1),
                exc_info=True,
            )
            return None

    async def batch_search_by_names(
        self, names: List[str],
    ) -> Optional[Dict[str, str]]:
        """Look up multiple concept names against UMLS data in Neo4j.

        Uses pre-computed ``lower_name`` and ``lower_synonyms`` properties
        (indexed) for fast case-insensitive matching.  Names are processed
        in sub-batches of 2000 to avoid Neo4j transaction timeouts when
        thousands of concepts are extracted per KG batch.

        Results are cached per-name (including negative "no match" results),
        so repeated n-grams across chunks skip the database entirely.  A
        Bloom filter over the UMLS vocabulary (when configured) additionally
        rejects non-UMLS names up front, before any round-trip.

        Returns a dict mapping input name -> CUI for matches found.
        Returns None if unavailable.
        """
        if not self._check_available():
            return None
        if not names:
            return {}

        # De-duplicate while preserving original casing for the result map
        seen: Dict[str, str] = {}  # lower -> original
        for n in names:
            low = n.lower()
            if low not in seen:
                seen[low] = n
        unique_lower = list(seen.keys())

        # Per-name cache: ("batch_search_by_names", lower) -> CUI or None.
        # None marks a confirmed "no match", so both hits and misses skip the DB.
        cache_prefix = "batch_search_by_names"
        mapping: Dict[str, str] = {}
        missing: List[str] = []
        cache_hits = 0
        bloom_rejected = 0
        for low in unique_lower:
            hit, cached = self._cache.get((cache_prefix, low))
            if hit:
                cache_hits += 1
                if cached is not None:
                    mapping[low] = cached
            elif self._bloom_filter is not None and low not in self._bloom_filter:
                # Definitely not a UMLS name — drop without a round-trip.
                bloom_rejected += 1
            else:
                missing.append(low)

        if missing:
            # Two-phase lookup: (1) indexed lower_name (fast), then
            # (2) lower_synonyms only for names not yet matched.  A 2000-name
            # query resolves in tens of ms against the RANGE indexes, well
            # under the 120s transaction timeout.
            SUB_BATCH = 2000
            start = time.time()
            failed = False
            queried: set = set()

            # Phase 1: Indexed preferred_name lookup (fast)
            for sb_start in range(0, len(missing), SUB_BATCH):
                sb_names = missing[sb_start:sb_start + SUB_BATCH]
                try:
                    result = await self._neo4j.execute_query(
                        "UNWIND $names AS name "
                        "MATCH (c:UMLSConcept) "
                        "WHERE c.lower_name = name "
                        "RETURN name, c.cui AS cui",
                        {"names": sb_names},
                    )
                    queried.update(sb_names)
                    if result:
                        for r in result:
                            nv = r.get("name")
                            cv = r.get("cui")
                            if nv and cv and nv not in mapping:
                                mapping[nv] = cv
                except Exception:
                    logger.warning(
                        "umls_client_query_failed",
                        method="batch_search_by_names_pn",
                        sub_batch_start=sb_start,
                        exc_info=True,
                    )
                    failed = True

            # Phase 2: Synonym lookup for unmatched names only
            unmatched = [n for n in missing if n not in mapping]
            if unmatched:
                for sb_start in range(0, len(unmatched), SUB_BATCH):
                    sb_names = unmatched[
                        sb_start:sb_start + SUB_BATCH
                    ]
                    try:
                        result = await self._neo4j.execute_query(
                            "UNWIND $names AS name "
                            "MATCH (s:UMLSSynonym {name: name})"
                            "<-[:HAS_SYNONYM]-(c:UMLSConcept) "
                            "RETURN name, c.cui AS cui",
                            {"names": sb_names},
                        )
                        queried.update(sb_names)
                        if result:
                            for r in result:
                                nv = r.get("name")
                                cv = r.get("cui")
                                if nv and cv and nv not in mapping:
                                    mapping[nv] = cv
                    except Exception:
                        logger.warning(
                            "umls_client_query_failed",
                            method="batch_search_by_names_syn",
                            sub_batch_start=sb_start,
                            exc_info=True,
                        )
                        failed = True

            # Cache every name we actually queried, including negatives, so
            # repeated n-grams across chunks skip the DB.  Names from failed
            # sub-batches are left uncached so they are retried next time.
            for low in queried:
                self._cache.put((cache_prefix, low), mapping.get(low))

            latency = time.time() - start
            logger.debug(
                "umls_client_query",
                method="batch_search_by_names",
                name_count=len(unique_lower),
                cache_hits=cache_hits,
                bloom_rejected=bloom_rejected,
                queried=len(missing),
                matched=len(mapping),
                latency_ms=round(latency * 1000, 1),
                had_failures=failed,
            )

            if not mapping and failed:
                # All fresh lookups failed and nothing was cached — return
                # None so the caller knows UMLS is unavailable.
                return None
        else:
            logger.debug(
                "umls_client_query",
                method="batch_search_by_names",
                name_count=len(unique_lower),
                cache_hits=cache_hits,
                bloom_rejected=bloom_rejected,
                queried=len(missing),
                matched=len(mapping),
                latency_ms=0.0,
                had_failures=False,
            )

        # Map lowercased keys back to original casing
        orig_mapping: Dict[str, str] = {}
        for low_name, cui in mapping.items():
            orig = seen.get(low_name, low_name)
            orig_mapping[orig] = cui

        return orig_mapping
