## Purpose

This feature implements persistent storage of Wikidata and ConceptNet enrichment data in the knowledge graph. Currently, the `ContentAnalyzer` fetches external knowledge base data (Wikidata Q-numbers, instance-of relationships, ConceptNet relationships) but only uses it transiently for chunking decisions. This feature will persist this enrichment data to Neo4j to improve knowledge synthesis coverage, accuracy, and precision.

The enrichment enables entity disambiguation via Wikidata Q-numbers, multi-hop reasoning via ontological paths, and cross-document connections via shared external entities.


### Key Terms
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

### Requirement: Wikidata Entity Enrichment

The system SHALL support: As a knowledge system, I want to enrich extracted concepts with Wikidata Q-numbers, so that I can disambiguate entities and link to canonical external knowledge.

#### Scenario: WHEN a concept is extracted from document content, THE Enric

- **THEN** WHEN a concept is extracted from document content, THE Enrichment_Service SHALL query Wikidata for matching entities

#### Scenario: WHEN a Wikidata entity match is found with confidence above

- **THEN** WHEN a Wikidata entity match is found with confidence above 0.7, THE Enrichment_Service SHALL store the Q-number on the Concept_Node

#### Scenario: WHEN multiple Wikidata entity matches are found, THE Enrichm

- **THEN** WHEN multiple Wikidata entity matches are found, THE Enrichment_Service SHALL select the best match based on context similarity

#### Scenario: IF the Wikidata API is unavailable, THEN THE Enrichment_Serv

- **GIVEN** the Wikidata API is unavailable
- **THEN** IF the Wikidata API is unavailable, THEN THE Enrichment_Service SHALL continue processing without enrichment and log the failure

#### Scenario: WHEN querying Wikidata, THE Wikidata_Client SHALL use a time

- **THEN** WHEN querying Wikidata, THE Wikidata_Client SHALL use a timeout of 5 seconds per request

#### Scenario: WHEN a Q-number is already cached for a concept name, THE En

- **THEN** WHEN a Q-number is already cached for a concept name, THE Enrichment_Service SHALL use the cached value instead of querying the API

### Requirement: Wikidata Instance-Of Relationships

The system SHALL support: As a knowledge system, I want to store Wikidata instance-of relationships, so that I can understand the ontological classification of concepts.

#### Scenario: WHEN a concept has a Wikidata Q-number, THE Enrichment_Servi

- **THEN** WHEN a concept has a Wikidata Q-number, THE Enrichment_Service SHALL fetch the instance-of (P31) property values

#### Scenario: WHEN instance-of values are retrieved, THE Enrichment_Servic

- **THEN** WHEN instance-of values are retrieved, THE Enrichment_Service SHALL create External_Entity_Node entries for each Wikidata class

#### Scenario: WHEN instance-of values are retrieved, THE Enrichment_Servic

- **THEN** WHEN instance-of values are retrieved, THE Enrichment_Service SHALL create INSTANCE_OF relationships from the Concept_Node to the External_Entity_Node

#### Scenario: THE External_Entity_Node SHALL store the Q-number, label, an

- **THEN** THE External_Entity_Node SHALL store the Q-number, label, and description from Wikidata

#### Scenario: WHEN the same Wikidata class is referenced by multiple conce

- **THEN** WHEN the same Wikidata class is referenced by multiple concepts, THE Enrichment_Service SHALL reuse the existing External_Entity_Node

### Requirement: ConceptNet Relationship Storage

The system SHALL support: As a knowledge system, I want to persist ConceptNet relationships between concepts, so that I can leverage commonsense knowledge for reasoning.

#### Scenario: WHEN a concept is extracted, THE Enrichment_Service SHALL qu

- **THEN** WHEN a concept is extracted, THE Enrichment_Service SHALL query ConceptNet for relationships involving that concept

#### Scenario: WHEN ConceptNet relationships are found, THE Enrichment_Serv

- **THEN** WHEN ConceptNet relationships are found, THE Enrichment_Service SHALL create edges in Neo4j with the relationship type as the edge label

#### Scenario: THE Enrichment_Service SHALL store ConceptNet relationship t

- **THEN** THE Enrichment_Service SHALL store ConceptNet relationship types including: IsA, PartOf, UsedFor, CapableOf, HasProperty, AtLocation, Causes, HasPrerequisite, MotivatedByGoal, RelatedTo

#### Scenario: WHEN storing ConceptNet relationships, THE Enrichment_Servic

- **THEN** WHEN storing ConceptNet relationships, THE Enrichment_Service SHALL include the weight/confidence score from ConceptNet

#### Scenario: IF the ConceptNet API is unavailable, THEN THE Enrichment_Se

- **GIVEN** the ConceptNet API is unavailable
- **THEN** IF the ConceptNet API is unavailable, THEN THE Enrichment_Service SHALL continue processing without enrichment and log the failure

#### Scenario: WHEN querying ConceptNet, THE ConceptNet_Client SHALL use a

- **THEN** WHEN querying ConceptNet, THE ConceptNet_Client SHALL use a timeout of 5 seconds per request

#### Scenario: WHEN ConceptNet relationships are already cached for a conce

- **THEN** WHEN ConceptNet relationships are already cached for a concept, THE Enrichment_Service SHALL use the cached values

### Requirement: Enrichment Integration with Document Processing

The system SHALL support: As a document processor, I want enrichment to happen automatically during document processing, so that all documents benefit from external knowledge.

#### Scenario: WHEN the Knowledge_Graph_Builder processes a document chunk,

