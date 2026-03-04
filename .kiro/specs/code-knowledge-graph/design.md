# Code Knowledge Graph Design Document

## Overview

The Code_Knowledge_Graph feature addresses the limitations of using ConceptNet for code-specific knowledge enrichment. By implementing a dedicated knowledge graph for code concepts, the system can properly handle technical terminology, API relationships, and software architecture patterns that ConceptNet cannot represent.

This design document outlines the architecture, components, data models, and integration strategy for the Code_Knowledge_Graph feature. The implementation leverages the existing Neo4j infrastructure while maintaining clear namespace isolation to prevent conflicts with existing ConceptNet data.

The feature introduces three primary components: Code_Extractor for pattern recognition and concept extraction, CodeKnowledgeGraphClient for Neo4j operations, and CodeIntelligenceSources for external data integration. These components integrate with the existing EnrichmentService to provide comprehensive code-aware enrichment for RAG queries.

## Architecture

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          Document Processing Pipeline                            │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌──────────────┐    ┌──────────────────┐    ┌──────────────────────────────┐  │
│  │   Document   │───▶│  Code_Extractor  │───▶│  CodeKnowledgeGraphClient    │  │
│  │   Content    │    │  (Pattern Rec)   │    │  (Neo4j Operations)          │  │
│  └──────────────┘    └──────────────────┘    └───────────────┬──────────────┘  │
│                                                              │                   │
│                                                              ▼                   │
│  ┌──────────────┐    ┌──────────────────┐    ┌──────────────────────────────┐  │
│  │   RAG Query  │◀───│  EnrichmentSvc   │◀───│  ConceptNet Integration      │  │
│  │   Context    │    │  (Merges Graphs) │    │  (Fallback)                  │  │
│  └──────────────┘    └──────────────────┘    └──────────────────────────────┘  │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            External Integrations                                 │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────────────┐  │
│  │ CodeIntelligence │    │   PyPI Metadata  │    │   GitHub API             │  │
│  │ Sources Interface│    │   (Seed Data)    │    │   (Repository Structure) │  │
│  └──────────────────┘    └──────────────────┘    └──────────────────────────┘  │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Architecture Overview

The Code_Knowledge_Graph architecture follows a layered approach with clear separation of concerns. The Code_Extractor operates as the first layer, processing document content to identify and normalize code patterns. This extraction layer uses regex-based pattern recognition to identify snake_case, camelCase, PascalCase identifiers, method calls, and import statements.

The CodeKnowledgeGraphClient serves as the data access layer, managing all Neo4j operations with proper namespace isolation. This client implements caching strategies to meet performance requirements and handles the circuit breaker pattern for graceful degradation. The client exposes an async API that integrates with the existing dependency injection system.

The EnrichmentService integration layer sits at the top, coordinating between Code_Knowledge_Graph and ConceptNet lookups. This layer implements the fallback logic, relationship merging, and prioritization rules defined in the requirements. The integration is transparent to callers, who receive enriched context regardless of the underlying knowledge graph source.

### Integration Points

The Code_Knowledge_Graph integrates with several existing system components. The primary integration point is the EnrichmentService, which already handles ConceptNet lookups. The Code_Knowledge_Graph integration extends this service to check code-specific relationships first, then fall back to ConceptNet for general knowledge.

The monitoring infrastructure receives metrics and health check data from the CodeKnowledgeGraphClient. This integration uses the existing structured logging and CloudWatch metrics system, ensuring consistent observability across the application.

The dependency injection system provides lazy initialization of the CodeKnowledgeGraphClient, preventing import-time database connections. This follows the established pattern for all database clients in the system.

## Components and Interfaces

### Code_Extractor

The Code_Extractor component identifies and parses code syntax patterns in document text. It implements pattern recognition algorithms for multiple naming conventions and extracts normalized concept names for lookup.

**Pattern Recognition Algorithm:**

The extractor processes text through a series of pattern recognition passes. Each pass uses compiled regex patterns to identify specific syntax constructs. The algorithm processes patterns in order of specificity, starting with the most specific patterns (import statements) and progressing to general identifier patterns.

