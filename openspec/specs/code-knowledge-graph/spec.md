## Purpose

The Multimodal Librarian currently uses ConceptNet for knowledge graph enrichment to provide contextual relationships between concepts extracted from documents. However, ConceptNet has significant limitations when processing technical and code-related content:

- **Exact match dependency**: ConceptNet lookups require exact term matching, but code concepts often use inconsistent naming conventions (snake_case, camelCase, PascalCase)
- **Coverage gap**: Technical terms like "langchain_anthropic", "invoke()", "from_messages", and "AsyncIterator" do not exist in ConceptNet
- **Relationship absence**: Analysis shows 3,604 CODE_TERM concepts (15% of document concepts) have zero relationships because they cannot be found in ConceptNet
- **Domain mismatch**: ConceptNet is designed for general world knowledge, not software engineering concepts, APIs, or code patterns

The Code_Knowledge_Graph feature addresses these limitations by providing a dedicated knowledge graph for code-specific concepts. This feature enables semantic enrichment of technical documents, improved RAG responses for code-related queries, and better understanding of software architecture and API relationships.


### Key Terms
- **Code_Knowledge_Graph**: A specialized knowledge graph that stores relationships between code-specific concepts including classes, functions, modules, APIs, and programming constructs
- **Code_Concept**: A discrete code-related term extracted from documents, including function names, class names, module names, method signatures, library names, and API endpoints
- **Code_Pattern**: A recognized syntax pattern in source code, including snake_case, camelCase, PascalCase, method calls with parentheses, dot notation for attribute access, and import statements
- **ConceptNet**: The existing general-purpose knowledge graph used for non-code concept enrichment
- **Code_Extractor**: The component responsible for identifying and extracting code concepts from document content
- **Code_Relationship**: A directed or undirected edge between two Code_Concepts representing a meaningful connection such as inheritance, composition, usage, or documentation
- **Namespace**: A logical partition within Neo4j that isolates the Code_Knowledge_Graph from other data including ConceptNet relationships
- **Code_Intelligence_Source**: An external data provider that supplies code knowledge such as type hierarchies, API documentation, or code search results

## Requirements

### Requirement: Code Concept Storage

The system SHALL support: As a system, I want to store code-specific concepts in a dedicated knowledge graph, so that technical terms from documents can be enriched with relationships.

#### Scenario: THE Code_Knowledge_Graph SHALL store Code_Concepts with the

- **THEN** THE Code_Knowledge_Graph SHALL store Code_Concepts with the following attributes: concept identifier, display name, concept type, source document reference, and extraction timestamp

#### Scenario: THE Code_Knowledge_Graph SHALL support concept types: FUNCTI

- **THEN** THE Code_Knowledge_Graph SHALL support concept types: FUNCTION, CLASS, MODULE, METHOD, LIBRARY, API_ENDPOINT, TYPE, and CONSTANT

#### Scenario: WHEN a Code_Concept is stored, THE Code_Knowledge_Graph SHAL

- **THEN** WHEN a Code_Concept is stored, THE Code_Knowledge_Graph SHALL normalize the display name to a canonical form for consistent lookups

#### Scenario: THE Code_Knowledge_Graph SHALL prevent duplicate concepts by

- **THEN** THE Code_Knowledge_Graph SHALL prevent duplicate concepts by using a hash of the normalized name and concept type as the unique identifier

#### Scenario: WHEN a duplicate concept is detected from a different source

- **THEN** WHEN a duplicate concept is detected from a different source document, THE Code_Knowledge_Graph SHALL update the source document reference to include both documents

### Requirement: Code Pattern Recognition

The system SHALL support: As a system, I want to recognize and parse code syntax patterns, so that code concepts can be extracted regardless of naming convention.

#### Scenario: WHEN processing document text, THE Code_Extractor SHALL iden

- **THEN** WHEN processing document text, THE Code_Extractor SHALL identify snake_case identifiers and split them into constituent words for lookup

#### Scenario: WHEN processing document text, THE Code_Extractor SHALL iden

- **THEN** WHEN processing document text, THE Code_Extractor SHALL identify camelCase identifiers and split them into constituent words for lookup

#### Scenario: WHEN processing document text, THE Code_Extractor SHALL iden

- **THEN** WHEN processing document text, THE Code_Extractor SHALL identify method calls with parentheses and extract the method name separately from the call syntax

