# Requirements Document

## Introduction

This feature implements persistent storage of Wikidata and ConceptNet enrichment data in the knowledge graph. Currently, the `ContentAnalyzer` fetches external knowledge base data (Wikidata Q-numbers, instance-of relationships, ConceptNet relationships) but only uses it transiently for chunking decisions. This feature will persist this enrichment data to Neo4j to improve knowledge synthesis coverage, accuracy, and precision.

The enrichment enables entity disambiguation via Wikidata Q-numbers, multi-hop reasoning via ontological paths, and cross-document connections via shared external entities.

## Glossary

- **Enrichment_Service**: The service responsible for fetching and persisting external knowledge base data for concepts
- **Wikidata_Client**: The client that queries the Wikidata SPARQL endpoint for entity information
- **ConceptNet_Client**: The client that queries the ConceptNet API for relationship information
- **Q_Number**: A unique identifier for entities in Wikidata (e.g., Q42 for Douglas Adams)
- **Instance_Of**: A Wikidata property (P31) indicating what type/class an entity belongs to
- **Concept_Node**: A node in the knowledge graph representing an extracted concept
- **External_Entity_Node**: A node representing a Wikidata or ConceptNet entity
- **Knowledge_Graph_Builder**: The component that extracts concepts and relationships from document content
- **Knowledge_Graph_Service**: The service layer for persisting nodes and relationships to Neo4j

## Requirements

### Requirement 1: Wikidata Entity Enrichment

**User Story:** As a knowledge system, I want to enrich extracted concepts with Wikidata Q-numbers, so that I can disambiguate entities and link to canonical external knowledge.

#### Acceptance Criteria

1. WHEN a concept is extracted from document content, THE Enrichment_Service SHALL query Wikidata for matching entities
2. WHEN a Wikidata entity match is found with confidence above 0.7, THE Enrichment_Service SHALL store the Q-number on the Concept_Node
3. WHEN multiple Wikidata entity matches are found, THE Enrichment_Service SHALL select the best match based on context similarity
4. IF the Wikidata API is unavailable, THEN THE Enrichment_Service SHALL continue processing without enrichment and log the failure
5. WHEN querying Wikidata, THE Wikidata_Client SHALL use a timeout of 5 seconds per request
6. WHEN a Q-number is already cached for a concept name, THE Enrichment_Service SHALL use the cached value instead of querying the API

### Requirement 2: Wikidata Instance-Of Relationships

**User Story:** As a knowledge system, I want to store Wikidata instance-of relationships, so that I can understand the ontological classification of concepts.

#### Acceptance Criteria

1. WHEN a concept has a Wikidata Q-number, THE Enrichment_Service SHALL fetch the instance-of (P31) property values
2. WHEN instance-of values are retrieved, THE Enrichment_Service SHALL create External_Entity_Node entries for each Wikidata class
3. WHEN instance-of values are retrieved, THE Enrichment_Service SHALL create INSTANCE_OF relationships from the Concept_Node to the External_Entity_Node
4. THE External_Entity_Node SHALL store the Q-number, label, and description from Wikidata
5. WHEN the same Wikidata class is referenced by multiple concepts, THE Enrichment_Service SHALL reuse the existing External_Entity_Node

### Requirement 3: ConceptNet Relationship Storage

**User Story:** As a knowledge system, I want to persist ConceptNet relationships between concepts, so that I can leverage commonsense knowledge for reasoning.

#### Acceptance Criteria

1. WHEN a concept is extracted, THE Enrichment_Service SHALL query ConceptNet for relationships involving that concept
2. WHEN ConceptNet relationships are found, THE Enrichment_Service SHALL create edges in Neo4j with the relationship type as the edge label
3. THE Enrichment_Service SHALL store ConceptNet relationship types including: IsA, PartOf, UsedFor, CapableOf, HasProperty, AtLocation, Causes, HasPrerequisite, MotivatedByGoal, RelatedTo
4. WHEN storing ConceptNet relationships, THE Enrichment_Service SHALL include the weight/confidence score from ConceptNet
5. IF the ConceptNet API is unavailable, THEN THE Enrichment_Service SHALL continue processing without enrichment and log the failure
6. WHEN querying ConceptNet, THE ConceptNet_Client SHALL use a timeout of 5 seconds per request
7. WHEN ConceptNet relationships are already cached for a concept, THE Enrichment_Service SHALL use the cached values