For snake_case identifiers, the algorithm splits on underscore boundaries while preserving acronyms as single units. The normalization function converts the split words to lowercase and joins with spaces for ConceptNet compatibility. For example, "langchain_anthropic" normalizes to "langchain anthropic", and "HTTP_Request" normalizes to "http request".

For camelCase identifiers, the algorithm uses regex lookbehind to identify uppercase letter boundaries. The normalization preserves consecutive uppercase letters as single units to handle acronyms correctly. "invokeAsyncIterator" normalizes to "invoke async iterator", while "HTTPResponse" normalizes to "http response".

**Component Interface:**

```python
class CodeExtractor:
    """Extracts code concepts from document text."""
    
    async def extract_concepts(self, text: str) -> List[CodeConcept]:
        """Extract all code concepts from document text.
        
        Args:
            text: Raw document text to process
            
        Returns:
            List of extracted CodeConcept objects with normalized names
        """
        
    async def extract_relationships(
        self, 
        concepts: List[CodeConcept], 
        context: str
    ) -> List[CodeRelationship]:
        """Extract relationships between concepts based on context.
        
        Args:
            concepts: List of extracted concepts
            context: Surrounding document context for relationship inference
            
        Returns:
            List of inferred CodeRelationship objects
        """
```

### CodeKnowledgeGraphClient

The CodeKnowledgeGraphClient manages all Neo4j operations for the Code_Knowledge_Graph. It implements namespace isolation using label prefixes, handles caching for performance, and provides the async API for concept and relationship management.

**Core Operations:**

The client implements concept storage with deduplication based on normalized name hash. When storing a concept, it first checks for existing concepts with the same normalized name and type. If found, it updates the source document reference to include both documents rather than creating a duplicate.

Query operations support both exact and fuzzy matching. The fuzzy matching uses Neo4j's full-text search index with configurable similarity thresholds. The client caches frequently accessed concepts to meet the 100ms response time requirement.

**Component Interface:**

```python
class CodeKnowledgeGraphClient:
    """Neo4j client for code knowledge graph operations."""
    
    async def store_concept(
        self, 
        concept: CodeConcept
    ) -> CodeConcept:
        """Store a code concept with namespace isolation.
        
        Args:
            concept: CodeConcept to store
            
        Returns:
            Stored concept with generated ID
        """
        
    async def store_relationship(
        self, 
        relationship: CodeRelationship
    ) -> CodeRelationship:
        """Store a relationship between concepts.
        
        Args:
            relationship: CodeRelationship to create
            
        Returns:
            Created relationship with generated ID
        """
        
    async def query_concepts(
        self, 
        name: str, 
        fuzzy: bool = False
    ) -> List[CodeConcept]:
        """Query concepts by name with optional fuzzy matching.
        
        Args:
            name: Concept name (normalized or partial)
            fuzzy: Enable fuzzy matching for partial names
            
        Returns:
            Matching concepts
        """
        
    async def query_relationships(
        self, 
        concept_id: str, 
        relationship_type: Optional[str] = None
    ) -> List[CodeRelationship]:
        """Query relationships for a concept.
        
        Args:
            concept_id: Source concept identifier
            relationship_type: Optional filter for specific relationship type
            
        Returns:
            Related concepts with relationship details
        """
        
    async def get_related_concepts(
        self, 
        concept_name: str
    ) -> List[EnrichmentContext]:
        """Get all related concepts for enrichment.
        
        Args:
            concept_name: Normalized concept name
            
        Returns:
            List of enrichment contexts from related concepts
        """
```

### CodeIntelligenceSources

The CodeIntelligenceSources interface provides integration with external code knowledge providers. This component handles authentication, rate limiting, and data transformation for external API responses.

**Supported Sources:**

The initial implementation supports three intelligence sources. PyPI metadata provides package information including module structures, dependencies, and type stub references. GitHub API integration retrieves repository structure, file paths, and dependency relationships. Type stub repositories (such as typeshed) provide type information for standard library and third-party functions.