#### Scenario: WHEN processing document text, THE Code_Extractor SHALL iden

- **THEN** WHEN processing document text, THE Code_Extractor SHALL identify dot notation for attribute access and extract the full qualified name

#### Scenario: WHEN processing import statements, THE Code_Extractor SHALL

- **THEN** WHEN processing import statements, THE Code_Extractor SHALL extract module names and imported symbols

#### Scenario: THE Code_Extractor SHALL handle edge cases including acronym

- **THEN** THE Code_Extractor SHALL handle edge cases including acronyms, numbers in identifiers, and leading underscores for private members

### Requirement: Code Relationship Definition

The system SHALL support: As a system, I want to define meaningful relationships between code concepts, so that the knowledge graph captures software architecture and API usage patterns.

#### Scenario: THE Code_Knowledge_Graph SHALL support the following relatio

- **THEN** THE Code_Knowledge_Graph SHALL support the following relationship types: CALLS, DEFINES, IMPORTS, INHERITS_FROM, IMPLEMENTS, RETURNS_TYPE, PARAMETER_TYPE, and DOCUMENTED_BY

#### Scenario: WHEN a function calls another function, THE Code_Knowledge_G

- **THEN** WHEN a function calls another function, THE Code_Knowledge_Graph SHALL create a CALLS relationship from the caller to the callee

#### Scenario: WHEN a class defines a method, THE Code_Knowledge_Graph SHAL

- **THEN** WHEN a class defines a method, THE Code_Knowledge_Graph SHALL create a DEFINES relationship from the class to the method

#### Scenario: WHEN a module imports from another module, THE Code_Knowledg

- **THEN** WHEN a module imports from another module, THE Code_Knowledge_Graph SHALL create an IMPORTS relationship between the modules

#### Scenario: WHEN a class inherits from a parent class, THE Code_Knowledg

- **THEN** WHEN a class inherits from a parent class, THE Code_Knowledge_Graph SHALL create an INHERITS_FROM relationship

#### Scenario: WHEN a function returns a specific type, THE Code_Knowledge_

- **THEN** WHEN a function returns a specific type, THE Code_Knowledge_Graph SHALL create a RETURNS_TYPE relationship

#### Scenario: WHEN a function accepts a parameter of a specific type, THE

- **THEN** WHEN a function accepts a parameter of a specific type, THE Code_Knowledge_Graph SHALL create a PARAMETER_TYPE relationship

#### Scenario: THE Code_Knowledge_Graph SHALL store relationship metadata i

- **THEN** THE Code_Knowledge_Graph SHALL store relationship metadata including source document reference, confidence score, and extraction context

### Requirement: ConceptNet Integration

The system SHALL support: As a system, I want to integrate the Code_Knowledge_Graph with ConceptNet, so that code concepts can receive both code-specific and general knowledge enrichment.

#### Scenario: WHEN enriching a Code_Concept, THE Enrichment_Service SHALL

- **THEN** WHEN enriching a Code_Concept, THE Enrichment_Service SHALL first query the Code_Knowledge_Graph for code-specific relationships

#### Scenario: WHEN a Code_Concept has no relationships in the Code_Knowled

- **THEN** WHEN a Code_Concept has no relationships in the Code_Knowledge_Graph, THE Enrichment_Service SHALL fall back to ConceptNet lookup using normalized term names

#### Scenario: WHEN a Code_Concept exists in both knowledge graphs, THE Enr

- **THEN** WHEN a Code_Concept exists in both knowledge graphs, THE Enrichment_Service SHALL merge relationships from both sources

#### Scenario: THE Enrichment_Service SHALL prioritize Code_Knowledge_Graph

- **THEN** THE Enrichment_Service SHALL prioritize Code_Knowledge_Graph relationships over ConceptNet relationships for code-related queries

#### Scenario: WHEN ConceptNet provides general knowledge relationships for

- **THEN** WHEN ConceptNet provides general knowledge relationships for a code term, THE Enrichment_Service SHALL namespace these relationships to distinguish them from code-specific relationships

### Requirement: Code Intelligence Source Integration

The system SHALL support: As a system, I want to integrate with external code intelligence sources, so that the Code_Knowledge_Graph can be populated with comprehensive code knowledge.

#### Scenario: THE Code_Knowledge_Graph SHALL provide an integration interf

- **THEN** THE Code_Knowledge_Graph SHALL provide an integration interface for Code_Intelligence_Sources

