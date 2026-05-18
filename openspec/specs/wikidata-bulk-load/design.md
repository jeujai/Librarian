# YAGO Bulk Load Design

## Introduction

This document defines the technical design for bulk-loading YAGO into Neo4j to enable local knowledge graph queries. The system replaces external API calls with local Neo4j queries while maintaining graceful degradation.

## Architecture Overview

The system consists of three main components in a pipeline:

```
YAGO Dump → YagoDumpProcessor → YagoNeo4jLoader → Neo4j (yago namespace)
                                                            ↓
YagoLocalClient ← EnrichmentService ← Query Interface
```

### Component Responsibilities

1. **YagoDumpProcessor**: Downloads and streams the YAGO data dump with memory limits
2. **YagoNeo4jLoader**: Batch imports filtered entities into Neo4j with retry logic
3. **YagoLocalClient**: Local query API (similar to ConceptNetClient pattern)

## Data Flow

1. Download YAGO data dump with resume support
2. Stream process line-by-line with 512MB memory limit
3. Filter for English labels only (en, en-gb, en-us)
4. Extract entity ID, label, description, instanceOf (P31), subclassOf (P279)
5. Batch import into Neo4j with 1000-entity batches
6. YagoLocalClient queries local Neo4j data
7. Fall back to external API if local data unavailable

## Component Specifications

### YagoDumpProcessor

**Responsibilities:**
- Download YAGO dump with HTTP resume support
- Stream process line-by-line with memory limits
- Filter for English entities
- Emit filtered entities for import

**Interface:**
```python
class YagoDumpProcessor:
    def __init__(self, dump_path: str, output_path: str):
        """Initialize processor with dump path and filtered output path."""
        
    async def download(self, url: str) -> str:
        """Download YAGO dump with resume support."""
        
    async def process(self, checkpoint_interval: int = 10000) -> AsyncIterator[FilteredEntity]:
        """Stream process dump, yielding filtered English entities."""
        
    def get_progress(self) -> float:
        """Return processing progress as percentage."""
```

**Memory Management:**
- Process one line at a time (one JSON entity per line)
- Use streaming JSON parser (ijson or similar)
- Emit entities immediately, don't buffer
- Maximum memory: 512MB

**English Filtering:**
```python
def has_english_label(entity: dict) -> bool:
    """Check if entity has English label."""
    labels = entity.get("labels", {})
    return any(lang in labels for lang in ["en", "en-gb", "en-us"])

def extract_english_data(entity: dict) -> FilteredEntity:
    """Extract entity data with English label."""
    labels = entity.get("labels", {})
    descriptions = entity.get("descriptions", {})
    
    # Get first available English label
    english_label = None
    for lang in ["en", "en-gb", "en-us"]:
        if lang in labels:
            english_label = labels[lang].get("value")
            break
    
    # Get English description
    english_desc = None
    for lang in ["en", "en-gb", "en-us"]:
        if lang in descriptions:
            english_desc = descriptions[lang].get("value")
            break
    
    return FilteredEntity(
        entity_id=entity["id"],
        label=english_label,
        description=english_desc,
        instance_of=extract_claims(entity, "P31"),
        subclass_of=extract_claims(entity, "P279"),
        aliases=extract_aliases(entity),
        see_also=extract_see_also(entity)
    )
```

### YagoNeo4jLoader

**Responsibilities:**
- Batch import entities into Neo4j
- Create :YagoEntity nodes with properties
- Create :INSTANCE_OF, :SUBCLASS_OF, :ALIAS_OF, :SEE_ALSO relationships
- Handle retries and dead-letter queue

**Interface:**
```python
class YagoNeo4jLoader:
    def __init__(self, neo4j_client: GraphClient, batch_size: int = 1000):
        """Initialize loader with Neo4j client and batch size."""
        
    async def import_entities(
        self, 
        entities: AsyncIterator[FilteredEntity]
    ) -> ImportResult:
        """Import entities with batch transactions and retry logic."""
        
    async def create_entity_node(self, entity: FilteredEntity) -> int:
        """Create YagoEntity node, return node ID."""
        
    async def create_relationships(
        self, 
        entity_id: str, 
        relationships: List[Relationship]
    ) -> int:
        """Create relationships from entity to targets."""
        
    async def get_stats(self) -> YagoStats:
        """Return entity and relationship counts."""
        
    async def clear_all(self) -> None:
        """Remove all YAGO data from Neo4j."""
```

