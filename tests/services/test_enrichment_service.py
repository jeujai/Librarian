"""
Tests for Knowledge Graph External Enrichment Service.

This module tests the enrichment service functionality including:
- EnrichmentCache with LRU and TTL
- CircuitBreaker for API resilience
- YAGO local client and ConceptNetClient
- EnrichmentService core functionality
"""

import asyncio
import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.multimodal_librarian.components.yago.models import (
    YagoEntityData,
    YagoSearchResult,
)
from src.multimodal_librarian.models.enrichment import (
    CacheEntry,
    CacheStats,
    CircuitBreakerOpenError,
    CircuitBreakerStats,
    CircuitState,
    ConceptNetAPIError,
    ConceptNetRelation,
    EnrichedConcept,
    EnrichmentError,
    EnrichmentResult,
)
from src.multimodal_librarian.models.knowledge_graph import ConceptNode
from src.multimodal_librarian.services.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerRegistry,
    get_circuit_breaker,
    get_circuit_breaker_registry,
)
from src.multimodal_librarian.services.enrichment_cache import (
    EnrichmentCache,
    clear_enrichment_cache,
    get_enrichment_cache,
)
from src.multimodal_librarian.services.enrichment_service import (
    YAGO_CONFIDENCE_THRESHOLD,
    EnrichmentService,
    get_enrichment_service,
)

# =============================================================================
# Test Data Models
# =============================================================================


class TestEnrichmentModels:
    """Test enrichment data models."""

    def test_yago_entity_creation(self):
        """Test YagoEntityData dataclass creation."""
        entity = YagoEntityData(
            entity_id="Q42",
            label="Douglas Adams",
            description="English writer",
            aliases=["Douglas Noel Adams"],
            instance_of=["Q5"],
            confidence=0.95,
        )

        assert entity.entity_id == "Q42"
        assert entity.label == "Douglas Adams"
        assert entity.confidence == 0.95

    def test_yago_entity_defaults(self):
        """Test YagoEntityData default values."""
        entity = YagoEntityData(
            entity_id="Q42",
            label="Douglas Adams",
            confidence=0.95,
        )

        assert entity.description is None
        assert entity.instance_of == []
        assert entity.subclass_of == []
        assert entity.aliases == []

    def test_conceptnet_relation_creation(self):
        """Test ConceptNetRelation dataclass creation."""
        relation = ConceptNetRelation(
            subject="writer",
            relation="IsA",
            object="person",
            weight=0.8,
            source_uri="/a/[/r/IsA/,/c/en/writer/,/c/en/person/]",
        )

        assert relation.subject == "writer"
        assert relation.relation == "IsA"
        assert relation.weight == 0.8

    def test_enriched_concept_properties(self):
        """Test EnrichedConcept computed properties."""
        # Empty enrichment
        empty = EnrichedConcept(concept_id="c1", concept_name="test")
        assert not empty.is_enriched
        assert not empty.has_yago
        assert not empty.has_conceptnet

        # With YAGO
        with_yago = EnrichedConcept(
            concept_id="c2",
            concept_name="test",
            yago_entity=YagoEntityData(
                entity_id="Q1", label="test", confidence=0.9
            ),
        )
        assert with_yago.is_enriched
        assert with_yago.has_yago
        assert not with_yago.has_conceptnet

        # With ConceptNet
        with_conceptnet = EnrichedConcept(
            concept_id="c3",
            concept_name="test",
            conceptnet_relations=[
                ConceptNetRelation(
                    subject="test",
                    relation="IsA",
                    object="thing",
                    weight=0.5,
                )
            ],
        )
        assert with_conceptnet.is_enriched
        assert not with_conceptnet.has_yago
        assert with_conceptnet.has_conceptnet

    def test_cache_entry_expiration(self):
        """Test CacheEntry TTL expiration."""
        entry = CacheEntry(data="test", created_at=time.time() - 100)

        # Not expired with long TTL
        assert not entry.is_expired(200)

        # Expired with short TTL
        assert entry.is_expired(50)

    def test_cache_stats_hit_rates(self):
        """Test CacheStats hit rate calculations."""
        stats = CacheStats(
            yago_hits=80,
            yago_misses=20,
            conceptnet_hits=60,
            conceptnet_misses=40,
        )

        assert stats.yago_hit_rate == 0.8
        assert stats.conceptnet_hit_rate == 0.6

    def test_cache_stats_zero_division(self):
        """Test CacheStats with no requests."""
        stats = CacheStats()
        assert stats.yago_hit_rate == 0.0
        assert stats.conceptnet_hit_rate == 0.0


# =============================================================================
# Test Enrichment Cache
# =============================================================================


