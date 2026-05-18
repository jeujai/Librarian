## Purpose

This feature overhauls the concept extraction pipeline in the knowledge graph builder (`kg_builder.py`) to replace low-quality regex-based extraction with proper spaCy NER via the model server, retains curated regex patterns (MULTI_WORD, CODE_TERM), adds a local ConceptNet validation gate using data imported into Neo4j, and replaces noisy co-occurrence RELATED_TO relationships with real ConceptNet relationships. Existing data will be reloaded from scratch rather than migrated.


### Key Terms
- **KG_Builder**: The `KnowledgeGraphBuilder` and `ConceptExtractor` classes in `kg_builder.py` responsible for extracting concepts and relationships from document chunks.
- **Model_Server**: The dedicated model server container running spaCy `en_core_web_sm` that exposes NER via the `/nlp/process` endpoint.
- **Model_Server_Client**: The async HTTP client (`model_server_client.py`) that communicates with the Model_Server, providing `process_nlp()` and `get_entities()` methods.
- **ConceptNet_Store**: The local ConceptNet 5.7 English assertion data imported into the existing Neo4j instance under a separate label namespace (`:ConceptNetConcept`, `:ConceptNetRelation`).
- **Validation_Gate**: The post-extraction step that checks candidate concepts against the ConceptNet_Store and filters or enriches them based on their source (NER entity type, CODE_TERM, MULTI_WORD).
- **Enrichment_Service**: The existing `enrichment_service.py` that orchestrates Wikidata and ConceptNet API-based enrichment for concepts.
- **Celery_Pipeline**: The Celery background processing chain in `celery_service.py` that orchestrates document processing stages including `update_knowledge_graph_task` and `enrich_concepts_task`.
- **NER_Entity**: A named entity recognized by spaCy NER with a label such as ORG, PERSON, GPE, PRODUCT, WORK_OF_ART, EVENT, LAW, NORP, FAC, LOC.
- **Junk_Concept**: A concept extracted by the overly permissive ENTITY (`[A-Z][a-z]+`), PROCESS (`[a-z]+ing`), or PROPERTY (`[a-z]+(?:ness|ity|tion|sion)`) regex patterns that does not represent a meaningful domain concept.

## Requirements

### Requirement: Import ConceptNet English Triples into Neo4j

The system SHALL support: As a system administrator, I want to import ConceptNet 5.7 English-only assertions into the existing Neo4j instance, so that the system has a local knowledge base for concept validation without relying on external API calls.

#### Scenario: THE Import_Script SHALL download ConceptNet 5.7 English-only

- **THEN** THE Import_Script SHALL download ConceptNet 5.7 English-only assertions and parse them into concept-relation-concept triples.

#### Scenario: WHEN importing triples, THE Import_Script SHALL store concep

- **THEN** WHEN importing triples, THE Import_Script SHALL store concepts as `:ConceptNetConcept` nodes and relationships as `:ConceptNetRelation` edges in Neo4j, using a separate label namespace from document concepts.

#### Scenario: THE Import_Script SHALL create indexes on `:ConceptNetConcep

- **THEN** THE Import_Script SHALL create indexes on `:ConceptNetConcept(name)` for fast lookup by concept name.

#### Scenario: WHEN a ConceptNet concept name contains underscores or hyphe

- **THEN** WHEN a ConceptNet concept name contains underscores or hyphens, THE Import_Script SHALL normalize the name to lowercase with spaces for consistent matching.

#### Scenario: IF the import is run multiple times, THEN THE Import_Script

- **GIVEN** the import is run multiple times
- **THEN** IF the import is run multiple times, THEN THE Import_Script SHALL use MERGE operations to avoid duplicate nodes and relationships.

#### Scenario: WHEN the import completes, THE Import_Script SHALL log the t

- **THEN** WHEN the import completes, THE Import_Script SHALL log the total number of concepts and relationships imported.

### Requirement: Replace Regex Extraction with spaCy NER

The system SHALL support: As a developer, I want the concept extraction pipeline to use spaCy NER from the model server instead of overly permissive regex patterns, so that extracted concepts are meaningful named entities rather than arbitrary capitalized words or gerunds.

#### Scenario: WHEN extracting concepts from text, THE KG_Builder SHALL cal

- **THEN** WHEN extracting concepts from text, THE KG_Builder SHALL call the Model_Server_Client `get_entities()` method to obtain NER_Entity results from spaCy.

#### Scenario: THE KG_Builder SHALL remove the ENTITY pattern (`[A-Z][a-z]+