**Sync Operations:**

The sync mechanism supports both full and incremental updates. Full sync replaces all concepts from a source, used for initial seed data loading. Incremental sync fetches only changed items based on modification timestamps, used for periodic updates.

```python
class CodeIntelligenceSource(Protocol):
    """Protocol for code intelligence source integration."""
    
    async def fetch_concepts(self) -> List[CodeConcept]:
        """Fetch concepts from the intelligence source.
        
        Returns:
            List of concepts with source attribution
        """
        
    async def fetch_relationships(
        self, 
        concepts: List[CodeConcept]
    ) -> List[CodeRelationship]:
        """Fetch relationships between concepts.
        
        Args:
            concepts: Concepts to find relationships for
            
        Returns:
            Relationships with source attribution
        """
        
    async def get_last_modified(self) -> Optional[datetime]:
        """Get last modification timestamp for incremental sync.
        
        Returns:
            Timestamp of last sync or None for full sync
        """
```

## Data Models

### Neo4j Schema

The Neo4j schema uses namespace prefixes to isolate code knowledge graph data from existing ConceptNet data. All nodes use the `CodeConcept` label, and all relationships use the `CODE_` prefix for relationship types.

**Node Labels:**

```
(:CodeConcept {
    id: string (primary key, hash of normalized name + type),
    display_name: string (original extracted name),
    normalized_name: string (canonical form for lookups),
    concept_type: string (FUNCTION | CLASS | MODULE | METHOD | LIBRARY | API_ENDPOINT | TYPE | CONSTANT),
    source_documents: list[string] (document IDs referencing this concept),
    first_extracted_at: datetime,
    last_updated_at: datetime,
    version: integer (increment on update),
    metadata: map (additional source-specific data)
})
```

**Relationship Types:**

```
(:CodeConcept)-[:CODE_CALLS {
    source_document: string,
    confidence: float (0.0-1.0),
    context: string (extraction context snippet),
    created_at: datetime
}]->(:CodeConcept)

(:CodeConcept)-[:CODE_DEFINES {
    source_document: string,
    confidence: float,
    context: string,
    created_at: datetime
}]->(:CodeConcept)

(:CodeConcept)-[:CODE_IMPORTS {
    source_document: string,
    confidence: float,
    context: string,
    created_at: datetime
}]->(:CodeConcept)

(:CodeConcept)-[:CODE_INHERITS_FROM {
    source_document: string,
    confidence: float,
    context: string,
    created_at: datetime
}]->(:CodeConcept)

(:CodeConcept)-[:CODE_IMPLEMENTS {
    source_document: string,
    confidence: float,
    context: string,
    created_at: datetime
}]->(:CodeConcept)

(:CodeConcept)-[:CODE_RETURNS_TYPE {
    source_document: string,
    confidence: float,
    context: string,
    created_at: datetime
}]->(:CodeConcept)

(:CodeConcept)-[:CODE_PARAMETER_TYPE {
    source_document: string,
    parameter_name: string,
    confidence: float,
    context: string,
    created_at: datetime
}]->(:CodeConcept)

(:CodeConcept)-[:CODE_DOCUMENTED_BY {
    source_document: string,
    confidence: float,
    context: string,
    created_at: datetime
}]->(:CodeConcept)
```

**Indexes:**

```cypher
CREATE INDEX code_concept_normalized_name_idx 
FOR (n:CodeConcept) ON (n.normalized_name)

CREATE INDEX code_concept_type_idx 
FOR (n:CodeConcept) ON (n.concept_type)

CREATE INDEX code_concept_display_name_idx 
FOR (n:CodeConcept) ON (n.display_name)

CREATE FULLTEXT INDEX code_concept_fulltext_idx 
FOR (n:CodeConcept) ON EACH [n.normalized_name, n.display_name]
```

### Pydantic Models

