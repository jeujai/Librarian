## Purpose

The Multimodal Librarian system processes PDF documents and builds a knowledge graph in Neo4j using ConceptNet data. Currently, the system uses a static `RelationshipType` enum with only three values (CAUSAL, HIERARCHICAL, ASSOCIATIVE) and hardcodes `RelationshipType.ASSOCIATIVE` for every ConceptNet relationship edge in the `ConceptNetValidator`. Multiple mapping functions across `kg_manager.py`, `kg_builder.py`, and `enrichment_service.py` each maintain their own incomplete, hardcoded dictionaries for classifying ConceptNet relation types.

ConceptNet is a living knowledge base with many relation types (RelatedTo, IsA, UsedFor, CapableOf, HasProperty, etc.) and new ones can appear as the dataset evolves. The system must adapt to new ConceptNet relation types without code changes, preserve the raw ConceptNet relation type for downstream consumers, and consolidate the scattered mapping logic into a single authoritative source.


### Key Terms
- **Relation_Type_Mapper**: A centralized service that classifies raw ConceptNet relation type strings into the internal `RelationshipType` taxonomy (CAUSAL, HIERARCHICAL, ASSOCIATIVE)
- **RelationshipType**: The internal three-value enum taxonomy used for graph reasoning (CAUSAL, HIERARCHICAL, ASSOCIATIVE)
- **Raw_Relation_Type**: The original ConceptNet relation type string (e.g., "IsA", "UsedFor", "CapableOf") stored verbatim on relationship edges
- **RelationshipEdge**: The Pydantic/dataclass model representing an edge in the knowledge graph
- **ConceptNetValidator**: The component that validates candidate concepts against local ConceptNet data in Neo4j and retrieves semantic relationships
- **Relation_Type_Registry**: An in-memory cache of ConceptNet relation types discovered from Neo4j at startup, enabling the system to self-adapt to whatever ConceptNet data is loaded
- **Neo4j_Client**: The async client used to execute Cypher queries against the Neo4j graph database

## Requirements

### Requirement: Store Raw ConceptNet Relation Type on RelationshipEdge

The system SHALL support: As a knowledge graph consumer, I want each relationship edge to carry the original ConceptNet relation type string, so that I can distinguish between fine-grained relation semantics beyond the three-value internal taxonomy.

#### Scenario: THE RelationshipEdge model SHALL include a `raw_relation_typ

- **THEN** THE RelationshipEdge model SHALL include a `raw_relation_type` field of type `Optional[str]` with a default value of `None`

#### Scenario: WHEN a RelationshipEdge is serialized via `to_dict`, THE Rel

- **THEN** WHEN a RelationshipEdge is serialized via `to_dict`, THE RelationshipEdge SHALL include the `raw_relation_type` value in the output dictionary

#### Scenario: WHEN a RelationshipEdge is deserialized via `from_dict`, THE

- **THEN** WHEN a RelationshipEdge is deserialized via `from_dict`, THE RelationshipEdge SHALL restore the `raw_relation_type` value from the input dictionary

#### Scenario: WHEN a RelationshipEdge is created from ConceptNet data, THE

- **THEN** WHEN a RelationshipEdge is created from ConceptNet data, THE creating component SHALL populate `raw_relation_type` with the original ConceptNet relation type string

### Requirement: Centralized Relation Type Mapping

The system SHALL support: As a developer, I want a single authoritative mapping from ConceptNet relation types to the internal RelationshipType taxonomy, so that classification logic is consistent and maintainable.

#### Scenario: THE Relation_Type_Mapper SHALL provide a `classify` method t

- **THEN** THE Relation_Type_Mapper SHALL provide a `classify` method that accepts a raw ConceptNet relation type string and returns a `RelationshipType` enum value

#### Scenario: THE Relation_Type_Mapper SHALL classify known causal relatio

- **THEN** THE Relation_Type_Mapper SHALL classify known causal relations (Causes, HasPrerequisite, MotivatedByGoal, CausesDesire, Entails, HasSubevent, HasFirstSubevent, HasLastSubevent) as `RelationshipType.CAUSAL`

#### Scenario: THE Relation_Type_Mapper SHALL classify known hierarchical r

- **THEN** THE Relation_Type_Mapper SHALL classify known hierarchical relations (IsA, PartOf, HasA, InstanceOf, MannerOf, MadeOf, DefinedAs, FormOf) as `RelationshipType.HIERARCHICAL`

#### Scenario: THE Relation_Type_Mapper SHALL classify known associative re

- **THEN** THE Relation_Type_Mapper SHALL classify known associative relations (RelatedTo, SimilarTo, Synonym, Antonym, UsedFor, CapableOf, HasProperty, AtLocation, DerivedFrom, ReceivesAction, CreatedBy, SymbolOf, LocatedNear, HasContext, DistinctFrom, EtymologicallyRelatedTo, EtymologicallyDerivedFrom) as `RelationshipType.ASSOCIATIVE`