class TestEnrichmentCache:
    """Test EnrichmentCache functionality."""

    @pytest.fixture
    def cache(self):
        """Create a fresh cache for each test."""
        return EnrichmentCache(max_size=5, ttl_seconds=60)

    def test_cache_initialization(self, cache):
        """Test cache initialization."""
        assert cache.max_size == 5
        assert cache.ttl == 60

        stats = cache.get_stats()
        assert stats.yago_size == 0
        assert stats.conceptnet_size == 0

    def test_yago_cache_set_get(self, cache):
        """Test YAGO cache set and get."""
        entity = YagoEntityData(
            entity_id="Q42", label="Douglas Adams", confidence=0.95
        )

        cache.set_yago("douglas adams", entity)
        result = cache.get_yago("douglas adams")

        assert result is not None
        assert result.entity_id == "Q42"

    def test_yago_cache_miss(self, cache):
        """Test YAGO cache miss."""
        result = cache.get_yago("nonexistent")
        assert result is None

        stats = cache.get_stats()
        assert stats.yago_misses == 1

    def test_yago_cache_hit_tracking(self, cache):
        """Test YAGO cache hit tracking."""
        entity = YagoEntityData(
            entity_id="Q42", label="Douglas Adams", confidence=0.95
        )

        cache.set_yago("douglas adams", entity)
        cache.get_yago("douglas adams")
        cache.get_yago("douglas adams")

        stats = cache.get_stats()
        assert stats.yago_hits == 2

    def test_conceptnet_cache_set_get(self, cache):
        """Test ConceptNet cache set and get."""
        relations = [
            ConceptNetRelation(
                subject="writer",
                relation="IsA",
                object="person",
                weight=0.8,
            )
        ]

        cache.set_conceptnet("writer", relations)
        result = cache.get_conceptnet("writer")

        assert result is not None
        assert len(result) == 1
        assert result[0].relation == "IsA"

    def test_conceptnet_cache_miss(self, cache):
        """Test ConceptNet cache miss."""
        result = cache.get_conceptnet("nonexistent")
        assert result is None

        stats = cache.get_stats()
        assert stats.conceptnet_misses == 1

    def test_cache_key_normalization(self, cache):
        """Test cache key normalization (case insensitive)."""
        entity = YagoEntityData(
            entity_id="Q42", label="Douglas Adams", confidence=0.95
        )

        cache.set_yago("Douglas Adams", entity)

        # Should find with different case
        result = cache.get_yago("douglas adams")
        assert result is not None

        result = cache.get_yago("DOUGLAS ADAMS")
        assert result is not None

    def test_lru_eviction(self, cache):
        """Test LRU eviction when cache is full."""
        # Fill cache to max_size
        for i in range(5):
            entity = YagoEntityData(
                entity_id=f"Q{i}", label=f"Entity {i}", confidence=0.9
            )
            cache.set_yago(f"entity{i}", entity)

        # Add one more - should evict oldest
        entity = YagoEntityData(
            entity_id="Q99", label="New Entity", confidence=0.9
        )
        cache.set_yago("new_entity", entity)

        stats = cache.get_stats()
        assert stats.yago_size == 5
        assert stats.evictions == 1

        # First entry should be evicted
        assert cache.get_yago("entity0") is None

    def test_ttl_expiration(self):
        """Test TTL expiration."""
        cache = EnrichmentCache(max_size=10, ttl_seconds=1)

        entity = YagoEntityData(
            entity_id="Q42", label="Douglas Adams", confidence=0.95
        )
        cache.set_yago("douglas adams", entity)

        # Should be found immediately
        assert cache.get_yago("douglas adams") is not None

        # Wait for expiration
        time.sleep(1.5)

        # Should be expired
        assert cache.get_yago("douglas adams") is None

    def test_cache_clear(self, cache):
        """Test cache clear."""
        entity = YagoEntityData(
            entity_id="Q42", label="Douglas Adams", confidence=0.95
        )
        cache.set_yago("douglas adams", entity)

        relations = [
            ConceptNetRelation(
                subject="writer",
                relation="IsA",
                object="person",
                weight=0.8,
            )
        ]
        cache.set_conceptnet("writer", relations)

        cache.clear()

        stats = cache.get_stats()
        assert stats.yago_size == 0
        assert stats.conceptnet_size == 0
        assert stats.yago_hits == 0
        assert stats.evictions == 0

    def test_cleanup_expired(self):
        """Test cleanup of expired entries."""
        cache = EnrichmentCache(max_size=10, ttl_seconds=1)

        # Add entries
        for i in range(3):
            entity = YagoEntityData(
                entity_id=f"Q{i}", label=f"Entity {i}", confidence=0.9
            )
            cache.set_yago(f"entity{i}", entity)

        # Wait for expiration
        time.sleep(1.5)

        # Cleanup
        removed = cache.cleanup_expired()
        assert removed == 3

        stats = cache.get_stats()
        assert stats.yago_size == 0


# =============================================================================
# Test Circuit Breaker
# =============================================================================


