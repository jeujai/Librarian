# Requirements Document

## Introduction

This feature integrates the UMLS (Unified Medical Language System) Semantic Network into the Multimodal Librarian's existing Neo4j knowledge graph. UMLS provides a comprehensive biomedical ontology with ~3.6 million concept nodes, ~105 million relationships, 127 semantic types, and 54 relationship types. By grounding document-extracted concepts against UMLS, the system gains medical concept disambiguation via CUI (Concept Unique Identifier), synonym expansion for query enhancement, semantic type validation to filter hallucinated concepts, and relationship traversal for multi-hop biomedical reasoning.

The integration follows a tiered approach: a lightweight "UMLS Lite" tier loads only the 127 semantic types and 54 relationship types from the Semantic Network, while the full Metathesaurus tier loads concept nodes from MRCONSO and relationships from MRREL. The system degrades gracefully when UMLS data is not loaded.

## Glossary

- **UMLS_Loader**: The component responsible for preprocessing and bulk-loading UMLS data files into Neo4j
- **UMLS_Client**: The local client for querying UMLS data stored in Neo4j, following the same pattern as YagoLocalClient and ConceptNetClient
- **UMLS_Linker**: The component that links document-extracted concepts to UMLS concepts during knowledge graph extraction
- **UMLS_Query_Expander**: The component that expands RAG queries using UMLS synonyms and related concepts
- **CUI**: Concept Unique Identifier, the canonical identifier for a concept in UMLS (e.g., C0004057 for "aspirin")
- **Semantic_Type**: One of 127 broad categories in the UMLS Semantic Network (e.g., T121 for Pharmacologic Substance, T047 for Disease or Syndrome)
- **Semantic_Relationship**: One of 54 relationship types in the UMLS Semantic Network (e.g., treats, causes, inhibits)
- **MRCONSO**: The UMLS Metathesaurus file containing concept names, synonyms, and CUIs
- **MRREL**: The UMLS Metathesaurus file containing relationships between concepts
- **MRSTY**: The UMLS Metathesaurus file mapping CUIs to semantic types
- **SRDEF**: The UMLS Semantic Network file defining semantic types and relationships
- **Knowledge_Graph_Builder**: The existing component that extracts concepts and relationships from document content
- **KG_Query_Engine**: The existing component that queries the Neo4j knowledge graph during RAG retrieval
- **ConceptNet_Validator**: The existing component that validates extracted concepts against ConceptNet data in Neo4j

## Requirements

### Requirement 1: UMLS Semantic Network Loading (Lite Tier)

**User Story:** As a system administrator, I want to load the UMLS Semantic Network types and relationships into Neo4j, so that the system can classify and validate biomedical concepts without requiring the full Metathesaurus.

#### Acceptance Criteria

1. WHEN the SRDEF file is provided, THE UMLS_Loader SHALL parse all 127 semantic type definitions and create UMLSSemanticType nodes in Neo4j
2. WHEN the SRDEF file is provided, THE UMLS_Loader SHALL parse all 54 semantic relationship definitions and create UMLS_SEMANTIC_REL edges between UMLSSemanticType nodes
3. THE UMLSSemanticType node SHALL store the following properties: type_id (e.g., T121), type_name (e.g., Pharmacologic Substance), definition, and tree_number
4. THE UMLS_SEMANTIC_REL edge SHALL store the following properties: relation_name (e.g., treats), relation_inverse (e.g., treated_by), and definition
5. THE UMLS_Loader SHALL complete the Semantic Network load in under 10 seconds given the small dataset size (fewer than 200 nodes)
6. THE UMLS_Loader SHALL store all UMLS data under a dedicated "umls" namespace using the node label prefix UMLSSemanticType, UMLSConcept, and relationship prefix UMLS_ to isolate from document concepts, ConceptNet, and YAGO data

### Requirement 2: UMLS Metathesaurus Concept Loading (Full Tier)

