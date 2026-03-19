# Requirements Document

## Introduction

The UMLS Knowledge Graph Loader enables the Multimodal Librarian to ingest a targeted subset of the Unified Medical Language System (UMLS) Metathesaurus into the existing Neo4j knowledge graph. This provides a rich clinical ontology backbone (SNOMED CT, MeSH, ICD-10-CM, RxNorm, LOINC, HPO) that, when bridged to document-extracted concepts via SAME_AS edges, allows the KG-guided retrieval pipeline to traverse from user queries through clinical relationships to relevant document chunks. The system already has a partial UMLSLoader component, UMLSClient, and UMLSLinker; this feature extends them into a production-grade CLI-driven bulk loading pipeline with SAME_AS bridging, progress tracking, and resource-aware operation on a 32 GB RAM machine.

## Glossary

- **UMLS_Loader**: The CLI script (`scripts/load_umls.py`) that orchestrates parsing of RRF files and bulk-loading data into Neo4j.
- **UMLSLoader_Component**: The existing `UMLSLoader` class in `src/multimodal_librarian/components/knowledge_graph/umls_loader.py` that performs batch Neo4j writes.
- **UMLS_Bridger**: The CLI script or module responsible for creating SAME_AS edges between UMLSConcept nodes and document-extracted Concept nodes.
- **Neo4j_Client**: The existing `Neo4jClient` class in `src/multimodal_librarian/clients/neo4j_client.py` used for all Neo4j operations.
- **RRF_File**: A pipe-delimited text file from the UMLS Metathesaurus release (e.g., MRCONSO.RRF, MRREL.RRF, MRSTY.RRF, MRDEF.RRF).
- **CUI**: Concept Unique Identifier, the primary key for UMLS concepts (e.g., C0027051).
- **UMLSConcept**: A Neo4j node label for UMLS Metathesaurus concepts loaded from MRCONSO.RRF.
- **Concept**: A Neo4j node label for concepts extracted from uploaded documents by the KG builder.
- **SAME_AS_Edge**: A Neo4j relationship linking a UMLSConcept node to a document-extracted Concept node by name matching.
- **Source_Vocabulary**: A UMLS source abbreviation (e.g., SNOMEDCT_US, MSH, ICD10CM, RXNORM, LNC, HPO) used to filter which concepts and relationships to load.
- **Targeted_Vocabulary_Set**: The default set of six clinically-relevant vocabularies: SNOMEDCT_US, MSH, ICD10CM, RXNORM, LNC, HPO.
- **RELA**: The specific relationship attribute in MRREL.RRF (e.g., finding_site_of, may_treat) as opposed to the generic REL field.
- **Batch_UNWIND**: A Neo4j Cypher pattern using `UNWIND $items AS item` to process multiple records in a single transaction for performance.
- **Progress_Checkpoint**: A record stored in the UMLSMetadata Neo4j node tracking the last successfully completed batch number, enabling resume after interruption.
- **MetamorphoSys**: The UMLS installation tool that extracts a customized subset of RRF files from the full UMLS release; run manually by the user before the loader.

## Requirements

### Requirement 1: CLI Script Entry Point

**User Story:** As a system administrator, I want a standalone CLI script to load UMLS data into Neo4j, so that I can run the import independently of the running application.

#### Acceptance Criteria

