# YAGO Bulk Load Requirements

## Introduction

This specification defines the requirements for bulk-loading YAGO into Neo4j to enable local knowledge graph queries. The system will process the YAGO data dump, filter for English-labeled entities, and create a local client for querying the data. This replaces external API calls with local Neo4j queries while maintaining graceful degradation when YAGO data is unavailable.

## Glossary

- **YagoDumpProcessor**: The component responsible for downloading, streaming, and processing the YAGO data dump
- **YagoNeo4jLoader**: The component responsible for importing filtered entities and relationships into Neo4j
- **YagoLocalClient**: The local client API for querying the Neo4j-stored YAGO data (similar to ConceptNetClient)
- **Entity**: A YAGO entity (e.g., Q42 for Douglas Adams)
- **Label**: The human-readable name of an entity in a specific language
- **InstanceOf**: The relationship between an entity and the class it belongs to (P31)
- **SubclassOf**: The relationship between a class and its parent class (P279)
- **English Entity**: An entity that has a label in English (en, en-gb, or en-us)
- **YAGO Dump**: The YAGO knowledge base export file

## Requirements

### Requirement 1: Download YAGO Dump

**User Story:** As a system administrator, I want to download the YAGO data dump, so that I can process it for local storage.

#### Acceptance Criteria

1. WHEN the download process is initiated, THE YagoDumpProcessor SHALL download the latest YAGO dump from the official YAGO download server
2. THE YagoDumpProcessor SHALL support resuming interrupted downloads using HTTP range requests
3. THE YagoDumpProcessor SHALL verify file integrity using the provided checksum
4. WHEN the download completes, THE YagoDumpProcessor SHALL store the file at a configurable path

### Requirement 2: Stream Process Large Dump

**User Story:** As a system operator, I want to process the YAGO dump without loading it entirely into memory, so that I can handle the large data file.

#### Acceptance Criteria

1. THE YagoDumpProcessor SHALL process the dump in a streaming fashion using line-by-line parsing
2. THE YagoDumpProcessor SHALL use no more than 512MB of memory during processing
3. THE YagoDumpProcessor SHALL process at least 10,000 entities per second on standard hardware
4. WHEN an entity is parsed, THE YagoDumpProcessor SHALL emit a structured event containing the entity data

### Requirement 3: Filter for English Entities

**User Story:** As a data engineer, I want to filter the YAGO dump to only include entities with English labels, so that I can reduce storage requirements and improve query performance.

#### Acceptance Criteria

1. WHEN an entity is processed, THE YagoDumpProcessor SHALL check for labels in any of: en, en-gb, en-us
2. WHERE an entity has no English label, THE YagoDumpProcessor SHALL skip the entity
3. WHERE an entity has an English label, THE YagoDumpProcessor SHALL extract the following:
   - The English label (alias: name)
   - The entity ID (e.g., Q42)
   - The entity description
   - All instanceOf (P31) claims
   - All subclassOf (P279) claims
4. THE YagoDumpProcessor SHALL emit filtered entities at a rate of at least 2,000 entities per second

### Requirement 4: Import Entities into Neo4j

**User Story:** As a data engineer, I want to import filtered entities into Neo4j, so that I can query them locally.

#### Acceptance Criteria

1. WHEN a filtered entity is received, THE YagoNeo4jLoader SHALL create a node with label :YagoEntity
2. THE YagoNeo4jLoader SHALL set the following node properties:
   - `entity_id`: The YAGO entity identifier (e.g., "Q42")
   - `label`: The English label
   - `description`: The English description
   - `data`: The full JSON data as a string property
3. WHERE an entity has instanceOf claims, THE YagoNeo4jLoader SHALL create :INSTANCE_OF relationships to target entities
4. WHERE an entity has subclassOf claims, THE YagoNeo4jLoader SHALL create :SUBCLASS_OF relationships to target entities
5. THE YagoNeo4jLoader SHALL use batch imports with batch sizes of 1,000 nodes or relationships
6. THE YagoNeo4jLoader SHALL commit transactions atomically per batch

### Requirement 4.1: Dedicated YAGO Namespace

**User Story:** As a system architect, I want YAGO data stored in a dedicated Neo4j namespace, so that it remains separate from document concepts and ConceptNet data.

#### Acceptance Criteria

1. THE YagoNeo4jLoader SHALL store all YAGO entities in a dedicated "yago" namespace
2. YAGO nodes SHALL use the label `:YagoEntity` prefixed with the namespace (e.g., `yago:YagoEntity`)
3. YAGO relationships SHALL use types `:INSTANCE_OF` and `:SUBCLASS_OF` prefixed with the namespace
4. WHERE an entity has aliases, THE YagoNeo4jLoader SHALL create `:ALIAS_OF` relationships to alias nodes
5. WHERE an entity has "see also" references, THE YagoNeo4jLoader SHALL create `:SEE_ALSO` relationships
6. THE YAGO namespace SHALL be isolated from the "concepts" namespace used for document concepts
7. THE YAGO namespace SHALL be isolated from the "concept" namespace used for ConceptNet data
8. WHERE querying YAGO, THE YagoLocalClient SHALL scope queries to the yago namespace only

