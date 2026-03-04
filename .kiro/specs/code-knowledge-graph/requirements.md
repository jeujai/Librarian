# Code Knowledge Graph Requirements Document

## Introduction

The Multimodal Librarian currently uses ConceptNet for knowledge graph enrichment to provide contextual relationships between concepts extracted from documents. However, ConceptNet has significant limitations when processing technical and code-related content:

- **Exact match dependency**: ConceptNet lookups require exact term matching, but code concepts often use inconsistent naming conventions (snake_case, camelCase, PascalCase)
- **Coverage gap**: Technical terms like "langchain_anthropic", "invoke()", "from_messages", and "AsyncIterator" do not exist in ConceptNet
- **Relationship absence**: Analysis shows 3,604 CODE_TERM concepts (15% of document concepts) have zero relationships because they cannot be found in ConceptNet
- **Domain mismatch**: ConceptNet is designed for general world knowledge, not software engineering concepts, APIs, or code patterns

The Code_Knowledge_Graph feature addresses these limitations by providing a dedicated knowledge graph for code-specific concepts. This feature enables semantic enrichment of technical documents, improved RAG responses for code-related queries, and better understanding of software architecture and API relationships.

## Glossary

- **Code_Knowledge_Graph**: A specialized knowledge graph that stores relationships between code-specific concepts including classes, functions, modules, APIs, and programming constructs
- **Code_Concept**: A discrete code-related term extracted from documents, including function names, class names, module names, method signatures, library names, and API endpoints
- **Code_Pattern**: A recognized syntax pattern in source code, including snake_case, camelCase, PascalCase, method calls with parentheses, dot notation for attribute access, and import statements
- **ConceptNet**: The existing general-purpose knowledge graph used for non-code concept enrichment
- **Code_Extractor**: The component responsible for identifying and extracting code concepts from document content
- **Code_Relationship**: A directed or undirected edge between two Code_Concepts representing a meaningful connection such as inheritance, composition, usage, or documentation
- **Namespace**: A logical partition within Neo4j that isolates the Code_Knowledge_Graph from other data including ConceptNet relationships
- **Code_Intelligence_Source**: An external data provider that supplies code knowledge such as type hierarchies, API documentation, or code search results

## Requirements

### Requirement 1: Code Concept Storage

**User Story:** As a system, I want to store code-specific concepts in a dedicated knowledge graph, so that technical terms from documents can be enriched with relationships.

#### Acceptance Criteria

1. THE Code_Knowledge_Graph SHALL store Code_Concepts with the following attributes: concept identifier, display name, concept type, source document reference, and extraction timestamp
2. THE Code_Knowledge_Graph SHALL support concept types: FUNCTION, CLASS, MODULE, METHOD, LIBRARY, API_ENDPOINT, TYPE, and CONSTANT
3. WHEN a Code_Concept is stored, THE Code_Knowledge_Graph SHALL normalize the display name to a canonical form for consistent lookups
4. THE Code_Knowledge_Graph SHALL prevent duplicate concepts by using a hash of the normalized name and concept type as the unique identifier
5. WHEN a duplicate concept is detected from a different source document, THE Code_Knowledge_Graph SHALL update the source document reference to include both documents

### Requirement 2: Code Pattern Recognition

**User Story:** As a system, I want to recognize and parse code syntax patterns, so that code concepts can be extracted regardless of naming convention.

#### Acceptance Criteria

1. WHEN processing document text, THE Code_Extractor SHALL identify snake_case identifiers and split them into constituent words for lookup
2. WHEN processing document text, THE Code_Extractor SHALL identify camelCase identifiers and split them into constituent words for lookup
3. WHEN processing document text, THE Code_Extractor SHALL identify method calls with parentheses and extract the method name separately from the call syntax
4. WHEN processing document text, THE Code_Extractor SHALL identify dot notation for attribute access and extract the full qualified name
5. WHEN processing import statements, THE Code_Extractor SHALL extract module names and imported symbols
6. THE Code_Extractor SHALL handle edge cases including acronyms, numbers in identifiers, and leading underscores for private members

### Requirement 3: Code Relationship Definition