**Batch Import with Retry:**
```python
async def import_entities(
    self, 
    entities: AsyncIterator[FilteredEntity]
) -> ImportResult:
    """Import entities with 3 retries per batch."""
    batch = []
    result = ImportResult()
    
    async for entity in entities:
        batch.append(entity)
        
        if len(batch) >= self.batch_size:
            success = await self._import_batch(batch)
            if success:
                result.imported += len(batch)
            else:
                result.failed.extend(batch)
            batch = []
    
    # Process remaining entities
    if batch:
        await self._import_batch(batch)
    
    return result

async def _import_batch(self, batch: List[FilteredEntity]) -> bool:
    """Import batch with retry logic."""
    for attempt in range(3):
        try:
            await self._execute_batch_import(batch)
            return True
        except Exception as e:
            logger.warning(f"Batch import attempt {attempt + 1} failed: {e}")
            if attempt == 2:
                return False
    return False
```

### YagoLocalClient

**Responsibilities:**
- Query YAGO data from local Neo4j
- Provide same interface as external API client
- Return None when data unavailable (graceful degradation)

**Interface:**
```python
class YagoLocalClient:
    """Local client for YAGO data in Neo4j."""
    
    async def get_entity(self, entity_id: str) -> Optional[YagoEntityData]:
        """Get YAGO entity by ID."""
        
    async def search_entities(
        self, 
        query: str, 
        limit: int = 10
    ) -> List[YagoSearchResult]:
        """Fuzzy search by English label."""
        
    async def get_instances_of(
        self, 
        class_id: str, 
        limit: int = 100
    ) -> List[str]:
        """Get all entities that are instances of a class."""
        
    async def get_subclasses_of(
        self, 
        class_id: str, 
        limit: int = 100
    ) -> List[str]:
        """Get all subclasses of a class."""
        
    async def get_related_entities(
        self, 
        entity_id: str, 
        relationship_type: str
    ) -> List[str]:
        """Get related entities by relationship type."""
        
    async def is_available(self) -> bool:
        """Check if YAGO data is loaded."""
```

**Neo4j Query Examples:**
```python
async def get_entity(self, entity_id: str) -> Optional[YagoEntityData]:
    """Get YAGO entity from Neo4j."""
    query = """
    MATCH (e:YagoEntity {entity_id: $entity_id})
    RETURN e.entity_id as id, e.label as label, e.description as description,
           e.data as data
    """
    result = await self._neo4j.execute_query(query, {"entity_id": entity_id})
    if not result:
        return None
    return YagoEntityData(**result[0])

async def search_entities(self, query: str, limit: int = 10) -> List[YagoSearchResult]:
    """Fuzzy search by English label."""
    query = """
    MATCH (e:YagoEntity)
    WHERE e.label CONTAINS $query
    RETURN e.entity_id as id, e.label as label, e.description as description
    ORDER BY e.label
    LIMIT $limit
    """
    results = await self._neo4j.execute_query(query, {"query": query, "limit": limit})
    return [YagoSearchResult(**r) for r in results]

async def get_instances_of(self, class_id: str, limit: int = 100) -> List[str]:
    """Get entities that are instances of a class."""
    query = """
    MATCH (e:YagoEntity)-[:INSTANCE_OF]->(c:YagoEntity {entity_id: $class_id})
    RETURN e.entity_id as id
    LIMIT $limit
    """
    results = await self._neo4j.execute_query(query, {"class_id": class_id, "limit": limit})
    return [r["id"] for r in results]
```

## Data Models

### FilteredEntity (Intermediate Representation)

```python
@dataclass
class FilteredEntity:
    """Entity filtered from YAGO dump."""
    entity_id: str              # e.g., "Q42"
    label: Optional[str]        # English label
    description: Optional[str]  # English description
    instance_of: List[str]      # P31 target IDs
    subclass_of: List[str]      # P279 target IDs
    aliases: List[str]          # Alias labels
    see_also: List[str]         # See also IDs
```