class TestCircuitBreaker:
    """Test CircuitBreaker functionality."""

    @pytest.fixture
    def breaker(self):
        """Create a fresh circuit breaker for each test."""
        return CircuitBreaker(
            name="test",
            failure_threshold=3,
            failure_window=60,
            recovery_timeout=5,
        )

    def test_circuit_breaker_initialization(self, breaker):
        """Test circuit breaker initialization."""
        assert breaker.name == "test"
        assert breaker.failure_threshold == 3
        assert breaker.state == CircuitState.CLOSED

    def test_record_success(self, breaker):
        """Test recording successful calls."""
        breaker.record_success()

        stats = breaker.get_stats()
        assert stats.successes == 1
        assert stats.state == CircuitState.CLOSED

    def test_record_failure(self, breaker):
        """Test recording failed calls."""
        breaker.record_failure()

        stats = breaker.get_stats()
        assert stats.failures == 1
        assert stats.state == CircuitState.CLOSED

    def test_circuit_opens_on_threshold(self, breaker):
        """Test circuit opens after failure threshold."""
        for _ in range(3):
            breaker.record_failure()

        assert breaker.state == CircuitState.OPEN
        assert breaker.is_open()
        assert not breaker.allow_request()

    def test_circuit_stays_closed_below_threshold(self, breaker):
        """Test circuit stays closed below threshold."""
        breaker.record_failure()
        breaker.record_failure()

        assert breaker.state == CircuitState.CLOSED
        assert not breaker.is_open()
        assert breaker.allow_request()

    def test_circuit_recovery_to_half_open(self):
        """Test circuit transitions to half-open after timeout."""
        breaker = CircuitBreaker(
            name="test",
            failure_threshold=2,
            failure_window=60,
            recovery_timeout=1,  # Short timeout for testing
        )

        # Open the circuit
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        # Wait for recovery timeout
        time.sleep(1.5)

        # Should transition to half-open
        assert breaker.state == CircuitState.HALF_OPEN
        assert breaker.allow_request()

    def test_circuit_closes_on_success_in_half_open(self):
        """Test circuit closes on success in half-open state."""
        breaker = CircuitBreaker(
            name="test",
            failure_threshold=2,
            failure_window=60,
            recovery_timeout=1,
        )

        # Open the circuit
        breaker.record_failure()
        breaker.record_failure()

        # Wait for half-open
        time.sleep(1.5)
        assert breaker.state == CircuitState.HALF_OPEN

        # Record success
        breaker.record_success()
        assert breaker.state == CircuitState.CLOSED

    def test_circuit_reopens_on_failure_in_half_open(self):
        """Test circuit reopens on failure in half-open state."""
        breaker = CircuitBreaker(
            name="test",
            failure_threshold=2,
            failure_window=60,
            recovery_timeout=1,
        )

        # Open the circuit
        breaker.record_failure()
        breaker.record_failure()

        # Wait for half-open
        time.sleep(1.5)
        assert breaker.state == CircuitState.HALF_OPEN

        # Record failure
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

    def test_circuit_reset(self, breaker):
        """Test circuit reset."""
        # Open the circuit
        for _ in range(3):
            breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        # Reset
        breaker.reset()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.allow_request()

    def test_failure_window_expiration(self):
        """Test failures outside window don't count."""
        breaker = CircuitBreaker(
            name="test",
            failure_threshold=3,
            failure_window=1,  # 1 second window
            recovery_timeout=60,
        )

        # Record 2 failures
        breaker.record_failure()
        breaker.record_failure()

        # Wait for window to expire
        time.sleep(1.5)

        # Record 1 more failure - should not open circuit
        breaker.record_failure()
        assert breaker.state == CircuitState.CLOSED

    def test_get_recovery_time(self, breaker):
        """Test get_recovery_time."""
        # Not open - no recovery time
        assert breaker.get_recovery_time() is None

        # Open the circuit
        for _ in range(3):
            breaker.record_failure()

        # Should have recovery time
        recovery_time = breaker.get_recovery_time()
        assert recovery_time is not None
        assert isinstance(recovery_time, datetime)


class TestCircuitBreakerRegistry:
    """Test CircuitBreakerRegistry functionality."""

    @pytest.fixture
    def registry(self):
        """Create a fresh registry for each test."""
        return CircuitBreakerRegistry()

    def test_registry_get_creates_breaker(self, registry):
        """Test registry creates breaker on first get."""
        breaker = registry.get("test_api")

        assert breaker is not None
        assert breaker.name == "test_api"

    def test_registry_get_returns_same_breaker(self, registry):
        """Test registry returns same breaker on subsequent gets."""
        breaker1 = registry.get("test_api")
        breaker2 = registry.get("test_api")

        assert breaker1 is breaker2

    def test_registry_get_all_stats(self, registry):
        """Test getting stats for all breakers."""
        registry.get("api1")
        registry.get("api2")

        stats = registry.get_all_stats()
        assert "api1" in stats
        assert "api2" in stats

    def test_registry_reset_all(self, registry):
        """Test resetting all breakers."""
        breaker1 = registry.get("api1")
        breaker2 = registry.get("api2")

        # Open both
        for _ in range(5):
            breaker1.record_failure()
            breaker2.record_failure()

        assert breaker1.state == CircuitState.OPEN
        assert breaker2.state == CircuitState.OPEN

        # Reset all
        registry.reset_all()

        assert breaker1.state == CircuitState.CLOSED
        assert breaker2.state == CircuitState.CLOSED


# =============================================================================
# Test Enrichment Service
# =============================================================================