```python
from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional
from enum import Enum

class ConceptType(str, Enum):
    FUNCTION = "FUNCTION"
    CLASS = "CLASS"
    MODULE = "MODULE"
    METHOD = "METHOD"
    LIBRARY = "LIBRARY"
    API_ENDPOINT = "API_ENDPOINT"
    TYPE = "TYPE"
    CONSTANT = "CONSTANT"

class CodeConcept(BaseModel):
    """Represents a code concept extracted from documents."""
    id: Optional[str] = None
    display_name: str = Field(..., description="Original extracted name")
    normalized_name: str = Field(..., description="Canonical form for lookups")
    concept_type: ConceptType
    source_documents: List[str] = Field(default_factory=list)
    first_extracted_at: datetime = Field(default_factory=datetime.utcnow)
    last_updated_at: datetime = Field(default_factory=datetime.utcnow)
    version: int = Field(default=1)
    metadata: dict = Field(default_factory=dict)

class CodeRelationshipType(str, Enum):
    CALLS = "CODE_CALLS"
    DEFINES = "CODE_DEFINES"
    IMPORTS = "CODE_IMPORTS"
    INHERITS_FROM = "CODE_INHERITS_FROM"
    IMPLEMENTS = "CODE_IMPLEMENTS"
    RETURNS_TYPE = "CODE_RETURNS_TYPE"
    PARAMETER_TYPE = "CODE_PARAMETER_TYPE"
    DOCUMENTED_BY = "CODE_DOCUMENTED_BY"

class CodeRelationship(BaseModel):
    """Represents a relationship between code concepts."""
    id: Optional[str] = None
    source_concept_id: str
    target_concept_id: str
    relationship_type: CodeRelationshipType
    source_document: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    context: Optional[str] = None
    parameter_name: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class EnrichmentContext(BaseModel):
    """Context for RAG enrichment from knowledge graph."""
    concept: CodeConcept
    relationships: List[CodeRelationship] = Field(default_factory=list)
    source: str = Field(default="code_knowledge_graph")
    confidence: float = Field(default=1.0)
```

### Pattern Normalization Algorithm

The normalization algorithm converts extracted code patterns to canonical forms suitable for both Neo4j lookups and ConceptNet fallback queries.

```python
def normalize_identifier(identifier: str) -> str:
    """Normalize a code identifier to canonical form.
    
    Args:
        identifier: Raw identifier from document text
        
    Returns:
        Normalized name suitable for lookups
    """
    # Remove leading/trailing whitespace and underscores
    normalized = identifier.strip().strip('_')
    
    # Handle snake_case: split on underscores, preserve acronyms
    if '_' in normalized and not normalized.replace('_', '').isupper():
        parts = normalized.split('_')
        # Keep consecutive uppercase as single unit (HTTP_Request -> HTTP Request)
        words = []
        for part in parts:
            if part.isupper() and len(part) > 1:
                words.append(part)
            else:
                words.append(part.lower())
        return ' '.join(words)
    
    # Handle camelCase/PascalCase: split on uppercase boundaries
    words = []
    current_word = ''
    for i, char in enumerate(normalized):
        if char.isupper():
            if current_word:
                words.append(current_word)
            current_word = char.lower()
        elif char.isdigit():
            if current_word and not current_word[-1].isdigit():
                words.append(current_word)
                current_word = ''
            current_word += char
        else:
            current_word += char
    
    if current_word:
        words.append(current_word)
    
    return ' '.join(words)

# Examples:
# "langchain_anthropic" -> "langchain anthropic"
# "invokeAsyncIterator" -> "invoke async iterator"
# "HTTP_Request" -> "http request"
# "__private_method" -> "private method"
# "parse2DArray" -> "parse 2d array"
```



## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Concept Deduplication

*For any* CodeConcept with a given normalized name and concept type, storing it multiple times from different source documents SHALL result in a single concept node with all source documents in the source_documents list.

**Validates: Requirements 1.2, 1.3**

### Property 2: Pattern Normalization Consistency

*For any* code identifier, applying the normalization algorithm SHALL produce the same normalized form regardless of the context in which the identifier appears in the document.

**Validates: Requirements 1.1, 2.1, 2.2, 2.6**