### YagoEntityData (Query Response)

```python
@dataclass
class YagoEntityData:
    """YAGO entity data for enrichment."""
    entity_id: str
    label: str
    description: Optional[str]
    instance_of: List[str]
    subclass_of: List[str]
    aliases: List[str]
    confidence: float = 1.0  # Local data has full confidence
    
    @classmethod
    def from_filtered_entity(cls, entity: FilteredEntity) -> "YagoEntityData":
        """Create from filtered entity."""
        return cls(
            entity_id=entity.entity_id,
            label=entity.label,
            description=entity.description,
            instance_of=entity.instance_of,
            subclass_of=entity.subclass_of,
            aliases=entity.aliases
        )
```

### YagoSearchResult

```python
@dataclass
class YagoSearchResult:
    """Search result for fuzzy lookup."""
    entity_id: str
    label: str
    description: Optional[str]
    score: float = 1.0
```

## Neo4j Schema

### Nodes

```
(:YagoEntity {
    entity_id: string,    # Q-number (e.g., "Q42")
    label: string,        # English label
    description: string,  # English description
    data: string          # Full JSON data
})
```

### Relationships

```
(:YagoEntity)-[:INSTANCE_OF]->(:YagoEntity)
(:YagoEntity)-[:SUBCLASS_OF]->(:YagoEntity)
(:YagoEntity)-[:ALIAS_OF]->(:YagoEntity {label: string})
(:YagoEntity)-[:SEE_ALSO]->(:YagoEntity)
```

### Namespace Isolation

YAGO data is stored in a dedicated namespace:
- Node labels: `:YagoEntity` (no prefix, but isolated by label)
- Relationship types: `:INSTANCE_OF`, `:SUBCLASS_OF`, `:ALIAS_OF`, `:SEE_ALSO`

This is separate from:
- Document concepts: `:Concept` nodes in "concepts" namespace
- ConceptNet data: `:ConceptNetConcept` nodes in "concept" namespace

## Correctness Properties

### Download Properties

1. **Resume Support**: If download is interrupted and resumed, all previously downloaded bytes are preserved
2. **Checksum Verification**: Downloaded file matches MD5 checksum from Wikimedia
3. **Complete Download**: When download completes, file is fully verified

### Processing Properties

4. **Memory Bound**: Peak memory usage never exceeds 512MB during processing
5. **English Only**: Only entities with English labels (en, en-gb, en-us) are emitted
6. **Data Preservation**: All English label, description, and claim data is preserved
7. **Throughput**: At least 10,000 entities processed per second

### Import Properties

8. **Batch Atomicity**: Each batch of 1000 entities is imported atomically
9. **Relationship Creation**: All instanceOf and subclassOf claims become relationships
10. **No Duplicate Nodes**: Each entity ID creates exactly one node
11. **Namespace Isolation**: YAGO nodes use :YagoEntity label only

### Query Properties

12. **Local Query Accuracy**: YagoLocalClient returns same data as external API
13. **Graceful Degradation**: Returns None when local data unavailable
14. **Fallback Behavior**: External API used when local client returns None

### Error Handling Properties

15. **Retry Logic**: Failed batch imports are retried 3 times
16. **Progress Tracking**: Last successfully imported entity ID is tracked
17. **Dead Letter Queue**: Failed batches are logged for later retry

### Incremental Update Properties

18. **Update Processing**: Incremental dumps update existing entities
19. **Deletion Processing**: Entities not in incremental dump are removed
20. **Timestamp Tracking**: Last processed timestamp is maintained

### Performance Properties

21. **Query Latency**: Local queries complete in under 100ms
22. **Import Rate**: At least 1000 entities imported per second
23. **Storage Efficiency**: English-only import reduces storage by ~80%
24. **Memory Efficiency**: Streaming processing uses constant memory

## Error Handling

### Retry Logic