class TestEnrichmentService:
    """Test EnrichmentService functionality."""

    @pytest.fixture
    def mock_yago_client(self):
        """Create mock YAGO local client."""
        client = MagicMock()
        client.search_entities = AsyncMock(
            return_value=[
                YagoSearchResult(
                    entity_id="Q42",
                    label="Douglas Adams",
                    description="English writer",
                    score=0.95,
                )
            ]
        )
        client.get_entity = AsyncMock(
            return_value=YagoEntityData(
                entity_id="Q42",
                label="Douglas Adams",
                description="English writer",
                confidence=0.95,
            )
        )
        client.is_available = AsyncMock(return_value=True)
        return client

    @pytest.fixture
    def mock_conceptnet_client(self):
        """Create mock ConceptNet client."""
        client = MagicMock()
        client.get_relationships = AsyncMock(
            return_value=[
                ConceptNetRelation(
                    subject="writer",
                    relation="IsA",
                    object="person",
                    weight=0.8,
                    source_uri="/a/test",
                )
            ]
        )
        return client

    @pytest.fixture
    def mock_cache(self):
        """Create mock cache."""
        cache = MagicMock(spec=EnrichmentCache)
        cache.get_yago = MagicMock(return_value=None)
        cache.get_conceptnet = MagicMock(return_value=None)
        cache.set_yago = MagicMock()
        cache.set_conceptnet = MagicMock()
        cache.get_stats = MagicMock(
            return_value=CacheStats(yago_hits=0, conceptnet_hits=0)
        )
        return cache

    @pytest.fixture
    def service(self, mock_yago_client, mock_conceptnet_client, mock_cache):
        """Create enrichment service with mocks."""
        return EnrichmentService(
            yago_client=mock_yago_client,
            conceptnet_client=mock_conceptnet_client,
            cache=mock_cache,
            kg_service=None,
        )

    @pytest.mark.asyncio
    async def test_enrich_single_concept_with_yago(
        self, service, mock_yago_client
    ):
        """Test enriching a single concept with YAGO."""
        concept = ConceptNode(
            concept_id="c1",
            concept_name="Douglas Adams",
            concept_type="ENTITY",
            confidence=0.9,
        )

        result = await service.enrich_single_concept(concept, "doc1")

        assert result.concept_id == "c1"
        assert result.yago_entity is not None
        assert result.yago_entity.entity_id == "Q42"
        mock_yago_client.search_entities.assert_called_once()

    @pytest.mark.asyncio
    async def test_enrich_single_concept_with_conceptnet(
        self, service, mock_conceptnet_client
    ):
        """Test enriching a single concept with ConceptNet."""
        concept = ConceptNode(
            concept_id="c1",
            concept_name="writer",
            concept_type="ENTITY",
            confidence=0.9,
        )

        result = await service.enrich_single_concept(concept, "doc1")

        assert result.concept_id == "c1"
        assert len(result.conceptnet_relations) == 1
        assert result.conceptnet_relations[0].relation == "IsA"
        mock_conceptnet_client.get_relationships.assert_called_once()

    @pytest.mark.asyncio
    async def test_enrich_single_concept_uses_cache(
        self, mock_yago_client, mock_conceptnet_client
    ):
        """Test that enrichment uses cache."""
        cached_entity = YagoEntityData(
            entity_id="Q42",
            label="Douglas Adams",
            confidence=0.95,
        )

        cache = MagicMock(spec=EnrichmentCache)
        cache.get_yago = MagicMock(return_value=cached_entity)
        cache.get_conceptnet = MagicMock(return_value=[])
        cache.get_stats = MagicMock(
            return_value=CacheStats(yago_hits=1, conceptnet_hits=0)
        )

        service = EnrichmentService(
            yago_client=mock_yago_client,
            conceptnet_client=mock_conceptnet_client,
            cache=cache,
            kg_service=None,
        )

        concept = ConceptNode(
            concept_id="c1",
            concept_name="Douglas Adams",
            concept_type="ENTITY",
            confidence=0.9,
        )

        result = await service.enrich_single_concept(concept, "doc1")

        assert result.yago_entity is not None
        # Should use cached value, not call API
        mock_yago_client.search_entities.assert_not_called()

    @pytest.mark.asyncio
    async def test_enrich_concepts_batch(self, service, mock_yago_client, mock_conceptnet_client):
        """Test batch enrichment of concepts."""
        # The service iterates concepts and calls search_entities/get_entity per concept.
        # Mock search_entities to return a result for each concept name.
        mock_yago_client.search_entities = AsyncMock(
            side_effect=lambda name, limit=10: [
                YagoSearchResult(
                    entity_id=f"Q{name[-1]}",
                    label=name,
                    description=f"Description of {name}",
                    score=0.95,
                )
            ]
        )
        mock_yago_client.get_entity = AsyncMock(
            side_effect=lambda eid: YagoEntityData(
                entity_id=eid,
                label=f"Label {eid}",
                confidence=0.95,
            )
        )
        mock_conceptnet_client.batch_get_relationships = AsyncMock(
            return_value={
                "Concept 0": [],
                "Concept 1": [],
                "Concept 2": [],
            }
        )
        
        concepts = [
            ConceptNode(
                concept_id=f"c{i}",
                concept_name=f"Concept {i}",
                concept_type="ENTITY",
                confidence=0.9,
            )
            for i in range(3)
        ]

        result = await service.enrich_concepts(concepts, "doc1")

        assert result.concepts_processed == 3
        assert len(result.enriched_concepts) == 3

    @pytest.mark.asyncio
    async def test_enrich_concepts_error_isolation(
        self, mock_conceptnet_client, mock_cache
    ):
        """Test that errors in one concept don't affect others.
        
        The enrichment service iterates concepts and calls search_entities/get_entity
        per concept. This test verifies that both concepts are processed even when
        the YAGO lookup returns None for one concept.
        """

        # Create mock YAGO client — returns None for "Failing", entity for "Succeeding"
        mock_yago = MagicMock()
        
        async def _search_entities(name, limit=10):
            if name == "Failing":
                return []  # No results for failing concept
            return [
                YagoSearchResult(
                    entity_id="Q1", label="Test", description="Test entity", score=0.9
                )
            ]
        
        mock_yago.search_entities = AsyncMock(side_effect=_search_entities)
        mock_yago.get_entity = AsyncMock(
            return_value=YagoEntityData(
                entity_id="Q1", label="Test", confidence=0.9
            )
        )
        mock_yago.is_available = AsyncMock(return_value=True)
        
        # Mock ConceptNet batch method
        mock_conceptnet_client.batch_get_relationships = AsyncMock(
            return_value={
                "Failing": [],
                "Succeeding": [
                    ConceptNetRelation(
                        subject="Succeeding",
                        relation="IsA",
                        object="thing",
                        weight=0.8,
                        source_uri="/a/test",
                    )
                ],
            }
        )

        service = EnrichmentService(
            yago_client=mock_yago,
            conceptnet_client=mock_conceptnet_client,
            cache=mock_cache,
            kg_service=None,
        )

        concepts = [
            ConceptNode(
                concept_id="c1",
                concept_name="Failing",
                concept_type="ENTITY",
                confidence=0.9,
            ),
            ConceptNode(
                concept_id="c2",
                concept_name="Succeeding",
                concept_type="ENTITY",
                confidence=0.9,
            ),
        ]

        result = await service.enrich_concepts(concepts, "doc1")

        # Both should be processed - error isolation works
        assert result.concepts_processed == 2
        assert len(result.enriched_concepts) == 2
        
        # First concept should not have YAGO entity (search returned empty)
        assert result.enriched_concepts[0].yago_entity is None
        # Second concept should have YAGO entity
        assert result.enriched_concepts[1].yago_entity is not None
        assert result.enriched_concepts[1].yago_entity.entity_id == "Q1"

    def test_map_conceptnet_relation(self, service):
        """Test ConceptNet relation type mapping."""
        assert service._map_conceptnet_relation("IsA") == "IS_A"
        assert service._map_conceptnet_relation("PartOf") == "PART_OF"
        assert service._map_conceptnet_relation("UsedFor") == "USED_FOR"
        assert service._map_conceptnet_relation("CapableOf") == "CAPABLE_OF"
        assert service._map_conceptnet_relation("HasProperty") == "HAS_PROPERTY"
        assert service._map_conceptnet_relation("AtLocation") == "AT_LOCATION"
        assert service._map_conceptnet_relation("Causes") == "CAUSES"
        assert service._map_conceptnet_relation("HasPrerequisite") == "HAS_PREREQUISITE"
        assert service._map_conceptnet_relation("MotivatedByGoal") == "MOTIVATED_BY_GOAL"
        assert service._map_conceptnet_relation("RelatedTo") == "RELATED_TO"
        # Unknown relation defaults to RELATED_TO
        assert service._map_conceptnet_relation("Unknown") == "RELATED_TO"

    def test_confidence_threshold(self):
        """Test confidence threshold constant."""
        assert YAGO_CONFIDENCE_THRESHOLD == 0.7