1. THE UMLS_Loader SHALL provide a CLI entry point at `scripts/load_umls.py` accepting subcommands: `dry-run`, `load`, `bridge`, `stats`, and `clean`.
2. WHEN the `load` subcommand is invoked, THE UMLS_Loader SHALL accept arguments for the RRF directory path, an optional list of source vocabularies, batch size, and memory limit.
3. WHEN the `dry-run` subcommand is invoked, THE UMLS_Loader SHALL scan the RRF files and report estimated concept count, relationship count, and memory usage without writing to Neo4j.
4. WHEN the `bridge` subcommand is invoked, THE UMLS_Bridger SHALL create SAME_AS edges between UMLSConcept nodes and existing document-extracted Concept nodes.
5. WHEN the `stats` subcommand is invoked, THE UMLS_Loader SHALL query Neo4j and display counts of UMLSConcept nodes, UMLSSemanticType nodes, UMLS_REL relationships, SAME_AS edges, and the loaded tier.
6. WHEN the `clean` subcommand is invoked, THE UMLS_Loader SHALL remove all UMLS-namespaced nodes and relationships from Neo4j.
7. THE UMLS_Loader SHALL default the source vocabulary list to the Targeted_Vocabulary_Set (SNOMEDCT_US, MSH, ICD10CM, RXNORM, LNC, HPO) when no vocabularies are specified.
8. WHEN the `--neo4j-uri`, `--neo4j-user`, or `--neo4j-password` arguments are provided, THE UMLS_Loader SHALL use those values to connect to Neo4j instead of environment variable defaults.

### Requirement 2: RRF File Parsing

**User Story:** As a system administrator, I want the loader to parse standard UMLS RRF files, so that I can load data from any MetamorphoSys extraction.

#### Acceptance Criteria

1. WHEN a valid MRCONSO.RRF file is provided, THE UMLS_Loader SHALL parse pipe-delimited fields and extract CUI, language (LAT), term status (TS), string type (STT), source vocabulary (SAB), and concept name (STR) for each row.
2. THE UMLS_Loader SHALL filter MRCONSO.RRF rows to include only English-language entries (LAT = "ENG").
3. WHEN source vocabularies are specified, THE UMLS_Loader SHALL filter MRCONSO.RRF rows to include only entries where SAB matches one of the specified vocabularies.
4. WHEN a valid MRREL.RRF file is provided, THE UMLS_Loader SHALL parse pipe-delimited fields and extract CUI1, REL, CUI2, RELA, and SAB for each row.
5. WHEN a valid MRSTY.RRF file is provided, THE UMLS_Loader SHALL parse pipe-delimited fields and extract CUI and TUI for each row.
6. WHEN a valid MRDEF.RRF file is provided, THE UMLS_Loader SHALL parse pipe-delimited fields and extract CUI, SAB, and DEF for each row.
7. IF a required RRF file (MRCONSO.RRF or MRREL.RRF) is missing from the specified directory, THEN THE UMLS_Loader SHALL raise a FileNotFoundError with the missing file path.
8. IF an RRF row contains fewer fields than expected, THEN THE UMLS_Loader SHALL log a warning with the line number and skip the malformed row.

### Requirement 3: Concept Loading (MRCONSO)

**User Story:** As a system administrator, I want UMLS concepts loaded as UMLSConcept nodes in Neo4j, so that the knowledge graph contains clinical terminology for retrieval.

#### Acceptance Criteria

1. THE UMLSLoader_Component SHALL aggregate MRCONSO.RRF rows by CUI, selecting the preferred name from the row where TS = "P" and STT = "PF", and collecting remaining names as synonyms.
2. THE UMLSLoader_Component SHALL create UMLSConcept nodes using Batch_UNWIND MERGE queries keyed on the `cui` property.
3. THE UMLSLoader_Component SHALL store `preferred_name`, `synonyms` (as a list), `source_vocabulary`, and `suppressed` properties on each UMLSConcept node.
4. WHEN MRDEF.RRF is available, THE UMLSLoader_Component SHALL store the first English definition for each CUI as a `definition` property on the UMLSConcept node.
5. WHEN MRSTY.RRF is available, THE UMLSLoader_Component SHALL create HAS_SEMANTIC_TYPE relationships from UMLSConcept nodes to existing UMLSSemanticType nodes using Batch_UNWIND MERGE queries.
6. THE UMLSLoader_Component SHALL create Neo4j indexes on `UMLSConcept.cui`, `UMLSConcept.preferred_name`, and `UMLSSemanticType.type_id` before loading data.