#### Scenario: WHEN a Code_Intelligence_Source is configured, THE Code_Know

- **THEN** WHEN a Code_Intelligence_Source is configured, THE Code_Knowledge_Graph SHALL periodically sync concepts and relationships from that source

#### Scenario: THE Code_Knowledge_Graph SHALL support the following initial

- **THEN** THE Code_Knowledge_Graph SHALL support the following initial sources: PyPI package metadata, GitHub API for repository structure, and type stub repositories

#### Scenario: WHEN syncing from a Code_Intelligence_Source, THE Code_Knowl

- **THEN** WHEN syncing from a Code_Intelligence_Source, THE Code_Knowledge_Graph SHALL preserve the source attribution for all imported concepts and relationships

#### Scenario: THE Code_Knowledge_Graph SHALL provide a refresh mechanism t

- **THEN** THE Code_Knowledge_Graph SHALL provide a refresh mechanism to update concepts from Code_Intelligence_Sources on demand

### Requirement: Query Interface

The system SHALL support: As a developer, I want to query the Code_Knowledge_Graph for code concepts and relationships, so that I can retrieve relevant code knowledge for RAG enrichment.

#### Scenario: THE Code_Knowledge_Graph SHALL provide a query interface tha

- **THEN** THE Code_Knowledge_Graph SHALL provide a query interface that accepts a concept name and returns all related concepts

#### Scenario: WHEN querying with a partial concept name, THE Code_Knowledg

- **THEN** WHEN querying with a partial concept name, THE Code_Knowledge_Graph SHALL return concepts that match the partial name using fuzzy matching

#### Scenario: THE Code_Knowledge_Graph SHALL support relationship-based qu

- **THEN** THE Code_Knowledge_Graph SHALL support relationship-based queries that return concepts connected by a specific relationship type

#### Scenario: WHEN querying for a code pattern, THE Code_Knowledge_Graph S

- **THEN** WHEN querying for a code pattern, THE Code_Knowledge_Graph SHALL normalize the pattern before lookup

#### Scenario: THE Query_Interface SHALL return results within 100ms for qu

- **THEN** THE Query_Interface SHALL return results within 100ms for queries against the cached concept set

### Requirement: Neo4j Namespace Isolation

The system SHALL support: As a system administrator, I want to isolate the Code_Knowledge_Graph in a separate Neo4j namespace, so that code concepts do not conflict with existing knowledge graph data.

#### Scenario: THE Code_Knowledge_Graph SHALL use a dedicated Neo4j label p

- **THEN** THE Code_Knowledge_Graph SHALL use a dedicated Neo4j label prefix: CodeConcept and CodeRelationship

#### Scenario: THE Code_Knowledge_Graph SHALL use a dedicated relationship

- **THEN** THE Code_Knowledge_Graph SHALL use a dedicated relationship type prefix: CODE_

#### Scenario: WHEN creating nodes and relationships, THE Code_Knowledge_Gr

- **THEN** WHEN creating nodes and relationships, THE Code_Knowledge_Graph SHALL apply the appropriate prefix to prevent naming conflicts

#### Scenario: THE Code_Knowledge_Graph SHALL allow queries to be scoped to

- **THEN** THE Code_Knowledge_Graph SHALL allow queries to be scoped to only code concepts by filtering on the prefixed labels

#### Scenario: WHEN integrating with ConceptNet, THE Code_Knowledge_Graph S

- **THEN** WHEN integrating with ConceptNet, THE Code_Knowledge_Graph SHALL maintain clear separation between code and general knowledge graph data

### Requirement: Document Enrichment Pipeline Integration

The system SHALL support: As a system, I want to integrate the Code_Knowledge_Graph into the document enrichment pipeline, so that code concepts from processed documents are automatically enriched.

#### Scenario: WHEN a document is processed, THE Enrichment_Pipeline SHALL

- **THEN** WHEN a document is processed, THE Enrichment_Pipeline SHALL extract Code_Concepts using the Code_Extractor

#### Scenario: WHEN Code_Concepts are extracted, THE Enrichment_Pipeline SH

- **THEN** WHEN Code_Concepts are extracted, THE Enrichment_Pipeline SHALL store them in the Code_Knowledge_Graph

#### Scenario: WHEN Code_Concepts are stored, THE Enrichment_Pipeline SHALL