### Requirement 4: Enrichment Integration with Document Processing

**User Story:** As a document processor, I want enrichment to happen automatically during document processing, so that all documents benefit from external knowledge.

#### Acceptance Criteria

1. WHEN the Knowledge_Graph_Builder processes a document chunk, THE Enrichment_Service SHALL be called for each extracted concept
2. WHEN enrichment is performed, THE Enrichment_Service SHALL use async operations to avoid blocking document processing
3. IF enrichment fails for any concept, THEN THE Knowledge_Graph_Builder SHALL continue processing other concepts
4. WHEN document processing completes, THE system SHALL log enrichment statistics including concepts enriched, API calls made, and cache hits
5. THE Enrichment_Service SHALL batch API requests where possible to minimize external API calls

### Requirement 5: Cross-Document Entity Linking

**User Story:** As a knowledge system, I want to link concepts across documents via shared Wikidata entities, so that I can discover connections between documents.

#### Acceptance Criteria

1. WHEN two concepts from different documents share the same Q-number, THE Knowledge_Graph_Service SHALL create a SAME_AS relationship between them
2. WHEN querying for related concepts, THE Knowledge_Graph_Service SHALL traverse SAME_AS relationships to find cross-document connections
3. THE Knowledge_Graph_Service SHALL provide a method to find all documents containing concepts linked to a given Wikidata entity

### Requirement 6: Enrichment Cache Management

**User Story:** As a system administrator, I want enrichment data to be cached efficiently, so that API rate limits are respected and performance is optimized.

#### Acceptance Criteria

1. THE Enrichment_Service SHALL cache Wikidata query results in memory with a configurable TTL (default 24 hours)
2. THE Enrichment_Service SHALL cache ConceptNet query results in memory with a configurable TTL (default 24 hours)
3. WHEN the cache size exceeds a configurable limit (default 10000 entries), THE Enrichment_Service SHALL evict least-recently-used entries
4. THE Enrichment_Service SHALL provide methods to clear the cache and view cache statistics
5. WHEN the application restarts, THE Enrichment_Service SHALL rebuild the cache lazily as concepts are processed

### Requirement 7: Error Handling and Resilience

**User Story:** As a system operator, I want enrichment failures to be handled gracefully, so that document processing is not disrupted by external API issues.

#### Acceptance Criteria

1. IF a Wikidata API request fails, THEN THE Enrichment_Service SHALL retry up to 3 times with exponential backoff
2. IF a ConceptNet API request fails, THEN THE Enrichment_Service SHALL retry up to 3 times with exponential backoff
3. WHEN an API is consistently failing (more than 5 failures in 1 minute), THE Enrichment_Service SHALL enter a circuit-breaker state and skip enrichment for 5 minutes
4. THE Enrichment_Service SHALL emit metrics for API success rate, latency, and circuit-breaker state
5. IF enrichment is skipped due to circuit-breaker, THEN THE Enrichment_Service SHALL mark the concept for later enrichment

### Requirement 8: Neo4j Schema for External Entities

**User Story:** As a database administrator, I want a clear schema for external entity storage, so that queries are efficient and data is well-organized.

#### Acceptance Criteria

1. THE Knowledge_Graph_Service SHALL create an index on External_Entity_Node.q_number for fast lookups
2. THE Knowledge_Graph_Service SHALL create an index on Concept_Node.wikidata_qid for fast entity resolution
3. THE External_Entity_Node SHALL have properties: q_number, label, description, source (wikidata/conceptnet), fetched_at
4. THE INSTANCE_OF relationship SHALL have properties: confidence, fetched_at
5. THE ConceptNet relationship edges SHALL have properties: weight, source_uri, fetched_at