### Requirement 4: Relationship Loading (MRREL)

**User Story:** As a system administrator, I want UMLS relationships loaded into Neo4j, so that the knowledge graph captures clinical associations like symptom-to-anatomy and drug-to-condition links.

#### Acceptance Criteria

1. THE UMLSLoader_Component SHALL create UMLS_REL relationships between UMLSConcept nodes using Batch_UNWIND MERGE queries.
2. THE UMLSLoader_Component SHALL store `rel_type` (REL field), `rela_type` (RELA field), `source_vocabulary`, and `edge_type` properties on each UMLS_REL relationship.
3. WHEN source vocabularies are specified, THE UMLSLoader_Component SHALL filter MRREL.RRF rows to include only entries where SAB matches one of the specified vocabularies.
4. THE UMLSLoader_Component SHALL skip MRREL.RRF rows where either CUI1 or CUI2 does not exist in the loaded UMLSConcept set, to avoid dangling relationships.
5. WHEN the RELA field is non-empty, THE UMLSLoader_Component SHALL set the `edge_type` property to `UMLS_{RELA}` (e.g., `UMLS_finding_site_of`); otherwise THE UMLSLoader_Component SHALL set it to `UMLS_{REL}`.
6. THE UMLSLoader_Component SHALL support loading the following clinically-relevant RELA types: `isa`, `finding_site_of`, `has_finding_site`, `causative_agent_of`, `has_causative_agent`, `may_treat`, `may_be_treated_by`, `clinically_associated_with`, `mapped_to`, `has_manifestation`, `manifestation_of`.

### Requirement 5: SAME_AS Bridging

**User Story:** As a system administrator, I want SAME_AS edges linking UMLS concepts to document-extracted concepts, so that the KG retrieval pipeline can traverse from document chunks through clinical relationships and back to relevant chunks.

#### Acceptance Criteria

1. THE UMLS_Bridger SHALL query all existing Concept nodes (document-extracted) and all UMLSConcept nodes from Neo4j.
2. THE UMLS_Bridger SHALL create SAME_AS relationships from Concept nodes to UMLSConcept nodes where the Concept `concept_name` matches the UMLSConcept `preferred_name` using case-insensitive exact matching.
3. THE UMLS_Bridger SHALL also match Concept `concept_name` against UMLSConcept `synonyms` list entries using case-insensitive exact matching.
4. THE UMLS_Bridger SHALL use Batch_UNWIND MERGE queries to create SAME_AS edges for performance.
5. THE UMLS_Bridger SHALL store `match_type` ("preferred_name" or "synonym") and `created_at` timestamp properties on each SAME_AS edge.
6. THE UMLS_Bridger SHALL log the total number of Concept nodes matched, SAME_AS edges created, and unmatched Concept nodes.
7. THE UMLS_Bridger SHALL be idempotent: running the bridge command multiple times SHALL not create duplicate SAME_AS edges.

### Requirement 6: Progress Tracking and Resume

**User Story:** As a system administrator, I want the loader to track progress and resume after interruption, so that I do not lose hours of work if the process is interrupted during a large import.

#### Acceptance Criteria

1. THE UMLSLoader_Component SHALL update the `last_batch_number` property on the UMLSMetadata singleton node after each successful batch.
2. THE UMLSLoader_Component SHALL update the `import_status` property on the UMLSMetadata node to "in_progress" at the start of loading and "complete" upon successful completion.
3. WHEN the `load` subcommand is invoked with the `--resume` flag, THE UMLS_Loader SHALL read the `last_batch_number` from UMLSMetadata and skip already-completed batches.
4. THE UMLS_Loader SHALL log progress at regular intervals including: records processed, concepts/relationships created, elapsed time, estimated time remaining, and current batch number.
5. IF a batch fails after all retry attempts, THEN THE UMLSLoader_Component SHALL log the batch number and error, increment the failed batch counter, and continue with the next batch.
6. THE UMLSLoader_Component SHALL retry failed batches up to 3 times with exponential backoff delays of 1, 2, and 4 seconds.