- **THEN** WHEN Code_Concepts are stored, THE Enrichment_Pipeline SHALL query for related concepts to build the enrichment context

#### Scenario: THE Enrichment_Pipeline SHALL include Code_Knowledge_Graph r

- **THEN** THE Enrichment_Pipeline SHALL include Code_Knowledge_Graph relationships in the RAG context for queries about code topics

#### Scenario: WHEN a document contains no code concepts, THE Enrichment_Pi

- **THEN** WHEN a document contains no code concepts, THE Enrichment_Pipeline SHALL skip Code_Knowledge_Graph operations without error

### Requirement: Performance Requirements

The system SHALL support: As a system operator, I want the Code_Knowledge_Graph to meet performance targets, so that document processing latency remains acceptable.

#### Scenario: THE Code_Knowledge_Graph SHALL store a new concept within 50

- **THEN** THE Code_Knowledge_Graph SHALL store a new concept within 50ms of receiving the store request

#### Scenario: THE Code_Knowledge_Graph SHALL return query results within 1

- **THEN** THE Code_Knowledge_Graph SHALL return query results within 100ms for single-concept lookups

#### Scenario: THE Code_Knowledge_Graph SHALL handle batch operations of up

- **THEN** THE Code_Knowledge_Graph SHALL handle batch operations of up to 1000 concepts without exceeding 500ms total processing time

#### Scenario: THE Code_Knowledge_Graph SHALL support at least 100 concurre

- **THEN** THE Code_Knowledge_Graph SHALL support at least 100 concurrent queries without degradation in response time

#### Scenario: WHEN the Code_Knowledge_Graph is unavailable, THE Enrichment

- **THEN** WHEN the Code_Knowledge_Graph is unavailable, THE Enrichment_Pipeline SHALL continue processing using ConceptNet only

### Requirement: Scalability Requirements

The system SHALL support: As a system architect, I want the Code_Knowledge_Graph to scale with document volume, so that performance remains acceptable as the knowledge base grows.

#### Scenario: THE Code_Knowledge_Graph SHALL support storing at least 1,00

- **THEN** THE Code_Knowledge_Graph SHALL support storing at least 1,000,000 unique Code_Concepts without performance degradation

#### Scenario: THE Code_Knowledge_Graph SHALL support at least 10,000,000 r

- **THEN** THE Code_Knowledge_Graph SHALL support at least 10,000,000 relationships between concepts

#### Scenario: THE Code_Knowledge_Graph SHALL use Neo4j indexing to maintai

- **THEN** THE Code_Knowledge_Graph SHALL use Neo4j indexing to maintain query performance as the dataset grows

#### Scenario: THE Code_Knowledge_Graph SHALL provide a mechanism to archiv

- **THEN** THE Code_Knowledge_Graph SHALL provide a mechanism to archive old concepts that are no longer frequently queried

#### Scenario: THE Code_Knowledge_Graph SHALL support horizontal scaling th

- **THEN** THE Code_Knowledge_Graph SHALL support horizontal scaling through Neo4j clustering for high availability

### Requirement: Data Consistency and Integrity

The system SHALL support: As a data manager, I want the Code_Knowledge_Graph to maintain data integrity, so that enrichment results are reliable and consistent.

#### Scenario: THE Code_Knowledge_Graph SHALL enforce referential integrity

- **THEN** THE Code_Knowledge_Graph SHALL enforce referential integrity for all relationships (no orphaned relationship nodes)

#### Scenario: THE Code_Knowledge_Graph SHALL use transactions for all writ

- **THEN** THE Code_Knowledge_Graph SHALL use transactions for all write operations to ensure atomicity

#### Scenario: WHEN a concept is deleted, THE Code_Knowledge_Graph SHALL ca

- **THEN** WHEN a concept is deleted, THE Code_Knowledge_Graph SHALL cascade delete all associated relationships

#### Scenario: THE Code_Knowledge_Graph SHALL maintain a version number for

- **THEN** THE Code_Knowledge_Graph SHALL maintain a version number for each concept to track updates

#### Scenario: THE Code_Knowledge_Graph SHALL log all write operations for

- **THEN** THE Code_Knowledge_Graph SHALL log all write operations for audit purposes

### Requirement: Initial Seed Data

The system SHALL support: As a system operator, I want the Code_Knowledge_Graph to be pre-populated with common code concepts, so that new installations have immediate coverage.

#### Scenario: THE Code_Knowledge_Graph SHALL include a seed dataset of com

