# Requirements Document

## Introduction

The Multimodal Librarian system processes PDF documents and builds a knowledge graph in Neo4j using ConceptNet data. Currently, the system uses a static `RelationshipType` enum with only three values (CAUSAL, HIERARCHICAL, ASSOCIATIVE) and hardcodes `RelationshipType.ASSOCIATIVE` for every ConceptNet relationship edge in the `ConceptNetValidator`. Multiple mapping functions across `kg_manager.py`, `kg_builder.py`, and `enrichment_service.py` each maintain their own incomplete, hardcoded dictionaries for classifying ConceptNet relation types.

ConceptNet is a living knowledge base with many relation types (RelatedTo, IsA, UsedFor, CapableOf, HasProperty, etc.) and new ones can appear as the dataset evolves. The system must adapt to new ConceptNet relation types without code changes, preserve the raw ConceptNet relation type for downstream consumers, and consolidate the scattered mapping logic into a single authoritative source.

## Glossary

- **Relation_Type_Mapper**: A centralized service that classifies raw ConceptNet relation type strings into the internal `RelationshipType` taxonomy (CAUSAL, HIERARCHICAL, ASSOCIATIVE)
- **RelationshipType**: The internal three-value enum taxonomy used for graph reasoning (CAUSAL, HIERARCHICAL, ASSOCIATIVE)
- **Raw_Relation_Type**: The original ConceptNet relation type string (e.g., "IsA", "UsedFor", "CapableOf") stored verbatim on relationship edges
- **RelationshipEdge**: The Pydantic/dataclass model representing an edge in the knowledge graph
- **ConceptNetValidator**: The component that validates candidate concepts against local ConceptNet data in Neo4j and retrieves semantic relationships
- **Relation_Type_Registry**: An in-memory cache of ConceptNet relation types discovered from Neo4j at startup, enabling the system to self-adapt to whatever ConceptNet data is loaded
- **Neo4j_Client**: The async client used to execute Cypher queries against the Neo4j graph database

## Requirements

### Requirement 1: Store Raw ConceptNet Relation Type on RelationshipEdge

**User Story:** As a knowledge graph consumer, I want each relationship edge to carry the original ConceptNet relation type string, so that I can distinguish between fine-grained relation semantics beyond the three-value internal taxonomy.

#### Acceptance Criteria

1. THE RelationshipEdge model SHALL include a `raw_relation_type` field of type `Optional[str]` with a default value of `None`
2. WHEN a RelationshipEdge is serialized via `to_dict`, THE RelationshipEdge SHALL include the `raw_relation_type` value in the output dictionary
3. WHEN a RelationshipEdge is deserialized via `from_dict`, THE RelationshipEdge SHALL restore the `raw_relation_type` value from the input dictionary
4. WHEN a RelationshipEdge is created from ConceptNet data, THE creating component SHALL populate `raw_relation_type` with the original ConceptNet relation type string

### Requirement 2: Centralized Relation Type Mapping

**User Story:** As a developer, I want a single authoritative mapping from ConceptNet relation types to the internal RelationshipType taxonomy, so that classification logic is consistent and maintainable.

#### Acceptance Criteria

1. THE Relation_Type_Mapper SHALL provide a `classify` method that accepts a raw ConceptNet relation type string and returns a `RelationshipType` enum value
2. THE Relation_Type_Mapper SHALL classify known causal relations (Causes, HasPrerequisite, MotivatedByGoal, CausesDesire, Entails, HasSubevent, HasFirstSubevent, HasLastSubevent) as `RelationshipType.CAUSAL`
3. THE Relation_Type_Mapper SHALL classify known hierarchical relations (IsA, PartOf, HasA, InstanceOf, MannerOf, MadeOf, DefinedAs, FormOf) as `RelationshipType.HIERARCHICAL`
4. THE Relation_Type_Mapper SHALL classify known associative relations (RelatedTo, SimilarTo, Synonym, Antonym, UsedFor, CapableOf, HasProperty, AtLocation, DerivedFrom, ReceivesAction, CreatedBy, SymbolOf, LocatedNear, HasContext, DistinctFrom, EtymologicallyRelatedTo, EtymologicallyDerivedFrom) as `RelationshipType.ASSOCIATIVE`
5. WHEN the Relation_Type_Mapper receives an unrecognized relation type string, THE Relation_Type_Mapper SHALL return `RelationshipType.ASSOCIATIVE` as the default classification
6. THE Relation_Type_Mapper SHALL perform case-insensitive matching on the input relation type string

### Requirement 3: Integrate Centralized Mapper into ConceptNetValidator

**User Story:** As a system maintainer, I want the ConceptNetValidator to use the centralized mapper instead of hardcoding ASSOCIATIVE, so that ConceptNet edges carry accurate classifications.

#### Acceptance Criteria

1. WHEN the ConceptNetValidator creates a RelationshipEdge from a ConceptNet query result, THE ConceptNetValidator SHALL use the Relation_Type_Mapper to determine the `relationship_type` value
2. WHEN the ConceptNetValidator creates a RelationshipEdge from a ConceptNet query result, THE ConceptNetValidator SHALL populate the `raw_relation_type` field with the original relation type string from the query result

### Requirement 4: Integrate Centralized Mapper into KG Manager and KG Builder

**User Story:** As a system maintainer, I want the KG Manager and KG Builder to delegate relation type classification to the centralized mapper, so that duplicate mapping dictionaries are eliminated.

#### Acceptance Criteria

1. WHEN the ExternalKnowledgeBootstrapper in kg_manager.py classifies a ConceptNet predicate, THE ExternalKnowledgeBootstrapper SHALL delegate to the Relation_Type_Mapper instead of using a local mapping dictionary
2. WHEN the RelationshipExtractor in kg_builder.py classifies a predicate, THE RelationshipExtractor SHALL delegate to the Relation_Type_Mapper instead of using a local mapping dictionary

### Requirement 5: Discover and Cache Relation Types from Neo4j at Startup

**User Story:** As a system operator, I want the system to discover the set of ConceptNet relation types present in Neo4j at startup, so that the system self-adapts to whatever ConceptNet data is loaded without code changes.

#### Acceptance Criteria

1. THE Relation_Type_Registry SHALL query Neo4j for distinct ConceptNet relation types during initialization
2. THE Relation_Type_Registry SHALL cache the discovered relation types in memory for the lifetime of the application
3. THE Relation_Type_Registry SHALL provide a method to retrieve the set of all discovered relation types
4. THE Relation_Type_Registry SHALL provide a method to check whether a given relation type string exists in the discovered set
5. WHEN Neo4j is unavailable during initialization, THE Relation_Type_Registry SHALL log a warning and operate with an empty discovered set without preventing application startup
6. THE Relation_Type_Registry SHALL follow the project dependency injection pattern by using lazy initialization and avoiding import-time connections
7. THE Relation_Type_Registry SHALL provide a `refresh` method that re-queries Neo4j and updates the cached set of relation types

### Requirement 6: Backward Compatibility

**User Story:** As a developer, I want existing serialized RelationshipEdge data to remain valid after the model changes, so that no data migration is required.

#### Acceptance Criteria

1. WHEN a RelationshipEdge is deserialized from data that lacks a `raw_relation_type` field, THE RelationshipEdge SHALL default `raw_relation_type` to `None`
2. WHEN a RelationshipEdge is deserialized from data with an existing `relationship_type` field, THE RelationshipEdge SHALL preserve the stored `relationship_type` value