#### Scenario: WHEN the Relation_Type_Mapper receives an unrecognized relat

- **THEN** WHEN the Relation_Type_Mapper receives an unrecognized relation type string, THE Relation_Type_Mapper SHALL return `RelationshipType.ASSOCIATIVE` as the default classification

#### Scenario: THE Relation_Type_Mapper SHALL perform case-insensitive matc

- **THEN** THE Relation_Type_Mapper SHALL perform case-insensitive matching on the input relation type string

### Requirement: Integrate Centralized Mapper into ConceptNetValidator

The system SHALL support: As a system maintainer, I want the ConceptNetValidator to use the centralized mapper instead of hardcoding ASSOCIATIVE, so that ConceptNet edges carry accurate classifications.

#### Scenario: WHEN the ConceptNetValidator creates a RelationshipEdge from

- **THEN** WHEN the ConceptNetValidator creates a RelationshipEdge from a ConceptNet query result, THE ConceptNetValidator SHALL use the Relation_Type_Mapper to determine the `relationship_type` value

#### Scenario: WHEN the ConceptNetValidator creates a RelationshipEdge from

- **THEN** WHEN the ConceptNetValidator creates a RelationshipEdge from a ConceptNet query result, THE ConceptNetValidator SHALL populate the `raw_relation_type` field with the original relation type string from the query result

### Requirement: Integrate Centralized Mapper into KG Manager and KG Builder

The system SHALL support: As a system maintainer, I want the KG Manager and KG Builder to delegate relation type classification to the centralized mapper, so that duplicate mapping dictionaries are eliminated.

#### Scenario: WHEN the ExternalKnowledgeBootstrapper in kg_manager.py clas

- **THEN** WHEN the ExternalKnowledgeBootstrapper in kg_manager.py classifies a ConceptNet predicate, THE ExternalKnowledgeBootstrapper SHALL delegate to the Relation_Type_Mapper instead of using a local mapping dictionary

#### Scenario: WHEN the RelationshipExtractor in kg_builder.py classifies a

- **THEN** WHEN the RelationshipExtractor in kg_builder.py classifies a predicate, THE RelationshipExtractor SHALL delegate to the Relation_Type_Mapper instead of using a local mapping dictionary

### Requirement: Discover and Cache Relation Types from Neo4j at Startup

The system SHALL support: As a system operator, I want the system to discover the set of ConceptNet relation types present in Neo4j at startup, so that the system self-adapts to whatever ConceptNet data is loaded without code changes.

#### Scenario: THE Relation_Type_Registry SHALL query Neo4j for distinct Co

- **THEN** THE Relation_Type_Registry SHALL query Neo4j for distinct ConceptNet relation types during initialization

#### Scenario: THE Relation_Type_Registry SHALL cache the discovered relati

- **THEN** THE Relation_Type_Registry SHALL cache the discovered relation types in memory for the lifetime of the application

#### Scenario: THE Relation_Type_Registry SHALL provide a method to retriev

- **THEN** THE Relation_Type_Registry SHALL provide a method to retrieve the set of all discovered relation types

#### Scenario: THE Relation_Type_Registry SHALL provide a method to check w

- **THEN** THE Relation_Type_Registry SHALL provide a method to check whether a given relation type string exists in the discovered set

#### Scenario: WHEN Neo4j is unavailable during initialization, THE Relatio

- **THEN** WHEN Neo4j is unavailable during initialization, THE Relation_Type_Registry SHALL log a warning and operate with an empty discovered set without preventing application startup

#### Scenario: THE Relation_Type_Registry SHALL follow the project dependen

- **THEN** THE Relation_Type_Registry SHALL follow the project dependency injection pattern by using lazy initialization and avoiding import-time connections

#### Scenario: THE Relation_Type_Registry SHALL provide a `refresh` method

- **THEN** THE Relation_Type_Registry SHALL provide a `refresh` method that re-queries Neo4j and updates the cached set of relation types

### Requirement: Backward Compatibility

The system SHALL support: As a developer, I want existing serialized RelationshipEdge data to remain valid after the model changes, so that no data migration is required.

#### Scenario: WHEN a RelationshipEdge is deserialized from data that lacks

- **THEN** WHEN a RelationshipEdge is deserialized from data that lacks a `raw_relation_type` field, THE RelationshipEdge SHALL default `raw_relation_type` to `None`

#### Scenario: WHEN a RelationshipEdge is deserialized from data with an ex

- **THEN** WHEN a RelationshipEdge is deserialized from data with an existing `relationship_type` field, THE RelationshipEdge SHALL preserve the stored `relationship_type` value