**User Story:** As a system administrator, I want to load UMLS Metathesaurus concepts into Neo4j, so that the system can match document concepts to canonical biomedical terms.

#### Acceptance Criteria

1. WHEN the MRCONSO.csv file is provided, THE UMLS_Loader SHALL parse concept entries and create UMLSConcept nodes in Neo4j
2. THE UMLS_Loader SHALL filter MRCONSO entries to include only English-language terms (LAT = ENG)
3. THE UMLSConcept node SHALL store the following properties: cui (Concept Unique Identifier), preferred_name (from TS = P and STT = PF), source_vocabulary (SAB), and suppressed flag
4. WHEN multiple names exist for the same CUI, THE UMLS_Loader SHALL store the preferred name as the primary name and additional names as a synonyms list property
5. THE UMLS_Loader SHALL use batch imports with configurable batch size (default 5000 nodes per transaction) to manage memory
6. THE UMLS_Loader SHALL support a subset mode that loads only concepts from specified source vocabularies (e.g., SNOMEDCT_US, MeSH, RXNORM) to reduce memory requirements
7. WHEN the MRSTY file is provided, THE UMLS_Loader SHALL create HAS_SEMANTIC_TYPE relationships from UMLSConcept nodes to UMLSSemanticType nodes

### Requirement 3: UMLS Relationship Loading

**User Story:** As a system administrator, I want to load UMLS relationships into Neo4j, so that the system can traverse biomedical concept connections for multi-hop reasoning.

#### Acceptance Criteria

1. WHEN the MRREL.csv file is provided, THE UMLS_Loader SHALL parse relationship entries and create typed edges between UMLSConcept nodes
2. THE UMLS_Loader SHALL map MRREL relationship types (REL and RELA fields) to Neo4j edge types using the UMLS_ prefix (e.g., UMLS_treats, UMLS_causes)
3. THE UMLS relationship edge SHALL store the following properties: rel_type (from REL), rela_type (from RELA), source_vocabulary (SAB), and cui_pair (source CUI and target CUI)
4. THE UMLS_Loader SHALL use batch imports with configurable batch size (default 10000 edges per transaction) to manage memory
5. THE UMLS_Loader SHALL support filtering relationships by source vocabulary to match the concept subset loaded in Requirement 2
6. WHERE both source and target CUIs of a relationship are not present in the loaded concept set, THE UMLS_Loader SHALL skip that relationship

### Requirement 4: UMLS Local Query Client

**User Story:** As a developer, I want a local client for querying UMLS data in Neo4j, so that I can look up concepts, synonyms, and relationships without external API calls.

#### Acceptance Criteria

1. THE UMLS_Client SHALL provide a lookup_by_cui(cui) method that returns the UMLSConcept node data for a given CUI
2. THE UMLS_Client SHALL provide a search_by_name(name) method that performs case-insensitive matching against preferred names and synonyms, returning matching CUIs
3. THE UMLS_Client SHALL provide a get_synonyms(cui) method that returns all known names for a given CUI
4. THE UMLS_Client SHALL provide a get_semantic_types(cui) method that returns the semantic type labels for a given CUI
5. THE UMLS_Client SHALL provide a get_related_concepts(cui, relationship_type, limit) method that traverses UMLS relationships and returns related CUIs
6. THE UMLS_Client SHALL provide a batch_search_by_names(names) method that performs a single Neo4j query to look up multiple concept names, returning a mapping of name to CUI
7. WHERE Neo4j is unavailable or UMLS data is not loaded, THE UMLS_Client SHALL return None for all query methods

### Requirement 5: Concept Linking During Knowledge Graph Extraction

**User Story:** As a knowledge system, I want to link document-extracted concepts to UMLS concepts during extraction, so that biomedical terms are grounded to canonical identifiers.

#### Acceptance Criteria

