"""
UMLS Client for querying UMLS data stored in Neo4j.

Provides async query methods for looking up concepts, synonyms,
semantic types, and relationships. Follows the ConceptNetValidator
pattern with graceful degradation when Neo4j is unavailable or
UMLS data is not loaded.

All methods return None when unavailable. Query latency is logged
via structlog.
"""

import threading
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

import structlog

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
    ) -> None:
        self._neo4j = neo4j_client
        self._cache = _TTLLRUCache(maxsize=cache_max_size, ttl=cache_ttl)
        self._is_umls_loaded: bool = False
        self._unavailable_logged: bool = False

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
        in sub-batches of 200 to avoid Neo4j transaction timeouts when
        thousands of concepts are extracted per KG batch.

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

        cache_key = (
            "batch_search_by_names",
            tuple(sorted(unique_lower)),
        )
        hit, cached = self._cache.get(cache_key)
        if hit:
            return cached

        # Sub-batch to keep each Neo4j transaction small.
        # Two-phase lookup: (1) indexed lower_name (fast), then
        # (2) lower_synonyms only for names not yet matched.
        SUB_BATCH = 200
        mapping: Dict[str, str] = {}
        start = time.time()
        failed = False

        # Phase 1: Indexed preferred_name lookup (fast)
        for sb_start in range(0, len(unique_lower), SUB_BATCH):
            sb_names = unique_lower[sb_start:sb_start + SUB_BATCH]
            try:
                result = await self._neo4j.execute_query(
                    "UNWIND $names AS name "
                    "MATCH (c:UMLSConcept) "
                    "WHERE c.lower_name = name "
                    "RETURN name, c.cui AS cui",
                    {"names": sb_names},
                )
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
        unmatched = [n for n in unique_lower if n not in mapping]
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

        # Map lowercased keys back to original casing
        orig_mapping: Dict[str, str] = {}
        for low_name, cui in mapping.items():
            orig = seen.get(low_name, low_name)
            orig_mapping[orig] = cui

        latency = time.time() - start
        logger.debug(
            "umls_client_query",
            method="batch_search_by_names",
            name_count=len(unique_lower),
            matched=len(orig_mapping),
            latency_ms=round(latency * 1000, 1),
            had_failures=failed,
        )

        if not orig_mapping and failed:
            # All sub-batches failed — return None so caller knows
            return None

        self._cache.put(cache_key, orig_mapping)
        return orig_mapping
