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
                "MATCH (c:UMLSConcept) "
                "WHERE toLower(c.preferred_name) = toLower($name) "
                "   OR any(s IN c.synonyms WHERE toLower(s) = toLower($name)) "
                "RETURN c.cui AS cui, c.preferred_name AS preferred_name",
                {"name": name},
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
        """Look up multiple concept names in a single Cypher query.

        Returns a dict mapping input name -> CUI for matches found.
        Returns None if unavailable.
        """
        if not self._check_available():
            return None
        if not names:
            return {}

        cache_key = (
            "batch_search_by_names",
            tuple(sorted(n.lower() for n in names)),
        )
        hit, cached = self._cache.get(cache_key)
        if hit:
            return cached

        start = time.time()
        try:
            result = await self._neo4j.execute_query(
                "UNWIND $names AS name "
                "OPTIONAL MATCH (c:UMLSConcept) "
                "WHERE toLower(c.preferred_name) = toLower(name) "
                "   OR any(s IN c.synonyms WHERE toLower(s) = toLower(name)) "
                "WITH name, c "
                "WHERE c IS NOT NULL "
                "RETURN name, c.cui AS cui",
                {"names": list(names)},
            )
            latency = time.time() - start
            logger.debug(
                "umls_client_query",
                method="batch_search_by_names",
                name_count=len(names),
                latency_ms=round(latency * 1000, 1),
            )
            mapping: Dict[str, str] = {}
            if result:
                for r in result:
                    name_val = r.get("name")
                    cui_val = r.get("cui")
                    if name_val and cui_val and name_val not in mapping:
                        mapping[name_val] = cui_val
            self._cache.put(cache_key, mapping)
            return mapping
        except Exception:
            latency = time.time() - start
            logger.warning(
                "umls_client_query_failed",
                method="batch_search_by_names",
                name_count=len(names),
                latency_ms=round(latency * 1000, 1),
                exc_info=True,
            )
            return None