### Requirement 5: Create Local Query Client

**User Story:** As a developer, I want a local client API for querying YAGO data in Neo4j, so that I can replace external API calls with local queries.

#### Acceptance Criteria

1. THE YagoLocalClient SHALL provide a get_entity(entity_id) method that returns entity data from Neo4j
2. THE YagoLocalClient SHALL provide a search_entities(query) method for fuzzy search by English label
3. THE YagoLocalClient SHALL provide a get_instances_of(class_id) method returning all entities that are instances of a given class
4. THE YagoLocalClient SHALL provide a get_subclasses_of(class_id) method returning all subclasses of a given class
5. THE YagoLocalClient SHALL provide a get_related_entities(entity_id, relationship_type) method
6. WHERE Neo4j is unavailable, THE YagoLocalClient SHALL return None for all methods

### Requirement 6: Replace External API Calls

**User Story:** As a system architect, I want to replace external YAGO API calls with local Neo4j queries, so that I can reduce external API dependencies and improve response times.

#### Acceptance Criteria

1. WHERE YagoLocalClient returns valid data, THE System SHALL use the local data instead of calling the external API
2. WHERE YagoLocalClient returns None (data unavailable), THE System SHALL fall back to the external YAGO API
3. THE System SHALL maintain the same response format whether using local or external data
4. THE System SHALL log which data source was used for each query

### Requirement 7: Graceful Degradation

**User Story:** As a system operator, I want the system to function normally when YAGO data is not loaded, so that I can deploy the system without requiring the full import.

#### Acceptance Criteria

1. WHERE the YagoNeo4jLoader has not imported any data, THE YagoLocalClient SHALL return None for all query methods
2. WHERE YagoLocalClient returns None, THE System SHALL use the external YAGO API as a fallback
3. THE System SHALL start successfully regardless of YAGO data availability
4. THE System SHALL log a warning at startup if YAGO data is not loaded
5. WHERE the Neo4j database is unavailable, THE YagoLocalClient SHALL return None without crashing

### Requirement 8: Incremental Updates

**User Story:** As a data engineer, I want to apply incremental updates to the YAGO data, so that I can keep the local copy current without reimporting the entire dump.

#### Acceptance Criteria

1. THE YagoDumpProcessor SHALL support processing incremental dump files
2. WHERE an incremental update is processed, THE YagoNeo4jLoader SHALL update existing entities or create new ones
3. THE YagoNeo4jLoader SHALL remove entities that no longer exist in the incremental dump
4. THE YagoNeo4jLoader SHALL track the last processed timestamp for incremental updates

### Requirement 9: Storage Management

**User Story:** As a system operator, I want to manage the storage footprint of the YAGO data, so that I can balance between storage costs and data completeness.

#### Acceptance Criteria

1. THE YagoNeo4jLoader SHALL provide a storage estimate before import begins
2. THE YagoNeo4jLoader SHALL support importing only entities with a certain number of claims or connections
3. THE YagoNeo4jLoader SHALL support removing all YAGO data from Neo4j
4. THE YagoNeo4jLoader SHALL provide a data statistics query showing entity and relationship counts

### Requirement 10: Compatibility with Enrichment Code

**User Story:** As a developer, I want the YAGO integration to work with existing enrichment code, so that I can use YAGO data for entity enrichment without modifications.

#### Acceptance Criteria

1. THE YagoLocalClient SHALL provide the same interface as the current YAGO API client
2. THE YagoLocalClient SHALL return data in the same format as the external API
3. WHERE existing code calls the YAGO API, THE System SHALL transparently use YagoLocalClient without code changes
4. THE YagoLocalClient SHALL be registered in the dependency injection system

### Requirement 11: Error Handling

**User Story:** As a system operator, I want robust error handling during import, so that I can recover from failures without losing progress.

#### Acceptance Criteria

1. WHERE a batch import fails, THE YagoNeo4jLoader SHALL retry the batch up to 3 times
2. WHERE a batch import fails after retries, THE YagoNeo4jLoader SHALL log the failed batch and continue with the next batch
3. THE YagoNeo4jLoader SHALL track the last successfully imported entity ID
4. WHERE processing resumes, THE YagoNeo4jLoader SHALL continue from the last successful entity
5. THE YagoNeo4jLoader SHALL provide a progress percentage during import

### Requirement 12: Monitoring and Logging

**User Story:** As a system operator, I want to monitor the YAGO import process, so that I can track progress and identify issues.

#### Acceptance Criteria

1. THE YagoDumpProcessor SHALL emit structured log events for each processing stage
2. THE YagoNeo4jLoader SHALL log the import rate in entities per second
3. THE YagoNeo4jLoader SHALL log the total entity and relationship counts at completion
4. THE YagoLocalClient SHALL log query performance metrics
5. THE System SHALL expose a health check endpoint for YAGO data availability