# =============================================================================
# Test Global Functions
# =============================================================================


class TestGlobalFunctions:
    """Test global singleton functions."""

    def test_get_enrichment_cache_singleton(self):
        """Test get_enrichment_cache returns singleton."""
        cache1 = get_enrichment_cache()
        cache2 = get_enrichment_cache()
        assert cache1 is cache2

    def test_get_circuit_breaker_registry_singleton(self):
        """Test get_circuit_breaker_registry returns singleton."""
        registry1 = get_circuit_breaker_registry()
        registry2 = get_circuit_breaker_registry()
        assert registry1 is registry2

    def test_get_circuit_breaker_by_name(self):
        """Test get_circuit_breaker returns breaker by name."""
        breaker = get_circuit_breaker("test_api")
        assert breaker is not None
        assert breaker.name == "test_api"

    def test_get_enrichment_service_singleton(self):
        """Test get_enrichment_service returns singleton."""
        service1 = get_enrichment_service()
        service2 = get_enrichment_service()
        assert service1 is service2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# =============================================================================
# Test Cross-Document Linking
# =============================================================================


class TestCrossDocumentLinking:
    """Test cross-document linking functionality."""

    @pytest.fixture
    def mock_yago_client(self):
        """Create mock YAGO local client."""
        client = MagicMock()
        client.search_entities = AsyncMock(
            return_value=[
                YagoSearchResult(
                    entity_id="Q42",
                    label="Douglas Adams",
                    description="English writer",
                    score=0.95,
                )
            ]
        )
        client.get_entity = AsyncMock(
            return_value=YagoEntityData(
                entity_id="Q42",
                label="Douglas Adams",
                description="English writer",
                confidence=0.95,
            )
        )
        client.is_available = AsyncMock(return_value=True)
        return client

    @pytest.fixture
    def mock_conceptnet_client(self):
        """Create mock ConceptNet client."""
        client = MagicMock()
        client.get_relationships = AsyncMock(
            return_value=[
                ConceptNetRelation(
                    subject="writer",
                    relation="IsA",
                    object="person",
                    weight=0.8,
                    source_uri="/a/test",
                )
            ]
        )
        return client

    @pytest.fixture
    def mock_cache(self):
        """Create mock cache."""
        cache = MagicMock(spec=EnrichmentCache)
        cache.get_yago = MagicMock(return_value=None)
        cache.get_conceptnet = MagicMock(return_value=None)
        cache.set_yago = MagicMock()
        cache.set_conceptnet = MagicMock()
        cache.get_stats = MagicMock(
            return_value=CacheStats(yago_hits=0, conceptnet_hits=0)
        )
        return cache

    @pytest.fixture
    def mock_kg_service(self):
        """Create mock knowledge graph service."""
        kg_service = MagicMock()
        kg_service.client = MagicMock()
        kg_service.client.execute_query = AsyncMock(return_value=[])
        kg_service.create_same_as_relationship = AsyncMock(return_value=True)
        kg_service.find_documents_by_entity = AsyncMock(return_value=[])
        kg_service.query_with_same_as_traversal = AsyncMock(return_value=[])
        return kg_service

    @pytest.fixture
    def service_with_kg(
        self, mock_yago_client, mock_conceptnet_client, mock_cache,
        mock_kg_service
    ):
        """Create enrichment service with KG service."""
        return EnrichmentService(
            yago_client=mock_yago_client,
            conceptnet_client=mock_conceptnet_client,
            cache=mock_cache,
            kg_service=mock_kg_service,
        )

    @pytest.mark.asyncio
    async def test_create_cross_document_links_no_kg_service(
        self, mock_yago_client, mock_conceptnet_client, mock_cache
    ):
        """Test cross-document links returns empty when no KG service."""
        service = EnrichmentService(
            yago_client=mock_yago_client,
            conceptnet_client=mock_conceptnet_client,
            cache=mock_cache,
            kg_service=None,
        )

        concept = ConceptNode(
            concept_id="c1",
            concept_name="Test",
            concept_type="ENTITY",
            confidence=0.9,
            source_document="doc1",
        )

        result = await service.create_cross_document_links(concept, "Q42")
        assert result == []

    @pytest.mark.asyncio
    async def test_create_cross_document_links_finds_matching_concepts(
        self, service_with_kg, mock_kg_service
    ):
        """Test cross-document links finds concepts with same Q-number."""
        # Mock finding other concepts with same Q-number (new Chunk-based format)
        # First call: find matching concepts with document_ids from Chunk traversal
        # Second call: get current concept's source_ids from Chunk nodes
        mock_kg_service.client.execute_query = AsyncMock(side_effect=[
            [
                {"concept_id": "c2", "document_ids": ["doc2"]},
                {"concept_id": "c3", "document_ids": ["doc3"]},
            ],
            [{"source_ids": ["doc1"]}],
        ])

        concept = ConceptNode(
            concept_id="c1",
            concept_name="Douglas Adams",
            concept_type="ENTITY",
            confidence=0.9,
            source_document="doc1",
        )

        result = await service_with_kg.create_cross_document_links(
            concept, "Q42"
        )

        # Should create SAME_AS relationships with both concepts
        assert len(result) == 2
        assert "c2" in result
        assert "c3" in result
        assert mock_kg_service.create_same_as_relationship.call_count == 2

    @pytest.mark.asyncio
    async def test_create_cross_document_links_skips_same_document(
        self, service_with_kg, mock_kg_service
    ):
        """Test cross-document links skips concepts from same document."""
        # Mock finding concepts - one from same doc, one from different
        # Uses Chunk-based document_ids format
        mock_kg_service.client.execute_query = AsyncMock(side_effect=[
            [
                {"concept_id": "c2", "document_ids": ["doc1"]},  # Same document
                {"concept_id": "c3", "document_ids": ["doc2"]},  # Different document
            ],
            [{"source_ids": ["doc1"]}],
        ])

        concept = ConceptNode(
            concept_id="c1",
            concept_name="Douglas Adams",
            concept_type="ENTITY",
            confidence=0.9,
            source_document="doc1",
        )

        result = await service_with_kg.create_cross_document_links(
            concept, "Q42"
        )

        # Should only link to concept from different document
        assert len(result) == 1
        assert "c3" in result
        assert mock_kg_service.create_same_as_relationship.call_count == 1

    @pytest.mark.asyncio
    async def test_create_cross_document_links_handles_errors(
        self, service_with_kg, mock_kg_service
    ):
        """Test cross-document links handles errors gracefully."""
        mock_kg_service.client.execute_query = AsyncMock(
            side_effect=Exception("Database error")
        )

        concept = ConceptNode(
            concept_id="c1",
            concept_name="Test",
            concept_type="ENTITY",
            confidence=0.9,
            source_document="doc1",
        )

        result = await service_with_kg.create_cross_document_links(
            concept, "Q42"
        )

        # Should return empty list on error
        assert result == []

    @pytest.mark.asyncio
    async def test_find_documents_by_entity_no_kg_service(
        self, mock_yago_client, mock_conceptnet_client, mock_cache
    ):
        """Test find_documents_by_entity returns empty when no KG service."""
        service = EnrichmentService(
            yago_client=mock_yago_client,
            conceptnet_client=mock_conceptnet_client,
            cache=mock_cache,
            kg_service=None,
        )

        result = await service.find_documents_by_entity("Q42")
        assert result == []

    @pytest.mark.asyncio
    async def test_find_documents_by_entity_delegates_to_kg_service(
        self, service_with_kg, mock_kg_service
    ):
        """Test find_documents_by_entity delegates to KG service."""
        mock_kg_service.find_documents_by_entity = AsyncMock(
            return_value=["doc1", "doc2", "doc3"]
        )

        result = await service_with_kg.find_documents_by_entity("Q42")

        assert result == ["doc1", "doc2", "doc3"]
        mock_kg_service.find_documents_by_entity.assert_called_once_with("Q42")

    @pytest.mark.asyncio
    async def test_query_cross_document_concepts_no_kg_service(
        self, mock_yago_client, mock_conceptnet_client, mock_cache
    ):
        """Test query_cross_document_concepts returns empty when no KG."""
        service = EnrichmentService(
            yago_client=mock_yago_client,
            conceptnet_client=mock_conceptnet_client,
            cache=mock_cache,
            kg_service=None,
        )

        result = await service.query_cross_document_concepts("c1")
        assert result == []

    @pytest.mark.asyncio
    async def test_query_cross_document_concepts_delegates_to_kg_service(
        self, service_with_kg, mock_kg_service
    ):
        """Test query_cross_document_concepts delegates to KG service."""
        mock_kg_service.query_with_same_as_traversal = AsyncMock(
            return_value=[
                {
                    "concept_id": "c2",
                    "name": "Related Concept",
                    "document_ids": ["doc2"],
                    "q_number": "Q42",
                    "hops": 1
                }
            ]
        )

        result = await service_with_kg.query_cross_document_concepts("c1", 2)

        assert len(result) == 1
        assert result[0]["concept_id"] == "c2"
        mock_kg_service.query_with_same_as_traversal.assert_called_once_with(
            "c1", 2
        )