### Property 3: Relationship Referential Integrity

*For any* CodeRelationship created between two concepts, both the source and target concepts SHALL exist in the knowledge graph, and deleting either concept SHALL cascade delete the relationship.

**Validates: Requirements 3.1, 11.1, 11.3**

### Property 4: Enrichment Service Fallback and Merging

*For any* CodeConcept, the EnrichmentService SHALL first query the Code_Knowledge_Graph, then fall back to ConceptNet if no relationships are found, and merge relationships from both sources when available, with Code_Knowledge_Graph relationships prioritized.

**Validates: Requirements 4.1, 4.2, 4.3, 4.4**

### Property 5: Query Performance Bound

*For any* query against the Code_Knowledge_Graph for a cached concept, the response time SHALL NOT exceed 100 milliseconds, and store operations SHALL complete within 50 milliseconds.

**Validates: Requirements 6.5, 9.1, 9.2**

### Property 6: Batch Operation Throughput

*For any* batch of up to 1000 concept store operations, the total processing time SHALL NOT exceed 500 milliseconds.

**Validates: Requirements 9.3**

### Property 7: Namespace Isolation

*For any* query scoped to CodeConcept nodes using the CodeConcept label and CODE_ relationship prefix, the results SHALL NOT include any nodes from the general knowledge graph, and vice versa.

**Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5**

### Property 8: Graceful Degradation

*For any* EnrichmentService operation when the Code_Knowledge_Graph is unavailable, the service SHALL continue processing using ConceptNet only, logging a warning without raising an exception.

**Validates: Requirements 9.5, 14.1, 14.4**

### Property 9: Seed Data Completeness

*For any* seed concept in the initial seed dataset, the concept SHALL exist in the knowledge graph after initial setup, and all defined relationships between seed concepts SHALL be present.

**Validates: Requirements 12.1, 12.2, 12.3**

### Property 10: Write Atomicity

*For any* store operation for a concept with relationships, either both the concept and all relationships SHALL be successfully stored in a single transaction, or none SHALL be stored.

**Validates: Requirements 11.2**

### Property 11: Code Pattern Extraction

*For any* document text containing code patterns, the Code_Extractor SHALL correctly identify and extract snake_case identifiers, camelCase identifiers, method calls with parentheses, dot notation, and import statements, handling edge cases including acronyms, numbers, and leading underscores.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6**

### Property 12: Relationship Type Coverage

*For any* pair of concepts that have a code relationship (function calls, class defines method, module imports, class inherits, function returns type, function has parameter type), the Code_Knowledge_Graph SHALL create the appropriate relationship type (CALLS, DEFINES, IMPORTS, INHERITS_FROM, RETURNS_TYPE, PARAMETER_TYPE) with complete metadata.

**Validates: Requirements 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8**

## Error Handling

### Circuit Breaker Configuration

The CodeKnowledgeGraphClient implements the circuit breaker pattern to prevent cascade failures during extended outages. The circuit breaker uses three states: closed (normal operation), open (failures detected, fast-fail), and half-open (testing recovery).

```python
from async_timeout import timeout
from tenacity import retry, stop_after_attempt, wait_exponential

class CircuitBreaker:
    """Circuit breaker for Neo4j operations."""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_success_threshold: int = 3
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_success_threshold = half_open_success_threshold
        self.state = "closed"
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
```

### Retry Logic

Write operations implement exponential backoff retry with jitter. The retry configuration attempts up to 3 operations with increasing delays between attempts.

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.1, min=0.1, max=1.0)
)
async def store_concept_with_retry(self, concept: CodeConcept) -> CodeConcept:
    """Store concept with automatic retry on transient failures."""
    async with self._circuit_breaker:
        async with self._neo4j_session:
            return await self._store_concept_impl(concept)