**User Story:** As a system, I want to define meaningful relationships between code concepts, so that the knowledge graph captures software architecture and API usage patterns.

#### Acceptance Criteria

1. THE Code_Knowledge_Graph SHALL support the following relationship types: CALLS, DEFINES, IMPORTS, INHERITS_FROM, IMPLEMENTS, RETURNS_TYPE, PARAMETER_TYPE, and DOCUMENTED_BY
2. WHEN a function calls another function, THE Code_Knowledge_Graph SHALL create a CALLS relationship from the caller to the callee
3. WHEN a class defines a method, THE Code_Knowledge_Graph SHALL create a DEFINES relationship from the class to the method
4. WHEN a module imports from another module, THE Code_Knowledge_Graph SHALL create an IMPORTS relationship between the modules
5. WHEN a class inherits from a parent class, THE Code_Knowledge_Graph SHALL create an INHERITS_FROM relationship
6. WHEN a function returns a specific type, THE Code_Knowledge_Graph SHALL create a RETURNS_TYPE relationship
7. WHEN a function accepts a parameter of a specific type, THE Code_Knowledge_Graph SHALL create a PARAMETER_TYPE relationship
8. THE Code_Knowledge_Graph SHALL store relationship metadata including source document reference, confidence score, and extraction context

### Requirement 4: ConceptNet Integration

**User Story:** As a system, I want to integrate the Code_Knowledge_Graph with ConceptNet, so that code concepts can receive both code-specific and general knowledge enrichment.

#### Acceptance Criteria

1. WHEN enriching a Code_Concept, THE Enrichment_Service SHALL first query the Code_Knowledge_Graph for code-specific relationships
2. WHEN a Code_Concept has no relationships in the Code_Knowledge_Graph, THE Enrichment_Service SHALL fall back to ConceptNet lookup using normalized term names
3. WHEN a Code_Concept exists in both knowledge graphs, THE Enrichment_Service SHALL merge relationships from both sources
4. THE Enrichment_Service SHALL prioritize Code_Knowledge_Graph relationships over ConceptNet relationships for code-related queries
5. WHEN ConceptNet provides general knowledge relationships for a code term, THE Enrichment_Service SHALL namespace these relationships to distinguish them from code-specific relationships

### Requirement 5: Code Intelligence Source Integration

**User Story:** As a system, I want to integrate with external code intelligence sources, so that the Code_Knowledge_Graph can be populated with comprehensive code knowledge.

#### Acceptance Criteria

1. THE Code_Knowledge_Graph SHALL provide an integration interface for Code_Intelligence_Sources
2. WHEN a Code_Intelligence_Source is configured, THE Code_Knowledge_Graph SHALL periodically sync concepts and relationships from that source
3. THE Code_Knowledge_Graph SHALL support the following initial sources: PyPI package metadata, GitHub API for repository structure, and type stub repositories
4. WHEN syncing from a Code_Intelligence_Source, THE Code_Knowledge_Graph SHALL preserve the source attribution for all imported concepts and relationships
5. THE Code_Knowledge_Graph SHALL provide a refresh mechanism to update concepts from Code_Intelligence_Sources on demand

### Requirement 6: Query Interface

**User Story:** As a developer, I want to query the Code_Knowledge_Graph for code concepts and relationships, so that I can retrieve relevant code knowledge for RAG enrichment.

#### Acceptance Criteria

1. THE Code_Knowledge_Graph SHALL provide a query interface that accepts a concept name and returns all related concepts
2. WHEN querying with a partial concept name, THE Code_Knowledge_Graph SHALL return concepts that match the partial name using fuzzy matching
3. THE Code_Knowledge_Graph SHALL support relationship-based queries that return concepts connected by a specific relationship type
4. WHEN querying for a code pattern, THE Code_Knowledge_Graph SHALL normalize the pattern before lookup
5. THE Query_Interface SHALL return results within 100ms for queries against the cached concept set

### Requirement 7: Neo4j Namespace Isolation

**User Story:** As a system administrator, I want to isolate the Code_Knowledge_Graph in a separate Neo4j namespace, so that code concepts do not conflict with existing knowledge graph data.

#### Acceptance Criteria