```python
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

async def _import_batch_with_retry(self, batch: List[FilteredEntity]) -> bool:
    """Import batch with exponential backoff."""
    for attempt in range(MAX_RETRIES):
        try:
            await self._execute_batch_import(batch)
            return True
        except Neo4jConnectionError as e:
            delay = RETRY_DELAY * (2 ** attempt)
            logger.warning(f"Batch import failed, retrying in {delay}s: {e}")
            await asyncio.sleep(delay)
        except Exception as e:
            logger.error(f"Batch import failed permanently: {e}")
            self._dead_letter_queue.append(batch)
            return False
    return False
```

### Dead Letter Queue

```python
class DeadLetterQueue:
    """Queue for failed batches."""
    
    def __init__(self, max_size: int = 1000):
        self._queue: List[FilteredEntity] = []
        self._max_size = max_size
    
    def append(self, batch: List[FilteredEntity]) -> None:
        """Add failed batch to queue."""
        self._queue.extend(batch)
        if len(self._queue) > self._max_size:
            # Remove oldest entries
            self._queue = self._queue[-self._max_size:]
    
    def retry(self) -> List[FilteredEntity]:
        """Get all failed entities for retry."""
        failed = self._queue.copy()
        self._queue.clear()
        return failed
```

### Graceful Degradation

```python
class YagoAPIFallback:
    """Fallback to external API when local data unavailable."""
    
    def __init__(
        self, 
        local_client: YagoLocalClient,
        external_client: YagoClient
    ):
        self._local = local_client
        self._external = external_client
    
    async def get_entity(self, entity_id: str) -> Optional[YagoEntityData]:
        """Try local first, fall back to external."""
        local_result = await self._local.get_entity(entity_id)
        if local_result is not None:
            logger.info(f"YAGO: local lookup for {entity_id}")
            return local_result
        
        external_result = await self._external.search_entity(entity_id)
        if external_result is not None:
            logger.info(f"YAGO: API fallback for {entity_id}")
            return external_result
        
        logger.warning(f"YAGO: not found (local or API) for {entity_id}")
        return None
```

## Integration with Enrichment Service

### Dependency Injection

```python
# In api/dependencies/services.py

async def get_yago_local_client() -> Optional[YagoLocalClient]:
    """Get YAGO local client, return None if not loaded."""
    try:
        client = YagoLocalClient(
            neo4j_client=await get_graph_client()
        )
        if await client.is_available():
            return client
        return None
    except Exception as e:
        logger.warning(f"YAGO local client unavailable: {e}")
        return None

async def get_yago_client() -> YagoClient:
    """Get YAGO client with local-first fallback."""
    local = await get_yago_local_client()
    external = YagoClient()
    
    if local is not None:
        return YagoAPIFallback(local, external)
    return external
```

### Usage in Enrichment Service

```python
# In services/enrichment_service.py

class EnrichmentService:
    def __init__(
        self,
        yago_client: YagoClient = Depends(get_yago_client),
        conceptnet_client: ConceptNetClient = Depends(get_conceptnet_client),
        # ... other dependencies
    ):
        self.yago = yago_client
        # ...
    
    async def _get_yago_entity(self, concept: ConceptNode) -> Optional[YagoEntity]:
        """Get YAGO entity using local-first client."""
        # This now uses local Neo4j data if available,
        # falls back to external API if not
        return await self.yago.search_entity(concept.concept_name)
```

## Testing Strategy

### Unit Tests

- Test YagoDumpProcessor filtering logic
- Test YagoNeo4jLoader batch import
- Test YagoLocalClient query methods
- Test English label detection
- Test relationship extraction

### Property-Based Tests

- **Memory Property**: Processing never exceeds 512MB
- **Filtering Property**: Only English entities are emitted
- **Query Property**: Local queries return same data as external API
- **Import Property**: All filtered entities are imported

### Integration Tests

- Complete pipeline test with small dump
- Error recovery and retry logic
- Graceful degradation when Neo4j unavailable
- Fallback to external API

### Performance Tests

- Throughput: 10,000 entities/second processing
- Import rate: 1,000 entities/second to Neo4j
- Query latency: <100ms for local queries
- Memory usage: <512MB during processing

## Implementation Tasks

See tasks.md for detailed implementation breakdown.