# =============================================================================
# Test KnowledgeGraphService Cross-Document Methods
# =============================================================================


class TestKnowledgeGraphServiceCrossDocument:
    """Test KnowledgeGraphService cross-document linking methods."""

    @pytest.fixture
    def mock_client(self):
        """Create mock database client."""
        client = MagicMock()
        client.execute_query = AsyncMock(return_value=[])
        return client

    @pytest.fixture
    def kg_service(self, mock_client):
        """Create KG service with mock client."""
        from src.multimodal_librarian.services.knowledge_graph_service import (
            KnowledgeGraphService,
        )
        service = KnowledgeGraphService.__new__(KnowledgeGraphService)
        service.client = mock_client
        return service

    @pytest.mark.asyncio
    async def test_find_documents_by_entity(self, kg_service, mock_client):
        """Test find_documents_by_entity returns document IDs."""
        mock_client.execute_query = AsyncMock(return_value=[
            {"document_id": "doc1"},
            {"document_id": "doc2"},
            {"document_id": None},  # Should be filtered out
        ])

        result = await kg_service.find_documents_by_entity("Q42")

        assert result == ["doc1", "doc2"]
        mock_client.execute_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_documents_by_entity_handles_errors(
        self, kg_service, mock_client
    ):
        """Test find_documents_by_entity handles errors gracefully."""
        mock_client.execute_query = AsyncMock(
            side_effect=Exception("Database error")
        )

        result = await kg_service.find_documents_by_entity("Q42")

        assert result == []

    @pytest.mark.asyncio
    async def test_query_with_same_as_traversal(self, kg_service, mock_client):
        """Test query_with_same_as_traversal returns related concepts."""
        mock_client.execute_query = AsyncMock(return_value=[
            {
                "concept_id": "c2",
                "name": "Related",
                "document_ids": ["doc2"],
                "q_number": "Q42",
                "hops": 1
            }
        ])

        result = await kg_service.query_with_same_as_traversal("c1", 2)

        assert len(result) == 1
        assert result[0]["concept_id"] == "c2"
        assert result[0]["document_ids"] == ["doc2"]

    @pytest.mark.asyncio
    async def test_query_with_same_as_traversal_handles_errors(
        self, kg_service, mock_client
    ):
        """Test query_with_same_as_traversal handles errors gracefully."""
        mock_client.execute_query = AsyncMock(
            side_effect=Exception("Database error")
        )

        result = await kg_service.query_with_same_as_traversal("c1")

        assert result == []

    @pytest.mark.asyncio
    async def test_create_same_as_relationship_new(
        self, kg_service, mock_client
    ):
        """Test create_same_as_relationship creates new relationship."""
        # First call checks for existing - returns empty
        # Second call creates relationship - returns result
        mock_client.execute_query = AsyncMock(
            side_effect=[
                [],  # No existing relationship
                [{"r": {}}]  # Created relationship
            ]
        )

        result = await kg_service.create_same_as_relationship(
            "c1", "c2", "Q42"
        )

        assert result is True
        assert mock_client.execute_query.call_count == 2

    @pytest.mark.asyncio
    async def test_create_same_as_relationship_existing(
        self, kg_service, mock_client
    ):
        """Test create_same_as_relationship returns True for existing."""
        # Relationship already exists
        mock_client.execute_query = AsyncMock(return_value=[{"r": {}}])

        result = await kg_service.create_same_as_relationship(
            "c1", "c2", "Q42"
        )

        assert result is True
        # Should only check for existing, not create
        assert mock_client.execute_query.call_count == 1

    @pytest.mark.asyncio
    async def test_create_same_as_relationship_handles_errors(
        self, kg_service, mock_client
    ):
        """Test create_same_as_relationship handles errors gracefully."""
        mock_client.execute_query = AsyncMock(
            side_effect=Exception("Database error")
        )

        result = await kg_service.create_same_as_relationship(
            "c1", "c2", "Q42"
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_get_concepts_by_q_number(self, kg_service, mock_client):
        """Test get_concepts_by_q_number returns concepts."""
        mock_client.execute_query = AsyncMock(return_value=[
            {"c": {"concept_id": "c1", "name": "Test"}, "node_id": 1},
            {"c": {"concept_id": "c2", "name": "Test2"}, "node_id": 2},
        ])

        result = await kg_service.get_concepts_by_q_number("Q42")

        assert len(result) == 2
        assert result[0]["concept_id"] == "c1"
        assert result[0]["id"] == 1


# =============================================================================
# Test KnowledgeGraphService Index Creation Methods
# =============================================================================


class TestKnowledgeGraphServiceIndexCreation:
    """Test KnowledgeGraphService index creation methods.
    
    Requirements: 8.1, 8.2
    """

    @pytest.fixture
    def mock_client(self):
        """Create mock database client."""
        client = MagicMock()
        client.execute_query = AsyncMock(return_value=[])
        return client

    @pytest.fixture
    def kg_service(self, mock_client):
        """Create KG service with mock client."""
        from src.multimodal_librarian.services.knowledge_graph_service import (
            KnowledgeGraphService,
        )
        service = KnowledgeGraphService.__new__(KnowledgeGraphService)
        service.client = mock_client
        service._indexes_created = False
        return service

    @pytest.mark.asyncio
    async def test_ensure_enrichment_indexes_creates_indexes(
        self, kg_service, mock_client
    ):
        """Test ensure_enrichment_indexes creates required indexes."""
        # Mock successful index creation
        mock_client.execute_query = AsyncMock(return_value=[])

        result = await kg_service.ensure_enrichment_indexes()

        assert result["status"] in ("success", "partial")
        # Should have attempted to create both indexes
        assert "external_entity_qnum_idx" in (
            result.get("indexes_created", []) + 
            result.get("indexes_skipped", [])
        )
        assert "concept_yago_idx" in (
            result.get("indexes_created", []) + 
            result.get("indexes_skipped", [])
        )

    @pytest.mark.asyncio
    async def test_ensure_enrichment_indexes_skips_if_already_created(
        self, kg_service
    ):
        """Test ensure_enrichment_indexes skips if already created."""
        kg_service._indexes_created = True

        result = await kg_service.ensure_enrichment_indexes()

        assert result["status"] == "skipped"
        assert result["reason"] == "already_created"

    @pytest.mark.asyncio
    async def test_ensure_enrichment_indexes_handles_errors(
        self, kg_service, mock_client
    ):
        """Test ensure_enrichment_indexes handles errors gracefully."""
        # Mock Neo4j client to test error handling
        mock_client.__class__.__name__ = "Neo4jClient"
        # Mock error during index creation
        mock_client.execute_query = AsyncMock(
            side_effect=Exception("Database error")
        )

        result = await kg_service.ensure_enrichment_indexes()

        # Should still complete, but with errors
        assert result["status"] in ("failed", "partial")
        assert len(result.get("errors", [])) > 0

    def test_detect_client_type_neo4j(self, kg_service, mock_client):
        """Test _detect_client_type identifies Neo4j client."""
        mock_client.__class__.__name__ = "Neo4jClient"

        result = kg_service._detect_client_type()

        assert result == "neo4j"

    def test_detect_client_type_neptune(self, kg_service, mock_client):
        """Test _detect_client_type identifies Neptune client."""
        mock_client.__class__.__name__ = "NeptuneClient"
        mock_client.g = MagicMock()  # Gremlin traversal source

        result = kg_service._detect_client_type()

        assert result == "neptune"

    @pytest.mark.asyncio
    async def test_get_index_info_neo4j(self, kg_service, mock_client):
        """Test get_index_info returns Neo4j index information."""
        mock_client.__class__.__name__ = "Neo4jClient"
        mock_client.execute_query = AsyncMock(return_value=[
            {
                "name": "test_idx",
                "type": "BTREE",
                "labelsOrTypes": ["Concept"],
                "properties": ["yago_qid"],
                "state": "ONLINE"
            }
        ])

        result = await kg_service.get_index_info()

        assert result["status"] == "success"
        assert result["client_type"] == "neo4j"
        assert len(result["indexes"]) == 1

    @pytest.mark.asyncio
    async def test_get_index_info_neptune(self, kg_service, mock_client):
        """Test get_index_info returns Neptune index information."""
        mock_client.__class__.__name__ = "NeptuneClient"
        mock_client.g = MagicMock()

        result = await kg_service.get_index_info()

        assert result["status"] == "success"
        assert result["client_type"] == "neptune"
        assert "note" in result
        assert len(result["enrichment_indexes"]) == 2