- **THEN** THE Code_Knowledge_Graph SHALL include a seed dataset of common Python standard library concepts

#### Scenario: THE Code_Knowledge_Graph SHALL include a seed dataset of com

- **THEN** THE Code_Knowledge_Graph SHALL include a seed dataset of common LLM and AI library concepts (OpenAI, Anthropic, LangChain, Hugging Face)

#### Scenario: THE seed dataset SHALL include relationships between seed co

- **THEN** THE seed dataset SHALL include relationships between seed concepts to demonstrate the knowledge graph structure

#### Scenario: THE seed dataset SHALL be versioned and updatable through th

- **THEN** THE seed dataset SHALL be versioned and updatable through the Code_Intelligence_Source integration

#### Scenario: THE seed dataset SHALL be loaded during initial system setup

- **THEN** THE seed dataset SHALL be loaded during initial system setup without requiring manual intervention

### Requirement: Monitoring and Observability

The system SHALL support: as a system operator, I want to monitor the Code_Knowledge_Graph health and performance, so that I can detect and diagnose issues.

#### Scenario: THE Code_Knowledge_Graph SHALL expose health check endpoints

- **THEN** THE Code_Knowledge_Graph SHALL expose health check endpoints for connectivity and operational status

#### Scenario: THE Code_Knowledge_Graph SHALL track and expose metrics for

- **THEN** THE Code_Knowledge_Graph SHALL track and expose metrics for concept count, relationship count, query latency, and cache hit rate

#### Scenario: THE Code_Knowledge_Graph SHALL log significant events includ

- **THEN** THE Code_Knowledge_Graph SHALL log significant events including concept additions, sync operations, and errors

#### Scenario: THE Code_Knowledge_Graph SHALL integrate with the existing m

- **THEN** THE Code_Knowledge_Graph SHALL integrate with the existing monitoring system for alerting on degraded performance or unavailability

#### Scenario: THE Code_Knowledge_Graph SHALL provide a diagnostic endpoint

- **THEN** THE Code_Knowledge_Graph SHALL provide a diagnostic endpoint that returns statistics about the current state of the knowledge graph

### Requirement: Error Handling and Recovery

The system SHALL support: As a system, I want to handle errors gracefully and recover from failures, so that document processing continues despite Code_Knowledge_Graph issues.

#### Scenario: WHEN the Code_Knowledge_Graph is unavailable, THE Enrichment

- **THEN** WHEN the Code_Knowledge_Graph is unavailable, THE Enrichment_Pipeline SHALL log a warning and continue processing without code enrichment

#### Scenario: WHEN a query times out, THE Code_Knowledge_Graph SHALL retur

- **THEN** WHEN a query times out, THE Code_Knowledge_Graph SHALL return an empty result set rather than blocking

#### Scenario: WHEN a write operation fails, THE Code_Knowledge_Graph SHALL

- **THEN** WHEN a write operation fails, THE Code_Knowledge_Graph SHALL retry the operation up to 3 times before reporting failure

#### Scenario: THE Code_Knowledge_Graph SHALL implement circuit breaker pat

- **THEN** THE Code_Knowledge_Graph SHALL implement circuit breaker pattern to prevent cascade failures during extended outages

#### Scenario: THE Code_Knowledge_Graph SHALL provide a recovery mechanism

- **THEN** THE Code_Knowledge_Graph SHALL provide a recovery mechanism to rebuild the graph from source documents if data corruption is detected

### Requirement: API Design

The system SHALL support: As a developer, I want a clean API for interacting with the Code_Knowledge_Graph, so that integration is straightforward and maintainable.

#### Scenario: THE Code_Knowledge_Graph SHALL provide an async Python API f

- **THEN** THE Code_Knowledge_Graph SHALL provide an async Python API for all operations

#### Scenario: THE API SHALL follow the naming conventions established in t

- **THEN** THE API SHALL follow the naming conventions established in the existing codebase

#### Scenario: THE API SHALL accept and return Pydantic models for type saf

- **THEN** THE API SHALL accept and return Pydantic models for type safety and validation

#### Scenario: THE API SHALL include docstrings following the existing docu

- **THEN** THE API SHALL include docstrings following the existing documentation style

#### Scenario: THE API SHALL be documented with docstrings that include usa

- **THEN** THE API SHALL be documented with docstrings that include usage examples ## Constraints and Assumptions
