# Requirements Document

## Introduction

The UMLS synonym matching step in the knowledge graph pipeline is the primary bottleneck during document upload processing. The query `WHERE name IN u.lower_synonyms` performs a full scan of all 1.6M UMLSConcept nodes because Neo4j RANGE indexes do not support list property lookups. This optimization replaces the list-based synonym storage with an indexed data model (separate UMLSSynonym nodes linked to UMLSConcept via relationships) so that synonym lookups use index-backed equality matching instead of full scans. The goal is to reduce UMLS bridging time from ~63 minutes to seconds.

## Glossary

- **UMLSConcept**: A Neo4j node representing a UMLS Metathesaurus concept, keyed by CUI, with properties including `preferred_name`, `lower_name`, `synonyms`, and `lower_synonyms`.
- **UMLSSynonym**: A new Neo4j node representing a single lowercased synonym string, with a RANGE-indexed `name` property, linked to its parent UMLSConcept via a HAS_SYNONYM relationship.
- **CUI**: Concept Unique Identifier from the UMLS Metathesaurus.
- **UMLS_Bridger**: The component (`umls_bridger.py`) that creates SAME_AS edges between document-extracted Concept nodes and UMLSConcept nodes by matching on preferred names and synonyms.
- **UMLS_Client**: The component (`umls_client.py`) that provides lookup methods (`search_by_name`, `batch_search_by_names`) for resolving concept names to CUIs via Neo4j.
- **UMLS_Loader**: The component (`umls_loader.py`) that imports UMLS Metathesaurus data from MRCONSO files into Neo4j as UMLSConcept nodes.
- **Synonym_Lookup_Query**: A Cypher query that resolves a concept name to a UMLSConcept by matching against synonyms.
- **SAME_AS_Edge**: A relationship between a document-extracted Concept node and a UMLSConcept node indicating they refer to the same medical concept.
- **RANGE_Index**: A Neo4j B-tree index that supports fast equality and range lookups on scalar node properties.

## Requirements

### Requirement 1: Create UMLSSynonym Node Model

**User Story:** As a system operator, I want synonym data stored as individually indexed nodes, so that synonym lookups use index-backed equality matching instead of full list scans.

#### Acceptance Criteria

1. WHEN the UMLS_Loader loads concepts from MRCONSO, THE UMLS_Loader SHALL create one UMLSSynonym node per unique lowercased synonym string with a `name` property set to the lowercased synonym value.
2. WHEN a UMLSSynonym node is created, THE UMLS_Loader SHALL create a HAS_SYNONYM relationship from the corresponding UMLSConcept node to the UMLSSynonym node.
3. THE UMLS_Loader SHALL create a RANGE index on `UMLSSynonym.name` before loading synonym data.
4. WHEN multiple UMLSConcept nodes share the same lowercased synonym string, THE UMLS_Loader SHALL reuse the single UMLSSynonym node and create a HAS_SYNONYM relationship from each UMLSConcept to that shared node.
5. THE UMLS_Loader SHALL retain the existing `synonyms` and `lower_synonyms` list properties on UMLSConcept nodes for backward compatibility until all consumers are migrated.

### Requirement 2: Migrate UMLS Bridger Synonym Queries

**User Story:** As a developer, I want the UMLS bridger to use the indexed UMLSSynonym nodes for synonym matching, so that SAME_AS edge creation completes in seconds instead of minutes.

#### Acceptance Criteria

1. WHEN the UMLS_Bridger performs synonym matching in `_match_concepts_batch`, THE UMLS_Bridger SHALL query UMLSSynonym nodes using an indexed equality match (`WHERE s.name = name`) joined to UMLSConcept via HAS_SYNONYM, instead of scanning `lower_synonyms` list properties.
2. WHEN the UMLS_Bridger matches a concept name via synonym, THE UMLS_Bridger SHALL return the same result structure (concept_name, cui, match_type, created_at) as the current implementation.
3. WHEN the UMLS_Bridger processes a batch of 200 concept names for synonym matching, THE UMLS_Bridger SHALL complete the synonym query within 5 seconds for a database containing 1.6M UMLSConcept nodes.

### Requirement 3: Migrate UMLS Client Synonym Queries