1. WHEN the Knowledge_Graph_Builder extracts concepts from a document chunk, THE UMLS_Linker SHALL attempt to match each concept name against UMLS using case-insensitive search
2. WHEN a UMLS match is found, THE UMLS_Linker SHALL store the CUI in the ConceptNode external_ids dictionary under the key "umls_cui"
3. WHEN a UMLS match is found, THE UMLS_Linker SHALL store the semantic type in the ConceptNode concept_type field if the concept_type is the default "ENTITY"
4. WHEN multiple UMLS matches are found for a concept name, THE UMLS_Linker SHALL select the match whose semantic type is most consistent with the document context
5. THE UMLS_Linker SHALL use the batch_search_by_names method to look up all concepts from a chunk in a single query
6. IF UMLS data is not loaded, THEN THE UMLS_Linker SHALL skip UMLS linking and allow the existing extraction pipeline to proceed unchanged

### Requirement 6: UMLS-Based Concept Validation

**User Story:** As a knowledge system, I want to use UMLS semantic types to validate extracted concepts, so that hallucinated or low-quality biomedical concepts are filtered out.

#### Acceptance Criteria

1. WHEN a concept is matched to a UMLS CUI, THE ConceptNet_Validator SHALL treat the concept as validated (equivalent to Tier 1 ConceptNet match)
2. THE ConceptNet_Validator SHALL add UMLS as a fourth validation tier: Tier 1 ConceptNet, Tier 1b UMLS, Tier 2 NER, Tier 3 Pattern
3. WHEN a concept has both a ConceptNet match and a UMLS match, THE ConceptNet_Validator SHALL prefer the UMLS semantic type for biomedical documents
4. THE ConceptNet_Validator SHALL expose a validation statistics field for kept_by_umls count in the ValidationResult

### Requirement 7: UMLS-Enhanced Query Expansion

**User Story:** As a user, I want my medical queries to find relevant results even when I use different terminology than the documents, so that synonym variations do not cause missed results.

#### Acceptance Criteria

1. WHEN a query contains a term that matches a UMLS concept, THE UMLS_Query_Expander SHALL retrieve synonyms for that concept via the UMLS_Client
2. WHEN synonyms are retrieved, THE UMLS_Query_Expander SHALL add up to 5 synonyms to the query expansion set, ranked by term frequency in the UMLS source
3. WHEN a query contains a term that matches a UMLS concept, THE UMLS_Query_Expander SHALL retrieve directly related concepts (1-hop) via UMLS relationships
4. THE UMLS_Query_Expander SHALL assign expansion terms a weight between 0.3 and 0.8 relative to the original query term, based on relationship distance and type
5. IF UMLS data is not loaded, THEN THE UMLS_Query_Expander SHALL return the original query without expansion

### Requirement 8: UMLS Semantic Type Filtering for RAG

**User Story:** As a knowledge system, I want to use UMLS semantic types to filter and re-rank RAG retrieval results, so that responses are grounded in the correct biomedical domain.

#### Acceptance Criteria

1. WHEN the KG_Query_Engine retrieves concepts for a query, THE KG_Query_Engine SHALL boost concepts whose UMLS semantic type matches the inferred query domain
2. WHEN a query is classified as biomedical (contains UMLS-matched terms), THE KG_Query_Engine SHALL apply a confidence multiplier of 1.2 to UMLS-grounded concepts in the retrieval results
3. WHEN a retrieved concept has a UMLS semantic type that contradicts the query domain (e.g., a geographic location for a drug query), THE KG_Query_Engine SHALL apply a confidence penalty of 0.7
4. IF UMLS data is not loaded, THEN THE KG_Query_Engine SHALL use the existing scoring without UMLS adjustments

### Requirement 9: Graceful Degradation

**User Story:** As a system operator, I want the system to function normally when UMLS data is not loaded, so that I can deploy the system without requiring the UMLS license or data files.

#### Acceptance Criteria