### Requirement 7: Resource-Aware Operation

**User Story:** As a system administrator running on a 32 GB RAM machine, I want the loader to operate within memory constraints, so that the import does not crash the system or other services.

#### Acceptance Criteria

1. WHEN the `--memory-limit` argument is provided, THE UMLS_Loader SHALL estimate memory usage before loading and abort with a warning if the estimate exceeds the limit.
2. THE UMLS_Loader SHALL default the batch size to 5000 for concept loading and 10000 for relationship loading.
3. THE UMLS_Loader SHALL use streaming file reads (line-by-line iteration) for all RRF files to avoid loading entire files into memory.
4. THE UMLS_Loader SHALL log memory usage estimates during the dry-run subcommand, including per-vocabulary breakdowns when multiple vocabularies are selected.
5. IF the `dry-run` estimate exceeds the memory budget, THEN THE UMLS_Loader SHALL recommend a reduced vocabulary set that fits within the budget.

### Requirement 8: Neo4j Configuration Documentation

**User Story:** As a system administrator, I want clear documentation on Neo4j memory configuration changes needed for UMLS data, so that I can prepare the database before running the import.

#### Acceptance Criteria

1. THE UMLS_Loader SHALL include a `--check-config` flag that queries Neo4j for current heap size, page cache size, and database store size, and reports whether they meet recommended minimums for the targeted vocabulary set.
2. WHEN the `--check-config` flag detects insufficient configuration, THE UMLS_Loader SHALL print specific recommended values: heap size of 5-6 GB, page cache of 3 GB.
3. THE UMLS_Loader SHALL print a summary of recommended `docker-compose.yml` environment variable changes for Neo4j when configuration is insufficient.

### Requirement 9: Data Cleanup

**User Story:** As a system administrator, I want to cleanly remove all UMLS data from Neo4j, so that I can re-import a newer UMLS version or free up resources.

#### Acceptance Criteria

1. WHEN the `clean` subcommand is invoked, THE UMLS_Loader SHALL delete all UMLS_REL relationships, HAS_SEMANTIC_TYPE relationships, UMLS_SEMANTIC_REL relationships, SAME_AS edges between UMLSConcept and Concept nodes, UMLSConcept nodes, UMLSSemanticType nodes, UMLSRelationshipDef nodes, and UMLSMetadata nodes.
2. THE UMLS_Loader SHALL delete relationships before nodes to avoid constraint violations.
3. WHEN the `clean` subcommand is invoked with the `--confirm` flag, THE UMLS_Loader SHALL proceed without interactive confirmation; otherwise THE UMLS_Loader SHALL prompt the user for confirmation.
4. THE UMLS_Loader SHALL log the count of deleted nodes and relationships for each category.

### Requirement 10: Load Ordering and Orchestration

**User Story:** As a system administrator, I want the load process to execute steps in the correct order, so that all dependencies (indexes, semantic types, concepts) exist before dependent data (relationships, SAME_AS edges) is created.

#### Acceptance Criteria

1. THE UMLS_Loader SHALL execute the `load` subcommand in the following order: (a) create indexes, (b) load semantic network from SRDEF if present, (c) load concepts from MRCONSO, (d) load semantic type edges from MRSTY, (e) load definitions from MRDEF, (f) load relationships from MRREL.
2. WHEN the `load` subcommand completes, THE UMLS_Loader SHALL print a summary including total concepts loaded, relationships loaded, SAME_AS edges created (if `--bridge` flag is set), elapsed time, and any failed batches.
3. WHEN the `--bridge` flag is passed to the `load` subcommand, THE UMLS_Loader SHALL automatically run the SAME_AS bridging step after relationship loading completes.
4. IF the semantic network (SRDEF) file is not present, THEN THE UMLS_Loader SHALL log a warning and skip the semantic network loading step without aborting the import.