**User Story:** As a developer, I want the UMLS client lookup methods to use the indexed UMLSSynonym nodes, so that all synonym resolution paths benefit from the index optimization.

#### Acceptance Criteria

1. WHEN `search_by_name` performs a synonym lookup for a single name, THE UMLS_Client SHALL query UMLSSynonym nodes using an indexed equality match joined to UMLSConcept via HAS_SYNONYM, instead of checking `lower_synonyms` list membership.
2. WHEN `batch_search_by_names` performs Phase 2 synonym lookup for unmatched names, THE UMLS_Client SHALL query UMLSSynonym nodes using an indexed equality match joined to UMLSConcept via HAS_SYNONYM, instead of scanning `lower_synonyms` list properties.
3. THE UMLS_Client SHALL return identical result formats and semantics (name-to-CUI mappings) as the current implementation for both `search_by_name` and `batch_search_by_names`.

### Requirement 4: Data Migration for Existing UMLS Data

**User Story:** As a system operator, I want a migration path that creates UMLSSynonym nodes from the existing `lower_synonyms` data in Neo4j, so that the optimization can be applied without a full UMLS reimport.

#### Acceptance Criteria

1. WHEN the migration is executed, THE UMLS_Loader SHALL read the `lower_synonyms` list property from each existing UMLSConcept node and create corresponding UMLSSynonym nodes with HAS_SYNONYM relationships.
2. WHEN the migration creates UMLSSynonym nodes, THE UMLS_Loader SHALL use MERGE operations to ensure idempotent execution (safe to run multiple times).
3. WHEN the migration completes, THE UMLS_Loader SHALL log the total count of UMLSSynonym nodes created and HAS_SYNONYM relationships created.
4. IF the migration encounters a batch failure, THEN THE UMLS_Loader SHALL log the error, skip the failed batch, and continue processing remaining batches.

### Requirement 5: Index Creation and Schema Management

**User Story:** As a system operator, I want the required indexes created automatically, so that synonym lookups are fast from the first query after deployment.

#### Acceptance Criteria

1. WHEN the UMLS_Loader `create_indexes` method is called, THE UMLS_Loader SHALL create a RANGE index named `umls_synonym_name` on `UMLSSynonym.name` using `IF NOT EXISTS` for idempotent execution.
2. WHEN the Neo4j client `ensure_indexes` method runs at application startup, THE Neo4j_Client SHALL create the `umls_synonym_name` RANGE index on `UMLSSynonym.name` using `IF NOT EXISTS`.
3. THE RANGE_Index on `UMLSSynonym.name` SHALL support equality lookups that resolve in O(log n) time complexity instead of O(n) full scans.

### Requirement 6: Query Result Equivalence

**User Story:** As a developer, I want the optimized synonym queries to produce the same matching results as the current implementation, so that no concept matches are lost or incorrectly added.

#### Acceptance Criteria

1. FOR ALL valid concept names that match via `lower_synonyms` list membership in the current implementation, THE optimized Synonym_Lookup_Query SHALL return the same set of (name, CUI) pairs.
2. FOR ALL valid concept names that do not match any synonym in the current implementation, THE optimized Synonym_Lookup_Query SHALL return no results.
3. WHEN a concept name matches both a preferred name and a synonym on different UMLSConcept nodes, THE UMLS_Bridger SHALL return both matches (deduplicated by concept_name + CUI pair), consistent with current behavior.

### Requirement 7: Performance Target

**User Story:** As a system operator, I want the full UMLS bridging step for a typical 45-page document to complete within 60 seconds, so that total document upload time is reduced from over 2 hours to under 90 minutes.

#### Acceptance Criteria

1. WHEN the UMLS_Bridger processes a typical 45-page medical document (approximately 500-2000 unique concept names), THE UMLS_Bridger SHALL complete the full `bridge_concepts` call (matching + SAME_AS edge creation) within 60 seconds against a database containing 1.6M UMLSConcept nodes.
2. WHEN the UMLS_Client performs a `batch_search_by_names` call with 200 names, THE UMLS_Client SHALL complete the call within 5 seconds against a database containing 1.6M UMLSConcept nodes.
3. WHEN the UMLS_Client performs a `search_by_name` call for a single name, THE UMLS_Client SHALL complete the call within 500 milliseconds against a database containing 1.6M UMLSConcept nodes.