- **THEN** WHEN the Knowledge_Graph_Builder processes a document chunk, THE Enrichment_Service SHALL be called for each extracted concept

#### Scenario: WHEN enrichment is performed, THE Enrichment_Service SHALL u

- **THEN** WHEN enrichment is performed, THE Enrichment_Service SHALL use async operations to avoid blocking document processing

#### Scenario: IF enrichment fails for any concept, THEN THE Knowledge_Grap

- **GIVEN** enrichment fails for any concept
- **THEN** IF enrichment fails for any concept, THEN THE Knowledge_Graph_Builder SHALL continue processing other concepts

#### Scenario: WHEN document processing completes, THE system SHALL log enr

- **THEN** WHEN document processing completes, THE system SHALL log enrichment statistics including concepts enriched, API calls made, and cache hits

#### Scenario: THE Enrichment_Service SHALL batch API requests where possib

- **THEN** THE Enrichment_Service SHALL batch API requests where possible to minimize external API calls

### Requirement: Cross-Document Entity Linking

The system SHALL support: As a knowledge system, I want to link concepts across documents via shared Wikidata entities, so that I can discover connections between documents.

#### Scenario: WHEN two concepts from different documents share the same Q-

- **THEN** WHEN two concepts from different documents share the same Q-number, THE Knowledge_Graph_Service SHALL create a SAME_AS relationship between them

#### Scenario: WHEN querying for related concepts, THE Knowledge_Graph_Serv

- **THEN** WHEN querying for related concepts, THE Knowledge_Graph_Service SHALL traverse SAME_AS relationships to find cross-document connections

#### Scenario: THE Knowledge_Graph_Service SHALL provide a method to find a

- **THEN** THE Knowledge_Graph_Service SHALL provide a method to find all documents containing concepts linked to a given Wikidata entity

### Requirement: Enrichment Cache Management

The system SHALL support: As a system administrator, I want enrichment data to be cached efficiently, so that API rate limits are respected and performance is optimized.

#### Scenario: THE Enrichment_Service SHALL cache Wikidata query results in

- **THEN** THE Enrichment_Service SHALL cache Wikidata query results in memory with a configurable TTL (default 24 hours)

#### Scenario: THE Enrichment_Service SHALL cache ConceptNet query results

- **THEN** THE Enrichment_Service SHALL cache ConceptNet query results in memory with a configurable TTL (default 24 hours)

#### Scenario: WHEN the cache size exceeds a configurable limit (default 10

- **THEN** WHEN the cache size exceeds a configurable limit (default 10000 entries), THE Enrichment_Service SHALL evict least-recently-used entries

#### Scenario: THE Enrichment_Service SHALL provide methods to clear the ca

- **THEN** THE Enrichment_Service SHALL provide methods to clear the cache and view cache statistics

#### Scenario: WHEN the application restarts, THE Enrichment_Service SHALL

- **THEN** WHEN the application restarts, THE Enrichment_Service SHALL rebuild the cache lazily as concepts are processed

### Requirement: Error Handling and Resilience

The system SHALL support: As a system operator, I want enrichment failures to be handled gracefully, so that document processing is not disrupted by external API issues.

#### Scenario: IF a Wikidata API request fails, THEN THE Enrichment_Service

- **GIVEN** a Wikidata API request fails
- **THEN** IF a Wikidata API request fails, THEN THE Enrichment_Service SHALL retry up to 3 times with exponential backoff

#### Scenario: IF a ConceptNet API request fails, THEN THE Enrichment_Servi

- **GIVEN** a ConceptNet API request fails
- **THEN** IF a ConceptNet API request fails, THEN THE Enrichment_Service SHALL retry up to 3 times with exponential backoff

#### Scenario: WHEN an API is consistently failing (more than 5 failures in

- **THEN** WHEN an API is consistently failing (more than 5 failures in 1 minute), THE Enrichment_Service SHALL enter a circuit-breaker state and skip enrichment for 5 minutes

#### Scenario: THE Enrichment_Service SHALL emit metrics for API success ra

- **THEN** THE Enrichment_Service SHALL emit metrics for API success rate, latency, and circuit-breaker state

#### Scenario: IF enrichment is skipped due to circuit-breaker, THEN THE En

- **GIVEN** enrichment is skipped due to circuit-breaker
- **THEN** IF enrichment is skipped due to circuit-breaker, THEN THE Enrichment_Service SHALL mark the concept for later enrichment

### Requirement: Neo4j Schema for External Entities

The system SHALL support: As a database administrator, I want a clear schema for external entity storage, so that queries are efficient and data is well-organized.

#### Scenario: THE Knowledge_Graph_Service SHALL create an index on Externa

- **THEN** THE Knowledge_Graph_Service SHALL create an index on External_Entity_Node.q_number for fast lookups

#### Scenario: THE Knowledge_Graph_Service SHALL create an index on Concept

- **THEN** THE Knowledge_Graph_Service SHALL create an index on Concept_Node.wikidata_qid for fast entity resolution

#### Scenario: THE External_Entity_Node SHALL have properties: q_number, la

- **THEN** THE External_Entity_Node SHALL have properties: q_number, label, description, source (wikidata/conceptnet), fetched_at

#### Scenario: THE INSTANCE_OF relationship SHALL have properties: confiden

- **THEN** THE INSTANCE_OF relationship SHALL have properties: confidence, fetched_at

#### Scenario: THE ConceptNet relationship edges SHALL have properties: wei

- **THEN** THE ConceptNet relationship edges SHALL have properties: weight, source_uri, fetched_at