- **THEN** THE KG_Builder SHALL remove the ENTITY pattern (`[A-Z][a-z]+`), PROCESS pattern (`[a-z]+ing`), and PROPERTY pattern (`[a-z]+(?:ness|ity|tion|sion)`) from the concept extraction pipeline.

#### Scenario: THE KG_Builder SHALL retain the MULTI_WORD and CODE_TERM reg

- **THEN** THE KG_Builder SHALL retain the MULTI_WORD and CODE_TERM regex patterns for extracting domain-specific multi-word phrases and code identifiers.

#### Scenario: WHEN the Model_Server is unavailable, THE KG_Builder SHALL f

- **THEN** WHEN the Model_Server is unavailable, THE KG_Builder SHALL fall back to using only the MULTI_WORD and CODE_TERM regex patterns and log a warning.

#### Scenario: WHEN an NER_Entity is extracted, THE KG_Builder SHALL store

- **THEN** WHEN an NER_Entity is extracted, THE KG_Builder SHALL store the spaCy entity label (ORG, PERSON, GPE, PRODUCT, etc.) as the concept type.

#### Scenario: WHEN extracting concepts asynchronously, THE KG_Builder SHAL

- **THEN** WHEN extracting concepts asynchronously, THE KG_Builder SHALL use the async Model_Server_Client `get_entities()` method without blocking the event loop.

### Requirement: ConceptNet Validation Gate

The system SHALL support: As a developer, I want extracted candidate concepts to be validated against the local ConceptNet data, so that only meaningful concepts and their real relationships are stored in the knowledge graph.

#### Scenario: WHEN a candidate concept exists in the ConceptNet_Store, THE

- **THEN** WHEN a candidate concept exists in the ConceptNet_Store, THE Validation_Gate SHALL keep the concept and retrieve its ConceptNet relationships.

#### Scenario: WHEN a candidate concept does not exist in the ConceptNet_St

- **THEN** WHEN a candidate concept does not exist in the ConceptNet_Store but was identified by NER as a named entity (ORG, PERSON, GPE, PRODUCT, WORK_OF_ART, EVENT, LAW, NORP, FAC, LOC), THE Validation_Gate SHALL keep the concept as a domain-specific entity.

#### Scenario: WHEN a candidate concept does not exist in the ConceptNet_St

- **THEN** WHEN a candidate concept does not exist in the ConceptNet_Store and was not from NER, THE Validation_Gate SHALL keep the concept only if it was matched by the CODE_TERM or MULTI_WORD regex patterns.

#### Scenario: WHEN a concept is validated against ConceptNet, THE Validati

- **THEN** WHEN a concept is validated against ConceptNet, THE Validation_Gate SHALL replace co-occurrence RELATED_TO relationships with real ConceptNet relationship types (IsA, PartOf, UsedFor, HasProperty, RelatedTo, etc.).

#### Scenario: WHEN querying the ConceptNet_Store for validation, THE Valid

- **THEN** WHEN querying the ConceptNet_Store for validation, THE Validation_Gate SHALL use case-insensitive matching with normalized concept names.

### Requirement: Update the Celery Processing Pipeline

The system SHALL support: As a developer, I want the Celery background processing pipeline to use the new extraction and validation pipeline, so that newly processed documents produce high-quality knowledge graph data.

#### Scenario: WHEN `update_knowledge_graph_task` processes document chunks

- **THEN** WHEN `update_knowledge_graph_task` processes document chunks, THE Celery_Pipeline SHALL use the updated KG_Builder that calls spaCy NER via the Model_Server_Client.

#### Scenario: WHEN `update_knowledge_graph_task` processes document chunks

- **THEN** WHEN `update_knowledge_graph_task` processes document chunks, THE Celery_Pipeline SHALL apply the Validation_Gate to filter and enrich extracted concepts before persisting them to Neo4j.

#### Scenario: WHEN the Model_Server is unavailable during Celery processin

- **THEN** WHEN the Model_Server is unavailable during Celery processing, THE Celery_Pipeline SHALL fall back to MULTI_WORD and CODE_TERM extraction only and log a warning.

#### Scenario: THE Celery_Pipeline SHALL persist ConceptNet-validated relat

- **THEN** THE Celery_Pipeline SHALL persist ConceptNet-validated relationships instead of co-occurrence RELATED_TO relationships for concepts that exist in the ConceptNet_Store.

#### Scenario: WHEN the enrichment task runs after knowledge graph update,

- **THEN** WHEN the enrichment task runs after knowledge graph update, THE Enrichment_Service SHALL operate on the validated concept set produced by the new pipeline.