```

### Fallback Behavior

When the Code_Knowledge_Graph is unavailable, the EnrichmentService falls back to ConceptNet-only enrichment. This fallback is transparent to callers and includes warning-level logging.

```python
async def enrich_concept(
    self,
    concept_name: str,
    context: Optional[str] = None
) -> EnrichmentResult:
    """Enrich a concept with code and general knowledge."""
    # Try Code_Knowledge_Graph first
    try:
        code_contexts = await self._code_graph.get_related_concepts(concept_name)
        if code_contexts:
            return EnrichmentResult(contexts=code_contexts, source="code_knowledge_graph")
    except CodeGraphUnavailableError:
        logger.warning("Code_Knowledge_Graph unavailable, falling back to ConceptNet")
    
    # Fall back to ConceptNet
    conceptnet_contexts = await self._conceptnet.get_related_concepts(concept_name)
    return EnrichmentResult(contexts=conceptnet_contexts, source="conceptnet")
```

### Timeout Handling

All Neo4j operations use configurable timeouts. Query operations timeout at 5 seconds, and store operations timeout at 10 seconds. Timeout errors are caught and converted to empty result sets with appropriate logging.

```python
async def query_concepts(
    self,
    name: str,
    fuzzy: bool = False,
    timeout_seconds: float = 5.0
) -> List[CodeConcept]:
    """Query concepts with timeout protection."""
    try:
        async with timeout(timeout_seconds):
            return await self._query_concepts_impl(name, fuzzy)
    except asyncio.TimeoutError:
        logger.error(f"Query timeout for concept name: {name}")
        return []
```

## Testing Strategy

### Dual Testing Approach

The Code_Knowledge_Graph implementation requires both unit tests and property-based tests for comprehensive coverage. Unit tests verify specific examples and edge cases, while property-based tests validate universal properties across generated inputs.

### Unit Testing Focus

Unit tests cover the following areas:

- Pattern normalization edge cases (acronyms, numbers, underscores)
- Concept deduplication logic with multiple source documents
- Relationship creation with various type combinations
- Circuit breaker state transitions
- Fallback behavior when services are unavailable
- Seed data loading and validation

### Property-Based Testing Configuration

Property-based tests use the Hypothesis library with the following configuration:

```python
import hypothesis
from hypothesis import given, settings
from hypothesis.strategies import text, lists, dictionaries

@given(
    concept_name=text(min_size=1, max_size=100, alphabet=ascii_letters + '_'),
    concept_type=st.sampled_from(ConceptType)
)
@settings(max_examples=100, deadline=1000)
async def test_concept_normalization_idempotence(concept_name, concept_type):
    """Normalizing twice should produce the same result."""
    normalized1 = normalize_identifier(concept_name)
    normalized2 = normalize_identifier(normalized1)
    assert normalized1 == normalized2

@given(
    concepts=lists(
        dictionaries({
            'display_name': text(min_size=1, max_size=50),
            'concept_type': st.sampled_from(ConceptType)
        }),
        min_size=1,
        max_size=1000
    )
)
@settings(max_examples=50, deadline=5000)
async def test_batch_store_performance(concepts):
    """Batch store of 1000 concepts should complete within 500ms."""
    start_time = time.monotonic()
    results = await client.batch_store_concepts(concepts)
    elapsed = time.monotonic() - start_time
    assert elapsed < 0.5
    assert len(results) == len(concepts)
```

### Test Tag Format

All property-based tests include tags referencing the design document properties:

```python
# Feature: code-knowledge-graph, Property 2: Pattern Normalization Consistency
@given(identifier=text(alphabet=ascii_letters + '_', min_size=1, max_size=50))
@settings(max_examples=100)
async def test_normalization_consistency(identifier):
    normalized = normalize_identifier(identifier)
    assert normalize_identifier(normalized) == normalized
```

### Integration Testing

Integration tests verify the complete enrichment pipeline with real Neo4j connections:

- Document processing with code extraction
- EnrichmentService coordination between Code_Knowledge_Graph and ConceptNet
- Performance under concurrent load
- Circuit breaker activation during simulated outages

### Mock Testing

Unit tests use mocked Neo4j connections to verify error handling without requiring database infrastructure:

```python
@pytest.fixture
def mock_neo4j_session():
    """Mock Neo4j session for unit testing."""
    session = AsyncMock(spec=Neo4jSession)
    session.run = AsyncMock(return_value=MockCursor([]))
    return session