1. THE Code_Knowledge_Graph SHALL use a dedicated Neo4j label prefix: CodeConcept and CodeRelationship
2. THE Code_Knowledge_Graph SHALL use a dedicated relationship type prefix: CODE_
3. WHEN creating nodes and relationships, THE Code_Knowledge_Graph SHALL apply the appropriate prefix to prevent naming conflicts
4. THE Code_Knowledge_Graph SHALL allow queries to be scoped to only code concepts by filtering on the prefixed labels
5. WHEN integrating with ConceptNet, THE Code_Knowledge_Graph SHALL maintain clear separation between code and general knowledge graph data

### Requirement 8: Document Enrichment Pipeline Integration

**User Story:** As a system, I want to integrate the Code_Knowledge_Graph into the document enrichment pipeline, so that code concepts from processed documents are automatically enriched.

#### Acceptance Criteria

1. WHEN a document is processed, THE Enrichment_Pipeline SHALL extract Code_Concepts using the Code_Extractor
2. WHEN Code_Concepts are extracted, THE Enrichment_Pipeline SHALL store them in the Code_Knowledge_Graph
3. WHEN Code_Concepts are stored, THE Enrichment_Pipeline SHALL query for related concepts to build the enrichment context
4. THE Enrichment_Pipeline SHALL include Code_Knowledge_Graph relationships in the RAG context for queries about code topics
5. WHEN a document contains no code concepts, THE Enrichment_Pipeline SHALL skip Code_Knowledge_Graph operations without error

### Requirement 9: Performance Requirements

**User Story:** As a system operator, I want the Code_Knowledge_Graph to meet performance targets, so that document processing latency remains acceptable.

#### Acceptance Criteria

1. THE Code_Knowledge_Graph SHALL store a new concept within 50ms of receiving the store request
2. THE Code_Knowledge_Graph SHALL return query results within 100ms for single-concept lookups
3. THE Code_Knowledge_Graph SHALL handle batch operations of up to 1000 concepts without exceeding 500ms total processing time
4. THE Code_Knowledge_Graph SHALL support at least 100 concurrent queries without degradation in response time
5. WHEN the Code_Knowledge_Graph is unavailable, THE Enrichment_Pipeline SHALL continue processing using ConceptNet only

### Requirement 10: Scalability Requirements

**User Story:** As a system architect, I want the Code_Knowledge_Graph to scale with document volume, so that performance remains acceptable as the knowledge base grows.

#### Acceptance Criteria

1. THE Code_Knowledge_Graph SHALL support storing at least 1,000,000 unique Code_Concepts without performance degradation
2. THE Code_Knowledge_Graph SHALL support at least 10,000,000 relationships between concepts
3. THE Code_Knowledge_Graph SHALL use Neo4j indexing to maintain query performance as the dataset grows
4. THE Code_Knowledge_Graph SHALL provide a mechanism to archive old concepts that are no longer frequently queried
5. THE Code_Knowledge_Graph SHALL support horizontal scaling through Neo4j clustering for high availability

### Requirement 11: Data Consistency and Integrity

**User Story:** As a data manager, I want the Code_Knowledge_Graph to maintain data integrity, so that enrichment results are reliable and consistent.

#### Acceptance Criteria

1. THE Code_Knowledge_Graph SHALL enforce referential integrity for all relationships (no orphaned relationship nodes)
2. THE Code_Knowledge_Graph SHALL use transactions for all write operations to ensure atomicity
3. WHEN a concept is deleted, THE Code_Knowledge_Graph SHALL cascade delete all associated relationships
4. THE Code_Knowledge_Graph SHALL maintain a version number for each concept to track updates
5. THE Code_Knowledge_Graph SHALL log all write operations for audit purposes

### Requirement 12: Initial Seed Data

**User Story:** As a system operator, I want the Code_Knowledge_Graph to be pre-populated with common code concepts, so that new installations have immediate coverage.

#### Acceptance Criteria

1. THE Code_Knowledge_Graph SHALL include a seed dataset of common Python standard library concepts
2. THE Code_Knowledge_Graph SHALL include a seed dataset of common LLM and AI library concepts (OpenAI, Anthropic, LangChain, Hugging Face)
3. THE seed dataset SHALL include relationships between seed concepts to demonstrate the knowledge graph structure
4. THE seed dataset SHALL be versioned and updatable through the Code_Intelligence_Source integration
5. THE seed dataset SHALL be loaded during initial system setup without requiring manual intervention