1. THE System SHALL start successfully regardless of UMLS data availability in Neo4j
2. WHERE UMLS data is not loaded, THE UMLS_Client SHALL return None for all query methods without raising exceptions
3. WHERE the UMLS_Client returns None, THE UMLS_Linker SHALL skip UMLS linking and allow the existing pipeline to proceed
4. WHERE the UMLS_Client returns None, THE UMLS_Query_Expander SHALL return the original query without expansion
5. THE System SHALL log a warning at startup if UMLS data is not detected in Neo4j
6. THE UMLS_Client SHALL be registered in the dependency injection system with both required and optional variants following the existing pattern (get_umls_client and get_umls_client_optional)

### Requirement 10: Neo4j Memory and Performance Management

**User Story:** As a system operator, I want UMLS data loading to respect Neo4j memory constraints, so that the database remains stable with the current Docker memory allocation.

#### Acceptance Criteria

1. THE UMLS_Loader SHALL provide a dry-run mode that estimates node count, relationship count, and approximate memory usage before importing
2. THE UMLS_Loader SHALL support a configurable memory limit parameter that stops the import if estimated memory usage exceeds the limit
3. THE UMLS_Loader SHALL create indexes on UMLSConcept.cui, UMLSConcept.preferred_name, and UMLSSemanticType.type_id before importing data
4. THE UMLS_Loader SHALL log import progress every 50000 records including records processed, elapsed time, and estimated time remaining
5. WHERE the full Metathesaurus exceeds available memory, THE UMLS_Loader SHALL recommend specific source vocabulary subsets (SNOMEDCT_US, MeSH, RXNORM) that fit within the memory budget

### Requirement 11: UMLS Data Management

**User Story:** As a system administrator, I want to manage the UMLS data lifecycle, so that I can update, subset, or remove UMLS data from Neo4j.

#### Acceptance Criteria

1. THE UMLS_Loader SHALL provide a remove_all_umls_data command that deletes all UMLS nodes and relationships from Neo4j
2. THE UMLS_Loader SHALL provide a get_umls_stats command that returns counts of UMLSConcept nodes, UMLSSemanticType nodes, and UMLS relationship edges
3. THE UMLS_Loader SHALL track the UMLS version and load timestamp as metadata properties on a UMLSMetadata singleton node
4. WHEN a new UMLS version is loaded, THE UMLS_Loader SHALL remove the previous version data before importing the new version
5. THE UMLS_Loader SHALL support resuming an interrupted import from the last successfully committed batch

### Requirement 12: Error Handling During Import

**User Story:** As a system operator, I want robust error handling during UMLS import, so that I can recover from failures without losing progress.

#### Acceptance Criteria

1. WHERE a batch import fails, THE UMLS_Loader SHALL retry the batch up to 3 times with exponential backoff
2. WHERE a batch import fails after retries, THE UMLS_Loader SHALL log the failed batch details and continue with the next batch
3. THE UMLS_Loader SHALL track the last successfully imported batch number in the UMLSMetadata node
4. WHERE processing resumes after a failure, THE UMLS_Loader SHALL continue from the last successful batch
5. IF the MRCONSO or MRREL file is malformed, THEN THE UMLS_Loader SHALL log a descriptive error and skip the malformed row without stopping the import

### Requirement 13: UMLS Health Check and Monitoring

**User Story:** As a system operator, I want to monitor UMLS data availability and query performance, so that I can verify the integration is working correctly.

#### Acceptance Criteria

1. THE System SHALL expose UMLS data availability in the existing health check endpoint, reporting loaded tier (none, lite, full), concept count, and relationship count
2. THE UMLS_Client SHALL log query latency for each query method using structured logging
3. THE UMLS_Client SHALL cache frequently accessed CUI lookups in memory with a configurable TTL (default 1 hour) and maximum cache size (default 50000 entries)
4. WHEN the cache size exceeds the maximum, THE UMLS_Client SHALL evict least-recently-used entries