def test_store_concept_deduplication(mock_neo4j_session):
    """Test that duplicate concepts are merged."""
    client = CodeKnowledgeGraphClient(session_factory=lambda: mock_neo4j_session)
    
    concept1 = CodeConcept(
        display_name="HTTP_Request",
        normalized_name="http request",
        concept_type=ConceptType.CLASS
    )
    
    concept2 = CodeConcept(
        display_name="HTTP_Request", 
        normalized_name="http request",
        concept_type=ConceptType.CLASS
    )
    
    result1 = await client.store_concept(concept1)
    result2 = await client.store_concept(concept2)
    
    # Should return same concept with merged source documents
    assert result1.id == result2.id
    assert len(result2.source_documents) == 2
```

## Implementation Plan

### Task Breakdown

**Phase 1: Core Infrastructure**

1. Create Neo4j schema with namespace isolation
   - Dependencies: None
   - Creates indexes and constraints for CodeConcept nodes

2. Implement CodeKnowledgeGraphClient with basic CRUD operations
   - Dependencies: Task 1
   - Async API for concept and relationship management

3. Implement pattern normalization algorithm
   - Dependencies: None
   - Unit tests for all pattern types

**Phase 2: Code Extraction**

4. Implement Code_Extractor component
   - Dependencies: Task 3
   - Regex patterns for all code syntax types

5. Implement relationship inference from context
   - Dependencies: Task 4
   - Heuristics for CALLS, DEFINES, IMPORTS relationships

**Phase 3: Integration**

6. Integrate with EnrichmentService
   - Dependencies: Tasks 2, 4
   - Fallback logic and relationship merging

7. Implement ConceptNet fallback
   - Dependencies: Task 6
   - Normalized term lookup for general knowledge

**Phase 4: External Sources**

8. Implement CodeIntelligenceSources interface
   - Dependencies: Task 2
   - Protocol definition and base class

9. Implement PyPI metadata source
   - Dependencies: Task 8
   - Package and module concept extraction

10. Implement GitHub API source
    - Dependencies: Task 8
    - Repository structure and dependency extraction

**Phase 5: Seed Data and Validation**

11. Create seed dataset for Python stdlib
    - Dependencies: Task 2
    - Common modules, functions, and types

12. Create seed dataset for LLM libraries
    - Dependencies: Task 2
    - OpenAI, Anthropic, LangChain concepts

13. Implement seed data loader
    - Dependencies: Tasks 11, 12
    - Versioned loading with validation

**Phase 6: Observability**

14. Add health check endpoints
    - Dependencies: Task 2
    - Connectivity and status checks

15. Add metrics collection
    - Dependencies: Task 2
    - Query latency, cache hit rate, concept count

16. Add structured logging
    - Dependencies: Task 2
    - Concept additions, sync operations, errors

### Dependency Graph

```
Task 1 ──┬──▶ Task 2 ──┬──▶ Task 6 ──┬──▶ Task 7
         │             │             │
         │             ▼             │
         │         Task 4 ──▶ Task 5 │
         │             │             │
         ▼             ▼             ▼
Task 3 ──┴────────────────────────────▶ Task 8 ──┬──▶ Task 9 ──┬──▶ Task 10
                                                   │             │
                                                   ▼             ▼
                              Task 11 ──┬──▶ Task 13 ◀─────── Task 12
                              Task 12 ──┘             │
                                                   ▼
                              Task 14 ──┬──▶ Task 15 ──▶ Task 16
```

### Estimated Effort

- Phase 1 (Core Infrastructure): 3-4 days
- Phase 2 (Code Extraction): 2-3 days
- Phase 3 (Integration): 2 days
- Phase 4 (External Sources): 3-4 days
- Phase 5 (Seed Data): 2 days
- Phase 6 (Observability): 1-2 days

Total estimated effort: 13-17 days