### Requirement 13: Monitoring and Observability

**User Story:** as a system operator, I want to monitor the Code_Knowledge_Graph health and performance, so that I can detect and diagnose issues.

#### Acceptance Criteria

1. THE Code_Knowledge_Graph SHALL expose health check endpoints for connectivity and operational status
2. THE Code_Knowledge_Graph SHALL track and expose metrics for concept count, relationship count, query latency, and cache hit rate
3. THE Code_Knowledge_Graph SHALL log significant events including concept additions, sync operations, and errors
4. THE Code_Knowledge_Graph SHALL integrate with the existing monitoring system for alerting on degraded performance or unavailability
5. THE Code_Knowledge_Graph SHALL provide a diagnostic endpoint that returns statistics about the current state of the knowledge graph

### Requirement 14: Error Handling and Recovery

**User Story:** As a system, I want to handle errors gracefully and recover from failures, so that document processing continues despite Code_Knowledge_Graph issues.

#### Acceptance Criteria

1. WHEN the Code_Knowledge_Graph is unavailable, THE Enrichment_Pipeline SHALL log a warning and continue processing without code enrichment
2. WHEN a query times out, THE Code_Knowledge_Graph SHALL return an empty result set rather than blocking
3. WHEN a write operation fails, THE Code_Knowledge_Graph SHALL retry the operation up to 3 times before reporting failure
4. THE Code_Knowledge_Graph SHALL implement circuit breaker pattern to prevent cascade failures during extended outages
5. THE Code_Knowledge_Graph SHALL provide a recovery mechanism to rebuild the graph from source documents if data corruption is detected

### Requirement 15: API Design

**User Story:** As a developer, I want a clean API for interacting with the Code_Knowledge_Graph, so that integration is straightforward and maintainable.

#### Acceptance Criteria

1. THE Code_Knowledge_Graph SHALL provide an async Python API for all operations
2. THE API SHALL follow the naming conventions established in the existing codebase
3. THE API SHALL accept and return Pydantic models for type safety and validation
4. THE API SHALL include docstrings following the existing documentation style
5. THE API SHALL be documented with docstrings that include usage examples

## Constraints and Assumptions

### Constraints

1. The Code_Knowledge_Graph SHALL use the existing Neo4j infrastructure rather than deploying a separate database
2. The Code_Knowledge_Graph SHALL NOT modify existing ConceptNet data or relationships
3. The Code_Knowledge_Graph SHALL be implemented in Python following the existing code style and patterns
4. The Code_Knowledge_Graph SHALL integrate with the existing dependency injection system
5. The Code_Knowledge_Graph SHALL NOT require changes to the PostgreSQL schema

### Assumptions

1. Neo4j has sufficient capacity to store the additional code knowledge graph data
2. The existing Neo4j connection pool can handle the additional query load
3. Code_Intelligence_Sources provide APIs that can be accessed programmatically
4. The seed dataset can be curated from publicly available sources
5. Users will not require write access to the Code_Knowledge_Graph from the API (read-only for queries, writes only from enrichment pipeline)

## Out of Scope

The following items are explicitly out of scope for this feature:

- Full code parsing and abstract syntax tree (AST) analysis
- Runtime code execution or dynamic analysis
- Integration with IDE plugins or development tools
- Automatic code generation or refactoring suggestions
- License analysis or compliance checking
- Security vulnerability detection in code
- Support for code in image or non-text formats within documents

## Dependencies

- Neo4j database (existing infrastructure)
- Existing Enrichment_Pipeline components
- Existing dependency injection system
- Existing monitoring and logging infrastructure

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Neo4j performance degradation under increased load | High | Implement caching layer, use Neo4j clustering |
| Code_Intelligence_Source API changes | Medium | Abstract source integration behind interface, implement versioning |
| Seed data quality issues | Medium | Implement validation on seed data, allow manual corrections |
| Concept name normalization edge cases | Low | Extensive testing, user feedback loop for corrections |